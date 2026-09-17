"""Owner discovery screening is deterministic and never claims full coverage."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from material_query import owner_screening
from material_query.reading_owner import assess_owners
from material_query.reading_strategy import accepted_sources
from material_query.validation import QueryError


def hit(pid, text, *, channel='lexical', record='MEM-A', locator=None, protected=False):
    return {
        'projection_id': pid,
        'text': text,
        'source_level': 'L3',
        'channels': [channel],
        'locator': locator,
        'refs': [{'kind': 'record', 'id': record, 'revision': 1,
                  'sha256': (pid[-1].lower() if pid[-1].isalnum() else 'a') * 64, 'locator': locator}],
        'matched_protected_terms': ['X200'] if protected else [],
        'relevance_score': 1.0,
    }


class OwnerScreeningTests(unittest.TestCase):
    def test_core_then_complementary_route_record_and_protected_window(self):
        candidate = {'owner_id': 'RES-A', 'title': 'Owner A', 'hits': [
            hit('P-A', 'core answer', channel='lexical'),
            hit('P-B', 'dense mechanism', channel='dense', record='MEM-B'),
            hit('P-C', 'X200 fails below 0.5 mV', record='MEM-C', protected=True),
            hit('P-D', 'nearly duplicate core answer', channel='lexical'),
            hit('P-E', 'fourth distinct location', channel='identity', record='MEM-E'),
        ]}
        packet = owner_screening.build(candidate, {'regular_windows': 3, 'max_windows': 4,
                                                   'batch_owners': 10})
        self.assertEqual(packet['owner_id'], 'RES-A')
        self.assertEqual(len(packet['windows']), 3)
        self.assertEqual({window['projection_id'] for window in packet['windows']}, {'P-A', 'P-B', 'P-C'})
        self.assertFalse(packet['coverage']['complete'])
        self.assertEqual(len(packet['packet_digest']), 64)

    def test_exact_duplicate_text_is_merged_but_provenance_is_preserved(self):
        first = hit('P-A', 'same text')
        second = hit('P-B', 'same text', channel='dense', record='MEM-B')
        packet = owner_screening.build({'owner_id': 'RES-A', 'hits': [first, second]},
                                       {'regular_windows': 3, 'max_windows': 4, 'batch_owners': 10})
        self.assertEqual(len(packet['windows']), 1)
        self.assertEqual({ref['id'] for ref in packet['windows'][0]['refs']}, {'MEM-A', 'MEM-B'})
        self.assertEqual(set(packet['windows'][0]['channels']), {'lexical', 'dense'})

    def test_single_complete_l4_can_report_complete(self):
        only = hit('P-A', 'short complete experience')
        only.update(source_level='L4', complete_source=True)
        packet = owner_screening.build({'owner_id': 'RES-A', 'hits': [only]},
                                       {'regular_windows': 3, 'max_windows': 4, 'batch_owners': 10})
        self.assertTrue(packet['coverage']['complete'])

    def test_no_relevant_owner_offers_but_does_not_run_fulltext_compensation(self):
        session = {'strategy': 'standard', 'owner_packets': {'RES-A': {'packet_digest': 'a' * 64}},
                   'owner_progress': {}}
        result = assess_owners(session, {'assessments': [{'owner_id': 'RES-A', 'status': 'uncertain',
            'reason': '筛选面不足', 'packet_digest': 'a' * 64}]})
        self.assertTrue(result['fulltext_compensation_available'])
        self.assertNotIn('fulltext_compensation', result.get('retrieval_source', ''))
        self.assertEqual(session['owner_progress']['RES-A']['judgment'], 'uncertain')

    def test_quick_relevant_owner_does_not_direct_to_full_read(self):
        ref = {'kind': 'record', 'id': 'MEM-A', 'revision': 1, 'sha256': 'b' * 64, 'locator': 'record'}
        session = {'strategy': 'quick', 'owner_packets': {'RES-A': {'packet_digest': 'a' * 64}},
                   'owner_progress': {}, 'candidates': {'RC-A': {'owner_id': 'RES-A', 'stale': False,
                       'quick_sources': [ref]}}}
        result = assess_owners(session, {'assessments': [{'owner_id': 'RES-A', 'status': 'relevant',
            'reason': '片段足够形成快速笔记', 'packet_digest': 'a' * 64}]})
        self.assertEqual(result['next_action'], 'synthesize')
        self.assertEqual(accepted_sources(session, owner_id='RES-A'), [ref])


if __name__ == '__main__':
    unittest.main()
