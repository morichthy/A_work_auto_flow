"""Freeze this local development result, never a distributable business backup.

Run after all writers finish. Exclusive outputs protect earlier evidence from
being silently overwritten. The deployment allowlist supplies framework inputs;
only this Run's explicit receipts supply outputs. No models or business trees
are traversed for the source snapshot.
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
    """Hash the exact bytes written; paths stay relative to the workspace."""
    rows = []
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(set(members)):
            raw = source.read_bytes()
            name = source.relative_to(ROOT).as_posix()
            bundle.writestr(name, raw)
            rows.append({'path': name, 'bytes': len(raw),
                         'sha256': hashlib.sha256(raw).hexdigest()})
    return rows


def main():
    out = RUN / '.run-captures/final-evidence'
    out.mkdir(exist_ok=False)
    # This also checks the final frontend build fingerprints. The new strategy
    # module must be part of the normal upgrade set without a special installer.
    names = deployment.framework_files(ROOT)
    assert 'automation/scripts/material_query/reading_strategy.py' in names
    source_rows = archive(out / 'source.zip', [ROOT / name for name in names])
    artifacts = [RUN / name for name in (
        'RESULTS.md', 'BACKEND_RESULTS.md', 'UI_RESULTS.md', 'AI_CHECK.md',
        'ai_driver.py', 'AI_FIXTURE.json', 'reading-suite.log',
        'deployment-tests.log', 'deployment-final-retest.log',
        'testing-audit-final.log', 'validate-initial.log', 'validate-final.log',
        'refresh-index.log', 'association-root-retest.log',
        'association-final-retest.log')]
    artifacts += list((RUN / 'ai-receipts').glob('*.json'))
    artifacts += [p for p in (RUN / '.run-captures/ui').rglob('*') if p.is_file()]
    artifacts += [ROOT / 'projects/architecture-evolution/plans/reading-three-modes-20260917.md']
    artifact_rows = archive(out / 'receipts.zip', artifacts)
    manifest = {'captured_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'Local development evidence; includes existing working-tree changes; not a release.',
                'source_files': source_rows, 'artifact_files': artifact_rows}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    card = RUN / 'run.json'
    before = card.read_bytes()
    value = json.loads(before)
    value.update(status='completed', started_at=value['created_at'],
                 ended_at=datetime.now(timezone.utc).isoformat(),
                 question='三种阅读策略能否保持固定证据、累计范围和note质量边界，并由工作台控制？',
                 conclusion='三模式、可保存默认配置、联想线索与综合note已实现；最终软件及合成AI验证见RESULTS.md。',
                 limitations=['AI自查不等于科学复核或用户认可。',
                              '合成场景不能证明真实业务召回率、错误关联率或提速。',
                              '仅本机Windows隔离升级验证；未发布，第二物理机未验收。'])
    evidence.replace(card, value, hashlib.sha256(before).hexdigest())
    relative = lambda path: path.relative_to(ROOT).as_posix()
    result = run_capture.register(ROOT, value['run_id'],
        [relative(out / 'source.zip')],
        [relative(out / 'receipts.zip'), relative(out / 'manifest.json'),
         relative(RUN / 'RESULTS.md'), relative(Path(__file__))])
    print(json.dumps({'registration': result, 'source_files': len(source_rows),
                      'artifacts': len(artifact_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
