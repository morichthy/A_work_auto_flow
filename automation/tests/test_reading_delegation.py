"""阅读委派与 notes-only 交接的公开契约测试。

使用独立的真实固定存储 fixture；不继承 ReadingWorkflowTests，避免把原有
阅读流程的整套测试再次执行。这里验证主 agent 永远不会经 handoff 收到正文包。
"""
from copy import copy, deepcopy
from dataclasses import replace
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import uuid
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from material_query_fixture import materialize
from material_query.api import dispatch
from material_query.budget import DEFAULT_BUDGET
from material_query.cli import add_commands, execute
from material_query.contracts import AssociationOptions, DefinitionRef, QueryRequest, Scope
from material_query.coordinator import Coordinator
from material_query.reading import path, read_json, save
from material_query.wire import json_value
from memory.service import MemoryService
from memory import contracts
from test_memory_documents_v3 import unit_payload
import workspace_settings
import evidence_view


class ReadingDelegationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.fixture = materialize(Path(cls.base.name) / '委派 基线', isolation_root=cls.base.name)
        # 为委派测试加入稳定的短正文与技术单元，避免依赖基础 fixture 的通用词。
        draft = {key: deepcopy(cls.fixture.records['A.unit'][key]) for key in
                 (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
        draft.update(title='delegationfixture 技术单元', body_markdown='', payload=unit_payload(),
                     sources=[cls.fixture.source_ref('A')], keywords=['delegationfixture'])
        draft['payload']['blocks'][1]['markdown'] += ' delegationfixture ONLY_DELEGATION_BODY'
        cls.fixture.commit_draft('delegation.unit', draft)
        draft = {key: deepcopy(cls.fixture.records['A.experience'][key]) for key in
                 (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
        draft.update(title='delegationfixture 经验甲', body_markdown='delegationfixture 短正文甲',
                     sources=[cls.fixture.source_ref('A')], keywords=['delegationfixture'])
        cls.fixture.commit_draft('delegation.experience.first', draft)
        draft['title'] = 'delegationfixture 经验乙'
        cls.fixture.commit_draft('delegation.experience.second', draft)

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / '委派副本'
        shutil.copytree(self.fixture.root, self.root)
        self.app = Coordinator(self.root)
        self.sid = 'RS-' + str(uuid.uuid4())
        self.scope = Scope((self.fixture.owner_ids['A'],), None, None, None, None, None, None,
                           False, (), (), None, None)
        budget = replace(DEFAULT_BUDGET, model_calls=6, model_tokens=3072, model_input_tokens=3072,
                         output_chars=40000)
        self.query = QueryRequest(DefinitionRef('full', '1'), 'delegationfixture', (), self.scope, self.scope,
                                  'exploration', AssociationOptions('off', 'existing-relations', '1', 0, 0., None),
                                  budget, 'current', 10, 'reject', (), '')
        started = dispatch(self.app, 'reading-start', {
            'session_id': self.sid, 'goal': '仅向主 agent 交接笔记', 'conditions': ['固定版本'],
            'query': json_value(self.query)})
        self.assertEqual(started['status'], 'ok', started)
        self.revision = 1

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def action(self, name, **raw):
        result = dispatch(self.app, 'reading-' + name, {'session_id': self.sid, **raw})
        value = result.get('value') or {}
        if 'revision' in value:
            self.revision = value['revision']
        return result

    def recall_and_note(self, *, summary='已压缩的阅读理解'):
        recalled = self.action('recall', expected_revision=self.revision, request_id=str(uuid.uuid4()),
                               question='delegationfixture', keywords=[], scope=json_value(self.scope), reason='准备交接')
        self.assertIn(recalled['status'], {'ok', 'partial'}, recalled)
        candidate = next(item for item in recalled['value']['candidates'] if item['source'] == 'overview_experience')
        read = self.action('read', expected_revision=self.revision, request_id=str(uuid.uuid4()),
                           candidate_ids=[candidate['candidate_id']])
        self.assertIn(read['status'], {'ok', 'partial'}, read)
        noted = self.action('note', expected_revision=self.revision, request_id=str(uuid.uuid4()),
                            candidate_id=candidate['candidate_id'], summary=summary,
                            connection={'kind': 'direct', 'explanation': '仅作合成连接', 'chain': ['需后续复核']},
                            details=[], uncertainties=['未作现实验证'])
        self.assertEqual(noted['status'], 'ok', noted)
        self.recalled_candidates = recalled['value']['candidates']
        return candidate

    def note_another_candidate(self, summary):
        """同一召回轮添加第二条笔记，避免在 review 阶段非法重新 recall。"""
        candidate = next(item for item in self.recalled_candidates
                         if item['candidate_id'] not in self.noted_candidate_ids)
        read = self.action('read', expected_revision=self.revision, request_id=str(uuid.uuid4()),
                           candidate_ids=[candidate['candidate_id']])
        self.assertIn(read['status'], {'ok', 'partial'}, read)
        noted = self.action('note', expected_revision=self.revision, request_id=str(uuid.uuid4()),
                            candidate_id=candidate['candidate_id'], summary=summary,
                            connection={'kind': 'direct', 'explanation': '第二条合成连接', 'chain': []},
                            details=[], uncertainties=[])
        self.assertEqual(noted['status'], 'ok', noted)
        self.noted_candidate_ids.add(candidate['candidate_id'])

    def set_subagents(self, value):
        current = workspace_settings.read(self.root)
        settings = deepcopy(current['settings'])
        settings['collaboration']['subagents'] = value
        workspace_settings.update(self.root, {'expected_revision': current['revision'], 'settings': settings})

    def test_public_dispatch_and_cli_expose_delegate_and_handoff(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest='command', required=True)
        add_commands(sub)
        for action in ('reading-delegate', 'reading-handoff'):
            parsed = parser.parse_args(['material-query', action, '--request', 'request.json'])
            self.assertEqual(parsed.action, action)
        request = self.root / 'delegate.json'
        request.write_text(json.dumps({'session_id': self.sid, 'host_supports_subagents': False}), encoding='utf-8')
        value, code = execute(self.root, argparse.Namespace(action='reading-delegate', owner=None, session=None,
                             markdown=False, request=request, assemble=False, expand=None, documents=None))
        self.assertEqual(code, 0, value)
        result = self.action('delegate', host_supports_subagents=False)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['value']['route'], 'single-agent')

    def test_delegate_falls_back_without_host_or_when_workspace_policy_is_off(self):
        host_off = self.action('delegate', host_supports_subagents=False)
        self.assertEqual(host_off['value']['route'], 'single-agent')
        self.assertFalse(host_off['value']['dispatched'])
        self.assertNotIn('packet', json.dumps(host_off['value'], ensure_ascii=False))
        self.set_subagents('off')
        policy_off = self.action('delegate', host_supports_subagents=True)
        self.assertEqual(policy_off['value']['route'], 'single-agent')
        self.assertFalse(policy_off['value']['dispatched'])

    def test_custom_model_requirements_reach_host_and_worker_without_overriding_route_or_scope(self):
        current = workspace_settings.read(self.root)
        settings = deepcopy(current['settings'])
        custom = '  高能力模型和高推理，处理复杂推导；仅使用本RS已授权材料。  '
        settings['collaboration']['subagent_requirements'] = custom
        workspace_settings.update(self.root, {'expected_revision': current['revision'], 'settings': settings})
        for enabled in (True, False):
            if not enabled:
                self.set_subagents('off')
            result = self.action('delegate', host_supports_subagents=True)
            self.assertEqual(result['status'], 'ok', result)
            value = result['value']
            self.assertEqual(value['route'], 'subagent' if enabled else 'single-agent')
            self.assertFalse(value['dispatched'])
            self.assertEqual(value['model_preference']['requirements'], custom)
            self.assertEqual(value['model_preference']['selection'], 'host_decides')
            self.assertNotIn('cost', value['model_preference'])
            self.assertNotIn('reasoning', value['model_preference'])
            self.assertEqual(value['worker_brief']['model_requirements'], custom)
            self.assertEqual(value['worker_brief']['query']['scope'], json_value(self.scope))
            self.assertEqual(value['worker_brief']['query']['budget'], json_value(self.query.budget))

    def test_delegate_is_read_only_and_brief_never_contains_material_or_diagnostics(self):
        before = read_json(path(self.root, self.sid, 'HEAD.json'))
        result = self.action('delegate', host_supports_subagents=True, expected_revision=self.revision)
        self.assertEqual(result['status'], 'ok', result)
        value = result['value']
        self.assertEqual(value['route'], 'subagent')
        self.assertFalse(value['dispatched'], 'API only returns a host-consumable worker brief')
        self.assertEqual(value['revision'], before['revision'])
        encoded = json.dumps(value, ensure_ascii=False)
        for forbidden in ('packet', 'coverage', 'body_markdown', 'query_sources', 'ranking'):
            self.assertNotIn(forbidden, encoded)
        after = read_json(path(self.root, self.sid, 'HEAD.json'))
        self.assertEqual(after['revision'], before['revision'])
        self.assertGreaterEqual(after['consumed']['read_bytes'], before['consumed']['read_bytes'])

    def test_handoff_is_bounded_notes_only_and_omits_whole_notes(self):
        first = self.recall_and_note(summary='甲' * 400)
        self.noted_candidate_ids = {first['candidate_id']}
        self.note_another_candidate('乙' * 400)
        result = self.action('handoff', expected_revision=self.revision, max_chars=512)
        self.assertIn(result['status'], {'ok', 'partial'}, result)
        value = result['value']
        self.assertLessEqual(len(json.dumps(value, ensure_ascii=False)), 512)
        self.assertEqual(set(value) - {'session_id', 'revision', 'context_markdown', 'complete', 'phase', 'gaps',
                                       'notes_count', 'omitted_note_count', 'unnoted_candidate_count',
                                       'needs_user_input','goal','conditions','latest_decision'}, set())
        self.assertNotIn('ONLY_FULL_RESULT', value['context_markdown'])
        self.assertNotIn('coverage', json.dumps(value, ensure_ascii=False))
        self.assertGreaterEqual(value['omitted_note_count'], 1)
        self.assertNotIn('甲' * 300, value['context_markdown'])

    def test_handoff_reports_unnoted_partial_and_ask_user_never_complete(self):
        self.recall_and_note()
        # review 不是终止阶段；未读候选数需透明显示，但不单独决定 complete。
        handoff = self.action('handoff', expected_revision=self.revision)
        self.assertFalse(handoff['value']['complete'])
        self.assertGreater(handoff['value']['unnoted_candidate_count'], 0)
        decided = self.action('decide', expected_revision=self.revision, request_id=str(uuid.uuid4()),
                              direction='ask_user', reason='需要取舍', next_step='等待用户', outcome='', human_decision='')
        self.assertEqual(decided['status'], 'ok', decided)
        waiting = self.action('handoff', expected_revision=self.revision)
        self.assertFalse(waiting['value']['complete'])
        self.assertEqual(waiting['value']['phase'], 'ask_user')

    def test_handoff_conflict_revocation_stale_and_old_budget_are_not_hidden(self):
        self.recall_and_note()
        stale = self.action('handoff', expected_revision=1)
        self.assertEqual(stale['code'], 'CONFLICT')
        before = read_json(path(self.root, self.sid, 'HEAD.json'))
        self.app.close(); self.app = Coordinator(self.root)
        resumed = self.action('handoff', expected_revision=self.revision)
        after = read_json(path(self.root, self.sid, 'HEAD.json'))
        self.assertGreaterEqual(after['consumed']['read_bytes'], before['consumed']['read_bytes'])
        self.assertEqual(after['query']['budget'], before['query']['budget'])
        self.assertIn(resumed['status'], {'ok', 'partial'}, resumed)
        catalog = self.root / 'retrieval/sources.json'
        raw = json.loads(catalog.read_text(encoding='utf-8'))
        for source in raw['sources']:
            source['enabled'] = False
        catalog.write_text(json.dumps(raw), encoding='utf-8')
        denied = self.action('handoff', expected_revision=self.revision)
        self.assertEqual(denied['code'], 'DENIED')
        self.assertIsNone(denied['value'])

    def test_stale_fixed_revision_returns_partial_without_old_note_text(self):
        self.recall_and_note(summary='不可交给主 agent 的旧笔记')
        # 采用真实 Owner 提交新修订，而非改写 RS 文件伪造 stale 标记。
        fx = copy(self.fixture)
        fx.root, fx.service = self.root, MemoryService(self.root)
        fx.records, fx.refs, fx.record_ids = deepcopy(self.fixture.records), deepcopy(self.fixture.refs), dict(self.fixture.record_ids)
        fx.clock = deepcopy(self.fixture.clock)
        fx.revise('delegation.updated', 'delegation.experience.first', title='新修订经验')
        result = self.action('handoff', expected_revision=self.revision)
        self.assertEqual(result['status'], 'partial', result)
        self.assertFalse(result['value']['complete'])
        self.assertNotIn('不可交给主 agent 的旧笔记', result['value']['context_markdown'])

    def test_delegate_and_handoff_reject_strict_types_unknown_candidates_and_budget_leakage(self):
        self.assertEqual(self.action('delegate', host_supports_subagents=1)['code'], 'VALIDATION')
        self.assertEqual(self.action('handoff', max_chars=True)['code'], 'VALIDATION')
        self.assertEqual(self.action('handoff', candidate_ids=['RC-invented'])['code'], 'VALIDATION')
        self.recall_and_note(summary='预算不足时不得泄漏的笔记')
        head = path(self.root, self.sid, 'HEAD.json')
        session = read_json(head)
        # 模拟已耗尽旧RS输出额度；只改合成fixture，验证失败回执绝不携带笔记。
        session['query']['budget']['output_chars'] = session['consumed']['output_chars']
        save(head, session)
        exhausted = self.action('handoff', expected_revision=self.revision)
        self.assertEqual(exhausted['code'], 'BUDGET')
        self.assertIsNone(exhausted['value'])
        self.assertNotIn('预算不足时不得泄漏的笔记', json.dumps(exhausted, ensure_ascii=False))

    def test_real_http_routes_delegate_and_handoff_through_materials_dispatch(self):
        service = SimpleNamespace(root=self.root, materials=self.app)
        server, url = evidence_view.create_server(self.root, controller=SimpleNamespace(app=service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def post(action, payload):
            parsed = urlsplit(url)
            request = Request(url + 'api/v1/materials/' + action, json.dumps(payload).encode(), {
                'Content-Type': 'application/json', 'Origin': f'{parsed.scheme}://{parsed.netloc}'})
            try:
                response = urlopen(request, timeout=5)
            except HTTPError as exc:
                response = exc
            with response:
                return response.status, json.loads(response.read())
        try:
            status, delegated = post('reading-delegate', {'session_id': self.sid, 'host_supports_subagents': False})
            self.assertEqual(status, 200, delegated)
            self.assertEqual(delegated['value']['route'], 'single-agent')
            status, handoff = post('reading-handoff', {'session_id': self.sid, 'max_chars': 512})
            self.assertEqual(status, 200, handoff)
            self.assertNotIn('coverage', json.dumps(handoff, ensure_ascii=False))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
