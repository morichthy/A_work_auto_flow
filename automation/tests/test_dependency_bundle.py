"""公共依赖分发边界、损坏拒绝及可恢复升级；测试数据只存在临时目录。"""
import hashlib
import base64
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'automation/scripts'))
import dependency_bundle as bundle
import deployment


class DependencyBundleTests(unittest.TestCase):
    def add_reranker(self, root):
        files = {}
        for name in ('model_quint8_avx2.onnx', 'tokenizer.json', 'config.json', 'tokenizer_config.json', 'special_tokens_map.json', 'README.md'):
            path = self.write(root, 'services/reranker/model/' + name, 'synthetic ' + name)
            files[name] = bundle.sha(path)
        self.write(root, 'services/reranker/model-manifest.json', json.dumps({
            'schema_version': 1, 'model': 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1',
            'revision': '1' * 40, 'onnx_file': 'model_quint8_avx2.onnx', 'max_length': 512, 'files': files}))

    def test_optional_reranker_install_restore_and_old_bundle_preservation(self):
        self.add_reranker(self.target)
        old = bundle.tree_state(self.target / 'services/reranker')
        backup = bundle.install(self.package, self.target, self.source)
        self.assertEqual(bundle.tree_state(self.target / 'services/reranker'), old)
        bundle.restore(backup)
        self.add_reranker(self.package)
        self.write(self.target, 'services/reranker/model/old.onnx', 'old version')
        original = bundle.tree_state(self.target / 'services/reranker')
        self.manifest()
        backup = bundle.install(self.package, self.target, self.source)
        self.assertFalse((self.target / 'services/reranker/model/old.onnx').exists())
        distribution = json.loads((self.target / bundle.DISTRIBUTION).read_text())
        self.assertIn('services/reranker/model/tokenizer.json', distribution['files'])
        bundle.restore(backup)
        self.assertEqual(bundle.tree_state(self.target / 'services/reranker'), original)

    def test_reranker_manifest_corruption_and_unlisted_cache_rejected(self):
        self.add_reranker(self.package)
        path = self.package / 'services/reranker/model/tokenizer.json'
        path.write_text('tampered', encoding='utf-8')
        self.manifest()  # 外层 ZIP 哈希自洽仍不能覆盖内层模型哈希的不一致。
        with self.assertRaisesRegex(ValueError, '重排模型'):
            bundle.verify(self.package, self.source)
        self.assertFalse(bundle.allowed('services/reranker/model/.cache/token'))
        self.assertFalse(bundle.allowed('services/reranker/model/business.json'))

    def test_reranker_custom_config_is_preserved_and_conflict_rejected(self):
        self.add_reranker(self.package)
        self.manifest()
        config = '{"reranker":{"path":"custom/private-model"}}'
        self.write(self.target, 'retrieval/config.json', config)
        with self.assertRaisesRegex(ValueError, '自定义'):
            bundle.install(self.package, self.target, self.source)
        self.assertEqual((self.target / 'retrieval/config.json').read_text(), config)
        self.write(self.target, 'retrieval/config.json', '{"reranker":{"provider":"custom"}}')
        with self.assertRaisesRegex(ValueError, '自定义'):
            bundle.install(self.package, self.target, self.source)
        disabled = '{"reranker":{"provider":"off"}}'
        self.write(self.target, 'retrieval/config.json', disabled)
        bundle.install(self.package, self.target, self.source)
        self.assertEqual((self.target / 'retrieval/config.json').read_text(), disabled)

    def test_component_switch_retries_transient_windows_lock_but_remains_bounded(self):
        error = PermissionError('synthetic Windows sharing lock')
        error.winerror = 5
        source, destination = Path('synthetic-source'), Path('synthetic-target')
        with patch.object(Path, 'rename', side_effect=[error, None]) as rename, \
                patch.object(bundle.time, 'sleep') as sleep:
            bundle.rename_component(source, destination)
            self.assertEqual(rename.call_count, 2)
            sleep.assert_called_once_with(0.25)
        with patch.object(Path, 'rename', side_effect=error) as rename, \
                patch.object(bundle.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                bundle.rename_component(source, destination)
            self.assertEqual(rename.call_count, 7)
            self.assertEqual(sleep.call_count, 6)
        with patch.object(Path, 'rename', side_effect=FileNotFoundError('missing')), \
                patch.object(bundle.time, 'sleep') as sleep:
            with self.assertRaises(FileNotFoundError):
                bundle.rename_component(source, destination)
            sleep.assert_not_called()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.target = self.base / 'old'
        self.package = self.base / 'bundle'
        for root in (self.source, self.target, self.package):
            root.mkdir()
            self.write(root, 'services/qdrant/requirements.lock.txt', 'example==1.0\n')
        self.write(self.target, 'workspace.json', '{}')
        self.write(self.target, 'services/qdrant/runtime/python.exe', 'old python')
        self.write(self.target, 'services/qdrant/runtime/obsolete.py', 'old only')
        self.write(self.target, 'services/qdrant/models/multilingual-minilm/model.onnx', 'old model')
        self.write(self.target, 'services/qdrant/model-manifest.json', '{}')
        for name, value in {
            'services/qdrant/runtime/python.exe': 'synthetic interpreter; never execute',
            'services/qdrant/runtime/python312._pth': 'relative\n',
            'services/qdrant/models/multilingual-minilm/model.onnx': 'new model',
            'services/qdrant/model-manifest.json': '{}',
        }.items():
            self.write(self.package, name, value)
        self.manifest()

    def write(self, root, name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def manifest(self):
        manifest = {'schema': 1, 'platform': 'windows-x64', 'python': '3.12.10', 'id': 'synthetic',
                    'packages': {'example': '1.0'}, 'files': {p.relative_to(self.package).as_posix(): bundle.sha(p)
                    for p in self.package.rglob('*') if p.is_file() and p.name != bundle.MANIFEST}}
        self.write(self.package, bundle.MANIFEST, json.dumps(manifest))
        return manifest

    def test_verify_rejects_corruption_extra_files_and_incompatible_lock(self):
        bundle.verify(self.package, self.source)
        path = self.package / 'services/qdrant/runtime/python.exe'
        original = path.read_bytes()
        path.write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, '校验失败'):
            bundle.verify(self.package, self.source)
        path.write_bytes(original)
        extra = self.write(self.package, 'services/qdrant/runtime/private.txt', 'private')
        with self.assertRaisesRegex(ValueError, '未登记'):
            bundle.verify(self.package, self.source)
        extra.unlink()
        self.write(self.source, 'services/qdrant/requirements.lock.txt', 'example==2.0')
        with self.assertRaisesRegex(ValueError, '锁定版本'):
            bundle.verify(self.package, self.source)

    def test_paths_cannot_escape_or_smuggle_business_database(self):
        for name in ['../secret', 'services/qdrant/runtime/../../data/a', 'C:/python.exe',
                     'services/qdrant/storage/database', 'runs/private/run.json', 'services/qdrant/runtime/a:b',
                     'services/qdrant/runtime/a./b', 'services/qdrant/runtime/CON', 'services\\qdrant\\runtime\\x']:
            self.assertFalse(bundle.allowed(name), name)
        manifest = self.manifest()
        manifest['files']['services/qdrant/runtime/PYTHON.EXE'] = '0' * 64
        self.write(self.package, bundle.MANIFEST, json.dumps(manifest))
        with self.assertRaises(ValueError):
            bundle.verify(self.package, self.source)

    def test_inventory_only_includes_distribution_files_not_local_private_additions(self):
        # 构造微型发行包，不读取本机用户 Python；验证公共打包的来源边界。
        root = self.source
        archive = root / 'services/qdrant/downloads/python-3.12.10-embed-amd64.zip'
        archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive, 'w') as zipped:
            zipped.writestr('python.exe', 'synthetic python')
            zipped.writestr('python312._pth', 'original')
        self.write(root, 'services/qdrant/runtime/python.exe', 'synthetic python')
        self.write(root, 'services/qdrant/checksums.json', json.dumps({'downloads/' + archive.name: bundle.sha(archive)}))
        distributions = []
        for name, version in [('example', '1.0'), ('pip', '26.2.1')]:
            path = self.write(root, f'services/qdrant/runtime/Lib/site-packages/{name}/__init__.py', 'synthetic package')
            encoded = base64.urlsafe_b64encode(bytes.fromhex(bundle.sha(path))).decode().rstrip('=')
            record = f'{name}/__init__.py,sha256={encoded},17\n{name}-{version}.dist-info/RECORD,,\n../../bin/{name}.exe,sha256=unused,10\n'
            distributions.append(SimpleNamespace(metadata={'Name': name, 'License': 'MIT'}, version=version,
                                                  read_text=lambda n, value=record: value if n == 'RECORD' else None))
        model = self.write(root, 'services/qdrant/models/multilingual-minilm/model.onnx', 'synthetic model')
        self.write(root, 'services/qdrant/model-manifest.json', json.dumps({'path': 'services/qdrant/models/multilingual-minilm', 'files': {'model.onnx': bundle.sha(model)}}))
        self.add_reranker(root)
        private_names = ['runs/secret.json', 'services/qdrant/storage/database', 'services/qdrant/runtime/private.txt',
                         'services/qdrant/runtime/Lib/site-packages/private.py', 'services/qdrant/models/multilingual-minilm/.cache/token',
                         'services/reranker/model/.cache/token', 'services/reranker/model/business.json']
        for name in private_names:
            self.write(root, name, 'private never include')
        with patch.object(bundle.importlib.metadata, 'distributions', return_value=distributions):
            paths, generated, packages = bundle.inventory(root)
            self.assertTrue(set(private_names).isdisjoint(paths))
            self.assertIn('services/qdrant/runtime/python.exe', paths)
            self.assertIn('services/qdrant/models/multilingual-minilm/model.onnx', paths)
            self.assertIn('services/reranker/model/tokenizer.json', paths)
            self.assertEqual(packages, {'example': '1.0'})
            self.assertNotIn(b'../../bin', generated['services/qdrant/runtime/Lib/site-packages/example-1.0.dist-info/RECORD'])
            # 接收者没有原始下载缓存时，也能按安装来源清单再次打包。
            self.write(root, bundle.DISTRIBUTION, json.dumps({'schema': 1, 'platform': 'windows-x64', 'python': '3.12.10',
                'files': {'services/qdrant/runtime/python.exe': bundle.sha(root / 'services/qdrant/runtime/python.exe'),
                          'services/qdrant/runtime/python312._pth': hashlib.sha256(bundle.PTH).hexdigest()}}))
            archive.unlink()
            repacked, _, _ = bundle.inventory(root)
            self.assertEqual(set(repacked), set(paths))
            model.write_text('tampered', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '发行记录不同'):
                bundle.inventory(root)

    def test_component_swap_preserves_data_and_removes_stale_packages_then_restores(self):
        protected = ['runs/private/run.json', 'services/qdrant/storage/database']
        for name in protected:
            self.write(self.target, name, 'private unchanged')
        self.write(self.target, 'retrieval/config.json', '{"private":true}')
        original = {name: bundle.tree_state(self.target / name) for name in bundle.COMPONENTS}
        backup = bundle.install(self.package, self.target, self.source)
        self.assertFalse((self.target / 'services/qdrant/runtime/obsolete.py').exists())
        for name in protected:
            self.assertEqual((self.target / name).read_text(), 'private unchanged')
        self.assertEqual((self.target / 'retrieval/config.json').read_text(), '{"private":true}')
        self.assertIsNone(bundle.install(self.package, self.target, self.source))
        bundle.restore(backup, preview=True)
        self.assertFalse((self.target / 'services/qdrant/runtime/obsolete.py').exists())
        bundle.restore(backup)
        bundle.restore(backup)  # 幂等恢复不移走已恢复的旧组件。
        for name, state in original.items():
            self.assertEqual(bundle.tree_state(self.target / name), state)

    def test_restore_preflights_modified_dependencies_and_corrupt_backup(self):
        backup = bundle.install(self.package, self.target, self.source)
        changed = self.write(self.target, 'services/qdrant/runtime/user.py', 'new edit')
        with self.assertRaisesRegex(ValueError, '已修改'):
            bundle.restore(backup)
        changed.unlink()
        self.write(backup, 'previous/services/qdrant/runtime/python.exe', 'corrupted')
        with self.assertRaisesRegex(ValueError, '备份校验'):
            bundle.restore(backup)

    def test_interrupted_component_switch_automatically_restores(self):
        original = {name: bundle.tree_state(self.target / name) for name in bundle.COMPONENTS}
        rename = Path.rename
        def fail_on_model(path, target):
            if 'incoming' in path.parts and path.name == 'multilingual-minilm':
                raise PermissionError('simulated DLL/file lock')
            return rename(path, target)
        with patch.object(Path, 'rename', fail_on_model):
            with self.assertRaises(PermissionError):
                bundle.install(self.package, self.target, self.source)
        for name, state in original.items():
            self.assertEqual(bundle.tree_state(self.target / name), state)

    def test_framework_lock_upgrades_and_rolls_back_with_user_config_preserved(self):
        self.write(self.target, 'services/qdrant/requirements.lock.txt', 'example==0.9')
        self.write(self.target, 'retrieval/config.json', 'user configuration')
        entries = deployment.plan(self.source, self.target)
        self.assertIn('services/qdrant/requirements.lock.txt', [e['path'] for e in entries])
        backup = deployment.apply_upgrade(self.source, self.target, entries)
        self.assertEqual(bundle.locked(self.target), {'example': '1.0'})
        deployment.rollback(backup)
        self.assertEqual(bundle.locked(self.target), {'example': '0.9'})
        self.assertEqual((self.target / 'retrieval/config.json').read_text(), 'user configuration')

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell bootstrap')
    def test_core_preview_does_not_load_an_optional_full_bundle(self):
        for name in ['setup.cmd', 'automation/setup.ps1', 'automation/python.ps1',
                     'automation/scripts/deployment.py', 'automation/scripts/dependency_bundle.py']:
            dst = self.source / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dst)
        self.write(self.source, 'dependencies-windows-x64.zip', 'not a valid ZIP; core must ignore it')
        result = subprocess.run(['cmd.exe', '/d', '/c', 'setup.cmd', '--profile', 'core', '--preview'],
                                cwd=self.source, env=dict(os.environ, CODEX_WORKSPACE_PYTHON=sys.executable),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.source / '.local').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell bootstrap')
    def test_no_python_bootstrap_preview_corruption_and_path_boundary(self):
        # 同一真实 PowerShell 引导路径必须接受新可选组件并保持严格白名单。
        self.add_reranker(self.package)
        self.manifest()
        archive = self.base / 'dependencies.zip'
        def write_zip(extra=None):
            with zipfile.ZipFile(archive, 'w') as stream:
                for path in self.package.rglob('*'):
                    if path.is_file():
                        stream.write(path, path.relative_to(self.package).as_posix())
                if extra:
                    stream.writestr(extra, 'private')
            archive.with_suffix('.zip.sha256').write_text(bundle.sha(archive))
        def invoke(preview=True):
            args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'automation/dependency-bundle.ps1'),
                    '-Archive', str(archive), '-SourceRoot', str(self.source)]
            if preview:
                args.append('-Preview')
            return subprocess.run(args, capture_output=True, text=True, timeout=30, env=dict(os.environ, TEMP=str(self.base), TMP=str(self.base)))
        write_zip()
        result = invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.source / '.local').exists())
        result = invoke(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        stage = self.base / 'rdwork-deps' / bundle.sha(archive)[:16]
        bundle.verify(stage, self.source)
        self.write(stage, 'services/qdrant/runtime/injected.py', 'not in package')
        self.assertNotEqual(invoke(False).returncode, 0)
        write_zip('../outside.txt')
        self.assertNotEqual(invoke().returncode, 0)
        self.assertFalse((self.source / 'outside.txt').exists())
        write_zip()
        archive.with_suffix('.zip.sha256').write_text('0' * 64)
        self.assertNotEqual(invoke().returncode, 0)


if __name__ == '__main__':
    unittest.main()
