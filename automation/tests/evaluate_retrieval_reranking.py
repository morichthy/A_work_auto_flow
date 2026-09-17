"""冻结候选池的真实模型消融；只比较排序，不把候选覆盖当业务召回。

默认仅运行 development；holdout 只有显式 --phase final 才能执行。
标签仅进入指标计算，condition_status 永远不输入模型/条件模块。
退出码：0 完成，2 配置/模型/输入/执行失败；不静默换模型或填造分数。
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_retrieval_reranking_baseline import ROOT, load_fixture, rrf_ranking
from material_query.budget import DEFAULT_BUDGET, Ledger
from material_query.cross_encoder import load_provider
from material_query.reranking import rank, settings
from memory.evaluation import ranking_metrics


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def explicit_conditions(mapping):
    """仅转换冻结查询的显式键值；不猜字段别名、不解析候选生成特征。

    例如 temperature '< -20 °C' 转为数值条件；字段仍是 temperature，
    不擅自把正文中的任意温度当成它。自然语言、多个词或缺字段可 unknown。
    """
    result = []
    operators = {'<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge', '=': 'eq', '': 'eq'}
    for field, value in mapping.items():
        item = {'id': field, 'field': field, 'kind': 'literal', 'operator': 'eq', 'expected': value}
        match = re.fullmatch(r'\s*(<=|>=|<|>|=)?\s*([+-]?\d+(?:\.\d+)?)\s*([^\s\d]+)?\s*', value)
        if match:
            item.update(kind='numeric', operator=operators[match[1] or ''], expected=float(match[2]))
            if match[3]:
                item['unit'] = match[3]
        result.append(item)
    return result


def evaluate(split='development', phase='development'):
    if split == 'holdout' and phase != 'final':
        raise ValueError('holdout 仅允许 --phase final；不用于开发调参')
    fixture, fixture_hash = load_fixture()
    # 在循环前筛选；开发运行不打印、评分或分析留出题。
    queries = [q for q in fixture['queries'] if q['split'] == split]
    load_start = time.perf_counter()
    provider = load_provider(ROOT)
    cold_ms = (time.perf_counter() - load_start) * 1000
    sources = [Path(__file__), ROOT / 'automation/scripts/material_query/cross_encoder.py',
               ROOT / 'automation/scripts/material_query/reranking.py',
               ROOT / 'automation/scripts/material_query/conditions.py',
               ROOT / 'automation/scripts/material_query/query_plan.py']
    report = {'fixture_sha256': fixture_hash, 'fixture_version': fixture['fixture_version'],
              'split': split, 'phase': phase, 'k': 6, 'model': provider.identity,
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              'cold_model_load_ms': cold_ms, 'rows': [], 'aggregate': {},
              'limitations': ['合成固定候选池；不含线上召回、权限回读及上下文组装耗时。',
                             '短输入是有意的消融输入，并不声称它具有完整上下文。',
                             '条件只使用查询显式字段；未知不转成满足或冲突。',
                             '无答案误报仅测是否返回候选；没有训练分数阈值，空候选题不能验证拒答能力。',
                             '冷耗时是进程首次加载，操作系统文件缓存未清空；暖运行重复一次并如实计费。']}
    for query in queries:
        start = time.perf_counter()
        base = rrf_ranking(query, fixture['query_routes'])
        base_ms = (time.perf_counter() - start) * 1000
        ids = [row['canonical_id'] for row in base]
        labels = {row['canonical_id']: row['grade'] for row in query['relevant']}
        result = {'query_id': query['query_id'], 'question': query['query'],
                  'query_sha256': digest(query), 'candidate_ids': ids,
                  'candidate_coverage': ranking_metrics(labels, ids, k=max(1, len(ids))), 'variants': {}}
        result['variants']['rrf'] = {'ranking': ids, 'metrics': ranking_metrics(labels, ids, k=6),
                                     'elapsed_ms': base_ms, 'model_tokens': 0,
                                     'no_answer_false_positive': bool(ids) if not labels else None}
        for name, context, with_conditions in [('ce_short', 'short_context', False),
                                                ('ce_context', 'full_context', False),
                                                ('ce_context_conditions', 'full_context', True)]:
            prepared = []
            for cid in ids:
                doc = query['documents'][cid]
                text = doc['title'] + '\n' + doc[context]
                prepared.append({'canonical_id': cid, 'text': text, 'complete': True,
                                 'evidence_parts': [{'text': doc[context], 'role': 'direct',
                                                     'ref': {'fixture_sha256': fixture_hash, 'canonical_id': cid}}]})
            options = settings({'mode': 'required', 'candidate_limit': 30,
                                'conditions': explicit_conditions(query['conditions']) if with_conditions else []})
            attempts = []
            for repeat in range(2):
                # 消融预算独立，完整报告真实token；不是产品默认预算或性能承诺。
                ledger = Ledger(replace(DEFAULT_BUDGET, model_calls=100, model_tokens=100000,
                                        model_input_tokens=100000, rerank_items=100))
                with ledger.active():
                    output = rank(ROOT, query['query'], prepared, options, ledger)
                ranked = [row['canonical_id'] for row in output['items']]
                attempts.append({'repeat': repeat, 'ranking': ranked, 'diagnostics': output['diagnostics'],
                                 'cost': ledger.snapshot(), 'gaps': output['gaps'],
                                 'scores_and_conditions': {row['canonical_id']: row['ranking'] for row in output['items']}})
            result['variants'][name] = {'input_sha256': digest(prepared), 'inputs': prepared,
                'conditions': options['conditions'], 'ranking': attempts[0]['ranking'],
                'metrics': ranking_metrics(labels, attempts[0]['ranking'], k=6),
                'model_tokens': sum(a['cost']['model_tokens'] for a in attempts),
                'warm_repeat_stable': attempts[0]['ranking'] == attempts[1]['ranking'],
                'no_answer_false_positive': bool(attempts[0]['ranking']) if not labels else None,
                'attempts': attempts}
        report['rows'].append(result)
    for variant in ('rrf', 'ce_short', 'ce_context', 'ce_context_conditions'):
        variants = [r['variants'][variant] for r in report['rows']]
        scored = [v for v in variants if v['metrics']['recall'] is not None]
        no_answer = [v['no_answer_false_positive'] for v in variants if v['no_answer_false_positive'] is not None]
        statuses = Counter(c['status'] for v in variants for a in v.get('attempts', [])[:1]
                           for row in a['scores_and_conditions'].values() for c in row['conditions'])
        report['aggregate'][variant] = {'scored_queries': len(scored),
            'recall_at_6': sum(v['metrics']['recall'] for v in scored) / len(scored) if scored else None,
            'ndcg_at_6': sum(v['metrics']['ndcg'] for v in scored) / len(scored) if scored else None,
            'no_answer_count': len(no_answer), 'no_answer_false_positives': sum(no_answer),
            'total_model_tokens_including_repeat': sum(v['model_tokens'] for v in variants),
            'condition_status_counts': dict(statuses)}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=('development', 'holdout'), default='development')
    parser.add_argument('--phase', choices=('development', 'final'), default='development')
    parser.add_argument('--output', type=Path, required=True, help='JSON结果路径；父目录须存在，不覆盖已有结果。')
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('输出文件已存在；保留原实验，请选新路径')
        report = evaluate(args.split, args.phase)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps(report['aggregate'], ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f'消融实验失败：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
