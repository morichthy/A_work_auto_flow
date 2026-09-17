"""三批更新已有设置/委派成果；需主任务冻结、成功登记 Run 后显式运行。

本文件不直接修改规范记录、HEAD 或旧 Run。所有变更均经公开预检/提交；
每批先固定当前 HEAD，再以目标原 revision=1 做 CAS。复跑复用原 request_id，
不自动吞并并发变化，不重建平行文稿。全文回读仅证明组装，仍需主 Agent 实读。
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parent.parent
HERE = RUN / 'memory-update-v2'
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import evidence
from memory import api, contracts, documents
from memory.service import MemoryService

OWNER = 'PRJ-ARCHITECTURE-EVOLUTION'
IDS = {
    'settings-unit': 'MEM-472e4d18-f18d-5d13-84e3-28d3d5ae211a',
    'settings-section': 'MEM-7df3c088-504b-532d-ad74-b459bed75ba4',
    'reader-unit': 'MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b',
    'reader-section': 'MEM-50f66b7c-7953-5715-8b70-5ae7705176ab',
    'settings-overview': 'MEM-67e69e5f-8de7-5c24-b8bc-eb41299f8eaf',
    'reader-overview': 'MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155',
    'settings-document': 'MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152',
    'reader-document': 'MEM-bd121869-a0b9-59e3-af23-8e8675374a63',
}
CHANGE = '沿用既有身份补充子Agent能力偏好；保留原阶段固定块、失败及验证范围，更新现行章节、概览和文稿固定关系。'
CURRENT = ('新增 collaboration.subagent_requirements 自由文本模型/能力偏好；缺省优先低成本、'
           '较低能力可用模型和低推理深度，并须完成检索、完整阅读与结构化笔记。用户自定义文本'
           '原样保留，去除首尾空白后限1–2000字符；经policy及委派包交给宿主按实际可用模型选择。'
           'off始终优先，无宿主能力仍同RS回退；偏好不授予工具或材料权限，不扩大原RS预算。')
BOUNDARY = ('旧schema-1缺新字段仅内存补默认，原字节及revision不变；完整写入禁止遗漏字段丢失偏好。'
            '软件和本机合成升级验证不证明指定模型实际可用、业务阅读质量、总费用或端到端延迟改善；'
            '原阶段实际reader、字符对比、失败和覆盖缺口均保留为历史证据。')


def archive(name, value):
    """结果先完整生成再落盘，避免空 JSON 被 Owner 业务扫描发现。"""
    target = HERE / name
    if target.exists():
        if evidence.read(target) != value:
            raise RuntimeError('拒绝覆盖已冻结回执：' + name)
        return
    raw = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    temporary = target.with_suffix('.pending')
    temporary.write_text(raw, encoding='utf-8')
    temporary.replace(target)


def call(service, action, request):
    """error:null 是成功合同的一部分，只检查值，不检查键是否存在。"""
    result = api.dispatch(service, action, request)
    if result.get('error'):
        raise RuntimeError(result)
    return result


def inspect(service, key, revision=1):
    return call(service, 'inspect', {'owner_id': OWNER, 'record_id': IDS[key],
                                    'revision': revision})['record']


def draft(record):
    """白名单复制可编辑字段，去掉服务生成的身份、hash、时间与审计字段。"""
    value = {key: deepcopy(record[key]) for key in
             (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
    value['change_reason'] = CHANGE
    value['keywords'] = list(dict.fromkeys([*value['keywords'], 'subagent_requirements', '能力偏好']))
    return value


def unique_refs(*groups):
    values = []
    for group in groups:
        for ref in group:
            if ref not in values:
                values.append(deepcopy(ref))
    return values


def batch(service, key, changes):
    """成功回执可复用；中断后以冻结请求预检/提交，CAS冲突须人工读差异。

    schema-3 CommitRequest 允许既有v3 detail/section/document与v4 overview；
    不把记录本身批量升版本。每条revision CAS与Owner HEAD CAS同时保留。
    """
    request_file, receipt_file = HERE / (key + '-request.json'), HERE / (key + '-commit.json')
    if request_file.exists():
        request = evidence.read(request_file)
        expected_drafts = {IDS[name]: value for name, value in changes.items()}
        if {op['record_id']: op['draft'] for op in request['operations']} != expected_drafts:
            raise RuntimeError('冻结请求与本次内容不同，停止续跑：' + key)
    else:
        current = call(service, 'inspect', {'owner_id': OWNER})
        archive(key + '-head-before.json', current)
        # 明确限定r1→r2。并发新修订不会被本脚本自动合并或覆盖。
        for name in changes:
            latest = call(service, 'inspect', {'owner_id': OWNER, 'record_id': IDS[name]})['record']
            if latest['revision'] != 1:
                raise RuntimeError('目标已不在已审查r1：' + name)
        request = {'schema_version': 3, 'request_id': str(uuid.uuid4()),
                   'actor': {'kind': 'ai', 'id': 'codex-capability-settings'},
                   'owner_id': OWNER, 'expected_head': current['head']['commit_id'],
                   'operations': [{'op': 'put_record', 'record_id': IDS[name],
                                   'expected_revision': 1, 'draft': value}
                                  for name, value in changes.items()]}
        archive(key + '-request.json', request)
    if receipt_file.exists():
        receipt = evidence.read(receipt_file)
    else:
        # 已预检而提交回执尚未落盘时直接重放同request_id。commit公开入口先查
        # 幂等回执，再做HEAD/CAS验证；此时强制再次预检会把已成功提交误报冲突。
        validation_file = HERE / (key + '-validation.json')
        if validation_file.exists():
            checked = evidence.read(validation_file)
        else:
            checked = api.dispatch(service, 'validate-draft', request)
            if checked.get('error') or not checked.get('valid'):
                archive(key + '-validation-error-' + uuid.uuid4().hex + '.json', checked)
                raise RuntimeError(checked)
            archive(key + '-validation.json', checked)
        if checked.get('error') or not checked.get('valid'):
            raise RuntimeError(checked)
        receipt = api.dispatch(service, 'commit', request)
        if receipt.get('error'):
            archive(key + '-commit-error-' + uuid.uuid4().hex + '.json', receipt)
            raise RuntimeError(receipt)
        archive(key + '-commit.json', receipt)
    if receipt.get('error'):
        raise RuntimeError(receipt)
    results = {item['record_id']: item for item in receipt['record_results']}
    records = {}
    for name in changes:
        result = results[IDS[name]]
        if result['revision'] != 2:
            raise RuntimeError('不是预期r2：' + name)
        record = inspect(service, name, 2)
        archive(name + '-r2-readback.json', record)
        records[name] = record
    return records


def main():
    # 不在import时初始化服务或创建目录，未成功登记Run绝不开始记忆写入。
    run = evidence.read(RUN / 'run.json')
    if run.get('status') != 'succeeded' or not run.get('artifacts'):
        raise RuntimeError('先冻结源码/RESULTS、将Run标为succeeded并登记产物，再执行本脚本')
    results_text = (RUN / 'RESULTS.md').read_text(encoding='utf-8')
    if not results_text.strip():
        raise RuntimeError('RESULTS不得为空')
    service = MemoryService(ROOT)
    HERE.mkdir(exist_ok=True)
    run_ref = {'target_kind': 'owner', 'target_id': run['run_id'], 'revision': None,
               'sha256': evidence.fingerprint(run), 'locator': 'RESULTS与能力偏好固定验证产物',
               'relation': 'input'}
    # 续跑时Run变化会被原来源快照拒绝，不能让同一r2绑定浮动证据。
    archive('run-source.json', run_ref)
    old = {name: inspect(service, name) for name in IDS}
    for name, record in old.items():
        archive(name + '-r1-baseline.json', record)

    unit = draft(old['settings-unit'])
    unit['sources'] = unique_refs(unit['sources'], [run_ref])
    payload = unit['payload']
    payload['run_ref'] = run_ref
    payload['evidence_refs'] = unique_refs(payload['evidence_refs'], [run_ref])
    # 原settings-results内容逐字保留；历史时点由章节过渡明确，不倒改原数字。
    payload['blocks'].append({'block_id': 'requirements-results', 'role': 'results',
                              'markdown': results_text, 'requires_block_ids': []})
    description = payload['retrieval_description']
    description['question'] += ' 同时如何保留可编辑子Agent能力偏好与旧配置兼容？'
    description['method'] += ' 本轮新增偏好文本/兼容/CAS边界、宿主选择传递、UI与真实旧工作区保护验证。'
    description['key_findings'].append(CURRENT)
    description['limitations'] = list(dict.fromkeys([*description['limitations'], BOUNDARY, *run['limitations']]))
    updated = batch(service, '01-unit', {'settings-unit': unit})
    unit_ref = documents.fixed_ref(updated['settings-unit'])
    reader_ref = documents.fixed_ref(old['reader-unit'])

    setting_section = draft(old['settings-section'])
    setting_section['payload']['blocks'] = [
        {'type': 'prose', 'markdown': '以下settings-results为统一设置初始阶段的历史原文，数字仅对应当时验证。当前能力偏好以其后requirements-results为准。', 'evidence_refs': [unit_ref]},
        {'type': 'unit', 'ref': unit_ref, 'block_ids': ['settings-results']},
        {'type': 'prose', 'markdown': CURRENT + '\n\n' + BOUNDARY, 'evidence_refs': [unit_ref]},
        {'type': 'unit', 'ref': unit_ref, 'block_ids': ['requirements-results']}]
    setting_section['sources'] = [unit_ref]
    reader_section = draft(old['reader-section'])
    reader_section['payload']['blocks'] = [
        {'type': 'prose', 'markdown': '以下原委派单元r1保留当时实现、低成本reader及全部验证限制；其中固定low选择是历史行为，现行模型选择由后续能力偏好更新说明限定。', 'evidence_refs': [reader_ref]},
        *reader_section['payload']['blocks'],
        {'type': 'prose', 'markdown': CURRENT + '\n\n' + BOUNDARY, 'evidence_refs': [unit_ref]},
        {'type': 'unit', 'ref': unit_ref, 'block_ids': ['requirements-results']}]
    reader_section['sources'] = unique_refs(reader_section['sources'], [unit_ref])
    middle = {'settings-section': setting_section, 'reader-section': reader_section}
    for name in ('settings-overview', 'reader-overview'):
        overview = draft(old[name])
        # 原概览作为明确历史段落保存；新要求另起现行段，避免低成本被误读为硬约束。
        overview['body_markdown'] = ('原阶段概览（历史验证范围）：\n\n' + overview['body_markdown'] +
                                    '\n\n本轮现行补充：\n\n' + CURRENT + '\n\n' + BOUNDARY)
        body = overview['payload']
        body['results'] = ['历史阶段：' + item for item in body['results']]
        body['results'].extend([CURRENT, '本轮验证及失败边界见requirements-results固定块；不以历史测试数量替代本轮回执。'])
        body['limitations'] = list(dict.fromkeys([*body['limitations'], BOUNDARY, *run['limitations']]))
        body['technical_refs'] = unique_refs(body['technical_refs'], [unit_ref])
        overview['sources'] = unique_refs(overview['sources'], [unit_ref])
        middle[name] = overview
    updated.update(batch(service, '02-sections-overviews', middle))

    final = {}
    for prefix in ('settings', 'reader'):
        name = prefix + '-document'
        document = draft(old[name])
        section_ref = documents.fixed_ref(updated[prefix + '-section'])
        common_refs = [unit_ref] if prefix == 'settings' else [reader_ref, unit_ref]
        document['payload']['common_refs'] = common_refs
        document['payload']['section_refs'] = [section_ref]
        document['payload']['scope'] += '；含本轮能力偏好、旧设置无损兼容与宿主传递扩展。'
        document['payload']['purpose'] += '，并区分历史默认low与当前可编辑模型偏好'
        document['sources'] = unique_refs(common_refs, [section_ref])
        final[name] = document
    updated.update(batch(service, '03-documents', final))

    # 保存两份完整文稿、影响报告和当前HEAD；覆盖提示不等于全Owner已同步。
    for prefix in ('settings', 'reader'):
        record = updated[prefix + '-document']
        request = {'owner_id': OWNER, 'document_id': record['record_id'], 'revision': record['revision']}
        for action in ('document', 'document-impact'):
            archive(prefix + '-' + action + '-request.json', request)
            response = call(service, action, request)
            # 每次续跑的动态impact保留新回执，不覆盖首次固定报告。
            name = prefix + '-' + action + '.json'
            if (HERE / name).exists() and evidence.read(HERE / name) != response:
                name = prefix + '-' + action + '-' + uuid.uuid4().hex + '.json'
            archive(name, response)
            if action == 'document' and not response['report']['complete']:
                raise RuntimeError('文稿组装不完整：' + prefix)
    head = call(service, 'inspect', {'owner_id': OWNER})
    archive('owner-head-' + head['head']['commit_id'] + '.json', head)
    identities = {name: documents.fixed_ref(record) for name, record in updated.items()}
    archive('identities.json', identities)
    print(json.dumps(identities, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
