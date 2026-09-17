"""通过实际 MQ/固定存储测试阅读流程；只将缺失模型作为显式降级。

测试笔记是合成输入，不声称真实 AI 理解或业务质量通过。
"""
from copy import copy, deepcopy
from dataclasses import replace
from pathlib import Path
import json
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch

from material_query_fixture import materialize
from test_memory_documents_v3 import unit_payload
from memory import contracts
from memory.service import MemoryService
from material_query.api import dispatch
from material_query.budget import DEFAULT_BUDGET
from material_query.contracts import AssociationOptions, DefinitionRef, QueryRequest, Scope
from material_query.coordinator import Coordinator
from material_query.wire import json_value


class ReadingWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.fx = materialize(Path(cls.base.name) / '阅读 模板', isolation_root=cls.base.name)
        draft = {key: deepcopy(cls.fx.records['A.unit'][key]) for key in
                 (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
        draft.update(title='合成阅读单位', body_markdown='', payload=unit_payload(),
                     sources=[cls.fx.source_ref('A')], keywords=['readingfixture'])
        draft['payload']['blocks'][1]['markdown'] += ' readingfixture'
        cls.fx.commit_draft('reading.unit', draft)
        # Use a real legacy experience too, to verify its whole payload is kept.
        draft = {key: deepcopy(cls.fx.records['A.experience'][key]) for key in
                 (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
        draft.update(title='readingfixture 经验', body_markdown='完整短正文结尾 KEEP_SHORT_END',
                     keywords=['readingfixture'], sources=[cls.fx.source_ref('A')])
        cls.fx.commit_draft('reading.experience', draft)
        draft['title'] = 'readingfixture 另一条经验'
        cls.fx.commit_draft('reading.experience.second', draft)

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / '阅读副本'
        shutil.copytree(self.fx.root, self.root)
        self.app = Coordinator(self.root)
        self.sid = 'RS-' + str(uuid.uuid4())
        self.scope = Scope((self.fx.owner_ids['A'],), None, None, None, None, None, None, False, (), (), None, None)
        # No model in this synthetic fixture: dense must report degradation,
        # while actual FTS and fixed record assembly still execute.
        budget = replace(DEFAULT_BUDGET, model_calls=6, model_tokens=3072, model_input_tokens=3072)
        self.query = QueryRequest(DefinitionRef('full', '1'), 'readingfixture', (), self.scope, self.scope,
            'exploration', AssociationOptions('off', 'existing-relations', '1', 2, .15, None),
            budget, 'current', 10, 'skip', (), '')
        result = dispatch(self.app, 'reading-start', {'session_id': self.sid, 'goal': '合成目标',
            'conditions': ['保留单位与条件'], 'query': json_value(self.query)})
        self.assertEqual(result['status'], 'ok', result)
        self.revision = 1

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def call(self, action, **kwargs):
        request = dict(session_id=self.sid, expected_revision=self.revision, request_id=str(uuid.uuid4()), **kwargs)
        result = dispatch(self.app, 'reading-' + action, request)
        if result.get('value', {}) and 'revision' in result['value']:
            self.revision = result['value']['revision']
        return result

    def recall(self):
        result = self.call('recall', question='readingfixture', keywords=[], scope=json_value(self.scope), reason='初次多路')
        self.assertIn(result['status'], {'ok', 'partial'}, result)
        return result

    def unit(self, result):
        return next(item for item in result['value']['candidates'] if item['ref']['id'] == self.fx.record_ids['reading.unit'])

    def note(self, key):
        return self.call('note', candidate_id=key, summary='合成理解：温标换算需固定单位',
            connection={'kind': 'inspiration', 'explanation': '借鉴先定义变量的方法', 'chain': ['迁移适用性仍待验证']},
            details=[{'text': '$T=t+273.15$', 'reason': '保留精确常数', 'block_ids': ['result']}], uncertainties=['不是现实测量验证'])

    def test_independent_lanes_short_full_and_technical_required_blocks(self):
        result = self.recall()
        self.assertEqual([lane['source'] for lane in result['value']['coverage']['lanes']],
                         ['overview_experience', 'process', 'technical'])
        unit = self.unit(result)
        body = json.dumps(unit['packet'], ensure_ascii=False)
        self.assertIn('ONLY_FULL_RESULT', body)
        self.assertIn('ONLY_DEFINITION', body)
        self.assertNotIn('OPTIONAL_BLOCK', body)
        short = next(item for item in result['value']['candidates'] if item['source'] == 'overview_experience')
        self.assertIn('KEEP_SHORT_END', json.dumps(short['packet']))
        self.assertTrue(Path(unit['link']).is_file())
        self.assertTrue(result['value']['gaps'], 'Missing model is not silently declared available')

    def test_full_read_then_note_and_cross_process_resume(self):
        unit = self.unit(self.recall())
        self.assertEqual(self.note(unit['candidate_id'])['code'], 'VALIDATION')
        full = self.call('read', candidate_ids=[unit['candidate_id']])
        self.assertIn('OPTIONAL_BLOCK', json.dumps(full))
        self.assertEqual(self.note(unit['candidate_id'])['status'], 'ok')
        self.app.close()
        self.app = Coordinator(self.root)
        restored = self.call('resume')
        self.assertEqual(restored['status'], 'ok', restored)
        self.assertIn('273.15', restored['value']['context_markdown'])
        self.assertIn('合成目标', restored['value']['context_markdown'])
        self.assertGreater(restored['consumed']['read_bytes'], full['consumed']['read_bytes'])

    def test_shared_definition_is_delivered_once_across_multiple_hits(self):
        result = self.call('recall', question='ONLY_FULL_RESULT ONLY_DEFINITION', keywords=[],
                           scope=json_value(self.scope), reason='多个正文命中共享定义')
        unit = self.unit(result)
        definitions = [part for part in unit['packet']['parts'] if part['selectors'] == ['detail.blocks.definitions']]
        self.assertEqual(len(definitions), 1, unit)

    def test_expansion_is_judgment_based_and_explicit_question_is_preserved(self):
        self.recall()
        decided = self.call('decide', direction='proceed', reason='可以检验', next_step='运行合成计算', outcome='', human_decision='')
        self.assertEqual(decided['value']['direction'], 'proceed')
        blocked = self.call('recall', question='readingfixture', keywords=[], scope=json_value(self.scope), reason='重复')
        self.assertEqual(blocked['code'], 'VALIDATION')
        first = self.call('decide', direction='expand', reason='失败后补查', next_step='查边界', outcome='计算未解答问题', human_decision='')
        self.assertFalse(first['value']['needs_user_input'])
        self.recall()
        second = self.call('decide', direction='expand', reason='仍缺条件', next_step='扩大主题', outcome='缺少边界定义', human_decision='')
        self.assertFalse(second['value']['needs_user_input'])
        asked = self.call('decide', direction='ask_user', reason='方向需要用户取舍', next_step='等待方向', outcome='有两个方向', human_decision='')
        self.assertTrue(asked['value']['needs_user_input'])
        blocked = self.call('decide', direction='expand', reason='擅自推进', next_step='扩大主题', outcome='缺定义', human_decision='')
        self.assertEqual(blocked['code'], 'VALIDATION')
        continued = self.call('decide', direction='expand', reason='用户选定方向', next_step='扩大主题', outcome='缺定义', human_decision='合成用户：继续边界方向')
        self.assertEqual(continued['value']['direction'], 'expand')

    def test_owner_binding_listing_and_latest_view_survive_restart(self):
        self.call('bind', owner_id=self.fx.owner_ids['A'], checkpoint_ref=None)
        unit = self.unit(self.recall())
        self.call('read', candidate_ids=[unit['candidate_id']])
        self.note(unit['candidate_id'])
        self.app.close()
        self.app = Coordinator(self.root)
        listed = dispatch(self.app, 'reading-list', {'owner_id': self.fx.owner_ids['A']})
        self.assertEqual([x['session_id'] for x in listed['value']['items']], [self.sid])
        viewed = dispatch(self.app, 'reading-view', {'session_id': self.sid})
        self.assertEqual(viewed['value']['revision'], self.revision)
        self.assertIn('273.15', viewed['value']['context_markdown'])
        self.assertTrue(viewed['value']['candidates'])
        other = dispatch(self.app, 'reading-list', {'owner_id': self.fx.owner_ids['B']})
        self.assertEqual(other['value']['items'], [])

    def test_archive_preserves_files_blocks_work_and_can_restore(self):
        self.call('archive', archived=True, reason='合成归档')
        files = list((self.root / '.local/reading-sessions' / self.sid).glob('revision-*.json'))
        self.assertTrue(files)
        self.assertEqual(dispatch(self.app, 'reading-list', {})['value']['items'], [])
        self.assertEqual(len(dispatch(self.app, 'reading-list', {'include_archived': True})['value']['items']), 1)
        self.assertEqual(self.call('recall', question='x', keywords=[], scope=json_value(self.scope), reason='归档后') ['code'], 'VALIDATION')
        self.assertEqual(dispatch(self.app, 'reading-view', {'session_id': self.sid})['status'], 'ok')
        self.call('archive', archived=False, reason='恢复合成工作')
        self.recall()
        self.assertTrue(all(p.exists() for p in files))

    def test_filtered_catalog_pages_and_content_order_ignore_uuid_and_view_time(self):
        from material_query.reading import read_json, save
        original = read_json(self.root / '.local/reading-sessions' / self.sid / 'HEAD.json')
        # 前20个UUID均属于另一Owner；目标必须在筛选后的第一页出现。
        for number in range(25):
            session = deepcopy(original)
            session.update(session_id='RS-' + str(uuid.UUID(int=number + 1)),
                           owner_id=self.fx.owner_ids['B'], updated_at='2026-01-01T00:00:00+00:00')
            file = self.root / '.local/reading-sessions' / session['session_id'] / 'HEAD.json'
            file.parent.mkdir(parents=True)
            save(file, session)
        self.call('bind', owner_id=self.fx.owner_ids['A'], checkpoint_ref=None)
        listed = dispatch(self.app, 'reading-list', {'owner_id': self.fx.owner_ids['A'], 'limit': 1})['value']
        self.assertEqual([item['session_id'] for item in listed['items']], [self.sid])
        self.assertIsNone(listed['next_offset'])
        updated = listed['items'][0]['updated_at']
        dispatch(self.app, 'reading-view', {'session_id': self.sid, 'notes_only': True})
        listed = dispatch(self.app, 'reading-list', {'owner_id': self.fx.owner_ids['A']})['value']
        self.assertEqual(listed['items'][0]['updated_at'], updated)
        self.assertEqual(listed['items'][0]['note_count'], 0)

    def test_superset_access_keeps_original_ceiling_and_rejects_narrower_host(self):
        from material_query.reading import Reading, read_json, save
        from material_query.budget import Ledger
        file = self.root / '.local/reading-sessions' / self.sid / 'HEAD.json'
        session = read_json(file)
        session['access'] = [self.fx.owner_ids['A']]
        save(file, session)
        reading = Reading(self.app)
        reading.ledger = Ledger(DEFAULT_BUDGET)
        state = reading.state(session)
        self.assertEqual(state.request.scope_ceiling.owner_ids, (self.fx.owner_ids['A'],))
        view = dispatch(self.app, 'reading-view', {'session_id': self.sid, 'notes_only': True})
        self.assertEqual(view['status'], 'partial', view)
        self.assertEqual(read_json(file)['access'], session['access'])
        self.assertEqual(read_json(file)['revision'], session['revision'])
        narrow = Coordinator(self.root, access_owner_ids=[self.fx.owner_ids['B']])
        try:
            self.assertEqual(dispatch(narrow, 'reading-view', {'session_id': self.sid, 'notes_only': True})['code'], 'DENIED')
            self.assertEqual(dispatch(narrow, 'reading-list', {})['value']['items'], [])
        finally:
            narrow.close()

    def test_notes_view_snapshot_and_failed_derived_write_preserve_canonical_note(self):
        unit = self.unit(self.recall())
        self.call('read', candidate_ids=[unit['candidate_id']])
        with patch('material_query.reading_snapshot.write_snapshot', side_effect=OSError('synthetic disk failure')):
            noted = self.note(unit['candidate_id'])
        self.assertEqual(noted['status'], 'ok', noted)
        self.assertTrue(any('Markdown' in warning for warning in noted['warnings']))
        viewed = dispatch(self.app, 'reading-view', {'session_id': self.sid, 'notes_only': True})
        self.assertIn(viewed['status'], {'ok', 'partial'}, viewed)
        value = viewed['value']
        self.assertEqual(value['notes_count'], 1)
        self.assertEqual([row['ref'] for row in value['candidates']], [unit['ref']])
        self.assertNotIn('coverage', value)
        self.assertNotIn('ONLY_FULL_RESULT', json.dumps(value))
        snapshot = self.root / 'context/reading-notes' / self.sid / 'current.md'
        body = snapshot.read_text(encoding='utf-8')
        self.assertIn('273.15', body)
        self.assertIn('不是权威状态', body)
        self.assertIn(f'版本 r{self.revision}', body)
        # 新建但尚未记录理解的会话即使更“新”，也不能遮住实际note。
        empty = dispatch(self.app, 'reading-start', {'session_id': 'RS-' + str(uuid.uuid4()),
            'goal': '尚无笔记的新会话', 'conditions': [], 'query': json_value(self.query)})
        self.assertEqual(empty['status'], 'ok', empty)
        listed = dispatch(self.app, 'reading-list', {'limit': 1})['value']
        self.assertEqual(listed['items'][0]['session_id'], self.sid)
        self.assertEqual(listed['items'][0]['note_count'], 1)
        self.assertEqual(listed['next_offset'], 1)
        before = snapshot.read_bytes()
        sources = self.root / 'retrieval/sources.json'
        raw = json.loads(sources.read_text(encoding='utf-8'))
        for source in raw['sources']:
            source['enabled'] = False
        sources.write_text(json.dumps(raw), encoding='utf-8')
        self.assertIsNone(dispatch(self.app, 'reading-view', {'session_id': self.sid, 'notes_only': True})['value'])
        self.assertEqual(snapshot.read_bytes(), before)

    def test_listing_and_view_hide_revoked_sources(self):
        self.recall()
        file = self.root / 'retrieval/sources.json'
        raw = json.loads(file.read_text(encoding='utf-8'))
        for source in raw['sources']:
            source['enabled'] = False
        file.write_text(json.dumps(raw), encoding='utf-8')
        listed = dispatch(self.app, 'reading-list', {})
        self.assertEqual(listed['value']['items'], [])
        self.assertNotIn('合成目标', json.dumps(listed, ensure_ascii=False))
        viewed = dispatch(self.app, 'reading-view', {'session_id': self.sid})
        self.assertIsNone(viewed['value'])

    def test_binding_requires_real_owner_and_correct_checkpoint(self):
        self.assertEqual(self.call('bind', owner_id='RES-NOT-FOUND', checkpoint_ref=None)['code'], 'DENIED')
        wrong = self.fx.ref('A.unit.r1')
        self.assertNotEqual(self.call('bind', owner_id=self.fx.owner_ids['A'], checkpoint_ref=json_value(wrong))['status'], 'ok')

    def test_fixed_checkpoint_binding_and_view_budget_do_not_rewrite_history(self):
        from material_query_fixture import _draft
        from material_query.legacy_adapter import fixed_record
        fx = copy(self.fx)
        fx.root, fx.service = self.root, MemoryService(self.root)
        fx.records, fx.refs, fx.record_ids = deepcopy(self.fx.records), deepcopy(self.fx.refs), dict(self.fx.record_ids)
        fx.clock = deepcopy(self.fx.clock)
        goal = _draft(fx, 'A', 'goal', '合成交接', {
            'objective': '继续核对方法', 'constraints': [], 'success_criteria': ['固定依据可读'],
            'previous_goal_ref': None, 'change_impact': '合成初始目标'})
        fx.commit_draft('binding.goal', goal)
        checkpoint = _draft(fx, 'A', 'checkpoint', '阅读交接', {
            'goal_ref': fx.ref('binding.goal'), 'route_refs': [], 'completed_refs': [], 'question_refs': [],
            'next_step': '阅读固定方法', 'prerequisites': [], 'stop_reason': '交接',
            'budget_remaining': {'value': None, 'reason': 'not_acquired', 'note': '未知'}})
        record = fx.commit_draft('binding.checkpoint', checkpoint)
        fixed = json_value(fixed_record(record))
        result = self.call('bind', owner_id=fx.owner_ids['A'], checkpoint_ref=fixed)
        self.assertEqual(result['status'], 'ok', result)
        home = self.root / '.local/reading-sessions' / self.sid
        history = {p.name: p.read_bytes() for p in home.glob('revision-*.json')}
        first = dispatch(self.app, 'reading-view', {'session_id': self.sid})
        second = dispatch(self.app, 'reading-view', {'session_id': self.sid})
        self.assertEqual(first['value']['checkpoint_ref'], fixed)
        self.assertEqual(second['value']['revision'], self.revision)
        self.assertGreater(second['consumed']['read_bytes'], first['consumed']['read_bytes'])
        self.assertEqual(history, {p.name: p.read_bytes() for p in home.glob('revision-*.json')})
        self.assertEqual(dispatch(self.app, 'reading-list', {'owner_id': 123})['code'], 'VALIDATION')

    def test_paging_keeps_scope_and_delivers_unread_short_records(self):
        self.sid = 'RS-' + str(uuid.uuid4())
        result = dispatch(self.app, 'reading-start', {'session_id': self.sid, 'goal': '分批阅读', 'conditions': [],
            'query': json_value(replace(self.query, result_limit=1))})
        self.assertEqual(result['status'], 'ok')
        first = self.recall()
        page = self.call('page')
        self.assertIn(page['status'], {'ok', 'partial'}, page)
        seen = {item['ref']['id'] for item in first['value']['candidates']}
        next_ids = {item['ref']['id'] for item in page['value']['candidates']}
        self.assertTrue(next_ids)
        self.assertFalse(seen & next_ids)
        self.assertEqual(page['value']['coverage']['scope']['exclude_ids'], [])
        self.assertGreater(page['consumed']['candidates'], first['consumed']['candidates'])

    def test_budget_consumption_persists_after_exhaustion_and_restart(self):
        self.sid = 'RS-' + str(uuid.uuid4())
        result = dispatch(self.app, 'reading-start', {'session_id': self.sid, 'goal': '预算用尽', 'conditions': [],
            'query': json_value(replace(self.query, budget=replace(self.query.budget, output_chars=15)))})
        self.assertEqual(result['status'], 'ok')
        rejected = self.call('resume')
        self.assertEqual(rejected['code'], 'BUDGET')
        self.app.close()
        self.app = Coordinator(self.root)
        again = self.call('resume')
        self.assertEqual(again['code'], 'BUDGET')
        self.assertGreater(again['consumed']['read_bytes'], rejected['consumed']['read_bytes'])

    def test_replay_conflict_and_unrecognized_candidate(self):
        request = dict(session_id=self.sid, expected_revision=1, request_id=str(uuid.uuid4()))
        first = dispatch(self.app, 'reading-resume', request)
        replay = dispatch(self.app, 'reading-resume', request)
        self.assertEqual(first['value']['revision'], replay['value']['revision'])
        self.assertTrue(replay['value']['replayed'])
        conflict = self.call('resume')
        self.assertEqual(conflict['code'], 'CONFLICT')
        self.revision = first['value']['revision']
        self.assertEqual(self.call('read', candidate_ids=['invented'])['code'], 'VALIDATION')

    def test_source_revocation_blocks_saved_notes_and_retry(self):
        unit = self.unit(self.recall())
        self.call('read', candidate_ids=[unit['candidate_id']])
        self.note(unit['candidate_id'])
        file = self.root / 'retrieval/sources.json'
        catalog = json.loads(file.read_text(encoding='utf-8'))
        for item in catalog['sources']:
            item['enabled'] = False
        file.write_text(json.dumps(catalog), encoding='utf-8')
        result = self.call('resume')
        self.assertNotEqual(result['status'], 'ok')
        self.assertNotIn('273.15', json.dumps(result))

    def test_new_revision_marks_old_understanding_stale_without_rewriting_it(self):
        unit = self.unit(self.recall())
        self.call('read', candidate_ids=[unit['candidate_id']])
        self.note(unit['candidate_id'])
        fx = copy(self.fx)
        fx.root, fx.service = self.root, MemoryService(self.root)
        fx.records, fx.refs, fx.record_ids = deepcopy(self.fx.records), deepcopy(self.fx.refs), dict(self.fx.record_ids)
        fx.clock = deepcopy(self.fx.clock)
        fx.revise('reading.updated', 'reading.unit', title='新版合成阅读单位')
        restored = self.call('resume')
        self.assertEqual(restored['status'], 'partial', restored)
        self.assertIn('旧版阅读理解', restored['value']['context_markdown'])
        self.assertEqual(self.note(unit['candidate_id'])['code'], 'VALIDATION')

    def test_scope_ceiling_and_access_identity_survive_restart(self):
        self.app.close()
        self.app = Coordinator(self.root, access_owner_ids=[])
        result = self.call('resume')
        self.assertEqual(result['code'], 'DENIED')
        self.assertNotIn('合成目标', json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
