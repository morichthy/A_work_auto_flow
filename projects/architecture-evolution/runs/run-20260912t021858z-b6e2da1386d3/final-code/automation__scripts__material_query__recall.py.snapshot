"""Bounded retrieval providers; canonical authorization stays in Coordinator.

SQLite/Qdrant contain disposable search metadata. Their scores never authorize
body reads or prove semantic truth. All candidates still pass fixed source checks.
"""
from memory import index
from memory.errors import MemoryError
from .validation import QueryError


def dense(root, db, state, owner_ids, source_kinds, limit):
    """Reuse the offline encoder and reject stale physical entry signatures.

    Allowed IDs are metadata, not record bodies. SQL filters the selected content
    kind before vector ranking. The current local backend scans vectors internally;
    only bounded groups/windows cross back into the query coordinator.
    """
    marks = ','.join('?' for _ in owner_ids)
    kind_sql = ' AND kind IN (' + ','.join('?' for _ in source_kinds) + ')' if source_kinds else ''
    backend = None
    output, gaps = [], []
    try:
        eligible = set()
        for row in db.execute(f"SELECT canonical_id FROM memory_records WHERE owner_id IN ({marks}) "
            "AND entity_kind IN ('record','claim') AND sensitivity!='restricted'" + kind_sql,
            [*owner_ids, *source_kinds]):
            state.ledger.checkpoint()
            eligible.add(row['canonical_id'])
        if not eligible:
            return output, gaps
        backend = index.MemoryVectorBackend(root)
        rows = backend.search_bounded(state.recall['text'], eligible, owner_ids=owner_ids,
                                      limit=limit, ledger=state.ledger)
        for hit in rows:
            state.ledger.checkpoint()
            # A stale vector may still exist after a failed partial sync. Its
            # signature must match the current FTS entry before it earns a vote.
            row = db.execute("""SELECT r.canonical_id,r.record_id,r.owner_id,r.entity_kind,
                r.revision,r.content_hash,r.keywords,e.entry_id,e.representation_id,e.block_id,
                e.signature FROM memory_entries e JOIN memory_records r ON r.canonical_id=e.canonical_id
                WHERE e.entry_id=? AND e.owner_id IN (""" + marks + ')',
                [hit.get('entry_id'), *owner_ids]).fetchone()
            if row is None or row['canonical_id'] not in eligible or row['signature'] != hit.get('signature'):
                gaps.append('部分向量条目版本失配，已省略；需要重建索引')
                continue
            output.append({**dict(row), 'raw_score': hit['raw_score'],
                           'start': hit.get('start', 0), 'end': hit.get('end', 0)})
        watermarks = db.execute(f'SELECT * FROM memory_index_state WHERE owner_id IN ({marks})', owner_ids)
        ready = {row['owner_id'] for row in watermarks if row['vector_status'] == 'indexed'
                 and row['vector_generation'] == row['indexed_generation']
                 and row['encoder_version'] == index.ENCODER_VERSION
                 and row['vector_collection'] == backend.collection}
        if ready != set(owner_ids):
            gaps.append('向量水位未完整覆盖所选范围；请通过索引维护入口补齐')
        if len({row['record_id'] for row in output}) >= limit:
            gaps.append('向量候选窗口已达预算上限，不能保证全量覆盖')
    except QueryError:
        raise  # Cancellation and cumulative budget stops belong to the caller.
    except Exception as exc:
        gaps.append('召回通道 dense 不可用；保留其他通道。' +
                    (str(exc) if isinstance(exc, MemoryError) else '本地模型或存储不可用'))
    finally:
        if backend is not None:
            try:
                backend.close()
            except Exception:
                gaps.append('本地向量连接关闭失败；保留已核验候选')
    return output, gaps
