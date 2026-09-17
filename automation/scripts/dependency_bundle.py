"""可分发的 Windows x64 依赖包：预览/打包、完整性校验、安装与恢复。

只复制有发行来源的 Python、锁定包与模型；不遍历业务目录或 Qdrant 数据库。
运行端无需 pip 安装或联网。SHA-256 用于检查完整性，不代表发布者签名。
"""
import argparse
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from deployment import safe

BASE = 'services/qdrant/'
MANIFEST = 'dependency-manifest.json'
DISTRIBUTION = BASE + 'dependency-distribution.json'
COMPONENTS = [BASE + 'runtime', BASE + 'models/multilingual-minilm', BASE + 'model-manifest.json', DISTRIBUTION]
RERANKER_MODEL = 'services/reranker/model'
RERANKER_MANIFEST = 'services/reranker/model-manifest.json'
OPTIONAL_COMPONENTS = [RERANKER_MODEL, RERANKER_MANIFEST]
# 受控标准模型文件白名单，不递归发布缓存或业务附加文件。
RERANKER_FILES = {'model_quint8_avx2.onnx', 'tokenizer.json', 'config.json',
                  'tokenizer_config.json', 'special_tokens_map.json', 'README.md'}
PTH = b'python312.zip\n.\nLib/site-packages\n../../..\nimport site\n'


def rename_component(source, destination):
    """Retry brief Windows sharing/access failures without weakening rollback.

    Copies of DLL-heavy components can be temporarily held by local scanners.
    Never remove the destination or retry unrelated errors; after a bounded wait
    the original error reaches the existing transaction recovery path.
    """
    delays = (0.25, 0.5, 1, 2, 4, 4)
    for attempt in range(len(delays) + 1):
        try:
            source.rename(destination)
            return
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == len(delays):
                raise
            time.sleep(delays[attempt])


def sha(path):
    """分块读取大模型，避免把整个模型/ZIP 放入内存。"""
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def locked(root):
    result = {}
    for line in (root / (BASE + 'requirements.lock.txt')).read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', line):
            raise ValueError('依赖锁必须是精确版本：' + line)
        name, version = line.split('==')
        result[normalized(name)] = version
    if not result:
        raise ValueError('依赖锁为空')
    return result


def allowed(name):
    """与 PowerShell 无 Python 引导器保持相同的固定路径边界。"""
    if not isinstance(name, str) or '\\' in name or ':' in name or '\x00' in name:
        return False
    parts = name.split('/')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts):
        return False
    if any(p.lower() in {'con', 'prn', 'aux', 'nul'} or re.fullmatch(r'(com|lpt)[1-9](\..*)?', p.lower()) for p in parts):
        return False
    return name == RERANKER_MANIFEST or name in {RERANKER_MODEL + '/' + n for n in RERANKER_FILES} or name in (BASE + 'model-manifest.json', BASE + 'requirements.lock.txt', 'THIRD_PARTY.md') or any(
        name.startswith(prefix + '/') for prefix in COMPONENTS[:2])


def reranker_files(root):
    """可选 CE 的内层指纹验证；模型及清单均缺失才表示旧版无此组件。"""
    manifest_path = safe(root, RERANKER_MANIFEST)
    if not manifest_path.exists():
        if safe(root, RERANKER_MODEL).exists():
            raise ValueError('重排模型缺少指纹清单')
        return {}
    model = json.loads(manifest_path.read_text(encoding='utf-8'))
    files = model.get('files')
    if (model.get('schema_version') != 1 or not isinstance(files, dict) or set(files) != RERANKER_FILES
            or model.get('model') != 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1'
            or model.get('onnx_file') != 'model_quint8_avx2.onnx'
            or not re.fullmatch(r'[a-f0-9]{40}', str(model.get('revision', '')))
            or type(model.get('max_length')) is not int or not 8 <= model['max_length'] <= 512):
        raise ValueError('重排模型标准清单不兼容')
    result = {}
    for name, fingerprint in files.items():
        path = safe(root, RERANKER_MODEL + '/' + name)
        if not isinstance(fingerprint, str) or not re.fullmatch(r'[a-f0-9]{64}', fingerprint) or not path.is_file() or sha(path) != fingerprint:
            raise ValueError('重排模型文件校验失败：' + name)
        result[RERANKER_MODEL + '/' + name] = fingerprint
    result[RERANKER_MANIFEST] = sha(manifest_path)
    return result


def inventory(root):
    """按发行清单选取文件，不把整个 site-packages 或模型缓存直接公开。

    Python 根文件和 wheel 安装文件必须仍与原始发行哈希相同；仅 _pth
    使用本框架可迁移配置。安装器生成的 RECORD 重新生成，去除本机命令路径。
    """
    root = Path(root).resolve()
    paths, generated, licenses = {}, {}, []
    def add(name, expected=None):
        if not allowed(name):
            raise ValueError('包文件不在允许范围：' + name)
        path = safe(root, name)
        actual = sha(path)
        if expected and actual != expected:
            raise ValueError('本机依赖与发行记录不同：' + name)
        paths[name] = path

    archive = safe(root, BASE + 'downloads/python-3.12.10-embed-amd64.zip')
    if archive.exists():
        checks = json.loads(safe(root, BASE + 'checksums.json').read_text(encoding='utf-8'))
        if sha(archive) != checks.get('downloads/' + archive.name):
            raise ValueError('Python 原始发行包校验失败')
        with zipfile.ZipFile(archive) as source:
            python_files = {item.filename: hashlib.sha256(source.read(item)).hexdigest()
                            for item in source.infolist() if not item.is_dir()}
    else:
        # 接收机没有下载缓存时，沿用安装时保存的已验证分发清单。
        # 只接受 runtime 的直属文件；第三方包仍单独核验 RECORD，不能把任意
        # 本机追加文件混进下一次分发，也不必为了再次打包重新下载 Python。
        receipt = json.loads(safe(root, DISTRIBUTION).read_text(encoding='utf-8'))
        if receipt.get('schema') != 1 or receipt.get('platform') != 'windows-x64' or receipt.get('python') != '3.12.10':
            raise ValueError('已安装 Python 分发清单不兼容')
        prefix = BASE + 'runtime/'
        python_files = {name[len(prefix):]: fingerprint for name, fingerprint in receipt['files'].items()
                        if name.startswith(prefix) and '/' not in name[len(prefix):]}
    if 'python.exe' not in python_files or 'python312._pth' not in python_files:
        raise ValueError('Python 分发清单缺少必要入口')
    for relative, fingerprint in python_files.items():
        name = BASE + 'runtime/' + relative
        if relative == 'python312._pth':
            generated[name] = PTH
        else:
            add(name, fingerprint)
    packages = locked(root)
    site = safe(root, BASE + 'runtime/Lib/site-packages')
    found = {}
    for dist in importlib.metadata.distributions(path=[str(site)]):
        name = normalized(dist.metadata['Name'])
        if name in found:
            raise ValueError('本地环境存在重复发行包：' + name)
        found[name] = dist
    selected = dict(packages)
    selected['pip'] = '26.2.1'
    for name, version in sorted(selected.items()):
        dist = found.get(name)
        if dist is None or dist.version != version:
            raise ValueError('本地依赖版本与锁不一致：' + name)
        records = dist.read_text('RECORD')
        if not records:
            raise ValueError('发行包缺少 RECORD：' + name)
        clean = []
        record_name = None
        for relative, checksum, size in csv.reader(io.StringIO(records)):
            # pip --target 产生的绝对路径 launcher 不可迁移；使用端通过 python -m 调用。
            if '..' in PurePosixPath(relative).parts:
                continue
            if relative.endswith('/RECORD'):
                record_name = BASE + 'runtime/Lib/site-packages/' + relative
                clean.append((relative, '', ''))
                continue
            if relative.endswith(('.pyc', '.pyo', '/direct_url.json', '/INSTALLER', '/REQUESTED')):
                continue
            if not checksum.startswith('sha256='):
                raise ValueError('缺少发行文件 SHA-256：' + relative)
            expected = base64.urlsafe_b64decode(checksum[7:] + '===').hex()
            add(BASE + 'runtime/Lib/site-packages/' + relative, expected)
            clean.append((relative, checksum, size))
        if not record_name:
            raise ValueError('发行包 RECORD 未登记自身：' + name)
        stream = io.StringIO(newline='')
        csv.writer(stream).writerows(clean)
        generated[record_name] = stream.getvalue().encode()
        # 完整许可证随发行文件保留；摘要避免复制元数据中的任意本机路径。
        license_name = dist.metadata.get('License-Expression') or dist.metadata.get('License') or '见发行包许可证'
        if len(license_name) > 100 or '\n' in license_name:
            license_name = '见发行包许可证'
        licenses.append(f'| {name} | {version} | {license_name.replace("|", "/")} |')
    model = json.loads(safe(root, BASE + 'model-manifest.json').read_text(encoding='utf-8'))
    if model.get('path') != BASE + 'models/multilingual-minilm' or not model.get('files'):
        raise ValueError('仅支持已登记的标准相对模型路径；自定义模型需单独迁移')
    for name, fingerprint in model['files'].items():
        add(BASE + 'models/multilingual-minilm/' + name, fingerprint)
    add(BASE + 'model-manifest.json')
    reranker_payload = reranker_files(root)
    for name, fingerprint in reranker_payload.items():
        add(name, fingerprint)
    generated[BASE + 'requirements.lock.txt'] = ''.join(f'{n}=={v}\n' for n, v in sorted(packages.items())).encode()
    generated['THIRD_PARTY.md'] = ('# 第三方依赖\n\nPython 3.12.10 的许可证见 runtime/LICENSE.txt。'
        '下表发行包的许可证原文随各 dist-info/包目录保留。\n\n| 包 | 版本 | 许可证 |\n|---|---|---|\n' + '\n'.join(licenses) +
        '\n\n嵌入模型：qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q；Apache-2.0，'
        '来源和模型说明见 models/multilingual-minilm/README.md。OCR 模型随 rapidocr_onnxruntime 发行包保留。'
        '\n\n此包只含 Windows x64 CPU 运行依赖。Qdrant local 随 qdrant-client 提供；不含数据库或业务材料。\n').encode()
    if reranker_payload:
        generated['THIRD_PARTY.md'] += ('\n重排模型：cross-encoder/mmarco-mMiniLMv2-L12-H384-v1；'
            'Apache-2.0，固定版本与文件指纹见 services/reranker/model-manifest.json，'
            '模型说明见 services/reranker/model/README.md。\n').encode()
    return paths, generated, packages


def check_environment(root):
    """真实 CPU 嵌入、OCR 与临时 Qdrant 写入/搜索；禁止 Python socket 外连。"""
    import socket
    import tempfile
    from unittest.mock import patch
    if sys.platform != 'win32' or platform.machine().upper() not in {'AMD64', 'X86_64'} or sys.version_info[:2] != (3, 12):
        raise ValueError('依赖包要求 Windows x64 CPython 3.12')
    for name, version in locked(root).items():
        if importlib.metadata.version(name) != version:
            raise ValueError('解释器依赖版本不匹配：' + name)
    from qdrant_backend import LocalBackend
    from qdrant_client.models import PointStruct
    from rapidocr_onnxruntime import RapidOCR
    import numpy as np
    model = json.loads((root / (BASE + 'model-manifest.json')).read_text(encoding='utf-8'))
    cfg = {'embedding': {'path': model['path'], 'model': model['model'], 'manifest': BASE + 'model-manifest.json'}}
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('依赖检查禁止联网')):
        with tempfile.TemporaryDirectory(prefix='dependency-check-', dir=root / '.local') as temp:
            cfg['vector_store'] = {'path': str(Path(temp) / 'qdrant')}
            backend = LocalBackend(root, cfg)
            try:
                vector = list(next(backend.model.query_embed('dependency offline check')))
                if len(vector) != 384 or not np.isfinite(vector).all():
                    raise ValueError('嵌入结果无效')
                backend.client.upsert(backend.collection, [PointStruct(id=1, vector=vector, payload={'synthetic': True})])
                result = backend.client.query_points(backend.collection, query=vector, limit=1).points
                if not result or result[0].id != 1:
                    raise ValueError('Qdrant 写入/搜索失败')
            finally:
                backend.close()
            RapidOCR()(np.full((64, 160, 3), 255, dtype=np.uint8))
    return {'status': 'passed', 'embedding_dimensions': 384, 'qdrant': 'temporary upsert/query',
            'ocr': 'loaded and executed', 'reranker': check_reranker(root)}


def check_reranker(root):
    """标准组件存在时真实禁网推理，不改用户配置，也不让显式 off 绕过包自检。"""
    import socket
    from unittest.mock import patch
    if not reranker_files(root):
        return {'status': 'absent', 'note': 'optional component not installed'}
    from material_query.cross_encoder import OnnxCrossEncoder
    path = safe(root, RERANKER_MANIFEST)
    model = json.loads(path.read_text(encoding='utf-8'))
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('重排检查禁止联网')):
        provider = OnnxCrossEncoder(safe(root, RERANKER_MODEL), model, sha(path), model['max_length'])
        scores = provider.score_pairs([('低温如何预热？', '低温启动前可使用预热措施。'),
                                       ('How to preheat?', 'Preheat before cold startup.')])
    if len(scores) != 2 or not all(math.isfinite(score) for score in scores):
        raise ValueError('重排模型真实推理未返回有限分数')
    return {'status': 'passed', 'model': model['model'], 'pairs': 2, 'network': 'disabled'}


def pack(root, output, apply=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.is_relative_to(root) and not output.is_relative_to(root / 'dist'):
        raise ValueError('工作区内依赖包只能写入 dist')
    paths, generated, packages = inventory(root)
    files = {name: sha(path) for name, path in paths.items()}
    files.update({name: hashlib.sha256(raw).hexdigest() for name, raw in generated.items()})
    manifest = {'schema': 1, 'platform': 'windows-x64', 'python': '3.12.10', 'packages': packages, 'files': files}
    manifest['id'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    result = {'output': str(output), 'id': manifest['id'], 'files': len(files),
              'uncompressed_bytes': sum(p.stat().st_size for p in paths.values()) + sum(map(len, generated.values())), 'apply': apply}
    print(json.dumps(result), flush=True)
    if not apply:
        return result
    if output.exists() or output.with_suffix(output.suffix + '.sha256').exists():
        raise ValueError('输出已存在，请使用新文件名')
    # 打包前在真实本地运行时执行功能检查；拒绝系统 Python 冒充。
    subprocess.run([str(root / (BASE + 'runtime/python.exe')), str(Path(__file__).resolve()), 'check', '--root', str(root)], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.partial-' + uuid.uuid4().hex)
    try:
        with zipfile.ZipFile(temporary, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2).encode())
            for name, path in sorted(paths.items()):
                archive.write(path, name)
            for name, raw in sorted(generated.items()):
                archive.writestr(name, raw)
        # 校验实际 ZIP，捕获打包期间源文件变化；不将 .partial 报为可发布产物。
        with zipfile.ZipFile(temporary) as archive:
            for name, expected in files.items():
                with archive.open(name) as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                        raise ValueError('打包期间文件变化：' + name)
        if temporary.stat().st_size >= 2 * 1024**3:
            raise ValueError('单个 Release 资源必须小于 2 GiB')
        temporary.rename(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    fingerprint = sha(output)
    output.with_suffix(output.suffix + '.sha256').write_text(fingerprint + '  ' + output.name + '\n', encoding='ascii')
    result.update(sha256=fingerprint, bytes=output.stat().st_size)
    return result


def verify(root, source):
    """验证已解压包，执行前后均调用；额外文件亦拒绝以免残留模块被加载。"""
    root = Path(root).resolve()
    manifest = json.loads(safe(root, MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('platform') != 'windows-x64' or manifest.get('python') != '3.12.10':
        raise ValueError('依赖包平台或格式不兼容')
    if manifest.get('packages') != locked(source) or locked(root) != locked(source):
        raise ValueError('依赖包与新版框架锁定版本不一致，请使用配套 Release')
    source_model = source / (BASE + 'model-manifest.json')
    if source_model.exists() and json.loads(source_model.read_text(encoding='utf-8')) != json.loads(
            safe(root, BASE + 'model-manifest.json').read_text(encoding='utf-8')):
        raise ValueError('依赖包与新版框架模型清单不一致，请使用配套 Release')
    names = manifest.get('files', {})
    required = {BASE + 'runtime/python.exe', BASE + 'runtime/python312._pth', BASE + 'model-manifest.json', BASE + 'requirements.lock.txt'}
    if not isinstance(names, dict) or not required.issubset(names):
        raise ValueError('依赖清单缺少必要组件')
    seen = set()
    for name, expected in names.items():
        if not allowed(name) or name.casefold() in seen:
            raise ValueError('依赖清单路径非法或重复：' + name)
        seen.add(name.casefold())
        if sha(safe(root, name)) != expected:
            raise ValueError('依赖文件校验失败：' + name)
    actual = set()
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != '.local']
        for directory in dirs:
            safe(root, (Path(folder) / directory).relative_to(root).as_posix())
        actual.update((Path(folder) / n).relative_to(root).as_posix() for n in files)
    if actual != set(names) | {MANIFEST}:
        raise ValueError('依赖目录含有未登记文件')
    reranker_names = reranker_files(root)
    if any(name not in names for name in reranker_names):
        raise ValueError('依赖包未登记重排模型文件')
    return manifest


def tree_state(path):
    """恢复前核对整个组件，包含新加文件；不覆盖升级后用户的手动依赖修改。"""
    if not path.exists():
        return None
    if path.is_file():
        return sha(path)
    result = {}
    for folder, dirs, files in os.walk(path):
        for name in dirs + files:
            safe(path, (Path(folder) / name).relative_to(path).as_posix())
        for name in files:
            p = Path(folder) / name
            # 字节码是 Python 可重建缓存，不构成用户修改。
            if p.suffix not in {'.pyc', '.pyo'}:
                result[p.relative_to(path).as_posix()] = sha(p)
    return result


def restore(backup, preview=False):
    backup = Path(backup).resolve()
    receipt = json.loads((backup / 'receipt.json').read_text(encoding='utf-8'))
    target = Path(receipt['target']).resolve()
    if receipt.get('schema') != 1 or backup.parent != safe(target, '.local/dependency-backups'):
        raise ValueError('依赖恢复回执不属于目标工作区')
    for item in receipt['components']:
        name = item['path']
        if name not in COMPONENTS + OPTIONAL_COMPONENTS:
            raise ValueError('依赖恢复组件非法')
        current = tree_state(safe(target, name))
        old = safe(backup, 'previous/' + name)
        if current not in (item['before'], item['after'], None):
            raise ValueError('安装后依赖已修改，拒绝覆盖：' + name)
        if old.exists() and tree_state(old) != item['before']:
            raise ValueError('依赖备份校验失败')
        if item['before'] is not None and current != item['before'] and not old.exists():
            raise ValueError('依赖备份缺失')
    if not preview:
        for item in reversed(receipt['components']):
            live = safe(target, item['path'])
            if tree_state(live) == item['before']:
                continue
            if live.exists():
                moved = safe(backup, 'removed-' + uuid.uuid4().hex + '/' + item['path'])
                moved.parent.mkdir(parents=True, exist_ok=True)
                rename_component(live, moved)
            old = safe(backup, 'previous/' + item['path'])
            if old.exists():
                live.parent.mkdir(parents=True, exist_ok=True)
                rename_component(old, live)
    return {'restored_dependencies': not preview, 'preview': preview, 'target': str(target)}


def install(bundle, target, source):
    """在目标盘先复制暂存，再逐组件重命名；失败自动恢复，保留可审计回执。

    安装进程必须运行于包的独立引导目录，不能正在执行将被替换的目标 python.exe。
    不切换整个 services/qdrant，避免碰触数据库、配置及外部来源引用。
    """
    manifest = verify(bundle, source)
    config = target / 'retrieval/config.json'
    if config.exists():
        settings = json.loads(config.read_text(encoding='utf-8'))
        embedding = settings.get('embedding', {})
        model = json.loads(safe(bundle, BASE + 'model-manifest.json').read_text(encoding='utf-8'))
        if embedding.get('provider') == 'fastembed-local' and (
                embedding.get('path') != BASE + 'models/multilingual-minilm' or
                embedding.get('manifest', BASE + 'model-manifest.json') != BASE + 'model-manifest.json' or
                embedding.get('model') != model.get('model')):
            raise ValueError('目标使用自定义模型，标准依赖包不能覆盖；请单独迁移该模型并沿用现有配置')
        reranker = settings.get('reranker', {})
        if safe(bundle, RERANKER_MANIFEST).exists() and reranker and (
                not isinstance(reranker, dict) or
                reranker.get('provider', 'onnx-cross-encoder') not in ('onnx-cross-encoder', 'off') or
                reranker.get('path', RERANKER_MODEL) != RERANKER_MODEL or
                reranker.get('manifest', RERANKER_MANIFEST) != RERANKER_MANIFEST):
            raise ValueError('目标使用自定义重排模型，标准依赖包不能覆盖；保留原配置')
    # Windows 不允许替换正在执行的解释器；先阻止，不留下半切换的目录。
    if Path(sys.executable).resolve().is_relative_to(safe(target, BASE + 'runtime')):
        raise ValueError('请从新版源码目录使用 --bundle 安装，不能用目标运行时替换自身')
    backup = safe(target, '.local/dependency-backups/' + uuid.uuid4().hex)
    items = []
    for name in COMPONENTS + OPTIONAL_COMPONENTS:
        # 保留包来源清单，使接收机无需 Python 原始下载缓存也能再次分发。
        live = safe(target, name)
        incoming = safe(bundle, MANIFEST if name == DISTRIBUTION else name)
        # 老包缺可选 CE 时保持目标原组件，绝不把“缺失”解释成删除请求。
        if name in OPTIONAL_COMPONENTS and not incoming.exists():
            continue
        before, after = tree_state(live), tree_state(incoming)
        if before == after:
            continue
        staged = safe(backup, 'incoming/' + name)
        staged.parent.mkdir(parents=True, exist_ok=True)
        if incoming.is_dir():
            shutil.copytree(incoming, staged)
        else:
            shutil.copy2(incoming, staged)
        if tree_state(staged) != after:
            raise ValueError('依赖暂存复制校验失败')
        items.append({'path': name, 'before': before, 'after': after})
    if not items:
        return None
    receipt = {'schema': 1, 'target': str(target), 'bundle_id': manifest['id'], 'components': items}
    (backup / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    try:
        for item in items:
            live = safe(target, item['path'])
            if tree_state(live) != item['before']:
                raise ValueError('切换前依赖发生变化')
            if live.exists():
                old = safe(backup, 'previous/' + item['path'])
                old.parent.mkdir(parents=True, exist_ok=True)
                rename_component(live, old)
            live.parent.mkdir(parents=True, exist_ok=True)
            rename_component(safe(backup, 'incoming/' + item['path']), live)
    except Exception:
        restore(backup)
        raise
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['pack', 'check', 'check-reranker'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == 'check-reranker':
        result = check_reranker(root)
    elif args.command == 'check':
        safe(root, '.local').mkdir(exist_ok=True)
        result = check_environment(root)
    else:
        result = pack(root, args.output or root / 'dist/dependencies-windows-x64.zip', args.apply)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print('依赖操作失败：' + str(error), file=sys.stderr)
        sys.exit(2)
