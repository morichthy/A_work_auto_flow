"""一次性归档本轮真实验证；只处理本Run及其明确现行导航，不改历史记忆。"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parent.parent

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def main():
    final_log = (RUN / 'verification/material-regression.log').read_text(encoding='utf-8-sig')
    # unittest总结之后可能还有stdout中的真实模型指标，不能要求文件以OK结尾。
    if '\nOK\n' not in final_log or '\nFAILED (' in final_log:
        raise RuntimeError('材料相关回归尚未完成或未通过，不登记成功')
    import re
    count, elapsed = re.findall(r'Ran (\d+) tests in ([\d.]+)s', final_log)[-1]
    results = RUN / 'RESULTS.md'
    body = results.read_text(encoding='utf-8').replace(
        '材料查询关联回归结果以`verification/material-regression.log`最终回执为准。',
        f'材料查询关联回归{count}项通过（{elapsed}秒），含实际dense、组包、范围、权限和证据边界；日志为`verification/material-regression.log`。')
    body = body.replace('按影响维护README、ARCHITECTURE、CORE、docs索引、TESTING、DEVELOPMENT_HISTORY，',
        '按影响维护README、ARCHITECTURE、CORE、docs索引、TESTING与DEVELOPMENT_HISTORY；DOCUMENTATION_MAINTENANCE核对后沿用，')
    results.write_text(body, encoding='utf-8')
    plan = ROOT / 'projects/architecture-evolution/plans/retrieval-ranking-latency-20260916.md'
    text = plan.read_text(encoding='utf-8')
    text = text.replace('# 检索排序与延迟诊断讨论\n', '# 检索排序与延迟诊断讨论\n\n当前：推荐组合的首轮实现和验证已完成，见下方实施清单及收口。本页前半部分保留开发授权前的只读诊断。\n', 1)
    text = text.replace('| 进行中 |', '| 已完成；固定基线先于实现 |').replace('| 待实现 |', '| 已实现并验证 |')
    text = text.replace('| 待执行 |', '| 已执行；结果及适用边界见Run |')
    text += '\n## 实施收口（2026-09-16）\n\n已按B1→F1–F6→D1/V1–V3完成本轮正文/条件/CE排序演进，完整方法、对照、失败修复与Windows离线交付见[RESULTS](../runs/run-20260916t035620z-93aca3a94bae/RESULTS.md)。原诊断和历史指标保留时点，不作为新实现事实。\n\n变化处置：新增有界正文输入与独立提供器/条件模块；分页固定模型、累计费用和撤权边界修复；六份现行文档按影响核对，material-query Skill同步。原设计文稿保留历史，本轮新增独立技术结果。业务效果、长文窗口、非空无答案和规模p50/p95仍待验收；没有声称CE使冷启动提速。\n'
    plan.write_text(text, encoding='utf-8')
    for relative, marker, paragraph in [
        ('projects/architecture-evolution/README.md', '## 从这里继续\n',
         '\n2026-09-16已完成[召回排序演进](plans/retrieval-ranking-latency-20260916.md)：有界RRF候选、固定正文/必要定义、离线Cross-encoder与显式条件特征接入AI阅读；[完整结果与验证](runs/run-20260916t035620z-93aca3a94bae/RESULTS.md)保留开发/留出对照、真实CLI及离线安装升级恢复。小样本不代表业务达标，冷启动与长文窗口继续评估。本轮未发布。\n'),
        ('context/NOW.md', '## 当前开发\n',
         '\n2026-09-16正文/条件/CE重排已接入新AI阅读模板（auto，旧RS保持off），真实离线模型与Windows分发链已验证。见[实施结果](../projects/architecture-evolution/runs/run-20260916t035620z-93aca3a94bae/RESULTS.md)。本轮新增独立可选重排模型，不改变384维召回索引；业务效果、长文窗口与规模延迟仍待验收，尚未公开发布。\n')]:
        p = ROOT / relative
        p.write_text(p.read_text(encoding='utf-8').replace(marker, marker + paragraph, 1), encoding='utf-8')
    p = ROOT / 'context/NOW.md'
    p.write_text(p.read_text(encoding='utf-8').replace('本次没有更换模型或依赖。标准模型自动迁移只限约定名称/路径与兼容384维。',
        '召回向量标准模型自动迁移限约定名称/路径与兼容384维；2026-09-16新增的CE重排模型是独立可选组件，见上方结果。'), encoding='utf-8')
    project_path=ROOT/'projects/architecture-evolution/project.json'
    project=json.loads(project_path.read_text(encoding='utf-8'))
    project['active_plan']='plans/retrieval-ranking-latency-20260916.md'
    project['updated_at']='2026-09-16'
    project['non_goals']=[('不替换384维召回编码器与存储引擎；正文重排使用独立可选模型'
                          if value=='本轮不切换检索算法或存储引擎' else value) for value in project.get('non_goals',[])]
    write_json(project_path,project)
    run_path = RUN / 'run.json'
    run = json.loads(run_path.read_text(encoding='utf-8'))
    run.update(status='succeeded', ended_at=datetime.now(timezone.utc).isoformat(),
        question='在保留各层候选覆盖、权限及费用边界下改善前列排序，并测量新增成本。',
        keywords=['retrieval','Cross-encoder','reranking','显式条件','offline-model'],
        parameters={'candidate_limit':30,'batch_size':16,'max_length':512,'baseline':'frozen-development-before-implementation'},
        metrics={'development_recall_at_6':1.0,'development_ndcg_at_6':0.832659408538247,
                 'holdout_recall_at_6':1.0,'holdout_ndcg_at_6':0.9914211139533698},
        quality_results=[{'check':name,'status':'passed','required':True} for name in
                         ['reading-40','reranking-unit-11',f'material-{count}','dependency-13','real-setup-18','offline-install-upgrade-repack-rollback','public-cli-ai-reading']],
        conclusion='已实现正文/条件/CE重排及离线交付；冻结小样本改善前列质量，尚不代表业务质量达标或端到端提速。',
        limitations=['小型合成题集','条件自然语言多为unknown','单候选超过512 token全窗停止CE','独立CLI不共享加载缓存','第二物理机未验收','未全仓库回归，既有B01问题保留'])
    # 指标以真正实验JSON为唯一数值来源，避免人工复制小数误差。
    for split, filename in [('development','reranking-development-ablation.json'),('holdout','reranking-holdout-final.json')]:
        aggregate=json.loads((RUN/'verification'/filename).read_text(encoding='utf-8'))['aggregate']['ce_context_conditions']
        run['metrics'][split+'_recall_at_6']=aggregate['recall_at_6']
        run['metrics'][split+'_ndcg_at_6']=aggregate['ndcg_at_6']
    write_json(run_path, run)
    (RUN / 'README.md').write_text('# 召回排序演进\n\n完整方法、结果、失败与验证范围见[RESULTS](RESULTS.md)。本Run执行状态为软件验证成功，不等于科学复核或真实业务验收。\n', encoding='utf-8')
    # 小型代码快照供复核；它不是可安装发行包，不包含模型、原件或业务库。
    import zipfile
    names = ['.gitignore','README.md','ARCHITECTURE.md',
        'automation/dependency-bundle.ps1','automation/scripts/dependency_bundle.py','automation/scripts/deployment.py',
        'automation/scripts/material_query/coordinator.py','automation/scripts/material_query/reading.py',
        'automation/scripts/material_query/reranking.py','automation/scripts/material_query/conditions.py',
        'automation/scripts/material_query/cross_encoder.py','automation/testing/catalog.json',
        'automation/tests/test_dependency_bundle.py','automation/tests/verify_dependency_release.py',
        'automation/tests/test_reading_reranking.py','automation/tests/test_reading_reranking_integration.py',
        'automation/tests/test_material_conditions.py','automation/tests/test_material_cross_encoder.py',
        'automation/tests/test_retrieval_reranking_baseline.py','automation/tests/evaluate_retrieval_reranking.py',
        'automation/tests/fixtures/retrieval_reranking/fixture.json','automation/workflows/material-query/SKILL.md']
    names += ['docs/'+name+'.md' for name in ['CORE','README','TESTING','DEVELOPMENT_HISTORY','AI_READING',
        'MATERIAL_QUERY','MEMORY_STORAGE_EXPLAINED','DEPENDENCY_RELEASE','UPGRADE_TESTING','DOCUMENTATION_MAINTENANCE']]
    manifest = {'source_commit':run['code']['commit'],'dirty':True,'scope':'selected source snapshot, not an installable release',
                'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}}
    write_json(RUN/'verification/implementation-source-manifest.json',manifest)
    with zipfile.ZipFile(RUN/'verification/implementation-source-snapshot.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for name in names: archive.write(ROOT/name,name)
    print(json.dumps({'material_tests':int(count),'elapsed_seconds':float(elapsed),'run_status':run['status']},ensure_ascii=False))

if __name__ == '__main__':
    main()
