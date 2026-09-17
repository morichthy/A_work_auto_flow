"""经公开接口保存固定验证结果，保留幂等请求并回读完整文稿。"""
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
    # 不覆盖旧请求或回执，重试应复用同一身份而非制造新知识副本。
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
                'actor': {'kind': 'ai', 'id': 'codex-reading-delegation'}, 'owner_id': OWNER,
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
        'record_reason': '保存子Agent阅读与有界笔记交接的实现、实际独立AI和软件验证边界。',
        'discovery': 'workspace_summary', 'sensitivity': 'internal',
        'keywords': ['reading-note', 'subagent', '上下文预算', '固定来源', 'handoff']}


def main():
    HERE.mkdir(exist_ok=True)
    run = evidence.read(RUN / 'run.json')
    if run['status'] != 'succeeded' or not run['artifacts']:
        raise RuntimeError('先完成测试、结果与Run登记，再冻结记忆来源')
    run_ref = {'target_kind': 'owner', 'target_id': run['run_id'], 'revision': None,
               'sha256': evidence.fingerprint(run), 'locator': 'RESULTS与固定验证产物', 'relation': 'input'}
    baseline = api.dispatch(service, 'inspect', {'owner_id': OWNER,
        'record_id': 'MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152', 'revision': 1})['record']
    baseline_ref = documents.fixed_ref(baseline)
    unit = save('reader-unit', draft('detail', '独立子Agent阅读与有界笔记交接：实现及验证', {
        'unit_type': 'analysis', 'retrieval_description': {
            'question': run['question'], 'method': '现状基线、独立reader与仅笔记交接、固定预算及权限负例、真实独立上下文验收。',
            'key_findings': ['宿主实际派工，主侧只回读有界reading note。',
                             '关闭或缺宿主能力时同RS回退；不增加代理运行依赖。'],
            'applicable': ['遵守material-query Skill且提供子Agent工具的AI宿主', '单Agent兼容阅读路径'],
            'not_applicable': ['声称任意宿主会自动派工', '总AI费用下降或语义准确率的统计证明'],
            'limitations': run['limitations']},
        'run_ref': run_ref, 'evidence_refs': [run_ref, baseline_ref],
        'blocks': [{'block_id': 'reader-results', 'role': 'results',
                    'markdown': (RUN / 'RESULTS.md').read_text(encoding='utf-8'), 'requires_block_ids': []}],
        'figures': [], 'missing_refs': []}, [run_ref, baseline_ref], level='L1'))
    unit_ref = documents.fixed_ref(unit)
    section = save('reader-section', draft('document_section', '子Agent阅读与主Agent交接', {
        'section_key': 'reading-delegation-20260916', 'title': '子Agent阅读与主Agent交接', 'role': 'methods',
        'blocks': [{'type': 'prose', 'markdown': '本章记录独立新增的阅读委派能力；统一设置的历史报告保留其当时验证范围，作为固定基线引用。',
                    'evidence_refs': [unit_ref, baseline_ref]},
                   {'type': 'unit', 'ref': unit_ref, 'block_ids': ['reader-results']}],
        'watch_refs': [], 'missing_refs': []}, [unit_ref]))
    section_ref = documents.fixed_ref(section)
    document = save('reader-document', draft('document', '子Agent材料阅读与有界笔记交接完整报告', {
        'document_type': 'research_process', 'purpose': '复现阅读上下文隔离、主侧交接及边界验证',
        'audience': '框架开发者和AI工作流使用者', 'scope': '仅2026-09-16子Agent材料阅读与有界笔记交接，不重新认可历史业务结论',
        'common_refs': [unit_ref], 'section_refs': [section_ref], 'watch_refs': [], 'missing_refs': []}, [unit_ref, section_ref]))
    overview = save('reader-overview', draft('overview', '2026-09-16子Agent阅读实施概览', {
        'question': run['question'], 'methods': ['宿主无关委派任务包', '同RS有界notes-only交接', '权限/预算/完整性软件测试与独立低成本AI'],
        'results': ['已实现委派/回退与有界笔记交接，真实AI和软件结果见固定报告', run['conclusion']],
        'current_stage': '本机必要验证完成，未发布；人工/第二物理机另行验收',
        'limitations': run['limitations'], 'open_questions': ['真实业务阅读完整性及长期费用/延迟表现', '其他宿主工具的实际接入体验'],
        'technical_refs': [unit_ref], 'process_refs': [], 'experience_refs': [], 'claims': []}, [unit_ref],
        body='材料检索和完整阅读由宿主独立低成本reader执行，主Agent只接收带固定出处的有界笔记。关闭或无宿主支持时同RS单Agent执行；不增加后台AI服务。交接继续核验权限、版本和原预算，超长/陈旧及检索覆盖缺口明示。软件、真实合成AI自查与业务正确性分开；详细数字以固定报告为准。', level='L4', version=4))
    request = {'owner_id': OWNER, 'document_id': document['record_id'], 'revision': document['revision']}
    for action in ('outline', 'document', 'document-impact'):
        if not (HERE / ('assembled-' + action + '.json')).exists():
            archive('assembled-' + action + '.json', api.dispatch(service, action, request))
    assembly = evidence.read(HERE / 'assembled-document.json')
    if not assembly['report']['complete']:
        raise RuntimeError('文稿组装有缺口')
    identities = {'unit': unit_ref, 'section': section_ref, 'document': documents.fixed_ref(document),
        'overview': documents.fixed_ref(overview), 'document_complete': assembly['report']['complete'],
        'coverage': assembly['report_coverage'], 'version_hints': assembly['report_version_hints'],
        'head': api.dispatch(service, 'inspect', {'owner_id': OWNER})['head']}
    if not (HERE / 'identities.json').exists():
        archive('identities.json', identities)
    print(json.dumps(identities, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
