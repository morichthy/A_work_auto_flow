"""通过公开memory API保存本轮独立技术结果、章节、文稿和概览；回执允许安全续接。"""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parent.parent
HERE = RUN / 'verification'
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import evidence
from memory import api, documents
from memory.service import MemoryService

OWNER = 'PRJ-ARCHITECTURE-EVOLUTION'
service = MemoryService(ROOT)

def archive(name, value):
    """仅写本脚本新回执；已有回执保持原字节，重试直接复用。"""
    path = HERE / name
    if path.exists():
        raise RuntimeError('拒绝覆盖已有固定回执：' + name)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def save(key, draft):
    receipt_path = HERE / (key + '-commit.json')
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    else:
        head = api.dispatch(service, 'inspect', {'owner_id':OWNER})['head']
        request = {'schema_version':3, 'request_id':str(uuid.uuid4()),
                   'actor':{'kind':'ai','id':'codex-reranking-implementation'},
                   'owner_id':OWNER,'expected_head':head['commit_id'],
                   'operations':[{'op':'put_record','client_key':key,'draft':draft}]}
        archive(key+'-request.json', request)
        validation = api.dispatch(service,'validate-draft',request)
        archive(key+'-validation.json',validation)
        if not validation['valid']:
            raise RuntimeError('草案预检失败')
        receipt = api.dispatch(service,'commit',request)
        archive(key+'-commit.json',receipt)
    row=receipt['record_results'][0]
    record=api.dispatch(service,'inspect',{'owner_id':OWNER,'record_id':row['record_id'],'revision':row['revision']})['record']
    if not (HERE/(key+'-readback.json')).exists():
        archive(key+'-readback.json',record)
    return record

def draft(kind,title,payload, *, sources, body='',level=None,version=3):
    return {'schema_version':version,'owner_id':OWNER,'kind':kind,'title':title,'level':level,
            'body_markdown':body,'payload':payload,'sources':sources,'provenance_gap':None,
            'record_reason':'保存2026-09-16已授权重排实施、真实验证和边界，供后续复用。',
            'discovery':'workspace_summary','sensitivity':'internal',
            'keywords':['Cross-encoder','重排','显式条件','冻结基线','离线模型']}

def main():
    run=evidence.read(RUN/'run.json')
    if run['status']!='succeeded' or not run['artifacts']:
        raise RuntimeError('先完成真实验证及Run材料登记')
    run_ref={'target_kind':'owner','target_id':run['run_id'],'revision':None,
             'sha256':evidence.fingerprint(run),'locator':'RESULTS及固定verification产物','relation':'input'}
    body=(RUN/'RESULTS.md').read_text(encoding='utf-8')
    unit=save('reranking-unit',draft('detail','正文、Cross-encoder与条件重排：实施和固定对照',{
        'unit_type':'analysis','retrieval_description':{
            'question':'候选覆盖高而前6排序差时如何改进，同时保护权限、费用和离线迁移？',
            'method':'冻结候选基线后，独立完整上下文、离线CE及显式条件；公开CLI和真实setup验收。',
            'key_findings':['开发Recall@6 0.75→1.00，留出nDCG@6 0.521→0.991，仅小样本。','自然语言fixture条件全unknown，未证明条件额外指标收益。'],
            'applicable':['本轮固定合成题集、Windows x64本机隔离软件验证'],
            'not_applicable':['不得直接推断业务质量达标、端到端加速或工程方案有效'],
            'limitations':run['limitations']},
        'run_ref':run_ref,'evidence_refs':[run_ref],
        'blocks':[{'block_id':'implementation-results','role':'results','markdown':body,'requires_block_ids':[]}],
        'figures':[],'missing_refs':[]},sources=[run_ref],level='L1'))
    unit_ref=documents.fixed_ref(unit)
    section=save('reranking-section',draft('document_section','正文重排完整实施与验证',{
        'section_key':'reranking-20260916','title':'正文重排完整实施与验证','role':'methods',
        'blocks':[{'type':'prose','markdown':'本章是2026-09-16独立重排演进的完整结果；历史表示查询设计仍保留原固定版本。','evidence_refs':[unit_ref]},
                  {'type':'unit','ref':unit_ref,'block_ids':['implementation-results']}],
        'watch_refs':[],'missing_refs':[]},sources=[unit_ref]))
    section_ref=documents.fixed_ref(section)
    document=save('reranking-document',draft('document','召回排序演进：正文、条件与Cross-encoder完整报告',{
        'document_type':'research_process','purpose':'复现本轮功能拆解、核心基线、实现及验证边界',
        'audience':'框架开发与检索评估人员','scope':'仅2026-09-16新增AI阅读重排，历史v0.1/v0.2稿保持其时点',
        'common_refs':[unit_ref],'section_refs':[section_ref],'watch_refs':[],'missing_refs':[]},sources=[unit_ref,section_ref]))
    overview=save('reranking-overview',draft('overview','2026-09-16召回排序演进概览',{
        'question':'在保留召回覆盖和可追溯边界下提升前列排序',
        'methods':['冻结基线→有界正文→离线CE与显式条件→排序及诊断','实际CLI阅读和Windows离线迁移验证'],
        'results':['已接入新AI阅读auto模板，旧RS保持off','小型开发和留出题集改善前列指标，完整结果见固定技术单元'],
        'current_stage':'软件及本机离线交付验证完成；真实业务与规模验收待做',
        'limitations':run['limitations'],'open_questions':['真实业务条件结构化覆盖率','长文窗口选择','冷暖p50/p95和非空无答案误报'],
        'technical_refs':[unit_ref],'process_refs':[],'experience_refs':[],'claims':[]},sources=[unit_ref],
        body='本轮已完成有界候选、固定正文/必要定义、Cross-encoder和显式条件重排，并验证预算、权限及Windows离线交付。开发Recall@6从0.75到1.00，留出nDCG@6从0.521到0.991；两套仅各两道有效题，不能替代业务验收。条件自然语料全unknown，冷启动模型加载占大头；尚不宣称加速。完整方法、失败、模型和限制由固定技术单元及独立文稿展开。',level='L4',version=4))
    request={'owner_id':OWNER,'document_id':document['record_id'],'revision':document['revision']}
    for action in ['outline','document','document-impact']:
        path=HERE/('reranking-'+action+'-readback.json')
        if not path.exists(): archive(path.name,api.dispatch(service,action,request))
    view=json.loads((HERE/'reranking-document-readback.json').read_text(encoding='utf-8'))
    # document-record回读与组装回读文件名区分，避免覆盖不可变证据。
    assembly=api.dispatch(service,'document',request)
    if not (HERE/'reranking-assembled-readback.json').exists(): archive('reranking-assembled-readback.json',assembly)
    if not assembly['report']['complete']: raise RuntimeError('文稿组装不完整')
    output={'unit':documents.fixed_ref(unit),'section':section_ref,'document':documents.fixed_ref(document),
            'overview':documents.fixed_ref(overview),'document_complete':assembly['report']['complete'],
            'coverage':assembly['report_coverage'],'version_hints':assembly['report_version_hints'],
            'head':api.dispatch(service,'inspect',{'owner_id':OWNER})['head']}
    if not (HERE/'saved-results-identities.json').exists(): archive('saved-results-identities.json',output)
    print(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
