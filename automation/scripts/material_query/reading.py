"""AI 阅读工作流：持久工作记录与规范知识分离，语义判断由调用者提供。

每次动作在单会话锁内进行，使用固定范围与累计账本；跨 CLI 进程不复活
MQ 游标、不清零消费。正文通过既有 Reader/Assembler 回源；持久文件保存
候选身份、交付范围、AI笔记和重排诊断（含条件原文片段），不存完整原正文副本。
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
import re
import time
import uuid

from memory import owners
from memory.errors import MemoryError
from .assembly import Assembler
from .budget import DEFAULT_BUDGET, Ledger
from .contracts import AssociationOptions, Budget, DefinitionRef, FixedRef, QueryRequest, Scope
from .coordinator import current_scope_allows, required_scope_allows, envelope, failure
from .validation import QueryError, object_fields, parse
from .wire import digest, json_value
from . import query_plan, reranking


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
        # 宿主权限可以扩大，但保存的阅读会话仍只在原授权域内回源。
        # 收紧临时请求的硬上限，不修改RS的query/access或其他并发查询。
        if session.get('access') is not None:
            ceiling = request.scope_ceiling.owner_ids
            allowed = set(session['access'])
            if ceiling is not None:
                allowed.intersection_update(ceiling)
            request = replace(request, scope_ceiling=replace(request.scope_ceiling, owner_ids=tuple(sorted(allowed))))
        state = self.app._new(request)
        self.state_ids.append(state.query_id)
        state.ledger = self.ledger
        state.result = {'warnings': [], 'issues': []}
        return state

    def dispatch(self, action, raw):
        if action == 'template':
            object_fields(raw, set())
            scope = Scope(None, None, None, None, None, None, None, False, (), (), None, None)
            # 只在建立新请求模板时读取进程缓存的默认值。start/resume继续
            # 使用请求及RS固定预算，设置变化不能隐式提高已授权的费用上限。
            from workspace_settings import read
            preferences = read(self.root)['settings']['reading']
            budget = parse(preferences['budget'], Budget)
            query = QueryRequest(DefinitionRef('full', '1'), '填写实际问题', (), scope, scope, 'exploration',
                AssociationOptions('off', 'existing-relations', '1', 0, 0.0, None), budget, 'current', preferences['result_limit'], 'reject', (), '')
            return envelope({'session_id': 'RS-' + str(uuid.uuid4()), 'goal': '填写实际目标',
                             'mode': 'owner_document',
                             'strategy': preferences.get('strategy', 'standard'),
                             'association': preferences.get('association', {'enabled': True, 'max_rounds': 3}),
                             'association_text': '',
                             'context': preferences.get('context', {'max_owners': 10, 'note_max_tokens': 6000}),
                             'screening': preferences.get('screening', {'regular_windows': 3, 'max_windows': 4, 'batch_owners': 10}),
                             'conditions': [], 'query': json_value(query),
                             'reranking': reranking.settings(preferences['reranking'])})
        if action == 'start':
            return self.start(raw)
        if action == 'list':
            from .reading_catalog import listing
            return listing(self, raw)
        # 查看动作从锁内读取最新版本，不要求用户先找UUID之外的修订号。
        # 它仍重新授权和累计读取费用，但不写AI决定或伪造一个新的语义修订。
        viewing = action in {'view', 'delegate', 'handoff'}
        common = {'session_id', 'expected_revision', 'request_id'}
        extras = {'recall': {'question', 'keywords', 'scope', 'reason'},
                  'read': {'candidate_ids'}, 'note': {'candidate_id', 'summary', 'connection', 'details', 'uncertainties'},
                  'decide': {'direction', 'reason', 'next_step', 'outcome', 'human_decision'}, 'resume': set(), 'page': set(),
                  'view': set(), 'delegate': set(), 'handoff': set(),
                  'bind': {'owner_id', 'checkpoint_ref'}, 'archive': {'archived', 'reason'}}
        extras.update(configure={'strategy', 'association_text'}, assess={'candidate_id', 'useful', 'reason'},
                      **{'assess-owners': {'assessments'}, 'recall-fulltext': set()}, synthesize={'research_note'})
        require(action in extras, '未知阅读动作')
        if action == 'delegate':
            object_fields(raw, {'session_id', 'host_supports_subagents'}, {'expected_revision'})
            require(type(raw['host_supports_subagents']) is bool, 'host_supports_subagents必须是布尔值')
        elif action == 'handoff':
            object_fields(raw, {'session_id'}, {'expected_revision', 'max_chars', 'candidate_ids'})
            require(type(raw.get('max_chars', 12000)) is int and 512 <= raw.get('max_chars', 12000) <= 30000,
                    'max_chars必须是512..30000整数')
        elif action in {'read', 'note'} and 'owner_id' in raw:
            object_fields(raw, common | {'owner_id'}, {'source_refs'} if action == 'read' else {'research_note', 'candidate_ids'})
        else:
            object_fields(raw, {'session_id'} if viewing else common | extras[action],
                          query_plan.PLAN_FIELDS | {'reranking', 'retrieval_kind', 'association_text', 'clue_sources'} if action == 'recall' else {'association'} if action == 'configure' else {'notes_only'} if action == 'view' else ())
        if action == 'view':
            require(type(raw.get('notes_only', False)) is bool, 'notes_only必须是布尔值')
        file = path(self.root, raw['session_id'], 'HEAD.json')
        if not viewing:
            text(raw['request_id'], 'request_id')
            require(type(raw['expected_revision']) is int and raw['expected_revision'] > 0, '缺少预期版本')
        elif 'expected_revision' in raw:
            require(type(raw['expected_revision']) is int and raw['expected_revision'] > 0, '预期版本必须为正整数')
        if not file.exists():
            raise QueryError('SOURCE_MISSING', '阅读会话不存在')
        with locked(file):
            session = read_json(file)
            # 不允许跨可信授权域读取保存的工作笔记。相同域内仍逐项重核来源。
            if not self.can_access(session):
                raise QueryError('DENIED', '阅读会话不属于当前授权域')
            from . import reading_owner
            owner_mode = session.get('mode') == 'owner_document'
            self.ledger = reading_owner.OperationLedger(parse(session['query']['budget'], Budget)) if owner_mode else Ledger(parse(session['query']['budget'], Budget))
            if not owner_mode:
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
                if 'expected_revision' in raw and raw['expected_revision'] != session['revision']:
                    raise QueryError('CONFLICT', '阅读记录已有新版本，请先续接')
                require(not session.get('archived') or action in {'view', 'resume', 'archive', 'handoff'}, '已归档会话请先恢复，再继续工作')
                method = 'notes_view' if action == 'view' and raw.get('notes_only') else 'resume' if action == 'view' else action
                require(owner_mode or action not in {'configure', 'assess', 'assess-owners', 'recall-fulltext', 'synthesize'},
                        'legacy会话不支持新策略动作')
                if owner_mode and method in reading_owner.ACTIONS:
                    value = reading_owner.execute(self, method, session, raw, state)
                else:
                    value = getattr(self, method)(session, raw, state)
                if not viewing:
                    session['revision'] += 1
                    session['updated_at'] = datetime.now(timezone.utc).isoformat()
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
            if result.get('value') is not None and (not viewing or action in {'view', 'handoff'}):
                # 快照是尽力生成的派生文件；失败不能把已保存的HEAD伪报成失败。
                from .reading_snapshot import write_snapshot
                try:
                    write_snapshot(self.root, session)
                except (OSError, ValueError, QueryError, MemoryError):
                    result.setdefault('warnings', []).append('阅读记录已保存/读取，但可读Markdown副本更新失败；以RS当前版本为准')
            return result

    def access(self):
        return None if self.app.access_owner_ids is None else sorted(self.app.access_owner_ids)

    def can_access(self, session):
        """当前可信权限须覆盖原域；窄域不得读取原无限域会话。"""
        current, original = self.access(), session['access']
        return current is None or original is not None and set(original).issubset(current)

    def start(self, raw):
        object_fields(raw, {'session_id', 'goal', 'conditions', 'query'}, {'owner_id', 'checkpoint_ref', 'reranking', 'mode', 'context', 'screening', 'strategy', 'association', 'association_text'})
        mode = raw.get('mode', 'legacy')
        require(mode in {'legacy', 'owner_document'}, '未知阅读模式')
        from .reading_owner import context_settings
        from .owner_screening import settings as screening_settings
        context = context_settings(raw.get('context'))
        from .reading_strategy import validate
        from workspace_settings import read
        defaults = read(self.root)['settings']['reading'] if mode == 'owner_document' else {}
        strategy = validate(raw.get('strategy', defaults.get('strategy', 'standard')),
                            raw.get('association', defaults.get('association', {'enabled': False, 'max_rounds': 3})),
                            raw.get('association_text', ''))
        text(raw['goal'], 'goal')
        strings(raw['conditions'], 'conditions')
        request = parse(raw['query'], QueryRequest)
        ranking_options = reranking.settings(raw.get('reranking', defaults.get('reranking')))
        screening = screening_settings(raw.get('screening', defaults.get('screening')))
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
                           requests={}, expansion_count=0, phase='ready', **binding, archived=False,
                           reranking=ranking_options, mode=mode, context=context,
                           screening=screening,
                           owner_progress={}, owner_notes={}, delivered_blocks=[])
            if mode == 'owner_document':
                session.update(strategy)
            session['updated_at'] = datetime.now(timezone.utc).isoformat()
            save(file, session)
        if mode == 'owner_document' and strategy['strategy'] == 'quick':
            guidance = ('先用reading-assess逐条判断实际交付的发现筛选片段，再仅按已接受固定片段写research_note；'
                        'quick不读取Owner全文。发现不足时只提示reading-recall-fulltext，未经用户选择不执行。')
        elif mode == 'owner_document':
            guidance = ('先用reading-assess-owners批量判断发现包；relevant Owner再reading-read。'
                        '发现不足时只提示reading-recall-fulltext，未经用户选择不执行。')
        else:
            guidance = GUIDANCE
        return envelope({'session_id': session['session_id'], 'revision': 1, 'next_action': 'recall',
                         'guidance': guidance}, state=state)

    def reauthorize(self, session, state):
        """笔记会透露源内容；恢复/重试也不能跳过源闭包与版本复查。"""
        reader = self.app.reader(state)
        self.check_binding(session, state, reader=reader)
        for row in session['candidates'].values():
            ref = parse(row['ref'], FixedRef)
            if ref.kind == 'owner':
                from .reading_owner import read_native_reference
                from .coordinator import owner_allowed
                _text, native = read_native_reference(reader, ref)
                owner = reader.owner(ref.id)
                if not owner_allowed(owner, replace(state.request, freshness='fixed')):
                    raise QueryError('DENIED', '已存Owner不再满足阅读范围')
                # read_native_reference accepts both the current native-byte
                # fingerprint and the legacy evidence fingerprint.  A
                # successful read is therefore the authoritative freshness
                # check; comparing only one of those digests would falsely
                # mark a current Owner discovery hit stale.
                row['stale'] = False
                continue
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
                elif source.kind == 'owner':
                    from .reading_owner import read_native_reference
                    read_native_reference(reader, source)
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
            from .reading_owner import OperationLedger, ReferenceAssembler
            assembler_type = ReferenceAssembler if isinstance(self.ledger, OperationLedger) else Assembler
            assembler = assembler_type(reader, self.ledger,
                lambda record: current_scope_allows(reader, record, state.request),
                required_allowed=lambda record: required_scope_allows(reader, record, state.request))
            for ref in refs:
                assembler.add_record(ref, definition, state.request.question)
            packet = self.app._packet(state, assembler)
            packet['definition'] = asdict(definition)
            links = {ref.id: self.link(reader, ref) for ref in refs}
        return packet, links

    def candidate_packet(self, candidate, lane, lane_state):
        """重排和实际交付共用固定正文，避免拿展示摘录当模型输入。"""
        ref = parse(candidate['refs'][0], FixedRef)
        selected = []
        if lane == 'technical':
            for hit in candidate.get('hits', []):
                for source in hit.get('representation_refs', []):
                    if source['id'] == ref.id and (source.get('locator') or '').startswith('block:'):
                        block = parse(source, FixedRef)
                        if block not in selected:
                            selected.append(block)
        definition = DefinitionRef('section' if selected else 'full', '1')
        # 重排无块命中时读取完整技术单元；旧off链路仍保持摘要预览语义。
        packet, links = self.packet(lane_state, selected or [ref], definition)
        parts = []
        for part in packet['parts']:
            if part['group'] == 'gaps':
                continue
            for source in part['refs']:
                parts.append({'text': part['markdown'], 'title': part.get('heading', ''),
                              'ref': source, 'role': part['group']})
        model_text = '\n\n'.join([candidate['title'], *[
            part.get('heading', '') + '\n' + part['markdown'] for part in packet['parts'] if part['group'] != 'gaps']])
        return {'key': digest(candidate['refs'][0]), 'text': model_text, 'complete': packet['complete'],
                'evidence_parts': parts, 'packet': packet, 'links': links, 'definition': definition}

    def recall(self, session, raw, state, *, continuation=False, frozen_plan=None, frozen_ranking=None):
        text(raw['question'], 'question')
        text(raw['reason'], 'reason')
        strings(raw['keywords'], 'keywords')
        require(session['phase'] in {'ready', 'expand'}, '先记录下一步/失败缺口，再决定是否补查')
        expanding = session['phase'] == 'expand'
        scope = parse(raw['scope'], Scope)
        # 保留原始显式排除，即使扩展直接范围也不丢失用户的反选。
        base = state.request
        ranking_options = reranking.settings(frozen_ranking if frozen_ranking is not None else
                                             raw.get('reranking', session.get('reranking')))
        require(ranking_options['mode'] == 'off' or ranking_options['candidate_limit'] >= base.result_limit,
                '重排candidate_limit必须至少覆盖交付result_limit；不会默默扩大候选窗')
        pool_limit = ranking_options['candidate_limit'] if ranking_options['mode'] != 'off' else base.result_limit
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
                                ranking_strategy='rrf', ranking_version='1', result_limit=pool_limit)
                retrieval_started = time.perf_counter()
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
                                   'elapsed_ms': (time.perf_counter() - retrieval_started) * 1000,
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
            prepared_by_key = {}
            if ranking_options['mode'] != 'off' and candidates:
                input_started = time.perf_counter()
                prepared = []
                # packet() owns its active-time scope. Nesting another scope
                # would raise CONFLICT and incorrectly turn every input into a gap.
                for candidate in candidates[:pool_limit]:
                    try:
                        item = self.candidate_packet(candidate, lane, lane_state)
                    except (QueryError, MemoryError) as exc:
                        if exc.code in {'BUDGET', 'CANCELLED', 'DENIED', 'ACCESS_DENIED'}:
                            raise
                        item = {'key': digest(candidate['refs'][0]), 'text': '', 'complete': False, 'evidence_parts': []}
                        gaps.append('重排必要正文不可用，未据摘要替代完整条件')
                    prepared.append(item)
                input_ms = (time.perf_counter() - input_started) * 1000
                expected_model = None
                if continuation and session['rounds']:
                    previous_lane = next((item for item in session['rounds'][-1]['lanes'] if item['source'] == lane), {})
                    if 'ranking' in previous_lane:
                        expected_model = previous_lane['ranking'].get('model') or {'unavailable': True}
                with self.ledger.active():
                    ranked = reranking.rank(self.root, raw['question'], prepared, ranking_options, self.ledger,
                                            expected_model=expected_model)
                prepared_by_key = {item['key']: item for item in ranked['items']}
                candidates_by_key = {digest(candidate['refs'][0]): candidate for candidate in candidates}
                candidates = [candidates_by_key[item['key']] for item in ranked['items']] + candidates[pool_limit:]
                info['ranking'] = {**ranked['diagnostics'], 'input_ms': input_ms}
                query_plan.charge_diagnostics(self.ledger, info['ranking'])
                gaps.extend(ranked['gaps'])
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
                    prepared = prepared_by_key.get(digest(candidate['refs'][0]))
                    if prepared and 'packet' in prepared:
                        packet, links, definition = prepared['packet'], prepared['links'], prepared['definition']
                    else:
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
                               protected_terms=plan['protected_terms'], packet_complete=packet['complete'])
                    if prepared:
                        query_plan.charge_diagnostics(self.ledger, prepared['ranking'])
                        row['ranking'] = deepcopy(prepared['ranking'])
                    row['contributors'] = list({digest(item): item for item in row['contributors'] + packet['contributors']}.values())
                    output.append({'candidate_id': key, 'title': row['title'], 'ref': row['ref'], 'link': row['link'],
                        'source': lane, 'reading_form': definition.key, 'packet': packet, 'channels': candidate['channels'],
                        'hits': candidate['hits'], 'query_sources': candidate['query_sources'],
                        'fusion_score': candidate['fusion_score'], 'condition_check': 'pending',
                        'protected_terms': plan['protected_terms'],
                        **({'ranking': prepared['ranking']} if prepared else {})})
                    if not packet['complete']:
                        gaps.append(key + '正文未完整交付，请检查packet缺口')
                except (QueryError, MemoryError) as exc:
                    gaps.append('候选正文未交付：' + str(exc))
        round_info['reranking'] = ranking_options
        # 保存本轮真实交付缺口，轻量handoff才可说明覆盖限制；仅保存已有
        # 诊断文字，不复制材料包。旧轮次没有该字段时不得反推“没有缺口”。
        round_info['gaps'] = list(dict.fromkeys(gaps))
        query_plan.charge_diagnostics(self.ledger, ranking_options)
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
                           continuation=True, frozen_plan=previous.get('query_plan'),
                           frozen_ranking=previous.get('reranking', {'mode': 'off'}))

    def read(self, session, raw, state):
        ids = strings(raw['candidate_ids'], 'candidate_ids')
        require(bool(ids) and all(key in session['candidates'] for key in ids), '只能读取已交付候选')
        output, gaps = [], []
        for key in dict.fromkeys(ids):
            row = session['candidates'][key]
            read_state = self.state(session, query=asdict(replace(state.request, scope=parse(json_value(row['scope']), Scope))))
            packet, links = self.packet(read_state, [replace(parse(row['ref'], FixedRef), locator=None)], DefinitionRef('full', '1'))
            # 条件诊断/此前笔记仍可能引用旧包的必要依赖；不完整全文不能清掉闭包。
            row['contributors'] = list({digest(ref): ref for ref in row.get('contributors', []) + packet['contributors']}.values())
            row['full_delivered'] = packet['complete']
            row['packet_complete'] = packet['complete']
            row['read_gaps'] = [] if packet['complete'] else ['完整阅读包存在缺口']
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

    def delegate(self, session, raw, state):
        """返回宿主委派意图，程序不spawn、不替旧RS提高预算或宣称已执行。"""
        from workspace_settings import read
        from .reading_delegation import delegate_value, serialized_size
        with self.ledger.active():
            collaboration = read(self.root)['settings']['collaboration']
            value = delegate_value(session, collaboration['subagents'], raw['host_supports_subagents'],
                                   collaboration['subagent_requirements'])
            # 身份字段在纯构造函数中预先加入，外层update不会增加未计量字符。
            self.ledger.charge('output_chars', serialized_size(value))
        return value

    def handoff(self, session, raw, state):
        """只交付实际笔记的单份有界上下文；不复用resume的全候选/历史输出。"""
        from .reading_delegation import handoff_value, serialized_size
        with self.ledger.active():
            value = handoff_value(session, raw.get('max_chars', 12000), raw.get('candidate_ids'))
            # 扣费在返回前完成；预算不足由dispatch回滚语义并保留已消费IO，
            # failure不携带value，因此不会把超预算笔记泄漏到错误返回。
            self.ledger.charge('output_chars', serialized_size(value))
        return value

    def notes_view(self, session, raw, state):
        """供工作台浏览笔记；省去召回诊断，仍支付原会话累计费用。"""
        from .reading_snapshot import notes_value
        from .reading_delegation import serialized_size
        value = notes_value(session)
        self.ledger.charge('output_chars', serialized_size(value))
        return value

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
                               'protected_terms': row.get('protected_terms', []),
                               **({'ranking': deepcopy(row['ranking'])} if 'ranking' in row else {})})
            lines.append(f"- [{row['title']}](<{row['link']}>) · {status}" + (' · 来源已变' if row.get('stale') else ''))
        markdown = '\n\n'.join(lines)
        query_plan.charge_diagnostics(self.ledger, {
            'plans': [round_info['query_plan'] for round_info in session['rounds'] if 'query_plan' in round_info],
            'routes': [lane['routes'] for round_info in session['rounds'] for lane in round_info['lanes'] if 'routes' in lane],
            'ranking': [lane['ranking'] for round_info in session['rounds'] for lane in round_info['lanes'] if 'ranking' in lane],
            'ranking_options': [round_info['reranking'] for round_info in session['rounds'] if 'reranking' in round_info],
            'candidate_diagnostics': [{key: row[key] for key in ('hits', 'query_sources', 'condition_check', 'protected_terms', 'ranking') if key in row}
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
