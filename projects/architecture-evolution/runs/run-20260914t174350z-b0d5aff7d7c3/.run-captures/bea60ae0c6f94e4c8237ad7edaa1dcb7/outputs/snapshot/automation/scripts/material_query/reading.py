"""AI 阅读工作流：持久工作记录与规范知识分离，语义判断由调用者提供。

每次动作在单会话锁内进行，使用固定范围与累计账本；跨 CLI 进程不复活
MQ 游标、不清零消费。正文通过既有 Reader/Assembler 回源，持久文件只存
候选身份、交付范围及 AI 笔记，不存另一份原始技术正文。
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
import json
import os
import re
import uuid

from memory import owners
from memory.errors import MemoryError
from .assembly import Assembler
from .budget import DEFAULT_BUDGET, Ledger
from .contracts import AssociationOptions, Budget, DefinitionRef, FixedRef, QueryRequest, Scope
from .coordinator import current_scope_allows, required_scope_allows, envelope, failure
from .validation import QueryError, object_fields, parse
from .wire import digest, json_value
from . import query_plan


BASE = '.local/reading-sessions'
LANES = ('overview_experience', 'process', 'technical')
GUIDANCE = ('先读返回的正文；可保留直接用途或有具体连接理由的间接启发。'
            '长链连接逐步注明依据和假设。保留候选后 reading-read 读完整记录，'
            '再 reading-note 保存理解、连接和必要细节。有可检验下一步先执行，失败后定向扩查。')


def require(condition, message):
    if not condition:
        raise QueryError('VALIDATION', message)


def text(value, name, *, empty=False):
    require(isinstance(value, str) and (empty or bool(value.strip())) and len(value) <= 12000,
            name + '必须为有界文本')
    return value


def strings(value, name):
    require(isinstance(value, list) and len(value) <= 100, name + '必须为有界数组')
    return [text(item, name) for item in value]


def path(root, sid, name):
    require(isinstance(sid, str) and re.fullmatch(r'RS-[0-9a-f-]{36}', sid), '阅读会话身份无效')
    return owners.safe_path(root, f'{BASE}/{sid}/{name}')


def read_json(file):
    if file.stat().st_size > 4 * 1024 * 1024:
        raise QueryError('BUDGET', '阅读工作记录超过4MiB；请整理并开始新的问题会话')
    value = json.loads(file.read_text(encoding='utf-8'))
    signature = value.pop('storage_digest')
    if digest(value) != signature:
        raise QueryError('CONFLICT', '阅读工作记录指纹不一致')
    return value


def save(file, value):
    """同盘临时文件原子切换；已发布版本另行保留，不覆盖历史。"""
    data = {**value, 'storage_digest': digest(value)}
    raw = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    require(len(raw.encode('utf-8')) <= 4 * 1024 * 1024, '阅读工作记录超过存储上限')
    temporary = file.with_name('.pending-' + uuid.uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, file)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(file):
    lock = file.with_name('operation.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise QueryError('CONFLICT', '阅读会话已有操作；遗留锁需核对进程后处理') from exc
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


class Reading:
    def __init__(self, coordinator):
        self.app = coordinator
        self.root = coordinator.root
        self.state_ids = []

    def state(self, session, *, query=None):
        request = parse(json_value(query or session['query']), QueryRequest)
        state = self.app._new(request)
        self.state_ids.append(state.query_id)
        state.ledger = self.ledger
        state.result = {'warnings': [], 'issues': []}
        return state

    def dispatch(self, action, raw):
        if action == 'template':
            object_fields(raw, set())
            scope = Scope(None, None, None, None, None, None, None, False, (), (), None, None)
            budget = replace(DEFAULT_BUDGET, model_calls=12, model_tokens=6144, model_input_tokens=6144)
            query = QueryRequest(DefinitionRef('full', '1'), '填写实际问题', (), scope, scope, 'exploration',
                AssociationOptions('off', 'existing-relations', '1', 0, 0.0, None), budget, 'current', 10, 'reject', (), '')
            return envelope({'session_id': 'RS-' + str(uuid.uuid4()), 'goal': '填写实际目标',
                             'conditions': [], 'query': json_value(query)})
        if action == 'start':
            return self.start(raw)
        if action == 'list':
            from .reading_catalog import listing
            return listing(self, raw)
        # 查看动作从锁内读取最新版本，不要求用户先找UUID之外的修订号。
        # 它仍重新授权和累计读取费用，但不写AI决定或伪造一个新的语义修订。
        viewing = action == 'view'
        common = {'session_id', 'expected_revision', 'request_id'}
        extras = {'recall': {'question', 'keywords', 'scope', 'reason'},
                  'read': {'candidate_ids'}, 'note': {'candidate_id', 'summary', 'connection', 'details', 'uncertainties'},
                  'decide': {'direction', 'reason', 'next_step', 'outcome', 'human_decision'}, 'resume': set(), 'page': set(),
                  'view': set(), 'bind': {'owner_id', 'checkpoint_ref'}, 'archive': {'archived', 'reason'}}
        require(action in extras, '未知阅读动作')
        object_fields(raw, {'session_id'} if viewing else common | extras[action],
                      query_plan.PLAN_FIELDS if action == 'recall' else ())
        file = path(self.root, raw['session_id'], 'HEAD.json')
        if not viewing:
            text(raw['request_id'], 'request_id')
            require(type(raw['expected_revision']) is int and raw['expected_revision'] > 0, '缺少预期版本')
        if not file.exists():
            raise QueryError('SOURCE_MISSING', '阅读会话不存在')
        with locked(file):
            session = read_json(file)
            # 不允许跨可信授权域读取保存的工作笔记。相同域内仍逐项重核来源。
            if session['access'] != self.access():
                raise QueryError('DENIED', '阅读会话不属于当前授权域')
            self.ledger = Ledger(parse(session['query']['budget'], Budget))
            self.ledger.used.update(session['consumed'])
            self.ledger.elapsed_seconds = session['consumed']['wall_ms'] / 1000
            state = self.state(session)
            original = deepcopy(session)
            signature = digest({'action': action, 'raw': raw})
            try:
                self.ledger.charge('read_bytes', file.stat().st_size)
                with self.ledger.active():
                    self.reauthorize(session, state)
                previous = None if viewing else session['requests'].get(raw['request_id'])
                if previous is not None:
                    if previous != signature:
                        raise QueryError('CONFLICT', '同一请求身份不能提交不同内容')
                    # 重试不重新检索或重复写笔记；正文可用新的 read 动作重新交付。
                    return envelope({'session_id': session['session_id'], 'revision': session['revision'],
                                     'replayed': True, 'next_action': 'resume'}, state=state)
                if not viewing and raw['expected_revision'] != session['revision']:
                    raise QueryError('CONFLICT', '阅读记录已有新版本，请先续接')
                require(not session.get('archived') or action in {'view', 'resume', 'archive'}, '已归档会话请先恢复，再继续工作')
                value = getattr(self, 'resume' if viewing else action)(session, raw, state)
                if not viewing:
                    session['revision'] += 1
                    session['requests'][raw['request_id']] = signature
                value.update(session_id=session['session_id'], revision=session['revision'])
                result = envelope(json_value(value), state=state, status='partial' if value.get('gaps') else 'ok',
                                  warnings=value.get('gaps', []))
            except (QueryError, MemoryError) as exc:
                # 拒绝的语义修改回滚，但已经发生的 IO/模型费用必须保存。
                session = original
                result = failure(exc, state)
            finally:
                session['consumed'] = self.ledger.snapshot()
                if session['revision'] != original['revision']:
                    archive = path(self.root, session['session_id'], f"revision-{session['revision']}-{uuid.uuid4().hex}.json")
                    save(archive, session)
                save(file, session)
            return result

    def access(self):
        return None if self.app.access_owner_ids is None else sorted(self.app.access_owner_ids)

    def start(self, raw):
        object_fields(raw, {'session_id', 'goal', 'conditions', 'query'}, {'owner_id', 'checkpoint_ref'})
        text(raw['goal'], 'goal')
        strings(raw['conditions'], 'conditions')
        request = parse(raw['query'], QueryRequest)
        require(request.purpose == 'exploration', '阅读工作流用于探索；正式结论另走证据准入')
        require(request.freshness == 'current', '新阅读会话从当前修订开始')
        # 固定多路策略；用户给出的硬预算不自动扩大。缺模型时回执报告降级。
        request = replace(request, channels=('identity', 'lexical', 'dense'), definition=DefinitionRef('full', '1'),
                          association=replace(request.association, mode='off'), content_source=None,
                          missing_policy='reject', fallback_definitions=())
        state = self.app._new(request)
        self.state_ids.append(state.query_id)
        self.ledger = state.ledger
        binding = {'owner_id': raw.get('owner_id'), 'checkpoint_ref': raw.get('checkpoint_ref')}
        self.check_binding(binding, state)
        file = path(self.root, raw['session_id'], 'HEAD.json')
        file.parent.mkdir(parents=True, exist_ok=True)
        with locked(file):
            if file.exists():
                raise QueryError('CONFLICT', '阅读会话已存在，请续接；不会重置预算')
            session = dict(schema_version=1, session_id=raw['session_id'], revision=1, goal=raw['goal'],
                           conditions=raw['conditions'], query=asdict(request), access=self.access(),
                           consumed=state.ledger.snapshot(), rounds=[], candidates={}, notes={}, decisions=[],
                           requests={}, expansion_count=0, phase='ready', **binding, archived=False)
            save(file, session)
        return envelope({'session_id': session['session_id'], 'revision': 1, 'next_action': 'recall',
                         'guidance': GUIDANCE}, state=state)

    def reauthorize(self, session, state):
        """笔记会透露源内容；恢复/重试也不能跳过源闭包与版本复查。"""
        reader = self.app.reader(state)
        self.check_binding(session, state, reader=reader)
        for row in session['candidates'].values():
            ref = parse(row['ref'], FixedRef)
            record = reader.record(ref)
            if not required_scope_allows(reader, record, replace(state.request, freshness='fixed')):
                raise QueryError('DENIED', '已存材料不再满足阅读范围')
            _, manifest = reader.store.head_manifest(reader.owner(record['owner_id']))
            latest = (manifest or {}).get('record_heads', {}).get(ref.id)
            row['stale'] = not latest or latest['record_hash'] != ref.sha256
            for source in row.get('contributors', []):
                source = parse(source, FixedRef)
                if source.kind == 'file':
                    reader.file_bytes(source)
                else:
                    dependency = reader.record(source)
                    if not required_scope_allows(reader, dependency, replace(state.request, freshness='fixed')):
                        raise QueryError('DENIED', '已存正文依赖不再满足阅读范围')
                    _, dependency_manifest = reader.store.head_manifest(reader.owner(dependency['owner_id']))
                    current = (dependency_manifest or {}).get('record_heads', {}).get(source.id)
                    row['stale'] |= not current or current['record_hash'] != source.sha256

    def check_binding(self, value, state, *, reader=None):
        """归属是导航，不扩展查询授权；检查点引用沿用现有FixedRef格式。

        旧RS没有绑定字段仍可读取，必须显式bind后才归入某Owner清单。
        检查点保存历史版本用于说明续接依据，不将RS混入MEM证据引用。
        """
        reader = reader or self.app.reader(state)
        oid, checkpoint = value.get('owner_id'), value.get('checkpoint_ref')
        if oid is not None:
            text(oid, 'owner_id')
            owner = reader.owner(oid)
            require(not owner.get('temporary'), '先采用稳定Owner再绑定阅读会话')
        if checkpoint is not None:
            require(oid is not None, '检查点必须属于明确Owner')
            ref = parse(checkpoint, FixedRef)
            require(ref.kind == 'record', '检查点必须为固定记录')
            record = reader.record(ref)
            require(record['kind'] == 'checkpoint' and record['owner_id'] == oid, '检查点不属于绑定对象')

    def bind(self, session, raw, state):
        require(raw['owner_id'] is not None, '绑定需要明确Owner')
        self.check_binding(raw, state)
        session.update(owner_id=raw['owner_id'], checkpoint_ref=deepcopy(raw['checkpoint_ref']))
        return {'owner_id': session['owner_id'], 'checkpoint_ref': session['checkpoint_ref']}

    def archive(self, session, raw, state):
        require(type(raw['archived']) is bool, 'archived必须是布尔值')
        text(raw['reason'], 'reason')
        session.update(archived=raw['archived'], archive_reason=raw['reason'])
        return {'archived': session['archived']}

    def link(self, reader, ref):
        """从已校验清单定位固定记录路径，不接受客户端文件名。"""
        record = reader.record(ref)
        owner = reader.owner(record['owner_id'])
        _, manifest = reader.store.head_manifest(owner)
        while manifest:
            entry = manifest['record_heads'].get(ref.id)
            if entry and entry['revision'] == ref.revision and entry['record_hash'] == ref.sha256:
                return reader.store.path(owner, entry['path']).as_posix()
            parent = manifest['parent_commit_id']
            manifest = reader.store._manifest(owner, parent, manifest['parent_manifest_hash']) if parent else None
        raise QueryError('SOURCE_MISSING', '固定来源链接不可定位')

    def packet(self, state, refs, definition):
        with self.ledger.active():
            reader = self.app.reader(state)
            assembler = Assembler(reader, self.ledger,
                lambda record: current_scope_allows(reader, record, state.request),
                required_allowed=lambda record: required_scope_allows(reader, record, state.request))
            for ref in refs:
                assembler.add_record(ref, definition, state.request.question)
            packet = self.app._packet(state, assembler)
            packet['definition'] = asdict(definition)
            links = {ref.id: self.link(reader, ref) for ref in refs}
        return packet, links

    def recall(self, session, raw, state, *, continuation=False, frozen_plan=None):
        text(raw['question'], 'question')
        text(raw['reason'], 'reason')
        strings(raw['keywords'], 'keywords')
        require(session['phase'] in {'ready', 'expand'}, '先记录下一步/失败缺口，再决定是否补查')
        expanding = session['phase'] == 'expand'
        scope = parse(raw['scope'], Scope)
        # 保留原始显式排除，即使扩展直接范围也不丢失用户的反选。
        base = state.request
        scope = replace(scope, excluded_refs=tuple(set(scope.excluded_refs + base.scope.excluded_refs)),
                        excluded_owner_ids=tuple(set(scope.excluded_owner_ids + base.scope.excluded_owner_ids)),
                        exclude_ids=tuple(set(scope.exclude_ids + base.scope.exclude_ids)))
        plan = deepcopy(frozen_plan) if frozen_plan is not None else query_plan.build(self.root, self.ledger, raw)
        query_plan.charge_diagnostics(self.ledger, plan)
        round_info = dict(question=raw['question'], keywords=raw['keywords'], reason=raw['reason'],
                          scope=asdict(scope), lanes=[], query_plan=plan)
        output, gaps = [], []
        # 分层独立候选窗；共享同一累计账本，顺序执行避免 Qdrant local 进程锁争用。
        for lane in LANES:
            batches, route_info = [], []
            known = {digest(row['ref']) for row in session['candidates'].values()} if continuation else set()
            for route in query_plan.routes(plan):
                query = replace(base, scope=scope, question=route['question'], keywords=tuple(route['keywords']),
                                content_source=lane, channels=(route['channel'],),
                                ranking_strategy='rrf', ranking_version='1')
                route_state = self.state(session, query=asdict(query))
                self.app._run_search(route_state)
                result = route_state.result
                # 已交付固定版本只用于分页跳过，绝不变成权限排除；依赖仍可读取。
                if continuation:
                    while result.get('value') and result['value'].get('next_cursor') and all(
                            digest(item['refs'][0]) in known for item in result['value']['candidates']):
                        result = self.app.resume(route_state.query_id, result['value']['next_cursor'])
                batches.append((route, [item for item in (result.get('value') or {}).get('candidates', [])
                                        if digest(item['refs'][0]) not in known]))
                warnings = list(result['warnings'])
                if result.get('code') and result['status'] not in {'ok', 'partial'}:
                    warnings.append(route['id'] + '未完成：' + result['code'])
                route_info.append({'query_source': route['id'], 'status': result['status'],
                                   'warnings': warnings,
                                   'has_more': bool((result.get('value') or {}).get('next_cursor'))})
            candidates = query_plan.fuse(batches)
            lane_warnings = list(dict.fromkeys(w for info in route_info for w in info['warnings']))
            info = {'source': lane, 'status': 'partial' if lane_warnings else 'ok', 'warnings': lane_warnings,
                    'has_more': any(info['has_more'] for info in route_info) or len(candidates) > base.result_limit,
                    'routes': route_info}
            query_plan.charge_diagnostics(self.ledger, route_info)
            # Packet selection uses the original natural question, not a keyword
            # route's empty question. Source authorization is still Coordinator's.
            lane_state = self.state(session, query=asdict(replace(base, scope=scope,
                question=raw['question'], keywords=tuple(raw['keywords']), content_source=lane)))
            round_info['lanes'].append(info)
            gaps.extend(lane_warnings)
            if info['has_more']:
                gaps.append(lane + '候选窗口仍有未交付材料；使用reading-page继续，预算累计，不代表全库已读')
            for candidate in candidates[:base.result_limit]:
                ref = parse(candidate['refs'][0], FixedRef)
                key = 'RC-' + digest(asdict(ref))[:24]
                selected = []
                if lane == 'technical':
                    for hit in candidate.get('hits', []):
                        for source in hit.get('representation_refs', []):
                            if source['id'] == ref.id and (source.get('locator') or '').startswith('block:'):
                                block = parse(source, FixedRef)
                                if block not in selected:
                                    selected.append(block)
                # 仅说明命中时不猜测技术块；交付摘要并明确待完整阅读。
                definition = DefinitionRef('section' if selected else 'unit_digest' if lane == 'technical' else 'full', '1')
                try:
                    query_plan.charge_diagnostics(self.ledger, {
                        'hits': candidate['hits'], 'query_sources': candidate['query_sources'],
                        'fusion_score': candidate['fusion_score'], 'condition_check': 'pending',
                        'protected_terms': plan['protected_terms']})
                    packet, links = self.packet(lane_state, selected or [ref], definition)
                    row = session['candidates'].setdefault(key, {'ref': asdict(ref), 'title': candidate['title'],
                        'full_delivered': False, 'contributors': []})
                    # A later round can rediscover this fixed record; retain its
                    # earlier hit origins, with plan fingerprints distinguishing
                    # reused route names such as original:lexical.
                    hits = list({digest(item): item for item in row.get('hits', []) + candidate['hits']}.values())
                    sources = list({digest(item): item for item in row.get('query_sources', []) + candidate['query_sources']}.values())
                    row.update(link=links[ref.id], lane=lane, scope=asdict(scope), hits=hits,
                               query_sources=sources, condition_check='pending',
                               protected_terms=plan['protected_terms'])
                    row['contributors'] = list({digest(item): item for item in row['contributors'] + packet['contributors']}.values())
                    output.append({'candidate_id': key, 'title': row['title'], 'ref': row['ref'], 'link': row['link'],
                        'source': lane, 'reading_form': definition.key, 'packet': packet, 'channels': candidate['channels'],
                        'hits': candidate['hits'], 'query_sources': candidate['query_sources'],
                        'fusion_score': candidate['fusion_score'], 'condition_check': 'pending',
                        'protected_terms': plan['protected_terms']})
                    if not packet['complete']:
                        gaps.append(key + '正文未完整交付，请检查packet缺口')
                except (QueryError, MemoryError) as exc:
                    gaps.append('候选正文未交付：' + str(exc))
        session['rounds'].append(round_info)
        if expanding:
            session['expansion_count'] += 1
        session['phase'] = 'review'
        return {'candidates': output, 'coverage': round_info, 'gaps': list(dict.fromkeys(gaps)), 'guidance': GUIDANCE}

    def page(self, session, raw, state):
        """跨进程继续同一发现轮：跳过已交付记录，不重用失效 MQ 游标。

        续批仍有实际索引工作并累计计量；只有明确扩查才改变问题与直接范围。
        """
        require(session['phase'] == 'review' and bool(session['rounds']), '当前没有可续读的候选轮')
        previous = session['rounds'][-1]
        require(any(lane['has_more'] for lane in previous['lanes']), '当前候选窗口已结束；需要补查请先说明缺口')
        scope = parse(json_value(previous['scope']), Scope)
        session['phase'] = 'ready'
        return self.recall(session, {'question': previous['question'], 'keywords': previous['keywords'],
                                    'scope': json_value(scope), 'reason': '同一查询继续未交付候选'}, state,
                           continuation=True, frozen_plan=previous.get('query_plan'))

    def read(self, session, raw, state):
        ids = strings(raw['candidate_ids'], 'candidate_ids')
        require(bool(ids) and all(key in session['candidates'] for key in ids), '只能读取已交付候选')
        output, gaps = [], []
        for key in dict.fromkeys(ids):
            row = session['candidates'][key]
            read_state = self.state(session, query=asdict(replace(state.request, scope=parse(json_value(row['scope']), Scope))))
            packet, links = self.packet(read_state, [replace(parse(row['ref'], FixedRef), locator=None)], DefinitionRef('full', '1'))
            row['contributors'] = packet['contributors']
            row['full_delivered'] = packet['complete']
            row['link'] = links[row['ref']['id']]
            output.append({'candidate_id': key, 'link': row['link'], 'packet': packet})
            if not packet['complete']:
                gaps.append(key + '完整阅读存在缺口，不能提交已完整阅读笔记')
        return {'readings': output, 'gaps': gaps}

    def note(self, session, raw, state):
        text(raw['candidate_id'], 'candidate_id')
        row = session['candidates'].get(raw['candidate_id'])
        require(row is not None and row['full_delivered'], '先完整交付正文，再提交阅读理解')
        require(not row.get('stale'), '材料已有新版本，请重新召回并阅读')
        text(raw['summary'], 'summary')
        object_fields(raw['connection'], {'kind', 'explanation', 'chain'})
        require(raw['connection']['kind'] in {'direct', 'inspiration', 'not_useful'}, '连接类别无效')
        text(raw['connection']['explanation'], 'connection.explanation')
        strings(raw['connection']['chain'], 'chain')
        strings(raw['uncertainties'], 'uncertainties')
        require(isinstance(raw['details'], list) and len(raw['details']) <= 50, '必要细节数量无效')
        with self.ledger.active():
            reader = self.app.reader(state)
            record = reader.record(parse(row['ref'], FixedRef))
            block_ids = {block['block_id'] for block in record['payload'].get('blocks', [])}
            for detail in raw['details']:
                object_fields(detail, {'text', 'reason', 'block_ids'})
                text(detail['text'], 'detail.text')
                text(detail['reason'], 'detail.reason')
                selected = strings(detail['block_ids'], 'detail.block_ids')
                require(set(selected) <= block_ids, '必要细节引用不存在的正文块')
        session['notes'][raw['candidate_id']] = {key: deepcopy(raw[key]) for key in ('summary', 'connection', 'details', 'uncertainties')}
        session['notes'][raw['candidate_id']]['authorship'] = 'caller_ai_or_human; not_semantically_verified'
        return {'saved': True, 'candidate_id': raw['candidate_id'], 'link': row['link']}

    def decide(self, session, raw, state):
        require(raw['direction'] in {'proceed', 'expand', 'ask_user', 'finish'}, '下一步类别无效')
        text(raw['reason'], 'reason')
        text(raw['next_step'], 'next_step')
        text(raw['outcome'], 'outcome', empty=True)
        text(raw['human_decision'], 'human_decision', empty=True)
        direction = raw['direction']
        if direction == 'expand':
            require(bool(raw['outcome'].strip()), '扩大召回前必须说明尝试结果或当前具体缺口')
        # 扩查次数是事实记录，不代替AI/用户对方向、成本和风险的判断。
        # 已有ask_user仍需真实意见才能继续；升级不追认旧会话获得授权。
        if session['phase'] == 'ask_user' and direction not in {'ask_user', 'finish'}:
            require(bool(raw['human_decision'].strip()), '仍在等待用户意见；不能自行越过已提出的问题')
        session['phase'] = direction
        session['decisions'].append({key: raw[key] for key in ('reason', 'next_step', 'outcome', 'human_decision')} | {'direction': direction})
        return {'direction': direction, 'next_step': raw['next_step'],
                'needs_user_input': direction == 'ask_user', 'expansion_count': session['expansion_count']}

    def resume(self, session, raw, state):
        lines = ['# 当前问题', session['goal'], f"阅读记录 {session['session_id']} · 读取版本 r{session['revision']}（本次视图）",
                 '\n## 条件', *['- ' + item for item in session['conditions']], '\n## 已读理解与必要细节']
        for key, note in session['notes'].items():
            row = session['candidates'][key]
            lines += [f"\n### {row['title']}", f"[固定原记录](<{row['link']}>) · r{row['ref']['revision']}",
                      note['summary'], '\n连接（' + note['connection']['kind'] + '）：' + note['connection']['explanation']]
            if row.get('stale'):
                lines += ['**来源已有新修订：以下是旧版阅读理解，继续使用前须重新阅读核对。**']
            lines += ['- 连接步骤/假设：' + item for item in note['connection']['chain']]
            for item in note['details']:
                lines += ['\n必要细节：' + item['text'], '保留原因：' + item['reason'], '块定位：' + ', '.join(item['block_ids'])]
            lines += ['- 待验证：' + item for item in note['uncertainties']]
        lines += ['\n## 尝试与下一步']
        lines += [f"- {item['direction']}：{item['next_step']}；理由：{item['reason']}；结果/缺口：{item['outcome']}" for item in session['decisions']]
        lines += ['\n## 阅读清单']
        candidates = []
        for key, row in session['candidates'].items():
            status = '已记录理解' if key in session['notes'] else '已交付全文，待记录理解' if row['full_delivered'] else '候选，待完整阅读'
            candidates.append({'candidate_id': key, 'title': row['title'], 'link': row['link'], 'ref': row['ref'],
                               'status': status, 'stale': row.get('stale', False), 'hits': row.get('hits', []),
                               'query_sources': row.get('query_sources', []),
                               'condition_check': row.get('condition_check', 'pending'),
                               'protected_terms': row.get('protected_terms', [])})
            lines.append(f"- [{row['title']}](<{row['link']}>) · {status}" + (' · 来源已变' if row.get('stale') else ''))
        markdown = '\n\n'.join(lines)
        query_plan.charge_diagnostics(self.ledger, {
            'plans': [round_info['query_plan'] for round_info in session['rounds'] if 'query_plan' in round_info],
            'routes': [lane['routes'] for round_info in session['rounds'] for lane in round_info['lanes'] if 'routes' in lane],
            'candidate_diagnostics': [{key: row[key] for key in ('hits', 'query_sources', 'condition_check', 'protected_terms')}
                                      for row in candidates]})
        self.ledger.charge('output_chars', len(markdown))
        return {'context_markdown': markdown, 'phase': session['phase'], 'round_count': len(session['rounds']),
                'owner_id': session.get('owner_id'), 'checkpoint_ref': session.get('checkpoint_ref'),
                'archived': session.get('archived', False), 'candidates': candidates,
                'unnoted_candidate_ids': [key for key in session['candidates'] if key not in session['notes']],
                'coverage': session['rounds'], 'guidance': GUIDANCE,
                'gaps': ['已有阅读材料发生修订，请核对旧版理解'] if any(row.get('stale') for row in session['candidates'].values()) else []}


def dispatch(coordinator, action, raw):
    reading = Reading(coordinator)
    try:
        return reading.dispatch(action, raw)
    except (QueryError, MemoryError) as exc:
        return failure(exc)
    except (OSError, ValueError, KeyError) as exc:
        return failure(QueryError('SOURCE_MISSING', '阅读工作记录不可用或请求结构错误'))
    finally:
        # 持久身份是 RS，不向调用者暴露这些短期 MQ 状态；完成后释放容量。
        for query_id in reading.state_ids:
            coordinator.store.states.pop(query_id, None)
