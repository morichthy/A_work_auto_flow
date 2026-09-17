"""Windows 一键部署：明确框架清单、可核对备份和冲突安全恢复。

默认执行安装；--preview 不写文件。升级原位保留业务记录、本机配置、环境和
用户规则；不扫描或复制外部材料。命令注册只占一个用户目录及一个 PATH 项。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def safe(root, relative):
    """拒绝链接/联接，包括工作区内部重定向；安装不能写到意外位置。"""
    root = Path(root).resolve()
    raw = root / relative
    if raw.resolve() != raw or not raw.is_relative_to(root):
        raise ValueError(f"路径越界或重定向：{relative}")
    return raw


def framework_files(source):
    """允许替换的框架，不包含任何业务实例、运行时、来源登记或检索历史。"""
    fixed = ['setup.cmd', 'workbench.cmd', 'portable.cmd', 'README.md', 'ARCHITECTURE.md', '.gitattributes',
             'services/qdrant/requirements.lock.txt', 'services/qdrant/README.md', 'core-algorithms/README.md',
             'automation/schemas/memory-v1.schema.json', 'automation/schemas/memory-v1.d.ts',
             'automation/schemas/memory-v2.schema.json', 'automation/schemas/memory-v2.d.ts',
             'automation/schemas/memory-v3.schema.json', 'automation/schemas/memory-v3.d.ts',
             'automation/schemas/memory-v4.schema.json', 'automation/schemas/memory-v4.d.ts',
             'automation/schemas/material-query.schema.json',
             # 查询术语的发行默认值与用户工作区中的实际词库分离。模板是
             # 受控程序输入，实际词库是可修改的本地状态，不能随源码覆盖。
             'automation/templates/query-terms.default.json',
             'automation/testing/catalog.json',
             'automation/schemas/memory-detail-v2.example.json']
    patterns = ['docs/templates/**/*', 'docs/design/*.md', 'docs/*.md',
                'services/qdrant/*.py']
    names = set(fixed)
    # Public query contracts and frozen inheritance references are controlled
    # release inputs. Do not glob arbitrary JSON or executed local receipts.
    query_docs = 'docs/design/representation-query-v0.2/'
    names.update(query_docs + name for name in (
        'README.md', 'CONTRACTS.md', 'DEVELOPMENT_READINESS.md', 'IMPLEMENTATION.md', 'TEST_DESIGN.md', 'WORKBENCH.md',
        'contracts.py', 'check_design.py', 'test-cases.json', 'development-files.json', 'INHERITANCE.md', 'inheritance-map.json', 'RUNTIME_STATUS.md',
        'baseline-v0.1/README.md', 'baseline-v0.1/CORE.md', 'baseline-v0.1/DATATYPES.md', 'baseline-v0.1/FUNCTIONS.md',
        'baseline-v0.1/IMPLEMENTATION.md', 'baseline-v0.1/PUBLIC_BASELINE.md', 'baseline-v0.1/REPRESENTATION_AND_GRAPH.md',
        'baseline-v0.1/SPEC.md', 'baseline-v0.1/check_contracts.py', 'baseline-v0.1/check_inheritance.py',
        'baseline-v0.1/contract_ports.py', 'baseline-v0.1/contract_types.py', 'baseline-v0.1/function-catalog.json',
        'baseline-v0.1/request-examples.json', 'baseline-v0.1/source-manifest.json'))
    names.update('automation/tests/fixtures/material-query/' + name for name in (
        'query-valid.json', 'query-invalid.json', 'result-valid.json', 'result-invalid.json', 'fixed-refs.json'))
    # Only version-controlled acceptance templates travel with framework code;
    # executed AI requests and reports remain in their owner Run.
    names.update(p.relative_to(source).as_posix() for p in (source / 'automation/testing/templates').glob('*.json'))
    # 记忆契约是 Python core 的运行输入；设计与冻结合成配方也是随源码
    # 分发的可复现实验输入。逐名登记 JSON，禁止通配业务 JSON 或本机回执。
    memory_docs = 'docs/design/system-memory/'
    names.update(memory_docs + name for name in (
        '01-data-contracts.md', '02-services-algorithms.md', '03-work-packages.md',
        '04-acceptance.md', '05-human-acceptance.md', 'STATUS.md', 'IMPLEMENTATION.md', 'L0-L4-REFACTOR.md',
        'RESEARCH-REPORT-COMPOSITION.md',
        'human-acceptance/REVIEW_TEMPLATE.md', 'human-acceptance/result-template.json',
        'human-acceptance/read-event-template.json', 'human-acceptance/plan-extension.json',
        'human-acceptance/cases.json', 'fixtures/README.md', 'fixtures/verify_plan.py',
        'fixtures/fixture-manifest.json', 'fixtures/acceptance.json', 'fixtures/ai-cases.json',
        'fixtures/negative-drafts.json', 'fixtures/queries.json', 'fixtures/records.json',
        'fixtures/scenarios.json', 'fixtures/variants.json', 'fixtures/work-packages.json',
        'fixtures/sources/cache.md', 'fixtures/sources/ocr.md', 'fixtures/sources/pressure.md',
        'fixtures/sources/repeat.md', 'fixtures/sources/retry.md', 'fixtures/sources/thermal.md',
        'fixtures/sources/thermal-v2.md', 'fixtures/sources/units.md', 'fixtures/sources/vibration.md'))
    # 在遍历时剪枝，避免每次升级遍历数万份前端依赖后再过滤。
    for folder, dirs, files in os.walk(source / 'automation'):
        dirs[:] = [d for d in dirs if d not in {'node_modules', '__pycache__', 'test-results', 'playwright-report'}]
        names.update((Path(folder) / name).relative_to(source).as_posix() for name in files
                     if Path(name).suffix in {'.py', '.ps1', '.html', '.md'})
    for pattern in patterns:
        names.update(p.relative_to(source).as_posix() for p in source.glob(pattern)
                     if p.is_file() and not set(p.parts) & {'__pycache__', 'node_modules', 'test-results', 'playwright-report'})
    # 前端源和资源按受控目录/清单分发，不将依赖缓存或本机数据带入升级。
    for folder, dirs, files in os.walk(source / 'automation/frontend'):
        dirs[:] = [d for d in dirs if d not in {'node_modules', 'test-results', 'playwright-report'}]
        names.update((Path(folder) / name).relative_to(source).as_posix() for name in files)
    manifest_path = source / 'automation/ui/workbench-assets/asset-manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for name, fingerprint in manifest.get('sources', {}).items():
            if digest(safe(source, 'automation/frontend/' + name)) != fingerprint:
                raise ValueError('前端源码与构建产物不匹配，请重新构建：' + name)
        names.add('automation/ui/workbench-assets/asset-manifest.json')
        for name, fingerprint in manifest['files'].items():
            path = safe(source, 'automation/ui/workbench-assets/' + name)
            if digest(path) != fingerprint:
                raise ValueError('工作台发布资源缺失或指纹不同：' + name)
            names.add(path.relative_to(source).as_posix())
    # Templates and baseline rules are only seeded when missing below.
    for base in ('projects', 'core-algorithms', 'research', 'runs', 'tools'):
        names.update(p.relative_to(source).as_posix() for p in (source / base / '_template').rglob('*') if p.is_file())
    return sorted(n for n in names if (source / n).is_file())


def seed_files(source):
    """本机可修改的配置/规则只补缺；绝不覆盖旧来源授权、关键词或自定义 Skill。"""
    names = ['workspace.json', '.gitignore', 'AGENTS.md', 'tools/registry.json']
    for pattern in ['retrieval/*.json', '*/AGENTS.md', 'context/*.md', 'governance/*.md',
                    '.agents/skills/*/SKILL.md', 'services/qdrant/*.json', 'services/qdrant/*.txt']:
        names.extend(p.relative_to(source).as_posix() for p in source.glob(pattern) if p.is_file())
    # `query-terms.json` 是用户维护的术语库。它只能由下面的明确默认
    # 模板在缺失时建立，绝不能把开发者工作区中的个人词条当作种子复制。
    excluded = {'services/qdrant/dependency-distribution.json', 'retrieval/query-terms.json'}
    return sorted(set(n for n in names if (source / n).is_file() and n not in excluded))


def plan(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    # Public archives omit local source registrations and task state. Seed only
    # missing files, including on first install; upgrades never replace user data.
    defaults = {'retrieval/sources.json': '{"schema_version": 1, "sources": []}\n',
                'context/NOW.md': '# 当前状态\n\n新工作区尚无工作记录；从 START_HERE.md 开始。\n'}
    # 默认模板没有业务词条；只在目标从未建立词库时写入，并将创建操作
    # 记录进升级回执，使 rollback 能精确恢复“原本不存在”的状态。
    terms_template = safe(source, 'automation/templates/query-terms.default.json')
    if terms_template.is_file():
        defaults['retrieval/query-terms.json'] = terms_template.read_text(encoding='utf-8')
    missing = [{'path': name, 'before': None,
                'after': hashlib.sha256(content.encode()).hexdigest(), 'content': content}
               for name, content in defaults.items() if not safe(target, name).exists()
               # sources/NOW use their hard-coded fallback only when a public
               # archive omitted local state. query-terms deliberately uses
               # its controlled template even if this developer checkout has
               # a private local copy beside that template.
               and (name == 'retrieval/query-terms.json' or not safe(source, name).exists())]
    if source == target:
        return missing
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError('新旧工作区不能互相嵌套')
    if not (target / 'workspace.json').is_file():
        raise ValueError('--target 必须是已有工作区，首次安装在解压目录直接运行')
    # 锁文件属于新版程序契约，不是用户配置；需要跟随框架并进入同一恢复回执。
    seeds = set(seed_files(source)) - {'services/qdrant/requirements.lock.txt'}
    entries = []
    for name in sorted(set(framework_files(source)) | seeds):
        src, dst = safe(source, name), safe(target, name)
        if name in seeds and dst.exists():
            continue
        before, after = digest(dst), digest(src)
        if before != after:
            entries.append({'path': name, 'before': before, 'after': after})
    # Add mandatory local exclusions while retaining every user rule.
    ignored = safe(target, '.gitignore')
    source_ignore = source / '.gitignore'
    existing = ignored.read_text(encoding='utf-8-sig') if ignored.exists() else (source_ignore.read_text(encoding='utf-8-sig') if source_ignore.exists() else '')
    suffix = ''.join('\n' + p + '\n' for p in ('.local/', 'context/monitor/', 'context/generated/evidence-view.html') if p not in existing.splitlines())
    if suffix:
        content = existing + suffix
        entries = [i for i in entries if i['path'] != '.gitignore']
        entries.append({'path': '.gitignore', 'before': digest(ignored), 'after': hashlib.sha256(content.encode()).hexdigest(), 'content': content})
    # 只识别旧版未被用户修改的受控 Skill 入口，迁移与其他文件共用备份/恢复。
    # 自定义同名入口仍受 seed 保留规则保护，不会被名称推断覆盖。
    from install_workspace_skills import managed_updates
    managed = managed_updates(source, target)
    replaced = {item['path'] for item in managed}
    return [item for item in entries if item['path'] not in replaced] + managed + missing


def apply_upgrade(source, target, entries):
    """全部原始文件先备份，再写框架。失败保留日志，可恢复；不删除旧程序或业务。"""
    if not entries:
        return None
    for item in entries:
        if item['after'] is None:
            if digest(safe(target, item['path'])) != item['before']:
                raise ValueError('退役入口发生变化，请重新预览')
            continue
        raw = item['content'].encode() if 'content' in item else safe(source, item['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['after']:
            raise ValueError('新版源文件发生变化，请重新预览')
        if digest(safe(target, item['path'])) != item['before']:
            raise ValueError(f"安装前文件发生变化：{item['path']}")
    backup = safe(target, '.local/upgrades/' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True)
    for item in entries:
        dst = safe(target, item['path'])
        if digest(dst) != item['before']:
            raise ValueError(f"安装前文件发生变化：{item['path']}")
        if dst.is_file():
            original = safe(backup, 'files/' + item['path'])
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, original)
    receipt = {'schema': 1, 'target': str(target), 'files': entries, 'applied': []}
    def save():
        (backup / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    for item in entries:
        dst = safe(target, item['path'])
        if digest(dst) != item['before']:
            raise ValueError(f"写入前文件发生变化：{item['path']}")
        if item['after'] is None:
            # 这里只删除已固定指纹并备份的单个发现文件；目录及自定义附属文件保留。
            receipt['applied'].append(item['path'])
            save()
            dst.unlink()
            continue
        content = item.get('content')
        raw = content.encode() if content is not None else safe(source, item['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['after']:
            raise ValueError('新版源文件发生变化，请重新预览')
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Journal intent before atomic replace; rollback accepts untouched originals after interruption.
        receipt['applied'].append(item['path'])
        save()
        temp = dst.with_name(dst.name + '.setup-' + uuid.uuid4().hex)
        temp.write_bytes(raw)
        os.replace(temp, dst)
    return backup


def rollback(backup, preview=False):
    backup = Path(backup).resolve()
    receipt = json.loads((backup / 'receipt.json').read_text(encoding='utf-8'))
    target = Path(receipt['target']).resolve()
    if receipt.get('schema') != 1 or backup.parent != safe(target, '.local/upgrades'):
        raise ValueError('恢复回执不属于目标工作区')
    selected = [i for i in receipt['files'] if i['path'] in receipt['applied']]
    # Preflight all conflicts before changing any file, including backup integrity.
    for item in selected:
        current = digest(safe(target, item['path']))
        if current not in (item['before'], item['after']):
            raise ValueError(f"安装后已修改，拒绝覆盖：{item['path']}")
        if item['before'] and digest(safe(backup, 'files/' + item['path'])) != item['before']:
            raise ValueError('备份校验失败')
    if not preview:
        for item in reversed(selected):
            dst = safe(target, item['path'])
            if item['before']:
                shutil.copy2(safe(backup, 'files/' + item['path']), dst)
            elif dst.exists():
                dst.unlink()
    return {'restored': len(selected), 'preview': preview, 'target': str(target)}


def run(root, *args):
    # 导入独立依赖包后必须使用目标运行时，不能继续使用引导目录的解释器。
    runtime = root / 'services/qdrant/runtime/python.exe'
    subprocess.run([str(runtime) if runtime.exists() else sys.executable, str(root / 'automation/scripts/workspace_cli.py'), *args], cwd=root, check=True)


def environment_ready(root):
    """复用已满足新版锁文件的旧环境；进程探测不会把包是否存在当版本兼容。"""
    runtime = root / 'services/qdrant/runtime/python.exe'
    if not runtime.is_file():
        return False
    lock = ROOT / 'services/qdrant/requirements.lock.txt'
    probe = "import importlib.metadata as m,json,sys; items=json.loads(sys.argv[1]); sys.exit(0 if all(m.version(n)==v for n,v in items) else 1)"
    items = [line.split('==', 1) for line in lock.read_text(encoding='utf-8').splitlines() if '==' in line]
    result = subprocess.run([str(runtime), '-c', probe, json.dumps(items)], capture_output=True, timeout=30)
    return result.returncode == 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--profile', choices=['core', 'full'], default='full')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--register', action='store_true')
    parser.add_argument('--unregister', action='store_true')
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--rollback', type=Path)
    parser.add_argument('--bundle-root', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--rollback-dependencies', type=Path, help='恢复依赖组件；关闭目标工作区进程后从新版源码目录执行')
    args = parser.parse_args(argv)
    root = (args.target or ROOT).resolve()
    import dependency_bundle
    if args.rollback_dependencies:
        print(json.dumps(dependency_bundle.restore(args.rollback_dependencies, args.preview), ensure_ascii=False)); return
    if args.bundle_root:
        args.bundle_root = args.bundle_root.resolve()
        if args.profile != 'full':
            raise ValueError('--bundle 用于 full 安装，不与 --profile core 混用')
        print('正在核验配套依赖与模型，随后执行离线组件检查……', flush=True)
        dependency_bundle.verify(args.bundle_root, ROOT)
        if not args.preview:
            subprocess.run([sys.executable, str(ROOT / 'automation/scripts/dependency_bundle.py'), 'check', '--root', str(args.bundle_root)], check=True)
    if args.rollback:
        print(json.dumps(rollback(args.rollback, args.preview), ensure_ascii=False)); return
    if args.unregister:
        import command_registration
        print(json.dumps(command_registration.register(root, remove=True, preview=args.preview), ensure_ascii=False)); return
    entries = plan(ROOT, root)
    replaced = {entry['path'] for entry in entries}
    # 原规则可能包含用户选择：不替换未知字节，但明确给出需要按新版审阅的路径。
    rule_merges = [name for name in seed_files(ROOT)
                   if (name.endswith('AGENTS.md') or name.startswith('.agents/skills/'))
                   and name not in replaced and safe(root, name).exists()
                   and digest(safe(root, name)) != digest(safe(ROOT, name))]
    print(json.dumps({'target': str(root), 'profile': args.profile, 'replacements': [e['path'] for e in entries],
                      'retired_managed_skills': [e['path'] for e in entries if e['after'] is None],
                      'preserved_rules_to_review': rule_merges,
                      'rules_note': '保留用户或未知版本规则；请按新版合并所列规则，不要覆盖原内容',
                      'preserve': 'business records, existing configs, user rules/skills and runtime', 'preview': args.preview}, ensure_ascii=False), flush=True)
    if args.preview:
        return
    import evidence
    safe(root, '.local').mkdir(exist_ok=True)
    with evidence.locked(safe(root, '.local/setup.lock')):
        backup = apply_upgrade(ROOT, root, entries)
        print(json.dumps({'backup': str(backup) if backup else None}, ensure_ascii=False), flush=True)
        if args.bundle_root:
            print('正在暂存、备份并导入运行时和模型……', flush=True)
        dependency_backup = dependency_bundle.install(args.bundle_root, root, ROOT) if args.bundle_root else None
        print(json.dumps({'dependency_backup': str(dependency_backup) if dependency_backup else None}), flush=True)
        runtime = root / 'services/qdrant/runtime/python.exe'
        if args.profile == 'full':
            # 配套依赖包必须直接满足锁；不允许失败后偷偷下载其他版本。
            if not environment_ready(root):
                if args.bundle_root:
                    raise ValueError('依赖包导入后版本检查失败；请按依赖回执恢复')
                install_args = [sys.executable, str(root / 'services/qdrant/install.py'), '--apply', '--lock', str(ROOT / 'services/qdrant/requirements.lock.txt')]
                if args.offline:
                    install_args.append('--offline')
                subprocess.run(install_args, cwd=root, check=True)
            model = root / 'services/qdrant/models/multilingual-minilm/model_optimized.onnx'
            if not model.is_file():
                if args.offline:
                    raise ValueError('离线缺少模型，保留旧数据和备份；补齐后重试')
                subprocess.run([str(runtime), str(root / 'services/qdrant/download_model.py'), '--apply'], cwd=root, check=True)
            subprocess.run([str(runtime), str(root / 'automation/scripts/portable.py'), 'check'], cwd=root, check=True)
        run(root, 'refresh-index')
        run(root, 'validate')
        if args.profile == 'full':
            # Rebuild using the configured model rather than silently substituting a different provider.
            subprocess.run([str(runtime), str(root / 'automation/scripts/workspace_cli.py'), 'index-knowledge'], cwd=root, check=True)
        if args.register:
            import command_registration
            print(json.dumps(command_registration.register(root), ensure_ascii=False))
    print(json.dumps({'status': 'installed', 'profile': args.profile, 'open': str(root / 'workbench.cmd'),
                      'note': ('完整组件检查与索引已通过；业务结论仍需领域验收' if args.profile == 'full' else 'core 不包含向量/OCR 验收') + '；外部来源路径请在目标机核对'}, ensure_ascii=False))
    if args.open:
        run(root, 'workbench')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'安装失败（保留备份与旧业务数据）：{exc}', file=sys.stderr)
        sys.exit(2)
