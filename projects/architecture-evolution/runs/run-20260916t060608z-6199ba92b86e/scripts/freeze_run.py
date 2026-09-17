"""冻结本次最终源码/结果并通过公开Run登记入口保存证据；不修改旧Run。"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import deployment
import run_capture


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    meta = json.loads((RUN / 'run.json').read_text(encoding='utf-8'))
    if meta['artifacts']:
        raise RuntimeError('Run已经登记，不覆盖固定证据')
    verify = RUN / 'verification'
    # 与真实源码升级采用同一收集器，同时核验前端现存源码/构建指纹。
    files = deployment.framework_files(ROOT)
    required = {'automation/scripts/material_query/reading_delegation.py',
                'automation/tests/test_reading_delegation.py',
                'automation/tests/test_reading_handoff_view.py'}
    if not required <= set(files):
        raise RuntimeError('新增后端/测试未进入源码分发')
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    snapshot = verify / 'framework-source-snapshot.zip'
    with zipfile.ZipFile(snapshot, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(ROOT / name, name)
    write(verify / 'source-manifest.json', {'files': hashes,
        'snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        'windows_portability': 'Windows x64 CLI/HTTP通过，分发收集和既有前端资源指纹通过；本轮未更改依赖/安装/缓存/前端。'})
    shutil.copyfile(ROOT / 'projects/architecture-evolution/plans/reading-delegation-20260916.md',
                    verify / 'plan-at-freeze.md')
    metrics = json.loads((verify / 'ai-reading-size-report.json').read_text(encoding='utf-8'))
    meta.update(status='succeeded', started_at=meta['created_at'],
        ended_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        question='如何由独立低成本子Agent完成材料检索与完整阅读，让主Agent仅使用有界且可追溯的reading note？',
        keywords=['subagent', 'reading-note', '上下文预算', '固定引用'],
        parameters={'handoff_default_max_chars': 12000, 'ai_handoff_max_chars': 6000,
                    'reader_model': 'gpt-5.6-terra', 'reader_reasoning': 'low', 'reader_fork_turns': 'none'},
        metrics={'distinct_reading_tests_passed': 52, **metrics},
        quality_results=[{'name': 'reading_software', 'status': 'passed', 'scope': '41既有+11新增，分次相关验证'},
                         {'name': 'actual_ai', 'status': 'passed_after_revision', 'scope': '独立reader合成验收，首版漏项补回；AI自查非用户认可'}],
        conclusion='已接入宿主委派/单Agent回退与同RS有界笔记交接；52项不同阅读测试有通过证据，实际低成本reader修订后保留必要细节。',
        limitations=['未实现任意宿主内置AI调度；宿主须实际提供工具并遵守Skill。',
                     '字符体积不等于token/总费用/端到端延迟；独立审查成本未计。',
                     '真实合成验收dense不可用、候选窗口未完；不证明全库覆盖或业务正确率。',
                     '首版笔记出现语义漏项，已保留并补回；仍需按任务核对关键细节。',
                     '第二物理机、其他宿主和人工业务验收未执行；本轮未发布。'])
    # 这是本轮尚未固定的新Run元数据；随后登记并作为规范Memory来源冻结。
    write(RUN / 'run.json', meta)
    artifacts = [str(p.relative_to(ROOT)) for p in verify.rglob('*') if p.is_file()]
    artifacts.append(str((RUN / 'RESULTS.md').relative_to(ROOT)))
    inputs = [str(p.relative_to(ROOT)) for p in (RUN / 'scripts').glob('*.py')]
    result = run_capture.register(ROOT, meta['run_id'], inputs=inputs, artifacts=artifacts)
    write(RUN / 'registration-summary.json', result)
    print(json.dumps({'status': result['status'], 'source_files': len(files),
                      'artifacts': len(artifacts), 'inputs': len(inputs)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
