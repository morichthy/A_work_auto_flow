# 版本记忆使用指南

工作台“对象记忆”的常用筛选为 L0–L4 和研究文稿六类，章节归入研究文稿。目标、路线、问题、检查点、复核、策略等仍服务于工作管理，可在折叠的“辅助工作流记录”查看；不是额外知识层级。旧 event/map 在对应层级访问，原类型与历史不删除。新建或修订记录遵守[单条独立可读标准](RESEARCH_RECORDING.md#每条记录必须独立可读可以正确复用)。

本指南按当前工作树实现核对（2026-09-11），对应 `automation/scripts/memory/api.py` 和 `memory/cli.py` 的实际入口。示例中的对象 ID、文件路径、请求 ID 和修订号需要替换为当前工作区的值；示例不是业务结论或验收记录。模块职责以 [ARCHITECTURE.md](../ARCHITECTURE.md) 为入口；修改功能时按 [文档维护约定](DOCUMENTATION_MAINTENANCE.md) 检查本指南、请求示例与 Skill 的同步范围。

## 1. 先理解保存的对象

**对象（Owner）**是已经登记的研究、Run、项目、核心算法、知识材料、报告、数据或工具。记忆附着在对象上，原业务登记继续决定对象身份。普通工具不会因为拥有记忆而变成核心算法。

**记忆记录（MEM）**保存正文、适用条件、来源和保存原因。修改生成新修订，旧修订仍能读取。**结论（CLM）**是记录中可单独复核的具体断言；保存记录、程序执行成功和结论获得复核分别记录。

**对象 HEAD**指向当前已提交快照。一个批次可以保存多条记录；发布 HEAD 后才成为可见的新版本。请求中的 `expected_head` 和记录的 `expected_revision` 用于拒绝覆盖他人的新修改。`request_id` 用于重试：同一逻辑提交重用原请求及其 ID，修改了内容后使用新的 ID。

**来源引用（Ref）**保留目标身份、版本或指纹、定位与关系。`supports`、`input` 表达依据；`background`、`analogous_to` 等关系帮助发现相关材料，不授予结论有效性。导航关联也不能替代依据复核。

| 记录类型 | 主要内容 |
| --- | --- |
| `source` | L0 的内部来源记录：独立来源或受控摘录；Run 输入/产物由统一 L0 视图汇总，无需再复制一条 source |
| `detail` | L1：实验、方法、推导或分析技术单元；检索说明用于发现，稳定正文块保存完整解释，实验绑定原生 Run |
| `narrative`（v4） | L2：有依据的研究路线、尝试、失败、选择理由与转折，保存完整正文 |
| `experience` | L3：局部经验、适用与禁止迁移条件、失败模式 |
| `overview`（v4） | L4：项目/研究整体问题、方法、结果、当前阶段、限制和未决事项 |
| `document_section` | 独立章节，level=null；用衔接文字和固定技术块组织阅读 |
| `document` | 完整研究过程或精简研究报告，level=null；固定有序章节、目的、读者与范围 |
| `question` | 问题、尝试、剩余缺口与解决依据 |
| `goal` | 当前目标、成功条件及目标变化来源 |
| `route` | 研究路线、备选路线和限制 |
| `checkpoint` | 暂停点、当前状态和继续工作的入口 |
| `association` | 可接受或拒绝的导航关联 |
| `representation` | 同一规范记录的检索表示，不创造第二份事实 |
| `policy` | 本对象的记录与续接策略 |
| `consolidation` | 阶段巩固及其固定输入版本 |
| `feedback` | 纠错、无关、撤回或其他使用反馈 |
| `review` | 某个 CLM 的独立复核历史；通过专用 `review` 入口保存 |

当前字段以 [v4 聚合契约](../automation/schemas/memory-v4.schema.json) 和服务校验为准；[v2](../automation/schemas/memory-v2.schema.json)、[v1](../automation/schemas/memory-v1.schema.json) 保留历史读取。新 narrative/overview 默认 v4，分类 experience 显式用 v4，其他种类默认 v3；新草案按类型明确版本，不靠兼容形状猜版本。CommitRequest 封套版本与记录版本相互独立，不能靠修改封套迁移正文。旧 event/map 不再提供单独的工作台筛选或新建入口；尚未整理的对象记录仍在相应层级可见，但不会冒充新内容查询的 narrative/overview。旧 v1 存储 L1/L2/L3 分别投影为新 L2/L3/L4，历史字节与哈希不变；v2 detail 仍读取原正文。公式说明符号、单位与适用条件。研究默认覆盖见 [分层记录标准](RESEARCH_RECORDING.md)。

需要完整方法/分析时保存 L1 `detail`：`unit_type` 区分 experiment/method/derivation/analysis，`retrieval_description` 说明问题、方法、发现与适用边界，完整技术正文只写入 `blocks`，`body_markdown` 留空。实验必须固定引用实际 Run；未执行的方法、推导或分析可以令 `run_ref=null`，并交代依据或缺口。再用 v4 L2 `narrative` 的 stages 和正文记录“为何作出选择”及实际转折，固定技术依据；L3 `experience` 明确 knowledge_type 与边界，L4 `overview` 保存整体概览。跨研究不自动意味着经验。研究经过可保存 `occurred_at`、`failure` 和目标/路线/Run 引用；失败字段记录类别、范围、结果、不能推出的判断和重试条件。经验的 `failure_modes` 不能代替实际失败经过，也不重复登记实验。

### 整理旧事件和地图

先读旧正文、实际依据、失败与适用边界，再编写新内容。通过 `put_record` 修订同一个 ID：只允许 event→narrative、map→overview，记录版本为 4，必须有完整 `body_markdown`、`change_reason`，并在 `sources` 中用 `relation: references` 固定上一修订的 ID、revision 和 record_hash。仍需通过正常 schema、来源授权和 HEAD/修订冲突检查；服务不会自动推导正文或展开关联。

新修订成为当前记录，索引按相同身份更新，不同时留下两条当前记录；旧修订、旧引用及审查历史保持不变。将经过和技术单元保存回读后，再用实际 revision/SHA 写入经验、概览的展开关系。完成后以 `memory rebuild --request 请求.json` 提交 `{"scope":["对象ID"],"vector":"auto"}`，分别核对保存、全文索引与向量索引状态。数据整理不重跑实验，也不提升科学复核状态。

各类Owner默认使用work-loop，按有用内容保存L0依据、L1方法/分析、L2有依据的经过、L3可复用认识及L4概览。允许缺层，文稿按阅读和交付需要编排；不为每轮凑记录或强制双文稿。固定引用复用原件，来源主张、AI推断与本次验证明确区分。已有显式对象策略保留。

需要构造请求时，只读[请求示例](MEMORY_REQUESTS.md)的当前动作。work-loop统一归属/记录/续接，material-query负责查阅与阅读记录，其他专项按需使用。所有Owner可按内容组合L0–L4，缺层正常，文稿按需；默认normal与auto_summary=false不改写已有显式策略。旧research-loop/workspace-context保留兼容跳转，安装器默认登记7项。

## 2. 日常操作

在工作台打开记忆页，选择已有对象，再查看或编辑记录。先填写保存原因、来源和适用范围，再预检与保存。已有记录打开后会固定编辑版本；出现冲突时保留草稿，比较新版本后重新编辑。

暂停研究时保存检查点，继续时查看“暂停与续接”。研究经过展示版本变化、问题与目标演进；时间线中的“已解决”是历史状态，后续依据失效需要单独查看，不能据历史标签直接复用结论。

跨研究检索有两种用途：

- `exploration` 用于发现相关经验与线索，保留未复核状态、适用范围和缺口。
- `formal` 必须给出 `scope`；只输出经过当前证据检查的适用 CLM。找到相关内容、相似度高或阶段总结完成，都不等于正式复核。

材料包保留用户的包含、排除与全文选择及预算。证据不足时扩展材料包，继续查看缺口；不要把缺失来源补写成已知事实。跨项目总结固定参与对象的 HEAD，保存前再次核对；期间对象更新会要求重新准备。

## 3. CLI：读取、预检与保存

从工作区根目录运行。CLI 请求使用 UTF-8 JSON 文件，标准输出为 JSON；所有命令可加 `--help` 查看实际参数。

```powershell
.\workbench.cmd memory --help
.\workbench.cmd memory list-owners
.\workbench.cmd memory inspect RES-EXAMPLE
.\workbench.cmd memory inspect RES-EXAMPLE --record-id MEM-EXAMPLE --revision 1
```

对于尚未采用的材料，`list-owners` 返回 `native_ref` 和 `fingerprint`。采用只增加记忆入口，保留原文件；以下路径和指纹必须来自刚才的结果：

```powershell
.\workbench.cmd memory adopt-owner "knowledge/example.md" --expected-hash "实际指纹" --actor "local-assistant"
```

普通保存使用 `commit` 请求，批次内每项带 `op` 和 `draft`。新记录使用 `client_key`；修改记录使用 `record_id` 与 `expected_revision`。顶层包含 `schema_version`、`request_id`、`actor`、`owner_id`、`expected_head`、`operations`。草案可由工作台编辑器准备；不要直接写规范存储目录。

```powershell
.\workbench.cmd memory validate-draft --request ".local/commit-request.json"
.\workbench.cmd memory commit --request ".local/commit-request.json" --dry-run
.\workbench.cmd memory commit --request ".local/commit-request.json"
```

`review` 使用专用复核请求；普通 `commit` 不能伪造复核记录。执行者字段是审计声明，不等于身份认证。复核必须说明理由、范围和固定依据，且验证流程确实获得授权并适用于该结论。

历史记录按其固定修订和结论指纹追溯来源，同时服从当前对象与来源授权。新修订删去某个来源，不会解除旧修订及其派生记录的原来源限制；历史来源已撤权时，搜索、查看和上下文包会屏蔽相关正文。来源沿袭统计也沿固定历史版本计算；来源数量不代表独立科学支持数量。

结论引用只固定结论指纹，不带父记录修订号。如果结论字节未变、父记录来源却改变，权限检查保守合并所有匹配指纹的历史父记录来源，不能借新版本绕过旧授权。历史定位只在一次请求内缓存；修订很多或结论已从当前记录删除时，会增加历史读取成本，尚未给这种极端历史深度承诺固定延迟。当前已限制的对象会在追加读取历史正文前被拒绝，相关正文不会返回给调用方。

以下检索 JSON 可保存为 `.local/search-request.json`：

```json
{"query":"预热后仍漂移的失败经验","purpose":"exploration","stage":"focus","vector":"auto"}
```

```powershell
.\workbench.cmd memory search --request ".local/search-request.json"
```

正式查询将 `purpose` 改为 `formal` 并补充实际 `scope`。`vector: "off"` 可显式只使用非向量通道；可选能力缺失或索引待更新会出现在返回状态中。

`retrieval_mode` 默认为 `knowledge`：发现 L1 技术说明及更高层知识，v3 技术单元的检索说明与稳定正文块均可召回，候选预览仍用说明，完整正文在固定引用展开时读取。technical-blocks v4派生投影需要重建，旧水位不会因HEAD未变就算覆盖。查文稿或章节使用 `documents`，该模式使用全文通道并关闭向量，不能同时要求 `vector:"required"`。L0 追溯用 `trace` 并显式选择实际 ID，或用 `raw-materials` / `raw-material` 查看已登记材料。独立文稿不默认混入知识排名；三种模式都保留权限、排除和版本检查。

探索查询明确提到已有主题关键词时，优先列出该主题的具体记录；匹配结论和其完整 Run 同时出现时，先展示结论，Run 仍可按 ID 或引用读取。缺少关键词的记录和其他向量结果保留为后备；没有明确主题时仍使用原多通道排序。显式选择与排除保持优先，检索位置不代表结论已经复核。当前质量评价与已知限制以[执行状态](design/system-memory/STATUS.md)为准。

| 操作 | CLI 动作与请求要点 |
| --- | --- |
| 研究过程或精简报告 | `document --request 文件`，包含 `owner_id`；`document_type` 默认为 `research_process`，可选 `research_report`；用 `document_id` 和可选 `revision` 固定文稿 |
| 文稿目录与局部阅读 | `outline` 返回章节 ID；`section-context` 带实际 `section_id`、选择清单及 `budget:{"max_chars":20000}`；返回正文、遗漏和缺失前提 |
| 文稿变更影响 | `document-impact` 比较固定依据、变化关注和两类文稿使用的版本；只提示需复核的章节，不自动改稿 |
| 原始记录与旧版本 | `history --request 文件`，包含 `owner_id`，可用 `offset`、`limit` 分页 |
| 继续研究 | `resume --request 文件`，包含 `owner_id`，可带 `budget`、`selection` |
| 准备阶段巩固 | `prepare --request 文件`，包含 `owner_id`，可带 `since_commit`、`trigger` |
| 保存阶段巩固 | `consolidate --request 文件`，使用准备结果的固定依据 |
| 跨项目总结 | `summaries-prepare` 包含 `query`、`owners`；`summaries-save` 保存草案和 `basis_heads` |
| 导航关联 | `associations-propose` 准备候选，`associations-decide` 保存决定；`associations-view` 查看 |
| 用户纠错 | `feedback --request 文件`，保留纠错目标和原因，不抹去旧版本 |
| 下游影响 | `impact --request 文件`，包含 `changed_ids`；返回待复核对象与实际传播路径，不自动撤回结论 |
| 问题解决依据 | `question-validity --request 文件`，包含 `question_ref`，可带 `scope`；历史解决状态与当前依据有效性分开返回 |
| 来源沿袭 | `source-lineage --request 文件`，包含 `target_ids`；可访问来源身份数不代表独立科学支持数 |
| 可读导出 | `export --request 文件`，包含 `owner_id`，可选 `record_ids`、`exclude_ids`、`format` |

可读导出的 `format` 为 `markdown`、`json` 或 `html`，返回 `filename`、`content` 和固定版本清单。它不会生成另一条规范记录，也不是包含完整历史的迁移包。

新文稿由独立 `document` / `document_section` 编排，按问题、方法、技术单元、讨论与结论阅读；`research_process` 与 `research_report` 共用固定证据，分别维护正文。章节 `unit` 块固定 L1 修订，可选 `block_ids` 并补齐同单元必要定义；章节 `prose` 块集中写衔接与综合。读取服务只校验与组装，不调用模型临时改写。

只有缺少所选独立文稿时，默认过程阅读才回退到旧 `map.payload.report`（此时 `report_record_id` 用于旧编排）；缺少 `research_report` 会报告未编排，不把旧长文稿改标签充当精简报告。独立文稿可用 `include_records:true` 附带原始记录卡，默认不重复附加。保存后检查 `document_source`、`report.complete`、`report_coverage`、`report_version_hints` 和来源问题，再实际阅读全文；完整性标记不等于结论复核或写作质量验收。AI 写作与局部更新见 [报告编排](RESEARCH_RECORDING.md#连贯报告的编排)。

## 4. 看懂回执与恢复

首先检查 `save_status`，再检查索引和错误字段：

| 返回状态 | 含义及下一步 |
| --- | --- |
| `committed` | 规范记录已保存；保留请求 ID 和 commit ID |
| `no_change` | 内容相同，没有增加修订；仍可通过原请求查询回执 |
| `not_committed` | 此次未完成规范提交，按错误信息处理 |
| `INDEX_PENDING` | 可能已经提交，仅索引待补偿；先检查 `save_status`，不要重新创建业务记录 |
| `VERSION_CONFLICT` / `STALE_BASIS` | 当前版本或输入依据变化；读取新版本，重新准备草案 |
| `IDEMPOTENCY_CONFLICT` | 同一请求 ID 被用于不同内容；核对原请求与原回执 |
| `LOCKED` | 当前仍有写入者或不能证明写入者已退出；检查恢复入口 |
| `INTEGRITY_ERROR` | 规范文件或包损坏；保留现场，不手改指纹让校验通过 |

CLI 的 `INDEX_PENDING` 返回非零退出码 3，因此“非零”不总表示内容未保存。API 对该状态返回 202；其他错误也有结构化代码。

索引补偿请求示例：

```json
{"owner_id":"RES-EXAMPLE","vector":"auto"}
```

```powershell
.\workbench.cmd memory reconcile --request ".local/reconcile-request.json"
.\workbench.cmd memory recover RES-EXAMPLE
.\workbench.cmd memory recover RES-EXAMPLE --apply
```

`recover` 默认检查，`--apply` 只处理已证明退出的锁及可识别恢复状态；不能据此覆盖活跃写入者。FTS、向量和材料视图属于派生索引，可以从规范记录重建。重建索引不修改原材料，也不重新验证业务结论。

## 5. 导出和导入一个对象的历史

`migration-export` 打包所选对象的原登记、可达提交历史、记录和回执。包不递归复制其他对象或引用原件。缺少依赖会在清单中声明；旧格式引用以 `legacy_target` 保留原定位，不自动授予目标机读取权限。

导出请求示例：

```json
{"owner_id":"RES-EXAMPLE","output":".local/exports/example-memory.zip"}
```

```powershell
.\workbench.cmd memory migration-export --request ".local/export-request.json"
```

在目标工作区准备预览请求。`package` 指向用户选定的包；可选 `path_mapping` 仅映射该对象的原登记文件位置，规范历史中的引用和指纹保持原样：

```json
{"package":"C:/Transfer/example-memory.zip","path_mapping":{"research/example/research.json":"research/imported-example/research.json"}}
```

```powershell
.\workbench.cmd memory migration-preview --request ".local/import-preview-request.json"
```

预览结果就是固定 `plan`。将完整结果放入 `{"plan": ...}` 的请求文件，再运行：

```powershell
.\workbench.cmd memory migration-import --request ".local/import-request.json" --dry-run
.\workbench.cmd memory migration-import --request ".local/import-request.json"
```

导入前校验路径、清单、指纹、契约、历史和冲突。导入仅创建缺失且一致的文件；同包重复导入返回 `no_change`，不同现有内容会被拒绝。包中没有的原件不会被自动复制。目标机缺失或尚未核对的依赖列在 `missing` 中，记录可以保留，但不能因此视作正式可用依据。

导入结果包含 `receipt_path`。恢复请求为 `{"receipt_path":"实际回执路径"}`，`migration-recover` 默认预览；请求中显式设置 `"dry_run": false` 才执行恢复。恢复只移除本次导入创建且指纹未变的文件；导入后的用户修改会使恢复被拒绝。

## 6. 从旧材料提取草案

`ingest-preview` 接受一个标准 `request` 和固定 `source_ref`，生成不可随意修改的计划；`ingest-apply` 接受 `{"plan": ...}`。原件必须已登记并获准读取，预览与实际保存之间再次核对来源版本。

提取保存解释性记录；不伪造原始 `source` 或独立 `review`，不补造发生时间、失败结果、执行者确认。未知字段维持未知；相同来源和相同解释草案再次执行复用原提取身份。原件变化后需要重新预览。

## 7. 文件由谁维护

- 原对象登记及业务材料：用户和原业务流程维护；采用与记忆保存不改写原件。
- 对象 `memory/` 或平面材料对应的记忆目录：记忆服务维护。`owner.json` 记录归属，`HEAD.json` 指向快照，`commits/` 保存不可变历史；不要手动清理孤立目录或改写回执。
- `.local/memory-migrations/`：导入暂存与恢复回执。保留需要恢复的批次，直到已确认不再需要。
- 本地索引与检索缓存：索引命令维护。删改缓存不等于撤回结论；撤回应保存正式反馈或复核变更，并检查下游引用。

框架整体升级仍使用 [部署手册](SETUP_WORKBENCH.md) 的 `setup.cmd --target` 流程，保留旧工作区目录和业务数据。单对象迁移不能替代完整依赖部署；跨机器安装、模型兼容和配套依赖包范围见 [依赖分发手册](DEPENDENCY_RELEASE.md)。
