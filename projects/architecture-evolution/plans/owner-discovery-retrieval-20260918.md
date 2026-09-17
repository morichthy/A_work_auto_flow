# Owner 压缩发现索引与互补筛选包开发计划

日期：2026-09-18。状态：已实施并完成关键功能、升级和调用链验证；效果/性能评估按约定未开展。归属：PRJ-ARCHITECTURE-EVOLUTION。

## 目标与明确边界

默认 AI 阅读先通过独立压缩发现索引找到尽可能多的相关 Owner，再为排序后的 Owner 生成覆盖互补筛选包供 AI 批量判断；AI 选中的 Owner 继续逐篇完整阅读。默认发现不查询 L1 blocks、完整文稿或 L0 原件；发现索引不可用、覆盖不足或结果不足时只提示，是否开启全库全文补偿召回由用户决定。

L0–L4 同时作为所有 Owner 的通用内容压缩、发现和展开层级。预期长期复用的新建或实质更新 Owner 至少维护一条自足 L4；短经验可只有 L4 且正文即全文。与主体目标不同但可迁移的经验形成 L3，方法/定义/计算细节进入 L1 `retrieval_description` 和 blocks。形成记录时分别维护展开、依据和联想关系。

本计划不执行 Owner 召回率、延迟、候选数量、CE 成本、上下文占用或错误联想率评估，不据本轮软件测试宣称性能或检索质量提升。旧 Owner 的发现缺口不只生成审计清单：由低等级模型实际阅读、通过公共 MEM 接口修订，成功后立即建立新发现索引；失败项保留明确原因。

详细目标算法与状态边界见 [Owner 发现设计](../../../docs/design/OWNER_DISCOVERY_RETRIEVAL.md)。

## 0. 实施前先固定功能基线

代码改动前先执行并保存现有相关回归的原始结果，至少覆盖 `test_memory_index`、`test_material_recall`、`test_reading_query_plan`、`test_reading_reranking`、`test_reading_reranking_integration`、`test_reading_owner_document` 和 `test_reading_workflow`。其中“记录候选先截断再折叠Owner”“任一超长输入导致整窗CE回退”“read_owner优先单份过程文稿”属于本次准备替代的现状，只保存为改造前观察，不登记为要求长期保留的正确行为。

随后先写目标契约测试并确认在旧实现上按预期失败，再修改产品代码。权限、固定版本、预算、旧RS和已选Owner全文授权等既有正确边界继续保持通过，不能为让新红测变绿而放松。测试输入固定在下面的共享合成工作区，红/绿输出保存到本次实施 Run；测试 catalog 只在用例真实存在并通过后登记。

实施前基线按测试文件逐项运行，不启动效果评估脚本。`automation/tests` 不是 Python package，不能使用 `automation.tests.*` 模块名；以下命令是本轮实际验证过的入口：

```powershell
$tests = @(
  'test_memory_index.py',
  'test_material_recall.py',
  'test_reading_query_plan.py',
  'test_reading_reranking.py',
  'test_reading_reranking_integration.py',
  'test_reading_owner_document.py',
  'test_reading_workflow.py'
)
foreach ($test in $tests) {
  .\automation\python.ps1 -m unittest discover -s automation/tests -p $test -v
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

合成工作区由 `test_memory_discovery_index.py` 的 `TemporaryDirectory` 和 `material_query_fixture.py` 共同建立，避免把运行数据留在仓库。覆盖对象至少包含：

- A：一条 L4、两条 L3、多条 L1 blocks，多个查询变体重复命中同一 Owner；
- B：只在 L3 出现跨主体可迁移经验；
- C：只在 L2 结构字段中出现过程/失败原因；
- D：技术词只出现在 L1 `retrieval_description`，完整 block 超过 512 token；
- E：简短经验，只有一条完整 L4；
- F：旧 Owner 缺 L4、L1 `retrieval_description` 缺失或为空；另准备一条字段非空但语义覆盖不足的 L1，供低等级模型在完整阅读后判断并修订；
- G：restricted、撤权或 HEAD/指纹已变化，用于拒绝与陈旧投影；
- H：正文含相似词但属于不同 Owner，且存在 accepted/candidate association，用于验证联想不变成证据。

先新增或冻结以下功能用例；目标能力尚不存在的测试先失败，不能修改断言迁就当前实现：

| 基线组 | 首个测试与关键断言 | 建议位置 |
|---|---|---|
| 现行兼容 | 固定现有 fixed-ref 去重、不同 revision 不误合并、route/query provenance 不丢失；旧 legacy RS 行为不变 | `test_reading_query_plan.py`、`test_reading_workflow.py` |
| 索引隔离 | 发现查询只读 discovery 表/collection；全文独有词默认不命中；删除发现投影后明确 unavailable，不能悄悄改查全文 FTS | 新建 `test_memory_discovery_index.py` |
| 派生与水位 | L4/L3/L2结构/L1检索说明各生成正确条目；L1 blocks、document、L0不进入；Owner HEAD/源指纹变化使旧投影 stale；reconcile只修投影 | `test_memory_discovery_index.py` |
| 权限与固定版本 | restricted、撤权、排除 Owner 和 fixed ref 失配均不能借投影返回；命中回映射到当前规范身份 | `test_material_recall.py` |
| Owner 融合 | 同一信号族每 Owner 一票；查询变体不重复加权；identity/lexical/dense provenance 全部保留；分页稳定且不因单 Owner 多记录挤掉其他 Owner | `test_reading_query_plan.py` |
| 互补筛选包 | 每 Owner 核心命中必有，新增窗口必须提供通道/记录/位置/受保护条件增量；精确重复去除；通常 2–3、硬上限4；标明 coverage 不完整 | 新建 `test_reading_owner_screening.py` |
| CE 窗口 | 单条 query+window 不超过512 token；长项围绕真实命中截窗；一个长项不使整批回退；auto/required 原失败语义和账本保留 | `test_reading_reranking.py`、`test_reading_reranking_integration.py` |
| AI 批量判断 | 一批 Owner 可分别保存 relevant/uncertain/irrelevant；只有 relevant 进入标准全文阅读；uncertain 不自动触发全文补偿 | `test_reading_owner_document.py` |
| 用户全文补偿 | 默认响应提供缺口和可选动作；没有显式用户动作时不查询 blocks/documents；显式动作复用冻结范围、查询计划、预算和版本 | `test_reading_owner_document.py`、API/组件测试 |
| 已选 Owner 全文 | 未交付 Owner 拒绝；选中后按当前全部可读正文分页到 `has_more=false`，精确去重并保留未展开 L0/图片/Run 缺口 | `test_reading_owner_document.py` |
| 旧 Owner 修订 | 程序只判定缺 L4、L1说明缺失/为空、投影未就绪、固定来源/权限/HEAD变化；低等级模型在固定HEAD全文上判断非空说明的语义覆盖。L4/L1说明/L3草案经 CAS 提交和回读；不得改 review/原件；逐 Owner 成功后立即重建，失败不阻塞其他 Owner | 新建 `test_discovery_repair.py`，外加实际AI场景记录 |
| 升级恢复 | 新表/collection可从旧工作区当前 HEAD 重建；重复升级幂等；rollback保留规范记录和旧索引；损坏水位拒绝假成功 | `test_memory_index.py`、真实 setup fixture |

这些是行为与安全基线。包条数断言用于保证接口边界，不作为“候选数量收益”评估；测试不记录或比较 Recall、延迟、模型费用和上下文成本。

## 1. 冻结发现投影契约

- [x] 新建 `automation/scripts/memory/discovery.py`，集中定义 `DiscoveryEntry`、来源选择、projection version、稳定 `projection_id` 和投影文本规范化。
- [x] SQLite 新增 `memory_discovery_entries`、`memory_discovery_fts`、`memory_discovery_index_state`；schema 初始化和升级集中在 `memory/index.py`，不复用 `memory_representations` 业务含义。
- [x] 定义独立 Qdrant collection/namespace，payload 固定 projection/source signature、Owner、层级和当前版本；沿用标准384维模型时仍与全文 collection 分开。
- [x] 水位至少区分 lexical/vector 的 `indexed|pending|unavailable|stale|failed`、Owner HEAD、projection version、模型指纹和最后错误。
- [x] 明确 `rebuild-discovery` 输入为 `owner_id + expected_head + projection_version`，按 Owner 幂等；lexical/vector 分别记状态，任一失败都不得把整体标为 indexed。执行中 HEAD 变化时标记 stale，不自动改用新 HEAD；规范内容已经保存但投影失败时只重试投影，不再次提交内容。
- [x] 定义构建输入：Owner元数据、L4、L3、L2紧凑结构、L1 retrieval_description；明确排除 blocks、documents、L0和RS note。
- [x] commit/reconcile/rebuild 只更新受影响 Owner；失败保留 pending/failed，不重复规范提交。

验收：即使现有全文 `memory_entries/memory_fts` 中存在独有词，默认发现查询也不能命中；删除并重建 discovery 投影后结果身份和 fixed refs 稳定，规范 HEAD 与历史文件字节不变。

## 2. 接入发现召回和 Owner 融合

- [x] 在 `memory/discovery.py` 增加显式 discovery 查询路径；命中返回 projection provenance，但候选身份回归规范 fixed ref 或 Owner 身份。
- [x] 在 `material_query/recall.py` 增加 discovery adapter，逐项核验范围、权限、排除、HEAD、源修订/指纹和向量水位。
- [x] 在 `material_query/query_plan.py` 增加信号族内变体归一和 Owner 级 RRF；先保留 fixed-ref 去重，再折叠 Owner，禁止历史 revision 误合并。
- [x] Owner candidate 保存最佳族排名、全部独特命中、查询来源和稳定 tie-break；分页游标冻结查询计划和投影版本。
- [x] 保留旧手动 material-query、legacy RS 和现有全文模式的明确兼容入口；不能让新 projection 暗中改变冻结评估 profile。

验收：单 Owner 的大量记录不会在融合前占据多个 Owner 名额；identity、lexical、dense 各自贡献仍可解释，查询变体不产生额外独立投票。

## 3. 生成覆盖互补筛选包并修复 CE 边界

- [x] 新建 `material_query/owner_screening.py`，将 relevance、route gain、record/location gain、受保护条件和重复度分开计算。
- [x] 第一版固定每 Owner 至少一个核心窗口、通常2–3个、硬上限4个；这些值进入同一设置契约，新 RS 冻结，旧 RS 不被改写。
- [x] CE 在单个发现窗口上运行；长输入由确定性 hit-centered window builder 截取，保留实际命中、标题和关键条件。
- [x] auto 仅对失败窗口保留原排序，不能因一个超长/缺上下文条目回退整窗；required 的失败、费用和账本语义继续显式。
- [x] CE 只排序，不删除 Owner；在给同一 Owner 第二个窗口前先覆盖其他 Owner 的首个窗口。
- [x] reading 响应只给 AI Owner 标识、筛选正文、fixed refs、命中原因和 coverage/gap；内部排名诊断不进入正文。

验收：合成 D 的超长 block 不进入发现索引，L1检索说明可以发现 Owner；人为构造的一个超长 L2 窗口只局部处理，不改变其他 Owner 的 CE 结果。

## 4. AI 判断、逐 Owner 全文阅读和用户补偿动作

- [x] `reading-recall` 默认只执行 discovery；按批返回 Owner screening packets。
- [x] 为 Owner 保存 `relevant|uncertain|irrelevant` 判断、理由和本轮实际包版本；状态更新使用会话 CAS。
- [x] standard/associative 对 relevant Owner 调用现有全文读取，但改为枚举全部可读当前内容并稳定分页，直至 `has_more=false`；精确正文去重，不用“报告已包含”推断省略其他记录。
- [x] quick 保持片段语义，不自动升级为全文阅读。
- [x] 新增独立的 `reading-recall-fulltext` 动作。默认响应仅返回 `fulltext_compensation_available`、原因和将扩大到的来源范围；UI 必须由用户点击，Skill 必须询问并等待真实选择。
- [x] 补偿动作复用原 session、scope ceiling、排除、冻结查询计划和预算，结果标明来自全文补偿；不得重建 RS 或清零额度。

验收：discovery unavailable/incomplete/no-sufficient-result 三种状态提示不同；未调用补偿动作时，通过 spy/fixture 证明 blocks/documents 全文查询没有执行。完整阅读已选 Owner 不被误标为全库补偿。

## 5. 低等级模型修复旧 Owner 并直接建索引

- [x] 提供内部 `memory discovery-gaps` 分页动作，机器只发现确定性缺口：缺 L4、L1 `retrieval_description` 缺失/为空、投影未就绪，以及固定来源、权限或 HEAD 缺失/变化。不得用长度、关键词或规则模板判断非空说明是否语义完整；该动作只驱动修复，不新增面向用户的审计终点。
- [x] `work-loop`/`consolidate-results` 生成受限 worker brief，按工作区低等级模型偏好逐 Owner 委派；同一 Owner 串行，多个独立 Owner 可按资源并行。
- [x] reader 固定当前 HEAD 和获准全文，先判断非空 `retrieval_description` 是否覆盖问题/用途、方法、主要发现、适用与不适用条件及限制，再形成 overview、必要的 experience 或 detail 新修订；原文主张、AI推断和本次验证分开，固定来源和关联关系使用真实 revision/SHA。
- [x] writer 只通过 `validate-draft/commit/inspect` 保存；VERSION_CONFLICT 时重读，不覆盖；来源不足时保存 gap，不生成无依据概览。
- [x] 每个 Owner 提交回读成功后立即以该次 `expected_head` 和 `projection_version` 调用 `rebuild-discovery --scope Owner-ID`，分别核对 lexical/vector 水位；HEAD 已变化则标 stale，投影失败只续接索引重试。不等待全批完成，不另外生成“待补清单”作为交付。
- [x] 失败项返回 owner_id、阶段和原因，可续接；成功项不得被整批后续失败回滚，且不能被报告成结论复核。

验收：程序测试证明 F 的结构缺口发现、逐 Owner 幂等重建、双水位失败/陈旧语义、仅重试投影和不写规范内容。实际低等级模型审核了三个现有长期 Owner，均已有 L4 与 L1 检索说明，只缺投影，因此没有制造内容修订；审核后直接完成逐 Owner 词法/向量重建。非空但语义覆盖不足的真实修订分支本轮没有自然样本，不能用合成规则输出冒充实际模型修订。旧修订、原件、review和文稿固定引用保持不变。

## 6. CLI、HTTP、工作台和设置

- [x] 契约增加 discovery readiness、projection provenance、Owner packets、coverage gaps 和显式 fulltext compensation 动作；生成 Python/TypeScript 类型。
- [x] 工作台按 Owner 卡片展示 L4及少量互补命中，同一 Owner 不平铺所有 chunk；保留层级、来源、定位、命中通道和展开入口。
- [x] 显示发现索引不可用、覆盖不完整和未找到足够结果的区别，并给出用户选择按钮；不能在加载、翻页或 AI `uncertain` 时自动点击。
- [x] 设置统一保存每 Owner 筛选包常规/硬上限、每批 Owner 数和 CE 单窗策略；旧配置内存补默认且不改原字节，写入严格完整。
- [x] 前端构建后更新预构建资源和指纹；使用端不新增 Node 要求。

## 7. 文档、升级与验证收口

- [x] 先把已决定的目标行为写入 ARCHITECTURE、CORE、记录标准、检索/AI阅读/存储说明、测试规范及相关 Skill；实施完成后已统一改为现行契约。
- [x] 新增本计划和 CORE 链接的详细设计，明确独立发现索引而非全文 level 过滤。
- [x] 代码实施后把文档中的“待实施”改成实装行为，并在 DEVELOPMENT_HISTORY 追加实际结果、失败和替代项。
- [x] 定向 Python：新 discovery/repair/screening tests，加现有 memory index、material recall、query plan、reranking、owner reading、权限/来源回归。
- [x] 前端变化执行组件、类型检查、实际浏览器、构建和资源指纹。
- [x] 因新增索引表/collection、rebuild和升级边界，执行真实 `setup.cmd` 已扩展旧工作区的预览、升级、重复升级、恢复、损坏拒绝和业务/自定义内容保护。
- [x] 运行 `testing audit`，判断哪些新用例进入 quick 基线；至少索引隔离、撤权/陈旧拒绝、未经用户选择不全文补偿、修复不改review/原件应进入固定基线。
- [x] 结构变化后执行 `refresh-index` 与 `validate`。

## 文档与 Skill 处置

| 入口 | 本轮计划文档阶段 | 实施完成后 |
|---|---|---|
| README | 标明决定的默认发现方向 | 已改为实际用户行为、入口和验证边界 |
| ARCHITECTURE | 增加目标模块、独立状态和当前差距 | 写实际文件/表/collection与故障恢复 |
| CORE | 保留当前行为，增加目标伪代码并链接详细设计 | 目标流程转为现行流程 |
| docs/README | 登记详细设计入口 | 链接实际手册/API |
| DOCUMENTATION_MAINTENANCE | 增加发现投影变更的同步检查 | 核对调用者和示例 |
| TESTING | 增加功能与拒绝边界；不启动效果评估 | 登记并执行测试 catalog |
| RESEARCH_RECORDING / MEMORY_USAGE / MEMORY_REQUESTS | 写通用压缩层级、L4、跨主体经验和三类关系 | 按实际契约调整示例 |
| AI_READING / RETRIEVAL / MEMORY_STORAGE_EXPLAINED | 区分当前全文路径和目标发现路径 | 补准确动作、状态和存储实体 |
| work-loop / context-maintenance / consolidate-results / material-query | 写记录形成、修复、默认发现和用户补偿判断 | 用实际命令替换计划占位 |

## 实施结果与保留边界

本轮已创建独立 discovery 表、FTS、向量 collection 和 Owner 双水位，实现 Owner 级路线融合、覆盖互补筛选包、CE 单窗口截取/局部失败、AI 三态判断、相关 Owner 全文分页、quick 片段边界及用户显式全文补偿。CLI、HTTP、生成契约、工作台设置和预构建资源已同步；旧 legacy 会话保留原全文路径。

三个现有长期 Owner 的确定性缺口只有 `DISCOVERY_INDEX_NOT_READY`，因此没有修改其规范正文；词法/向量发现投影已逐 Owner 重建。定向 Python、前端组件/类型/构建、真实浏览器、HTTP/socket、真实 `setup.cmd` 扩展旧工作区及测试 catalog 审计均有通过证据，完整结果见本次 [Run](../runs/run-20260917t181639z-af7701fd84ad/RESULTS.md)。

本轮按用户约定不测 Owner 召回率、延迟、候选数量、CE 成本、上下文占用或错误联想率，因此只能确认行为、状态、安全和升级边界，不能宣称检索效果或性能已经改善。非空 L1 检索说明语义不足的真实旧 Owner 修订分支也没有自然样本，后续遇到时按已落地 Skill 流程实际阅读、MEM CAS 提交、回读并重建。
