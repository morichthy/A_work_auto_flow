"""交接组包的语义边界：保留必要细节，已解决历史缺口不永久污染当前视图。"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from material_query.reading_delegation import handoff_value, serialized_size
from material_query.reading_snapshot import notes_value


class ReadingHandoffViewTests(unittest.TestCase):
    def session(self):
        # 仅测试纯装包。权限/固定来源真实性在真实Coordinator集成测试中核验。
        return {'session_id': 'RS-synthetic', 'revision': 5, 'phase': 'finish',
                'rounds': [{'gaps': [], 'lanes': [{'status': 'ok', 'warnings': [], 'has_more': False,
                    'routes': [{'query_source': 'original:lexical', 'status': 'ok', 'warnings': []}]}]}],
                'decisions': [], 'candidates': {'RC-a': {'title': '合成单位转换', 'link': '/synthetic/fixed.json',
                    'ref': {'id': 'MEM-a', 'revision': 2, 'sha256': 'a' * 64}, 'packet_complete': True}},
                'notes': {'RC-a': {'summary': '公式保留单位和输入边界。',
                    'connection': {'kind': 'direct', 'explanation': '用于指定温标换算', 'chain': ['先确认摄氏输入']},
                    'details': [{'text': '$T_K=T_C+273.15$；$T_C$单位°C，$T_K$单位K。',
                                 'reason': '不得截断常数或丢单位', 'block_ids': ['equation']}],
                    'uncertainties': ['该合成关系不能验证传感器校准精度']}}}

    def test_full_note_preserves_formula_uncertainty_and_fixed_hash_or_is_wholly_omitted(self):
        session = self.session()
        full = handoff_value(session)
        self.assertTrue(full['complete'])
        self.assertIn('$T_K=T_C+273.15$', full['context_markdown'])
        self.assertIn('单位°C', full['context_markdown'])
        self.assertIn('a' * 64, full['context_markdown'])
        self.assertIn('不能验证传感器校准精度', full['context_markdown'])
        limited = handoff_value(session, max_chars=serialized_size(full) - 1)
        self.assertEqual(limited['notes_count'], 0)
        self.assertEqual(limited['omitted_note_count'], 1)
        self.assertFalse(limited['complete'])
        self.assertNotIn('273.15', limited['context_markdown'])
        self.assertLessEqual(serialized_size(limited), serialized_size(full) - 1)

    def test_resolved_history_does_not_hide_current_success_but_latest_unknown_stays_partial(self):
        session = self.session()
        # 历史失败保留在RS；续页/补查后当前轮无缺口，不把历史事件当现存失败。
        session['rounds'].insert(0, {'lanes': [{'status': 'partial', 'has_more': True}]})
        self.assertTrue(handoff_value(session)['complete'])
        unknown = deepcopy(session)
        del unknown['rounds'][-1]['gaps']
        partial = handoff_value(unknown)
        self.assertFalse(partial['complete'])
        self.assertIn('旧轮诊断不全', '；'.join(partial['gaps']))
        session['rounds'][-1]['lanes'][0]['routes'][0].update(status='partial', warnings=['无模型'])
        session['rounds'][-1]['lanes'][0]['routes'][0]['query_source'] = 'original:dense'
        self.assertIn('向量缺口', '；'.join(handoff_value(session)['gaps']))

    def test_notes_display_counts_fixed_refs_inside_total_bound_and_keeps_stale_out(self):
        session = self.session()
        session.update(goal='检查温标关系', conditions=['保留单位'])
        full = notes_value(session)
        bounded = notes_value(session, max_chars=serialized_size(full) - 1)
        self.assertLessEqual(serialized_size(bounded), serialized_size(full) - 1)
        self.assertEqual(bounded['notes_count'], 0)
        self.assertEqual(bounded['candidates'], [])
        session['candidates']['RC-a']['stale'] = True
        stale = notes_value(session)
        self.assertEqual(stale['candidates'], [])
        self.assertNotIn('273.15', stale['context_markdown'])
        self.assertIn('来源已变', '；'.join(stale['gaps']))
        self.assertNotIn('phase=', full['context_markdown'])
        self.assertIn('### 阅读理解', full['context_markdown'])


if __name__ == '__main__':
    unittest.main()
