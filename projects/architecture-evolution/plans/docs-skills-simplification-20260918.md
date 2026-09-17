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
- [ ] 与用户确认逐篇顺序。
- [ ] 逐篇修改、回读和验证。
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

## 交互方式

每轮只处理一篇或一个紧密耦合的小组：

1. 给出该文档当前职责和与其他文件的关系。
2. 列出具体矛盾、重复、过时内容和阅读负担。
3. 给出建议结构、拟删除/迁移内容及不可删边界。
4. 用户确认取舍后修改。
5. 回读并运行与影响相称的链接、Skill 或工作区验证。

## 下一步

完成全局只读审查，提出第一篇建议处理的文档及原因。优先选择会影响其他文档判断的权威入口，而不是先做表面语言润色。
