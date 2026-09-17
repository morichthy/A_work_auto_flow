"""Owner阅读契约回归：真实固定存储；合成笔记不代表实际AI理解。"""
import uuid
from copy import copy, deepcopy
import json
import base64
import hashlib
from dataclasses import replace
from unittest.mock import patch

import test_reading_workflow as legacy
from material_query.api import dispatch
from material_query.wire import json_value
from material_query.reading import Reading, read_json, save
from material_query.reading_owner import OperationLedger, estimated_tokens, handoff_value
from material_query.budget import DEFAULT_BUDGET
from memory import contracts, documents, owners
from memory.service import MemoryService
from test_memory_documents_v3 import section_payload, document_payload


class OwnerDocumentTests(legacy.ReadingWorkflowTests):
    # 复用fixture和调用工具，但不重复执行legacy契约测试。
    def setUp(self):
        super().setUp()
        self.sid = 'RS-' + str(uuid.uuid4())
        result = dispatch(self.app, 'reading-start', {
            'session_id': self.sid, 'goal': 'Owner完整阅读', 'conditions': [],
            'query': json_value(self.query), 'mode': 'owner_document',
            'context': {'max_owners': 10, 'note_max_tokens': 6000}})
        self.assertEqual(result['status'], 'ok', result)
        self.revision = 1

    def test_owner_candidates_only_identity_and_text(self):
        result = self.recall()
        self.assertTrue(result['value']['candidates'])
        self.assertTrue(all(set(row) == {'owner_id', 'text'} for row in result['value']['candidates']))
        serialized = json.dumps({key: value for key, value in result['value'].items()
                                 if key not in {'session_id', 'revision'}}, ensure_ascii=False)
        self.assertEqual(result['consumed']['output_chars'], len(serialized))
        self.assertLessEqual(sum(row['text'].count('ONLY_DEFINITION') for row in result['value']['candidates']), 1)

    def test_owner_candidates_progress_one_per_page_then_skip_selected(self):
        first = self.recall()
        self.assertEqual(len(first['value']['candidates']), 1, first)
        self.assertTrue(first['value']['has_more'])
        self.assertEqual(first['value']['pending_owner_count'], 1)
        resumed = self.call('resume')
        self.assertTrue(resumed['value']['has_more'])
        self.assertEqual(resumed['value']['pending_owner_count'], 1)
        second = self.call('page')
        self.assertEqual(len(second['value']['candidates']), 1, second)
        self.assertNotEqual(second['value']['candidates'][0]['text'], first['value']['candidates'][0]['text'])
        head = read_json(self.root / '.local' / 'reading-sessions' / self.sid / 'HEAD.json')
        # Existing hits may retain bounded matched_text diagnostics. The new
        # pending state must not introduce packet/text/body copies of its own.
        for row in head['candidates'].values():
            self.assertTrue(set(row.get('preview', {})) <= {'form', 'refs'})
            self.assertFalse(set(row) & {'packet', 'text', 'body_markdown'})
        read = self.call('read', owner_id=self.fx.owner_ids['A'])
        self.assertIn(read['status'], {'ok', 'partial'}, read)
        third = self.call('page')
        self.assertEqual(third['value']['candidates'], [], third)
        self.assertEqual(third['value']['pending_owner_count'], 0)

    def test_partial_pending_packet_remains_resumable_without_repeating_text(self):
        self.recall()
        original = Reading.packet
        def partial_packet(reader, *args, **kwargs):
            packet, links = original(reader, *args, **kwargs)
            if 'ONLY_FULL_RESULT' in json.dumps(packet):
                packet['complete'] = False
            return packet, links
        with patch.object(Reading, 'packet', partial_packet):
            partial = self.call('page')
        self.assertEqual(len(partial['value']['candidates']), 1, partial)
        self.assertTrue(partial['value']['has_more'])
        complete = self.call('page')
        self.assertEqual(complete['value']['candidates'], [])
        self.assertEqual(complete['value']['pending_owner_count'], 0)

    def test_owner_sessions_without_delivery_fields_do_not_replay_old_candidates(self):
        self.recall()
        file = self.root / '.local' / 'reading-sessions' / self.sid / 'HEAD.json'
        session = read_json(file)
        for row in session['candidates'].values():
            for key in ('delivery', 'preview', 'preview_round_index'):
                row.pop(key, None)
        save(file, session)
        for _ in range(2):
            self.call('decide', direction='expand', reason='旧RS兼容检查', next_step='补查', outcome='仍需确认边界', human_decision='')
            result = self.recall()
            self.assertEqual(result['value']['candidates'], [], result)

    def test_owner_read_complete_fallback_and_repeat_progress(self):
        self.recall()
        result = self.call('read', owner_id=self.fx.owner_ids['A'])
        self.assertIn(result['status'], {'ok', 'partial'}, result)
        self.assertIn('OPTIONAL_BLOCK', str(result))
        self.assertTrue(result['value']['gaps'])
        resumed = self.call('resume')
        self.assertIn(self.fx.owner_ids['A'], resumed['value']['owner_progress'])

    def test_template_uses_owner_mode(self):
        result = dispatch(self.app, 'reading-template', {})
        self.assertEqual(result['value']['mode'], 'owner_document')

    def owner_read(self):
        self.recall()
        result = self.call('read', owner_id=self.fx.owner_ids['A'])
        self.assertIn(result['status'], {'ok', 'partial'}, result)
        return result['value']

    def research_note(self, sources):
        return dict(question='合成温标换算', conditions=['t以摄氏度表示'],
                    understanding='必须先固定温度基准', logic=['检查假设和量纲'],
                    details=['$$T=t+273.15$$\nT单位K；t单位°C。'], sources=sources,
                    limitations=['未验证现实测量'], next_steps=['用边界样本验证'])

    def test_note_fixed_sources_snapshot_and_handoff(self):
        result = self.owner_read()
        note = self.research_note(result['document_refs'])
        saved = self.call('note', owner_id=self.fx.owner_ids['A'], research_note=note)
        self.assertEqual(saved['status'], 'ok', saved)
        self.assertIn('estimated_note_tokens', saved['value'])
        handoff = dispatch(self.app, 'reading-handoff', {'session_id': self.sid})
        self.assertIn('273.15', handoff['value']['context_markdown'])
        self.assertNotIn('owner_progress', handoff['value'])
        self.assertTrue((self.root / 'context' / 'reading-notes' / self.sid / 'current.md').is_file())
        view = dispatch(self.app, 'reading-view', {'session_id': self.sid, 'notes_only': True})
        self.assertTrue(view['value']['candidates'])
        candidate = view['value']['candidates'][0]
        full = self.call('read', candidate_ids=[candidate['candidate_id']])
        self.assertIn('packet', full['value']['readings'][0])

    def test_spoofed_note_and_source_expansion_rejected(self):
        result = self.owner_read()
        forged = deepcopy(result['sources'][0])
        forged['sha256'] = '0' * 64
        note = self.research_note([forged])
        self.assertEqual(self.call('note', owner_id=self.fx.owner_ids['A'], research_note=note)['code'], 'VALIDATION')
        self.assertEqual(self.call('read', owner_id=self.fx.owner_ids['A'], source_refs=[forged])['code'], 'VALIDATION')

    def test_note_source_ids_resolve_to_delivered_fixed_refs(self):
        result = self.owner_read()
        target = result['document_refs'][0]
        note = self.research_note([target['id']])
        saved = self.call('note', owner_id=self.fx.owner_ids['A'], research_note=note)
        self.assertEqual(saved['status'], 'ok', saved)
        head = read_json(self.root / '.local' / 'reading-sessions' / self.sid / 'HEAD.json')
        refs = head['owner_notes'][self.fx.owner_ids['A']]['sources']
        self.assertTrue(refs)
        self.assertTrue(all(isinstance(ref, dict) and ref in result['sources'] for ref in refs))
        self.assertTrue(all(ref['id'] == target['id'] for ref in refs))
        unknown = self.call('note', owner_id=self.fx.owner_ids['A'], research_note=self.research_note(['MEM-UNKNOWN']))
        self.assertEqual(unknown['code'], 'VALIDATION', unknown)

    def test_note_unregistered_evidence_preserves_persisted_session(self):
        result = self.owner_read()
        note = self.research_note(result['document_refs'])
        self.assertEqual(self.call('note', owner_id=self.fx.owner_ids['A'], research_note=note)['status'], 'ok')
        folder = self.root / '.local' / 'reading-sessions' / self.sid
        before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        snapshot = self.root / 'context' / 'reading-notes' / self.sid / 'current.md'
        markdown = snapshot.read_bytes()
        note['details'].append('实验结果来自RUN-FORGED。')
        denied = self.call('note', owner_id=self.fx.owner_ids['A'], research_note=note)
        self.assertEqual(denied['code'], 'VALIDATION', denied)
        after = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        # Rejected operations retain real IO usage in HEAD.consumed by the existing
        # resource-audit contract. No semantic state/revision/history may change.
        previous_head, current_head = json.loads(before.pop('HEAD.json')), json.loads(after.pop('HEAD.json'))
        previous_head.pop('consumed'); current_head.pop('consumed')
        # The envelope fingerprint necessarily changes with the audited usage.
        previous_head.pop('storage_digest'); current_head.pop('storage_digest')
        self.assertEqual(previous_head, current_head)
        self.assertEqual(before, after)
        self.assertEqual(snapshot.read_bytes(), markdown)

    def test_selected_owner_no_more_snippets_and_operation_budget_resets(self):
        self.owner_read()
        head = self.root / '.local' / 'reading-sessions' / self.sid / 'HEAD.json'
        session = read_json(head)
        session['consumed'] = {key: value for key, value in session['query']['budget'].items()}
        save(head, session)
        resumed = self.call('resume')
        self.assertIn(resumed['status'], {'ok', 'partial'}, resumed)
        self.call('decide', direction='expand', reason='检验候选抑制', next_step='补查', outcome='具体未决问题', human_decision='')
        found = self.recall()
        self.assertEqual(found['value']['candidates'], [])

    def test_process_preferred_and_document_scope_not_retrieval_level(self):
        fx = copy(self.fx)
        fx.root, fx.service = self.root, MemoryService(self.root)
        fx.records, fx.record_ids, fx.refs = deepcopy(fx.records), deepcopy(fx.record_ids), deepcopy(fx.refs)
        source = fx.records['reading.unit']
        draft = {key: deepcopy(source[key]) for key in (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
        draft.update(kind='document_section', level=None, title='研究正文', body_markdown='',
                     payload=section_payload(documents.fixed_ref(source)), schema_version=3)
        section = fx.commit_draft('owner.section', draft)
        for name, dtype in [('owner.report', 'research_report'), ('owner.process', 'research_process')]:
            draft.update(kind='document', title=dtype, payload=document_payload([documents.fixed_ref(section)], document_type=dtype))
            fx.commit_draft(name, draft)
        result = self.owner_read()
        self.assertEqual(result['reading_form'], 'research_process', result)
        self.assertEqual(len(result['document_refs']), 1)
        self.assertIn('OPTIONAL_BLOCK', result['text'])

    def test_source_revision_and_revocation_block_saved_note(self):
        result = self.owner_read()
        target = next(ref for ref in result['sources'] if ref['id'] == self.fx.record_ids['reading.unit'])
        saved = self.call('note', owner_id=self.fx.owner_ids['A'], research_note=self.research_note([target]))
        self.assertEqual(saved['status'], 'ok', saved)
        fx = copy(self.fx)
        fx.root, fx.service = self.root, MemoryService(self.root)
        fx.records, fx.record_ids, fx.refs = deepcopy(fx.records), deepcopy(fx.record_ids), deepcopy(fx.refs)
        updated = deepcopy(fx.records['reading.unit']['payload'])
        updated['blocks'][1]['markdown'] += ' 新修订'
        fx.revise('owner.unit.updated', 'reading.unit', payload=updated)
        handoff = dispatch(self.app, 'reading-handoff', {'session_id': self.sid})
        self.assertEqual(handoff['value']['notes_count'], 0, handoff)
        self.assertEqual(handoff['value']['omitted_note_count'], 1)
        self.assertEqual(self.call('note', owner_id=self.fx.owner_ids['A'], research_note=self.research_note([target]))['code'], 'VALIDATION')
        with fx.source_access('A', enabled=False):
            denied = dispatch(self.app, 'reading-handoff', {'session_id': self.sid})
            self.assertEqual(denied['code'], 'DENIED', denied)
            self.assertIsNone(denied['value'])

    def test_max_owners_counts_selected_not_recall_candidates(self):
        self.sid = 'RS-' + str(uuid.uuid4())
        self.scope = replace(self.scope, owner_ids=(self.fx.owner_ids['A'], self.fx.owner_ids['B']))
        query = replace(self.query, scope=self.scope, scope_ceiling=self.scope)
        started = dispatch(self.app, 'reading-start', {'session_id': self.sid, 'goal': 'Owner选择限额',
            'conditions': [], 'query': json_value(query), 'mode': 'owner_document',
            'context': {'max_owners': 1, 'note_max_tokens': 6000}})
        self.assertEqual(started['status'], 'ok', started)
        result = self.call('recall', question='反馈', keywords=[], scope=json_value(self.scope), reason='合成多Owner')
        ids = set(row['owner_id'] for row in result['value']['candidates'])
        self.assertEqual(ids, {self.fx.owner_ids['A'], self.fx.owner_ids['B']}, result)
        first = self.call('read', owner_id=self.fx.owner_ids['A'])
        self.assertIn(first['status'], {'ok', 'partial'}, first)
        second = self.call('read', owner_id=self.fx.owner_ids['B'])
        self.assertEqual(second['code'], 'VALIDATION', second)

    def test_figure_reference_map_and_explicit_expansion(self):
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jCz0AAAAASUVORK5CYII=')
        image = self.root / '合成图.png'
        image.write_bytes(png)
        ref = dict(target_kind='file', target_id='SRC-OWNER-FIGURE', revision=None,
                   sha256=hashlib.sha256(png).hexdigest(), locator='', relation='references')
        registry = self.root / 'retrieval' / 'sources.json'
        data = json.loads(registry.read_text(encoding='utf-8'))
        data['sources'].append(dict(source_id=ref['target_id'], path='合成图.png', enabled=True,
                                    sensitivity='internal', sha256=ref['sha256']))
        registry.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        fx = copy(self.fx)
        fx.root, fx.service = self.root, MemoryService(self.root)
        fx.records, fx.record_ids, fx.refs = deepcopy(fx.records), deepcopy(fx.record_ids), deepcopy(fx.refs)
        updated = deepcopy(fx.records['reading.unit']['payload'])
        updated['blocks'][1]['markdown'] += '\n![合成图](figure:0)'
        updated['figures'] = [{'ref': ref, 'caption': '固定合成图注'}]
        fx.revise('owner.unit.figure', 'reading.unit', payload=updated)
        result = self.owner_read()
        self.assertNotIn('data:image', json.dumps(result))
        figure = result['references'][0]
        self.assertEqual(figure['caption'], '固定合成图注')
        self.assertIn(figure['marker'], result['text'])
        self.assertEqual(figure['block_ids'], ['result'])
        expanded = self.call('read', owner_id=self.fx.owner_ids['A'], source_refs=[figure['ref']])
        self.assertTrue(expanded['value']['expanded_sources'][0]['data_url'].startswith('data:image/png;base64,'))

    def test_declared_run_reference_expands_summary_only_and_rechecks_version(self):
        import evidence
        run = owners.resolve_owner(self.root, self.fx.run_ids['A'])
        run_ref = dict(target_kind='owner', target_id=run['owner_id'], revision=None,
                       sha256=evidence.fingerprint(run['native_data']), locator='', relation='references')
        fx = copy(self.fx)
        fx.root, fx.service = self.root, MemoryService(self.root)
        fx.records, fx.record_ids, fx.refs = deepcopy(fx.records), deepcopy(fx.record_ids), deepcopy(fx.refs)
        updated = deepcopy(fx.records['reading.unit']['payload'])
        updated['run_ref'] = run_ref
        fx.revise('owner.unit.run', 'reading.unit', payload=updated)
        self.sid = 'RS-' + str(uuid.uuid4())
        ceiling = replace(self.scope, owner_ids=(self.fx.owner_ids['A'], run['owner_id']))
        query = replace(self.query, scope_ceiling=ceiling)
        started = dispatch(self.app, 'reading-start', {'session_id': self.sid, 'goal': '按需Run引用',
            'conditions': [], 'query': json_value(query), 'mode': 'owner_document'})
        self.assertEqual(started['status'], 'ok', started)
        result = self.owner_read()
        reference = next(ref for ref in result['sources'] if ref['id'] == run['owner_id'])
        self.assertNotIn('run_capture', result['text'])
        expanded = self.call('read', owner_id=self.fx.owner_ids['A'], source_refs=[reference])
        self.assertIn(expanded['status'], {'ok', 'partial'}, expanded)
        self.assertTrue(any('Run未保存结论' in gap for gap in expanded['value']['gaps']))
        native = self.root / run['native_ref']['path']
        value = json.loads(native.read_text(encoding='utf-8'))
        value['conclusion'] = '合成新修订结论'
        native.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        denied = dispatch(self.app, 'reading-handoff', {'session_id': self.sid})
        self.assertEqual(denied['code'], 'STALE', denied)
        self.assertIsNone(denied['value'])


class OwnerBudgetTests(__import__('unittest').TestCase):
    def note_fixture(self):
        source = dict(kind='record', id='MEM-DOC', revision=1, sha256='a' * 64, locator=None)
        run = dict(kind='owner', id='RUN-20260917T000000Z-ABC123', revision=None, sha256='b' * 64, locator=None)
        figure = dict(kind='file', id='SRC-FIGURE-1', revision=None, sha256='c' * 64, locator=None)
        session = dict(owner_progress={'RES-A': {'full_delivered': True, 'sources': [source, run, figure]}},
                       candidates={}, owner_notes={'RES-A': {'previous': 'must survive rejected edits'}},
                       context={'note_max_tokens': 6000})
        note = dict(question='是否存在MEM-HYPOTHETICAL？', conditions=[], understanding='合成理解',
                    logic=[], details=[], sources=['MEM-DOC'], limitations=[], next_steps=[])
        return session, note, (source, run, figure)

    def test_note_evidence_ids_missing_or_unknown_reject_without_mutation(self):
        from material_query.reading_owner import note_owner
        from material_query.validation import QueryError
        for field, value in [('understanding', '见RUN-20260917T000000Z-ABC123。'),
                             ('logic', ['依据SRC-FIGURE-1，得出结论']),
                             ('details', ['未知MEM-FORGED应拒绝']),
                             ('details', ['[说明](https://example.org/a)另见SRC-FIGURE-1']),
                             ('details', ['[SRC-FIGURE-1](https://example.org/a)']),
                             ('details', ['`https://example.org/a`另见SRC-FIGURE-1']),
                             ('details', ['引用MEM-DOC-WRONG，不能匹配已交付前缀'])]:
            with self.subTest(field=field, value=value):
                session, note, _ = self.note_fixture(); note[field] = value
                before, raw_before = deepcopy(session), deepcopy(note)
                with self.assertRaises(QueryError) as caught:
                    note_owner(None, session, {'owner_id': 'RES-A', 'research_note': note}, None)
                self.assertEqual(caught.exception.code, 'VALIDATION')
                self.assertEqual(session, before)
                self.assertEqual(note, raw_before)

    def test_note_evidence_ids_chinese_punctuation_and_subset_normalize(self):
        from material_query.reading_owner import note_owner
        session, note, refs = self.note_fixture()
        note.update(understanding='根据【MEM-DOC】得到公式。',
                    logic=['（`RUN-20260917T000000Z-ABC123`）实验'],
                    details=['见SRC-FIGURE-1@1；图示边界。'], sources=[r['id'] for r in refs])
        self.assertTrue(note_owner(None, session, {'owner_id': 'RES-A', 'research_note': note}, None)['saved'])
        self.assertEqual(session['owner_notes']['RES-A']['sources'], list(refs))
        # Unmentioned delivered sources must not be forced into every note.
        session, note, refs = self.note_fixture()
        note['details'] = ['MEM-DOC：T=t+273.15；RES-A与RS-NAV仅导航；https://example.org/MEM-URL不是固定证据。']
        note_owner(None, session, {'owner_id': 'RES-A', 'research_note': note}, None)
        self.assertEqual(session['owner_notes']['RES-A']['sources'], [refs[0]])

    def test_delivered_nonstandard_source_id_is_matched_exactly(self):
        from material_query.reading_owner import note_owner
        from material_query.validation import QueryError
        session, note, _ = self.note_fixture()
        ref = dict(kind='file', id='FIG-local_01', revision=None, sha256='d' * 64, locator=None)
        session['owner_progress']['RES-A']['sources'].append(ref)
        note['details'] = ['图【FIG-local_01】对应此实验。']
        with self.assertRaises(QueryError):
            note_owner(None, session, {'owner_id': 'RES-A', 'research_note': note}, None)
        note['sources'].append(ref['id'])
        note_owner(None, session, {'owner_id': 'RES-A', 'research_note': note}, None)
        self.assertIn(ref, session['owner_notes']['RES-A']['sources'])

    def test_source_id_resolution_preserves_locators_and_rejects_ambiguity(self):
        from material_query.reading_owner import normalize_note_sources
        from material_query.validation import QueryError
        source = dict(kind='record', id='MEM-EXAMPLE', revision=1, sha256='a' * 64, locator=None)
        block = dict(source, locator='block:result')
        self.assertEqual(normalize_note_sources(['MEM-EXAMPLE', source], [source, block, source]), [source, block])
        for other in (dict(source, revision=2), dict(source, sha256='b' * 64), dict(source, kind='file')):
            with self.assertRaises(QueryError) as caught:
                normalize_note_sources(['MEM-EXAMPLE'], [source, other])
            self.assertEqual(caught.exception.code, 'VALIDATION')
            self.assertEqual(normalize_note_sources([source], [source, other]), [source])
        with self.assertRaises(QueryError):
            normalize_note_sources(['MEM-UNKNOWN'], [source])

    def test_internal_diagnostics_do_not_charge_ai_output_but_io_still_bounded(self):
        ledger = OperationLedger(DEFAULT_BUDGET)
        with ledger.internal():
            ledger.charge('output_chars', 900000)
            ledger.charge('read_bytes', 100)
        self.assertEqual(ledger.used['output_chars'], 0)
        self.assertEqual(ledger.used['read_bytes'], 100)
        ledger.charge('output_chars', 10)
        self.assertEqual(ledger.used['output_chars'], 10)

    def test_handoff_omits_whole_note_and_explains_token_estimate(self):
        note = dict(question='q', conditions=[], understanding='中' * 2000, logic=[],
                    details=['$$T=t+273.15$$'], sources=[], limitations=[], next_steps=[])
        session = dict(goal='g', conditions=[], decisions=[], candidates={}, owner_progress={},
                       owner_notes={'A': note}, context={'max_owners': 10, 'note_max_tokens': 512}, phase='finish')
        result = handoff_value(session)
        self.assertEqual(result['omitted_note_count'], 1)
        self.assertNotIn('273.15', result['context_markdown'])
        self.assertTrue(result['gaps'])
        self.assertEqual(estimated_tokens('中文'), 6)

    def test_finish_with_selected_unnoted_owner_remains_partial(self):
        note = dict(question='q', conditions=[], understanding='u', logic=[], details=[],
                    sources=[], limitations=[], next_steps=[])
        session = dict(goal='g', conditions=[], decisions=[], candidates={},
                       owner_progress={'A': {'selected': True}, 'B': {'selected': True}},
                       owner_notes={'A': note}, context={'max_owners': 10, 'note_max_tokens': 6000}, phase='finish')
        result = handoff_value(session)
        self.assertFalse(result['complete'])
        self.assertEqual(result['unnoted_candidate_count'], 1)
        self.assertTrue(any('尚未保存' in gap for gap in result['gaps']))


# Unittest inherits test methods. Keep this class scoped to the new contract;
# legacy tests continue in their original module with unchanged request shape.
for _name in dir(legacy.ReadingWorkflowTests):
    if _name.startswith('test_') and _name not in OwnerDocumentTests.__dict__:
        setattr(OwnerDocumentTests, _name, None)
