"""最终只读核验固定Run与源码，并固化收口回执；不重写已登记证据。"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import evidence
from memory import api
from memory.service import MemoryService


def main():
    run = evidence.read(RUN / 'run.json')
    unit = evidence.read(RUN / 'memory-save/reader-unit-readback.json')
    if evidence.fingerprint(run) != unit['payload']['run_ref']['sha256']:
        raise RuntimeError('Run在技术单元固定引用后发生变化')
    for item in run['inputs'] + run['artifacts']:
        if hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('登记文件变化：' + item['path'])
    sources = evidence.read(RUN / 'verification/source-manifest.json')['files']
    for name, expected in sources.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('源码在验证快照后变化：' + name)
    identities = evidence.read(RUN / 'memory-save/identities.json')
    head = api.dispatch(MemoryService(ROOT), 'inspect', {'owner_id': 'PRJ-ARCHITECTURE-EVOLUTION'})['head']
    if head != identities['head']:
        raise RuntimeError('成果保存后Owner有并发变化，须重新评估')
    for key in ('unit', 'section', 'document', 'overview'):
        receipt = evidence.read(RUN / f'memory-save/reader-{key}-commit.json')
        if receipt.get('error') or receipt['index_status'] != 'indexed':
            raise RuntimeError('保存/索引未完成：' + key)
    summary = {'registered_files_verified': len(run['inputs']) + len(run['artifacts']),
               'framework_files_verified': len(sources), 'fixed_run_hash': evidence.fingerprint(run),
               'head': head, 'document': identities['document'],
               'uncovered_historical_detail_ids': identities['coverage']['uncovered_detail_ids']}
    supplemental = [p for p in RUN.rglob('*') if p.is_file() and p.name != 'closure-manifest.json'
                    and '.run-captures' not in p.parts and '__pycache__' not in p.parts]
    summary['files'] = {p.relative_to(RUN).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in supplemental}
    (RUN / 'closure-manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key != 'files'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
