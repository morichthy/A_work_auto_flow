# 工作台开发与扩展

现行说明核对日期：2026-09-13。主要维护面包含材料关系、业务证据、版本记忆/研究文稿及材料查询 v0.2；全局数据流与模块影响见 [架构说明](../ARCHITECTURE.md)，其他细节从 [文档索引](README.md) 进入。本页按前端/API 影响阅读，不是每次开发的全量必读文件。

使用者通过 `setup.cmd --register --open` 安装并打开；开发者才需要 Node。预构建资源随源码分发，Python 服务不调用 npm，不从 CDN 取脚本。

## 代码边界

| 位置 | 职责 |
|---|---|
| `automation/frontend/src/App.tsx` | 应用外壳、静态页面注册、导航与任务状态 |
| `src/Relations.tsx`、`src/Evidence.tsx` | 材料关系、证据页面及交互状态 |
| `src/Memory.tsx`、`src/ReadingSessions.tsx`、`src/memory-contract.ts` | 对象记忆、L0、研究文稿、按Owner的实时阅读记录与固定请求的界面/契约检查 |
| `src/CurrentReading.tsx`、`MaterialNavigation.tsx`、`ReadingEvidence.tsx` | 当前笔记共享选择/Markdown正文、Owner与主题深链接、仅从笔记固定引用展开的一层来源；不把全库或同Owner的记录冒充证据 |
| `src/MaterialQuery.tsx`、`MaterialStructure.tsx`、`MaterialPacket.tsx` | 材料查询、逻辑/存储范围、固定候选与材料包；表示选择不是规范层级迁移 |
| `src/components.tsx`、`src/group-view.ts` | Canvas、详情对话框、只供展示的聚合 |
| `src/graph-model.ts` | 选择、排除、局部 BFS、范围一致的摘要 |
| `src/cluster.worker.ts`、`src/cluster.ts` | Louvain 与跨组候选的独立 Worker |
| `contracts/graph.schema.json`、`src/generated/contracts.ts` | 图 API 契约与生成类型 |
| `automation/schemas/memory-v4.schema.json`、`src/generated/memory-schema.ts` | 当前记忆契约与前端生成副本；旧v1–v3按版本兼容；新L1/文稿仍用v3 |
| `automation/scripts/material_query/contracts.py`、`automation/schemas/material-query.schema.json` | 查询运行字段真源与生成 schema；同一前端生成流程纳入查询契约 |
| `automation/scripts/workbench_app/web.py` | `/api/v1/` 路由、资源清单校验 |
| `service.py`、`cli.py` | 网页与命令行共享用例与输入边界 |
| `projection.py`、`analysis.py` | 业务材料适配、关键词及只读向量分析 |
| `automation/scripts/memory/api.py`、`service.py`、`store.py` | CLI/HTTP 固定动作、领域提交和对象不可变存储 |
| `memory/index.py`、`search.py`、`packets.py` | 可重建索引、规范身份排序及有预算的材料包 |
| `memory/technical_units.py`、`documents.py` | L1 技术块与独立双文稿/章节的读取、编排和影响检查 |
| `automation/scripts/material_query/api.py`、`coordinator.py`、`state.py` | 查询应用动作、范围/预算和短期查询状态；复用原 memory 存储，维护计划独立持久保存 |
| `jobs.py`、`storage.py` | 串行任务、进程锁、取消、原子本机存储 |
| `automation/scripts/workbench.py`、`evidence_view.py` | 启动、兼容旧入口、并发 HTTP 与同源保护 |
| `automation/ui/workbench-assets/` | 随发布包交付的 JS、CSS、Worker、许可和哈希清单 |

物理目录不是业务图数据库。原材料仍为现有 JSON/Markdown 和受控原件，规范记忆由各对象的 HEAD/不可变提交维护；投影、分析、视图偏好和候选独立保存。新 Run 按唯一对象归属保存，旧位置不因工作台升级而搬移。聚合边不写回正式依赖；`supports`、`input` 与 `contradicts`、`background` 保持原义及方向。

L1 v3 保存检索说明与稳定技术正文块；新完整过程和简版报告用独立 document/document_section 固定引用。L2 统一为研究经过、L4 统一为整体概览，筛选/新建/总结只提供一个入口；旧记录的实际迁移经统一写服务保存完整新修订，不通过界面别名伪造新内容。旧固定引用仍可读。界面不得直接修订规范 JSON、假设原始日志可常规搜索或以候选处理状态替代结论复核。材料关系页的两跳展示、memory 导航关联及评估用图扩展相互独立，默认 `memory context` 未自动执行整个关联遍历。详见 [检索](RETRIEVAL.md) 与 [材料关系](MATERIAL_RELATIONS.md)。

## 开发命令

历史构建记录使用过 Node 22.11、npm 10.9；开发时记录实际环境，依赖精确版本以锁文件为准。

```powershell
cd automation/frontend
npm ci
npm run build
npm test
npm run e2e
npm run format:check
```

`npm run dev` 监视源码并构建资源与清单。另开终端从仓库根运行 `workbench.cmd workbench --demo`，使用返回地址；修改后手动刷新浏览器。开发与生产使用相同的随机路径和 API，不另开绕过同源保护的代理。首次构建完成后再启动服务；重建瞬间资源不齐时，刷新重试。修改 Schema 后运行 `npm run contracts`，不要直接编辑生成文件。

E2E 在 Windows 使用已安装的 Edge，测试服务仅监听回环地址，`windowsHide` 启动，测试结束关闭。夹具按调用生成到 `.local` 或 `tmp`，不发布实例。非 Windows 开发者需要为 Playwright 配置可用浏览器；当前交付验收针对 Windows。

## 增加页面

页面采用首次访问后保留组件的标签页内生命周期，功能切换不应卸载已生成的结果或草稿。隐藏页面避免重复网络读取；真实任务更新、显式刷新和对象切换仍须处理失效与异步竞态。系统记忆默认“研究经过”，对象记忆显式生成；新增子功能需同时验证切走再返回、对象切换和旧请求晚到。此状态不写入浏览器持久存储，也不延长服务器查询有效期。

在 `src` 添加组件，在 `App.tsx` 的 `pages` 静态数组与页面分支登记，并通过 `api.ts` 调用相对 API。最小页面可只读能力信息：

```tsx
// 固定内部接口；状态失败应显示原因，不将未加载误报为空。
export function Overview({text}: {text: string}) {
  return <section className="card"><h1>概览</h1><p>{text}</p></section>;
}
```

数据写操作走固定服务用例；禁止将用户材料作为 HTML 或脚本执行。需要交互回归时加入 Playwright 场景；测试范围优先验证真实选择、边界及失败行为。

## 增加材料适配器

在 `projection.collect` 中映射已登记源，复用 `file_node`、`target`、`edge`，不要扫描整个共享盘。已有业务 ID 优先，普通文件按相对路径生成身份。最小关系映射示意：

```python
# 必须保留原字段与定位；belongs_to 是归属，不是验证依据。
edge(owner_id, target(existing_ref), 'belongs_to', metadata_path, 'related_ids')
```

新字段需明确其关系方向、指纹来源、缺失行为以及读取边界。把元数据中的 `project_id` 引用误当新主体会造成身份污染；主体只从对应身份卡建立。不要因添加工具适配器创建核心算法卡。

## 增加计算任务

在 `service.request_job` 固定允许的任务类型，计算放独立函数，通过 `Jobs.submit` 排队：

```python
def compute(progress):
    # progress 在批次间检查取消。先完成临时结果，再原子替换缓存。
    result = calculate_from_authorized_inputs(progress)
    progress(1, 1)
    return self.store.write('new-analysis', result)
```

结果记录方法版本、源指纹、范围、排除与遗漏。任务失败不得替换旧缓存。向量只读函数检查既有集合、模型身份与源版本；不创建集合、启动索引或删除锁。CPU 图计算优先 Worker；页面可继续查询轻量状态。HTTP 固定动作，不开放任意命令执行。

## 契约、资源与发布

图 Schema 版本为 1；记忆记录契约为 v3，兼容历史 v1/v2；材料查询应用契约为 v0.2。不要把 HTTP `/api/v1/` 或向量集合 `memory_v1_*` 当作记录版本。图、memory 和 material_query 由各自运行契约验证，前端副本来自各自 Schema；`npm run contracts` 同步前端生成项。后端生成工具在对应模块，改变字段时同步真实调用方与边界测试，不能编辑设计目录来代替修改运行真源。

构建后 `asset-manifest.json` 包含资源 SHA-256、所有前端源码哈希和总体源码指纹，附生产依赖及传递依赖许可。启动和框架升级检查源码与构建一致，每次资源响应校验文件。前端源码、锁文件、预构建资源需要一起交付；`node_modules`、测试实例与浏览器报告均排除。

`deployment.framework_files` 按资源清单纳入升级及备份，`portable.py` 排除开发缓存。修改前按 [分级测试入口](TESTING.md) 选择验证；前端变更后必须重建资源和指纹，涉及发行清单、扫描、安装或恢复还需执行真实 setup 的扩展旧工作区场景。纯文档修订不因此重跑全部模型或性能测试。结构性变更后运行 `refresh-index`、`validate`，实际文件检索材料变化时再刷新对应索引。完整集成验证要求实际必要模型，基础配置缺模型应明确报告，不能将跳过算作完整通过。

当前保留旧 `evidence-view --serve` 与静态证据页；它们不具备材料图写入接口。新工作台使用生产 CSP，不允许内联脚本。本文扩展代码是接口示意，必须结合已有授权范围和错误处理落地。
