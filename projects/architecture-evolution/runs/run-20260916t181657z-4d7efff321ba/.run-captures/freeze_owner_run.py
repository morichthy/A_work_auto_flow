"""Freeze this development experiment's source and receipts without rewriting history.

Run only after the readers/tests have finished.  The exclusive output directory
prevents a retry from replacing previously recorded evidence.  Business source
files, models and private configuration are not copied into the source archive.
This is evidence capture, not a release bundle or a semantic verification tool.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parents[1]
CAPTURE = RUN / '.run-captures'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    out = CAPTURE / 'final-evidence'
    out.mkdir(exist_ok=False)
    files = set((ROOT / 'automation/scripts').rglob('*.py'))
    files.update((ROOT / 'automation/tests').glob('test_reading*.py'))
    files.update((ROOT / 'automation/tests').glob('test_workspace_settings*.py'))
    files.update((ROOT / 'automation/tests').glob('test_material_query*.py'))
    files.update((ROOT / 'automation/frontend/src').rglob('*.tsx'))
    files.update((ROOT / 'automation/frontend/src').rglob('*.ts'))
    files.update((ROOT / 'automation/frontend/src').rglob('*.css'))
    files.update((ROOT / 'automation/workflows').rglob('SKILL.md'))
    for relative in [
        'README.md', 'ARCHITECTURE.md', 'docs/CORE.md', 'docs/AI_READING.md',
        'docs/WORKSPACE_SETTINGS.md', 'docs/TESTING.md', 'docs/DEVELOPMENT_HISTORY.md',
        'automation/testing/catalog.json', 'automation/ui/workbench-assets/asset-manifest.json',
        'automation/frontend/e2e/settings.spec.ts', 'automation/frontend/package-lock.json',
        'automation/tests/test_deployment_workbench.py', 'automation/tests/upgrade_fixture.py',
        'automation/tests/test_memory_documents_v3.py', 'automation/tests/material_query_fixture.py',
    ]:
        path = ROOT / relative
        if path.is_file():
            files.add(path)
    records = []
    with zipfile.ZipFile(out / 'source.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            raw = path.read_bytes()
            relative = path.relative_to(ROOT).as_posix()
            archive.writestr(relative, raw)
            records.append({'path': relative, 'bytes': len(raw), 'sha256': sha(raw)})
    manifest = {'captured_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'Selected runtime, reading/settings/upgrade tests, frontend source, skills and docs; not a complete release.',
                'files': records, 'source_zip_sha256': sha((out / 'source.zip').read_bytes())}
    (out / 'source-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    artifacts = []
    # Only explicit experiment containers are registered, not unrelated project
    # history or mutable RS HEAD files. Their API receipts preserve fixed refs.
    for directory in ['verification', 'owner-smoke', 'owner-smoke-progressive']:
        base = CAPTURE / directory
        if base.is_dir():
            for path in sorted(base.rglob('*')):
                if path.is_file():
                    artifacts.append({'path': path.relative_to(ROOT).as_posix(),
                                      'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())})
    (out / 'artifact-manifest.json').write_text(json.dumps({'files': artifacts}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'directory': str(out), 'source_count': len(records), 'artifact_count': len(artifacts),
                      'source_zip_sha256': manifest['source_zip_sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
