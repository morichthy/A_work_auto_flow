# Owner 文稿阅读与 note 上下文预算

## 目标与边界

用户要求将 AI 检索候选精简为正文和所属 `owner_id`，内部完成跨路线正文去重；AI 选中 Owner 后逐篇读取完整文稿，图片及 L0/Run 只保留固定引用并按需展开。最终 reading note 是保留关键经验的简化研究报告，主 Agent 只接收该报告。预算由工作区设置统一提供，以最多阅读 Owner 数和最终 note 的估算 token 为主要控制项。

项目不能保证宿主自动压缩子 Agent 上下文；保存会话进度和笔记，通过同一 RS 续接。权限、固定来源、超时和单次运行资源保护仍有效，内部搜索/诊断不消耗 AI 输出字符额度。旧 RS 与手动材料查询保持原语义。

## 已有依据

- [上次预算诊断](../runs/run-20260916t162155z-9d1612b40f6d/RESULTS.md)：21 次内部搜索文本累计 46,872 字符，诊断 46,443，成功装入正文 6,555。主要问题为内部重复计量，并非正文天然过大。
- 当前候选按固定记录身份融合，hit 内保留每条路线命中信息；只在局部组包去重，不是全阅读流程的正文块去重。
- 普通材料查询已有 Owner 文稿聚合能力，AI reading 仍以单条记录为单位。
- Run 已有 conclusion、limitations 和 README，未保证有已写完整总结；不得由产物或日志伪造总结。

## 实施清单

- [x] 基线测试：重复路线/正文块去重、Owner 已选后抑制、逐篇文稿、引用不自动展开、note 关键字段/引用、预算独立、旧会话兼容。
- [x] 后端：新模板显式 owner_document 模式；精简候选、逐 Owner 读取和研究式笔记；固定授权与版本；可续接。
- [x] 设置：reading.context.max_owners 与 note_max_tokens，旧配置补默认，旧值保留，工作台主预算与工程保护分开。
- [x] 交接：最终 note 整条交付不截公式，估算方法和遗漏可见，Markdown/工作台兼容。
- [x] 文档/Skill：精简 AI_READING 与 material-query，核对全部入口和六份现行说明。
- [x] 验证：针对性 Python/前端/浏览器、真实 setup 扩展旧工作区、实际浮点检索阅读与 note 场景；构建指纹、refresh-index/validate。
- [x] 留存本次输入/源码/配置/结果，回读与整理相关成果，不将结构校验等同于语义正确。

## 执行与分工

本次 Run：[RUN-20260916T181657Z-4D7EFFF321BA](../runs/run-20260916t181657z-4d7efff321ba/run.json)。主 Agent 负责设计判断、集成、文档、实际场景和记录；GPT-6 低推理分别开发后端与设置；terra 低推理只读核查 Run/文稿及影响入口。当前工作区包含其他任务未提交修改，仅修改本范围并保留已有内容。

## 当前状态

后端冻结，84个不同用例有通过记录，Owner文件19项；先执行契约红测再开发，渐进分页与来源ID便利均有红/绿证据。设置18项Python、11项组件、2项浏览器、类型检查和构建通过；真实setup扩展旧工作区19项通过（212.263秒）；预构建60源码/65资源指纹匹配。测试catalog audit通过（791发现/793登记，非已执行数）。refresh-index成功、validate 0错误21既有警告。

实际最终首批1Owner/320字符，10每路和30重排未降低。完整research_process读后形成最终r8研究式note，主Agent实际handoff回读，保留公式/Run/图/限制，估算5517/6000、无遗漏。召回约88.743秒且CE超窗口回退，尚不宣称整体提速。所有失败与捕获限制见本Run RESULTS.md。已冻结登记3项输入与96项产物，逐项指纹核验；规范文稿已完成本轮范围同步。

## 文档与Skill处置

六份现行文档已完整读取并按影响维护：README、ARCHITECTURE、CORE、docs/README、TESTING更新行为与边界；DOCUMENTATION_MAINTENANCE补默认预算单一来源。AI_READING与material-query精简，work-loop同步逐Owner阅读和Run总结职责；WORKSPACE_SETTINGS、WORKFLOW_ACTIONS、MEMORY_STORAGE_EXPLAINED同步。本轮所有8项活跃Skill及空兼容清单已核对；其余6项无需改动作，发现入口不变，历史与用户自定义内容保留。最终仍须按实际实现再核对。

## 本轮明确边界

- note token采用UTF-8字节数保守代理，非宿主精确token或费用；不保证任意模型分词上界。
- Run已有conclusion/limitations，复杂解释经L1/文稿进入检索；只有原生run.json无MEM正文的Run尚不直接进入三层召回，本轮不增加全库Run扫描或自动总结。
- 当前只测本机Windows x64隔离升级，非第二台物理机验收；软件通过不等于科学复核或检索相关性整体提升。

## 最终收口

本阶段完整成果已同步（范围：Owner文稿渐进阅读与note预算；AI一致性自查）。技术单元r5、章节r6、概览r7、文稿r7，Owner HEAD COM-71d22958-3510-4d7d-8a3f-2948ed45ef92 generation56；FTS/vector均indexed。完整阅读及固定关系、历史引用保留理由、其他17条L1范围排除见[闭环记录](../runs/run-20260916t181657z-4d7efff321ba/.run-captures/memory-closure/CLOSURE.md)。文稿组装complete=true与实际阅读r8仍因CE回退partial分开表达，不作科学复核或全项目一致性声明。

已再次核验源码快照181项未变化、前端60源码/65资源指纹以及全部99项登记输入/产物；Run固定字节hash为79ad2a2939c1ec3a935b9423a0e2b79b58cc3f3295e941e7931bed251e9f8f36。任务清单、NOW与Project导航已同步。既有工作台进程需重启以加载新后端及预构建资源；未发布。
