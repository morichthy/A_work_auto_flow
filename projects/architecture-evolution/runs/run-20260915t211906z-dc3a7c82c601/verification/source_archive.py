"""Audit a git archive: distribution boundaries, frontend hashes, and required entries."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
revision, label = sys.argv[1:3]
destination = ROOT / 'dist/release-v0.3.0'
destination.mkdir(parents=True, exist_ok=True)
archive_path = destination / ('framework-source-' + label + '.zip')
assert not archive_path.exists(), 'Refuse to overwrite an audited archive'
subprocess.run(['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'archive', '--format=zip',
                '--output=' + str(archive_path), revision], cwd=ROOT, check=True)
with zipfile.ZipFile(archive_path) as archive:
    files = {p for p in archive.namelist() if not p.endswith('/')}
    denied = [p for p in files if p.startswith(('projects/architecture-evolution/', 'research/floating-point-summation/',
        'research/ai-experience-context/', '.local/', 'services/qdrant/runtime/', 'services/qdrant/storage/',
        'tools/memory/', 'tools/runtime/', 'context/generated/')) or p in
        {'retrieval/sources.json', 'retrieval/query-terms.json', 'context/NOW.md', 'AI检索思路'}]
    assert not denied, denied
    # Each instance root may only retain its rules, README and reusable template.
    for root in ('projects', 'research', 'core-algorithms', 'runs'):
        unexpected = [p for p in files if p.startswith(root + '/') and len(p.split('/')) > 2
                      and p.split('/')[1] != '_template']
        assert not unexpected, unexpected
    required = {'setup.cmd', 'automation/templates/query-terms.default.json',
                'automation/workflows/consolidate-results/SKILL.md', '.agents/skills/consolidate-results/SKILL.md',
                'automation/scripts/material_query/query_plan.py', 'docs/CORE.md', 'docs/MEMORY_STORAGE_EXPLAINED.md'}
    assert required <= files, required - files
    manifest = json.loads(archive.read('automation/ui/workbench-assets/asset-manifest.json'))
    for category, prefix in [('sources', 'automation/frontend/'), ('files', 'automation/ui/workbench-assets/')]:
        for name, expected in manifest[category].items():
            assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == expected, prefix + name
    inventory = {p: hashlib.sha256(archive.read(p)).hexdigest() for p in sorted(files)}
    # Extraction is into a new isolated directory, after checking traversal.
    target = OUT / ('source-' + label)
    assert not target.exists()
    assert all(not p.startswith('/') and '..' not in Path(p).parts for p in archive.namelist())
    archive.extractall(target)
digest = hashlib.file_digest(archive_path.open('rb'), 'sha256').hexdigest()
archive_path.with_suffix('.zip.sha256').write_text(digest + '  ' + archive_path.name + '\n', encoding='ascii')
result = dict(revision=revision, archive=str(archive_path), sha256=digest, files=len(inventory),
              private_data_excluded=True, frontend_hashes_match=True, inventory=inventory)
(OUT / ('source-inventory-' + label + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k != 'inventory'}), flush=True)
