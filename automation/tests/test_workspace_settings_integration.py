"""公开设置入口、默认值消费和旧RS预算边界；只使用隔离空工作区。"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evidence_view
import workspace_settings
import workspace_settings_cli
from material_query.api import dispatch
from material_query.coordinator import Coordinator
from material_query.reading import path


class SettingsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = Coordinator(self.root)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def save(self, **reading):
        current = workspace_settings.read(self.root)
        changed = deepcopy(current['settings'])
        changed['collaboration']['subagents'] = 'off'
        changed['collaboration']['subagent_requirements'] = '使用较高能力模型，允许中等推理；不得扩大读取授权。'
        changed['materials']['result_limit'] = 7
        changed['materials']['budget']['output_chars'] = 4000
        changed['reading'].update(reading)
        return workspace_settings.update(self.root, {'expected_revision': current['revision'], 'settings': changed})

    def test_capabilities_and_new_template_consume_settings_but_saved_rs_is_fixed(self):
        saved = self.save(result_limit=6)
        caps = dispatch(self.app, 'capabilities', {})
        self.assertEqual(caps['default_result_limit'], 7)
        self.assertEqual(caps['default_budget']['output_chars'], 4000)
        self.assertEqual(caps['workspace_policy'], saved['settings']['collaboration'])
        template = dispatch(self.app, 'reading-template', {})['value']
        self.assertEqual(template['query']['result_limit'], 6)
        template['mode'] = 'legacy'
        # An explicit request is stronger than the template; settings do not
        # replace it again on start, and later edits cannot enlarge its ledger.
        template['query']['result_limit'] = 3
        template['query']['budget']['output_chars'] = 5000
        template['reranking']['mode'] = 'off'
        result = dispatch(self.app, 'reading-start', template)
        self.assertEqual(result['status'], 'ok', result)
        sid = template['session_id']
        before = json.loads(path(self.root, sid, 'HEAD.json').read_text(encoding='utf-8'))
        self.save(result_limit=12)
        updated = dispatch(self.app, 'reading-template', {})['value']
        self.assertEqual(updated['query']['result_limit'], 12)
        resumed = dispatch(self.app, 'reading-resume', {'session_id': sid, 'expected_revision': 1,
                                                     'request_id': str(uuid.uuid4())})
        self.assertEqual(resumed['status'], 'ok', resumed)
        after = json.loads(path(self.root, sid, 'HEAD.json').read_text(encoding='utf-8'))
        self.assertEqual(after['query'], before['query'])
        self.assertEqual(after['reranking'], before['reranking'])
        self.assertEqual(after['query']['budget']['output_chars'], 5000)
        self.assertEqual(after['query']['result_limit'], 3)
        self.assertEqual(saved['settings']['reading']['result_limit'], 6)

    def test_owner_template_uses_context_defaults_and_existing_session_keeps_snapshot(self):
        context = {'max_owners': 4, 'note_max_tokens': 8192}
        self.save(context=context)
        template = dispatch(self.app, 'reading-template', {})['value']
        self.assertEqual(template['mode'], 'owner_document')
        self.assertEqual(template['context'], context)
        started = dispatch(self.app, 'reading-start', template)
        self.assertEqual(started['status'], 'ok', started)
        self.save(context={'max_owners': 9, 'note_max_tokens': 12000})
        head = json.loads(path(self.root, template['session_id'], 'HEAD.json').read_text(encoding='utf-8'))
        self.assertEqual(head['context'], context)
        self.assertEqual(dispatch(self.app, 'reading-template', {})['value']['context'],
                         {'max_owners': 9, 'note_max_tokens': 12000})

    def test_public_cli_policy_set_and_stale_revision(self):
        self.save(result_limit=6)
        policy, code = workspace_settings_cli.execute(self.root, SimpleNamespace(settings_action='policy'))
        self.assertEqual(code, 0)
        self.assertEqual(policy['subagents'], 'off')
        self.assertEqual(policy['subagent_requirements'],
                         workspace_settings.read(self.root)['settings']['collaboration']['subagent_requirements'])
        self.assertEqual(policy['fallback'], 'single-agent')
        shown, code = workspace_settings_cli.execute(self.root, SimpleNamespace(settings_action='show'))
        request = self.root / 'request.json'
        shown['settings']['materials']['result_limit'] = 8
        request.write_text(json.dumps({'expected_revision': shown['revision'], 'settings': shown['settings']}), encoding='utf-8')
        args = SimpleNamespace(settings_action='set', request=request)
        value, code = workspace_settings_cli.execute(self.root, args)
        self.assertEqual(code, 0, value)
        self.assertEqual(value['settings']['materials']['result_limit'], 8)
        stale, code = workspace_settings_cli.execute(self.root, args)
        self.assertEqual(code, 5)
        self.assertEqual(stale['error']['code'], 'VERSION_CONFLICT')

    def test_real_http_get_save_conflict_and_origin_rejection(self):
        # The real token-prefixed loopback handler provides the write boundary;
        # a small controller avoids material indexing unrelated to this API.
        service = SimpleNamespace(root=self.root)
        server, url = evidence_view.create_server(self.root, controller=SimpleNamespace(app=service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def post(data, origin=None):
            parsed = urlsplit(url)
            request = Request(url + 'api/v1/settings', json.dumps(data).encode(),
                              {'Content-Type': 'application/json', 'Origin': origin or f'{parsed.scheme}://{parsed.netloc}'})
            try:
                response = urlopen(request, timeout=5)
            except HTTPError as exc:
                response = exc
            with response:
                return response.status, json.loads(response.read())
        try:
            with urlopen(url + 'api/v1/settings', timeout=5) as response:
                initial = json.loads(response.read())
            settings = deepcopy(initial['settings'])
            settings['collaboration']['subagents'] = 'off'
            payload = {'expected_revision': initial['revision'], 'settings': settings}
            status, saved = post(payload)
            self.assertEqual(status, 200, saved)
            self.assertEqual(workspace_settings.read(self.root)['settings'], settings)
            status, failed = post(payload)
            self.assertEqual(status, 409, failed)
            self.assertEqual(failed['error']['code'], 'VERSION_CONFLICT')
            status, _ = post({'expected_revision': saved['revision'], 'settings': settings}, 'https://invalid.example')
            self.assertEqual(status, 403)
            self.assertEqual(workspace_settings.read(self.root)['revision'], saved['revision'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
