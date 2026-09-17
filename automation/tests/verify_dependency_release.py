"""按需实测发布包，不加入每次单元回归。输入 --bundle，输出本机 JSON 回执。

在全新中文/空格路径复制源码入口，清空 Node/Python PATH 与系统引导变量，
通过真实 setup.cmd 完成离线安装、含旧业务数据的升级、损坏依赖替换及恢复。
数据仅写 .local；不修改正式环境，不下载，不注册用户命令，不上传。
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import dependency_bundle as bundle
import deployment
sys.path.insert(0, str(Path(__file__).resolve().parent))
import upgrade_fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    args = parser.parse_args()
    archive = args.bundle.resolve()
    base = ROOT / '.local/release-validation' / uuid.uuid4().hex
    source = base / '源码 ZIP'
    source.mkdir(parents=True)
    for name in set(deployment.framework_files(ROOT)) | set(deployment.seed_files(ROOT)):
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    # 默认配置无外部来源，不能把开发者的检索路径带进实测。
    (source / 'retrieval/sources.json').write_text('{"schema_version":1,"sources":[]}', encoding='utf-8')
    cfg_path = source / 'retrieval/config.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    cfg['include_directories'] = ['knowledge', 'runs', 'core-algorithms']
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    windows = Path(os.environ['SystemRoot'])
    env = dict(os.environ, PATH=str(windows / 'System32') + ';' + str(windows / 'System32/WindowsPowerShell/v1.0'),
               USERPROFILE=str(base / 'empty-user'), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    env.pop('CODEX_WORKSPACE_PYTHON', None)
    evidence = {'bundle_sha256': bundle.sha(archive), 'platform': sys.platform,
                'scope': 'same physical Windows machine; isolated source and target directories; no system Python/Node lookup', 'checks': []}
    with zipfile.ZipFile(archive) as package:
        expected_files = json.loads(package.read(bundle.MANIFEST))['files']
    expected_reranker = {name: fingerprint for name, fingerprint in expected_files.items()
                         if name.startswith('services/reranker/')}
    def assert_reranker(root):
        # 精确核对实际安装的模型清单与每个模型字节，不以目录存在代替交付成功。
        for name, fingerprint in expected_reranker.items():
            if bundle.sha(root / name) != fingerprint:
                raise AssertionError('reranker fingerprint changed: ' + name)
        if expected_reranker:
            bundle.reranker_files(root)
    def execute(name, cwd, *options):
        started = time.monotonic()
        result = subprocess.run([str(windows / 'System32/cmd.exe'), '/d', '/c', 'setup.cmd', *options],
                                cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
        (base / (name + '.log')).write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
        evidence['checks'].append({'name': name, 'returncode': result.returncode, 'seconds': round(time.monotonic() - started, 3)})
        (base / 'verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(evidence['checks'][-1]), flush=True)
        if result.returncode:
            raise RuntimeError(f'{name} failed: {base / (name + ".log")}\n' + result.stderr[-1800:])
        return result
    execute('fresh-offline-install', source, '--bundle', str(archive))
    assert_reranker(source)
    # 将首次安装目录整体改名，模拟旧机台已有数据；新源码仍不含 runtime。
    target = base / '旧 工作区'
    source.rename(target)
    source.mkdir()
    for name in set(deployment.framework_files(ROOT)) | set(deployment.seed_files(ROOT)):
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    private = target / 'knowledge/private-note.md'
    private.parent.mkdir(parents=True, exist_ok=True)
    private.write_text('# Synthetic private note\nDo not publish this fixture.\n', encoding='utf-8')
    protected = upgrade_fixture.populate(target)
    before = {name: bundle.sha(target / name) for name in ['knowledge/private-note.md', 'retrieval/config.json', 'retrieval/sources.json', 'AGENTS.md']}
    # 新包应替换整个 runtime，不能保留旧环境未登记的模块；旧版本仍留在恢复目录。
    stale = target / 'services/qdrant/runtime/stale-package.py'
    stale.write_text('synthetic stale package', encoding='utf-8')
    reranker_before = None
    if expected_reranker:
        # 制造真实旧组件残留，确保整组件替换及 rollback 都实际涉及 CE。
        (target / bundle.RERANKER_MODEL / 'obsolete-model.bin').write_bytes(b'synthetic previous model')
        reranker_before = bundle.tree_state(target / 'services/reranker')
    execute('offline-upgrade', source, '--bundle', str(archive), '--target', str(target))
    assert_reranker(target)
    if expected_reranker and (target / bundle.RERANKER_MODEL / 'obsolete-model.bin').exists():
        raise AssertionError('stale reranker file remained live')
    upgrade_fixture.assert_preserved(target, protected)
    if stale.exists():
        raise AssertionError('stale package remained live')
    for name, digest in before.items():
        if bundle.sha(target / name) != digest:
            raise AssertionError('business/config changed: ' + name)
    if (target / 'services/qdrant/downloads').exists():
        raise AssertionError('receiver unexpectedly has original Python download cache')
    execute('receiver-repack', target, '--pack-dependencies', '--apply')
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(target / 'dist/dependencies-windows-x64.zip') as repacked:
        first = json.loads(original.read(bundle.MANIFEST))
        second = json.loads(repacked.read(bundle.MANIFEST))
        if first != second:
            raise AssertionError('receiver repack changed distribution identity')
        if expected_reranker and any(second['files'].get(name) != digest for name, digest in expected_reranker.items()):
            raise AssertionError('receiver repack lost reranker identity')
    # 首次安装和升级各有回执；选取记录旧 runtime 中合成残留的升级批次。
    receipt = next(p for p in (target / '.local/dependency-backups').glob('*/receipt.json')
                   if (p.parent / 'previous/services/qdrant/runtime/stale-package.py').exists())
    execute('dependency-rollback', source, '--bundle', str(archive), '--rollback-dependencies', str(receipt.parent))
    upgrade_fixture.assert_preserved(target, protected)
    if not stale.exists():
        raise AssertionError('dependency rollback did not restore previous runtime')
    if expected_reranker and bundle.tree_state(target / 'services/reranker') != reranker_before:
        raise AssertionError('dependency rollback did not restore previous reranker bytes')
    for name, digest in before.items():
        if bundle.sha(target / name) != digest:
            raise AssertionError('rollback changed business/config: ' + name)
    evidence['preserved'] = list(before)
    evidence['reranker'] = {'present': bool(expected_reranker), 'files': expected_reranker,
                            'install_upgrade_repack_restore_checked': bool(expected_reranker)}
    evidence['expanded_workspace'] = {'protected_files': len(protected['files']), 'protected_directories': len(protected['directories']),
                                      'all_fingerprints_preserved': True}
    evidence['status'] = 'passed'
    (base / 'verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(base / 'verification.json'))


if __name__ == '__main__':
    main()
