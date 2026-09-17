import unittest
import material_query_fixture
from material_query import reading_strategy as strategy
from material_query.validation import QueryError

class StrategyTests(unittest.TestCase):
    def test_old_session_is_standard_disabled(self):
        self.assertEqual(strategy.configuration({}), {'strategy':'standard','association':{'enabled':False,'max_rounds':3},'association_text':''})
    def test_configure_preserves_state_and_rejects_legacy(self):
        s={'mode':'owner_document','rounds':[1],'query':{'scope':'fixed'}}
        strategy.configure(s, {'strategy':'quick','association_text':'方向'})
        self.assertEqual(s['rounds'],[1]); self.assertEqual(s['query'],{'scope':'fixed'})
        with self.assertRaises(QueryError): strategy.configure({'mode':'legacy'}, {'strategy':'quick','association_text':''})
    def test_assessment_requires_actual_delivery(self):
        s={'strategy':'quick','candidates':{'x':{'delivery':'pending'}}}
        with self.assertRaises(QueryError): strategy.assess(s, {'candidate_id':'x','useful':True,'reason':'有用'})
    def test_association_round_limit(self):
        s={'strategy':'associative','association':{'enabled':True,'max_rounds':1},'association_text':'热力学','rounds':[{'retrieval_kind':'associative'}]}
        with self.assertRaises(QueryError): strategy.recall_request(s, {'question':'原问题','reason':'缺口'})

    def test_disabled_association_and_conflicting_plan_are_not_bypassed(self):
        s = {'strategy':'standard', 'association':{'enabled':False,'max_rounds':3}, 'rounds':[]}
        with self.assertRaises(QueryError):
            strategy.recall_request(s, {'question':'温度','retrieval_kind':'associative'})
        s.update(strategy='associative', association={'enabled':True,'max_rounds':3}, association_text='新子问题')
        with self.assertRaises(QueryError):
            strategy.recall_request(s, {'question':'原问题','protected_terms':['原问题']})
        request, kind = strategy.recall_request(s, {'question':'新子问题','protected_terms':['新子问题']})
        self.assertEqual(request['protected_terms'], ['新子问题'])

    def test_old_configuration_does_not_mutate_storage_data(self):
        from copy import deepcopy
        old = {'mode':'owner_document','query':{'budget': {'read_bytes':42}}, 'rounds':[]}
        before = deepcopy(old)
        strategy.configuration(old)
        self.assertEqual(old, before)

import test_reading_owner_document as owner_tests
from material_query.api import dispatch
from material_query.reading import read_json, save


class ThreeModeIntegrationTests(owner_tests.OwnerDocumentTests):
    def test_quick_assess_note_switch_and_synthesis(self):
        configured = self.call('configure', strategy='quick', association_text='')
        self.assertEqual(configured['status'], 'ok', configured)
        result = self.recall()
        row = result['value']['candidates'][0]
        self.assertIn('candidate_id', row)
        self.assertTrue(row['sources'])
        self.assertEqual(result['value']['next_action'], 'assess')
        self.assertEqual(self.call('note', owner_id=row['owner_id'], research_note=self.research_note(row['sources']))['code'], 'VALIDATION')
        accepted = self.call('assess', candidate_id=row['candidate_id'], useful=True, reason='回答温标边界')
        self.assertEqual(accepted['status'], 'ok', accepted)
        note = self.research_note(row['sources'])
        from copy import deepcopy
        forged = deepcopy(note)
        forged['sources'][0]['locator'] = 'block:never-delivered'
        self.assertEqual(self.call('note', owner_id=row['owner_id'], research_note=forged)['code'], 'VALIDATION')
        saved = self.call('note', owner_id=row['owner_id'], candidate_ids=[row['candidate_id']], research_note=note)
        self.assertEqual(saved['status'], 'ok', saved)
        page = self.call('page')
        self.assertTrue(page['value']['candidates'], page)
        self.assertEqual(page['value']['candidates'][0]['owner_id'], row['owner_id'])
        synth = self.call('synthesize', research_note=note)
        self.assertEqual(synth['status'], 'ok', synth)
        handoff = dispatch(self.app, 'reading-handoff', {'session_id': self.sid})
        self.assertTrue(handoff['value']['synthesis_included'], handoff)
        self.assertIn('召回片段', handoff['value']['context_markdown'])
        self.call('assess', candidate_id=row['candidate_id'], useful=False, reason='发现不适用')
        revoked = dispatch(self.app, 'reading-handoff', {'session_id': self.sid})
        self.assertFalse(revoked['value']['synthesis_included'])
        self.call('configure', strategy='standard', association_text='')
        rejected = self.call('note', owner_id=row['owner_id'], research_note=note)
        self.assertEqual(rejected['code'], 'VALIDATION', rejected)
        full = self.call('read', owner_id=row['owner_id'])
        self.assertIn(full['status'], {'ok', 'partial'}, full)
        self.assertEqual(self.call('note', owner_id=row['owner_id'], research_note=self.research_note(full['value']['document_refs']))['status'], 'ok')

    def test_configuration_cas_and_idempotence(self):
        raw = dict(session_id=self.sid, expected_revision=self.revision, request_id='configure-once', strategy='quick', association_text='新方向')
        first = dispatch(self.app, 'reading-configure', raw)
        self.assertEqual(first['status'], 'ok', first)
        replay = dispatch(self.app, 'reading-configure', raw)
        self.assertTrue(replay['value']['replayed'])
        conflict = dispatch(self.app, 'reading-configure', dict(raw, request_id='new-id'))
        self.assertEqual(conflict['code'], 'CONFLICT')

    def test_association_real_query_and_round_limit(self):
        from material_query.wire import json_value
        original = self.owner_read()
        self.call('decide', direction='expand', reason='完整文稿给出下一线索', next_step='联想查缺口', outcome='已有正文仍缺上游', human_decision='')
        self.call('configure', strategy='associative', association_text='温度', association={'enabled':True,'max_rounds':1})
        result = self.call('recall', question='温度', keywords=[], scope=json_value(self.scope),
                           reason='依据已完整交付根文稿的具体线索', clue_sources=original['document_refs'])
        self.assertIn(result['status'], {'ok','partial'}, result)
        head = read_json(self.root / '.local' / 'reading-sessions' / self.sid / 'HEAD.json')
        self.assertEqual(head['rounds'][-1]['question'], '温度')
        self.assertEqual(head['rounds'][-1]['retrieval_kind'], 'associative')
        self.assertEqual(head['rounds'][-1]['clue_sources'], original['document_refs'])
        self.call('decide', direction='expand', reason='更多边界', next_step='继续查', outcome='尚缺量纲', human_decision='')
        from material_query.wire import json_value
        self.assertEqual(self.call('recall', question='温度', keywords=[], scope=json_value(self.scope), reason='再次查')['code'], 'VALIDATION')

    def test_synthesis_invalidates_after_owner_note_change(self):
        result = self.owner_read()
        note = self.research_note(result['document_refs'])
        self.assertEqual(self.call('note', owner_id=self.fx.owner_ids['A'], research_note=note)['status'], 'ok')
        self.assertEqual(self.call('synthesize', research_note=note)['status'], 'ok')
        note['understanding'] += ' 新理解'
        self.call('note', owner_id=self.fx.owner_ids['A'], research_note=note)
        handoff = dispatch(self.app, 'reading-handoff', {'session_id': self.sid})
        self.assertFalse(handoff['value']['synthesis_included'])
        self.assertTrue(any('底稿已变化' in gap for gap in handoff['value']['gaps']))

    def test_ask_user_configure_does_not_grant_recall_and_archived_rejects(self):
        from material_query.wire import json_value
        self.call('decide', direction='ask_user', reason='待范围意见', next_step='等待', outcome='', human_decision='')
        self.assertEqual(self.call('configure', strategy='associative', association_text='温度', association={'enabled': True, 'max_rounds': 2})['status'], 'ok')
        self.assertEqual(self.call('recall', question='温度', keywords=[], scope=json_value(self.scope), reason='越过等待')['code'], 'VALIDATION')
        self.call('archive', archived=True, reason='保存历史')
        self.assertEqual(self.call('configure', strategy='quick', association_text='')['code'], 'VALIDATION')

    def test_cross_owner_synthesis_and_quick_owner_limit(self):
        from dataclasses import replace
        from material_query.wire import json_value
        import uuid
        self.sid = 'RS-' + str(uuid.uuid4())
        self.scope = replace(self.scope, owner_ids=(self.fx.owner_ids['A'], self.fx.owner_ids['B']))
        query = replace(self.query, scope=self.scope, scope_ceiling=self.scope)
        started = dispatch(self.app, 'reading-start', dict(session_id=self.sid, goal='双Owner', conditions=[], query=json_value(query), mode='owner_document', strategy='quick', context={'max_owners': 1, 'note_max_tokens':6000}))
        self.assertEqual(started['status'], 'ok', started)
        self.assertIn('reading-assess', started['value']['guidance'])
        self.assertNotIn('reading-read', started['value']['guidance'])
        self.revision = 1
        found = self.call('recall', question='反馈', keywords=[], scope=json_value(self.scope), reason='合成双Owner')
        rows = found['value']['candidates']
        self.assertEqual(len(rows), 2, found)
        for row in rows:
            self.call('assess', candidate_id=row['candidate_id'], useful=True, reason='各有边界')
        first = self.call('note', owner_id=rows[0]['owner_id'], research_note=self.research_note(rows[0]['sources']))
        self.assertEqual(first['status'], 'ok', first)
        denied = self.call('note', owner_id=rows[1]['owner_id'], research_note=self.research_note(rows[1]['sources']))
        self.assertEqual(denied['code'], 'VALIDATION', denied)
        combined = self.call('synthesize', research_note=self.research_note([ref for row in rows for ref in row['sources']]))
        self.assertEqual(combined['code'], 'VALIDATION', combined)
        # Widen only the synthetic fixture's explicit cap, not product defaults.
        path = self.root / '.local' / 'reading-sessions' / self.sid / 'HEAD.json'
        fixture = read_json(path); fixture['context']['max_owners'] = 2; save(path, fixture)
        self.call('configure', strategy='standard', association_text='')
        sources = []
        for row in rows:
            full = self.call('read', owner_id=row['owner_id'])
            self.assertIn(full['status'], {'ok','partial'}, full)
            actual = read_json(path)['owner_progress'][row['owner_id']]
            sources.extend(actual['delivered_sources'])
        combined = self.call('synthesize', research_note=self.research_note(sources))
        self.assertEqual(combined['status'], 'ok', {'result': combined, 'progress': read_json(path)['owner_progress'], 'requested': sources})

    def test_synthesis_rejects_merely_declared_source(self):
        result = self.owner_read()
        head_path = self.root / '.local' / 'reading-sessions' / self.sid / 'HEAD.json'
        head = read_json(head_path)
        # sources is a references inventory, deliberately wider than actual
        # delivered_sources. The synthesis boundary must not trust the inventory.
        ref = dict(kind='file', id='SRC-UNREAD', revision=None, sha256='a'*64, locator=None)
        head['owner_progress'][self.fx.owner_ids['A']]['sources'].append(ref)
        save(head_path, head)
        denied = self.call('synthesize', research_note=self.research_note([ref]))
        self.assertEqual(denied['code'], 'VALIDATION', denied)


for _name in dir(owner_tests.OwnerDocumentTests):
    if _name.startswith('test_') and _name not in ThreeModeIntegrationTests.__dict__:
        setattr(ThreeModeIntegrationTests, _name, None)
