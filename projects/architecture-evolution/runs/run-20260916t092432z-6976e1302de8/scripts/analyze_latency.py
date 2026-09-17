"""读取三次实验固定计时与响应，只输出数值分析，不回显材料正文。"""
import csv
import io
import json
from pathlib import Path
import uuid
ROOT=Path(__file__).resolve().parents[5]
SLUGS=['run-20260916t085438z-3e40d5ed8471','run-20260916t091635z-effbef761124','run-20260916t092432z-6976e1302de8']
PHASES=['stdlib_import_ns','backend_import_ns','coordinator_ns','dispatch_ns','close_ns','serialize_ns','persist_ns']

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def chars(v): return len(json.dumps(v,ensure_ascii=False,allow_nan=False))
def write(p,v):
    t=p.with_name('.pending-'+uuid.uuid4().hex)
    t.write_text(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
    t.replace(p)

def sizes(v,path=''):
    result={'markdown_chars':0,'figure_data_url_chars':0,'markdown_fields':0,'figure_data_url_fields':0}
    if isinstance(v,dict):
        for k,x in v.items():
            if isinstance(x,str) and ('markdown' in k):
                result['markdown_chars']+=len(x); result['markdown_fields']+=1
            if isinstance(x,str) and (k=='data_url' or x.startswith('data:image/')):
                result['figure_data_url_chars']+=len(x); result['figure_data_url_fields']+=1
            if isinstance(x,(dict,list)):
                found=sizes(x,path+'/'+k)
                for k,n in found.items(): result[k]+=n
    elif isinstance(v,list):
        for x in v:
            found=sizes(x,path)
            for k,n in found.items(): result[k]+=n
    return result

def stamp(row,end=False):
    keys=['end_ms','returned_ms'] if end else ['start_ms','sent_ms']
    return next((row[k] for k in keys if isinstance(row.get(k),(int,float))),None)

def outer(p):
    if not p.exists(): p=p.parent/'raw'/p.name
    if not p.exists(): return {},[]
    value=read(p)
    if isinstance(value,list): return {},value
    return {k:v for k,v in value.items() if k.endswith('_ms') and isinstance(v,(int,float))},next((value[k] for k in ('events','outer_events') if isinstance(value.get(k),list)),[])

def main():
    analyzed=[]; timeline=[]
    for slug in SLUGS:
        run=ROOT/'projects/architecture-evolution/runs'/slug
        raw=run/'.run-captures/latency'
        events=[json.loads(x) for x in (raw/'events.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
        calls=[]; profiles=[]
        for e in events:
            if e.get('type')!='call': continue
            response=read(raw/e['response_file'])
            value=response.get('value') or {}
            s=sizes(value)
            item={k:e.get(k) for k in ('action','actor','profile','status','code','start_utc_ns','end_utc_ns','response_chars','response_utf8_bytes','consumed','consumed_delta')}
            item['phase_ms']={k.removesuffix('_ns')+'_ms':e.get(k,0)/1e6 for k in PHASES}
            item['top_level_json_chars']={k:chars(v) for k,v in response.items()}
            item['value_json_chars']=chars(value)
            item['value_component_json_chars']={k:chars(v) for k,v in value.items()}
            item['raw_string_sizes']=s
            item['handoff_context_markdown_chars']=len(value.get('context_markdown',''))
            coverage=e.get('coverage_timings',{})
            item['coverage_timings_ms']=coverage
            item['route_elapsed_sum_ms']=sum(v for k,v in coverage.items() if '/routes/' in k and k.endswith('/elapsed_ms'))
            item['ce_timings_ms']={name:sum(v for k,v in coverage.items() if '/ranking/' in k and k.endswith('/'+name)) for name in ('condition_ms','model_load_ms','inference_ms','total_ms','input_ms')}
            calls.append(item)
            timeline.append({'run':slug,'action':e['action'],'profile':e.get('profile',False),'status':e.get('status'),'start_utc_ns':e['start_utc_ns'],'end_utc_ns':e['end_utc_ns'],**item['phase_ms'],'response_chars':e['response_chars'],'figure_data_url_chars':s['figure_data_url_chars'],'markdown_chars':s['markdown_chars']})
            if e.get('profile'):
                pp=raw/e['response_file'].replace('-response.json','-profile.json')
                if pp.exists(): profiles.append({'action':e['action'],'top':read(pp)})
        rm,re=outer(raw/'reader-outer-events.json'); mm,me=outer(raw/'root-outer-events.json')
        envelopes=[]
        for source,rows in [('reader',re),('main',me)]:
            grouped={}
            for i,row in enumerate(rows):
                key=str(row.get('session_id')) if row.get('session_id') is not None else 'single-'+str(i)
                grouped.setdefault(key,[]).append(row)
            for key,rs in grouped.items():
                starts=[stamp(x) for x in rs if stamp(x) is not None]; ends=[stamp(x,True) for x in rs if stamp(x,True) is not None]
                if starts and ends:
                    lo,hi=min(starts),max(ends)
                    matching=[x for x in calls if lo*1e6<=x['start_utc_ns']<=hi*1e6]
                    envelopes.append({'source':source,'session_key':key,'labels':[r.get('label') for r in rs],
                                      'start_ms':lo,'end_ms':hi,'operation_envelope_ms':hi-lo,'last_exit_code':rs[-1].get('exit_code'),
                                      'matched_actions':[x['action'] for x in matching],
                                      'backend_dispatch_ms':sum(x['phase_ms']['dispatch_ms'] for x in matching),
                                      'note':'完整包络含poll间隙/稍晚poll；last_exit_code=null可能缺最终poll，不以wall总和替代。'})
        accepted=read(raw/'context-acceptance.json') if (raw/'context-acceptance.json').exists() else {}
        baseline=[x for x in calls if not x['profile']]
        note_start=next((stamp(r) for r in re if r.get('label')=='note_generation_start'),None)
        failed_note=next((r for r in re if 'note' in r.get('label','') and r.get('exit_code') not in (None,0)),None)
        note_api=next((x for x in baseline if x['action']=='reading-note' and x['status'] in ('ok','partial')),None)
        end_ms=accepted.get('context_accepted_ms')
        prepare_ms=min((r.get('entry_utc_ns',r.get('start_utc_ns',10**30)) for r in events if r.get('type') in ('settings','call')))/1e6
        note_stage={'explicit_start_ms':note_start,'failed_tool_start_ms':stamp(failed_note) if failed_note else None,
                    'success_api_start_ms':note_api['start_utc_ns']/1e6 if note_api else None,
                    'start_to_success_api_ms':note_api['start_utc_ns']/1e6-note_start if note_api and note_start else None,
                    'first_failed_tool_to_success_api_ms':note_api['start_utc_ns']/1e6-stamp(failed_note) if note_api and failed_note else None,
                    'meaning':'包含理解、草拟、工具错误修复和调度，不是纯推理耗时。'}
        observed={x['action'] for x in baseline if x['status'] in ('ok','partial')}
        analyzed.append({'run':slug,'calls':calls,'profile_details':profiles,'outer_envelopes':envelopes,
                         'imports_ms':{'stdlib_unique_pid_ms':sum(next(e.get('stdlib_import_ns',0) for e in events if e.get('pid')==pid and e.get('type')=='call') for pid in {e.get('pid') for e in events if e.get('type')=='call'})/1e6,
                                       'backend_call_import_ms':sum(e.get('backend_import_ns',0) for e in events if e.get('type')=='call' and not e.get('profile'))/1e6,
                                       'settings_import_ms':sum(e.get('import_ns',0) for e in events if e.get('type')=='settings')/1e6},
                         'missing_successful_stages':[a for a in ['reading-recall','reading-read','reading-note','reading-decide','reading-handoff'] if a not in observed],
                         'context_accepted':bool(accepted),'context_coverage_complete':accepted.get('coverage_complete'),
                         'prepare_entry_to_context_accepted_ms':end_ms-prepare_ms if end_ms else None,
                         'warm_followup_sent_to_context_accepted_ms':end_ms-mm['followup_sent_ms'] if end_ms and 'followup_sent_ms' in mm else None,
                         'reader_followup_received_to_context_accepted_ms':end_ms-rm['first_host_timestamp_ms'] if end_ms and 'first_host_timestamp_ms' in rm else None,
                         'context_received_to_accepted_ms':end_ms-accepted['context_received_ms'] if end_ms else None,
                         'note_stage':note_stage})
    dest=ROOT/'projects/architecture-evolution/runs'/SLUGS[-1]/'verification'
    dest.mkdir(exist_ok=True)
    write(dest/'analysis.json',{'runs':analyzed,'units':'所有*_ms为毫秒，*_ns为纳秒，chars为Python Unicode字符串长度，bytes为UTF8字节数。',
                              'limitations':['figure data_url与markdown计原字符串长度，不是JSON编码长度。','JSON分量大小不含父字段名/标点，不能简单求和为顶层体积。','packet统计递归覆盖value各packet，重复交付按实际重复计数。','coverage内部阶段可能重叠；不能把CE/input/routes直接相加为总耗时。','partial不表示完整覆盖；完整覆盖仅另列context_coverage_complete。','profile独立，不纳入baseline推断。','前两失败未进入完整阅读/笔记/主上下文；第三多变量诊断不能归因为优化。']})
    timeline.sort(key=lambda r:r['start_utc_ns'])
    buf=io.StringIO(newline=''); writer=csv.DictWriter(buf,fieldnames=list(timeline[0])); writer.writeheader(); writer.writerows(timeline)
    write(dest/'call-timeline.csv',buf.getvalue())
    print(json.dumps({'analysis':str(dest/'analysis.json'),'timeline':str(dest/'call-timeline.csv'),'calls':len(timeline)},ensure_ascii=False))

if __name__=='__main__': main()
