"""模拟长期使用后扩展的旧工作区，仅由测试显式调用，不含真实业务材料。"""
import hashlib
import json
from pathlib import Path
import uuid


def policy_request(owner_id, expected_head=None, *, record_id=None, revision=None, summary=False):
    """由真实 MemoryService 保存的合成策略请求，避免手填 HEAD/哈希。"""
    operation = {'op': 'put_record', 'draft': {
        'owner_id': owner_id, 'kind': 'policy', 'title': 'SYNTHETIC ONLY 升级保护策略',
        'keywords': [], 'body_markdown': '仅验证框架升级的字节保留。',
        'payload': {'mode': 'basic', 'overrides': {'auto_summary': summary}},
        'sources': [], 'provenance_gap': '合成软件测试配置，没有现实业务依据',
        'record_reason': '验证规范历史与入口升级保留',
        'discovery': 'owner_only', 'sensitivity': 'internal'}}
    if record_id:
        operation.update(record_id=record_id, expected_revision=revision)
    else:
        operation['client_key'] = 'policy'
    return {'schema_version': 1, 'request_id': str(uuid.uuid4()),
            'actor': {'kind': 'workflow', 'id': 'synthetic-upgrade-test'},
            'owner_id': owner_id, 'expected_head': expected_head, 'operations': [operation]}


def populate_memory(root):
    """真实提交目录及平铺文档记忆，保留失败现场和实际错误回执。"""
    from memory import owners
    from memory.service import MemoryService
    from memory.errors import MemoryError
    service = MemoryService(root)
    paths = []
    # 共享 fixture 也用于真实依赖安装后的空业务区，不能假定已有 demo RES。
    import workspace_cli
    research = root / 'research/synthetic-memory-upgrade'
    workspace_cli.render_template_tree(Path(__file__).resolve().parents[2] / 'research/_template', research,
        {'{{research_id}}': 'RES-SYNTHETIC-MEMORY-UPGRADE', '{{research_slug}}': 'synthetic-memory-upgrade',
         '{{title}}': 'SYNTHETIC ONLY 记忆升级保护', '{{date}}': '2026-01-01'})
    research_metadata = json.loads((research / 'research.json').read_text(encoding='utf-8'))
    # The production template conservatively defaults to restricted. This
    # explicitly synthetic fixture grants its local test actor internal scope.
    research_metadata['sensitivity'] = 'internal'
    (research / 'research.json').write_text(json.dumps(research_metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    research_id = research_metadata['research_id']
    original = research / 'synthetic-original.md'
    original_text = 'SYNTHETIC ONLY memory upgrade provenance.\n'
    original.write_text(original_text, encoding='utf-8', newline='\n')
    registry_path = root / 'retrieval/sources.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    registry.setdefault('sources', []).append({'source_id': 'SRC-MEMORY-UPGRADE',
        'path': original.relative_to(root).as_posix(), 'enabled': True, 'sensitivity': 'internal'})
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding='utf-8')
    source_ref = {'target_kind': 'file', 'target_id': 'SRC-MEMORY-UPGRADE', 'revision': None,
        'sha256': hashlib.sha256(original.read_bytes()).hexdigest(), 'locator': 'lines:1-1', 'relation': 'background'}
    document = root / 'knowledge/用户记忆/阶段 A/经验 文档.md'
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text('# SYNTHETIC ONLY\n迁移测试原件。\n', encoding='utf-8')
    view = next(v for v in owners.list_owners(root) if v['native_ref']['path'] == document.relative_to(root).as_posix())
    adopted = owners.adopt_owner(root, view['native_ref'], view['fingerprint'])
    for oid in (research_id, adopted['owner_id']):
        first = service.commit(policy_request(oid))
        assert first['save_status'] == 'committed'
        rid = first['record_results'][0]['record_id']
        second = service.commit(policy_request(oid, first['commit_id'], record_id=rid, revision=1, summary=True))
        assert second['save_status'] == 'committed'
        unchanged = service.commit(policy_request(oid, second['commit_id'], record_id=rid, revision=2, summary=True))
        assert unchanged['save_status'] == 'no_change'
        # Exercise all four levels and all auxiliary entities through the real
        # service. This protects actual payload/history/CLM/review layouts, not
        # merely a directory named memory with a few hand-written placeholders.
        from test_memory_contracts import examples
        from copy import deepcopy
        payloads = examples()
        # 这里保留旧四层历史；v2 detail 在 populate 的真实嵌套 Run 建好后
        # 单独提交，不能使用契约单测里的虚拟 RUN-synthetic 引用。
        payloads.pop('detail', None)
        def batch_ref(key):
            return {'client_key': key, 'relation': 'references', 'locator': 'SYNTHETIC ONLY fixed batch record'}
        payloads['source'].update(source_ref=source_ref, acquisition='verbatim_export', completeness='complete')
        payloads['event'].update(goal_ref=batch_ref('goal'), route_ref=batch_ref('route'))
        claim_id = 'CLM-UPGRADE-' + oid
        supporting = dict(source_ref, relation='supports')
        payloads['experience']['claims'] = [{'claim_id': claim_id, 'statement': 'SYNTHETIC ONLY memory upgrade provenance.',
            'kind': 'fact', 'scope': 'synthetic:upgrade', 'evidence_refs': [supporting]}]
        payloads['map'].update(goal_refs=[batch_ref('goal')], route_refs=[batch_ref('route')],
            result_refs=[batch_ref('experience')], question_refs=[batch_ref('question')],
            coverage={'owner_ids': [oid], 'source_versions': [source_ref], 'missing': []})
        payloads['route'].update(goal_ref=batch_ref('goal'), attempt_refs=[batch_ref('event')])
        payloads['checkpoint'].update(goal_ref=batch_ref('goal'), route_refs=[batch_ref('route')],
            completed_refs=[batch_ref('event')], question_refs=[batch_ref('question')])
        payloads['association'].update({'from': batch_ref('event'), 'to': batch_ref('experience')})
        payloads['representation'].update(target=batch_ref('experience'), boundary_refs=[batch_ref('experience')])
        payloads['consolidation']['basis_heads'] = {oid: second['commit_id']}
        payloads['feedback']['target'] = batch_ref('event')
        batch = policy_request(oid, second['commit_id'])
        batch['operations'] = []
        for kind, payload in payloads.items():
            if kind in {'policy', 'review'}:
                continue
            draft = deepcopy(policy_request(oid)['operations'][0]['draft'])
            draft.update(schema_version=1, kind=kind, title='SYNTHETIC ONLY upgrade ' + kind, payload=payload,
                sources=[source_ref], provenance_gap=None,
                body_markdown=original_text if kind == 'source' else 'SYNTHETIC ONLY 新记忆升级保护。')
            batch['operations'].append({'op': 'put_record', 'client_key': kind, 'draft': draft})
        contents = service.commit(batch)
        latest = service.review({'schema_version': 1, 'request_id': str(uuid.uuid4()), 'owner_id': oid,
            'expected_head': contents['commit_id'], 'actor': {'kind': 'workflow', 'id': 'synthetic-upgrade-test'},
            'target_claim_id': claim_id, 'state': 'accepted', 'reason': 'SYNTHETIC ONLY software fixture',
            'scope': 'synthetic:upgrade', 'evidence_refs': [supporting]})
        assert set(record['kind'] for record in service.inspect(oid)['records'].values()) == set(payloads)
        owner = owners.resolve_owner(root, oid)
        home = root / owner['memory_home']
        # 故障发生在 commit 目录发布后、HEAD 发布前。保存的是服务实际
        # 返回的错误，不手写假的成功回执；HEAD 仍能读到第四代规范快照。
        def fail(point):
            if point == 'before_head':
                raise OSError('SYNTHETIC ONLY upgrade recovery fixture')
        try:
            MemoryService(root, fault=fail).commit(policy_request(oid, latest['commit_id'], record_id=rid, revision=2))
        except MemoryError as exc:
            recovery = home / 'recovery-receipts' / 'synthetic-failure.json'
            recovery.parent.mkdir()
            recovery.write_text(json.dumps(exc.as_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        else:
            raise AssertionError('Synthetic fault did not fire')
        assert service.inspect(oid)['head']['commit_id'] == latest['commit_id']
        (home / 'staging/待恢复 空目录').mkdir(parents=True)
        paths.append(home)
    files = [document.relative_to(root).as_posix()]
    directories = set()
    paths.append(research)
    for home in paths:
        for path in [home, *home.rglob('*')]:
            if path.is_file():
                files.append(path.relative_to(root).as_posix())
            else:
                directories.add(path.relative_to(root).as_posix())
    return files, directories


def snapshot(root, names, directories):
    """记录受保护文件的字节指纹及目录集合；包含空目录，避免只测文件遗漏。"""
    return {'files': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
            'directories': sorted(directories)}



def legacy_skill(name):
    descriptions = {
        'research-loop': '规划并执行专题研究、数据诊断、模型设计验证和证据报告的闭环；适用于论文阅读、仿真、反证和可复现综合，不用于简单事实问答。',
        'material-query': '按内容来源、标准类型和版本查询已有研发材料，选择候选后展开正文或读取完整文稿，核对来源、预算和缺口；不自动生成新结论。',
    }
    return f"---\nname: {name}\ndescription: {descriptions[name]}\n---\n\n# 工作区技能入口\n\n在含 workspace.json 的当前研发工作区使用。读取 [完整工作流](../../../automation/workflows/{name}/SKILL.md)，按本轮任务执行；根 AGENTS 与用户明确要求优先。本文件只用于技能发现，方法和命令在工作流源维护。\n"

def populate(root, branches=8):
    """在各业务区添加多层目录、中文空格名称、单文件和目录工具以及用户扩展。

    目录规模固定且可重复；比较完整受保护集合，不以几个抽样文件替代数据保留验收。
    不在真实工作区调用：测试使用 TemporaryDirectory 或 .local 隔离目录。
    """
    root = Path(root).resolve()
    names, directories = [], set()
    def write(name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        names.append(name)
        directories.add(path.parent.relative_to(root).as_posix())
    for area in ['core-algorithms', 'research', 'runs', 'projects', 'knowledge', 'reports/sources', 'data/catalog']:
        for i in range(branches):
            parent = f'{area}/用户扩展 {i}/阶段 A/版本 01'
            write(parent + '/材料.txt', f'SYNTHETIC ONLY {area} {i}\n')
            empty = parent + '/空目录'
            (root / empty).mkdir()
            directories.add(empty)
    entries = ['tools/packages/用户库/子包', 'tools/scripts/用户脚本/任务组', 'tools/scripts/用户脚本/单文件.py']
    write(entries[0] + '/__init__.py', '# Synthetic package; never executed during migration.\n')
    write(entries[1] + '/worker.py', '# Synthetic script collection.\n')
    write(entries[2], '# Synthetic CLI.\n')
    write('automation/user-extension/nested/custom.py', '# User-owned extension, absent from new source.\n')
    write('.agents/skills/user-example/SKILL.md', '---\nname: user-example\ndescription: Synthetic fixture only.\n---\nSynthetic fixture.\n')
    # 依赖缓存含无效 JSON，必须按既有规则剪枝；业务目录中的无效 JSON 另作反例。
    write('automation/user-extension/node_modules/vendor/broken.json', '{synthetic invalid cache')
    write('.local/user-cache/nested/broken.json', '{synthetic invalid cache')
    registry = root / 'tools/registry.json'
    value = json.loads(registry.read_text(encoding='utf-8'))
    value['tools'].extend({'tool_id': f'TOOL-USER-SYNTHETIC-{i}', 'kind': 'python-package' if i == 0 else 'python-cli',
                           'entrypoint': entry, 'status': 'active'} for i, entry in enumerate(entries))
    registry.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    names.extend(['tools/registry.json', 'retrieval/config.json', 'retrieval/sources.json', 'AGENTS.md'])
    # 用不同于发行默认模板的条目模拟用户维护内容。完整保护清单必须把
    # 它作为业务字节保留，防止升级把开发者词条或默认值写回旧工作区。
    write('retrieval/query-terms.json', json.dumps({
        'schema_version': 1,
        'entries': [{
            'id': 'user-upgrade-term', 'domain': 'synthetic-upgrade',
            'zh': ['用户升级术语'], 'en': ['user upgrade term'],
            'aliases': ['UUT'], 'related': [], 'sources': ['SYNTHETIC ONLY'],
            'status': 'active',
        }],
    }, ensure_ascii=False, indent=2) + '\n')
    memory_files, memory_directories = populate_memory(root)
    names.extend(memory_files)
    directories.update(memory_directories)
    # Preserve an explicit, fingerprint-pinned legacy locator after a research
    # Run was moved. The old path remains absent throughout real setup cycles.
    relocated = 'research/用户迁移 样例/历史运行/结果.txt'
    write(relocated, 'SYNTHETIC ONLY frozen relocated evidence\n')
    source_registry = root / 'retrieval/sources.json'
    registered = json.loads(source_registry.read_text(encoding='utf-8'))
    registered['sources'].append({'source_id': 'SRC-UPGRADE-RELOCATED', 'path': relocated,
        'relocated_from': 'runs/旧布局/结果.txt', 'enabled': True, 'sensitivity': 'internal',
        'sha256': hashlib.sha256((root / relocated).read_bytes()).hexdigest()})
    source_registry.write_text(json.dumps(registered, ensure_ascii=False, indent=2), encoding='utf-8')
    # 各类真实 owner 的嵌套 Run、可读附件与空目录必须经过真实 setup 的
    # 全保护清单校验；不是只在任意深度放一个无身份文本来模拟业务对象。
    import workspace_cli
    specs = [
        ('research/升级 研究/research.json', 'research_id', 'RES-OWNED-UPGRADE'),
        ('projects/升级 项目/project.json', 'project_id', 'PRJ-OWNED-UPGRADE'),
        ('core-algorithms/升级 算法/module.json', 'module_id', 'MOD-OWNED-UPGRADE'),
        ('runs/升级 父运行/run.json', 'run_id', 'RUN-OWNED-UPGRADE'),
        ('knowledge/升级 经验.evidence.json', 'evidence_id', 'KN-OWNED-UPGRADE'),
        ('reports/sources/升级 报告.evidence.json', 'evidence_id', 'REP-OWNED-UPGRADE'),
        ('data/catalog/升级 数据.dataset.json', 'dataset_id', 'DATA-OWNED-UPGRADE')]
    for name, field, oid in specs:
        card = {field: oid, 'title': 'SYNTHETIC ONLY 对象内运行升级保护'}
        if field == 'module_id':
            card.update(entity_kind='core-algorithm', source_document='SYNTHETIC ONLY 模型说明')
        if field == 'evidence_id':
            document = name.replace('.evidence.json', '.md')
            write(document, '# SYNTHETIC ONLY\n对象归属。\n')
            card['document_path'] = document
        write(name, json.dumps(card, ensure_ascii=False))
    for oid in [item[2] for item in specs] + ['TOOL-USER-SYNTHETIC-0']:
        run = workspace_cli.create_run(root, None, 'SYNTHETIC ONLY 嵌套运行', owner_id=oid)
        for path in run.iterdir():
            names.append(path.relative_to(root).as_posix())
        prefix = run.relative_to(root).as_posix()
        write(prefix + '/inputs/重要 参数.json', '{"synthetic": true, "seed": 42}\n')
        write(prefix + '/artifacts/结果 图.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><text x="1" y="20">TEST</text></svg>\n')
        empty = prefix + '/artifacts/待补充 空目录'
        (root / empty).mkdir()
        directories.update({prefix, empty})
        if oid == 'RES-OWNED-UPGRADE':
            # 通过真实保存服务生成 v2 L1；固定 L0 输入/图表的注册 ID 与
            # 字节哈希，升级后的检查不能只验证一个松散 Markdown 存在。
            from memory.service import MemoryService
            from memory import owners
            source_registry = root / 'retrieval/sources.json'
            registered = json.loads(source_registry.read_text(encoding='utf-8'))
            refs = []
            for suffix, source_id in [('inputs/重要 参数.json', 'SRC-OWNED-UPGRADE-INPUT'),
                                      ('artifacts/结果 图.svg', 'SRC-OWNED-UPGRADE-FIGURE')]:
                relative = prefix + '/' + suffix
                registered['sources'].append({'source_id': source_id, 'path': relative,
                    'enabled': True, 'sensitivity': 'internal', 'memory_level': 'L0', 'discovery': 'trace_only'})
                refs.append({'target_kind': 'file', 'target_id': source_id, 'revision': None,
                    'sha256': hashlib.sha256((root / relative).read_bytes()).hexdigest(),
                    'locator': 'SYNTHETIC ONLY whole file', 'relation': 'input'})
            source_registry.write_text(json.dumps(registered, ensure_ascii=False, indent=2), encoding='utf-8')
            run_card = json.loads((run / 'run.json').read_text(encoding='utf-8'))
            import evidence
            run_ref = {'target_kind': 'owner', 'target_id': run_card['run_id'], 'revision': None,
                'sha256': evidence.fingerprint(run_card),
                'locator': 'run.json', 'relation': 'input'}
            draft = {'schema_version': 2, 'owner_id': oid, 'kind': 'detail',
                'title': 'SYNTHETIC ONLY L1 计算记录升级保护', 'keywords': ['升级保护'],
                'body_markdown': '# 合成计算说明\n\n使用 $s=a+b$ 验证公式和附件随历史保留。\n\n仅为软件升级测试，不构成业务模型结论。',
                'payload': {'run_ref': run_ref, 'question': '对象内 L0 与 L1 是否保持固定关联？',
                    'method': '构造受控输入和图表，以 SHA-256 固定引用并通过真实事务提交。',
                    'steps': ['创建本对象 Run 与固定输入。', '记录附件指纹。', '提交详细记录并回读。'],
                    'inputs': [refs[0]], 'parameters': [{'name': 'seed', 'value': 42, 'unit': 'dimensionless',
                        'description': '固定合成输入标识，不表示执行了随机实验。'}],
                    'formulas': [{'latex': 's=a+b', 'variables': [
                        {'symbol': symbol, 'meaning': meaning, 'unit': 'dimensionless'}
                        for symbol, meaning in [('a', '第一加数'), ('b', '第二加数'), ('s', '两者之和')]]}],
                    'figures': [{'caption': '合成 SVG 升级保护标记', 'ref': refs[1]}],
                    'results': '合成输入与 SVG 已生成；验证目标为固定引用和字节保留。',
                    'limitations': ['仅测试软件存储与升级，不验证现实科学结论。'], 'missing_refs': []},
                'sources': [run_ref, *refs], 'provenance_gap': None, 'record_reason': '固定 v2 L1 和 L0 附件的真实升级回归',
                'discovery': 'owner_only', 'sensitivity': 'internal'}
            service = MemoryService(root)
            saved = service.commit({'schema_version': 1, 'request_id': str(uuid.uuid4()),
                'actor': {'kind': 'workflow', 'id': 'synthetic-upgrade-test'}, 'owner_id': oid,
                'expected_head': None, 'operations': [{'op': 'put_record', 'client_key': 'detail', 'draft': draft}]})
            assert saved['save_status'] == 'committed', saved
            detail = service.inspect(oid)['records'][saved['record_results'][0]['record_id']]
            assert detail['schema_version'] == 2 and detail['level'] == 'L1'
            assert detail['payload']['figures'][0]['ref']['sha256'] == refs[1]['sha256']
            # 编排使用真实提交后回读的记录指纹。它是旧工作区内的业务
            # 记忆，源码升级必须逐字保留，不能只保留实验附件而丢掉论证顺序。
            fixed_detail = {'target_kind': 'record', 'target_id': detail['record_id'],
                'revision': detail['revision'], 'sha256': detail['record_hash'],
                'locator': '完整合成计算说明', 'relation': 'references'}
            report = {'schema_version': 2, 'owner_id': oid, 'kind': 'map',
                'title': 'SYNTHETIC ONLY 连贯报告升级保护', 'keywords': ['报告编排'],
                'body_markdown': '合成报告的编排与固定证据一起升级；不代表实际科学结论。',
                'payload': {'topic': '报告编排升级保护', 'goal_refs': [], 'route_refs': [],
                    'result_refs': [fixed_detail], 'question_refs': [], 'conflict_refs': [],
                    'next_steps': [], 'coverage': {'owner_ids': [oid],
                        'source_versions': [fixed_detail], 'missing': []},
                    'report': {'version': 1, 'title': '合成计算报告', 'sections': [
                        {'section_id': 'question', 'title': '问题与范围', 'role': 'introduction',
                         'blocks': [{'type': 'prose', 'markdown': '本报告仅用于验证升级时保留顺序和字节。', 'evidence_refs': []}]},
                        {'section_id': 'experiment', 'title': '固定输入的计算说明', 'role': 'experiment',
                         'blocks': [{'type': 'prose', 'markdown': '为核对固定输入，下面读取已保存的计算说明。', 'evidence_refs': [fixed_detail]},
                                    {'type': 'detail', 'ref': fixed_detail}]},
                        {'section_id': 'conclusion', 'title': '结果与边界', 'role': 'conclusion',
                         'blocks': [{'type': 'prose', 'markdown': '此项仅验证存储和升级，不能推出业务模型有效。', 'evidence_refs': [fixed_detail]}]}]}},
                'sources': [fixed_detail], 'provenance_gap': None,
                'record_reason': '验证编排段落、顺序和固定修订在升级恢复中不丢失',
                'discovery': 'owner_only', 'sensitivity': 'internal'}
            report_saved = service.commit({'schema_version': 1, 'request_id': str(uuid.uuid4()),
                'actor': {'kind': 'workflow', 'id': 'synthetic-upgrade-test'}, 'owner_id': oid,
                'expected_head': saved['commit_id'],
                'operations': [{'op': 'put_record', 'client_key': 'report', 'draft': report}]})
            assert report_saved['save_status'] == 'committed', report_saved
            home = root / owners.resolve_owner(root, oid)['memory_home']
            for path in [home, *home.rglob('*')]:
                relative = path.relative_to(root).as_posix()
                if path.is_dir():
                    directories.add(relative)
                elif path.is_file():
                    names.append(relative)
    # A separate owner exercises the v3 hierarchy while the legacy v1/v2 owner
    # assertions remain unchanged. All writes use the production transaction API.
    v3_owner = 'RES-DOCUMENT-UPGRADE'
    write('research/独立 文稿升级/research.json', json.dumps({
        'research_id': v3_owner, 'title': 'SYNTHETIC ONLY 技术单元双文稿升级'}, ensure_ascii=False))
    from memory.service import MemoryService
    from memory import owners
    service = MemoryService(root)

    def save_v3(kind, title, payload, refs):
        current = service.inspect(v3_owner)
        result = service.commit({'schema_version': 1, 'request_id': str(uuid.uuid4()),
            'actor': {'kind': 'workflow', 'id': 'synthetic-upgrade-test'}, 'owner_id': v3_owner,
            'expected_head': current['head']['commit_id'] if current['head'] else None,
            'operations': [{'op': 'put_record', 'client_key': kind, 'draft': {
                'schema_version': 3, 'owner_id': v3_owner, 'kind': kind, 'title': title,
                'body_markdown': '', 'keywords': ['合成文稿'], 'payload': payload,
                'sources': refs, 'provenance_gap': None if refs else '合成升级测试定义，无科学主张',
                'record_reason': '验证独立文稿与稳定技术块的升级保护',
                'sensitivity': 'internal', 'discovery': 'owner_only'}}]})
        assert result['save_status'] == 'committed', result
        record = service.inspect(v3_owner)['records'][result['record_results'][0]['record_id']]
        return {'target_kind': 'record', 'target_id': record['record_id'], 'revision': record['revision'],
                'sha256': record['record_hash'], 'locator': '', 'relation': 'references'}

    unit_ref = save_v3('detail', '合成独立方法', {'unit_type': 'method',
        'retrieval_description': {'question': '如何核对单位', 'method': '符号定义',
            'key_findings': ['长度单位应一致'], 'applicable': ['合成长度'],
            'not_applicable': ['其他量纲'], 'limitations': ['未执行实验']},
        'run_ref': None, 'evidence_refs': [], 'figures': [], 'missing_refs': [],
        'blocks': [{'block_id': 'definitions', 'role': 'definitions', 'markdown': '$x$ 为长度，单位米。', 'requires_block_ids': []},
                   {'block_id': 'method', 'role': 'methods', 'markdown': '比较前统一长度单位。', 'requires_block_ids': ['definitions']}]}, [])
    section_ref = save_v3('document_section', '独立方法章节', {'section_key': 'methods', 'title': '独立方法章节',
        'role': 'methods', 'blocks': [{'type': 'unit', 'ref': unit_ref, 'block_ids': ['method']}],
        'watch_refs': [], 'missing_refs': []}, [unit_ref])
    for document_type in ['research_process', 'research_report']:
        save_v3('document', '合成双文稿 ' + document_type, {'document_type': document_type,
            'purpose': '验证升级与固定章节', 'audience': '测试读者', 'scope': '隔离合成记录',
            'common_refs': [], 'section_refs': [section_ref], 'watch_refs': [], 'missing_refs': []}, [section_ref])
    home = root / owners.resolve_owner(root, v3_owner)['memory_home']
    for path in [home, *home.rglob('*')]:
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.add(relative)
        elif path.is_file():
            names.append(relative)
    # Maintenance plans are durable user work under .local, unlike rebuildable
    # index caches. Create one through the actual public application so upgrades
    # must preserve its real fixed context/read receipt and versioned plan bytes.
    # This is an unreviewed software fixture, never a fabricated AI assessment.
    from material_query.api import dispatch as material_dispatch
    from material_query.contracts import Scope, MaintenanceRequest
    from material_query.coordinator import Coordinator
    from material_query.legacy_adapter import from_legacy
    from material_query.wire import json_value
    material_app = Coordinator(root)
    try:
        material_scope = Scope((v3_owner,), None, None, None, None, None, None, False, (), (), None, None)
        request = MaintenanceRequest((from_legacy(unit_ref)[0],), material_scope, "dependency-review", "1")
        planned = material_dispatch(material_app, "maintenance-plan", json_value(request))
        assert planned.get('value') and planned['value']['plan_id'], planned
        # Reading sessions are durable user work too. Exercise the public
        # creation/decision API, then protect HEAD and immutable history bytes.
        template = material_dispatch(material_app, 'reading-template', {})['value']
        template.update(goal='SYNTHETIC ONLY 升级后接续阅读', conditions=['合成条件保留'], owner_id=v3_owner)
        template['query']['scope'] = json_value(material_scope)
        template['query']['scope_ceiling'] = json_value(material_scope)
        started = material_dispatch(material_app, 'reading-start', template)
        assert started['status'] == 'ok', started
        decided = material_dispatch(material_app, 'reading-decide', {
            'session_id': template['session_id'], 'expected_revision': 1, 'request_id': 'upgrade-decision',
            'direction': 'proceed', 'reason': '合成上下文足够', 'next_step': '升级后继续验证',
            'outcome': '', 'human_decision': ''})
        assert decided['status'] == 'ok', decided
    finally:
        material_app.close()
    plan_home = root / '.local/material-query/plans'
    for path in [plan_home, *plan_home.rglob('*')]:
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.add(relative)
        elif path.is_file():
            names.append(relative)
    reading_home = root / '.local/reading-sessions'
    for path in [reading_home, *reading_home.rglob('*')]:
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.add(relative)
        elif path.is_file():
            names.append(relative)
    # Raw execution containers may contain files named run.json which are data,
    # not business manifests. Upgrade must retain all bytes and empty folders.
    capture = 'runs/自动登记 升级/.run-captures/attempt-01'
    write('runs/自动登记 升级/run.json', json.dumps({'run_id': 'RUN-CAPTURE-UPGRADE',
        'status': 'failed', 'inputs': [], 'artifacts': [], 'claims': []}))
    write(capture + '/outputs/run.json', 'SYNTHETIC ONLY raw output, deliberately not JSON')
    write(capture + '/outputs/多层 结果/原始.txt', 'SYNTHETIC ONLY generated output')
    write(capture + '/registration.json', '{"synthetic": true}')
    write(capture + '/execution.json', '{"status": "failed", "exit_code": 3}')
    write(capture + '/stderr.txt', 'SYNTHETIC ONLY failed log')
    empty = capture + '/outputs/空 目录'
    (root / empty).mkdir(parents=True)
    directories.add(empty)
    return snapshot(root, names, directories)


def assert_preserved(root, expected):
    """缺失文件、目录或任何字节变化都失败；不自动修复测试目标掩盖问题。"""
    for name, fingerprint in expected['files'].items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != fingerprint:
            raise AssertionError('Protected file changed or missing: ' + name)
    for name in expected['directories']:
        if not (root / name).is_dir():
            raise AssertionError('Protected directory missing: ' + name)
    if 'research/用户迁移 样例/历史运行/结果.txt' in expected['files']:
        import evidence
        resolved = evidence.reference_path(root, 'runs/旧布局/结果.txt')
        if resolved != (root / 'research/用户迁移 样例/历史运行/结果.txt').resolve():
            raise AssertionError('Pinned source relocation no longer resolves')
