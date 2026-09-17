"""真实阅读计时成果的分阶段维护；默认不执行任何阶段。

先由主 Agent 显式运行 baseline-only，实际阅读全文、影响与候选，再运行 apply。
示例：python update_latency_memory.py baseline-only
      python update_latency_memory.py apply --run-json FIRST/run.json
          --run-json SECOND/run.json --run-json THIRD/run.json --metrics metrics.json
          --review-note reviewed.md [--summary-key conclusion]

仅公共 memory API 可写规范记录。JSON 回执全部保存在本 Run 的
.run-captures/memory-closure，避开业务JSON扫描；不修改旧Run或产品代码。
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parents[1]
HERE = RUN / '.run-captures' / 'memory-closure'
OWNER = 'PRJ-ARCHITECTURE-EVOLUTION'
TARGETS = {
    'unit': ('MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b', 1),
    'section': ('MEM-50f66b7c-7953-5715-8b70-5ae7705176ab', 2),
    'document': ('MEM-bd121869-a0b9-59e3-af23-8e8675374a63', 2),
    'overview': ('MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155', 2),
}
BOUNDARY = ('本轮保留默认预算下失败的实际路径，以及另行放宽预算的诊断路径；'
            'failed Run是失败与成本证据，不冒充成功完成。测量包含实际记录的工具、'
            '后端和调用间隔范围；调用间隔不直接等于模型推理，profile与正式计时分列。'
            '没有实施性能优化；不能据单次诊断推断普遍加速、费用降低或业务正确率。'
            '此前主上下文字符减少结果继续仅作为其原场景历史证据，不覆写旧数字。')
CHANGE = '追加真实浮点材料阅读链路计时、默认预算失败和诊断边界，保留原委派及上下文减量历史。'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def archive(name, value):
    """先构造完整JSON再原子发布；既有不同内容不能被复跑静默覆盖。"""
    path = HERE / name
    if path.exists():
        if load(path) != value:
            raise RuntimeError('冻结回执已存在且内容不同：' + name)
        return
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    temporary = path.with_name('.pending-' + uuid.uuid4().hex)
    temporary.write_text(raw, encoding='utf-8')
    temporary.replace(path)


def invoke(service, action, request, label):
    """公开调用的异常/返回错误均保留，error:null不误判失败。"""
    from memory import api
    from memory.errors import MemoryError
    try:
        value = api.dispatch(service, action, request)
    except MemoryError as exc:
        archive(label + '-error-' + uuid.uuid4().hex + '.json', {'error': exc.as_dict()})
        raise
    if value.get('error'):
        archive(label + '-error-' + uuid.uuid4().hex + '.json', value)
        raise RuntimeError(value)
    return value


def owner(service, label):
    return invoke(service, 'inspect', {'owner_id': OWNER}, label)


def baseline(service):
    """只读基线；全Owner快照让主Agent检查候选，而非假定本轮四记录覆盖全部。"""
    if (HERE / 'baseline-manifest.json').exists():
        print('已有冻结基线；请阅读保存的全文、候选及impact，未执行任何提交。')
        return
    start = owner(service, 'baseline-owner')
    archive('baseline-owner.json', start)
    for key, (record_id, expected) in TARGETS.items():
        value = invoke(service, 'inspect', {'owner_id': OWNER, 'record_id': record_id}, key)
        if value['record']['revision'] != expected:
            raise RuntimeError('目标revision与委托基线不同，先实际审查：' + key)
        archive('baseline-' + key + '-record.json', value)
    request = {'owner_id': OWNER, 'document_id': TARGETS['document'][0],
               'revision': TARGETS['document'][1]}
    for action in ('document', 'document-impact'):
        archive('baseline-' + action + '-request.json', request)
        value = invoke(service, action, request, 'baseline-' + action)
        archive('baseline-' + action + '.json', value)
        if action == 'document' and not value['report']['complete']:
            raise RuntimeError('原文稿不完整，先补齐阅读，不能自动继续')
    # 全部L1/概览/文稿候选只列固定身份与标题；完整记录已在owner快照内。
    # 主Agent据当前任务和impact审查新增候选，脚本不以关键词过滤冒充完整审查。
    candidates = [{field: record.get(field) for field in
                   ('record_id', 'revision', 'record_hash', 'kind', 'level', 'title', 'updated_at')}
                  for record in start['records'].values()
                  if record.get('kind') in ('detail', 'overview', 'document', 'document_section')]
    archive('baseline-candidates.json', candidates)
    end = owner(service, 'baseline-owner-end')
    archive('baseline-owner-end.json', end)
    if end['head'] != start['head']:
        raise RuntimeError('基线读取期间HEAD改变，需独立重审，不能标已完成')
    names = ['baseline-owner.json', 'baseline-unit-record.json', 'baseline-section-record.json',
             'baseline-document-record.json', 'baseline-overview-record.json',
             'baseline-document.json', 'baseline-document-impact.json',
             'baseline-candidates.json']
    # 完整文稿回执与record inspect分别命名，二者均冻结，不能互相覆盖。
    manifest = {'head': start['head'], 'files': {
        name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in names}}
    archive('baseline-manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def edited(record):
    from memory import contracts
    result = {key: deepcopy(record[key]) for key in
              (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
    result['change_reason'] = CHANGE
    result['keywords'] = list(dict.fromkeys([*result['keywords'], 'reading-latency', '默认预算失败']))
    return result


def refs(*groups):
    result = []
    for group in groups:
        for ref in group:
            if ref not in result:
                result.append(deepcopy(ref))
    return result


def commit_batch(service, label, changes, expected_head):
    """请求schema=3；记录仍保持原v3/v4，不混淆请求版本与记录版本。

    保存成功预检后若进程中断，复跑同request_id直接commit，公开服务会先检查
    幂等回执再做CAS。避免对已提交请求再次预检而误报HEAD冲突。
    """
    from memory import contracts
    request_path = HERE / (label + '-request.json')
    if request_path.exists():
        request = load(request_path)
        if {op['record_id']: op['draft'] for op in request['operations']} != {
                TARGETS[key][0]: value for key, value in changes.items()}:
            raise RuntimeError('冻结请求与当前草案不一致：' + label)
    else:
        current = owner(service, label + '-head')
        archive(label + '-head-before.json', current)
        if current['head']['commit_id'] != expected_head:
            raise RuntimeError('Owner并发变化，停止提交并实际检查新材料')
        request = {'schema_version': 3, 'request_id': str(uuid.uuid4()),
                   'actor': {'kind': 'ai', 'id': 'codex-reading-latency'},
                   'owner_id': OWNER, 'expected_head': expected_head,
                   'operations': [{'op': 'put_record', 'record_id': TARGETS[key][0],
                                   'expected_revision': TARGETS[key][1], 'draft': value}
                                  for key, value in changes.items()]}
        structural = contracts.validate_request(request)
        archive(label + '-structural-check.json', structural)
        if not structural['valid']:
            raise RuntimeError(structural)
        archive(label + '-request.json', request)
    receipt_path = HERE / (label + '-commit.json')
    if receipt_path.exists():
        receipt = load(receipt_path)
    else:
        if not (HERE / (label + '-preflight.json')).exists():
            checked = invoke(service, 'validate-draft', request, label + '-preflight')
            archive(label + '-preflight.json', checked)
            if not checked.get('valid'):
                raise RuntimeError(checked)
        elif not load(HERE / (label + '-preflight.json')).get('valid'):
            raise RuntimeError('已有预检不是成功结果')
        receipt = invoke(service, 'commit', request, label + '-commit')
        archive(label + '-commit.json', receipt)
    if receipt.get('error'):
        raise RuntimeError(receipt)
    saved = {}
    for key in changes:
        value = invoke(service, 'inspect', {'owner_id': OWNER, 'record_id': TARGETS[key][0],
                        'revision': TARGETS[key][1] + 1}, label + '-' + key)
        archive(label + '-' + key + '-readback.json', value)
        saved[key] = value['record']
    # 以实际提交回执head串联，不用“当前HEAD”自动接纳期间并发写入。
    return saved, receipt


def apply(service, args):
    import evidence
    from memory import documents
    manifest = load(HERE / 'baseline-manifest.json')
    for name, digest in manifest['files'].items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('基线证据被修改：' + name)
    review = args.review_note.read_text(encoding='utf-8')
    if not review.strip():
        raise RuntimeError('须先实际阅读基线并保存审查说明')
    metrics = load(args.metrics)
    conclusion = metrics.get(args.summary_key)
    if not isinstance(conclusion, str) or not conclusion.strip():
        raise RuntimeError('metrics指定结论字段须为非空字符串；不自动编造最终数字')
    if len(args.run_json) != 3:
        raise RuntimeError('必须明确提供三个Run元数据路径')
    runs = [load(path) for path in args.run_json]
    if len({run['run_id'] for run in runs}) != 3:
        raise RuntimeError('三个Run身份不得重复')
    for run in runs:
        # 失败是有效实验依据；只拒绝尚未结束/未登记输入，不要求全部succeeded。
        if run.get('status') not in ('succeeded', 'failed') or not run.get('artifacts'):
            raise RuntimeError('Run必须结束且登记产物：' + run['run_id'])
    if load(RUN / 'run.json')['run_id'] not in {run['run_id'] for run in runs}:
        raise RuntimeError('三个来源须包含当前诊断Run')
    result_text = (RUN / 'RESULTS.md').read_text(encoding='utf-8')
    if not result_text.strip():
        raise RuntimeError('RESULTS不得为空')
    run_refs = [{'target_kind': 'owner', 'target_id': run['run_id'], 'revision': None,
                 'sha256': evidence.fingerprint(run), 'locator': '实际计时、失败状态和固定产物',
                 'relation': 'input'} for run in runs]
    archive('apply-inputs.json', {'run_refs': run_refs, 'run_statuses': [r['status'] for r in runs],
                                'metrics': metrics, 'review_note': review,
                                'results_sha256': hashlib.sha256(result_text.encode()).hexdigest()})
    old = {key: load(HERE / ('baseline-' + key + '-record.json'))['record'] for key in TARGETS}
    unit = edited(old['unit'])
    if any(block['block_id'] == 'latency-results' for block in unit['payload']['blocks']):
        raise RuntimeError('已存在latency-results，先检查既有提交')
    unit['sources'] = refs(unit['sources'], run_refs)
    unit['payload']['evidence_refs'] = refs(unit['payload']['evidence_refs'], run_refs)
    unit['payload']['run_ref'] = next(ref for ref in run_refs if ref['target_id'] == load(RUN / 'run.json')['run_id'])
    unit['payload']['blocks'].append({'block_id': 'latency-results', 'role': 'results',
                                     'markdown': result_text, 'requires_block_ids': []})
    description = unit['payload']['retrieval_description']
    description['method'] += '；新增真实浮点材料阅读全链路计时，分开默认预算失败与放宽预算诊断。'
    description['key_findings'].append(conclusion)
    description['limitations'] = list(dict.fromkeys([*description['limitations'], BOUNDARY]))
    saved, receipt = commit_batch(service, '01-unit', {'unit': unit}, manifest['head']['commit_id'])
    unit_ref = documents.fixed_ref(saved['unit'])
    section = edited(old['section'])
    blocks = section['payload']['blocks']
    matches = [block for block in blocks if block.get('type') == 'unit' and
               block.get('ref', {}).get('target_id') == TARGETS['unit'][0]]
    if len(matches) != 1:
        raise RuntimeError('原章节必须恰好引用reader unit一次')
    matches[0]['ref'] = unit_ref
    matches[0]['block_ids'] = list(dict.fromkeys([*matches[0].get('block_ids',
        [b['block_id'] for b in old['unit']['payload']['blocks']]), 'latency-results']))
    blocks.insert(0, {'type': 'prose', 'markdown': '原reader-results与原能力偏好块为历史固定依据；latency-results追加本轮真实计时。\n\n' + conclusion + '\n\n' + BOUNDARY,
                      'evidence_refs': [unit_ref]})
    section['sources'] = refs([ref for ref in section['sources'] if ref['target_id'] != TARGETS['unit'][0]], [unit_ref])
    overview = edited(old['overview'])
    overview['body_markdown'] += '\n\n本轮真实计时补充：\n\n' + conclusion + '\n\n' + BOUNDARY
    overview['payload']['results'].append(conclusion)
    # 只标注已审查的那条旧限制所属阶段，不改历史正文/数字；新计时不能让
    # “本轮未重跑”的旧时点措辞看似仍在描述当前阶段。
    historical_limit = '本轮没有重跑实际材料阅读质量/费用基准，沿用前阶段固定证据的历史适用范围。'
    overview['payload']['limitations'] = [
        '能力偏好阶段（历史验证范围）：' + item if item == historical_limit else item
        for item in overview['payload']['limitations']]
    overview['payload']['limitations'] = list(dict.fromkeys([*overview['payload']['limitations'], BOUNDARY]))
    overview['payload']['current_stage'] = (
        '本次分阶段计时已完成；默认预算与限流两次试验失败，最小诊断已完成阅读、笔记、'
        '决定与交接闭环但覆盖仍为partial；性能优化尚未实施。最终测量值与边界见固定计时结果。')
    overview['payload']['technical_refs'] = refs(overview['payload']['technical_refs'], [unit_ref])
    overview['sources'] = refs(overview['sources'], [unit_ref])
    middle, second = commit_batch(service, '02-section-overview', {'section': section, 'overview': overview},
                                 commit_id(receipt))
    document = edited(old['document'])
    section_ref = documents.fixed_ref(middle['section'])
    document['payload']['section_refs'] = [section_ref if ref['target_id'] == TARGETS['section'][0] else ref
                                         for ref in document['payload']['section_refs']]
    document['payload']['common_refs'] = refs([ref for ref in document['payload']['common_refs']
                                              if ref['target_id'] != TARGETS['unit'][0]], [unit_ref])
    document['payload']['scope'] += '；追加真实浮点材料阅读的默认预算失败和放宽预算计时诊断，不含性能优化实施。'
    document['sources'] = refs(document['payload']['common_refs'], document['payload']['section_refs'])
    final, third = commit_batch(service, '03-document', {'document': document}, commit_id(second))
    request = {'owner_id': OWNER, 'document_id': TARGETS['document'][0], 'revision': final['document']['revision']}
    # 完整输出含coverage/version_hints；不把完整组装当作AI已阅读或科学复核。
    for action in ('document', 'document-impact'):
        response = invoke(service, action, request, 'final-' + action)
        filename = 'final-' + action + '.json'
        if (HERE / filename).exists() and load(HERE / filename) != response:
            filename = 'final-' + action + '-' + uuid.uuid4().hex + '.json'
        archive(filename, response)
        if action == 'document' and not response['report']['complete']:
            raise RuntimeError('新文稿组装有缺口')
    final_owner = owner(service, 'final-owner')
    archive('final-owner-' + final_owner['head']['commit_id'] + '.json', final_owner)
    archive('identities.json', {key: documents.fixed_ref(value) for key, value in {**saved, **middle, **final}.items()})
    print('已保存固定修订及全文/impact。尚需主Agent阅读全文与coverage/hints后声明本范围同步。')


def commit_id(receipt):
    """只接纳公开回执的commit_id；缺失时停止，不用猜测当前HEAD补齐。"""
    value = receipt.get('commit_id')
    if not isinstance(value, str) or not value:
        raise RuntimeError('提交回执缺少commit_id，请检查公开合同：' + repr(receipt))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='stage', required=True)
    sub.add_parser('baseline-only', help='仅保存完整只读基线，随后由主Agent实际阅读')
    apply_parser = sub.add_parser('apply', help='主Agent已读基线后显式提交三批更新')
    apply_parser.add_argument('--run-json', type=Path, action='append', required=True)
    apply_parser.add_argument('--metrics', type=Path, required=True)
    apply_parser.add_argument('--summary-key', default='conclusion')
    apply_parser.add_argument('--review-note', type=Path, required=True)
    args = parser.parse_args()
    # 只有明确阶段参数才导入业务模块和创建服务；静态AST检查不触发API或索引。
    sys.path.insert(0, str(ROOT / 'automation/scripts'))
    from memory.service import MemoryService
    HERE.mkdir(parents=True, exist_ok=True)
    service = MemoryService(ROOT)
    if args.stage == 'baseline-only':
        baseline(service)
    else:
        apply(service, args)


if __name__ == '__main__':
    main()
