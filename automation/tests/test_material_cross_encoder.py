"""离线重排边界：无模型、越界路径、完整性、真实计量与超长拒绝。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from material_query import cross_encoder as ce


class CrossEncoderTests(unittest.TestCase):
    def test_real_offline_model_smoke_and_length(self):
        root = Path(__file__).resolve().parents[2]
        if not (root / 'services/reranker/model-manifest.json').is_file():
            self.skipTest('未部署可选离线模型；不把接口测试当作模型验证')
        from unittest.mock import patch
        with patch('socket.socket.connect', side_effect=AssertionError('禁止联网')):
            provider = ce.load_provider(root)
            self.assertIs(provider, ce.load_provider(root))
            pairs = [('低温启动失败如何解决？', '低温条件下先预热电池可以改善启动性能。'),
                     ('低温启动失败如何解决？', '本章节讨论办公室打印机的纸张尺寸。')]
            scores = provider.score_pairs(pairs)
            self.assertEqual(len(scores), 2)
            self.assertGreater(scores[0], scores[1])
            single = [provider.score_pairs([pair])[0] for pair in pairs]
            # 动态INT8量化的范围随batch变化；不拿事后选定公差当质量保证。
            # 这里只要求两种执行都返回有限数且此固定smoke的相关性顺序保持。
            import math
            self.assertTrue(all(math.isfinite(value) for value in single))
            self.assertGreater(single[0], single[1])
            self.assertEqual(provider.calls_for_pairs(0), 0)
            self.assertEqual(provider.calls_for_pairs(17), 2)
            self.assertEqual(provider.identity['batch_size'], 16)
            long_text = '低温启动失败 ' * 1000
            self.assertGreater(provider.count_tokens('低温', long_text), provider.max_length)
            with self.assertRaisesRegex(ValueError, '截断'):
                provider.score_pairs([('低温', long_text)])

    def test_missing_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ce.ProviderUnavailable, '配置'):
                ce.load_provider(Path(folder))

    def test_path_cannot_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'retrieval').mkdir()
            (root / 'retrieval/config.json').write_text(json.dumps({'reranker': {
                'provider': 'onnx-cross-encoder', 'path': '../outside',
                'manifest': '../outside/manifest.json'}}), encoding='utf-8')
            with self.assertRaisesRegex(ce.ProviderUnavailable, '工作区'):
                ce.load_provider(root)

    def test_tampering_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'retrieval').mkdir()
            (root / 'model').mkdir()
            (root / 'model/tokenizer.json').write_text('changed')
            (root / 'manifest.json').write_text(json.dumps({'model': 'test',
                'files': {'tokenizer.json': '0' * 64}, 'onnx_file': 'model.onnx',
                'max_length': 512}), encoding='utf-8')
            (root / 'retrieval/config.json').write_text(json.dumps({'reranker': {
                'provider': 'onnx-cross-encoder', 'path': 'model',
                'manifest': 'manifest.json'}}), encoding='utf-8')
            with self.assertRaises(ce.ProviderUnavailable):
                ce.load_provider(root)


if __name__ == '__main__':
    unittest.main()
