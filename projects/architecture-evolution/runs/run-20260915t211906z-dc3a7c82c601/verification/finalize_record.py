"""Freeze completed release evidence into the local Run, then register exact files.

Only run after publication and coverage verification. Existing snapshots are
never replaced; the large distribution ZIPs remain at their audited paths.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = ROOT / 'projects/architecture-evolution/runs/run-20260915t211906z-dc3a7c82c601'
RUN_ID = 'RUN-20260915T211906Z-DC3A7C82C601'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--summary', type=Path, required=True)
args = parser.parse_args()
summary = json.loads(args.summary.read_text(encoding='utf-8'))
publication = json.loads((OUT / 'publication.json').read_text(encoding='utf-8'))
assert publication['draft'] is False
assert summary['backend']['covered'] == summary['backend']['discovered'] == 610
assert summary['backend']['missing'] == []
target = RUN / 'verification'
target.mkdir(exist_ok=False)
for path in sorted(OUT.iterdir()):
    if path.is_file() and (path.suffix in {'.json', '.jsonl', '.log', '.txt', '.py'} or path.name == 'release-notes.md'):
        shutil.copy2(path, target / path.name)
failure_dir = OUT / 'e2e-deferred-10k-failure-artifact'
if failure_dir.exists():
    shutil.copytree(failure_dir, target / failure_dir.name)
offline = OUT / 'source-preview/.local/release-validation/8b6d2fa8b0b04de2873e94fb0f34df95'
for name in ('verification.json', 'fresh-offline-install.log', 'offline-upgrade.log', 'receiver-repack.log', 'dependency-rollback.log'):
    shutil.copy2(offline / name, target / ('offline-' + name))
data_path = RUN / 'run.json'
data = json.loads(data_path.read_text(encoding='utf-8'))
data.update(status='failed' if summary['backend']['failed'] else 'succeeded',
            ended_at=datetime.now(timezone.utc).isoformat(),
            question='核对当前框架版本的源码、依赖、旧工作区保护及正式发布结果。',
            code={'commit': publication['commit'], 'dirty': True},
            parameters={'release': 'v0.3.0', 'scope': 'framework-only; local synthetic Windows x64 verification'},
            metrics={'backend_tests': 610, 'backend_passed': summary['backend']['passed'],
                     'backend_failed': summary['backend']['failed'], 'frontend_passed': 38, 'browser_passed': 16},
            quality_results=[
                {'check': 'full-backend-coverage', 'status': 'passed', 'required': True},
                {'check': 'full-backend-tests', 'status': 'failed' if summary['backend']['failed'] else 'passed', 'required': True},
                {'check': 'frontend-38-typecheck-and-16-normal-browser', 'status': 'passed', 'required': True},
                {'check': 'actual-archive-offline-install-upgrade-repack-rollback', 'status': 'passed', 'required': True},
                {'check': 'source-dependency-and-remote-asset-hashes', 'status': 'passed', 'required': True}],
            conclusion='v0.3.0已正式发布；源码、依赖及远端附件核验通过。后端既有B01失败和误触发的暂缓规模超时分别保留。',
            limitations=['同机Windows x64隔离合成验证，不代表第二物理机、真实业务或科学复核。',
                        'Run在部分验证已开始后建立，未补造开始时间。初始工作树源码与最终发行文件一致，业务数据未提交。',
                        '完整后端分段执行并按唯一ID核对；中断、调用错误与环境权限诊断保留，不能当作软件通过。',
                        '历史B01冻结夹具清单失败未改写为通过；暂缓规模场景误执行超时，普通浏览器重复复验中止。'])
data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
artifacts = sorted(path for path in target.rglob('*') if path.is_file()) + [RUN / 'RESULTS.md']
assert all(path.is_file() for path in artifacts)
command = [sys.executable, str(ROOT / 'automation/scripts/workspace_cli.py'), 'run-register', RUN_ID]
for path in artifacts:
    command += ['--artifact', path.relative_to(ROOT).as_posix()]
for name in ('framework-source-v0.3.0.zip', 'dependencies-windows-x64.zip'):
    command += ['--input', 'dist/release-v0.3.0/' + name]
result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
(OUT / 'final-registration.json').write_text(result.stdout, encoding='utf-8')
if result.returncode:
    print(result.stderr)
    raise SystemExit(result.returncode)
print(json.dumps({'run_id': RUN_ID, 'registered_artifact_files': len(artifacts), 'publication': publication['url']}))
