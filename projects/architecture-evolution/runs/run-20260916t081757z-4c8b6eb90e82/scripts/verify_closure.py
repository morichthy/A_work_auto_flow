"""只读核验已登记Run、源码及当前HEAD，固定补充回执，不改旧来源。"""
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
    folder = RUN / 'memory-update-v2'
    unit = evidence.read(folder / 'settings-unit-r2-readback.json')
    assert evidence.fingerprint(run) == unit['payload']['run_ref']['sha256'], '固定Run发生变化'
    for item in run['inputs'] + run['artifacts']:
        assert hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
    sources = evidence.read(RUN / 'verification/source-manifest.json')['files']
    for name, expected in sources.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    saved_heads = list(folder.glob('owner-head-*.json'))
    assert len(saved_heads) == 1
    saved = evidence.read(saved_heads[0])
    current = api.dispatch(MemoryService(ROOT), 'inspect', {'owner_id': 'PRJ-ARCHITECTURE-EVOLUTION'})
    assert current['head'] == saved['head'], '全文检查后有并发变化，需要补充审查'
    for key in ('01-unit', '02-sections-overviews', '03-documents'):
        receipt = evidence.read(folder / (key + '-commit.json'))
        assert not receipt.get('error') and receipt['index_status'] == 'indexed', key
    identities = evidence.read(folder / 'identities.json')
    summary = {'registered_files_verified': len(run['inputs']) + len(run['artifacts']),
               'framework_files_verified': len(sources), 'fixed_run_hash': evidence.fingerprint(run),
               'head': current['head'], 'identities': identities}
    # 补充脚本、失败请求、最终回读和收口说明以独立清单固定；不重登记修改Run hash。
    summary['files'] = {p.relative_to(RUN).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in RUN.rglob('*') if p.is_file() and p.name != 'closure-manifest.json'
                        and '.run-captures' not in p.parts and '__pycache__' not in p.parts}
    (RUN / 'closure-manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'files'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
