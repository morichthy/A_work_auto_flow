"""实际阅读仪表。AI间隔含排队、调度和工具交互，非纯模型推理。
脚本入口前启动与工具传输须宿主外测。prepare共用进程但每事件新Coordinator。
"""
import time
ENTRY_UTC_NS=time.time_ns()
ENTRY_MONO_NS=time.perf_counter_ns()
import argparse
import json
import os
from pathlib import Path
import sys
import uuid
RUN=Path(__file__).resolve().parents[1]
ROOT=RUN.parents[3]
OUT=RUN/'.run-captures'/'latency'
STATE=OUT/'state.json'
STDLIB_NS=time.perf_counter_ns()-ENTRY_MONO_NS

def encode(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False)

def write(path,value):
    # 完整编码后原子发布，不让扫描器看见空JSON。
    payload=encode(value)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.pending-'+uuid.uuid4().hex)
    temporary.write_text(payload,encoding='utf-8')
    temporary.replace(path)

def event(value):
    payload=encode(value)+'\n'
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'events.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(payload)
        stream.flush()

def timings(value,path=''):
    result={}
    if isinstance(value,dict):
        for k,v in value.items():
            name=path+'/'+k
            if isinstance(v,(int,float)) and any(s in k.lower() for s in ('time','elapsed','duration','_ms','_ns')):
                result[name]=v
            elif isinstance(v,(dict,list)):
                result.update(timings(v,name))
    elif isinstance(value,list):
        for i,v in enumerate(value): result.update(timings(v,path+'/'+str(i)))
    return result

def invoke(state,action,raw,actor,profile=False):
    print('[latency] '+action+' begin',file=sys.stderr,flush=True)
    utc,mono=time.time_ns(),time.perf_counter_ns()
    sys.path.insert(0,str(ROOT/'automation'/'scripts'))
    stamp=time.perf_counter_ns()
    from material_query.api import dispatch
    from material_query.coordinator import Coordinator
    imports=time.perf_counter_ns()-stamp
    key=str(utc)+'-'+actor+'-'+action
    profiler=None
    if profile:
        import cProfile
        profiler=cProfile.Profile()
        profiler.enable()
    stamp=time.perf_counter_ns()
    app=Coordinator(ROOT,access_owner_ids=state['access_owner_ids'])
    construction=time.perf_counter_ns()-stamp
    stamp=time.perf_counter_ns()
    try:
        result=dispatch(app,action,raw)
    finally:
        dispatch_ns=time.perf_counter_ns()-stamp
        stamp=time.perf_counter_ns()
        app.close()
        close_ns=time.perf_counter_ns()-stamp
        if profiler:
            profiler.disable()
            OUT.mkdir(parents=True,exist_ok=True)
            profiler.dump_stats(str(OUT/(key+'.prof')))
            import pstats
            stats=pstats.Stats(profiler)
            rows=[{'file':k[0],'line':k[1],'function':k[2],'calls':v[1],
                   'exclusive_s':v[2],'cumulative_s':v[3]} for k,v in stats.stats.items()]
            write(OUT/(key+'-profile.json'),{'cumulative':sorted(rows,key=lambda r:r['cumulative_s'],reverse=True)[:50],
                                           'exclusive':sorted(rows,key=lambda r:r['exclusive_s'],reverse=True)[:50]})
    stamp=time.perf_counter_ns()
    encoded=encode(result)
    size=len(encoded.encode('utf-8'))
    serialized=time.perf_counter_ns()-stamp
    consumed=result.get('consumed',{})
    previous=state.get('consumed',{})
    meta={'type':'call','action':action,'actor':actor,'profile':profile,'pid':os.getpid(),
          'entry_utc_ns':ENTRY_UTC_NS,'entry_monotonic_ns':ENTRY_MONO_NS,
          'start_utc_ns':utc,'start_monotonic_ns':mono,'stdlib_import_ns':STDLIB_NS,
          'backend_import_ns':imports,'coordinator_ns':construction,'dispatch_ns':dispatch_ns,
          'close_ns':close_ns,'serialize_ns':serialized,'status':result.get('status'),'code':result.get('code'),
          'response_chars':len(encoded),'response_utf8_bytes':size,'consumed':consumed,
          'consumed_delta':{k:v-previous.get(k,0) for k,v in consumed.items()},
          'coverage_timings':timings(result.get('value',{})),
          'request_file':key+'-request.json','response_file':key+'-response.json'}
    stamp=time.perf_counter_ns()
    write(OUT/meta['request_file'],raw)
    write(OUT/meta['response_file'],result)
    if action!='reading-template':
        # 失败回执可能返回零账本，不能覆盖已知累计基线。
        if consumed and all(v >= previous.get(k,0) for k,v in consumed.items()):
            state['consumed']=consumed
        if result.get('status') in {'ok','partial'}:
            value=result.get('value') or {}
            if 'revision' in value: state['revision']=value['revision']
        write(STATE,state)
    meta.update(persist_ns=time.perf_counter_ns()-stamp,end_utc_ns=time.time_ns(),
                end_monotonic_ns=time.perf_counter_ns(),script_elapsed_ns=time.perf_counter_ns()-ENTRY_MONO_NS)
    event(meta)
    print('[latency] '+action+' '+str(result.get('status'))+' dispatch_s='+str(dispatch_ns/1e9),file=sys.stderr,flush=True)
    if result.get('status') not in {'ok','partial'}:
        print(encode({'failure':meta,'response':result}))
        raise SystemExit(2)
    return result

def prepare(args):
    if STATE.exists(): raise RuntimeError('已有固定RS，不得重置预算；重做需新Run')
    sys.path.insert(0,str(ROOT/'automation'/'scripts'))
    stamp=time.perf_counter_ns()
    from workspace_settings import read
    import_ns=time.perf_counter_ns()-stamp
    utc,mono=time.time_ns(),time.perf_counter_ns()
    settings=read(ROOT)['settings']
    policy=settings['collaboration']
    event({'type':'settings','start_utc_ns':utc,'start_monotonic_ns':mono,
           'entry_utc_ns':ENTRY_UTC_NS,'entry_monotonic_ns':ENTRY_MONO_NS,
           'import_ns':import_ns,'read_policy_ns':time.perf_counter_ns()-mono,
           'policy':policy,'reading_defaults':settings['reading'],'end_utc_ns':time.time_ns()})
    state={'source_owner':args.source_owner,'binding_owner':'PRJ-ARCHITECTURE-EVOLUTION'}
    # 只读取身份元数据。明确owner/research字段或来源登记Run且位于来源目录下，才构成归属。
    from memory.owners import list_owners
    utc,mono=time.time_ns(),time.perf_counter_ns()
    catalog=list_owners(ROOT,metadata_only=True)
    source=next(row for row in catalog if row['owner_id']==args.source_owner)
    source_dir=Path(source['native_ref']['path']).parent
    declared=set(source['native_data'].get('exploration_run_ids',[]))
    runs=[]
    for row in catalog:
        if row['owner_type']!='run': continue
        native=row['native_data']
        explicit=any(native.get(field)==args.source_owner for field in ('owner_id','research_id'))
        registered=row['owner_id'] in declared and Path(row['native_ref']['path']).is_relative_to(source_dir)
        if explicit or registered: runs.append(row['owner_id'])
    state['access_owner_ids']=sorted(set([args.source_owner,state['binding_owner'],*runs]))
    event({'type':'owner_metadata','start_utc_ns':utc,'start_monotonic_ns':mono,
           'metadata_ns':time.perf_counter_ns()-mono,'end_utc_ns':time.time_ns(),
           'source_run_ids':sorted(runs),'access_owner_ids':state['access_owner_ids']})
    template=invoke(state,'reading-template',{},'main')['value']
    # 对照只允许显式改变这两个真实请求字段；默认不覆盖工作区设置。
    if args.result_limit is not None:
        template['query']['result_limit']=args.result_limit
    if args.rerank_candidate_limit is not None:
        template['reranking']['candidate_limit']=args.rerank_candidate_limit
    # 独立诊断显式扩大预算；不修改既有RS，不声称这是优化。
    if args.output_chars is not None: template['query']['budget']['output_chars']=args.output_chars
    if args.read_bytes is not None: template['query']['budget']['read_bytes']=args.read_bytes
    from material_query.contracts import QueryRequest
    from material_query.validation import parse
    from material_query.reranking import settings as ranking_settings
    parse(template['query'],QueryRequest)
    ranking_settings(template['reranking'])
    event({'type':'variant','utc_ns':time.time_ns(),'result_limit':template['query']['result_limit'],
           'reranking':template['reranking'],'budget':template['query']['budget'],
           'explicit_overrides':{'result_limit':args.result_limit,'rerank_candidate_limit':args.rerank_candidate_limit,'output_chars':args.output_chars,'read_bytes':args.read_bytes}})
    scope=template['query']['scope']
    scope['owner_ids']=[args.source_owner]
    template['query']['scope_ceiling']=json.loads(encode(scope))
    template['query']['scope_ceiling']['owner_ids']=state['access_owner_ids']
    template['query']['question']=args.question
    template.update(goal=args.question,owner_id=state['binding_owner'],
                    conditions=['仅阅读固定来源Owner；保留公式、强抵消边界与实测依据，不递归委派。'])
    state.update(session_id=template['session_id'],scope=scope,scope_ceiling=template['query']['scope_ceiling'],question=args.question)
    invoke(state,'reading-start',template,'main')
    delegated=invoke(state,'reading-delegate',{'session_id':state['session_id'],'host_supports_subagents':True},'main')
    write(OUT/'empty.json',{})
    print(encode({'state':state,'delegate':delegated,'driver':str(Path(__file__).resolve())}))

def call(args):
    state=json.loads(STATE.read_text(encoding='utf-8'))
    path=Path(args.request_path).resolve()
    if not path.is_relative_to(RUN): raise RuntimeError('请求文件必须位于本Run')
    if args.action not in {'reading-view','reading-delegate','reading-handoff','reading-recall','reading-page','reading-read','reading-note','reading-decide','reading-resume'}:
        raise RuntimeError('本仪表不允许建立其他会话或管理动作')
    if args.profile and args.action not in {'reading-view','reading-handoff'}:
        raise RuntimeError('诊断profile仅允许同RS只读view/handoff')
    raw=json.loads(path.read_text(encoding='utf-8-sig'))
    raw.setdefault('session_id',state['session_id'])
    if raw['session_id']!=state['session_id'] or ('scope' in raw and raw['scope']!=state['scope']):
        raise RuntimeError('RS或范围不匹配固定授权')
    if args.action not in {'reading-view','reading-delegate','reading-handoff'}:
        raw.setdefault('expected_revision',state['revision'])
        raw.setdefault('request_id',str(uuid.uuid4()))
    print(encode(invoke(state,args.action,raw,args.actor,args.profile)))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    p.add_argument('--source-owner',required=True)
    p.add_argument('--question',required=True)
    p.add_argument('--result-limit',type=int,default=None)
    p.add_argument('--rerank-candidate-limit',type=int,default=None)
    p.add_argument('--output-chars',type=int,default=None)
    p.add_argument('--read-bytes',type=int,default=None)
    p=sub.add_parser('call')
    p.add_argument('action')
    p.add_argument('request_path')
    p.add_argument('--actor',choices=['reader','main'],default='reader')
    p.add_argument('--profile',action='store_true')
    p=sub.add_parser('mark')
    p.add_argument('label')
    p.add_argument('--actor',choices=['reader','main'],default='main')
    sub.add_parser('report')
    args=parser.parse_args()
    if args.command=='prepare': prepare(args)
    elif args.command=='call': call(args)
    elif args.command=='mark':
        row={'type':'mark','label':args.label,'actor':args.actor,'utc_ns':time.time_ns(),
             'monotonic_ns':time.perf_counter_ns(),'entry_utc_ns':ENTRY_UTC_NS,'pid':os.getpid()}
        event(row)
        print(encode(row))
    else:
        rows=[json.loads(line) for line in (OUT/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        report={'events':rows,'limitations':'AI间隔包含调度/排队/交互，非纯模型推理；启动前与工具传输须外测；profile非baseline。'}
        write(OUT/'report.json',report)
        print(encode(report))

if __name__=='__main__': main()





