"""按Owner发现阅读会话；只读有界目录，不建立第二份RS索引或知识真源。"""
from itertools import islice
from datetime import datetime, timezone
import json
from .budget import DEFAULT_BUDGET, Ledger
from .coordinator import envelope
from .reading import BASE, path, read_json, require
from .validation import object_fields, QueryError
from memory.errors import MemoryError


def listing(reading, raw):
    object_fields(raw, set(), {'owner_id', 'offset', 'limit', 'include_archived'})
    offset, limit = raw.get('offset', 0), raw.get('limit', 20)
    require(type(offset) is int and offset >= 0, 'offset必须为非负整数')
    require(type(limit) is int and 1 <= limit <= 50, 'limit必须为1到50')
    require(type(raw.get('include_archived', False)) is bool, 'include_archived必须是布尔值')
    oid = raw.get('owner_id')
    require(oid is None or isinstance(oid, str) and bool(oid.strip()), 'owner_id必须是非空字符串')
    # 目录元数据盘点独立受有界预算约束；不执行研究召回或模型编码，
    # 也不返回笔记正文。查看正文仍走view的持久会话账本。
    reading.ledger = Ledger(DEFAULT_BUDGET)
    base = reading.root / BASE
    paths = list(islice(base.glob('RS-*/HEAD.json'), 10001)) if base.exists() else []
    require(len(paths) <= 10000, '阅读目录超过10000会话，需维护目录容量后重试；归档标记不会删除目录')
    items, unavailable = [], 0
    with reading.ledger.active():
        for candidate in paths:
            state = None
            try:
                file = path(reading.root, candidate.parent.name, 'HEAD.json')
                reading.ledger.charge('read_bytes', file.stat().st_size)
                session = read_json(file)
                if not reading.can_access(session):
                    continue
                if oid is not None and session.get('owner_id') != oid:
                    continue
                if session.get('archived') and not raw.get('include_archived', False):
                    continue
                state = reading.state(session)
                reading.reauthorize(session, state)
                item = {key: session.get(key) for key in ('session_id', 'revision', 'owner_id', 'goal', 'phase', 'archived')}
                # 旧RS没有时间字段时用语义修订文件；HEAD的mtime会被只读账本更新，
                # 不能把一次查看误当笔记内容的新更新。无修订文件才回退HEAD。
                updated = session.get('updated_at')
                if not updated:
                    revisions = list(candidate.parent.glob('revision-*.json'))
                    stamp = max((entry.stat().st_mtime for entry in revisions), default=file.stat().st_mtime)
                    updated = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
                item.update(note_count=len(session.get('owner_notes' if session.get('mode') == 'owner_document' else 'notes', {})), updated_at=updated)
                if session.get('mode') == 'owner_document' and session.get('synthesis_note'):
                    item['note_count'] += 1
                items.append(item)
            except QueryError as exc:
                # 目录预算耗尽不能被吞成“没有记录”；明确失败让用户保留现有视图。
                if exc.code in {'BUDGET', 'CANCELLED'}:
                    raise
                unavailable += 1
            except (MemoryError, OSError, ValueError, KeyError):
                # 不泄漏不可读会话的身份、目标或路径；其他会话仍可查看。
                unavailable += 1
            finally:
                if state is not None:
                    reading.app.store.states.pop(state.query_id, None)
    # 过滤、授权之后再分页，避免某Owner被其他Owner或归档记录挤到空页。
    items.sort(key=lambda item: (bool(item['note_count']), item['updated_at'], item['session_id']), reverse=True)
    selected = items[offset:offset + limit]
    reading.ledger.charge('output_chars', len(json.dumps(selected, ensure_ascii=False)))
    next_offset = offset + len(selected) if offset + len(selected) < len(items) else None
    result = envelope({'items': selected, 'next_offset': next_offset, 'unavailable_count': unavailable,
                       'scope_note': '按归属和当前授权筛选后分页；有笔记优先，同类按最近内容更新排序。未绑定旧会话可在全局列表发现。'})
    result['consumed'] = reading.ledger.snapshot()
    return result
