"""Check existing dependency ZIP bytes and GitHub metadata without exposing credentials."""
import hashlib
import json
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import dependency_bundle

def dependencies():
    path = ROOT / 'dist/release-v0.2.0/dependencies-windows-x64.zip'
    digest = dependency_bundle.sha(path)
    assert digest == path.with_suffix('.zip.sha256').read_text().split()[0]
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('dependency-manifest.json'))
        assert manifest['packages'] == dependency_bundle.locked(ROOT)
        model_path = 'services/qdrant/model-manifest.json'
        assert json.loads(archive.read(model_path)) == json.loads((ROOT / model_path).read_text(encoding='utf-8'))
        assert set(archive.namelist()) == set(manifest['files']) | {'dependency-manifest.json'}
        for name, expected in manifest['files'].items():
            assert dependency_bundle.allowed(name), name
            with archive.open(name) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, name
    result = dict(sha256=digest, id=manifest['id'], files=len(manifest['files']), bytes=path.stat().st_size,
                  locks_match=True, model_matches=True, all_file_hashes_match=True)
    (OUT / 'dependency-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)

def remote():
    git = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
    proc = subprocess.run(git + ['credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                          text=True, capture_output=True, check=True)
    credential = dict(line.split('=', 1) for line in proc.stdout.splitlines() if '=' in line)
    headers = {'Authorization': 'Bearer ' + credential['password'], 'Accept': 'application/vnd.github+json'}
    base = 'https://api.github.com/repos/livky/A_work_auto_flow'
    result = {}
    for key, suffix in [('repo', ''), ('releases', '/releases'), ('main', '/commits/main')]:
        with urllib.request.urlopen(urllib.request.Request(base + suffix, headers=headers), timeout=60) as response:
            value = json.load(response)
        if key == 'repo': result[key] = {k: value[k] for k in ('full_name', 'private', 'default_branch')}
        elif key == 'main': result[key] = value['sha']
        else: result[key] = [{k: r[k] for k in ('id', 'tag_name', 'draft', 'html_url')} for r in value]
    (OUT / 'remote-before.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)

if __name__ == '__main__':
    {'dependencies': dependencies, 'remote': remote}[sys.argv[1]]()
