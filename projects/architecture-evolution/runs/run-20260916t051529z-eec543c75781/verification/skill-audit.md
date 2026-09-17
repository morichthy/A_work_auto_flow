# 工作区设置跨入口 Skill 影响审查

日期：2026-09-16。审阅者：AI；范围为本次 workspace-settings 协作策略与检索默认值跨入口改动。只读完整阅读 8 份活跃方法源、8 份发现入口、安装器登记与方法、DOCUMENTATION_MAINTENANCE；按相关范围阅读 MEMORY_STORAGE_EXPLAINED 的开篇、索引/检索及当前有效性段落。没有修改产品、Skill 或规范记忆。下列处置描述是审查时状态，不把本次文字核对当产品行为验收。

## 结论

work-loop 与 material-query 已有的本轮改动与公开实现一致，其余六项没有需要同步的默认值或强制委派规则。未发现活跃 Skill/发现入口要求必须使用子 Agent。用户当前明确要求优先；subagents=off 是遵循工作区规则的 AI 工作流策略，不是宿主工具的硬禁用开关；auto 仅在任务适合且宿主提供能力时允许委派，没有能力时单 Agent 可完成同一流程。此前已授权的具体委派与本轮用户要求按实际上下文处理，不能把配置误写成工具权限提升。

## 逐项阅读与处置

| Skill | 触发与职责 | 公开接口/入口核对 | 本次处置及无需修改范围 |
|---|---|---|---|
| work-loop | 开发、分析、整理与持续工作；Owner归属、记录与续接 | 新增 workbench.cmd workspace-settings policy；原 memory list-owners/inspect/resume、reading-list/view、validate-draft/commit、run-execute/register | 已核对主线新增策略段：开始任务/用户修改设置后读一次，off不委派，auto无宿主能力回落单Agent，用户当前明确要求优先；后续无需额外修改 |
| material-query | 查找并完整阅读固定材料，保存阅读理解 | reading-template/start/recall/page/read/note/decide/list/view/bind/archive；公开模板实现读取 workspace_settings.read(root).settings.reading | 已核对主线修改：新模板由程序应用数量/预算/重排默认（出厂auto），AI不重复打开JSON；显式请求优先，旧RS保留原值且不能重建清零；无需额外修改 |
| context-maintenance | 批量接入已有获准材料、稳定身份与来源归组 | memory list-owners/inspect/adopt-owner/ingest-preview/ingest-apply；refresh-index/validate | 无自有检索默认或委派条款，普通记录沿work-loop；无需修改 |
| evidence-inspection | 查看依据/复核/下游、只读监测和维护候选 | memory inspect/raw-materials/raw-material/document/outline/section-context/document-impact/search/context/review/impact等；relations export/import-candidate；evidence-monitor | 复核及只读权限边界不受设置改变；未强制委派；旧memory入口参数保持现状，不能把新默认误套旧search；无需修改 |
| development-checks | 开发、修复、跨入口变更与按影响验证 | 文档/调用者/Skill检查，真实setup升级边界；refresh-index/validate | 已要求跨入口逐项Skill检查与缓存/升级验证，本次照现有规则记录即可；无需修改 |
| association-exploration | 对用户选定材料做结构关联、比较差异和迁移边界 | 材料查询取得固定包；memory associations-propose/associations-decide | 沿原材料包范围和累计预算，不创造额外默认或子Agent依赖；无需修改 |
| semantic-maintenance | 实际审查变化后的下游内容，形成并提交维护方案 | material-query maintenance-plan/review/apply；必要时memory公开预检/提交 | 协作开关不改变AI审查、CAS、request_id与权限要求；未强制委派；无需修改 |
| consolidate-results | 重要成果、阶段交接与实质变化后的全文/上下文同步 | memory inspect/outline/document/section-context/document-impact/validate-draft/commit/reconcile | 全文阅读和固定范围审查仍由执行AI负责，单Agent亦适用；无强制并行或子Agent，设置不豁免记录/复核；无需修改 |

## 注册、发现与公开动作

- install_workspace_skills.py 的 NAMES 正好为上述 8 项；COMPAT_NAMES=()；RETIRED_NAMES=(research-loop, workspace-context)。当前 automation/workflows 和 .agents/skills 均为这8项，没有额外兼容入口待审。
- .agents/skills 的8份SKILL.md完整读取，均为轻量发现入口，链接到各自方法源；name/description及用户明确要求优先说明与安装器generated一致，未复制另一套设置规则。
- 已实际运行安装器默认只读preview，退出0并逐项列出8入口；没有使用 --apply，没有覆盖自定义规则或安装全局Skill。原日志见 skill-install-preview.log。
- 已实际调用 workbench.cmd workspace-settings policy，返回 subagents=auto、fallback=single-agent、host_capability_required=true；未改变配置。原日志见 skill-policy-read.log。
- 源码核对 reading.py 的template分支明确从settings.reading读取预算、result_limit和reranking；start/resume使用请求/RS固定预算。精简policy由workspace_settings_cli公开读取同一权威设置，未另存协作状态。
- 发现/注册预览验证不能证明宿主强制执行off，也不能替代CLI/HTTP/UI与升级回归。

## 两份手册处置建议

1. docs/DOCUMENTATION_MAINTENANCE.md：已完整阅读，现有“逐项Skill闭环”“按影响维护”“MEMORY_STORAGE_EXPLAINED主动核对”条款已覆盖本次。建议记为已核对无需修改，不把设置字段或参数复制进维护规则。
2. docs/MEMORY_STORAGE_EXPLAINED.md：索引三表、固定版本与有效性、排名不代表可信度等相关解释仍成立，无需改写。开篇第3行“新模板auto”现已过于绝对：应改为“新模板遵循工作区设置，出厂auto；旧RS保留原预算/策略，无重排字段仍off”，并链接WORKSPACE_SETTINGS。可补一句设置是请求默认值、不是规范记录/索引/授权来源；无需复制预算表。更新核对日期/范围即可。

本报告仅作本轮审查记录，不晋升科学结论，不修改历史说明或用户规则。
