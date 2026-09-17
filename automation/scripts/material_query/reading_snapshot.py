"""从已重新授权的RS生成可读笔记；Markdown永不作为状态或输入读取。"""
from datetime import datetime, timezone
import os
import re
import uuid
from copy import deepcopy

from memory import owners
from .reading_delegation import handoff_value, serialized_size


def notes_value(session, max_chars=30000, *, titles=None):
    """与AI交接共用整条note装包，剔除陈旧内容且保留遗漏与固定出处。"""
    if session.get('mode') == 'owner_document':
        from .reading_owner import handoff_value as owner_handoff, source_candidates
        # Human display has its own character cap. A small AI-note allowance
        # must not make an already-saved near-limit note disappear after links
        # are decorated for the UI. The strong AI handoff keeps its own budget.
        displayed = deepcopy(session)
        displayed['citation_titles'] = titles or {}
        displayed.setdefault('context', {})['note_max_tokens'] = max_chars * 4
        value = owner_handoff(displayed, max_chars, display=True)
        value['note_max_tokens'] = session.get('context', {}).get('note_max_tokens', 6000)
        value['display_max_chars'] = max_chars
        value.update(goal=session.get('goal', ''), owner_id=session.get('owner_id'), archived=session.get('archived', False),
                     candidates=source_candidates(session, value['included_owner_ids']), round_count=len(session.get('rounds', [])))
        return value
    window = max_chars
    while True:
        included = []
        value = handoff_value(session, max_chars=window, included_keys=included, display=True)
        # 与整条装包共享实际纳入身份；不从自由Markdown反解析证据关系。
        candidates = []
        for key in included:
            row = session['candidates'][key]
            candidates.append({name: row[name] for name in ('title', 'link', 'ref')})
            candidates[-1].update(candidate_id=key, status='已记录理解', stale=False)
        value.update(goal=session.get('goal', ''), owner_id=session.get('owner_id'), archived=session.get('archived', False),
                     candidates=candidates, round_count=len(session.get('rounds', [])))
        excess = serialized_size(value) - max_chars
        if excess <= 0:
            return value
        # 固定引用等元数据也属于完整响应上限；缩小整note窗口后重新装包，
        # 绝不截断公式/来源。无法容纳元数据时由handoff明确拒绝。
        window -= excess
        if window < 512:
            from .validation import QueryError
            raise QueryError('BUDGET', '笔记展示元数据超出字符上限，未输出截断内容')


def write_snapshot(root, session, *, catalog=None):
    """共享读模型提供轻量权限与标题；不从核心反向依赖HTTP展示层。"""
    from .evidence_navigation import Catalog
    own_catalog = catalog is None
    catalog = catalog or Catalog(root, permission_metadata=True)
    try:
        return _write_snapshot(root, session, catalog=catalog)
    finally:
        if own_catalog:
            catalog.close()


def _write_snapshot(root, session, *, catalog):
    """授权成功后原子替换派生快照；既有快照不证明后续授权/来源仍有效。"""
    # safe_path逐层拒绝符号链接/重解析点；身份由Reading入口校验。
    from .reading import path
    path(root, session['session_id'], 'HEAD.json')
    relative = f"context/reading-notes/{session['session_id']}/current.md"
    target = owners.safe_path(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = owners.safe_path(root, relative)
    titles = {oid: row['title'] for oid, row in catalog.owners.items()}
    titles.update({rid: row['title'] for rid, row in catalog.records.items() if row.get('title')})
    from .evidence_navigation import read_json
    from pathlib import Path
    registry = owners.safe_path(root, 'retrieval/sources.json')
    if registry.exists():
        for source in read_json(registry).get('sources', []):
            identity = source.get('source_id') or source.get('id')
            if identity:
                titles[identity] = source.get('title') or source.get('name') or Path(source['path']).name
    value = notes_value(session, titles=titles)
    from .reading_citations import render
    from .reading_strategy import configuration
    sources = [ref for note in session.get('owner_notes', {}).values() for ref in note.get('sources', [])]
    if session.get('synthesis_note'):
        sources.extend(session['synthesis_note'].get('sources', []))
    if session.get('mode') != 'owner_document':
        sources.extend(session['candidates'][key]['ref'] for key in session.get('notes', {}) if key in session['candidates'])
    titles.update({row['ref']['id']: row['title'] for row in session.get('candidates', {}).values() if row.get('title')})
    value.setdefault('references', render('', sources, titles)[1])
    value.update(configuration(session))
    value['mode'] = session.get('mode', 'legacy')
    # A saved research goal is the human-facing name; RS remains the stable
    # identity. Normalize only this heading, leaving the full goal below intact.
    # Escape Markdown metacharacters so a question cannot turn into a heading
    # link or HTML. This does not rename directories or create another state.
    title = ' '.join((session.get('goal') or '未命名问题').split())
    title = title[:80] + ('…' if len(title) > 80 else '')
    title = re.sub(r'([\\`*_\[\]<>#])', r'\\\1', title)
    content = (f"# 阅读笔记：{title}\n\n问题标识：`{session['session_id']}` · 版本 r{session['revision']}\n\n"
               f"生成时间：{datetime.now(timezone.utc).isoformat()}\n\n"
               "> 本文件是RS JSON记录的可读派生快照，不是权威状态。它不会自动体现后续撤权或来源变化；"
               "继续使用前须经阅读接口重新核验授权与固定来源。生成不调用AI、不检索、不重置阅读预算。\n\n"
               "> 本副本独立采用30,000字符展示窗口，实际AI交接可能使用更小窗口；此文件不证明AI已接收全部内容。遗漏见下文。\n\n"
               + value['context_markdown'] + '\n' +
               ('\n## 当前交付缺口\n\n' + '\n'.join('- ' + gap for gap in value['gaps']) + '\n' if value.get('gaps') else ''))
    temporary = target.with_name('.pending-' + uuid.uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        owners.safe_path(root, relative)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    from .reading_notes import store_sidecar, check_sidecar, recent_items, write_recent_navigation
    store_sidecar(root, session, value, content, catalog)
    # Only sidecar metadata is needed to maintain the context entry. Existing
    # history is retained; no unrelated RS body is rebuilt here.
    rows, cache = [], {}
    for file in (root / 'context/reading-notes').glob('RS-*/current.json'):
        try:
            rows.append(check_sidecar(root, file, None, cache)['metadata'])
        except (OSError, ValueError, KeyError):
            continue
    write_recent_navigation(root, recent_items(rows))
