"""最近阅读问题与展示快照：访问检查和证据重验严格分开。

热读只访问签名sidecar、保存的Markdown与小型授权元数据的stat；登记/HEAD
改变即暂停旧快照，不把缓存当成当前证据。AI handoff保留原完整核验路径。
"""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import hashlib
import json
import os
import uuid

from memory import owners
from memory.errors import MemoryError
from material_query.validation import QueryError
from material_query.reading import path, read_json, save
from material_query.reading_citations import FORMAT_VERSION
from material_query.wire import digest
from .evidence_navigation import Catalog, file_stamp, workspace_id

NOTICE = '此为已保存阅读快照，仅检查当前访问边界；未重新核验证据内容。AI继续使用必须调用reading-handoff。'


def recent_items(rows, now=None):
    now = now or datetime.now(timezone.utc)
    threshold = now - timedelta(hours=24)
    values = []
    for row in rows:
        try:
            updated = datetime.fromisoformat(row['updated_at'].replace('Z', '+00:00'))
            if updated.tzinfo is None:
                continue
            if not row.get('archived') and row.get('note_count', 0) and threshold <= updated <= now:
                values.append(row)
        except (ValueError, KeyError, TypeError):
            continue
    return sorted(values, key=lambda r: (datetime.fromisoformat(r['updated_at'].replace('Z', '+00:00')), r['session_id']), reverse=True)


def locations(root, sid):
    path(root, sid, 'HEAD.json')  # Validate RS identity and reject reparse points.
    home = 'context/reading-notes/' + sid
    return owners.safe_path(root, home + '/current.json'), owners.safe_path(root, home + '/current.md')


def session_refs(value):
    if isinstance(value, dict):
        if value.get('kind') in {'record', 'representation', 'file', 'owner', 'claim'} and 'id' in value and 'sha256' in value:
            yield {'target_kind': 'record' if value['kind'] == 'representation' else value['kind'],
                   'target_id': value['id'], 'revision': value.get('revision'), 'sha256': value.get('sha256'),
                   'locator': value.get('locator'), 'relation': 'references'}
        for child in value.values():
            yield from session_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from session_refs(child)


def authorized(catalog, session):
    access = catalog.access
    original = session.get('access')
    if access is not None and (original is None or not set(original).issubset(access)):
        raise ValueError('阅读记录不属于当前授权域')
    if session.get('owner_id'):
        catalog.owner(session['owner_id'])
    # All saved candidate dependencies participate just as in strong handoff;
    # this checks current sensitivity/registry, never original file hashes.
    catalog.authorize({'sources': list(session_refs({'candidates':session.get('candidates', {}),
        'owner_packets': session.get('owner_packets', {}),
        'owner_notes':session.get('owner_notes', {}), 'synthesis_note':session.get('synthesis_note')}))})


def metadata(session, head):
    updated = session.get('updated_at')
    if not updated:
        revisions = list(head.parent.glob('revision-*.json'))
        stamp = max((entry.stat().st_mtime for entry in revisions), default=head.stat().st_mtime)
        updated = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
    result = {key: deepcopy(session.get(key)) for key in ('session_id', 'revision', 'owner_id', 'goal', 'phase', 'archived')}
    result.update(updated_at=updated, strategy=session.get('strategy', 'standard'),
                  note_count=len(session.get('owner_notes' if session.get('mode') == 'owner_document' else 'notes', {})) + bool(session.get('synthesis_note')))
    return result


def store_sidecar(root, session, value=None, markdown=None, catalog=None):
    """派生sidecar与MD使用各自原子替换、绑定摘要；撕裂写入会被拒绝重建。"""
    own_catalog = catalog is None
    catalog = catalog or Catalog(root, permission_metadata=True)
    try:
        authorized(catalog, session)
        head = path(root, session['session_id'], 'HEAD.json')
        before = file_stamp(root, head.relative_to(root).as_posix())
        if digest(read_json(head)) != digest(session):
            raise ValueError('RS在快照生成期间已变化，请重读选中记录')
        sidecar, target = locations(root, session['session_id'])
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        data = dict(format_version=FORMAT_VERSION, metadata=metadata(session, path(root, session['session_id'], 'HEAD.json')),
                    access=deepcopy(session.get('access')), guard=catalog.guard(), snapshot_ready=value is not None,
                    generated_at=datetime.now(timezone.utc).isoformat(), value=value,
                    markdown_hash=hashlib.sha256(markdown.encode('utf-8')).hexdigest() if markdown is not None else None)
        head_name = head.relative_to(root).as_posix()
        if file_stamp(root, head_name) != before:
            raise ValueError('RS在快照生成期间已变化，请重读选中记录')
        data['guard'][head_name] = before
        save(sidecar, data)
        return data
    finally:
        if own_catalog:
            catalog.close()


def check_sidecar(root, sidecar, access, cache=None):
    sidecar, _ = locations(root, sidecar.parent.name)
    data = read_json(sidecar)
    if data.get('metadata', {}).get('session_id') != sidecar.parent.name:
        raise ValueError('快照RS身份不一致')
    head_name = '.local/reading-sessions/' + sidecar.parent.name + '/HEAD.json'
    if head_name not in data.get('guard', {}):
        raise ValueError('旧快照缺少RS更新水位，需要重新生成')
    original = data.get('access')
    if access is not None and (original is None or not set(original).issubset(set(access))):
        raise ValueError('快照不属于当前授权域')
    cache = {} if cache is None else cache
    for name, before in data.get('guard', {}).items():
        if name not in cache:
            cache[name] = file_stamp(root, name)
        if cache[name] != before:
            raise ValueError('授权或记录元数据发生变化；旧快照暂停展示，请按选中RS重新生成')
    if not data.get('guard'):
        raise ValueError('快照缺少访问边界记录')
    return data


def recent(service, raw):
    if set(raw) - {'owner_id', 'limit', 'offset'}:
        raise ValueError('未知最近问题参数')
    limit, offset = raw.get('limit', 20), raw.get('offset', 0)
    if type(limit) is not int or not 1 <= limit <= 50 or type(offset) is not int or offset < 0:
        raise ValueError('最近问题分页参数无效')
    base = owners.safe_path(service.root, '.local/reading-sessions')
    files = list(base.glob('RS-*/HEAD.json')) if base.exists() else []
    if len(files) > 10000:
        raise ValueError('阅读记录数量超过导航上限')
    rows, warnings, cache, catalog = [], [], {}, None
    try:
        for file in files:
            sid = file.parent.name
            try:
                sidecar, _ = locations(service.root, sid)
                if not sidecar.exists():
                    # One-time old-RS metadata migration does not render all
                    # notes. Only the selected snapshot is rebuilt on demand.
                    session = read_json(path(service.root, sid, 'HEAD.json'))
                    row = metadata(session, file)
                    if not recent_items([row]):
                        continue
                    catalog = catalog or Catalog(service.root, service.materials.access_owner_ids, permission_metadata=True)
                    data = store_sidecar(service.root, session, catalog=catalog)
                else:
                    try:
                        data = check_sidecar(service.root, sidecar, service.materials.access_owner_ids, cache)
                    except (ValueError, OSError, KeyError, MemoryError, QueryError):
                        # Ordinary metadata edits must not make every picker
                        # entry disappear. Recheck only permissions; the body is
                        # invalidated and rebuilt later for the selected RS.
                        session = read_json(path(service.root, sid, 'HEAD.json'))
                        catalog = catalog or Catalog(service.root, service.materials.access_owner_ids, permission_metadata=True)
                        data = store_sidecar(service.root, session, catalog=catalog)
                row = data['metadata']
                rows.append(row)
            except (ValueError, OSError, KeyError, MemoryError, QueryError) as exc:
                warnings.append('部分阅读记录因访问边界变化或快照不可用未列出；请通过 reading-handoff 或 reading-view 接口重新核验。')
        items = recent_items(rows)
        write_recent_navigation(service.root, items)
        if raw.get('owner_id') is not None:
            items = [row for row in items if row['owner_id'] == raw['owner_id']]
        return dict(workspace_id=workspace_id(service.root), items=items[offset:offset+limit], total=len(items),
                    next_offset=offset+limit if offset+limit < len(items) else None, window_hours=24,
                    generated_at=datetime.now(timezone.utc).isoformat(), verification='snapshot_only', warnings=list(dict.fromkeys(warnings)))
    finally:
        if catalog:
            catalog.close()


def snapshot(service, raw):
    if set(raw) != {'session_id'}:
        raise ValueError('快照请求只接受session_id')
    sid = raw['session_id']
    sidecar, target = locations(service.root, sid)
    # A changed guard never permits the old body. Rebuild this selected RS from
    # canonical session metadata under fresh access checks, without original IO.
    try:
        data = check_sidecar(service.root, sidecar, service.materials.access_owner_ids)
        if data.get('format_version') != FORMAT_VERSION or not data.get('snapshot_ready'):
            raise ValueError('展示格式需要重建')
        markdown = target.read_text(encoding='utf-8')
        if hashlib.sha256(markdown.encode('utf-8')).hexdigest() != data['markdown_hash']:
            raise ValueError('可读快照已被修改')
    except (ValueError, OSError, KeyError, MemoryError, QueryError):
        session = read_json(path(service.root, sid, 'HEAD.json'))
        catalog = Catalog(service.root, service.materials.access_owner_ids, permission_metadata=True)
        try:
            authorized(catalog, session)
            from material_query.reading_snapshot import write_snapshot
            write_snapshot(service.root, session, catalog=catalog)
        finally:
            catalog.close()
        data = check_sidecar(service.root, sidecar, service.materials.access_owner_ids)
    value = deepcopy(data['value'])
    value.update(workspace_id=workspace_id(service.root), session_id=sid, revision=data['metadata']['revision'],
                 updated_at=data['metadata']['updated_at'], generated_at=data['generated_at'],
                 mode=value.get('mode', 'legacy'), verification='snapshot_only', warnings=[NOTICE])
    return value


def write_recent_navigation(root, items):
    """静态入口在写入/查询时更新；时钟自身不启动后台任务，不删除历史。"""
    target = owners.safe_path(root, 'context/reading-notes/recent.md')
    target.parent.mkdir(parents=True, exist_ok=True)
    text = '# 最近24小时阅读问题\n\n生成时间：'+datetime.now(timezone.utc).isoformat()+'\n\n'
    text += '> 按内容更新时间排列；查看不延长窗口。此静态入口在笔记写入或最近问题查询时刷新，历史记录不删除。\n\n'
    text += '> '+NOTICE+'\n\n'
    for row in items:
        label = row['goal'].replace('[', '（').replace(']', '）').replace('\n', ' ')
        text += '- ['+label+']('+row['session_id']+'/current.md) · '+row['updated_at']+' · r'+str(row['revision'])+'\n'
    temporary = target.with_name('.pending-'+uuid.uuid4().hex)
    try:
        temporary.write_text(text, encoding='utf-8')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
