"""设置阶段结果的公共预检、提交和固定回读；同request_id可恢复中断。"""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parent.parent
HERE = RUN / 'memory-save'
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import evidence
from memory import api, documents
from memory.service import MemoryService

OWNER = 'PRJ-ARCHITECTURE-EVOLUTION'
service = MemoryService(ROOT)


def archive(name, value):
    with (HERE / name).open('x', encoding='utf-8') as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write('\n')


def save(key, draft):
    receipt_path = HERE / (key + '-commit.json')
    request_path = HERE / (key + '-request.json')
    if receipt_path.exists():
        receipt = evidence.read(receipt_path)
    else:
        if request_path.exists():
            request = evidence.read(request_path)
        else:
            head = api.dispatch(service, 'inspect', {'owner_id': OWNER})['head']
            request = {'schema_version': 3, 'request_id': str(uuid.uuid4()),
                'actor': {'kind': 'ai', 'id': 'codex-workspace-settings'}, 'owner_id': OWNER,
                'expected_head': head['commit_id'],
                'operations': [{'op': 'put_record', 'client_key': key, 'draft': draft}]}
            archive(key + '-request.json', request)
            checked = api.dispatch(service, 'validate-draft', request)
            archive(key + '-validation.json', checked)
            if not checked['valid']:
                raise RuntimeError(checked)
        receipt = api.dispatch(service, 'commit', request)
        archive(key + '-commit.json', receipt)
    if receipt.get('error'):
        raise RuntimeError(receipt)
    result = receipt['record_results'][0]
    record = api.dispatch(service, 'inspect', {'owner_id': OWNER, 'record_id': result['record_id'],
                                             'revision': result['revision']})['record']
    if not (HERE / (key + '-readback.json')).exists():
        archive(key + '-readback.json', record)
    return record


def draft(kind, title, payload, sources, *, body='', level=None, version=3):
    return {'schema_version': version, 'owner_id': OWNER, 'kind': kind, 'title': title, 'level': level,
        'body_markdown': body, 'payload': payload, 'sources': sources, 'provenance_gap': None,
        'record_reason': '保存2026-09-16统一设置的实现、固定验证及性能/宿主边界。',
        'discovery': 'workspace_summary', 'sensitivity': 'internal',
        'keywords': ['workspace-settings', '配置缓存', '检索预算', '单Agent', 'CAS']}


def main():
    HERE.mkdir(exist_ok=True)
    run = evidence.read(RUN / 'run.json')
    if run['status'] != 'succeeded' or not run['artifacts']:
        raise RuntimeError('必须先完成验证和Run登记')
    run_ref = {'target_kind': 'owner', 'target_id': run['run_id'], 'revision': None,
               'sha256': evidence.fingerprint(run), 'locator': 'RESULTS及固定验证产物', 'relation': 'input'}
    unit = save('settings-unit', draft('detail', '工作区设置：协作开关、默认检索预算与缓存验证', {
        'unit_type': 'analysis', 'retrieval_description': {
            'question': run['question'],
            'method': '核心红测→独立配置契约/CAS/cache→CLI/HTTP/UI与模板→旧会话/升级验证。',
            'key_findings': ['已接入新请求默认值，旧RS预算不变。', '2000次warm读取不再解码JSON，p95为0.7553毫秒，仅设置读取。'],
            'applicable': ['当前Windows x64框架的工作台和AI阅读新模板', '遵守工作区流程的AI协作策略'],
            'not_applicable': ['任意宿主工具硬禁用', '端到端检索加速或业务相关性证明'],
            'limitations': run['limitations']},
        'run_ref': run_ref, 'evidence_refs': [run_ref],
        'blocks': [{'block_id': 'settings-results', 'role': 'results',
                    'markdown': (RUN / 'RESULTS.md').read_text(encoding='utf-8'), 'requires_block_ids': []}],
        'figures': [], 'missing_refs': []}, [run_ref], level='L1'))
    unit_ref = documents.fixed_ref(unit)
    section = save('settings-section', draft('document_section', '统一设置的实现与边界验证', {
        'section_key': 'workspace-settings-20260916', 'title': '统一设置的实现与边界验证', 'role': 'methods',
        'blocks': [{'type': 'prose', 'markdown': '本章独立记录统一设置，不改写前一阶段重排实验；默认策略已可配置，旧实验保留其当时时点。',
                    'evidence_refs': [unit_ref]}, {'type': 'unit', 'ref': unit_ref, 'block_ids': ['settings-results']}],
        'watch_refs': [], 'missing_refs': []}, [unit_ref]))
    section_ref = documents.fixed_ref(section)
    document = save('settings-document', draft('document', '工作区统一设置：协作、检索预算与兼容验证完整报告', {
        'document_type': 'research_process', 'purpose': '复现设置功能实现、程序消费与验证，保留性能及宿主能力边界',
        'audience': '框架开发与工作台使用者', 'scope': '仅2026-09-16统一设置功能，不重新评审历史重排与业务结论',
        'common_refs': [unit_ref], 'section_refs': [section_ref], 'watch_refs': [], 'missing_refs': []}, [unit_ref, section_ref]))
    overview = save('settings-overview', draft('overview', '2026-09-16工作区设置实施概览', {
        'question': run['question'], 'methods': ['严格设置/CAS与进程缓存', '新模板默认与旧RS固定预算', '真实HTTP/浏览器与旧工作区升级'],
        'results': ['工作台专页、CLI与HTTP共用配置，单Agent兼容策略明确',
                    '设置13、阅读41、组件48、浏览器2、升级18项通过；配置warm p95约0.7553毫秒'],
        'current_stage': '功能及必要本机验证完成，未发布；人工/第二物理机另行验收',
        'limitations': run['limitations'], 'open_questions': ['第二物理机与用户实际环境体验', '端到端检索冷暖性能仍需单独评估'],
        'technical_refs': [unit_ref], 'process_refs': [], 'experience_refs': [], 'claims': []}, [unit_ref],
        body='工作台新增统一设置，支持协作auto/off、默认结果数、上下文/模型预算与阅读重排。程序缓存解析，新请求使用默认，旧RS保留已授权预算。必要软件与Windows升级检查通过；0.7553毫秒是配置读取p95，不是检索总延迟。开关约束工作区工作流，不能强制任意宿主工具。完整证据和失败见固定技术单元与报告。', level='L4', version=4))
    request = {'owner_id': OWNER, 'document_id': document['record_id'], 'revision': document['revision']}
    for action in ('outline', 'document', 'document-impact'):
        name = 'assembled-' + action + '.json'
        if not (HERE / name).exists():
            archive(name, api.dispatch(service, action, request))
    assembly = evidence.read(HERE / 'assembled-document.json')
    if not assembly['report']['complete']:
        raise RuntimeError('文稿不完整')
    result = {'unit': unit_ref, 'section': section_ref, 'document': documents.fixed_ref(document),
        'overview': documents.fixed_ref(overview), 'document_complete': assembly['report']['complete'],
        'coverage': assembly['report_coverage'], 'version_hints': assembly['report_version_hints'],
        'head': api.dispatch(service, 'inspect', {'owner_id': OWNER})['head']}
    if not (HERE / 'identities.json').exists():
        archive('identities.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
