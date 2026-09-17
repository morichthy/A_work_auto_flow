"""Real offline hybrid recall over synthetic, independently labelled topics.

These small cross-language checks exercise the installed encoder and Qdrant, not
scientific validity or a representative production benchmark. No downloads.
"""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

import test_memory_documents_v3 as document_fixture
from test_memory_associations_real import install_model_links
from memory import index
from memory.errors import MemoryError
from material_query.budget import DEFAULT_BUDGET
from material_query.contracts import AssociationOptions, DefinitionRef, QueryRequest, Scope
from material_query.coordinator import Coordinator
from material_query.wire import json_value


class MaterialDenseRealTests(unittest.TestCase):
    setUp = document_fixture.DocumentV3Tests.setUp
    put = document_fixture.DocumentV3Tests.put
    operation = document_fixture.DocumentV3Tests.operation
    request = document_fixture.DocumentV3Tests.request
    save = document_fixture.DocumentV3Tests.save
    create = document_fixture.DocumentV3Tests.create
    revise = document_fixture.DocumentV3Tests.revise

    def test_real_hybrid_body_recall_metering_filter_and_stale_vectors(self):
        topics = [
            ('电池充电保护', '锂电池过充会加速老化，应限制充电截止电压，避免长时间保持满电。',
             'How can I prevent battery degradation caused by excessive charging?'),
            ('数据库灾难恢复', '数据库定期备份并验证恢复，磁盘损坏后可从备份恢复业务数据。',
             'How do backups help recover database records after a disk failure?'),
            ('光学镜片清洁', '镜头灰尘会降低图像清晰度，用气吹清除灰尘，避免直接擦伤镀膜。',
             'How should I remove dust from a camera lens without scratching it?'),
            ('灌溉节水', '土壤湿度下降时按需滴灌，减少蒸发损失，避免根部长期积水。',
             'How can soil moisture measurements reduce water waste in irrigation?'),
        ]
        records = []
        for title, body, _query in topics:
            payload = document_fixture.unit_payload()
            payload['blocks'][1]['markdown'] = body
            records.append(self.create('detail', payload, title=title, discovery='workspace_summary'))
        install_model_links(self.root)
        synced = index.sync_owner(self.root, 'RES-R', vector='required')
        self.assertEqual(synced['index_status'], 'indexed', synced)
        app = Coordinator(self.root)
        self.addCleanup(app.executor.shutdown)
        scope = Scope(('RES-R',), None, None, None, None, None, None, False, (), (), None, None)
        query = QueryRequest(DefinitionRef('full', '1'), topics[0][2], (), scope, scope, 'exploration',
            AssociationOptions('off', 'existing-relations', '1', 2, .15, None), DEFAULT_BUDGET,
            'current', 3, 'reject', (), '', channels=('lexical', 'dense'),
            ranking_strategy='rrf', content_source='technical')
        metrics = []
        for record, (_title, _body, question) in zip(records, topics):
            lexical = app.search(json_value(replace(query, question=question, channels=('lexical',))))
            result = app.search(json_value(replace(query, question=question)))
            self.assertEqual(result['status'], 'ok', result)
            candidates = result['value']['candidates']
            ids = [c['refs'][0]['id'] for c in candidates]
            self.assertEqual(ids[0], record['record_id'], result)
            self.assertEqual(result['consumed']['model_calls'], 1)
            self.assertGreater(result['consumed']['model_input_tokens'], 0)
            hit = next(h for h in candidates[0]['hits'] if h['channel'] == 'dense')
            self.assertIsInstance(hit['raw_score'], float)
            self.assertEqual(hit['representation_refs'][0]['sha256'], record['record_hash'])
            metrics.append({'question': question, 'top1_correct': ids[0] == record['record_id'],
                            'recall_at_3': record['record_id'] in ids,
                            'precision_at_3': sum(rid == record['record_id'] for rid in ids) / len(ids),
                            'other_topic_candidates': sum(rid != record['record_id'] for rid in ids),
                            'lexical_recall': any(c['refs'][0]['id'] == record['record_id']
                                                  for c in lexical['value']['candidates']),
                            'consumed': result['consumed']})
        print('FOUNDATION_REAL_METRICS=' + json.dumps(metrics, ensure_ascii=False))
        # No budget means no inference; lexical remains available and explicit.
        no_model = app.search(json_value(replace(query, question='电池',
            budget=replace(DEFAULT_BUDGET, model_calls=0))))
        self.assertEqual(no_model['status'], 'partial', no_model)
        self.assertEqual(no_model['consumed']['model_calls'], 0)
        self.assertTrue(no_model['value']['candidates'])
        oversized = app.search(json_value(replace(query, question='battery ' * 600, channels=('dense',))))
        self.assertEqual(oversized['status'], 'partial', oversized)
        self.assertEqual(oversized['consumed']['model_calls'], 0)
        # Content-kind filtering happens before the vector window.
        filtered = app.search(json_value(replace(query, content_source='process')))
        self.assertEqual(filtered['value']['candidates'], [], filtered)
        # Commit changes the FTS signature; the previous vector must not vote.
        changed = deepcopy(records[0]['payload'])
        changed['blocks'][1]['markdown'] = '新的合成内容 zqxreplacement'
        with patch.object(index, 'MemoryVectorBackend', side_effect=MemoryError('LOCKED', 'synthetic writer lock')):
            self.revise(records[0], payload=changed)
        stale = app.search(json_value(replace(query, channels=('dense',))))
        self.assertEqual(stale['status'], 'partial', stale)
        self.assertNotIn(records[0]['record_id'], [c['refs'][0]['id'] for c in stale['value']['candidates']])
        # Shrinking access must hide cached vector identities and body text even
        # when no reindex occurs after the native authorization change.
        self.put('research/topic/research.json', {'research_id': 'RES-R', 'title': 'SYNTHETIC ONLY',
                 'status': 'active', 'claims': [], 'dependencies': [], 'sensitivity': 'restricted'})
        denied = app.search(json_value(query))
        self.assertNotIn('电池充电保护', json.dumps(denied, ensure_ascii=False))
        self.assertFalse(denied.get('value') and denied['value']['candidates'])


if __name__ == '__main__':
    unittest.main()
