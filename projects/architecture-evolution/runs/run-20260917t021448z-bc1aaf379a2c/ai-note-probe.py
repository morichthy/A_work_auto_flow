"""本轮独立合成 AI 写作验收：prepare 只交付材料，不自动撰写 note。

使用公开材料查询 dispatch 和规范记忆提交；不修改生产数据或共享测试文件，
不加载向量模型。submit 只提交人/AI 已实际写好的 draft-note.json。
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid

RUN = Path(__file__).resolve().parent
REPO = RUN.parents[3]
sys.path[:0] = [str(REPO / 'automation/scripts'), str(REPO / 'automation/tests')]
from material_query_fixture import materialize
from test_memory_documents_v3 import unit_payload, section_payload, document_payload
from memory import contracts, documents
from material_query.api import dispatch
from material_query.coordinator import Coordinator

OUT = RUN / 'ai-note-probe'
ROOT = REPO / '.local' / 'writing-note-probe-20260917' / 'synthetic-attempt-02'

def write(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def call(app, action, request):
    result = dispatch(app, 'reading-' + action, request)
    write(action + '-request.json', request)
    write(action + '-response.json', result)
    if result['status'] not in ('ok', 'partial'):
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result['value']

def prepare():
    # materialize 自身验证隔离目录；目标已存在时拒绝，避免覆盖已有验收。
    fx = materialize(ROOT, isolation_root=ROOT.parent)
    base = fx.records['A.unit']
    draft = {k: deepcopy(base[k]) for k in (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
    payload = unit_payload()
    payload['blocks'] = [
        {'block_id':'definitions','role':'definitions','requires_block_ids':[],
         'markdown':'# 合成温度校准材料\n\nreadingfixture。摄氏温度 $t$ 单位为 °C，热力学温度 $T$ 单位为 K；合成电压 $V$ 单位为 V。模型 $V=a t+b$，$a=0.01$ V/°C、$b=0.50$ V，材料只覆盖 $0\\le t\\le80$ °C，不是现实传感器验证。'},
        {'block_id':'result','role':'results','requires_block_ids':['definitions'],
         'markdown':'原先直接把电压读数当温度会混淆单位，因此材料先固定线性校准和温标。反算 $t=(V-b)/a$，$T=t+273.15$。合成输入 $V=0.75$ V 对应 $t=25$ °C、$T=298.15$ K。假定 $a,b$ 无误差且电压标准不确定度 $u_V=0.002$ V，则 $u_t=u_V/|a|=0.2$ °C，$u_T=0.2$ K；若校准参数也不确定，该误差式不完整。'},
        {'block_id':'limits','role':'discussion','requires_block_ids':['definitions'],
         'markdown':'材料将95 °C作为超出校准区间的反例，没有验证其线性外推。材料建议如需扩展温区，应先加入独立边界校准样本；这只是材料中的建议，并无已完成实验。温标平移保留温差与不确定度数值，可作为跨温标比较的线索；没有给出后续检索词。'}]
    draft.update(schema_version=3, title='readingfixture 合成校准与温标', body_markdown='', payload=payload,
                 sources=[fx.source_ref('A')], keywords=['readingfixture'])
    unit = fx.commit_draft('ai.unit', draft)
    draft.update(kind='document_section', level=None, title='合成校准完整章节',
                 payload=section_payload(documents.fixed_ref(unit)))
    section = fx.commit_draft('ai.section', draft)
    draft.update(kind='document', title='合成校准研究过程',
                 payload=document_payload([documents.fixed_ref(section)]))
    fx.commit_draft('ai.document', draft)
    app = Coordinator(ROOT)
    try:
        start = call(app, 'template', {})
        scope = dict(owner_ids=[fx.owner_ids['A']], owner_types=None, levels=None, kinds=None,
                     source_ids=None, paths=None, updated_after=None, include_archived=False,
                     exclude_owner_ids=[], exclude_source_ids=[], sensitivity=None, tags=None)
        # 使用接口模板给出的字段，范围形状复制自模板后只限定合成Owner。
        scope = deepcopy(start['query']['scope']) if start['query']['scope'] else {}
        scope['owner_ids'] = [fx.owner_ids['A']]
        start.update(session_id='RS-' + str(uuid.uuid4()), goal='校准材料知识笔记验收', conditions=['仅合成材料'],
                     owner_id=fx.owner_ids['A'], strategy='associative', association_text='')
        start['query'].update(question='readingfixture', keywords=[], scope=scope, scope_ceiling=scope)
        start['reranking'] = {'mode':'off','candidate_limit':30,'conditions':[]}
        value = call(app, 'start', start)
        sid, rev = value['session_id'], value['revision']
        call(app, 'delegate', {'session_id':sid,'host_supports_subagents':True})
        value = call(app, 'recall', dict(session_id=sid, expected_revision=rev, request_id=str(uuid.uuid4()),
                     question='readingfixture',keywords=[],scope=scope,reason='读取合成校准材料'))
        value = call(app, 'read', dict(session_id=sid, expected_revision=value['revision'],
                     request_id=str(uuid.uuid4()),owner_id=fx.owner_ids['A']))
        write('state.json',dict(session_id=sid,revision=value['revision'],owner_id=fx.owner_ids['A'],root=str(ROOT)))
        print(json.dumps(value,ensure_ascii=False,indent=2))
    finally:
        app.close()

def retry_prepare():
    # 保留首次错误请求，修正reranking属于start外层；复用原合成材料而非重建。
    start = json.loads((OUT/'start-request.json').read_text(encoding='utf-8'))
    write('start-first-rejected-request.json',start)
    write('start-first-rejected-response.json',json.loads((OUT/'start-response.json').read_text(encoding='utf-8')))
    start['query'].pop('reranking',None)
    start['reranking']={'mode':'off','candidate_limit':30,'conditions':[]}
    start['query']['missing_policy']='skip'
    app=Coordinator(ROOT)
    try:
        value=call(app,'start',start)
        sid,rev=value['session_id'],value['revision']
        call(app,'delegate',{'session_id':sid,'host_supports_subagents':True})
        value=call(app,'recall',dict(session_id=sid,expected_revision=rev,request_id=str(uuid.uuid4()),
             question='readingfixture',keywords=[],scope=start['query']['scope'],reason='读取合成校准材料'))
        value=call(app,'read',dict(session_id=sid,expected_revision=value['revision'],request_id=str(uuid.uuid4()),owner_id=start['owner_id']))
        write('state.json',dict(session_id=sid,revision=value['revision'],owner_id=start['owner_id'],root=str(ROOT)))
        print(json.dumps(value,ensure_ascii=False,indent=2))
    finally:
        app.close()

def submit():
    state = json.loads((OUT/'state.json').read_text(encoding='utf-8'))
    app = Coordinator(ROOT)
    try:
        call(app,'delegate',{'session_id':state['session_id'],'host_supports_subagents':True})
        current=call(app,'view',{'session_id':state['session_id'],'notes_only':True})
        note = json.loads((OUT/'draft-note.json').read_text(encoding='utf-8'))
        saved = call(app,'note',dict(session_id=state['session_id'],expected_revision=current['revision'],
                   request_id=str(uuid.uuid4()),owner_id=state['owner_id'],research_note=note))
        saved = call(app,'decide',dict(session_id=state['session_id'],expected_revision=saved['revision'],
                   request_id=str(uuid.uuid4()),direction='finish',reason='合成文稿阅读和材料笔记已完成，覆盖缺口保留',
                   next_step='交回主Agent',outcome='',human_decision=''))
        print(json.dumps(call(app,'handoff',{'session_id':state['session_id'],'expected_revision':saved['revision']}),ensure_ascii=False,indent=2))
    finally:
        app.close()

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','retry-prepare','submit'])
    args=parser.parse_args()
    {'prepare':prepare,'retry-prepare':retry_prepare,'submit':submit}[args.action]()
