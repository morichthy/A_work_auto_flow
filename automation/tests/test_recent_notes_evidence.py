"""轻量展示不等于证据复核：测试时间窗口、撤权和禁止慢路径。"""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import material_query_fixture
from workbench_app import reading_notes
from material_query import reading_citations


class RecentNotesTests(unittest.TestCase):
    def test_display_does_not_inherit_near_full_ai_note_budget(self):
        from material_query.reading_snapshot import notes_value
        from material_query.reading_owner import handoff_value
        ref = dict(kind='record', id='MEM-abc', revision=1, sha256='b'*64, locator='block:formula')
        note = dict(question='q', conditions=[], understanding='理解' * 900, logic=[], details=['$s_0=0$'],
                    sources=[ref], limitations=[], next_steps=[])
        session = dict(mode='owner_document', goal='目标', conditions=[], phase='finish', decisions=[], rounds=[],
                       owner_progress={}, owner_notes={'A':note}, candidates={}, context={'note_max_tokens':6000,'max_owners':3})
        displayed = notes_value(session)
        self.assertIn('$s_0=0$', displayed['context_markdown'])
        self.assertEqual(displayed['omitted_note_count'], 0)
        self.assertEqual(handoff_value(session)['omitted_note_count'], 0)

    def test_owner_screening_packets_are_atomic_and_display_bounded(self):
        from material_query.reading_snapshot import notes_value
        from material_query.reading_delegation import serialized_size
        packets = {}
        for owner, marker in [('RES-A', 'ALPHA'), ('RES-B', 'BRAVO')]:
            packets[owner] = {
                'owner_id': owner, 'title': owner, 'overview': marker,
                'packet_digest': marker.lower(), 'retrieval_source': 'discovery',
                'coverage': {'complete': True, 'gaps': []},
                'windows': [{'text': marker * 120,
                             'refs': [{'kind': 'record', 'id': 'MEM-' + owner[-1], 'revision': 1,
                                       'sha256': owner[-1].lower() * 64, 'locator': 'block:summary'}],
                             'source_level': 'L4', 'channels': ['lexical']}],
            }
        session = dict(mode='owner_document', session_id='RS-screening', revision=1,
                       goal='筛选Owner', conditions=[], phase='review', decisions=[], candidates={},
                       rounds=[{'discovery': {'status': 'ready', 'reasons': [],
                                              'projection_version': 'owner-discovery-v1'}, 'gaps': []}],
                       owner_progress={}, owner_notes={}, owner_packets=packets,
                       owner_assessments={'RES-A': {'owner_id': 'RES-A', 'status': 'relevant',
                                                    'reason': '命中温标', 'packet_digest': 'alpha'}},
                       fulltext_compensation={'available': False, 'reason': ''},
                       context={'note_max_tokens': 6000, 'max_owners': 3})
        full = notes_value(session)
        self.assertEqual([row['owner_id'] for row in full['owner_packets']], ['RES-A', 'RES-B'])
        self.assertEqual(full['owner_packets'][0]['assessment']['status'], 'relevant')
        # Pick a cap that can hold the base view and exactly one complete packet.
        one_packet = deepcopy(full)
        one_packet['owner_packets'] = full['owner_packets'][:1]
        one_packet['screening_omitted_owner_count'] = 1
        one_packet['gaps'] = list(one_packet['gaps']) + [
            '1个Owner筛选包因工作台展示上限未显示；包仍完整保存在RS，可通过reading-view读取']
        bounded = notes_value(session, max_chars=serialized_size(one_packet))
        self.assertLessEqual(serialized_size(bounded), serialized_size(one_packet))
        self.assertEqual(len(bounded['owner_packets']), 1)
        self.assertEqual(bounded['owner_packets'][0]['windows'][0]['text'], 'ALPHA' * 120)
        self.assertEqual(bounded['screening_omitted_owner_count'], 1)
        self.assertNotIn('BRAVO', str(bounded))

    def test_recent_window_is_semantic_time_and_stable_order(self):
        now = datetime.now(timezone.utc)
        rows = [dict(session_id='old', updated_at=(now-timedelta(hours=25)).isoformat(), note_count=1, archived=False),
                dict(session_id='new', updated_at=now.isoformat(), note_count=1, archived=False),
                dict(session_id='archived', updated_at=now.isoformat(), note_count=1, archived=True)]
        self.assertEqual([r['session_id'] for r in reading_notes.recent_items(rows, now)], ['new'])
        local = now.astimezone(timezone(timedelta(hours=8)))
        rows += [dict(session_id='earlier-local', updated_at=(local-timedelta(minutes=5)).isoformat(), note_count=1, archived=False)]
        self.assertEqual([r['session_id'] for r in reading_notes.recent_items(rows, now)], ['new','earlier-local'])
        boundary = dict(session_id='boundary', updated_at=(now-timedelta(hours=24)).isoformat(), note_count=1, archived=False)
        future = dict(session_id='future', updated_at=(now+timedelta(microseconds=1)).isoformat(), note_count=1, archived=False)
        outside = dict(boundary, session_id='outside', updated_at=(now-timedelta(hours=24,microseconds=1)).isoformat())
        self.assertEqual([r['session_id'] for r in reading_notes.recent_items([future,outside,boundary], now)], ['boundary'])

    def test_numbered_reference_keeps_fixed_metadata_and_deep_link(self):
        refs = [dict(kind='record', id='MEM-abc', revision=2, sha256='a'*64, locator='block:result')]
        text, references = reading_citations.render('根据MEM-abc得到$T=t+273.15$。', refs)
        self.assertIn('[1]', text)
        self.assertIn('#/evidence?id=MEM-abc', text)
        self.assertIn('a'*64, references[0]['url'])
        self.assertEqual(references[0]['ref'], refs[0])
        self.assertIn('$T=t+273.15$', text)

    def test_citation_does_not_modify_code_math_existing_links_or_merge_blocks(self):
        base = dict(kind='record', id='MEM-abc', revision=2, sha256='a'*64)
        text, refs = reading_citations.render('MEM-abc；`MEM-abc`；$MEM-abc$；[原链接](https://example.org/MEM-abc)；MEM-unknown',
            [dict(base, locator='block:a'), dict(base, locator='block:b')])
        self.assertEqual(len(refs), 2)
        self.assertIn('`MEM-abc`', text); self.assertIn('$MEM-abc$', text)
        self.assertIn('[原链接](https://example.org/MEM-abc)', text)
        self.assertIn('MEM-unknown', text)


import test_reading_owner_document as fixtures
from types import SimpleNamespace
from material_query.api import dispatch
from workbench_app import web, evidence_browser
from material_query.reading import read_json, save, Reading


class RecentNotesIntegrationTests(fixtures.OwnerDocumentTests):
    def prepare(self):
        read = self.owner_read()
        saved = self.call('note', owner_id=self.fx.owner_ids['A'], research_note=self.research_note(read['document_refs']))
        self.assertEqual(saved['status'], 'ok', saved)
        self.service = SimpleNamespace(root=self.root, materials=self.app)
        return read

    def test_snapshot_and_recent_never_call_strong_reauthorize_or_original_hash(self):
        self.prepare()
        before = read_json(self.root / '.local/reading-sessions' / self.sid / 'HEAD.json')
        with patch.object(Reading, 'reauthorize', side_effect=AssertionError('slow reauthorize forbidden')), \
             patch('evidence.EvidenceGraph', side_effect=AssertionError('full graph forbidden')), \
             patch('evidence.sha256', side_effect=AssertionError('original hash forbidden')):
            recent = web.post(self.service, 'reading-notes/recent', {})
            self.assertIn(self.sid, [row['session_id'] for row in recent['items']], recent)
            shown = web.post(self.service, 'reading-notes/snapshot', {'session_id':self.sid})
            self.assertEqual(shown['verification'], 'snapshot_only')
            self.assertIn('273.15', shown['context_markdown'])
            self.assertIn('#/evidence?id=', shown['context_markdown'])
        after = read_json(self.root / '.local/reading-sessions' / self.sid / 'HEAD.json')
        self.assertEqual(before, after)
        # Owner-scoped UI queries must not rewrite global context navigation
        # as an empty or single-Owner subset.
        filtered = web.post(self.service, 'reading-notes/recent', {'owner_id':'RES-NO-MATCH'})
        self.assertEqual(filtered['items'], [])
        self.assertIn(self.sid, (self.root / 'context/reading-notes/recent.md').read_text(encoding='utf-8'))

    def test_revoked_source_blocks_cached_snapshot_and_recent_goal(self):
        self.prepare()
        import json
        path = self.root / 'retrieval/sources.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        for source in data['sources']:
            source['enabled'] = False
        path.write_text(json.dumps(data), encoding='utf-8')
        recent = web.post(self.service, 'reading-notes/recent', {})
        self.assertEqual(recent['items'], [])
        with self.assertRaises(Exception):
            web.post(self.service, 'reading-notes/snapshot', {'session_id':self.sid})

    def test_tampered_markdown_rebuilds_only_selected_without_changing_rs(self):
        self.prepare()
        sidecar, markdown = reading_notes.locations(self.root, self.sid)
        # Old cached display envelopes must acquire the question heading without
        # changing stable paths, RS revisions or the underlying research goal.
        cached = read_json(sidecar)
        cached['format_version'] = 2
        save(sidecar, cached)
        web.post(self.service, 'reading-notes/snapshot', {'session_id': self.sid})
        self.assertTrue(markdown.read_text(encoding='utf-8').startswith('# 阅读笔记：'))
        self.assertIn(read_json(self.root / '.local/reading-sessions' / self.sid / 'HEAD.json')['goal'], markdown.read_text(encoding='utf-8'))
        markdown.write_text('FORGED DISPLAY', encoding='utf-8')
        shown = web.post(self.service, 'reading-notes/snapshot', {'session_id':self.sid})
        self.assertNotIn('FORGED DISPLAY', shown['context_markdown'])
        self.assertIn('273.15', shown['context_markdown'])
        with self.assertRaises(Exception):
            web.post(self.service, 'reading-notes/snapshot', {'session_id':'../../outside'})
        head = self.root / '.local/reading-sessions' / self.sid / 'HEAD.json'
        latest = read_json(head)
        original_time = latest['updated_at']
        latest['revision'] += 1
        latest['owner_notes'][self.fx.owner_ids['A']]['understanding'] += ' HEAD_ONLY_UPDATE'
        save(head, latest)
        recent = web.post(self.service, 'reading-notes/recent', {})
        row = next(item for item in recent['items'] if item['session_id'] == self.sid)
        self.assertEqual(row['revision'], latest['revision'])
        fresh = web.post(self.service, 'reading-notes/snapshot', {'session_id':self.sid})
        self.assertIn('HEAD_ONLY_UPDATE', fresh['context_markdown'])
        self.assertEqual(fresh['updated_at'], original_time)

    def test_unrelated_metadata_change_keeps_recent_and_corrupt_record_is_isolated(self):
        self.prepare()
        import json
        owner = self.fx.service.store.root / 'projects/mq-b/project.json'
        # Choose the actual registered metadata locator, without assuming fixture
        # directory layout. Changing title must not hide every reading question.
        from material_query.evidence_navigation import Catalog
        catalog = Catalog(self.root)
        path = self.root / catalog.owners[self.fx.owner_ids['B']]['native_ref']['path']
        data = json.loads(path.read_text(encoding='utf-8')); data['title'] += ' 新标题'
        path.write_text(json.dumps(data), encoding='utf-8'); catalog.close()
        recent = web.post(self.service, 'reading-notes/recent', {})
        self.assertIn(self.sid, [r['session_id'] for r in recent['items']], recent)
        snapshot = web.post(self.service, 'reading-notes/snapshot', {'session_id':self.sid})
        self.assertIn('273.15', snapshot['context_markdown'])

    def test_payload_search_source_detail_and_current_record_revocation(self):
        self.prepare()
        found = web.post(self.service, 'evidence/search', {'query':'ONLY_FULL_RESULT'})
        self.assertIn(self.fx.record_ids['reading.unit'], [r['id'] for r in found['items']], found)
        source = web.post(self.service, 'evidence/detail', {'id':'SRC-MQ-A', 'locator':'完整合成输入'})
        self.assertEqual(source['kind'], 'file')
        self.assertTrue(source['impacts'])
        self.assertIn('未读取原件', source['content_markdown'])
        # Simulate the real-world failure mode: a directly changed canonical
        # record with unchanged HEAD must invalidate the warm display guard.
        from material_query.evidence_navigation import Catalog
        catalog = Catalog(self.root, permission_metadata=True)
        catalog.record(self.fx.record_ids['reading.unit'])
        record_path = next(self.root / p for p in catalog.record_paths if self.fx.record_ids['reading.unit'] in p)
        catalog.close()
        import json
        record = json.loads(record_path.read_text(encoding='utf-8'))
        record['sensitivity'] = 'restricted'
        record_path.write_text(json.dumps(record), encoding='utf-8')
        with self.assertRaises(Exception):
            web.post(self.service, 'reading-notes/snapshot', {'session_id':self.sid})

    def test_native_and_memory_search_detail_and_fixed_version(self):
        self.prepare()
        with patch('evidence.EvidenceGraph', side_effect=AssertionError('full graph forbidden')), \
             patch('evidence.sha256', side_effect=AssertionError('original hash forbidden')):
            result = web.post(self.service, 'evidence/search', {'query': self.fx.run_ids['A']})
            self.assertIn(self.fx.run_ids['A'], [row['id'] for row in result['items']], result)
            result = web.post(self.service, 'evidence/search', {'query': self.fx.record_ids['reading.unit']})
            self.assertIn(self.fx.record_ids['reading.unit'], [row['id'] for row in result['items']], result)
            item = web.post(self.service, 'evidence/detail', {'id':self.fx.record_ids['reading.unit'], 'locator':'block:result'})
            self.assertIn('ONLY_FULL_RESULT', item['content_markdown'])
            self.assertTrue(item['references'])
            self.assertEqual(item['fixed_ref']['locator'], 'block:result')
            with self.assertRaises(ValueError):
                web.post(self.service, 'evidence/detail', {'id':self.fx.record_ids['reading.unit'], 'sha256':'0'*64})


for _name in dir(fixtures.OwnerDocumentTests):
    if _name.startswith('test_') and _name not in RecentNotesIntegrationTests.__dict__:
        setattr(RecentNotesIntegrationTests, _name, None)
