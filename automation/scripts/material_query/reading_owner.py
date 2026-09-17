"""Owner级阅读：检索诊断留在RS，完整文稿交给reader，研究笔记交给主Agent。

上下文限制与工程预算分离：工程账本每次操作新建，仍受服务器硬上限、
取消和活动时间检查约束。内部检索文本不冒充已交付AI上下文。
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
import base64
import json
import re

from memory.evidence_adapter import iter_refs
from memory import index
from .assembly import Assembler
from .budget import Ledger, SERVER_LIMITS
from .contracts import DefinitionRef, FixedRef, Scope
from .coordinator import current_scope_allows, required_scope_allows
from .legacy_adapter import fixed_record, from_legacy
from .validation import QueryError, object_fields, parse
from .wire import digest, json_value


ACTIONS = {'recall', 'page', 'read', 'note', 'resume', 'notes_view', 'handoff', 'configure', 'assess',
           'assess-owners', 'recall-fulltext', 'synthesize'}
DEFAULT_CONTEXT = {'max_owners': 10, 'note_max_tokens': 6000}


def context_settings(value):
    """数量/笔记窗口固定在会话；不把当前配置隐式写入既有RS。"""
    value = deepcopy(DEFAULT_CONTEXT if value is None else value)
    object_fields(value, set(DEFAULT_CONTEXT))
    for key, minimum, maximum in [('max_owners', 1, 100), ('note_max_tokens', 512, 50000)]:
        if type(value[key]) is not int or not minimum <= value[key] <= maximum:
            raise QueryError('VALIDATION', key + '必须为正整数且不超过' + str(maximum))
    return value


class OperationLedger(Ledger):
    """只在受控内部组装期间暂停AI输出计费；IO和模型等保护仍正常。"""
    internal_depth = 0

    @contextmanager
    def internal(self):
        self.internal_depth += 1
        try:
            yield
        finally:
            self.internal_depth -= 1

    def charge(self, key, amount, **kwargs):
        if self.internal_depth and key == 'output_chars':
            self.checkpoint()
            return
        return super().charge(key, amount, **kwargs)

    def remaining(self, key):
        if self.internal_depth and key == 'output_chars':
            return SERVER_LIMITS.output_chars
        return super().remaining(key)


class ReferenceAssembler(Assembler):
    """文稿保持作者正文顺序；图片只给固定引用，显式展开才交付图像。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, defer_evidence=True)

    def add(self, group, title, text, selector, ref, *, figures=()):
        return super().add(group, title, text, selector, ref, figures=())


def owner_packet(reading, session, state, refs):
    """在既有授权/固定版本Reader之上组装正文，不自行解析任意文件。"""
    with reading.ledger.active(), reading.ledger.internal():
        reader = reading.app.reader(state)
        assembler = ReferenceAssembler(reader, reading.ledger,
            lambda record: required_scope_allows(reader, record, state.request),
            required_allowed=lambda record: required_scope_allows(reader, record, state.request))
        for ref in refs:
            assembler.add_record(ref, DefinitionRef('full', '1'), state.request.question)
        packet = reading.app._packet(state, assembler)
        # Reader has already checked source closure. Keep declared evidence refs
        # available for deliberate expansion without putting their bytes in text.
        sources = list(packet['contributors']) + [asdict(ref) for ref in refs]
        reference_map = []
        for record in reader.records.values():
            for legacy in iter_refs({'sources': record.get('sources', []), 'payload': record.get('payload', {})}):
                ref, _ = from_legacy(legacy)
                sources.append(asdict(ref))
            for number, figure in enumerate(record.get('payload', {}).get('figures', [])):
                ref, _ = from_legacy(figure['ref'])
                reference_map.append({'kind': 'figure', 'index': number, 'caption': figure['caption'],
                    'marker': 'figure:' + record['record_id'] + ':' + str(number),
                    'ref': asdict(ref), 'record_ref': asdict(fixed_record(record)),
                    'block_ids': [block['block_id'] for block in record['payload'].get('blocks', [])
                                  if f'](figure:{number})' in block['markdown']], 'expanded': False})
        sources = list({digest(ref): ref for ref in sources}.values())
        links = {ref.id: reading.link(reader, ref) for ref in refs}
        packet['reference_map'] = reference_map
        # Local figure numbers restart in every technical unit. Preserve an
        # unambiguous presentation marker without changing the canonical prose.
        for part in packet['parts']:
            for item in reference_map:
                if any(ref['id'] == item['record_ref']['id'] for ref in part['refs']):
                    part['markdown'] = part['markdown'].replace('](figure:' + str(item['index']) + ')', '](' + item['marker'] + ')')
    return packet, sources, links


def discovery_recall(reading, session, raw, state, *, page=False):
    """Recall Owner identities only from the independent compressed projection."""
    from . import query_plan, reranking, owner_screening
    from .reading import require, text, strings
    from .reading_strategy import configuration, recall_request
    retrieval_kind = None
    if page and session.get('strategy') == 'quick' and session.get('quick_candidate_queue'):
        queued = session['quick_candidate_queue']
        take = min(len(queued), session['screening']['batch_owners'])
        current, session['quick_candidate_queue'] = queued[:take], queued[take:]
        candidates = []
        for item in current:
            if 'window_index' in item:
                packet = session['owner_packets'][item['owner_id']]
                text_value = packet['windows'][item['window_index']]['text']
            else:
                owner_row = next(row for row in session['discovery_queue']
                                 if row['owner_id'] == item['owner_id'])
                hit = next(hit for hit in owner_row['hits']
                           if hit.get('projection_id') == item['projection_id'])
                text_value = hit['text']
            row = session['candidates'][item['candidate_id']]
            candidates.append({'owner_id': item['owner_id'], 'text': text_value,
                'candidate_id': item['candidate_id'], 'sources': deepcopy(row['quick_sources']),
                'coverage': 'delivered_discovery_fragments_only'})
        previous = session['rounds'][-1]
        owner_more = session.get('discovery_offset', 0) < len(session.get('discovery_queue', []))
        has_more = bool(session['quick_candidate_queue']) or owner_more
        previous['has_more'] = has_more
        previous['lanes'] = [{'source': 'discovery', 'has_more': has_more}]
        return {'candidates': candidates, 'owner_packets': [],
                'discovery': deepcopy(previous['discovery']),
                'fulltext_compensation_available': session.get('fulltext_compensation', {}).get('available', False),
                'fulltext_compensation_reason': session.get('fulltext_compensation', {}).get('reason', ''),
                'has_more': has_more, 'pending_owner_count': max(0,
                    len(session.get('discovery_queue', [])) - session.get('discovery_offset', 0)),
                'mode': 'owner_document', **configuration(session), 'next_action': 'assess',
                'gaps': deepcopy(previous.get('gaps', [])),
                'guidance': '逐条reading-assess判断实际交付的发现片段，再仅按已接受固定片段写research_note；quick不读取全文。'}
    if page:
        require(session['phase'] == 'review' and session.get('discovery_queue') is not None,
                '当前没有可续读的发现候选轮')
        previous = session['rounds'][-1]
        require(previous.get('retrieval_source') == 'discovery' and previous.get('has_more'),
                '当前发现候选窗口已结束')
        plan, scope = previous['query_plan'], parse(previous['scope'], Scope)
        question, keywords = previous['question'], previous['keywords']
        owner_rows = deepcopy(session['discovery_queue'])
        offset = session.get('discovery_offset', 0)
        discovery_info = deepcopy(previous['discovery'])
    else:
        raw, retrieval_kind = recall_request(session, raw)
        if raw.get('clue_sources'):
            from .reading_strategy import accepted_sources
            delivered = accepted_sources(session)
            for saved in session.get('owner_progress', {}).values():
                delivered.extend(saved.get('delivered_sources', saved.get('root_refs', [])))
                if saved.get('full_delivered'):
                    delivered.extend(saved.get('root_refs', []))
                delivered.extend(saved.get('expanded_sources', []))
            raw['clue_sources'] = normalize_note_sources(raw['clue_sources'], delivered)
        text(raw['question'], 'question')
        text(raw['reason'], 'reason')
        strings(raw['keywords'], 'keywords')
        require(session['phase'] in {'ready', 'expand'}, '先记录下一步/失败缺口，再决定是否补查')
        scope = parse(raw['scope'], Scope)
        base = state.request
        scope = replace(scope, excluded_refs=tuple(set(scope.excluded_refs + base.scope.excluded_refs)),
                        excluded_owner_ids=tuple(set(scope.excluded_owner_ids + base.scope.excluded_owner_ids)),
                        exclude_ids=tuple(set(scope.exclude_ids + base.scope.exclude_ids)))
        plan = query_plan.build(reading.root, reading.ledger, raw)
        question, keywords = raw['question'], raw['keywords']
        batches, provider_states, degradation = [], [], []
        statuses, projection_versions = [], set()
        from .recall import discovery
        for route in query_plan.routes(plan):
            route_state = reading.state(session, query=asdict(replace(base, scope=scope,
                question=route['question'] or question, keywords=tuple(route['keywords']),
                channels=(route['channel'],), content_source=None)))
            reader = reading.app.reader(route_state)
            candidates, info = discovery(reading.root, route_state, reader, route,
                                         min(100, max(base.result_limit, session['screening']['batch_owners']) * 4))
            batches.append((route, candidates))
            statuses.append(info['status'])
            provider_states.extend(info.get('states', []))
            degradation.extend(info.get('degradation', []))
            if info.get('projection_version'):
                projection_versions.add(info['projection_version'])
        owner_rows = query_plan.fuse_owners(batches)
        owner_rows = [row for row in owner_rows if not session.get('owner_progress', {}).get(
            row['owner_id'], {}).get('full_delivered')]
        for row in owner_rows:
            # Screening expects every unique projection hit, with all route
            # provenance already attached by Owner fusion.
            row['hits'] = list({hit.get('projection_id', digest(hit)): hit for hit in row['hits']}.values())
        if not owner_rows and statuses and all(status == 'ready' for status in statuses):
            status = 'insufficient'
        elif not statuses or all(status == 'unavailable' for status in statuses):
            status = 'unavailable'
        elif any(status != 'ready' for status in statuses):
            status = 'incomplete'
        else:
            status = 'ready'
        reasons = list(dict.fromkeys(item.get('reason', str(item)) for item in degradation))
        if status == 'insufficient':
            reasons.append('no_discovery_hits')
        discovery_info = {'status': status, 'reasons': reasons,
                          **({'projection_version': next(iter(projection_versions))}
                             if len(projection_versions) == 1 else {}),
                          'states': provider_states}
        session['discovery_queue'] = deepcopy(owner_rows)
        offset = 0
        session['discovery_offset'] = 0

    screening = owner_screening.settings(session.get('screening'))
    batch = owner_rows[offset:offset + screening['batch_owners']]
    packets = owner_screening.build_batch(batch, screening) if batch else []
    ranking_options = reranking.settings(session.get('reranking'))
    if ranking_options['mode'] != 'off' and packets:
        prepared, lookup = [], {}
        for packet in packets:
            for number, window in enumerate(packet['windows']):
                key = packet['owner_id'] + ':' + str(number)
                prepared.append({'key': key, 'text': window['text'], 'complete': True,
                                 'evidence_parts': [{'text': window['text'], 'ref': ref, 'role': 'direct'}
                                                    for ref in window.get('refs', [])]})
                lookup[key] = window
        with reading.ledger.active():
            ranked = reranking.rank(reading.root, question, prepared, ranking_options, reading.ledger)
        for item in ranked['items']:
            lookup[item['key']]['ranking'] = item['ranking']
        rank_by_owner = {packet['owner_id']: min((window.get('ranking', {}).get('final_rank', 10**9)
                                                  for window in packet['windows']), default=10**9)
                         for packet in packets}
        packets.sort(key=lambda packet: (rank_by_owner[packet['owner_id']], packet['owner_id']))
        ranking_gaps = ranked['gaps']
    else:
        ranking_gaps = []

    reader = reading.app.reader(state)
    progress = session.setdefault('owner_progress', {})
    saved_packets = session.setdefault('owner_packets', {})
    quick_entries = []
    for packet in packets:
        packet['retrieval_source'] = 'discovery'
        saved_packets[packet['owner_id']] = deepcopy(packet)
        progress.setdefault(packet['owner_id'], {'selected': False, 'full_delivered': False, 'sources': []})
        # Canonical refs, not projection text, drive every later permission and
        # version check.  Compact screening prose is saved separately.
        for window_index, window in enumerate(packet['windows']):
            window_refs = []
            for ref_value in window.get('refs', []):
                window_refs.append(deepcopy(ref_value))
                ref = parse(ref_value, FixedRef)
                key = 'RC-' + digest(ref_value)[:24]
                if key in session['candidates']:
                    continue
                if ref.kind == 'owner':
                    owner = reader.owner(ref.id)
                    title = owner['title']
                    link = owner.get('native_ref', {}).get('path', '')
                else:
                    record = reader.record(ref)
                    title, link = record['title'], reading.link(reader, ref)
                session['candidates'][key] = {'ref': ref_value, 'title': title,
                    'link': link, 'owner_id': packet['owner_id'],
                    'scope': asdict(scope), 'contributors': [], 'full_delivered': False,
                    'packet_complete': True, 'stale': False, 'delivery': 'screened'}
            if session.get('strategy') == 'quick' and window_refs:
                # Each complementary screening window is independently
                # assessable.  The row stores fixed refs only; prose remains in
                # the already-delivered Owner packet and is paged by index.
                window_refs = list({digest(ref): ref for ref in window_refs}.values())
                quick_key = 'RC-' + digest({'owner_id': packet['owner_id'],
                    'window_index': window_index, 'refs': window_refs})[:24]
                first = parse(window_refs[0], FixedRef)
                if first.kind == 'owner':
                    owner = reader.owner(first.id)
                    title = owner['title']
                    link = owner.get('native_ref', {}).get('path', '')
                else:
                    record = reader.record(first)
                    title, link = record['title'], reading.link(reader, first)
                session['candidates'][quick_key] = {'ref': window_refs[0], 'title': title,
                    'link': link, 'owner_id': packet['owner_id'], 'scope': asdict(scope),
                    'contributors': [], 'full_delivered': False, 'packet_complete': True,
                    'stale': False, 'delivery': 'screened', 'quick_sources': window_refs}
                quick_entries.append({'owner_id': packet['owner_id'],
                    'candidate_id': quick_key, 'window_index': window_index})
        if session.get('strategy') == 'quick':
            # Older quick sessions page through individually assessable
            # compressed hits.  Keep that compatibility using only discovery
            # projection text: supplemental hits never read blocks/documents
            # and do not enlarge the bounded Owner screening packet.
            selected_projection_ids = {window.get('projection_id') for window in packet['windows']}
            owner_row = next((row for row in batch if row['owner_id'] == packet['owner_id']), None)
            for hit in (owner_row or {}).get('hits', []):
                projection_id = hit.get('projection_id')
                refs = list({digest(ref): deepcopy(ref) for ref in hit.get('refs', [])}.values())
                if projection_id in selected_projection_ids or not refs or not hit.get('text'):
                    continue
                quick_key = 'RC-' + digest({'owner_id': packet['owner_id'],
                    'projection_id': projection_id, 'refs': refs})[:24]
                first = parse(refs[0], FixedRef)
                if first.kind == 'owner':
                    owner = reader.owner(first.id)
                    title = owner['title']
                    link = owner.get('native_ref', {}).get('path', '')
                else:
                    record = reader.record(first)
                    title, link = record['title'], reading.link(reader, first)
                session['candidates'][quick_key] = {'ref': refs[0], 'title': title,
                    'link': link, 'owner_id': packet['owner_id'], 'scope': asdict(scope),
                    'contributors': [], 'full_delivered': False, 'packet_complete': True,
                    'stale': False, 'delivery': 'screened', 'quick_sources': refs}
                quick_entries.append({'owner_id': packet['owner_id'],
                    'candidate_id': quick_key, 'projection_id': projection_id})
    new_offset = offset + len(batch)
    has_more = new_offset < len(owner_rows)
    session['discovery_offset'] = new_offset
    gaps = list(dict.fromkeys(discovery_info['reasons'] + ranking_gaps +
        ([] if discovery_info['status'] == 'ready' else ['压缩发现索引未完整覆盖；尚未搜索完整正文'])))
    round_info = {'question': question, 'keywords': keywords, 'reason': raw.get('reason', '同一发现轮续页'),
                  'scope': asdict(scope), 'query_plan': deepcopy(plan), 'retrieval_source': 'discovery',
                  'discovery': deepcopy(discovery_info), 'has_more': has_more,
                  'lanes': [{'source': 'discovery', 'has_more': has_more}], 'gaps': gaps,
                  'reranking': ranking_options}
    if retrieval_kind is not None:
        round_info.update(retrieval_kind=retrieval_kind,
            association_text=question if retrieval_kind == 'associative' else '',
            clue_sources=deepcopy(raw.get('clue_sources', [])))
    if page:
        session['rounds'][-1] = round_info
    else:
        session['rounds'].append(round_info)
    session['phase'] = 'review'
    available = discovery_info['status'] in {'unavailable', 'incomplete', 'insufficient'}
    session['fulltext_compensation'] = {'available': available,
        'reason': '；'.join(gaps) if gaps else ''}
    quick = session.get('strategy') == 'quick'
    legacy_candidates = []
    if quick:
        first_by_owner = {}
        remainder = []
        for item in quick_entries:
            if item['owner_id'] not in first_by_owner:
                first_by_owner[item['owner_id']] = item
            else:
                remainder.append(item)
        session.setdefault('quick_candidate_queue', []).extend(remainder)
        for item in first_by_owner.values():
            packet = saved_packets[item['owner_id']]
            window = packet['windows'][item['window_index']]
            row = session['candidates'][item['candidate_id']]
            legacy_candidates.append({'owner_id': item['owner_id'], 'text': window['text'],
                'candidate_id': item['candidate_id'], 'sources': deepcopy(row['quick_sources']),
                'coverage': 'delivered_discovery_fragments_only'})
        has_more = has_more or bool(session['quick_candidate_queue'])
        round_info['has_more'] = has_more
        round_info['lanes'] = [{'source': 'discovery', 'has_more': has_more}]
    else:
        legacy_candidates = [{'owner_id': packet['owner_id'],
                              'text': '\n\n'.join(window['text'] for window in packet['windows'])}
                             for packet in packets]
    return {'candidates': legacy_candidates, 'owner_packets': packets, 'discovery': discovery_info,
            'fulltext_compensation_available': available,
            'fulltext_compensation_reason': session['fulltext_compensation']['reason'],
            'has_more': has_more, 'pending_owner_count': max(0, len(owner_rows) - new_offset),
            'mode': 'owner_document', **configuration(session),
            'next_action': 'assess' if quick else 'assess-owners',
            'gaps': gaps, 'guidance': (
                '逐条reading-assess判断实际交付的发现片段，再仅按已接受固定片段写research_note；quick不读取全文。'
                if quick else '批量判断Owner为relevant、uncertain或irrelevant；仅relevant进入完整阅读。')}


def fulltext_recall(reading, session, raw, state, *, page=False):
    """内部覆盖不变，AI每页每Owner只收到一份正文；pending仅保存固定选择。

    delivery状态放在已有candidate行里，不新建平行队列或保存正文副本。
    已选择Owner的pending被跳过；未选Owner可跨进程逐份判断相关性。
    """
    from .reading import require
    from .reading_strategy import configuration, recall_request
    quick = configuration(session)['strategy'] == 'quick'
    retrieval_kind = None
    if not page:
        raw, retrieval_kind = recall_request(session, raw)
        if raw.get('clue_sources'):
            from .reading_strategy import accepted_sources
            delivered = accepted_sources(session)
            for saved in session.get('owner_progress', {}).values():
                delivered.extend(saved.get('delivered_sources', saved.get('root_refs', [])))
                if saved.get('full_delivered'):
                    delivered.extend(saved.get('root_refs', []))
                delivered.extend(saved.get('expanded_sources', []))
            raw['clue_sources'] = normalize_note_sources(raw['clue_sources'], delivered)
    progress = session.setdefault('owner_progress', {})
    if not quick:
        skip_selected_pending(session)
    pending = any(row.get('delivery') == 'pending' for row in session['candidates'].values())
    more_retrieval = retrieval_has_more(session)
    cached_packets, gaps = {}, []
    if page:
        require(session['phase'] == 'review' and bool(session['rounds']), '当前没有可续读的候选轮')
    if not page or not pending and more_retrieval:
        existing = set(session['candidates'])
        with reading.ledger.internal():
            result = reading.page(session, raw, state) if page else reading.recall(session, raw, state)
        if retrieval_kind is not None:
            session['rounds'][-1].update(retrieval_kind=retrieval_kind,
                association_text=raw['question'] if retrieval_kind == 'associative' else '',
                clue_sources=deepcopy(raw.get('clue_sources', [])))
        gaps.extend(result['gaps'])
        reader = reading.app.reader(state)
        for candidate in result['candidates']:
            key = candidate['candidate_id']
            row = session['candidates'][key]
            oid = reader.record(parse(row['ref'], FixedRef))['owner_id']
            row['owner_id'] = oid
            if progress.get(oid, {}).get('full_delivered') and not quick:
                row['delivery'] = 'skipped_selected'
                continue
            # Pre-progressive owner sessions already delivered every saved row.
            # Missing fields must never replay those historical snippets.
            if key in existing and 'delivery' not in row:
                continue
            form = candidate['reading_form']
            refs = [row['ref']]
            if form == 'section':
                refs = list({digest(ref): ref for part in candidate['packet']['parts']
                             for ref in part['refs'] if ref['id'] == row['ref']['id']}.values()) or refs
            preview = {'form': form, 'refs': refs}
            if row.get('delivery') == 'delivered' and row.get('preview') == preview:
                continue
            if row.get('delivery') == 'pending' and row.get('preview'):
                old = row['preview']
                # An explicit expansion while old candidates are pending must
                # not discard old block selections. Full supersedes sections;
                # sections are unioned by fixed identity without storing prose.
                if old['form'] == 'full' or form == 'full':
                    preview = {'form': 'full', 'refs': [row['ref']]}
                elif old['form'] == 'section' or form == 'section':
                    preview = {'form': 'section', 'refs': list({digest(ref): ref for ref in
                        (old['refs'] if old['form'] == 'section' else []) +
                        (refs if form == 'section' else [])}.values())}
            row.update(delivery='pending', preview=preview, preview_round_index=len(session['rounds']) - 1)
            # Cached packets exist only for this invocation. Persisted rows
            # contain refs/form, so later pages must reauthorize and reassemble.
            if preview == {'form': form, 'refs': refs}:
                cached_packets[key] = candidate['packet']
    elif session.get('rounds'):
        gaps.extend(session['rounds'][-1].get('gaps', []))

    output, seen, emitted = [], set(session.get('delivered_blocks', [])), set()
    for key, row in session['candidates'].items():
        oid = row.get('owner_id')
        if row.get('delivery') != 'pending' or oid in emitted:
            continue
        packet = cached_packets.get(key)
        if packet is None:
            preview = row['preview']
            question = session['rounds'][row['preview_round_index']]['question']
            read_state = reading.state(session, query=asdict(replace(state.request,
                scope=parse(json_value(row['scope']), Scope), question=question)))
            try:
                with reading.ledger.internal():
                    packet, _ = reading.packet(read_state, [parse(ref, FixedRef) for ref in preview['refs']],
                                                DefinitionRef(preview['form'], '1'))
            except QueryError as exc:
                if exc.code in {'BUDGET', 'CANCELLED'}:
                    raise
                gaps.append('待判断候选固定来源暂不可用：' + exc.message)
                continue
        texts, delivered_refs = [], []
        for part in packet['parts']:
            if part['group'] == 'gaps':
                continue
            identity = digest({'refs': part['refs'], 'selectors': part['selectors'], 'text': part['markdown']})
            # Identical prose saved twice in the same Owner provides no extra
            # screening information; fixed refs remain separately in candidates.
            body_identity = 'owner-text:' + digest({'owner_id': oid, 'text': part['markdown']})
            if identity not in seen and body_identity not in seen:
                texts.append(part['markdown'])
                delivered_refs.extend(deepcopy(part['refs']))
                seen.update((identity, body_identity))
        row['delivery'] = 'delivered' if packet['complete'] else 'pending'
        if not packet['complete']:
            gaps.append('候选正文交付存在缺口；完整Owner阅读需另行核对')
        if texts:
            candidate = {'owner_id': oid, 'text': '\n\n'.join(texts)}
            if quick:
                # Only refs attached to prose actually emitted in this response
                # are eligible. Deduplicated/internal packets grant no evidence.
                refs = list({digest(ref): ref for ref in delivered_refs}.values())
                row['quick_sources'] = list({digest(ref): ref for ref in row.get('quick_sources', []) + refs}.values())
                if row.get('assessment') and row['assessment'].get('sources_digest') != digest(row['quick_sources']):
                    row.pop('assessment')
                    gaps.append('候选新增交付片段，需重新逐条判断')
                candidate.update(candidate_id=key, sources=refs, coverage='delivered_recall_fragments_only')
            output.append(candidate)
            emitted.add(oid)
            progress.setdefault(oid, {'selected': False, 'full_delivered': False, 'sources': []})
        # Empty/deduplicated candidates do not consume this Owner's page slot;
        # continue until one actual new text or the pending list is exhausted.
    session['delivered_blocks'] = sorted(seen)
    pending_owners = {row['owner_id'] for row in session['candidates'].values() if row.get('delivery') == 'pending'}
    return {'candidates': output, 'gaps': list(dict.fromkeys(gaps)),
            'has_more': bool(pending_owners) or retrieval_has_more(session),
            'pending_owner_count': len(pending_owners), 'mode': 'owner_document', **configuration(session),
            'next_action': 'assess' if quick else 'read',
            'guidance': ('逐条reading-assess判断实际召回片段，再仅按已接受固定片段写research_note；reading-page续接，不自动读取全文。' if quick else
                         '每Owner本页最多一份正文；相关则reading-read(owner_id)，未确定可reading-page继续。')}


def assess_owners(session, raw):
    """Persist one batch of AI/user Owner decisions against exact packet bytes."""
    from .reading import require, text
    assessments = raw['assessments']
    require(isinstance(assessments, list) and 0 < len(assessments) <= 100,
            'assessments需要1..100项')
    packets = session.get('owner_packets', {})
    saved = session.setdefault('owner_assessments', {})
    output = []
    for item in assessments:
        object_fields(item, {'owner_id', 'status', 'reason', 'packet_digest'})
        owner_id = text(item['owner_id'], 'owner_id')
        reason = text(item['reason'], 'reason')
        require(item['status'] in {'relevant', 'uncertain', 'irrelevant'}, 'Owner判断状态无效')
        packet = packets.get(owner_id)
        require(packet is not None, '只能判断本会话实际交付的Owner筛选包')
        require(item['packet_digest'] == packet['packet_digest'], '筛选包已变化，请按当前版本重新判断')
        decision = {'status': item['status'], 'reason': reason,
                    'packet_digest': item['packet_digest']}
        saved[owner_id] = decision
        session.setdefault('owner_progress', {}).setdefault(owner_id, {
            'selected': False, 'full_delivered': False, 'sources': []})['judgment'] = item['status']
        if session.get('strategy') == 'quick':
            useful = item['status'] == 'relevant'
            for row in session['candidates'].values():
                if row.get('owner_id') == owner_id and row.get('quick_sources'):
                    row['assessment'] = {'useful': useful, 'reason': reason,
                                         'sources_digest': digest(row['quick_sources'])}
        output.append({'owner_id': owner_id, **decision})
    relevant = [item['owner_id'] for item in output if item['status'] == 'relevant']
    if not relevant:
        session['fulltext_compensation'] = {'available': True,
            'reason': '当前筛选包未判断出可直接完整阅读的Owner；是否扩大到全文召回由用户决定'}
    quick = session.get('strategy') == 'quick'
    return {'assessments': output, 'relevant_owner_ids': relevant,
            'next_action': ('synthesize' if quick and relevant else 'read' if relevant else 'page'),
            'fulltext_compensation_available': session.get('fulltext_compensation', {}).get('available', False),
            'fulltext_compensation_reason': session.get('fulltext_compensation', {}).get('reason', ''),
            'gaps': []}


def recall_fulltext(reading, session, raw, state):
    """Run the old full-text recall only after this explicit mutating action."""
    from .reading import require
    require(bool(session.get('rounds')), '尚无可补偿的发现轮')
    previous = session['rounds'][-1]
    require(previous.get('retrieval_source') == 'discovery', '全文补偿必须基于最近的发现轮')
    session['phase'] = 'ready'
    request = {'question': previous['question'], 'keywords': previous['keywords'],
               'scope': previous['scope'], 'reason': '用户明确选择全文补偿召回'}
    # Reuse the frozen language plan fields rather than rebuilding translation
    # choices.  Dictionary provenance remains attached to the new round.
    plan = previous.get('query_plan', {})
    request.update(query_variants=[{key: value for key, value in variant.items()
        if key in {'id', 'language', 'question', 'lexical_terms'}}
        for variant in plan.get('variants', [])[1:]],
        protected_terms=plan.get('protected_terms', []),
        corpus_language=plan.get('corpus_language', 'unknown'),
        language_reason=plan.get('language_reason', ''),
        query_domains=plan.get('query_domains', []))
    result = fulltext_recall(reading, session, request, state, page=False)
    packets = []
    for candidate in result['candidates']:
        owner_id = candidate['owner_id']
        refs = [row['ref'] for row in session['candidates'].values()
                if row.get('owner_id') == owner_id and row.get('delivery') == 'delivered']
        packet = {'owner_id': owner_id, 'windows': [{'text': candidate['text'], 'refs': refs,
                  'channels': ['fulltext']}], 'coverage': {'complete': False,
                  'gaps': ['全文补偿候选仍需选择Owner后完整阅读']},
                  'retrieval_source': 'fulltext_compensation'}
        packet['packet_digest'] = digest(packet)
        packets.append(packet)
        session.setdefault('owner_packets', {})[owner_id] = deepcopy(packet)
    session['fulltext_compensation'] = {'available': False, 'reason': '本轮已由用户明确执行'}
    return {**result, 'candidates': packets, 'owner_packets': packets,
            'retrieval_source': 'fulltext_compensation',
            'fulltext_compensation_available': False,
            'fulltext_compensation_reason': '本轮已由用户明确执行',
            'next_action': 'assess-owners'}


def retrieval_has_more(session):
    return bool(session.get('rounds') and any(lane.get('has_more') for lane in session['rounds'][-1]['lanes']))


def skip_selected_pending(session):
    """选中事实只有owner_progress权威保存；candidate delivery仅交付进度。"""
    progress = session.get('owner_progress', {})
    for row in session['candidates'].values():
        if row.get('delivery') == 'pending' and progress.get(row.get('owner_id'), {}).get('full_delivered'):
            row['delivery'] = 'skipped_selected'


def read_owner(reading, session, raw, state):
    from .reading import require, text
    oid = text(raw['owner_id'], 'owner_id')
    require(session.get('strategy', 'standard') != 'quick',
            'quick策略只使用已交付筛选片段；不能升级为Owner全文阅读')
    progress = session.setdefault('owner_progress', {})
    require(oid in progress, '只能读取本会话已交付的Owner')
    saved = progress[oid]
    if 'source_refs' in raw:
        return expand_sources(reading, session, raw, state, saved)
    assessment = session.setdefault('owner_assessments', {}).get(oid)
    if assessment is None:
        # Backward-compatible explicit selection: old clients that directly
        # click/read an actually delivered Owner still record a real relevance
        # decision instead of bypassing the new state machine.
        packet = session.get('owner_packets', {}).get(oid)
        session['owner_assessments'][oid] = {'status': 'relevant',
            'reason': '用户通过reading-read显式选择Owner',
            'packet_digest': packet.get('packet_digest') if packet else None}
        assessment = session['owner_assessments'][oid]
    require(assessment['status'] == 'relevant', '只有判断为relevant的Owner可以进入完整阅读')
    require(saved.get('selected') or sum(bool(row.get('selected')) for row in progress.values()) < session['context']['max_owners'],
            '已选Owner达到max_owners；进度已保存，需在既有范围完成阅读')
    reader = reading.app.reader(state)
    owner = reader.owner(oid)
    _, manifest = reader.store.head_manifest(owner)
    documents, fallback, scan_gaps = [], [], []
    # Use the derived directory only to locate IDs, then trust fixed store bytes.
    # Document lookup avoids reading unrelated material before the actual text.
    db = index.connect(reading.root, create=False)
    if db is None:
        raise QueryError('SOURCE_MISSING', '文稿目录索引尚未建立')
    try:
        limit = reading.ledger.remaining('candidates')
        offset = saved.get('read_offset', 0)
        rows = db.execute("SELECT record_id, kind FROM memory_records WHERE owner_id=? AND entity_kind='record' AND kind IN ('document','detail','narrative','experience','overview') ORDER BY CASE WHEN kind='document' THEN 0 ELSE 1 END,record_id LIMIT ? OFFSET ?", (oid, limit + 1, offset)).fetchall()
    finally:
        db.close()
    has_more = len(rows) > limit
    if has_more:
        scan_gaps.append('Owner正文仍有下一页；继续reading-read直到has_more=false')
    rows = rows[:limit]
    document_rows = [row for row in rows if row[1] == 'document']
    with reading.ledger.active():
        for rid, kind in rows:
            reading.ledger.charge('candidates', 1)
            entry = (manifest or {}).get('record_heads', {}).get(rid)
            if not entry:
                scan_gaps.append('索引记录已不在当前Owner清单；需要刷新索引')
                continue
            ref = FixedRef('record', rid, entry['revision'], entry['record_hash'], None)
            try:
                record = reader.record(ref)
            except QueryError as exc:
                if exc.code in {'BUDGET', 'CANCELLED'}:
                    raise
                scan_gaps.append('Owner内有记录不满足当前授权或固定来源不可用，未交付')
                continue
            if not required_scope_allows(reader, record, state.request):
                continue
            if record['kind'] == 'document' and record['payload'].get('document_type') in {'research_report', 'research_process'}:
                documents.append((record, ref))
            elif record['kind'] in {'detail', 'narrative', 'experience', 'overview'}:
                fallback.append((record, ref))
    # A document may embed technical units through immutable section refs.
    # Those units are current Owner content, but adding them again as fallback
    # would duplicate the exact正文.  Keep uncovered records while preserving
    # every document and every independently authored current record.
    covered_record_ids = set()
    for document, _document_ref in documents:
        for section_value in document.get('payload', {}).get('section_refs', []):
            try:
                section_ref, _ = from_legacy(section_value)
                section = reader.record(section_ref)
                for block in section.get('payload', {}).get('blocks', []):
                    if block.get('type') == 'unit' and block.get('ref'):
                        unit_ref, _ = from_legacy(block['ref'])
                        covered_record_ids.add(unit_ref.id)
            except (QueryError, KeyError, TypeError):
                scan_gaps.append('文稿章节覆盖关系暂不可用；正文仍按已授权固定记录交付')
    selected = documents + [(record, ref) for record, ref in fallback
                            if record['record_id'] not in covered_record_ids]
    gaps = list(dict.fromkeys(scan_gaps))
    if selected:
        form = 'all_available_current_content'
    else:
        form = 'complete_record_fallback'
        selected = fallback
        gaps.append(('当前范围内无可交付文稿（已登记文稿的授权、来源或版本不可用）' if document_rows else
                     'Owner目录未找到research_report/research_process文稿') +
                    '；仅交付实际完整记录，不表示完整研究报告')
    if not selected:
        saved.update(selected=True, full_delivered=not has_more, reading_form=form,
                     read_offset=offset + len(rows), gaps=gaps + ['Owner没有可交付完整正文'])
        return {'owner_id': oid, 'text': '', 'sources': [], 'document_refs': [],
                'references': [], 'reading_form': form,
                'complete': not has_more, 'has_more': has_more, 'gaps': saved['gaps']}
    refs = [item[1] for item in selected]
    packet, sources, links = owner_packet(reading, session, state, refs)
    complete = packet['complete'] and not has_more
    page_has_more = has_more or not packet['complete']
    if not complete:
        gaps.append('完整正文存在缺口，不能提交已完整阅读笔记')
    for record, ref in selected:
        key = 'RC-' + digest(asdict(ref))[:24]
        row = session['candidates'].setdefault(key, {})
        row.update(ref=asdict(ref), title=record['title'], link=links[ref.id], owner_id=oid,
                   scope=asdict(state.request.scope), full_delivered=complete,
                   packet_complete=complete, contributors=packet['contributors'], stale=False)
    # A transiently partial body packet must be retryable from the same stable
    # page.  Advancing the offset here would silently skip the failed page on
    # the next reading-read call.
    next_offset = offset + len(rows) if packet['complete'] else offset
    saved.update(selected=True, full_delivered=complete, reading_form=form,
                 read_offset=next_offset, gaps=gaps)
    saved['sources'] = list({digest(ref): ref for ref in saved.get('sources', []) + sources}.values())
    saved['root_refs'] = list({digest(ref): ref for ref in saved.get('root_refs', []) +
                               [asdict(ref) for ref in refs]}.values())
    saved['reference_map'] = list({digest(item): item for item in saved.get('reference_map', []) +
                                   packet['reference_map']}.values())
    saved['delivered_sources'] = list({digest(ref): ref for ref in saved.get('delivered_sources', []) +
        [ref for part in packet['parts'] if part['group'] != 'gaps' for ref in part['refs']]}.values())
    # Documents can expand the same canonical record that is also enumerated
    # directly.  Deliver each exact body once across all Owner pages while
    # retaining every fixed source in the source list and progress metadata.
    seen_bodies = set(saved.get('delivered_body_digests', []))
    body_parts = []
    for part in packet['parts']:
        if part['group'] == 'gaps':
            continue
        body_digest = digest({'markdown': part['markdown']})
        if body_digest in seen_bodies:
            continue
        seen_bodies.add(body_digest)
        body_parts.append(part['markdown'])
    saved['delivered_body_digests'] = sorted(seen_bodies)
    # Store source button identities for every actually delivered record. This
    # preserves the existing workbench contract without inventing a single
    # candidate as the provenance of the whole Owner research note.
    for source in sources:
        if source['kind'] not in {'record', 'representation'}:
            continue
        ref = parse(source, FixedRef)
        record = reader.record(ref)
        key = 'RC-' + digest(source)[:24]
        session['candidates'].setdefault(key, {
            'ref': source, 'title': record['title'], 'link': reading.link(reader, ref),
            'owner_id': oid, 'scope': asdict(state.request.scope), 'contributors': [],
            'full_delivered': False, 'packet_complete': True})
    return {'owner_id': oid, 'text': '\n\n'.join(body_parts),
            'sources': sources, 'document_refs': [asdict(ref) for ref in refs], 'has_more': page_has_more,
            'references': packet['reference_map'],
            'reading_form': form, 'complete': complete, 'gaps': gaps}


def expand_sources(reading, session, raw, state, saved):
    """展开必须源于已交付固定引用；不能提供新路径或换版本绕过授权。"""
    from .reading import require
    requested = raw['source_refs']
    require(isinstance(requested, list) and 0 < len(requested) <= 20, 'source_refs需要1..20项')
    available = {digest(ref) for ref in saved.get('sources', [])}
    require(all(digest(ref) in available for ref in requested), '只能展开已经交付的固定来源')
    output, gaps = [], []
    reader = reading.app.reader(state)
    with reading.ledger.active():
        for raw_ref in requested:
            ref = parse(raw_ref, FixedRef)
            if ref.kind == 'file':
                binary = reader.file_bytes(ref)
                mime = ('image/png' if binary.startswith(b'\x89PNG\r\n\x1a\n') else
                        'image/jpeg' if binary.startswith(b'\xff\xd8\xff') else
                        'image/webp' if binary[:4] == b'RIFF' and binary[8:12] == b'WEBP' else None)
                if mime:
                    require(len(binary) <= 8 * 1024 * 1024, '图像超过8MiB展开上限')
                    output.append({'ref': raw_ref, 'data_url': 'data:' + mime + ';base64,' + base64.b64encode(binary).decode('ascii')})
                else:
                    output.append({'ref': raw_ref, 'text': reader.file(ref)})
            elif ref.kind == 'owner':
                text, native = read_native_reference(reader, ref)
                if reader.owner(ref.id)['owner_type'] == 'run':
                    # Native Runs have no guaranteed authored report. Expose
                    # existing summary fields only, never arbitrary log files.
                    summary = {key: native[key] for key in ('title', 'conclusion', 'limitations') if native.get(key)}
                    text = json.dumps(summary, ensure_ascii=False, indent=2) if summary else ''
                    if not native.get('conclusion'):
                        gaps.append('Run未保存结论总结；不能把状态/日志当作完整研究正文')
                output.append({'ref': raw_ref, 'text': text})
            elif ref.kind in {'record', 'representation'}:
                # Packet owns its activity scope; defer until outside this one.
                output.append({'ref': raw_ref, '_record': True})
            else:
                gaps.append('该固定来源需专用证据接口展开：' + ref.kind)
    for item in output:
        if item.pop('_record', False):
            packet, _, _ = owner_packet(reading, session, state, [parse(item['ref'], FixedRef)])
            item['text'] = '\n\n'.join(part['markdown'] for part in packet['parts'] if part['group'] != 'gaps')
            if not packet['complete']:
                gaps.append('来源完整展开存在缺口')
    saved['expanded_sources'] = list({digest(ref): ref for ref in saved.get('expanded_sources', []) +
                                     [item['ref'] for item in output]}.values())
    # Expanded sources participate in every future reauthorization/version
    # check. Merely listed references stay references, not claims of having read.
    roots = {digest(ref) for ref in saved.get('root_refs', [])}
    for row in session['candidates'].values():
        if digest(row['ref']) in roots:
            row['contributors'] = list({digest(ref): ref for ref in row.get('contributors', []) +
                                        [item['ref'] for item in output if item['ref']['kind'] in {'file', 'owner', 'record', 'representation'}]}.values())
    return {'owner_id': raw['owner_id'], 'expanded_sources': output, 'gaps': gaps}


def read_native_reference(reader, ref):
    """旧MEM Owner引用采用evidence规范指纹；MQ原生引用采用文件字节指纹。

    两种已登记算法均需核对当前真实字节，不改写调用者保存的旧固定引用。
    只读取该Owner，不为单个Run构造整个工作区EvidenceGraph。
    """
    import evidence
    owner = reader.owner(ref.id)
    if ref.sha256 == owner['fingerprint']:
        return reader.native(ref)
    text, native = reader.native(replace(ref, sha256=owner['fingerprint']))
    if evidence.fingerprint(native) != ref.sha256:
        raise QueryError('STALE', 'Owner固定规范指纹已经变化')
    return text, native


NOTE_FIELDS = {'question', 'conditions', 'understanding', 'logic', 'details', 'sources', 'limitations', 'next_steps'}


def normalize_note_sources(requested, delivered):
    """ID简写只在本Owner已交付集合内解析，不查全库、不替换固定版本。

    同版本的多个定位均保留，以免把正文块/图示出处悄悄缩成一个定位。
    多kind、多修订或多hash无法唯一决定版本时，必须由调用者给完整FixedRef。
    """
    from .reading import require, text
    require(isinstance(requested, list) and bool(requested), '笔记必须包含已交付固定出处')
    available = {digest(ref): ref for ref in delivered}
    resolved = []
    for item in requested:
        if isinstance(item, str):
            identity = text(item, 'source_id')
            matches = [ref for ref in delivered if ref['id'] == identity]
            require(bool(matches), '笔记来源ID未在本Owner实际交付')
            versions = {(ref['kind'], ref['revision'], ref['sha256']) for ref in matches}
            require(len(versions) == 1, '笔记来源ID对应多个固定版本或类型，请提供已交付的完整FixedRef')
            resolved.extend(matches)
        else:
            require(isinstance(item, dict) and digest(item) in available, '笔记引用未交付来源或不同固定版本')
            resolved.append(available[digest(item)])
    return deepcopy(list({digest(ref): ref for ref in resolved}.values()))


def validate_note_evidence_ids(note, delivered):
    """核对证据正文的显式ID，不将字面校验冒充公式/实验的语义审核。

    未知身份只识别MEM/RUN/SRC前缀；其他已交付record/file/representation
    身份仅作精确匹配，且须含分隔符，避免将普通公式变量当来源。
    中文标点可直接贴邻ID；URL不是本地固定身份，Owner/RS仅作导航。
    question等问题/计划字段不检查。只在新note保存前调用，旧笔记不追审。
    """
    from .reading import require
    prose = '\n'.join([note['understanding'], *note['logic'], *note['details']])
    # Stop at Markdown delimiters and adjacent Chinese prose: otherwise stripping
    # a URL could swallow a real source ID immediately after a closing link/code.
    # This intentionally recognizes ordinary ASCII URL tokens, not arbitrary IRIs.
    prose = re.sub(r'https?://[^\s<>"`\[\](){}\u3000-\u303f\u3400-\u9fff\uff00-\uffef]+',
                   '', prose, flags=re.IGNORECASE)
    left, right = r'(?<![A-Za-z0-9_-])', r'(?![A-Za-z0-9_-])'
    identities = set(re.findall(left + r'(?:MEM|RUN|SRC)-[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*' + right, prose))
    for ref in delivered:
        identity = ref['id']
        if (ref['kind'] in {'record', 'file', 'representation'} and
                not identity.startswith(('RS-', 'RES-', 'PRJ-')) and
                ('-' in identity or '_' in identity) and
                re.search(left + re.escape(identity) + right, prose)):
            identities.add(identity)
    delivered_ids = {ref['id'] for ref in delivered}
    cited_ids = {ref['id'] for ref in note['sources']}
    unknown = sorted(identities - delivered_ids)
    require(not unknown, '笔记正文提及未交付来源ID：' + '、'.join(unknown))
    missing = sorted(identities - cited_ids)
    require(not missing, '笔记正文来源ID未列入sources：' + '、'.join(missing))


def note_owner(reading, session, raw, state):
    from .reading import require, text, strings
    oid = text(raw['owner_id'], 'owner_id')
    progress = session.get('owner_progress', {}).get(oid)
    from .reading_strategy import configuration, accepted_sources
    quick = configuration(session)['strategy'] == 'quick'
    if quick:
        sources = accepted_sources(session, oid, raw.get('candidate_ids'))
        require(bool(sources), '先逐条接受实际交付的召回片段，再提交quick笔记')
        selected = {key for key, value in session.get('owner_progress', {}).items() if value.get('selected')}
        require(oid in selected or len(selected) < session['context']['max_owners'], '已达到本RS的Owner数量上限')
        progress = {'sources': sources, 'root_refs': sources}
    else:
        require(progress is not None and progress.get('full_delivered'), '先完整交付Owner正文，再提交阅读笔记')
    require(not owner_stale(session, oid, use_note=False),
            'Owner来源已有修订，需重新读取并核对')
    note = raw.get('research_note')
    require(isinstance(note, dict), '缺少research_note')
    object_fields(note, NOTE_FIELDS, {'exploration_clues'})
    for field in ('question', 'understanding'):
        text(note[field], field)
    for field in ('conditions', 'logic', 'details', 'limitations', 'next_steps'):
        strings(note[field], field)
    note = deepcopy(note)
    note['sources'] = normalize_note_sources(note['sources'], progress['sources'])
    clues = note.get('exploration_clues', [])
    require(isinstance(clues, list) and len(clues) <= 30, 'exploration_clues必须为有界数组')
    for clue in clues:
        object_fields(clue, {'text', 'reason', 'sources', 'next_query', 'limitations'})
        for field in ('text', 'reason'):
            text(clue[field], 'exploration_clues.' + field)
        require(isinstance(clue['next_query'],str) and len(clue['next_query']) <= 8000,
                'exploration_clues.next_query必须为有界字符串，可留空待主Agent制定查询')
        strings(clue['limitations'], 'exploration_clues.limitations')
        clue['sources'] = normalize_note_sources(clue['sources'], progress['sources'])
        note['sources'] = list({digest(ref): ref for ref in note['sources'] + clue['sources']}.values())
    # Validate before the first mutation: rejection preserves the previous note,
    # RS revision and derived snapshot through the existing operation boundary.
    validate_note_evidence_ids(note, progress['sources'])
    if quick:
        note['coverage'] = 'delivered_recall_fragments_only'
        note['limitations'] = list(dict.fromkeys(note['limitations'] + ['仅依据已交付且接受的召回片段；未完整阅读Owner文稿。']))
    session.setdefault('owner_notes', {})[oid] = deepcopy(note) | {
        'authorship': 'caller_ai_or_human; not_semantically_verified',
        'basis_refs': deepcopy(progress.get('root_refs', []))}
    if quick:
        # Selecting a quick Owner does not grant full-delivery state. A later
        # standard strategy must still execute the complete-document read.
        session.setdefault('owner_progress', {}).setdefault(oid, {'full_delivered': False, 'sources': []})['selected'] = True
    estimate = estimated_tokens(note_markdown(oid, note))
    limit = session['context']['note_max_tokens']
    return {'saved': True, 'owner_id': oid, 'estimated_note_tokens': estimate,
            'note_max_tokens': limit, 'over_budget': estimate > limit,
            'token_estimation': 'utf8_bytes_conservative; not_host_exact_tokens',
            'gaps': ['单份笔记超过交接上限；请在保留必要细节后改写，原笔记已保存'] if estimate > limit else []}


def note_markdown(oid, note, titles=None, *, links=False):
    """完整Owner笔记是装包原子单位；公式、变量、单位不截断。"""
    # question and workflow decisions remain in the RS/API metadata. A note's
    # delivered body is reusable knowledge, not a second copy of its task brief.
    lines = ['## ' + oid, '### 理解', note['understanding']]
    for field, label in [('conditions', '条件'), ('logic', '逻辑与假设'), ('details', '细节、参数、单位与边界'),
                         ('limitations', '限制、反例与待验证'), ('next_steps', '可选的下一步建议')]:
        if note[field]:
            lines += ['### ' + label, *note[field]]
    if note.get('exploration_clues'):
        lines += ['### 待验证联想线索']
        for clue in note['exploration_clues']:
            lines += [clue['text'], '关联依据：' + clue['reason'],
                      '限制：' + '；'.join(clue['limitations']),
                      '线索依据：' + '、'.join(ref['id'] + (':' + ref['locator'] if ref.get('locator') else '') for ref in clue['sources'])]
    from .reading_citations import render
    return render('\n\n'.join(lines), note['sources'], titles, links=links)[0]


def estimated_tokens(text):
    """UTF-8字节数作非常保守估计；不保证任意分词器上界，不是宿主精确token。"""
    return len(text.encode('utf-8'))


def handoff_value(session, max_chars=None, *, display=False):
    notes = session.get('owner_notes', {})
    synthesis = session.get('synthesis_note')
    from .reading_strategy import accepted_sources
    synthesis_stale = bool(synthesis and (synthesis.get('owner_notes_digest') != digest(notes) or
        synthesis.get('accepted_sources_digest') != digest(accepted_sources(session)) or
        any(row.get('stale') and any(row['ref']['id'] == ref['id'] for ref in synthesis['sources']) for row in session['candidates'].values())))
    if synthesis and not synthesis_stale:
        notes = {'RS-SYNTHESIS': synthesis}
    limit = session.get('context', DEFAULT_CONTEXT)['note_max_tokens']
    context = []
    chunks, gaps, omitted, included = [], [], 0, []
    if synthesis_stale:
        gaps.append('综合note依据或Owner底稿已变化，需重新核对综合稿；当前仅交付可用底稿')
    quick_rows = [row for row in session['candidates'].values() if row.get('quick_sources')]
    pending_assessments = sum(not row.get('assessment') for row in quick_rows)
    if pending_assessments:
        gaps.append(str(pending_assessments) + '条已交付召回片段尚未逐条判断')
    synthesis_sources = {ref['id'] for ref in synthesis.get('sources', [])} if synthesis and not synthesis_stale else set()
    synthesis_owners = {row.get('owner_id') for row in session['candidates'].values() if row['ref']['id'] in synthesis_sources}
    if synthesis and not synthesis_stale:
        synthesis_owners.update(synthesis.get('basis_owner_ids', []))
    if any(row.get('assessment', {}).get('useful') and row.get('owner_id') not in session.get('owner_notes', {})
           and row.get('owner_id') not in synthesis_owners for row in quick_rows):
        gaps.append('已接受召回片段尚未保存研究笔记')
    stale = {oid for oid in notes if owner_stale(session, oid)}
    for oid, note in notes.items():
        titles = dict(session.get('citation_titles', {}))
        titles.update({row['ref']['id']: row['title'] for row in session['candidates'].values() if row.get('title')})
        chunk = note_markdown(oid, note, titles, links=display)
        proposed = '\n\n'.join(context + chunks + [chunk])
        if oid in stale or estimated_tokens(proposed) > limit or max_chars is not None and len(proposed) > max_chars:
            omitted += 1
            continue
        chunks.append(chunk)
        included.append(oid)
    if omitted:
        gaps.append(str(omitted) + '份Owner笔记因来源变化或上下文上限未交付；笔记完整保存在RS，未截断公式')
    if not notes:
        gaps.append('尚无实际Owner阅读笔记')
    unnoted = sum(bool(progress.get('selected')) and oid not in session.get('owner_notes', {}) and oid not in synthesis_owners
                  for oid, progress in session.get('owner_progress', {}).items())
    if unnoted:
        gaps.append(str(unnoted) + '个已选Owner尚未保存研究笔记')
    for progress in session.get('owner_progress', {}).values():
        gaps.extend(progress.get('gaps', []))
    if session.get('rounds'):
        gaps.extend(session['rounds'][-1].get('gaps', []))
    if session['phase'] not in {'finish', 'proceed'}:
        gaps.append('阅读尚未完成' if session['phase'] != 'ask_user' else '等待用户意见')
    markdown = '\n\n'.join(context + chunks)
    if estimated_tokens(markdown) > limit or max_chars is not None and len(markdown) > max_chars:
        markdown = ''
        gaps.append('问题/条件/决定本身超过交接窗口；已保存在RS，未截断交付')
    from .reading_strategy import configuration
    from .reading_citations import render
    delivered_references = []
    for oid in included:
        refs = render('', notes[oid]['sources'], titles)[1]
        for ref in refs:
            ref['section_owner_id'] = oid
        delivered_references.extend(refs)
    return {**configuration(session), 'synthesis_included': bool(synthesis and not synthesis_stale and chunks),
            'references': delivered_references,
            'context_markdown': markdown, 'mode': 'owner_document', 'phase': session['phase'],
            'included_owner_ids': included,
            'notes_count': len(chunks), 'omitted_note_count': omitted,
            'unnoted_candidate_count': unnoted,
            'estimated_note_tokens': estimated_tokens(markdown), 'note_max_tokens': limit,
            'token_estimation': 'utf8_bytes_conservative; not_host_exact_tokens',
            'complete': not gaps, 'gaps': list(dict.fromkeys(gaps)), 'needs_user_input': session['phase'] == 'ask_user'}


def owner_stale(session, oid, *, use_note=True):
    note = session.get('owner_notes', {}).get(oid) if use_note else None
    if note and note.get('coverage') == 'delivered_recall_fragments_only':
        from .reading_strategy import accepted_sources
        accepted = {digest(ref) for ref in accepted_sources(session, oid)}
        if any(digest(ref) not in accepted for ref in note['sources']):
            return True
    refs = (note.get('basis_refs', []) + note['sources']) if note else session.get('owner_progress', {}).get(oid, {}).get('root_refs', [])
    roots = {digest(ref) for ref in refs}
    return any(row.get('stale') and (digest(row['ref']) in roots or any(
        row['ref']['id'] == ref['id'] and row['ref']['sha256'] == ref['sha256'] for ref in refs))
        for row in session['candidates'].values())


def source_candidates(session, included_owner_ids=None):
    """只提供实际note引用的固定记录，工作台显式展开沿用既有candidate按钮。"""
    notes = session.get('owner_notes', {})
    if included_owner_ids and 'RS-SYNTHESIS' in included_owner_ids:
        notes = {'RS-SYNTHESIS': session['synthesis_note']}
    cited = [ref for oid, note in notes.items() if not owner_stale(session, oid)
             and (included_owner_ids is None or oid in included_owner_ids)
             for ref in note['sources']]
    return [dict(candidate_id=key, title=row['title'], link=row['link'], ref=row['ref'],
                 cited_sources=[ref for ref in cited if ref['id'] == row['ref']['id'] and ref['sha256'] == row['ref']['sha256']],
                 status='笔记固定出处（需按需展开）', stale=False, has_note=True)
            for key, row in session['candidates'].items() if any(row['ref']['id'] == ref['id'] and
                row['ref']['sha256'] == ref['sha256'] for ref in cited) and not row.get('stale')]


def screening_state(session):
    """Public, presentation-safe discovery state shared by view and snapshots."""
    packets = deepcopy(session.get('owner_packets', {}))
    for owner_id, packet in packets.items():
        if owner_id in session.get('owner_assessments', {}):
            packet['assessment'] = {'owner_id': owner_id,
                                    **deepcopy(session['owner_assessments'][owner_id])}
    return {'owner_packets': list(packets.values()),
            'discovery': deepcopy((session.get('rounds') or [{}])[-1].get('discovery', {
                'status': 'unavailable', 'reasons': ['not_recalled']})),
            'fulltext_compensation_available': session.get('fulltext_compensation', {}).get('available', False),
            'fulltext_compensation_reason': session.get('fulltext_compensation', {}).get('reason', '')}


def execute(reading, method, session, raw, state):
    """模式边界统一路由；legacy方法与原RS累计账本保持不变。"""
    from . import reading_strategy
    if method == 'configure':
        value = reading_strategy.configure(session, raw)
    elif method == 'assess':
        value = reading_strategy.assess(session, raw)
    elif method == 'assess-owners':
        value = assess_owners(session, raw)
    elif method == 'recall-fulltext':
        value = recall_fulltext(reading, session, raw, state)
    elif method == 'synthesize':
        value = reading_strategy.synthesize(reading, session, raw, state)
    elif method == 'recall' or method == 'page':
        if method == 'page' and session.get('rounds') and session['rounds'][-1].get('retrieval_source') != 'discovery':
            value = fulltext_recall(reading, session, raw, state, page=True)
        else:
            value = discovery_recall(reading, session, raw, state, page=method == 'page')
    elif method == 'read':
        if 'owner_id' in raw:
            value = read_owner(reading, session, raw, state)
            skip_selected_pending(session)
        else:
            # Existing workbench source buttons explicitly request a fixed
            # candidate. Keep their packet shape without selecting a new Owner.
            with reading.ledger.internal():
                value = reading.read(session, raw, state)
    elif method == 'note':
        value = note_owner(reading, session, raw, state)
    else:
        value = handoff_value(session, raw.get('max_chars'))
        if method in {'resume', 'notes_view'}:
            pending_owners = {row.get('owner_id') for row in session['candidates'].values()
                              if row.get('delivery') == 'pending' and
                              not session.get('owner_progress', {}).get(row.get('owner_id'), {}).get('selected')}
            value.update(owner_progress=deepcopy(session.get('owner_progress', {})),
                         owner_id=session.get('owner_id'), goal=session['goal'], archived=session.get('archived', False),
                         round_count=len(session['rounds']), candidates=source_candidates(session, value['included_owner_ids']),
                         pending_owner_count=len(pending_owners), has_more=bool(pending_owners) or retrieval_has_more(session))
            value.update(screening_state(session))
            if reading_strategy.configuration(session)['strategy'] == 'quick':
                value['quick_candidates'] = [dict(candidate_id=key, owner_id=row.get('owner_id'),
                    sources=deepcopy(row['quick_sources']), assessment=deepcopy(row.get('assessment')),
                    stale=row.get('stale', False), coverage='delivered_recall_fragments_only')
                    for key, row in session['candidates'].items() if row.get('quick_sources')]
    # Measure only the JSON delivered by this action, once. Binary images are
    # bounded by read_bytes and their explicit per-image size, not text tokens.
    measurement = deepcopy(value)
    for source in measurement.get('expanded_sources', []):
        source.pop('data_url', None)
    reading.ledger.charge('output_chars', len(json.dumps(measurement, ensure_ascii=False)))
    return value
