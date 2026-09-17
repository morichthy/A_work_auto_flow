"""只读计时元数据汇总，不导入业务API、不读取完整请求或响应。

用法：automation/python.ps1 本脚本 [--raw-dir DIR]
默认输入输出均在本Run/.run-captures/latency。测量完成后才运行。
"""
import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import uuid

RUN=Path(__file__).resolve().parents[1]
PHASES=('stdlib_import_ns','backend_import_ns','coordinator_ns','dispatch_ns','close_ns','serialize_ns','persist_ns')


def write_text(path,text):
    """先生成完整内容，再同目录原子发布。"""
    temporary=path.with_name('.pending-'+uuid.uuid4().hex)
    temporary.write_text(text,encoding='utf-8')
    temporary.replace(path)


def stamp(row,end=False):
    # 显式单位优先；Date.now字段按毫秒处理，不把monotonic当UTC。
    ns=('end_utc_ns','after_utc_ns','tool_end_utc_ns') if end else ('start_utc_ns','utc_ns','before_utc_ns','tool_start_utc_ns','entry_utc_ns')
    ms=('end_ms','after_ms','end_utc_ms','after_utc_ms','tool_end_ms','finished_ms','returned_ms') if end else ('start_ms','before_ms','start_utc_ms','before_utc_ms','tool_start_ms','started_ms','timestamp_ms','sent_ms')
    for key in ns:
        if isinstance(row.get(key),(int,float)): return int(row[key])
    for key in ms:
        if isinstance(row.get(key),(int,float)): return int(row[key]*1_000_000)
    return None


def utc(value):
    if value is None: return ''
    seconds,nano=divmod(value,1_000_000_000)
    return datetime.fromtimestamp(seconds,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')+f'.{nano:09d}Z'


def load_outer(path):
    if not path.exists(): return []
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(value,list): return value
    if isinstance(value,dict):
        for key in ('events','outer_events','calls','records'):
            if isinstance(value.get(key),list): return value[key]
        return [value]
    raise ValueError('外层事件应为对象或数组: '+str(path))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir',type=Path,default=RUN/'.run-captures'/'latency')
    args=parser.parse_args()
    raw=args.raw_dir.resolve()
    # 仅打开三个明示的元数据文件，不遍历目录也不加载response正文。
    events=[json.loads(line) for line in (raw/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    records=[{'source':'events.jsonl','sequence':i,'event':row} for i,row in enumerate(events)]
    outer={}
    for name in ('reader-outer-events.json','root-outer-events.json'):
        source_path=raw/name
        if not source_path.exists() and (raw/'raw'/name).exists(): source_path=raw/'raw'/name
        rows=[{k:v for k,v in row.items() if k not in {'output','stdout','stderr','response','request','content','text'}} for row in load_outer(source_path)]
        outer[name]=rows
        records.extend({'source':name,'sequence':i,'event':row} for i,row in enumerate(rows))
    records.sort(key=lambda r:(stamp(r['event']) is None,stamp(r['event']) or 0,r['source'],r['sequence']))
    columns=['source','sequence','type','actor','action','label','profile','start_utc','end_utc','start_utc_ns','end_utc_ns','event_wall_ms','status','code','response_chars','response_utf8_bytes',*PHASES,'coverage_timings','consumed_delta']
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=columns)
    writer.writeheader()
    for record in records:
        event=record['event']
        start,end=stamp(event),stamp(event,True)
        row={k:event.get(k,'') for k in columns}
        row.update(source=record['source'],sequence=record['sequence'],start_utc=utc(start),end_utc=utc(end),start_utc_ns=start,end_utc_ns=end,event_wall_ms=(end-start)/1e6 if start is not None and end is not None else '')
        for key in ('coverage_timings','consumed_delta'):
            row[key]=json.dumps(event.get(key,{}),ensure_ascii=False)
        writer.writerow(row)
    calls=[row for row in events if row.get('type')=='call']
    baseline=[row for row in calls if not row.get('profile',False)]
    diagnostic=[row for row in calls if row.get('profile',False)]
    baseline.sort(key=lambda row:stamp(row) or 0)
    gaps=[]
    for previous,current in zip(baseline,baseline[1:]):
        end,start=stamp(previous,True),stamp(current)
        if end is not None and start is not None:
            gaps.append({'previous_action':previous.get('action'),'next_action':current.get('action'),
                         'previous_actor':previous.get('actor'),'next_actor':current.get('actor'),
                         'start_utc_ns':end,'end_utc_ns':start,'gap_ms':(start-end)/1e6,
                         'meaning':'相邻调用之间的混合间隔，包含宿主调度、排队、人工/AI决策、请求写入与工具交互；不是纯模型推理时间。'})
    outer_spans=[]
    for name,rows in outer.items():
        for row in rows:
            start,end=stamp(row),stamp(row,True)
            if start is None or end is None: continue
            # 包含关系比仅按最近时间稳健：一个prepare外层可包含多个dispatch。
            matched=[call for call in calls if stamp(call) is not None and start <= stamp(call) <= end]
            dispatch_ms=sum(call.get('dispatch_ns',0) for call in matched)/1e6
            outer_spans.append({'source':name,'label':row.get('label'),'start_utc_ns':start,'end_utc_ns':end,
                                'tool_elapsed_ms':(end-start)/1e6,'exec_wall_time_seconds':row.get('wall_time_seconds',row.get('process_wall_seconds')),
                                'matched_actions':[call.get('action') for call in matched],
                                'dispatch_ms':dispatch_ms,'residual_ms':(end-start)/1e6-dispatch_ms,
                                'profile':any(call.get('profile',False) for call in matched),
                                'meaning':'残余含其他脚本阶段、启动、工具传输及调度，不是模型推理；未匹配动作不推断。'})
    # 长进程首次exec可能提前返回，后续poll沿session_id继续；另列联合跨度而不重复计为独立进程。
    session_groups={}
    for name,rows in outer.items():
        for row in rows:
            sid=row.get('session_id')
            if sid is not None:
                session_groups.setdefault((name,str(sid)),[]).append(row)
    process_spans=[]
    for (name,sid),rows in session_groups.items():
        starts=[stamp(row) for row in rows if stamp(row) is not None]
        ends=[stamp(row,True) for row in rows if stamp(row,True) is not None]
        if not starts or not ends: continue
        start,end=min(starts),max(ends)
        matched=[call for call in calls if stamp(call) is not None and start <= stamp(call) <= end]
        dispatch_ms=sum(call.get('dispatch_ns',0) for call in matched)/1e6
        process_spans.append({'source':name,'session_id':sid,'tool_event_count':len(rows),
                              'start_utc_ns':start,'end_utc_ns':end,'outer_span_ms':(end-start)/1e6,
                              'matched_actions':[call.get('action') for call in matched],
                              'dispatch_ms':dispatch_ms,'residual_ms':(end-start)/1e6-dispatch_ms,
                              'profile':any(call.get('profile',False) for call in matched),
                              'meaning':'从exec开始到最后poll返回的operation包络，包含poll间隙与稍晚poll；不将wall相加为执行时间。dispatch_ns才是backend测量。'})
    summary={'schema_version':1,'input_files':['events.jsonl',*outer],
             'baseline_call_count':len(baseline),'diagnostic_call_count':len(diagnostic),
             'baseline_phase_totals_ns':{phase:sum(row.get(phase,0) for row in baseline) for phase in PHASES},
             'baseline_response_chars':sum(row.get('response_chars',0) for row in baseline),
             'baseline_response_utf8_bytes':sum(row.get('response_utf8_bytes',0) for row in baseline),
             'baseline_calls':baseline,'profile_diagnostics':diagnostic,
             'non_call_events':[row for row in events if row.get('type')!='call'],
             'inter_call_gaps':gaps,'outer_events':outer,'outer_spans':outer_spans,'process_spans':process_spans,
             'unmapped_outer_timestamps':[{'source':r['source'],'sequence':r['sequence']} for r in records if stamp(r['event']) is None],
             'limitations':['script_elapsed_ns是进程内累计时间，prepare多个事件不得相加。',
                            'stdlib_import_ns在同一进程重复出现，阶段总和保留原始值用于比较，不能当不重叠总时长。',
                            'backend_import_ns不含已在settings事件导入的模块时间，settings.import_ns须单列。',
                            '原始coverage timings保留原字段单位，不能与dispatch直接相加。',
                            '外层工具耗时包含进程启动和传输；内部耗时不能代表模型推理。',
                            'profile诊断与baseline分开，失败调用按真实状态保留。']}
    write_text(raw/'timeline.csv',buffer.getvalue())
    write_text(raw/'summary.json',json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps({'timeline':str(raw/'timeline.csv'),'summary':str(raw/'summary.json'),'baseline_calls':len(baseline),'diagnostic_calls':len(diagnostic)},ensure_ascii=False))


if __name__=='__main__': main()



