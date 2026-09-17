"""完成报告后冻结本次三个计时Run；默认不允许覆盖已登记证据。

本文件被导入或AST检查时无副作用。只有明确执行main才收集源码、更新本次
三个run.json并调用公开run_capture.register；不查询业务材料、不刷新索引。
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[5]
RUNS=[ROOT/'projects/architecture-evolution/runs'/slug for slug in (
    'run-20260916t085438z-3e40d5ed8471','run-20260916t091635z-effbef761124',
    'run-20260916t092432z-6976e1302de8')]
PLAN=ROOT/'projects/architecture-evolution/plans/reading-latency-20260916.md'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path,value):
    # 编码完成后再原子替换，避免登记目录扫描读到空JSON。
    encoded=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    temporary=path.with_name('.pending-'+uuid.uuid4().hex)
    temporary.write_text(encoded,encoding='utf-8')
    temporary.replace(path)


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def files_under(folder):
    # 只遍历三个明确实验容器；不采集源研究材料、其他Run或工作区数据库。
    return sorted(path for path in folder.rglob('*') if path.is_file()
                  and not any(part=='__pycache__' or part.startswith('.pending-') for part in path.parts))


def main():
    prepared=[]
    for index,run in enumerate(RUNS):
        meta=read(run/'run.json')
        if meta.get('artifacts') or meta.get('inputs'):
            raise RuntimeError('Run已有固定登记，拒绝改写：'+meta['run_id'])
        result=run/'RESULTS.md'
        metrics=read(run/'verification/metrics.json')
        text=result.read_text(encoding='utf-8-sig')
        if not text.strip(): raise RuntimeError('最终RESULTS为空：'+str(result))
        for required in (run/'.run-captures/latency/events.jsonl',run/'.run-captures/latency/summary.json',run/'.run-captures/latency/timeline.csv',PLAN):
            if not required.is_file(): raise RuntimeError('缺少最终证据：'+str(required))
        if (run/'registration-summary.json').exists(): raise RuntimeError('登记摘要已存在，需人工检查部分完成状态')
        prepared.append((run,meta,metrics,text))
    verify=RUNS[0]/'verification'
    snapshot=verify/'framework-source-snapshot.zip'
    manifest=verify/'source-manifest.json'
    if snapshot.exists() or manifest.exists(): raise RuntimeError('已有源码冻结产物；拒绝覆盖，请检查上次中断状态')
    # 只在正式执行时加载发行收集器。收集规则与框架分发一致，不打包业务数据。
    sys.path.insert(0,str(ROOT/'automation/scripts'))
    import deployment
    import run_capture
    source_files=deployment.framework_files(ROOT)
    hashes={name:sha(ROOT/name) for name in source_files}
    pending=snapshot.with_name('.pending-'+uuid.uuid4().hex)
    with zipfile.ZipFile(pending,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in source_files: archive.write(ROOT/name,name)
    # 写入期间若源码变化，拒绝登记不一致快照；保留临时产物供诊断。
    with zipfile.ZipFile(pending) as archive:
        if any(hashlib.sha256(archive.read(name)).hexdigest()!=digest for name,digest in hashes.items()):
            raise RuntimeError('打包期间源码变化，未发布快照')
    pending.replace(snapshot)
    write(manifest,{'files':hashes,'snapshot_sha256':sha(snapshot),
                    'scope':'当前受控framework source，三个Run共享同一固定版本；不含业务材料或运行依赖。',
                    'validation_boundary':'本次仅测量与仪表；未执行第二物理机迁移或发布验收。'})
    ended=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    ids=[meta['run_id'] for _,meta,_,_ in prepared]
    # 先写完三Run的元数据、计划、关系及冻结清单，之后才调用register。
    registrations=[]
    for index,(run,meta,metrics,result_text) in enumerate(prepared):
        verification=run/'verification'
        shutil.copyfile(PLAN,verification/'plan-at-freeze.md')
        events=[json.loads(line) for line in (run/'.run-captures/latency/events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        defaults=next((row.get('reading_defaults',{}) for row in events if row.get('type')=='settings'),{})
        variant=next((row for row in events if row.get('type')=='variant'),{})
        # 默认实验实际预算失败；对照仅明确完成整个workflow才成功。
        status='succeeded' if index==2 and metrics.get('workflow_completed') is True else 'failed'
        first_times=[row.get('entry_utc_ns',row.get('start_utc_ns',row.get('utc_ns'))) for row in events]
        first_times=[value for value in first_times if isinstance(value,int)]
        started=datetime.fromtimestamp(min(first_times)/1e9,timezone.utc).isoformat().replace('+00:00','Z') if first_times else meta['created_at']
        relationship={'baseline_run_id':ids[0],'bounded_candidate_run_id':ids[1],'expanded_budget_diagnostic_run_id':ids[2],
                      'kind':'默认配置、独立候选限流失败对照、显式扩大预算诊断；非重复随机性能试验或优化完成',
                      'instrument_failure':'基线verification/latency-attempt-01保留初始DENIED；未创建RS，不纳入正常查询baseline。',
                      'comparison_boundary':'对照复用已规划query；第三Run收紧结果与CE为1/1、减少英文变体、提高预算至服务器上限，属多变量最小闭环诊断；不能据E2E差推速度提升归因。','diagnostic_prepare_failure':'第三Run .run-captures/latency-attempt-01保留超SERVER_LIMITS的VALIDATION拒绝，未创建RS。'}
        write(verification/'run-relationship.json',relationship)
        meta.update(status=status,started_at=started,ended_at=ended,
                    question='浮点求和真实主题查询→AI交互→reading note→主Agent上下文的分阶段计时及瓶颈。',
                    keywords=list(dict.fromkeys([*meta.get('keywords',[]),'reading-latency','real-materials','budget-failure','bounded-candidates'])),
                    parent_run_ids=ids[:index] if index else meta.get('parent_run_ids',[]),
                    parameters={'reader_model':'gpt-5.6-terra','reader_reasoning':'low','reader_fork_turns':None if index==2 else 'none',
                                'reader_context':'warm followup from bounded experiment' if index==2 else 'fresh isolated reader',
                                'source_owner_id':'RES-FLOATING-POINT-SUMMATION','reading_defaults':defaults,
                                'variant':variant,'relationship':relationship},
                    metrics=metrics,conclusion=metrics.get('conclusion','本次计时结果与边界见固定RESULTS.md产物。'),
                    quality_results=[{'name':'actual_reading_workflow','status':'passed' if status=='succeeded' else 'failed',
                                      'scope':'真实RS工作流，以最终metrics.workflow_completed及固定回执为据；不是业务结论复核。'}],
                    limitations=['单主题单次运行，不能推断p95或全库性能。','AI调用间隔含调度、排队、工具交互，不是纯模型推理。',
                                 'profile单列诊断，不混入baseline；初始仪表DENIED保留。','第三Run扩大预算只用于观测后半段，不证明优化完成或默认配置可用。','Windows本机测量，未做第二物理机/业务人工验收。'])
        write(run/'run.json',meta)
        inputs=[relative(snapshot),relative(manifest),*[relative(path) for path in files_under(run/'scripts')]]
        artifacts=[relative(path) for path in files_under(verification) if path not in {snapshot,manifest}]
        artifacts += [relative(path) for path in files_under(run/'.run-captures/latency')]
        # 第三Run的未建RS超限prepare失败也作为不可变原始证据登记。
        if (run/'.run-captures/latency-attempt-01').exists():
            artifacts += [relative(path) for path in files_under(run/'.run-captures/latency-attempt-01')]
        artifacts += [relative(run/'RESULTS.md')]
        artifacts=sorted(set(artifacts))
        inventory=verification/'freeze-evidence-manifest.json'
        write(inventory,{'run_id':meta['run_id'],'inputs':{name:sha(ROOT/name) for name in inputs},
                         'artifacts':{name:sha(ROOT/name) for name in artifacts},'status':status,
                         'note':'清单不自哈希；run.json由公开登记入口管理，不作为自身固定artifact。'})
        artifacts.append(relative(inventory))
        registrations.append((run,meta['run_id'],inputs,artifacts))
    for run,run_id,inputs,artifacts in registrations:
        result=run_capture.register(ROOT,run_id,inputs=inputs,artifacts=artifacts)
        write(run/'registration-summary.json',result)
        print(json.dumps({'run_id':run_id,'status':result['status'],'inputs':len(inputs),'artifacts':len(artifacts)},ensure_ascii=False))


if __name__=='__main__': main()



