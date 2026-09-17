"""Isolated, read-only browser acceptance of the actual floating-point records.

Copies only the named research subtree and its registered local sources. The
original HEAD is checked before/after copying. No product server lease, original
record, source registration or index is modified by this development check.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import uuid

ROOT = Path(os.environ.get('RDWORK_UI_ROOT', Path.cwd())).resolve()
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import workbench

def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    snapshot = ROOT / '.local' / ('floating-ui-' + uuid.uuid4().hex[:10])
    relative = Path('research/floating-point-summation')
    head = ROOT / relative / 'memory/HEAD.json'
    before = head.read_bytes()
    source = ROOT / relative
    # The bounded research directory includes required experiment Runs, fixed
    # original-document snapshots and plotted figures; caches are not copied.
    shutil.copytree(source, snapshot / relative, ignore=shutil.ignore_patterns('__pycache__', '.run-captures'))
    if before != head.read_bytes():
        raise RuntimeError('Research HEAD changed during snapshot; retry after commit')
    shutil.copy2(ROOT / 'workspace.json', snapshot / 'workspace.json')
    registry = json.loads((ROOT / 'retrieval/sources.json').read_text(encoding='utf-8-sig'))
    registry['sources'] = [entry for entry in registry['sources'] if
                           entry.get('path', '').replace('\\', '/').startswith(relative.as_posix() + '/')]
    (snapshot / 'retrieval').mkdir()
    shutil.copy2(ROOT / 'retrieval/config.json', snapshot / 'retrieval/config.json')
    (snapshot / 'retrieval/sources.json').write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding='utf-8')
    hashes = {}
    for path in (snapshot / relative).rglob('*'):
        if path.is_file():
            hashes[path.relative_to(snapshot).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = dict(snapshot_root=str(snapshot), original_root=str(ROOT), research_head=json.loads(before),
                  source_scope=relative.as_posix(), registry_count=len(registry['sources']),
                  files=hashes, synthetic=False, purpose='actual saved records in an isolated fixed snapshot')
    from material_query.evidence_navigation import Catalog
    catalog = Catalog(snapshot)
    try:
        report['records'] = [dict(record_id=record['record_id'], revision=record['revision'],
                                  kind=record['kind'], title=record['title'])
                             for rid, row in catalog.records.items()
                             if row['owner_id'] == 'RES-FLOATING-POINT-SUMMATION'
                             for record in [catalog.record(rid)]]
    finally:
        catalog.close()
    (output / 'FLOATING_UI_SNAPSHOT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'snapshot_root':str(snapshot)}, ensure_ascii=False), flush=True)
    workbench.serve(snapshot, open_browser=False)

if __name__ == '__main__':
    main()
