# 记录、Run 与检索索引：用浮点求和研究理解

2026-09-13补充：各Owner按有用内容组合层级，默认normal、auto_summary=false；阅读清单在工作台系统记忆内，RS以owner_id/可选checkpoint_ref关联，HEAD保存状态，Markdown是版本快照。路径与生命周期见[对象/Run/阅读记录](OBJECT_RUN_STORAGE.md)。

核对日期：2026-09-15（本轮查询计划影响范围），依据当前工作树。本页是 [CORE](CORE.md) 的按需补充：只讲关键概念、字段和对应实体，不列完整契约。**记录保存内容与依据，Run 保存一次运行，索引帮助找到内容。**

实例来自完整工作区的 [floating-point-summation](../research/floating-point-summation/README.md)。公共源码发行包不包含该研究或本机数据库；缺少实例时可读本文解释和实现链接，不代表程序缺少功能。示例用于说明存储，不重新确认实验结论。

## 1. L0–L4、记录、正文块和 Run

| 概念 | 保存什么 | 对应实体或字段 |
|---|---|---|
| Run | 一次执行的输入、代码、环境、结果和日志 | 对象内 `runs/<run>/`，总登记为 `run.json`；不是 memory 的一种 `kind` |
| L0 | 原始依据的统一清单与读取入口 | 汇总 Run 登记和固定来源；原件留原位置，不统一复制进 memory。独立来源可用 `kind=source` 记录，已有 Run 附件无需重复登记为 source |
| L1 | 实验、方法、推导或分析技术单元 | `kind=detail`；`payload.retrieval_description` 是检索说明，`payload.blocks` 保存完整技术正文 |
| L2–L4 | 研究经过、经验、整体概览 | `kind=narrative/experience/overview`；正文在 `body_markdown`，结构信息在 `payload` |
| 完整／精简文稿及章节 | 按阅读顺序组织已有依据与正文 | `kind=document/document_section`，`level=null`；`payload.document_type` 区分 `research_process/research_report` |
| 正文块 | 一条记录内部的一段内容，不是独立记忆记录 | L1 的 `payload.blocks[]` 使用 `block_id`、`markdown`；`requires_block_ids` 指明阅读所需定义 |

层级是内容职责，不是可信等级，也不是全部记录种类。目标、路线、问题、检查点、复核、关联、检索表示等另有类型。Run 是实验档案，L0 是查看这些档案中原始依据的入口，因此可以指向相同文件。实验类 L1 固定引用 Run；更高层沿技术单元、经过或原始来源引用，不逐层复制。

定义以 [RESEARCH_RECORDING](RESEARCH_RECORDING.md) 和 [运行契约](../automation/schemas/memory-v4.schema.json) 为准。

## 2. 一条记录与旁边的文件

例子：[《大数抵消场景的求和方法局部比较》第4版 JSON](../research/floating-point-summation/memory/commits/COM-3a8bbf38-bea9-4cea-90c9-e363107365fe/records/MEM-58fd845a-05a5-516c-8bbe-c88d887cbb91.json)。下列字段都在这一个文件里：

| 内容 | 关键字段 |
|---|---|
| 身份与分类 | `record_id`、`owner_id`、`kind`、`level` |
| 标题、关键词、正文 | `title`、`keywords`、`body_markdown` |
| 条件与建议 | `payload.applicable`、`prohibited`、`recommendation` |
| 原始依据、经过和技术关联 | `sources`、`payload.process_refs`、`technical_refs`；固定引用用 `target_id`、`revision`、`sha256`、`locator` 指明材料、版本与位置 |
| 历史与一致性 | `revision`、`previous_revision`、`change_reason`、作者/时间、`content_hash` 和 `record_hash`；指纹不证明内容正确 |

记录更新时保存新版本，旧版保留。整个研究共用以下管理文件，并非每条记录各建一套：

| 实体 | 作用与关键字段 |
|---|---|
| [owner.json](../research/floating-point-summation/memory/owner.json) | `owner_id` 和 `native_ref` 登记属于哪个研究、研究原生文件在哪 |
| [HEAD.json](../research/floating-point-summation/memory/HEAD.json) | `commit_id` 指向当前提交，`generation` 表示更新代数 |
| [manifest.json](../research/floating-point-summation/memory/commits/COM-1ded0a16-df08-4c51-b3ee-ee9988569d9c/manifest.json) | `record_heads` 列出每条记录当前的 `path`、`revision` 和指纹；先由 HEAD 找到这份清单，再找记录文件 |
| [receipt.json](../research/floating-point-summation/memory/commits/COM-3a8bbf38-bea9-4cea-90c9-e363107365fe/receipt.json) | `save_status`、`record_results`、`index_status` 保存当次提交结果；旧回执中的 pending 不是现在的索引状态 |

第一轮实验的文件则各有职责：

| 实体 | 作用与关键字段 |
|---|---|
| [run.json](../research/floating-point-summation/runs/run-20260908t201214z-d0ab308f66ad/run.json) | 总登记：`question`、`parameters`、`inputs`、`code`、`environment`、`metrics` |
| [inputs.json](../research/floating-point-summation/runs/run-20260908t201214z-d0ab308f66ad/inputs.json) | `methods` 保存方法，`cases[].values` 保存实际数组 |
| [results.json](../research/floating-point-summation/runs/run-20260908t201214z-d0ab308f66ad/results.json) | `rows` 保存逐项结果，`summary` 保存汇总，`reference` 说明精确基准 |
| [reproduce.py](../research/floating-point-summation/runs/run-20260908t201214z-d0ab308f66ad/reproduce.py) | 当次计算脚本 |
| [execution.json](../research/floating-point-summation/runs/run-20260908t201214z-d0ab308f66ad/execution.json) | 实际 `command`、起止时间和 `exit_code` |

同目录 README 是阅读说明，stdout/stderr 是输出与错误日志，lineage.jsonl 用于血缘记录；部分 Run 另有图表、验证报告和来源指纹清单。历史文件中的旧路径可能通过来源迁移映射解析，不能为了链接方便改写冻结文件。

## 3. 索引到底存什么

关键词库是 [retrieval/generated/search.sqlite3](../retrieval/generated/search.sqlite3)，它不止三张表。以下三张负责普通记录召回，都是可重建投影：

| 表 | 一行代表什么 | 关键内容 |
|---|---|---|
| `memory_records` | 一个当前可检索实体的信息；普通记录通常一行，也兼容 claim 和原生 Run 投影 | 身份、`kind`、`level`、版本、标题、`body`、`keywords`、结构信息及 `source_ref` |
| `memory_entries` | 一个可分别命中的文本单元 | `entry_id`、所属 `record_id/canonical_id`、`title`、`text`；正文块还带 `block_id` |
| `memory_fts` | 一个搜索条目的全文索引行（FTS5 虚拟表） | `entry_id` 对应条目，`title/text` 存拆分后的词项，由 FTS 建立查找索引 |

**records 管整条记录，entries 管搜它的哪段文字，fts 管快速找到匹配词。** 例如一条 L1 有3个正文块，通常对应1行 records、4行 entries（检索说明＋3块正文）和4行 FTS。L2 通常对应1行 records 和1行 entries：正文在两表中有部分重复，不是二选一。

`memory_records` 不是原 JSON 的完整备份，也不保存所有历史版本。普通记录的 title/keywords 通常沿用原字段；body 可追加适合检索的结构内容。新 L1 的 body 使用检索说明，完整 blocks/figures 不复制到该行 payload，块正文另进 entries。L0 正文不进入普通召回；文稿、章节和检索表示另有处理。`source_ref` 是带身份、版本和定位的结构化引用，不只是文件路径。

关系、摘要表示和索引进度另由辅助表保存。语义向量存于 [Qdrant storage](../services/qdrant/storage/) 下的集合 `storage.sqlite`：每个文本窗口有向量及记录ID、版本、指纹、`start/end` 位置。当前模型生成384维向量；实际路径和模型见 [config.json](../retrieval/config.json)，集合随编码/模型版本隔离，不把某个集合名写成永久路径。实现见 [index.py](../automation/scripts/memory/index.py)。

## 4. 一次查询怎样用这三张表

以下是说明流程的简化例子，不是本次执行的查询结果：L1记录A的“讨论”块写着“小增量被舍入丢失”，查询“舍入丢失”。

1. **FTS找文字**：将问题拆成“舍入、入丢、丢失”，在 memory_fts 找到匹配条目并计算相关度。
2. **entries定位块**：由 entry_id 得知命中属于记录A、具体是哪个 block_id。
3. **records确认身份**：取得A的层级、版本、归属等，检查查询范围和类型；同一记录多个块命中时合并。
4. **回源阅读**：返回固定候选与命中位置，按需读取该版本原文和必要定义。实际主要通过一次连表查询完成，不是逐表扫描全部正文。

关键词不只匹配手填 keywords：它索引 entries 的标题和检索文本拆出的词项。中文按相邻双字拆分，英文保留并拆分标识符，不仅挑少数“重要词”。但并非任意子串匹配：例如“浮点”不一定被单字“浮”命中，符号或不同措辞也可能漏检。当前查询词按 OR 匹配，任一词命中即可；范围、候选窗口和预算也影响最终返回，空结果不证明不存在材料。

预建词项索引相当于“词 → 出现在哪些条目”的目录，避免每次逐行读取全部文本；它与直接字符串匹配的语义不同。拆分见 [retrieval.py](../automation/scripts/retrieval.py)，连表与合并见 [coordinator.py](../automation/scripts/material_query/coordinator.py)。

2026-09-15增加的AI双语阅读计划位于这三表之外：AI填写中英等义句，reading-recall按领域读取[术语库](QUERY_TERMS.md)，词法使用紧凑同义词/别名，关联词单跳另查，向量使用完整语句。结果按固定记录融合并保留块/query来源；本轮词库指纹和计划保存在RS，续页不跟随词库改动。它不重写原记录或向三表灌入生成答案；型号、数值条件仍需回读正文判断。

显式启用语义查询时，本地模型将问题转成向量，与已索引文本窗口比较相似度，再核对条目版本和指纹；混合查询融合两路排名。它可补充不同措辞的候选，但不保证全召回或结论正确。实现见 [recall.py](../automation/scripts/material_query/recall.py)，原文读取见 [reader.py](../automation/scripts/material_query/reader.py)。

## 5. AI 怎样生成这么多字段，可靠吗

**AI 写内容草案，程序校验、生成管理字段并建立索引。** [请求示例](MEMORY_REQUESTS.md)和[写作标准](RESEARCH_RECORDING.md)类似填写指导，真正的强制规则来自 [Schema](../automation/schemas/memory-v4.schema.json)和[校验代码](../automation/scripts/memory/contracts.py)。

| 责任方 | 负责内容 |
|---|---|
| AI／人 | 标题、关键词、正文、适用条件、记录类型、修改理由，以及选择真实的固定依据；未知项明确留缺口 |
| 保存服务 | 校验草案和引用；生成记录ID、版本、时间与指纹；作者信息来自提交请求，不等于身份认证 |
| 存储与索引程序 | 写不可变版本、HEAD、manifest、回执，再生成搜索条目、FTS和向量 |

正常入口为 `memory validate-draft → commit --dry-run → commit → inspect`，预演按需使用；commit 本身也执行校验，不能靠跳过预检绕过。程序检查必填与类型、类型/层级关系、实验Run绑定、引用解析及适用的版本/指纹检查，并拒绝覆盖已更新版本。保存后还要回读正文和引用，另查索引状态；索引失败应补偿，不重复创建记录。实现见 [service.py](../automation/scripts/memory/service.py)、[store.py](../automation/scripts/memory/store.py)。

这些检查能约束结构和追溯关系，**不能判断关键词是否充分、限制是否全面、引用是否真正支持推论**。有模板且校验通过，不等于研究正确；复核走专用入口，普通提交不能伪造复核。AI应使用公共入口，直接手改规范文件会绕开正常提交流程。保存、索引和科学复核始终分别表达。

## 维护要求

2026-09-13补充：AI阅读会话的“阅读记录”与这里的规范知识记录不同。前者在 `.local/reading-sessions/RS-…/HEAD.json` 保存当前问题、条件、固定候选身份、AI理解、必要细节和下一步，并保留修订历史；不把原技术正文再复制一份，也不自动进入索引。原记录、SQLite与向量对应关系不变。恢复时重查授权，旧版理解遇新修订会提示复查；笔记保存不证明理解正确。各实体和操作见[AI阅读手册](AI_READING.md)。这个目录是用户工作数据，升级保留，不能因位于 `.local` 就当缓存删除。

本页是当前解释，不是冻结设计。涉及记录类型/字段、L0与Run登记、保存/校验/回执接口、索引投影/分词/向量、查询连表/排序/回源或AI写作职责的开发，**须同次主动核对并更新本页、CORE对应链接与必要示例**，记录核对日期；无需修改也在任务摘要注明。保持直白解释、关键字段及实体链接，不扩展成完整字段清单。完整定义仍以记录标准和运行契约为准；不改冻结实例来迎合说明。维护触发统一见 [DOCUMENTATION_MAINTENANCE](DOCUMENTATION_MAINTENANCE.md)。
