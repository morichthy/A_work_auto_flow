"""固定最终框架源码与验证文件，登记到本Run；不包含本机模型/材料/设置。"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parent.parent
HERE = RUN / 'verification'
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import deployment
import evidence
import run_capture

files = deployment.framework_files(ROOT)
assert 'workspace-settings.json' not in files
snapshot = HERE / 'framework-source-snapshot.zip'
with zipfile.ZipFile(snapshot, 'x', zipfile.ZIP_DEFLATED) as archive:
    for relative in files:
        archive.write(ROOT / relative, relative)
manifest = {'schema_version': 1, 'scope': 'deployment.framework_files only, not an installable release or user data backup',
    'files': {relative: evidence.sha256(ROOT / relative) for relative in files},
    'archive_sha256': evidence.sha256(snapshot)}
(HERE / 'source-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

path = RUN / 'run.json'
run = evidence.read(path)
run.update(status='succeeded', started_at=run['created_at'], ended_at=datetime.now(timezone.utc).isoformat(),
    owner='Codex', question='怎样提供可配置检索默认值和无子Agent兼容，同时避免AI逐次解析设置？',
    parameters={'settings_schema': 1, 'cache_roots': 64, 'max_file_bytes': 65536, 'warm_reads': 2000},
    keywords=['workspace-settings', '配置缓存', '单Agent', '检索预算', 'CAS'],
    metrics={'settings_tests_passed': 13, 'reading_tests_passed': 41, 'component_tests_passed': 48,
             'browser_tests_passed': 2, 'upgrade_tests_passed': 18, 'warm_read_p95_ms': 0.7553},
    quality_results=[{'check': '软件及本机Windows升级', 'status': 'passed'},
                     {'check': '实际AI调用与截图', 'status': 'AI consistency check only'}],
    conclusion='统一设置已接入CLI/HTTP/工作台与新查询模板，旧RS预算固定；必要验证通过。',
    limitations=['单机合成验证，非第二物理机验收', '配置缓存微测不代表端到端检索加速',
                 '子Agent开关是工作区工作流策略，不是宿主工具硬禁用', '旧search/CTX参数保持原契约',
                 '未全仓库回归，既有B01问题保留', '未公开发布'])
path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
# 尚未产生的memory/closure回执不列入这次Run指纹，防止随后反向改动已引用Run。
artifacts = [RUN / 'RESULTS.md', *sorted(HERE.glob('*'))]
artifacts = [p for p in artifacts if p.is_file()]
inputs = sorted((RUN / 'scripts').glob('*.py'))
result = run_capture.register(ROOT, run['run_id'],
    inputs=[p.relative_to(ROOT).as_posix() for p in inputs],
    artifacts=[p.relative_to(ROOT).as_posix() for p in artifacts])
(RUN / 'capture-receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'registration': result, 'framework_files': len(files), 'artifacts': len(artifacts),
                  'snapshot_bytes': snapshot.stat().st_size}, ensure_ascii=False, indent=2))
