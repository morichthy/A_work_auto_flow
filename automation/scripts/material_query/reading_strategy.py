"""阅读策略只控制已有RS的数据流，不创建授权域或重置消费和历史。"""
from copy import deepcopy
from .wire import digest
from .validation import object_fields


def configuration(session):
    """旧会话只读兼容：不把新的工作区默认值追写到历史RS。"""
    return {'strategy': session.get('strategy', 'standard'),
            'association': deepcopy(session.get('association', {'enabled': False, 'max_rounds': 3})),
            'association_text': session.get('association_text', '')}


def validate(strategy, association, association_text):
    from .reading import require, text
    require(strategy in {'standard', 'associative', 'quick'}, '未知阅读策略')
    object_fields(association, {'enabled', 'max_rounds'})
    require(type(association['enabled']) is bool, 'association.enabled必须为布尔值')
    require(type(association['max_rounds']) is int and 1 <= association['max_rounds'] <= 20,
            'association.max_rounds必须为1..20整数')
    text(association_text, 'association_text', empty=True)
    return dict(strategy=strategy, association=deepcopy(association), association_text=association_text)


def configure(session, raw):
    from .reading import require
    require(session.get('mode') == 'owner_document', 'legacy会话不支持策略切换')
    values = validate(raw['strategy'], raw.get('association', configuration(session)['association']), raw['association_text'])
    session.update(values)
    return {'saved': True, **configuration(session)}


def recall_request(session, raw):
    """联想使用真实子问题；轮数按成功持久化的召回轮计数，分页不重复计数。"""
    from .reading import require, text
    config = configuration(session)
    kind = raw.get('retrieval_kind', 'associative' if config['strategy'] == 'associative' else 'direct')
    require(kind in {'direct', 'associative'}, '未知retrieval_kind')
    request = deepcopy(raw)
    if kind == 'associative':
        require(config['association']['enabled'], '本RS联想已关闭；需显式配置启用')
        require(sum(r.get('retrieval_kind') == 'associative' for r in session['rounds']) < config['association']['max_rounds'], '联想轮次已耗尽')
        query = raw.get('association_text', config['association_text']) or raw['question']
        text(query, 'association_text')
        request['question'] = query
        # A caller's bilingual/equivalent plan must describe this subquestion;
        # silently deleting it would also discard engineering conditions.
        from .query_plan import PLAN_FIELDS
        require(query == raw['question'] or not any(key in raw for key in PLAN_FIELDS),
                '联想文本改变子问题时，请为该子问题显式提供匹配的question和查询计划')
    return request, kind


def assess(session, raw):
    from .reading import require, text
    require(configuration(session)['strategy'] == 'quick', '逐条判断只用于quick策略')
    row = session['candidates'].get(raw['candidate_id'])
    require(row is not None and row.get('quick_sources') and not row.get('stale'), '只能判断本RS实际交付的有效召回片段')
    require(type(raw['useful']) is bool, 'useful必须为布尔值')
    text(raw['reason'], 'reason')
    row['assessment'] = {'useful': raw['useful'], 'reason': raw['reason'], 'sources_digest': digest(row['quick_sources'])}
    return {'saved': True, 'candidate_id': raw['candidate_id'], 'assessment': deepcopy(row['assessment'])}


def accepted_sources(session, owner_id=None, candidate_ids=None):
    from .reading import require
    keys = candidate_ids if candidate_ids is not None else list(session['candidates'])
    require(isinstance(keys, list), 'candidate_ids必须为数组')
    refs = []
    for key in keys:
        row = session['candidates'].get(key)
        valid = (row and (owner_id is None or row.get('owner_id') == owner_id) and not row.get('stale')
                 and row.get('assessment', {}).get('useful') and row.get('quick_sources')
                 and row['assessment'].get('sources_digest') == digest(row['quick_sources']))
        if candidate_ids is not None:
            require(valid, '候选必须是当前Owner已交付且接受的固定片段')
        if valid:
            refs.extend(row['quick_sources'])
    return list({digest(ref): ref for ref in refs}.values())


def synthesize(reading, session, raw, state):
    """用实际全文或接受片段校验综合稿；保存底稿指纹防止底稿改写后静默复用。"""
    from .reading import require
    from .reading_owner import note_owner, owner_stale
    sources = accepted_sources(session)
    for oid, progress in session.get('owner_progress', {}).items():
        if not owner_stale(session, oid, use_note=False):
            sources.extend(progress.get('delivered_sources', []))
            if progress.get('full_delivered'):
                sources.extend(progress.get('root_refs', []))
            sources.extend(progress.get('expanded_sources', []))
    require(bool(sources), '综合note需要本RS实际交付的依据')
    temporary = deepcopy(session)
    temporary['strategy'] = 'standard'
    temporary.setdefault('owner_progress', {})['RS-SYNTHESIS'] = {'full_delivered': True, 'sources': sources}
    result = note_owner(reading, temporary, {'owner_id': 'RS-SYNTHESIS', 'research_note': raw['research_note']}, state)
    note = temporary['owner_notes']['RS-SYNTHESIS']
    cited = {ref['id'] for ref in note['sources']}
    cited_owners = {row.get('owner_id') for row in session['candidates'].values() if row['ref']['id'] in cited}
    # Expanded files/Run refs need not have a candidate row. Their actual
    # delivery is bound to the selected Owner's progress, which is authoritative.
    for oid, progress in session.get('owner_progress', {}).items():
        if any(ref['id'] in cited for ref in progress.get('delivered_sources', []) +
               progress.get('root_refs', []) + progress.get('expanded_sources', [])):
            cited_owners.add(oid)
    cited_owners.discard(None)
    selected = {oid for oid, row in session.get('owner_progress', {}).items() if row.get('selected')}
    require(len(selected | cited_owners) <= session['context']['max_owners'], '综合稿累计涉及Owner超过max_owners')
    note['coverage'] = 'actual_delivered_sources_only'
    note['basis_owner_ids'] = sorted(cited_owners)
    note['limitations'] = list(dict.fromkeys(note['limitations'] + ['综合稿仅覆盖本RS实际交付正文及已接受召回片段；未展开引用不代表已读。']))
    note['owner_notes_digest'] = digest(session.get('owner_notes', {}))
    note['accepted_sources_digest'] = digest(accepted_sources(session))
    for oid in cited_owners:
        # Cumulative selection is shared with read/note. It never implies that
        # a fragment-only Owner was completely read, even after mode switches.
        session.setdefault('owner_progress', {}).setdefault(oid, {'full_delivered': False, 'sources': []})['selected'] = True
    session['synthesis_note'] = note
    return {**result, 'synthesis': True}
