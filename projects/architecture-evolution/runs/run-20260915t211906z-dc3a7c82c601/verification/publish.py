"""Publish only the audited v0.3.0 artifacts; credentials remain in memory."""
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DEST = ROOT / 'dist/release-v0.3.0'
TAG = 'v0.3.0'
BASE = 'https://api.github.com/repos/livky/A_work_auto_flow'
git = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
head = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
credential = subprocess.run(git + ['credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, check=True)
token = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)['password']
headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
           'X-GitHub-Api-Version': '2022-11-28'}

def api(suffix, method='GET', body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    request = urllib.request.Request(BASE + suffix, data=data, method=method,
                                    headers={**headers, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def push():
    # Follow the host's already-configured network route; do not persist proxy settings.
    proxy = urllib.request.getproxies().get('https') or urllib.request.getproxies().get('http')
    command = git + (['-c', 'http.proxy=' + proxy] if proxy else [])
    subprocess.run(command + ['push', 'origin', 'HEAD:main'], check=True)
    assert api('/commits/main')['sha'] == head
    save('push.json', {'commit': head, 'remote': 'https://github.com/livky/A_work_auto_flow', 'branch': 'main'})
    print('Pushed and verified: ' + head, flush=True)

def draft_and_upload():
    assert api('/commits/main')['sha'] == head
    inventory = json.loads((OUT / 'source-inventory-v0.3.0.json').read_text(encoding='utf-8'))
    assert inventory['revision'] == head
    releases = [r for r in api('/releases') if r['tag_name'] == TAG]
    release = releases[0] if releases else api('/releases', 'POST', {
        'tag_name': TAG, 'target_commitish': head, 'name': 'v0.3.0 — 双语查询与完整成果维护',
        'body': (OUT / 'release-notes.md').read_text(encoding='utf-8'), 'draft': True, 'prerelease': False})
    assert release['draft'], 'Refuse to modify an existing public release'
    save('draft.json', {'id': release['id'], 'commit': head, 'url': release['html_url']})
    for name in ('framework-source-v0.3.0.zip', 'framework-source-v0.3.0.zip.sha256',
                 'dependencies-windows-x64.zip', 'dependencies-windows-x64.zip.sha256'):
        path = DEST / name
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        existing = [a for a in api('/releases/' + str(release['id']) + '/assets') if a['name'] == name]
        if existing:
            asset = existing[0]
        else:
            url = release['upload_url'].split('{')[0] + '?name=' + urllib.parse.quote(name)
            with path.open('rb') as stream:
                request = urllib.request.Request(url, data=stream, method='POST', headers={**headers,
                    'Content-Type': 'application/octet-stream', 'Content-Length': str(path.stat().st_size)})
                with urllib.request.urlopen(request, timeout=900) as response:
                    asset = json.load(response)
        assert asset['size'] == path.stat().st_size and asset.get('digest') == 'sha256:' + digest, name
        print('Uploaded and SHA256 verified: ' + name, flush=True)
    print('Draft attachments complete; ready for separate publication.', flush=True)

def publish():
    draft = json.loads((OUT / 'draft.json').read_text(encoding='utf-8'))
    assert draft['commit'] == head == api('/commits/main')['sha']
    release = api('/releases/' + str(draft['id']))
    expected = {}
    for path in DEST.iterdir():
        if path.name not in {'framework-source-v0.3.0.zip', 'framework-source-v0.3.0.zip.sha256',
                             'dependencies-windows-x64.zip', 'dependencies-windows-x64.zip.sha256'}:
            continue
        with path.open('rb') as stream:
            expected[path.name] = (path.stat().st_size, 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest())
    assets = api('/releases/' + str(draft['id']) + '/assets')
    assert len(assets) == len(expected) == 4
    assert all((a['size'], a.get('digest')) == expected[a['name']] for a in assets)
    if release['draft']:
        release = api('/releases/' + str(draft['id']), 'PATCH', {'draft': False,
            'body': (OUT / 'release-notes.md').read_text(encoding='utf-8'), 'make_latest': 'true'})
    tag = api('/git/ref/tags/' + TAG)['object']
    while tag['type'] == 'tag':
        tag = api('/git/tags/' + tag['sha'])['object']
    assert tag['sha'] == head and not release['draft']
    # Draft assets initially carry an untagged URL; re-read after publication.
    assets = api('/releases/' + str(draft['id']) + '/assets')
    assert len(assets) == 4 and all((a['size'], a.get('digest')) == expected[a['name']] for a in assets)
    receipt = {'commit': head, 'tag': TAG, 'tag_commit': tag['sha'], 'url': release['html_url'],
               'published_at': release['published_at'], 'draft': release['draft'],
               'assets': [{k: a[k] for k in ('name', 'size', 'digest', 'browser_download_url')} for a in assets]}
    save('publication.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)

{'push': push, 'upload': draft_and_upload, 'publish': publish}[sys.argv[1]]()
