# 发布后文档与 Skill 一致性审查

审查时间：2026-09-17  
发行源码提交：`414912a1e753668ba6f0fb43c7dbbf4a16c0557f`  
审查范围：六份核心文档、`automation/README.md`、8 个工作流方法源、8 个发现入口，以及安装器登记。此回执只记录阅读和比对结果，不修改产品行为。

## 核心文档

| 文档 | 本次处置 | 核对结果 |
|---|---|---|
| `README.md` | 已完整回读，无需修改 | 发布需完整审查六文档；8 个活跃 Skill、退休名称及 `work-loop` 替代关系正确。 |
| `ARCHITECTURE.md` | 已完整回读，无需修改 | `GUIDE` 的方法源、发现入口和六份核心文档职责边界与实际目录一致。 |
| `docs/CORE.md` | 已完整回读，无需修改 | 工作、成果整理、材料查询和语义维护的职责/实现入口与方法源一致。 |
| `docs/README.md` | 已完整回读，无需修改 | Skill 索引明确为 8 个活跃方法源，旧名已退休；导航目标存在。 |
| `docs/DOCUMENTATION_MAINTENANCE.md` | 已完整回读，无需修改 | 第 45 行规定的发布审查范围与本次检查一致；发现入口只负责发现、方法正文留在 workflow。 |
| `docs/TESTING.md` | 已完整回读，无需修改 | 发布验证、风险选择和 catalog 维护边界未与本次文档/Skill 改动发生冲突。 |

## 自动化文档与登记

| 项目 | 本次处置 | 核对结果 |
|---|---|---|
| `automation/README.md` | 已回读，已核对修正 | 当前准确列出 `work-loop`、`context-maintenance`、`evidence-inspection`、`development-checks`、`material-query`、`association-exploration`、`semantic-maintenance`、`consolidate-results` 八项；明确 `research-loop`、`workspace-context` 已退休并由 `work-loop` 承接。 |
| `automation/workflows/README.md` | 已完整回读，无需修改 | 8 项适用时机、默认发现/安装和退休替代去向与自动化 README 一致。 |
| `automation/scripts/install_workspace_skills.py` | 已回读相关登记，无需修改 | `NAMES` 正好包含上述 8 项，`COMPAT_NAMES=()`，`RETIRED_NAMES` 为两个旧名。安装器生成的入口指向同名 workflow；受控旧入口仅按指纹退休，用户自定义内容保留。 |

## 八项活跃 Skill

| Skill | 触发/真实动作 | 发现、公开动作与替代核对 |
|---|---|---|
| `work-loop` | 有产物、结论或复用价值的工作，负责归属、记录、Run 与续接。 | 发现入口存在并回链方法源；通过公共 memory/Run 动作保存；是退休 `research-loop` 与 `workspace-context` 的统一替代。 |
| `consolidate-results` | 重要成果、阶段总结/交接或实质变化后的全文与上下文收口。 | 发现入口存在并回链方法源；复用公开 memory/document 动作；不替代普通中间记录。 |
| `material-query` | 查本地材料、固定全文阅读和阅读记录。 | 发现入口存在并回链方法源；使用公开 material-query/reading 动作；不自动确认结论。 |
| `context-maintenance` | 批量接入、来源整理、身份采用和文档—代码映射。 | 发现入口存在并回链方法源；使用公开 ingest/adopt/memory 动作；日常记录转交 `work-loop`。 |
| `development-checks` | 开发、修复和接口变更的影响检查与验证。 | 发现入口存在并回链方法源；发布时要求核对所有入口；不替代产品实现。 |
| `association-exploration` | 已选材料的跨领域结构比较和待验证导航草案。 | 发现入口存在并回链方法源；使用公开 associations 动作；不替代语义维护或科学确认。 |
| `evidence-inspection` | 证据追溯、复核状态查看及只读监测。 | 发现入口存在并回链方法源；使用公开 memory/evidence 动作；不替代当前证据与范围核验。 |
| `semantic-maintenance` | 已变更材料对下游内容的实际语义审查和维护。 | 发现入口存在并回链方法源；使用公开 maintenance 动作；成果阶段收口转交 `consolidate-results`。 |

## 结论

此前阻断的 `automation/README.md` 旧入口文案已经修正。发布源码中，8 个活跃方法源、8 个发现入口、安装器登记、公开动作边界、退休名称及替代路径相互一致；没有剩余的文档或 Skill 发布阻断项。
