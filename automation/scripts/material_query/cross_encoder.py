"""窄的离线 ONNX Cross-encoder 边界；不下载、不执行模型仓库 Python。

缓存只在本进程复用模型会话，键包含工作区、清单哈希和全部文件状态。
每次加载先核对文件状态；发生变更时重新校验 SHA-256，不能复用旧会话。
调用方负责上下文组装和预算；这里计量真实 token 并拒绝隐式截断。
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from pathlib import Path


class ProviderUnavailable(RuntimeError):
    """模型/配置不就绪，调用者必须公开降级原因。"""


_CACHE: dict[tuple, 'OnnxCrossEncoder'] = {}
_LOCK = threading.RLock()


def _inside(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or '..' in candidate.parts:
        raise ProviderUnavailable('重排路径必须位于工作区内')
    result = (root / candidate).resolve()
    if not result.is_relative_to(root):
        raise ProviderUnavailable('重排路径越出工作区（包括链接）')
    return result


class OnnxCrossEncoder:
    """CPU 单 logit 序列分类模型，分数不是校准的正确概率。"""

    def __init__(self, model_dir: Path, manifest: dict, digest: str, max_length: int):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.max_length = max_length
        self.batch_size = 16
        self.identity = {'provider': 'onnx-cross-encoder', 'model': manifest['model'],
                         'revision': manifest.get('revision', ''), 'manifest_sha256': digest,
                         'max_length': max_length, 'batch_size': self.batch_size,
                         'implementation': 'onnx-pair-batch-v1'}
        self._tokenizer = Tokenizer.from_file(str(model_dir / 'tokenizer.json'))
        # 仓库 tokenizer 可能预设截断/补齐；统一禁用，避免计量低估。
        self._tokenizer.no_truncation()
        self._tokenizer.no_padding()
        configuration = json.loads((model_dir / 'config.json').read_text(encoding='utf-8'))
        self._pad_token_id = configuration['pad_token_id']
        if type(self._pad_token_id) is not int or self._pad_token_id < 0:
            raise ProviderUnavailable('模型缺合法 pad_token_id')
        self._session = ort.InferenceSession(str(model_dir / manifest['onnx_file']),
                                             providers=['CPUExecutionProvider'])
        self._inputs = {item.name for item in self._session.get_inputs()}
        if not {'input_ids', 'attention_mask'} <= self._inputs or self._inputs - {
                'input_ids', 'attention_mask', 'token_type_ids'}:
            raise ProviderUnavailable('不支持的重排 ONNX 输入契约')

    def count_tokens(self, question: str, text: str) -> int:
        """含 pair 分隔符和 special tokens；即使超长也返回完整长度。"""
        return len(self._tokenizer.encode(question, text).ids)

    def calls_for_pairs(self, count: int) -> int:
        """真实 ONNX run 次数，供上层预约模型调用预算。"""
        return (count + self.batch_size - 1) // self.batch_size

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        import numpy as np
        encodings = [self._tokenizer.encode(q, text) for q, text in pairs]
        if any(len(item.ids) > self.max_length for item in encodings):
            raise ValueError('Cross-encoder 输入超过 max_length；未执行截断或推理')
        scores = []
        # 每批至多16对；右侧补齐遵循模型pad id且mask=0，不隐式截断。
        for offset in range(0, len(encodings), self.batch_size):
            batch = encodings[offset:offset + self.batch_size]
            width = max(len(item.ids) for item in batch)
            arrays = {'input_ids': [], 'attention_mask': [], 'token_type_ids': []}
            for item in batch:
                padding = width - len(item.ids)
                arrays['input_ids'].append(item.ids + [self._pad_token_id] * padding)
                arrays['attention_mask'].append(item.attention_mask + [0] * padding)
                arrays['token_type_ids'].append(item.type_ids + [0] * padding)
            values = self._session.run(None, {
                name: np.asarray(arrays[name], dtype=np.int64) for name in self._inputs})
            logits = np.asarray(values[0]).reshape(-1)
            if logits.size != len(batch) or any(not math.isfinite(float(x)) for x in logits):
                raise ValueError('Cross-encoder 必须每对输出单个有限 logit')
            scores.extend(float(x) for x in logits)
        return scores


def load_provider(root: Path) -> OnnxCrossEncoder:
    """仅从本机配置加载；缺配置/损坏文件均抛明确异常，不模拟成功。"""
    root = Path(root).resolve()
    try:
        config_path = root / 'retrieval/config.json'
        config = json.loads(config_path.read_text(encoding='utf-8-sig')) if config_path.exists() else {}
        settings = config.get('reranker')
        if settings is None and (root / 'services/reranker/model-manifest.json').is_file():
            settings = {'provider': 'onnx-cross-encoder', 'path': 'services/reranker/model',
                        'manifest': 'services/reranker/model-manifest.json'}
        if not isinstance(settings, dict) or settings.get('provider') != 'onnx-cross-encoder':
            raise ProviderUnavailable('未配置本地 onnx-cross-encoder 重排模型')
        model_dir = _inside(root, settings['path'])
        manifest_path = _inside(root, settings['manifest'])
        raw = manifest_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        manifest = json.loads(raw)
        files = manifest['files']
        required = {'tokenizer.json', 'config.json', manifest['onnx_file']}
        if not isinstance(files, dict) or not required <= files.keys():
            raise ProviderUnavailable('重排模型清单缺必要文件')
        # 标准发行使用单文件 ONNX；逐项校验清单文件，不能加载远程资源。
        paths = {name: _inside(model_dir, name) for name in files}
        states = tuple((name, path.stat().st_size, path.stat().st_mtime_ns,
                        path.stat().st_ctime_ns) for name, path in sorted(paths.items()))
        length = settings.get('max_length', manifest.get('max_length', 512))
        if type(length) is not int or not 1 <= length <= manifest.get('max_length', 512):
            raise ProviderUnavailable('重排 max_length 超出模型契约')
        key = (str(root), str(model_dir), digest, length, states)
        with _LOCK:
            if key in _CACHE:
                return _CACHE[key]
            for name, path in paths.items():
                with path.open('rb') as stream:
                    actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                if actual != files[name]:
                    raise ProviderUnavailable(f'重排模型哈希不匹配：{name}')
            provider = OnnxCrossEncoder(model_dir, manifest, digest, length)
            # 不跨模型版本累积大模型；仅保留最近一次成功加载。
            _CACHE.clear()
            _CACHE[key] = provider
            return provider
    except ProviderUnavailable:
        raise
    except Exception as exc:
        raise ProviderUnavailable(f'重排配置或本地模型不可用：{exc}') from exc
