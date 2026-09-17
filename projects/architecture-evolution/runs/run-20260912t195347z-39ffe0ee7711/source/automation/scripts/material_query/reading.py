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
        common = {'session_id', 'expected_revision', 'request_id'}
        extras = {'recall': {'question', 'keywords', 'scope', 'reason'},
                  'read': {'candidate_ids'}, 'note': {'candidate_id', 'summary', 'connection', 'details', 'uncertainties'},
                  'decide': {'direction', 'reason', 'next_step', 'outcome', 'human_decision'}, 'resume': set(), 'page': set()}
        require(action in extras, '未知阅读动作')
        object_fields(raw, common | extras[action])
        file = path(self.root, raw['session_id'], 'HEAD.json')
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
                previous = session['requests'].get(raw['request_id'])
                if previous is not None:
                    if previous != signature:
                        raise QueryError('CONFLICT', '同一请求身份不能提交不同内容')
                    # 重试不重新检索或重复写笔记；正文可用新的 read 动作重新交付。
                    return envelope({'session_id': session['session_id'], 'revision': session['revision'],
                                     'replayed': True, 'next_action': 'resume'}, state=state)
                if raw['expected_revision'] != session['revision']:
                    raise QueryError('CONFLICT', '阅读记录已有新版本，请先续接')
                value = getattr(self, action)(session, raw, state)
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
        object_fields(raw, {'session_id', 'goal', 'conditions', 'query'})
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
        file = path(self.root, raw['session_id'], 'HEAD.json')
        file.parent.mkdir(parents=True, exist_ok=True)
        with locked(file):
            if file.exists():
                raise QueryError('CONFLICT', '阅读会话已存在，请续接；不会重置预算')
            session = dict(schema_version=1, session_id=raw['session_id'], revision=1, goal=raw['goal'],
                           conditions=raw['conditions'], query=asdict(request), access=self.access(),
                           consumed=state.ledger.snapshot(), rounds=[], candidates={}, notes={}, decisions=[],
                           requests={}, expansion_count=0, phase='ready')
            save(file, session)
        return envelope({'session_id': session['session_id'], 'revision': 1, 'next_action': 'recall',
                         'guidance': GUIDANCE}, state=state)

    def reauthorize(self, session, state):
        """笔记会透露源内容；恢复/重试也不能跳过源闭包与版本复查。"""
        reader = self.app.reader(state)
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

    def recall(self, session, raw, state, *, continuation=False):
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
        round_info = dict(question=raw['question'], keywords=raw['keywords'], reason=raw['reason'], scope=asdict(scope), lanes=[])
        output, gaps = [], []
        # 分层独立候选窗；共享同一累计账本，顺序执行避免 Qdrant local 进程锁争用。
        for lane in LANES:
            query = replace(base, scope=scope, question=raw['question'], keywords=tuple(raw['keywords']), content_source=lane)
            lane_state = self.state(session, query=asdict(query))
            self.app._run_search(lane_state)
            result = lane_state.result
            if continuation:
                # 重建当前固定范围的候选页；已交付记录不是权限排除项，否则
                # 它们作为新命中的必要依赖时也会被错误拒绝。
                known = {row['ref']['id'] for row in session['candidates'].values()}
                while result.get('value') and result['value'].get('next_cursor') and all(
                        item['refs'][0]['id'] in known for item in result['value']['candidates']):
                    result = self.app.resume(lane_state.query_id, result['value']['next_cursor'])
            info = {'source': lane, 'status': result['status'], 'warnings': result['warnings'],
                    'has_more': bool((result.get('value') or {}).get('next_cursor'))}
            round_info['lanes'].append(info)
            gaps.extend(result['warnings'])
            if info['has_more']:
                gaps.append(lane + '候选窗口仍有未交付材料；使用reading-page继续，预算累计，不代表全库已读')
            for candidate in (result.get('value') or {}).get('candidates', []):
                ref = parse(candidate['refs'][0], FixedRef)
                if continuation and ref.id in known:
                    continue
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
                    packet, links = self.packet(lane_state, selected or [ref], definition)
                    row = session['candidates'].setdefault(key, {'ref': asdict(ref), 'title': candidate['title'],
                        'full_delivered': False, 'contributors': []})
                    row.update(link=links[ref.id], lane=lane, scope=asdict(scope))
                    row['contributors'] = list({digest(item): item for item in row['contributors'] + packet['contributors']}.values())
                    output.append({'candidate_id': key, 'title': row['title'], 'ref': row['ref'], 'link': row['link'],
                        'source': lane, 'reading_form': definition.key, 'packet': packet, 'channels': candidate['channels']})
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
                                    'scope': json_value(scope), 'reason': '同一查询继续未交付候选'}, state, continuation=True)

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
            if session['expansion_count'] >= 1 and not raw['human_decision'].strip():
                direction = 'ask_user'
        session['phase'] = direction
        session['decisions'].append({key: raw[key] for key in ('reason', 'next_step', 'outcome', 'human_decision')} | {'direction': direction})
        return {'direction': direction, 'next_step': raw['next_step'],
                'needs_user_input': direction == 'ask_user', 'expansion_count': session['expansion_count']}

    def resume(self, session, raw, state):
        lines = ['# 当前问题', session['goal'], '\n## 条件', *['- ' + item for item in session['conditions']], '\n## 已读理解与必要细节']
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
        markdown = '\n\n'.join(lines)
        self.ledger.charge('output_chars', len(markdown))
        return {'context_markdown': markdown, 'phase': session['phase'], 'round_count': len(session['rounds']),
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
