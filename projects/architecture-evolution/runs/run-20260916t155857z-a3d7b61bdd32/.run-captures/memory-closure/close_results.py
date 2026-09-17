"""Bounded results closure via public memory actions only.

Run only after the parent has frozen this Run and approved the reference. Each
logical request is saved before submission, enabling idempotent recovery. The
script preserves every existing document section and overview history verbatim.
"""
import argparse
import copy
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).parent
RUN = OUT.parent.parent
sys.path.insert(0, str(ROOT / 'automation' / 'scripts'))
from memory.api import dispatch
from memory.service import MemoryService

OWNER = 'PRJ-ARCHITECTURE-EVOLUTION'
DOC = 'MEM-bd121869-a0b9-59e3-af23-8e8675374a63'
OVERVIEW = 'MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155'
RUN_ID = 'RUN-20260916T155857Z-A3D7B61BDD32'
service = MemoryService(ROOT)

def save(name, value):
    (OUT / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    return value

def call(action, request, name):
    try:
        value = dispatch(service, action, request)
    except Exception as exc:
        save(name + '-error', exc.as_dict() if hasattr(exc, 'as_dict') else {'message':str(exc)})
        raise
    save(name, value)
    print(name, 'saved', flush=True)
    return value

def fixed(record):
    return dict(target_kind='record', target_id=record['record_id'], revision=record['revision'],
                sha256=record['record_hash'], locator='', relation='references')

def editable(record):
    audit = {'record_id', 'revision', 'previous_revision', 'record_hash', 'content_hash',
             'created_at', 'created_by', 'updated_at', 'updated_by'}
    return copy.deepcopy({k: v for k, v in record.items() if k not in audit})

def submit(name, operations, head):
    request_path = OUT / (name + '-request.json')
    if request_path.exists():
        request = json.loads(request_path.read_text(encoding='utf-8'))
    else:
        request = dict(schema_version=3, request_id=str(uuid.uuid4()), actor={'kind':'ai','id':'codex-reading-note-closure'},
                       owner_id=OWNER, expected_head=head, operations=operations)
        save(name + '-request', request)
    prior = OUT / (name + '-commit.json')
    if prior.exists():
        receipt = json.loads(prior.read_text(encoding='utf-8'))
    else:
        validation = call('validate-draft', request, name + '-validation')
        if not validation.get('valid'): raise RuntimeError(validation)
        receipt = call('commit', request, name + '-commit')
    if receipt.get('save_status') not in {'committed','no_change'}: raise RuntimeError(receipt)
    records = []
    for item in receipt['record_results']:
        value = call('inspect', {'owner_id':OWNER,'record_id':item['record_id'],'revision':item['revision']}, name + '-' + item['record_id'])
        records.append(value['record'])
    return records, receipt['commit_id']

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Commit after the final Run is frozen and authorized.')
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit('Prepared only. --apply is intentionally required after the final Run signal.')
    baseline = json.loads((OUT / 'baseline-owner.json').read_text(encoding='utf-8'))
    # Resolve the native Run through the same public fixed expansion used by UI.
    packet = call('expand', {'refs':[RUN_ID], 'budget':16000}, 'fixed-run')
    run_ref = next(ref for ref in packet['manifest']['source_refs'] if ref['target_id'] == RUN_ID)
    run_ref.update(locator='RESULTS及本轮固定验证产物', relation='input')
    head = baseline['head']['commit_id']
    text = (RUN / 'RESULTS.md').read_text(encoding='utf-8')
    summary = ('工作台共享当前阅读笔记；授权覆盖原RS域后可查看，原查询范围与预算保持；'
               '列表先筛选后分页，有笔记优先。合法接口派生Markdown，JSON仍是权威；'
               '当前笔记证据仅固定引用及一层显式sources，不用同Owner全库冒充依据。')
    limits = ('真实浮点RS仍r5/partial、2条候选未记笔记；列表5项约20.266秒，未完成性能优化。'
              '规模N0浏览器超时保留为失败；非record证据仅组件覆盖，第二物理机和业务科学复核未完成；未发布。')
    draft = dict(schema_version=3, owner_id=OWNER, kind='detail', level='L1', title='阅读笔记可读副本与工作台入口：固定依据及验证',
                 body_markdown='', keywords=['reading-note','Markdown派生快照','当前笔记','固定版本证据','Windows升级'],
                 payload=dict(unit_type='analysis', retrieval_description=dict(question='如何使已授权阅读笔记可读、可发现并准确定位其固定依据？',
                     method='公开RS/记忆接口、单一当前选择、固定引用一层展开及分级软件验证。', key_findings=[summary],
                     applicable=['本机Windows x64工作台与合法RS阅读接口'], not_applicable=['总费用或检索速度改善证明','科学结论认可'], limitations=[limits]),
                     run_ref=run_ref, evidence_refs=[run_ref], blocks=[dict(block_id='reading-ui-storage-results',role='results',markdown=text,requires_block_ids=[])], figures=[],missing_refs=[]),
                 sources=[run_ref],provenance_gap=None,record_reason='保存阅读笔记可读性、授权兼容、定向证据和导航修复的实施依据与失败边界。',discovery='workspace_summary',sensitivity='internal')
    unit_records, head = submit('unit', [{'op':'put_record','client_key':'reading-ui-storage','draft':draft}], head)
    unit_ref = fixed(unit_records[0])
    section = dict(schema_version=3,owner_id=OWNER,kind='document_section',level=None,title='阅读笔记可读副本与工作台入口',body_markdown='',keywords=draft['keywords'],
                   payload=dict(section_key='reading-ui-storage-20260916',title='阅读笔记可读副本与工作台入口',role='methods',
                     blocks=[dict(type='prose',markdown='本章新增阅读笔记的可读派生副本、合法会话发现和工作台入口。前章保留委派、能力配置及真实计时的历史固定依据；本章修复不重新验证浮点科学内容，也不将可见性修复解释为性能优化。',evidence_refs=[unit_ref]),
                             dict(type='unit',ref=unit_ref,block_ids=['reading-ui-storage-results'])],watch_refs=[],missing_refs=[]),
                   sources=[unit_ref],provenance_gap=None,record_reason='将本次UI/storage独立结果编排入既有完整报告，保留旧章节原修订。',discovery='workspace_summary',sensitivity='internal')
    sections, head = submit('section',[{'op':'put_record','client_key':'reading-ui-storage-section','draft':section}],head)
    section_ref = fixed(sections[0])
    old_overview = baseline['records'][OVERVIEW]
    overview = editable(old_overview)
    overview['body_markdown'] += '\n\n## 2026-09-17阅读笔记与工作台入口补充\n\n' + summary + '\n\n' + limits + '\n\n本轮具体软件验证、构建指纹和升级复验见新增固定技术单元；旧测量、失败与能力配置数字保留其历史范围。'
    overview['payload']['technical_refs'].append(unit_ref)
    overview['payload']['results'].append(summary)
    overview['payload']['limitations'].append(limits)
    overview['payload']['current_stage'] = '阅读笔记可读副本和工作台入口修复已实施并完成本范围验证；历史计时与partial覆盖边界保留，尚未完成性能优化或修复既有规模N0超时。'
    overview['sources'].append(unit_ref)
    overview['change_reason'] = '追加本次UI/storage结果，保留全部旧计时、委派、能力配置正文和固定引用。'
    old_doc = baseline['records'][DOC]
    document = editable(old_doc)
    document['payload']['section_refs'].append(section_ref)
    document['payload']['common_refs'].append(unit_ref)
    document['payload']['scope'] += '；新增2026-09-16至17阅读笔记Markdown派生副本、合法会话发现、当前笔记与定向证据/导航修复及验证；不宣称性能优化完成。'
    document['sources'].extend([unit_ref,section_ref])
    document['change_reason'] = overview['change_reason']
    _, head = submit('overview-document', [
        {'op':'put_record','record_id':OVERVIEW,'expected_revision':old_overview['revision'],'draft':overview},
        {'op':'put_record','record_id':DOC,'expected_revision':old_doc['revision'],'draft':document},
    ], head)
    for action in ('outline','document','document-impact'):
        call(action,{'owner_id':OWNER,'document_id':DOC},'final-'+action)
    save('closure-head', {'commit_id':head,'unit':unit_ref,'section':section_ref})
