"""固定候选上的流水线防线；假评分器仅验证控制，不证明模型效果。"""
from pathlib import Path
import sys
import unittest
from dataclasses import asdict, replace
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from material_query.budget import Ledger, DEFAULT_BUDGET
from material_query.validation import QueryError
from material_query import reranking
from material_query.reading import Reading
from material_query.contracts import AssociationOptions, DefinitionRef, FixedRef, QueryRequest, Scope


class Provider:
    identity = {'model': 'synthetic-control-only', 'sha256': '0' * 64}
    max_length = 512

    def count_tokens(self, question, text):
        return len(text) + len(question)

    def score_pairs(self, pairs):
        return [float('answer' in text) for _, text in pairs]


class ReadingRerankingTests(unittest.TestCase):
    def ledger(self, **overrides):
        return Ledger(replace(DEFAULT_BUDGET, **dict(dict(model_calls=5, model_tokens=2000,
            model_input_tokens=2000, rerank_items=30), **overrides)))

    def items(self):
        return [dict(key=str(i), text=text, complete=True,
                     evidence_parts=[dict(text=text, ref={'id': str(i)}, role='direct')])
                for i, text in enumerate(['型号: X\n背景', '型号: Y\nanswer', '型号: X\nanswer'])]

    def options(self, **changes):
        return reranking.settings(dict(mode='auto', candidate_limit=30, conditions=[], **changes))

    def run_rank(self, items=None, options=None, ledger=None, factory=None, **kwargs):
        return reranking.rank(Path('.'), 'query', items or self.items(), options or self.options(),
                              ledger or self.ledger(), provider_factory=factory or (lambda _: Provider()), **kwargs)

    def test_ce_then_explicit_conflict_demotes_without_removal(self):
        options = reranking.settings({'mode': 'auto', 'candidate_limit': 30,
            'conditions': [{'id': 'model', 'kind': 'literal', 'field': '型号', 'operator': 'eq', 'expected': 'X'}]})
        result = self.run_rank(options=options)
        self.assertEqual([row['key'] for row in result['items']], ['2', '0', '1'])
        self.assertEqual(result['diagnostics']['scored_count'], 3)
        self.assertEqual(len(result['items']), 3)
        self.assertEqual(result['items'][-1]['ranking']['conditions'][0]['status'], 'conflict')

    def test_unavailable_or_failed_model_keeps_original_order(self):
        def fail(_):
            raise ValueError('unavailable')
        result = self.run_rank(factory=fail)
        self.assertEqual([row['key'] for row in result['items']], ['0', '1', '2'])
        self.assertEqual(result['diagnostics']['status'], 'fallback')
        self.assertTrue(result['gaps'])

    def test_required_model_failure_is_explicit(self):
        def fail(_):
            raise ValueError('no model')
        with self.assertRaises(QueryError):
            self.run_rank(options=reranking.settings({'mode': 'required'}), factory=fail)

    def test_overlong_input_is_not_silently_truncated_or_sent(self):
        items = self.items()
        items[1]['text'] = 'answer' * 1000
        ledger = self.ledger()
        result = self.run_rank(items=items, ledger=ledger)
        self.assertEqual(result['diagnostics']['status'], 'fallback')
        self.assertEqual(ledger.snapshot()['model_calls'], 0)
        self.assertIn('input_too_long', result['items'][1]['ranking']['issues'])

    def test_insufficient_budget_never_calls_provider(self):
        ledger = self.ledger(rerank_items=0)
        result = self.run_rank(ledger=ledger)
        self.assertEqual(result['diagnostics']['status'], 'fallback')
        self.assertEqual(ledger.snapshot()['model_calls'], 0)

    def test_successful_pairs_are_metered_once(self):
        ledger = self.ledger()
        self.run_rank(ledger=ledger)
        self.assertEqual(ledger.snapshot()['model_calls'], 1)
        self.assertEqual(ledger.snapshot()['rerank_items'], 3)
        self.assertEqual(ledger.snapshot()['model_input_tokens'], sum(Provider().count_tokens('query', i['text']) for i in self.items()))

    def test_model_change_on_page_does_not_silently_change_strategy(self):
        result = self.run_rank(expected_model={'model': 'older'})
        self.assertEqual(result['diagnostics']['status'], 'fallback')
        self.assertTrue(any('模型' in gap for gap in result['gaps']))
        again = self.run_rank(expected_model=result['diagnostics']['model'])
        self.assertEqual(again['diagnostics']['status'], 'fallback')
        self.assertEqual(again['diagnostics']['model'], {'model': 'older'})

    def test_failed_batch_does_not_charge_unattempted_pairs(self):
        class FailingBatch(Provider):
            batch_size = 1

            def calls_for_pairs(self, count):
                return count

            def score_pairs(self, pairs):
                raise RuntimeError('synthetic first-batch failure')
        ledger = self.ledger()
        result = self.run_rank(ledger=ledger, factory=lambda _: FailingBatch())
        self.assertEqual(result['diagnostics']['status'], 'fallback')
        self.assertEqual(ledger.snapshot()['model_calls'], 1)
        self.assertEqual(ledger.snapshot()['rerank_items'], 1)
        self.assertEqual(ledger.snapshot()['model_input_tokens'], Provider().count_tokens('query', self.items()[0]['text']))

    def test_cancellation_after_inference_stops_before_next_batch(self):
        ledger = self.ledger()

        class CancelAfterBatch(Provider):
            batch_size = 1

            def calls_for_pairs(self, count):
                return count

            def score_pairs(self, pairs):
                ledger.cancelled.set()
                return [0.0]
        with self.assertRaises(QueryError) as stopped:
            self.run_rank(ledger=ledger, factory=lambda _: CancelAfterBatch())
        self.assertEqual(stopped.exception.code, 'CANCELLED')
        self.assertEqual(ledger.snapshot()['rerank_items'], 1)
        self.assertEqual(sum(ledger.held.values()), 0)

    def test_invalid_scores_cannot_replace_rrf_and_attempt_is_charged(self):
        class Invalid(Provider):
            def score_pairs(self, pairs):
                return [float('nan')] * len(pairs)
        ledger = self.ledger()
        result = self.run_rank(ledger=ledger, factory=lambda _: Invalid())
        self.assertEqual([row['key'] for row in result['items']], ['0', '1', '2'])
        self.assertEqual(ledger.snapshot()['rerank_items'], 3)
        self.assertEqual(result['diagnostics']['status'], 'fallback')

    def test_full_read_unions_new_contributors_with_prior_condition_evidence(self):
        """A partial later full packet must not erase dependencies used for reranking conditions."""
        scope = Scope(None, None, None, None, None, None, None, False, (), (), None, None)
        request = QueryRequest(DefinitionRef('full', '1'), 'query', (), scope, scope, 'exploration',
            AssociationOptions('off', 'existing-relations', '1', 0, 0.0, None), DEFAULT_BUDGET,
            'current', 1, 'reject', (), '')
        candidate = FixedRef('record', 'REC-current', 1, 'a' * 64, None)
        prior_condition = FixedRef('record', 'REC-condition-parent', 1, 'b' * 64, None)
        shared = FixedRef('record', 'REC-shared', 1, 'c' * 64, None)
        later_full = FixedRef('record', 'REC-later-full', 1, 'd' * 64, None)
        reader = object.__new__(Reading)
        reader.state = lambda session, *, query: object()
        reader.packet = lambda state, refs, definition: (
            {'contributors': [asdict(shared), asdict(later_full)], 'complete': False}, {candidate.id: 'fixed-link'})
        session = {'candidates': {'RC-test': {'ref': asdict(candidate), 'scope': asdict(scope),
                    'contributors': [asdict(prior_condition), asdict(shared)], 'link': 'old-link',
                    'full_delivered': False}}}
        result = reader.read(session, {'candidate_ids': ['RC-test']}, SimpleNamespace(request=request))
        self.assertEqual(result['gaps'], ['RC-test完整阅读存在缺口，不能提交已完整阅读笔记'])
        contributors = session['candidates']['RC-test']['contributors']
        self.assertEqual({(row['id'], row['sha256']) for row in contributors}, {
            (prior_condition.id, prior_condition.sha256), (shared.id, shared.sha256),
            (later_full.id, later_full.sha256)})


if __name__ == '__main__':
    unittest.main()
