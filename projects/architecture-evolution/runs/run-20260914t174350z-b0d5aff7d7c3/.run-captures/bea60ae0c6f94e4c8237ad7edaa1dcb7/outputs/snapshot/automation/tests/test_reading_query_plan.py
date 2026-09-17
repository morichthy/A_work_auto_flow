"""Language plans use real fixed-store/FTS fixtures; no translation is simulated."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

import test_reading_workflow as workflow
from material_query import query_plan
from material_query.api import dispatch
from material_query.budget import Ledger, DEFAULT_BUDGET
from material_query.validation import QueryError
from material_query.wire import json_value


class ReadingQueryPlanTests(unittest.TestCase):
    setUpClass = classmethod(workflow.ReadingWorkflowTests.setUpClass.__func__)
    tearDownClass = classmethod(workflow.ReadingWorkflowTests.tearDownClass.__func__)
    setUp = workflow.ReadingWorkflowTests.setUp
    tearDown = workflow.ReadingWorkflowTests.tearDown
    call = workflow.ReadingWorkflowTests.call

    def terms(self, **changes):
        entry = dict(id='fixture', domain='testing', zh=['合成检索'], en=['readingfixture'],
                     aliases=[], related=['ONLY_FULL_RESULT'], sources=['synthetic test fixture'], status='active')
        entry.update(changes)
        file = self.root / 'retrieval/query-terms.json'
        file.parent.mkdir(exist_ok=True)
        file.write_text(json.dumps({'schema_version': 1, 'entries': [entry]}), encoding='utf-8')
        return file

    def request(self, **changes):
        raw = dict(question='合成检索', keywords=['合成检索'], scope=json_value(self.scope), reason='双语合成验证',
                   corpus_language='mixed', query_domains=['testing'], language_reason='固定中英合成语料',
                   query_variants=[dict(id='english', language='en', question='readingfixture',
                                        lexical_terms=['readingfixture'])])
        raw.update(changes)
        return raw

    def test_separate_channel_inputs_real_fts_fusion_and_provenance(self):
        self.terms()
        calls = []
        search = self.app._run_search
        def observed(state):
            calls.append(state.request)
            return search(state)
        with patch.object(self.app, '_run_search', side_effect=observed):
            result = self.call('recall', **self.request())
        self.assertIn(result['status'], {'ok', 'partial'}, result)
        candidates = result['value']['candidates']
        ids = [item['candidate_id'] for item in candidates]
        self.assertEqual(len(ids), len(set(ids)))
        unit = next(item for item in candidates if item['ref']['id'] == self.fx.record_ids['reading.unit'])
        self.assertIn('ONLY_FULL_RESULT', json.dumps(unit['packet']))
        self.assertEqual(unit['condition_check'], 'pending')
        self.assertTrue(unit['hits'])
        self.assertTrue(all('query_source' in hit for hit in unit['hits']))
        self.assertIn('related:lexical', {s['id'] for s in unit['query_sources']})
        dense = [q for q in calls if q.channels == ('dense',)]
        self.assertEqual({q.question for q in dense}, {'合成检索', 'readingfixture'})
        self.assertTrue(all(not q.keywords for q in dense))
        self.assertTrue(all(not q.question for q in calls if 'lexical' in q.channels))
        plan = result['value']['coverage']['query_plan']
        self.assertEqual(len(plan['dictionary']['sha256']), 64)
        self.assertEqual(plan['matched_entries'][0]['id'], 'fixture')
        restored = self.call('resume')
        saved = next(row for row in restored['value']['candidates'] if row['candidate_id'] == unit['candidate_id'])
        self.assertEqual(saved['query_sources'], unit['query_sources'])
        self.assertTrue(all(len(source['query_plan_id']) == 64 for source in saved['query_sources']))
        self.assertTrue(all(set(source) == set(query_plan.SOURCE_FIELDS) | {'rank'} for source in saved['query_sources']))
        self.assertEqual(saved['hits'], unit['hits'])

    def test_missing_domain_does_not_expand_polysemous_terms(self):
        self.terms()
        plan = query_plan.build(self.root, Ledger(DEFAULT_BUDGET), self.request(query_domains=[], query_variants=[]))
        self.assertEqual(plan['matched_entries'], [])
        self.assertEqual(plan['related_terms'], [])
        self.assertNotIn('readingfixture', plan['variants'][0]['lexical_terms'])

    def test_related_only_recall_is_separate_and_not_an_equivalent(self):
        self.terms(zh=['zzseedquery'], en=['zzseedalias'], related=['readingfixture'])
        result = self.call('recall', **self.request(question='zzseedquery', keywords=['zzseedquery'], query_variants=[]))
        self.assertIn(result['status'], {'ok', 'partial'}, result)
        rows = result['value']['candidates']
        self.assertTrue(rows)
        self.assertTrue(all(source['kind'] == 'related' for row in rows for source in row['query_sources']))
        self.assertTrue(all(source['weight'] == .25 for row in rows for source in row['query_sources']))

    def test_page_freezes_dictionary_plan_and_retains_scope(self):
        file = self.terms()
        self.sid = 'RS-' + str(uuid.uuid4())
        dispatch(self.app, 'reading-start', {'session_id': self.sid, 'goal': '分页词库快照', 'conditions': [],
                 'query': json_value(replace(self.query, result_limit=1))})
        first = self.call('recall', **self.request())
        self.assertIn(first['status'], {'ok', 'partial'}, first)
        file.write_text('invalid now', encoding='utf-8')
        second = self.call('page')
        self.assertIn(second['status'], {'ok', 'partial'}, second)
        self.assertEqual(first['value']['coverage']['query_plan'], second['value']['coverage']['query_plan'])
        self.assertFalse({c['candidate_id'] for c in first['value']['candidates']} &
                         {c['candidate_id'] for c in second['value']['candidates']})
        self.assertEqual(second['value']['coverage']['scope'], first['value']['coverage']['scope'])
        self.assertGreater(second['consumed']['candidates'], first['consumed']['candidates'])

    def test_invalid_dictionary_is_visible_and_cannot_commit_round(self):
        self.terms(sources=[])
        result = self.call('recall', **self.request())
        self.assertEqual(result['code'], 'VALIDATION', result)
        self.assertEqual(self.revision, 1)

    def test_protected_model_and_numeric_changes_rejected_before_search(self):
        for changed in ['X201 v2.1 drift at 80 °C below 0.5 mV',
                        'X200 v2.1 drift at 80 °C below 0.55 mV',
                        'X200 v2.1 drift at 80 °C below 0.5 mV or 0.6 mV']:
            raw = self.request(question='X200 v2.1 在 80 °C 漂移低于 0.5 mV', protected_terms=['80 °C', '0.5 mV'],
                               query_variants=[dict(id='en', language='en', question=changed, lexical_terms=['drift'])])
            with self.subTest(changed=changed), patch.object(self.app, '_run_search') as search:
                result = self.call('recall', **raw)
                self.assertEqual(result['code'], 'VALIDATION', result)
                search.assert_not_called()

    def test_tiny_output_budget_rejects_plan_before_search_and_preserves_consumption(self):
        self.terms()
        self.sid = 'RS-' + str(uuid.uuid4())
        started = dispatch(self.app, 'reading-start', {'session_id': self.sid, 'goal': '诊断预算', 'conditions': [],
            'query': json_value(replace(self.query, budget=replace(self.query.budget, output_chars=1)))})
        self.assertEqual(started['status'], 'ok', started)
        with patch.object(self.app, '_run_search') as search:
            failed = self.call('recall', **self.request())
            self.assertEqual(failed['code'], 'BUDGET', failed)
            search.assert_not_called()
        home = self.root / '.local/reading-sessions' / self.sid / 'HEAD.json'
        stored = json.loads(home.read_text(encoding='utf-8'))
        self.assertEqual(stored['revision'], 1)
        self.assertEqual(stored['rounds'], [])
        self.assertGreater(stored['consumed']['read_bytes'], started['consumed']['read_bytes'])
        self.assertEqual(stored['consumed']['read_bytes'], failed['consumed']['read_bytes'])
        self.app.close()
        self.app = workflow.Coordinator(self.root)
        retried = self.call('recall', **self.request())
        self.assertEqual(retried['code'], 'BUDGET', retried)
        self.assertGreater(retried['consumed']['read_bytes'], failed['consumed']['read_bytes'])

    def test_cli_markdown_budget_failure_returns_json_and_nonzero_without_traceback(self):
        """Exercise the public process boundary with an actual exhausted RS budget."""
        self.sid = 'RS-' + str(uuid.uuid4())
        started = dispatch(self.app, 'reading-start', {'session_id': self.sid, 'goal': 'CLI诊断预算', 'conditions': [],
            'query': json_value(replace(self.query, budget=replace(self.query.budget, output_chars=1)))})
        self.assertEqual(started['status'], 'ok', started)
        cli = Path(__file__).resolve().parents[1] / 'scripts/workspace_cli.py'
        process = subprocess.run([sys.executable, str(cli),
            'material-query', 'reading-view', '--session', self.sid, '--markdown'], cwd=self.root,
            capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertNotEqual(process.returncode, 0)
        self.assertNotIn('Traceback', process.stdout + process.stderr)
        receipt = json.loads(process.stdout)
        self.assertEqual(receipt['code'], 'BUDGET', receipt)
        self.assertIsNone(receipt['value'])

    def test_equivalent_dedup_and_per_language_vote_normalization(self):
        plan = query_plan.build(self.root, Ledger(DEFAULT_BUDGET), self.request(query_variants=[
            dict(id='same', language='zh', question='合成检索', lexical_terms=['别名']),
            dict(id='en', language='en', question='readingfixture', lexical_terms=['readingfixture']),
            dict(id='en2', language='en', question='reading fixture', lexical_terms=['fixture'])]))
        self.assertEqual(len(plan['variants']), 3)
        self.assertIn('别名', plan['variants'][0]['lexical_terms'])
        route_list = list(query_plan.routes(plan))
        self.assertEqual(sum(r['weight'] for r in route_list if r['language'] == 'en' and r['channel'] == 'dense'), 1)
        candidate = dict(refs=[dict(id='record', revision=1, sha256='a' * 64)], channels=['lexical'], hits=[])
        second_version = deepcopy(candidate)
        second_version['refs'][0].update(revision=2, sha256='b' * 64)
        fused = query_plan.fuse([(route_list[0], [candidate, candidate, second_version]),
                                 (route_list[2], [candidate])])
        self.assertEqual(len(fused), 2, 'fixed revisions must not collapse into bare ID')
        self.assertEqual(len(fused[0]['query_sources']), 2, 'duplicate route entries must not earn extra votes')


if __name__ == '__main__':
    unittest.main()
