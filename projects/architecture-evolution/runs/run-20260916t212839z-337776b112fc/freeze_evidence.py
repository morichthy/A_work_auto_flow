"""固定本次局部开发与验证字节；仅本地证据，不是公共发行包。

最后一个开发/文档写入者结束后执行。采用独占创建，拒绝覆盖旧的固定证据。
源码仅用部署白名单，回执仅限本Run；不遍历原件、数据库或模型目录。
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[3]
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import deployment
import evidence
import run_capture


def archive(path, members):
    rows = []
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(set(members)):
            raw = source.read_bytes()
            name = source.relative_to(ROOT).as_posix()
            bundle.writestr(name, raw)
            rows.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    return rows


def main():
    target = RUN / '.run-captures/final-evidence'
    target.mkdir(exist_ok=False, parents=True)
    names = deployment.framework_files(ROOT)
    for required in ('automation/scripts/material_query/reading_notes.py',
                     'automation/scripts/material_query/evidence_navigation.py',
                     'automation/scripts/material_query/reading_citations.py',
                     'automation/frontend/src/EvidenceBrowser.tsx'):
        assert required in names, required
    source_rows = archive(target / 'source.zip', [ROOT / name for name in names])
    receipts = [p for p in RUN.rglob('*') if p.is_file() and target not in p.parents
                and p.name not in {'run.json', 'lineage.jsonl'} and '__pycache__' not in p.parts]
    receipts += [ROOT / 'projects/architecture-evolution/plans/recent-notes-evidence-20260917.md']
    artifact_rows = archive(target / 'receipts.zip', receipts)
    manifest = {'captured_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'Local development evidence; existing dirty changes included; not a release.',
                'source_files': source_rows, 'artifact_files': artifact_rows}
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    # Update only this run's mutable card; past captures and business records stay fixed.
    card = RUN / 'run.json'
    before = card.read_bytes()
    value = json.loads(before)
    value.update(status='completed', started_at=value['created_at'], ended_at=datetime.now(timezone.utc).isoformat(),
                 question='最近问题笔记能否快速展示，且公式、固定引用和记录详情导航保持可追溯？',
                 conclusion='最近24小时多问题选择、轻量快照、编号引用、公式及证据详情已实施；验证与实际限制见RESULTS.md。',
                 limitations=['快照展示不等于证据或科学结论重新核验。',
                              '早期CLI完整性失败与后续API成功差异未定位，未改写历史指纹。',
                              '本机隔离Windows升级验证；未发布，第二物理机未验收。'])
    evidence.replace(card, value, hashlib.sha256(before).hexdigest())
    relative = lambda p: p.relative_to(ROOT).as_posix()
    result = run_capture.register(ROOT, value['run_id'], [relative(target/'source.zip')],
        [relative(target/'receipts.zip'), relative(target/'manifest.json'), relative(RUN/'RESULTS.md'), relative(Path(__file__))])
    print(json.dumps({'registration': result, 'source_files': len(source_rows), 'artifact_files': len(artifact_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
