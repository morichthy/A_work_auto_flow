# 关键文档与 Skill 一致性精简

更新：2026-09-18

## 目标

完整审查当前关键文档与活跃 Skill，识别前后不一致、职责重叠、过时状态、逻辑顺序问题和不必要的语言负担。与用户逐篇确认后再修改；不做未经讨论的批量改写。

## 范围

第一层为开发检查规定的六份现行文档：

- `README.md`
- `ARCHITECTURE.md`
- `docs/CORE.md`
- `docs/README.md`
- `docs/DOCUMENTATION_MAINTENANCE.md`
- `docs/TESTING.md`

第二层为影响现行工作入口的文档与全部活跃工作流 Skill：

- `AGENTS.md`、`context/START_HERE.md`、`context/NOW.md`、`context/MEMORY.md`
- `docs/DEVELOPMENT_HISTORY.md`、`docs/WORKFLOW_ACTIONS.md`
- `automation/workflows/README.md`
- `automation/workflows/` 下八个活跃 `SKILL.md` 及 `.agents/skills/` 发现入口

历史 Run、旧设计和固定版本只用于确认演进原因，不改写其历史时点。

## 审查准则

1. 每项现行事实或规则有一个权威来源；其他入口只摘要并链接。
2. 区分现行规范、当前状态、操作手册、历史依据和任务计划。
3. 保留权限、数据边界、失败模式、兼容性与验证要求，不用“精简”删除安全约束。
4. 先修矛盾和职责，再处理段落顺序，最后精简句子。
5. 每篇修改前向用户给出问题、拟删改内容和关键取舍；确认后实施并验证相关链接与调用者。

## 当前进度

- [x] 读取根规则、项目规则、`context/START_HERE.md`、`context/NOW.md`。
- [x] 读取 `work-loop` 与 `development-checks` 的发现入口和完整方法源。
- [x] 读取工作区协作策略；当前允许对子任务使用较低成本、低推理深度的 reader。
- [x] 完整阅读六份现行文档并建立职责/重复矩阵。
- [x] 完整阅读八个活跃 Skill 并建立触发条件/输入输出/副作用矩阵。
- [x] 核对入口文档、当前状态、项目 README 和开发历史。
- [x] 与用户确认逐篇顺序。
- [ ] 逐篇修改、回读和验证：`ARCHITECTURE.md` 已完成首轮精简并独立复核；下一篇为 `context/NOW.md`。
- [ ] 完成整体一致性复查并整理成果。

## 已发现的问题候选

- `context/NOW.md` 将 2026-09-18 Owner 发现索引记为已实施并验证；`projects/architecture-evolution/README.md` 的首条状态仍写产品代码尚未实现。需以实际代码和固定 Run 核实，并统一现行入口。
- `context/NOW.md` 已接近变更日志规模，可能同时承担当前状态、历史摘要和发布记录三种职责；需判断哪些内容下沉到项目时间线或开发历史。
- 根 `AGENTS.md` 同时包含工作区通用规则、框架开发约束和详细发行规范，可能与专项手册重复；必须先划清不可删的强制规则与可链接的操作细节。
- `ARCHITECTURE.md` 的“数据流与当前限制”存在两组完全重复段落：Owner 文稿模式/预算说明重复一次，APP 页面状态/EVD 监测说明重复一次。
- `ARCHITECTURE.md` 开头称旧 Owner 修复、升级恢复和端到端验证“仍在收口”，后文、`CORE.md`、`DEVELOPMENT_HISTORY.md` 与固定 Run 均称相关链路已验证；应明确真正未完成的是效果/性能评估，而不是已完成的软件与升级验证。
- `context/NOW.md` 页首更新时间为 2026-09-16，但正文已包含 2026-09-18 状态；正文大量逐日完成记录削弱了“当前状态”用途。
- `docs/TESTING.md` 前半定义测试强度和基线政策，后半持续累积各近期功能的详细测试设计；稳定政策与专项测试矩阵应分开。
- `docs/README.md` 同时承担快速导航和历史文件逐项分类，首屏路由不够直接；历史清单应压为单一入口。
- `work-loop`、`material-query`、`association-exploration` 对“受限关联召回”和“跨材料结构分析”的分界重复且不够统一。
- `semantic-maintenance` 与 `consolidate-results` 互相引用，需明确一次语义处置后只同步结果，不能再次递归发起语义维护。
- `evidence-inspection` 标题/描述强调只读，但实际允许复核状态、关联候选和监测状态写入；应显式区分只读主路径和已授权受控写入。
- `.agents/skills/material-query` 的 description 比方法源更宽，缺少“已知源码、配置、状态直接读取不触发”的排除条件。

## 建议的现行职责

| 内容 | 权威入口 |
|---|---|
| 用户用途、常用任务入口 | `README.md` |
| 模块、依赖、状态权威、现行架构限制 | `ARCHITECTURE.md` |
| 功能块、主流程、用户可观察边界 | `docs/CORE.md` |
| 文档导航 | `docs/README.md` |
| 文档职责、维护闭环、冻结历史政策 | `docs/DOCUMENTATION_MAINTENANCE.md` |
| 测试强度、基线准入/退出、结果分类 | `docs/TESTING.md` |
| 设计选择、替代关系和失败教训 | `docs/DEVELOPMENT_HISTORY.md` |
| 当前优先事项、阻塞、发布状态和稳定限制 | `context/NOW.md` |
| 工作入口决策树 | `context/START_HERE.md` |
| 保存、复核、纠错和保留政策 | `context/MEMORY.md` |
| 公共命令、身份、CAS/回执 | `docs/WORKFLOW_ACTIONS.md` |
| L0–L4 与文稿的语义定义 | `docs/RESEARCH_RECORDING.md` |

## 建议的逐篇顺序

1. `ARCHITECTURE.md`：先修明确重复和状态矛盾，并固定架构权威边界。
2. `context/NOW.md`：恢复为可扫描的当前状态页，移除逐日流水。
3. `docs/DOCUMENTATION_MAINTENANCE.md`：统一“六份基础现行文档 + 条件必读决策历史”的术语和职责表。
4. `docs/TESTING.md`：保留稳定测试政策，把专项断言移回 catalog、功能手册或计划/Run。
5. `docs/README.md`：按新职责压缩为任务入口、领域导航、历史入口三层。
6. `README.md` 与 `docs/CORE.md`：减少 AI 阅读、设置、成果整理和开发治理的重复。
7. `docs/DEVELOPMENT_HISTORY.md`：把近期条目压成“问题—选择与代价—状态—证据”，解决重复 D25 标识。
8. `work-loop`、`material-query`、`association-exploration`：统一触发与分工。
9. `semantic-maintenance`、`consolidate-results`：明确单向交接，消除表面循环。
10. `evidence-inspection` 及其他 Skill：区分读写副作用，抽取重复公共规则并同步发现入口。
11. `WORKFLOW_ACTIONS.md`、`MEMORY.md`、`START_HERE.md`：在前述权威边界稳定后收口公共操作、保存政策和入口路由。

## 逐篇处置记录

### `ARCHITECTURE.md`

- 状态：已修改并回读，等待用户确认本篇收口。
- 删除开头的日期、实施状态和验证进度，只保留本页职责及到用户入口、功能定义、文档索引和开发历史的导航。
- 删除两组完全重复段落，将日期式实施叙述改为七个稳定主题：Owner发现、阅读模式、工作台与监测、设置与协作、排序与降级、保存与兼容、安装与迁移。
- 保留稳定设计约束、模块影响表、状态权威表、显式全文补偿、旧会话兼容、权限/版本/预算、索引与规范分离、依赖未完全倒置及离线迁移边界。
- 独立复核发现并补回两项硬边界：只有检索索引/投影可重建，独立关联和历史回执不可清理；层级迁移仅允许 `event → narrative`、`map → overview` 的显式完整修订并固定引用前版。
- 验证：`workspace.ps1 validate` 通过，0错误、21个既有警告；警告来自历史固定文件链接和已有大模型文件，不由本次改动引入。

### 主要术语定义

- 状态：已建立规则并修正首批核心术语；后续每篇审查继续执行术语检查。
- `docs/AI_READING.md` 新增阅读领域术语表，正式区分 RS、`owner_document`、`legacy`、阅读策略、reading note、互补筛选包、handoff 与 snapshot。
- `context/GLOSSARY.md` 作为跨模块短定义入口，补 Owner、RS、阅读模式/策略、发现投影、固定引用、范围/依赖上限及筛选包；同时修正过时的 L2/L3/L4 和 v3 字段说明。
- `docs/DOCUMENTATION_MAINTENANCE.md` 增加四项术语验收：定义存在、首次可理解、跨文档一致、可追溯到契约；多义字段必须带领域限定。
- `ARCHITECTURE.md`、`docs/CORE.md`、`docs/README.md` 和 `material-query` Skill 的首次相关用法已链接到权威定义。
- 派生的 `context/generated/context-pack.md` 是 2026-09-13 的旧导航快照，`build-context` 本轮调用未更新其时间戳；它不作为现行定义来源，后续整理公共动作/上下文入口时单独处理其生成行为。
- 验证：刷新 workspace index；`validate` 通过，0错误、21个既有警告。

### 历史迁移规则

- 用户确认：从现行文档删去的历史修改必须按逻辑整理到开发历史，不能因精简而消失。
- `docs/DOCUMENTATION_MAINTENANCE.md` 已增加强制规则：删除实施过程、被替代方案、失败教训或验证结果前，须并入对应决策或确认固定历史已完整覆盖；已有条目只补缺口。
- `docs/DEVELOPMENT_HISTORY.md` 新增 D43，明确本轮从 `ARCHITECTURE.md` 移出的内容分别归入 D20、D25–D42、部署手册、Project 计划和固定 Run。
- 映射复核后，在 `ARCHITECTURE.md` 补回三类仍约束当前系统、不能只留在历史中的内容：成果整理三种状态独立；子Agent能力偏好的兼容读取/严格写入边界；中英查询计划冻结、保护文本及手动查询不自动翻译。

## 交互方式

每轮只处理一篇或一个紧密耦合的小组：

1. 给出该文档当前职责和与其他文件的关系。
2. 列出具体矛盾、重复、过时内容和阅读负担。
3. 给出建议结构、拟删除/迁移内容及不可删边界。
4. 用户确认取舍后修改。
5. 回读并运行与影响相称的链接、Skill 或工作区验证。

## 下一步

完成全局只读审查，提出第一篇建议处理的文档及原因。优先选择会影响其他文档判断的权威入口，而不是先做表面语言润色。
