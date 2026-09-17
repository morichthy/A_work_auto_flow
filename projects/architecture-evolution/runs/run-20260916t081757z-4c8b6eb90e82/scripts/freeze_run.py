"""冻结本次源码和验证回执，再登记新 Run；不会修改任何历史 Run。"""
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
import workspace_settings


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    meta = json.loads((RUN / 'run.json').read_text(encoding='utf-8'))
    if meta['artifacts']:
        raise RuntimeError('已有固定产物，不覆盖或重新登记改变后的证据')
    verify = RUN / 'verification'
    verify.mkdir(exist_ok=True)
    # 在全部实现/构建完成后调用同一分发收集器，核验资源和源码指纹匹配。
    files = deployment.framework_files(ROOT)
    assert 'automation/scripts/workspace_settings.py' in files
    assert 'workspace-settings.json' not in files
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    with zipfile.ZipFile(verify / 'framework-source-snapshot.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(ROOT / name, name)
    write(verify / 'source-manifest.json', {'files': hashes, 'private_settings_distributed': False})
    write(verify / 'formal-settings-readonly.json', workspace_settings.read(ROOT))
    # 原始失败日志与成功复验一起保存，不把失败覆盖成成功。
    shutil.copytree(ROOT / '.local/capability-settings-tests', verify / 'tests')
    shutil.copyfile(ROOT / 'projects/architecture-evolution/plans/subagent-requirements-20260916.md',
                    verify / 'plan-at-freeze.md')
    meta.update(status='succeeded', started_at=meta['created_at'],
        ended_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        question='如何配置子Agent能力偏好，保留低能力默认、旧配置及源码/私人设置的发布边界？',
        keywords=['workspace-settings', 'subagent', '能力偏好', '升级保护'],
        parameters={'field': 'collaboration.subagent_requirements', 'trimmed_length_range': [1, 2000],
                    'schema_version': 1, 'default_requirements': workspace_settings.read(ROOT)['defaults']['collaboration']['subagent_requirements']},
        metrics={'backend_related_tests': 25, 'settings_component_tests': 10, 'settings_browser_tests': 2,
                 'windows_setup_tests': 18},
        conclusion='设置页与后端已支持自由文本能力要求，默认较低能力/低成本/低推理；旧文件只读兼容，自定义偏好在委派和升级中保留。',
        quality_results=[{'name': 'targeted_software', 'status': 'passed',
                          'scope': '后端、设置组件、真实浏览器与Windows扩展旧工作区setup；首次失败与修复复验回执保留。'}],
        limitations=['宿主决定实际模型；没有可用模型时配置文本不能自行安装或调用模型。',
                     '本轮没有重跑实际材料阅读质量/费用基准，沿用前阶段固定证据的历史适用范围。',
                     '无新增AI配置解析调用；未以此推断端到端检索延迟或总AI费用改善。',
                     '仅本机Windows x64合成升级验收；第二物理机与用户业务验收未执行；未推送发布。'])
    write(RUN / 'run.json', meta)
    artifacts = [str(p.relative_to(ROOT)) for folder in (verify, RUN / 'baseline')
                 for p in folder.rglob('*') if p.is_file()]
    artifacts.append(str((RUN / 'RESULTS.md').relative_to(ROOT)))
    inputs = [str(p.relative_to(ROOT)) for p in (RUN / 'scripts').glob('*.py')]
    result = run_capture.register(ROOT, meta['run_id'], inputs=inputs, artifacts=artifacts)
    write(RUN / 'registration-summary.json', result)
    print(json.dumps({'status': result['status'], 'source_files': len(files),
                      'artifacts': len(artifacts)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
