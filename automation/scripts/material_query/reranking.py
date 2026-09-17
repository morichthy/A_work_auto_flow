"""有界候选上的配对评分和显式条件特征；不读取文件或改变召回范围。

调用者先通过 Reader/Assembler 固定回读正文，再传入本模块。模型是外围
提供器，条件和排序不依赖其具体运行库。任何缺失输入、模型或预算均保留
原候选；不将未评分项机械放到最后，也不把排序分数写成知识复核状态。
"""
from copy import deepcopy
import math
import time

from .conditions import validate_conditions, evaluate_conditions
from .validation import QueryError


def settings(raw=None):
    """请求只选择固定策略和有界参数；禁止客户端指定模型文件或代码。"""
    raw = {'mode': 'off'} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - {'mode', 'candidate_limit', 'conditions'}:
        raise QueryError('VALIDATION', '重排只接受mode、candidate_limit、conditions')
    mode, limit = raw.get('mode', 'auto'), raw.get('candidate_limit', 30)
    if mode not in ('off', 'auto', 'required') or type(limit) is not int or not 1 <= limit <= 100:
        raise QueryError('VALIDATION', '重排模式无效或候选窗不在1..100')
    try:
        conditions = validate_conditions(raw.get('conditions', []))
    except ValueError as exc:
        raise QueryError('VALIDATION', str(exc)) from exc
    return {'mode': mode, 'candidate_limit': limit, 'conditions': conditions}


def load_provider(root):
    # 延迟导入：off、旧会话和无模型安装不要求推理库存在。
    from .cross_encoder import load_provider as load
    return load(root)


def rank(root, question, prepared, options, ledger, *, provider_factory=None, expected_model=None):
    """保持候选集合不变，在完整有界输入上批量重排。

    排序按明确条件冲突分组，同组以CE得分排序；未知与满足不人为分成
    两档。任何一项不能评分时，整窗使用原RRF顺序（仍可解释条件冲突），
    避免因长文本/缺模型而把未评分材料全部压低。原始名次始终是稳定次序。
    """
    started = time.perf_counter()
    rows = deepcopy(prepared)
    diagnostics = {'version': 'context-conditions-ce-v1', 'mode': options['mode'],
                   'status': 'off', 'candidate_count': len(rows), 'scored_count': 0,
                   'model': deepcopy(expected_model), 'condition_ms': 0.0, 'model_load_ms': 0.0, 'inference_ms': 0.0}
    gaps = []
    for position, row in enumerate(rows, 1):
        row['ranking'] = {'original_rank': position, 'final_rank': position,
                          'ce_score': None, 'conditions': [], 'issues': []}
    if options['mode'] == 'off' or not rows:
        diagnostics['total_ms'] = (time.perf_counter() - started) * 1000
        return {'items': rows, 'diagnostics': diagnostics, 'gaps': gaps}

    condition_start = time.perf_counter()
    for row in rows:
        ledger.checkpoint()
        # 不完整上下文可能遗漏否定或限定；不能用局部片段证明适用条件。
        evidence = row.get('evidence_parts', []) if row.get('complete') else []
        row['ranking']['conditions'] = evaluate_conditions(options['conditions'], evidence)
        if not row.get('complete'):
            row['ranking']['issues'].append('incomplete_context')
    diagnostics['condition_ms'] = (time.perf_counter() - condition_start) * 1000

    def fallback(message):
        if options['mode'] == 'required':
            raise QueryError('UNSUPPORTED', message)
        diagnostics['status'] = 'fallback'
        gaps.append(message + '；保留候选及原RRF相对顺序，显式条件冲突仍单列')

    provider, tokens = None, []
    load_start = time.perf_counter()
    try:
        provider = (provider_factory or load_provider)(root)
        diagnostics['model'] = deepcopy(provider.identity)
        if expected_model is not None and provider.identity != expected_model:
            # 原发现轮的模型身份不可被本页失败尝试替换；否则第三页会接受新模型。
            diagnostics['attempted_model'] = deepcopy(provider.identity)
            diagnostics['model'] = deepcopy(expected_model)
            fallback('续页模型身份与冻结轮次不一致')
            provider = None
    except QueryError:
        raise
    except Exception:
        fallback('离线Cross-encoder不可用（缺模型、配置或指纹异常）')
    diagnostics['model_load_ms'] = (time.perf_counter() - load_start) * 1000
    ledger.checkpoint()
    if provider is not None:
        try:
            for row in rows:
                count = provider.count_tokens(question, row['text'])
                if type(count) is not int or count < 1:
                    raise ValueError('invalid token count')
                tokens.append(count)
                row['ranking']['input_tokens'] = count
                if count > provider.max_length:
                    row['ranking']['issues'].append('input_too_long')
            if any(row['ranking']['issues'] for row in rows):
                fallback('重排正文缺失或超过模型token窗口，未静默截断')
                provider = None
        except QueryError:
            raise
        except Exception:
            fallback('重排输入分词失败')
            provider = None

    if provider is not None:
        calls = provider.calls_for_pairs(len(rows)) if hasattr(provider, 'calls_for_pairs') else 1
        if type(calls) is not int or calls < 1:
            raise QueryError('UNSUPPORTED', '重排提供器没有有效模型调用计量')
        costs = {'model_calls': calls, 'model_tokens': sum(tokens),
                 'model_input_tokens': sum(tokens), 'rerank_items': len(rows)}
        if any(ledger.remaining(key) < value for key, value in costs.items()):
            fallback('累计预算不足以完成本窗重排，未调用模型')
        else:
            # 在实际调用前原子预约并扣费，失败推理也有成本；结算不重复扣费。
            reservation = ledger.reserve(costs)
            spent = {}
            inference_start = time.perf_counter()
            try:
                with ledger.provider(reservation):
                    scores = []
                    batch_size = getattr(provider, 'batch_size', len(rows))
                    if type(batch_size) is not int or batch_size < 1:
                        raise ValueError('invalid batch size')
                    # 分批实际扣费并检查取消；第二批失败不把从未调用的后续批计费。
                    for offset in range(0, len(rows), batch_size):
                        batch = rows[offset:offset + batch_size]
                        batch_tokens = sum(tokens[offset:offset + batch_size])
                        batch_cost = {'model_calls': 1, 'model_tokens': batch_tokens,
                                      'model_input_tokens': batch_tokens, 'rerank_items': len(batch)}
                        for key, value in batch_cost.items():
                            ledger.charge(key, value)
                            spent[key] = spent.get(key, 0) + value
                        scores.extend(provider.score_pairs([(question, row['text']) for row in batch]))
                        ledger.checkpoint()
                    if len(scores) != len(rows) or any(isinstance(score, bool) or
                        not isinstance(score, (int, float)) or not math.isfinite(score) for score in scores):
                        raise ValueError('invalid model scores')
                    for row, score in zip(rows, scores):
                        row['ranking']['ce_score'] = float(score)
                    diagnostics.update(status='reranked', scored_count=len(scores))
            except QueryError:
                raise  # 取消/超时必须停止，不将它改成成功的降级。
            except Exception:
                fallback('Cross-encoder推理失败或返回非有限分数')
            finally:
                ledger.settle(reservation, spent)
                diagnostics['inference_ms'] = (time.perf_counter() - inference_start) * 1000

    def order(row):
        facts = row['ranking']
        conflict = any(c['status'] == 'conflict' for c in facts['conditions'])
        # CE仅在完整成功的候选窗内比较；原RRF顺序是稳定的最终tie-break。
        score = facts['ce_score'] if diagnostics['status'] == 'reranked' else 0.0
        return (conflict, -score, facts['original_rank'])

    rows.sort(key=order)
    for position, row in enumerate(rows, 1):
        row['ranking']['final_rank'] = position
    diagnostics['total_ms'] = (time.perf_counter() - started) * 1000
    return {'items': rows, 'diagnostics': diagnostics, 'gaps': gaps}
