"""固定本机 HTTP 与 CLI 共用契约，真实 socket 校验错误码和保存身份。"""
from copy import deepcopy
import builtins
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

import test_memory_store as fixture
from test_memory_store import request, draft
from memory.cli import execute
from memory import index
from memory.errors import MemoryError
import evidence_view


class MemoryHttpTests(unittest.TestCase):
    def setUp(self):
        fixture.MemoryStoreTests.setUp(self)
        self.server, self.url = evidence_view.create_server(self.root, controller=SimpleNamespace(app=SimpleNamespace(root=self.root)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        fixture.MemoryStoreTests.tearDown(self)

    def post(self, action, value, *, origin=None):
        headers = {"Content-Type": "application/json", "Origin": origin or self.url.split('/',3)[0]+'//'+self.url.split('/')[2]}
        req = Request(self.url + 'api/v1/memory/' + action, json.dumps(value).encode(), headers)
        try:
            response = urlopen(req, timeout=60)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def cli(self, action, value):
        path = self.root/'request.json'; path.write_text(json.dumps(value), encoding='utf-8')
        return execute(self.root, [action, '--request', str(path)])

    def test_U01_U03_same_request_identity_and_index_pending(self):
        req = request()
        with patch.object(index, 'sync_owner', side_effect=OSError('SYNTHETIC INDEX FAILURE')):
            status, http = self.post('commit', req)
        self.assertEqual(status, 202)
        self.assertEqual(http['save_status'], 'committed')
        cli, code = self.cli('commit', req)
        self.assertEqual(code, 3)
        for field in ('commit_id', 'generation', 'record_results', 'save_status'):
            self.assertEqual(http[field], cli[field])
        bad = request(head=http['commit_id']); bad['operations'][0]['draft']['level'] = 'L4'
        hs, hv = self.post('commit', bad); cv, cc = self.cli('commit', bad)
        self.assertEqual(hs, 422); self.assertEqual(cc, 2)
        self.assertEqual(hv['error'], cv['error'])
        rid = http['record_results'][0]['record_id']
        changed = draft(); changed['body_markdown'] = '新版本'
        accepted = self.service.commit(request(changed, head=http['commit_id'], rid=rid, revision=1))
        stale = request(draft(), head=http['commit_id'], rid=rid, revision=1)
        status, error = self.post('commit', stale)
        self.assertEqual(status, 409); self.assertEqual(error['error']['code'], 'VERSION_CONFLICT')
        self.assertEqual(self.service.inspect('RES-TEST')['head']['commit_id'], accepted['commit_id'])

    def test_discovery_gap_and_rebuild_actions_use_real_http_dispatch(self):
        """The workbench HTTP wildcard must expose the same auditable repair surface."""
        from memory import discovery
        from memory.store import MemoryStore
        from memory import owners
        self.service.commit(request())
        owner = owners.resolve_owner(self.root, 'RES-TEST')
        head = MemoryStore(self.root).read_snapshot(owner)['head']
        status, gaps = self.post('discovery-gaps', {'owner_id': 'RES-TEST'})
        self.assertEqual(status, 200, gaps)
        self.assertEqual(gaps['owners'][0]['owner_id'], 'RES-TEST')
        status, preview = self.post('rebuild-discovery', {
            'owner_id': 'RES-TEST', 'expected_head': head,
            'projection_version': discovery.PROJECTION_VERSION,
            'vector': 'off', 'dry_run': True})
        self.assertEqual(status, 200, preview)
        self.assertTrue(preview['dry_run'])
        self.assertEqual(preview['writes'], 0)
        status, built = self.post('rebuild-discovery', {
            'owner_id': 'RES-TEST', 'expected_head': head,
            'projection_version': discovery.PROJECTION_VERSION,
            'vector': 'off'})
        self.assertEqual(status, 200, built)
        self.assertEqual(built['index_status'], 'indexed')

    def test_U08_origin_shell_and_path_do_not_read_external(self):
        status, _ = self.post('commit', request(), origin='https://untrusted.invalid')
        self.assertEqual(status, 403)
        status, error = self.post('shell', {'command': 'echo injected'})
        self.assertEqual(status, 400); self.assertEqual(error['error']['code'], 'INVALID_ARGUMENT')
        with patch('pathlib.Path.read_bytes', side_effect=AssertionError('must not read arbitrary path')):
            status, error = self.post('adopt-owner', {'native_ref': '../secret.txt', 'expected_hash': '0'*64, 'actor': {'kind':'ai','id':'synthetic'}})
        self.assertEqual(status, 403); self.assertEqual(error['error']['code'], 'UNSAFE_PATH')
        value = draft(); value['title'] = '<script>globalThis.pwned=1</script>'
        receipt = self.service.commit(request(value))
        status, exported = self.post('export', {'owner_id':'RES-TEST','format':'html'})
        self.assertEqual(status, 200)
        self.assertNotIn('<script>', exported['content'])
        self.assertIn('&lt;script&gt;', exported['content'])

    def test_U01_real_review_and_subprocess_stdout_match_public_http(self):
        # 用已登记合成文本执行真实复核，不能用模拟成功回执代替两个入口。
        source = self.root/'review-source.txt'
        source.write_text('SYNTHETIC ONLY transport review\n', encoding='utf-8')
        (self.root/'retrieval').mkdir(exist_ok=True)
        (self.root/'retrieval/sources.json').write_text(json.dumps({'schema_version': 1, 'sources': [
            {'source_id': 'SRC-HTTP-REVIEW', 'path': source.name, 'enabled': True, 'sensitivity': 'internal'}]}), encoding='utf-8')
        ref = {'target_kind': 'file', 'target_id': 'SRC-HTTP-REVIEW', 'revision': None,
               'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'relation': 'supports', 'locator': 'lines:1-1'}
        value = draft()
        value['sources'] = [dict(ref, relation='background')]
        value['payload']['claims'] = [{'claim_id': 'CLM-HTTP-'+str(n), 'statement': 'SYNTHETIC ONLY 文本标记 '+str(n),
            'kind': 'fact', 'scope': 'synthetic:http', 'evidence_refs': [ref]} for n in (1, 2)]
        saved = self.service.commit(request(value))
        review = {'schema_version': 1, 'request_id': str(uuid.uuid4()), 'owner_id': 'RES-TEST',
                  'expected_head': saved['commit_id'], 'actor': {'kind': 'workflow', 'id': 'synthetic-http-test'},
                  'target_claim_id': 'CLM-HTTP-1', 'state': 'accepted', 'reason': '合成传输契约验证',
                  'scope': None, 'evidence_refs': [ref]}
        head = self.service.inspect('RES-TEST')['head']
        hs, invalid_http = self.post('review', review)
        invalid_cli, code = self.cli('review', review)
        self.assertEqual((hs, code), (422, 9))
        self.assertEqual(invalid_http, invalid_cli)
        self.assertEqual(self.service.inspect('RES-TEST')['head'], head)
        review['scope'] = 'synthetic:http'
        hs, accepted_http = self.post('review', review)
        accepted_cli, code = self.cli('review', review)
        self.assertEqual((hs, code), (202, 3))
        for key in ('commit_id', 'save_status', 'record_results', 'index_status'):
            self.assertEqual(accepted_http[key], accepted_cli[key])
        actual = self.service.inspect('RES-TEST')
        self.assertEqual(actual['claim_states']['CLM-HTTP-1']['review_state'], 'accepted')
        self.assertEqual(actual['claim_states']['CLM-HTTP-2']['review_state'], 'not-reviewed')
        # 真子进程标准输出必须只含JSON；不是仅调用execute后检查Python对象。
        result = subprocess.run([sys.executable, str(Path(fixture.__file__).parents[1]/'scripts/workspace_cli.py'),
            '--root', str(self.root), 'memory', 'inspect', 'RES-TEST'], capture_output=True,
            env={**os.environ, 'PYTHONUTF8': '1'}, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertEqual(json.loads(result.stdout), actual)

    def test_U08_unregistered_preview_hash_open_never_read_external_file(self):
        # 原件位于目标工作区之外；既不登记也不授权。监测实际底层打开和
        # 读字节路径，允许工具读取自己的配置，禁止碰到这个受控哨兵文件。
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC 外部只读边界 ') as external_dir:
            secret = Path(external_dir)/'未授权.txt'
            secret.write_text('SYNTHETIC FORBIDDEN CONTENT', encoding='utf-8')
            accesses = []
            old_open, old_path_open, old_read = builtins.open, Path.open, Path.read_bytes
            def check(path, action):
                if isinstance(path, (str, os.PathLike)) and Path(path).resolve() == secret.resolve():
                    accesses.append(action)
                    raise AssertionError('未经授权读取外部文件')
            def guarded_open(path, *args, **kwargs):
                check(path, 'open')
                return old_open(path, *args, **kwargs)
            def guarded_path_open(path, *args, **kwargs):
                check(path, 'Path.open')
                return old_path_open(path, *args, **kwargs)
            def guarded_read(path):
                check(path, 'read/hash')
                return old_read(path)
            ref = {'target_kind': 'file', 'target_id': str(secret), 'revision': None,
                   'sha256': None, 'locator': '', 'relation': 'background'}
            cases = [('hash', {'path': str(secret)}), ('open', {'path': str(secret)}),
                     ('shell', {'command': 'powershell Get-Content '+str(secret)}),
                     ('adopt-owner', {'native_ref': str(secret), 'expected_hash': '0'*64,
                                      'actor': {'kind': 'ai', 'id': 'synthetic'}}),
                     ('expand', {'refs': [ref]}),
                     ('ingest-preview', {'request': request(), 'source_ref': ref})]
            with patch('builtins.open', guarded_open), patch.object(Path, 'open', guarded_path_open), patch.object(Path, 'read_bytes', guarded_read):
                for action, payload in cases:
                    with self.subTest(action=action):
                        status, response = self.post(action, payload)
                        self.assertNotIn('SYNTHETIC FORBIDDEN CONTENT', json.dumps(response))
                        if action in {'hash', 'open', 'shell'}:
                            self.assertEqual(status, 400)
                        elif action == 'adopt-owner':
                            self.assertEqual(status, 403)
                        elif action == 'expand':
                            # 材料包可携带缺口返回，但不能含未登记原文。
                            self.assertTrue(response.get('error') or not response.get('context_text'))
                        else:
                            self.assertGreaterEqual(status, 400)
            self.assertEqual(accesses, [])

    def test_public_impact_question_and_lineage_match_cli_without_writes(self):
        """The final documentation must reach these views through real routes."""
        from test_memory_contracts import examples
        from memory_fixture import snapshot
        original = self.service.commit(request())
        rid = original['record_results'][0]['record_id']
        question = draft()
        question.update(kind='question', payload=examples()['question'])
        question['sources'] = [{'target_kind': 'record', 'target_id': rid, 'revision': 1,
                                'sha256': None, 'relation': 'background', 'locator': ''}]
        question['provenance_gap'] = None
        saved = self.service.commit(request(question, head=original['commit_id']))
        qid = saved['record_results'][0]['record_id']
        before = snapshot(self.root)
        requests = [('impact', {'changed_ids': [rid]}),
                    ('question-validity', {'question_ref': qid}),
                    ('source-lineage', {'target_ids': [rid]})]
        for action, value in requests:
            with self.subTest(action=action):
                status, response = self.post(action, value)
                result, code = self.cli(action, value)
                self.assertEqual((status, code), (200, 0))
                self.assertEqual(response, result)
                if action == 'impact':
                    self.assertIn(qid, [item['canonical_id'] for item in response['affected']])
                elif action == 'question-validity':
                    self.assertEqual(response['status'], 'open')
                else:
                    self.assertEqual(response['source_count'], 0)
                    self.assertIsNone(response['scientific_support_count'])
        # The CLI helper's request file is an input, not a business mutation.
        after = snapshot(self.root)
        for state in (before, after):
            state['files'].pop('request.json', None)
        self.assertEqual(before, after)

    def test_restricted_owner_not_listed_and_cli_http_mutations_rejected_before_snapshot(self):
        from memory import owners
        from memory.store import MemoryStore
        private = self.root / 'research/private/research.json'
        private.parent.mkdir()
        raw = {'research_id': 'RES-HIDDEN', 'title': 'SYNTHETIC SECRET TITLE',
               'sensitivity': 'internal', 'private_note': 'SYNTHETIC SECRET BODY'}
        private.write_text(json.dumps(raw), encoding='utf-8')
        original_request = request(draft('RES-HIDDEN'))
        saved = self.service.commit(original_request)
        raw['sensitivity'] = 'restricted'
        private.write_text(json.dumps(raw), encoding='utf-8')
        hidden = owners.resolve_owner(self.root, 'RES-HIDDEN')
        before = fixture.snapshot_files(self.root)
        status, listed = self.post('list-owners', {})
        command, exit_code = execute(self.root, ['list-owners'])
        self.assertEqual((status, exit_code), (200, 0))
        self.assertEqual(listed, command)
        for secret in ('RES-HIDDEN', 'SYNTHETIC SECRET TITLE', 'SYNTHETIC SECRET BODY', 'research/private'):
            self.assertNotIn(secret, json.dumps(listed))
        self.assertIn('RES-HIDDEN', {owner['owner_id'] for owner in owners.list_owners(self.root)})
        # A denied operation must not read the existing private HEAD or replay
        # an old receipt. The global patch also covers the HTTP-created service.
        with patch.object(MemoryStore, 'read_snapshot', side_effect=AssertionError('private snapshot must not be read')):
            for action, value in (('validate-draft', request(draft('RES-HIDDEN'), head=saved['commit_id'])),
                                  ('commit', request(draft('RES-HIDDEN'), head=saved['commit_id'])),
                                  ('commit', original_request)):
                status, response = self.post(action, value)
                command, exit_code = self.cli(action, value)
                self.assertEqual((status, exit_code), (403, 4))
                self.assertEqual(response['error']['code'], 'ACCESS_DENIED')
                self.assertEqual(command['error']['code'], 'ACCESS_DENIED')
            status, response = self.post('adopt-owner', {'native_ref': hidden['native_ref'],
                'expected_hash': hidden['fingerprint'], 'actor': {'kind': 'ai', 'id': 'synthetic'}})
            command, exit_code = execute(self.root, ['adopt-owner', hidden['native_ref']['path'],
                '--expected-hash', hidden['fingerprint'], '--actor', 'synthetic'])
            self.assertEqual((status, exit_code), (403, 4))
            self.assertEqual(response['error']['code'], command['error']['code'])
        after = fixture.snapshot_files(self.root)
        before.pop('request.json', None); after.pop('request.json', None)
        self.assertEqual(before, after)

    def test_owner_revocation_after_staging_prevents_head_publication(self):
        from memory import owners
        from memory.service import MemoryService
        saved = self.service.commit(request())
        owner = owners.resolve_owner(self.root, 'RES-TEST')
        head = self.root / owner['memory_home'] / 'HEAD.json'
        prior_head = head.read_bytes()
        native = self.root / owner['native_ref']['path']
        def revoke(point):
            if point == 'before_head':
                value = json.loads(native.read_text(encoding='utf-8'))
                value['sensitivity'] = 'restricted'
                native.write_text(json.dumps(value), encoding='utf-8')
        value = draft()
        value['body_markdown'] = 'SYNTHETIC ONLY must remain uncommitted'
        with self.assertRaises(MemoryError) as caught:
            MemoryService(self.root, fault=revoke).commit(request(value, head=saved['commit_id']))
        self.assertEqual(caught.exception.code, 'ACCESS_DENIED')
        self.assertEqual(head.read_bytes(), prior_head)
        snapshot = self.service.store.read_snapshot(owner)
        self.assertEqual(len(snapshot['records']), 1)
        self.assertNotIn(value['body_markdown'], json.dumps(snapshot['records']))


