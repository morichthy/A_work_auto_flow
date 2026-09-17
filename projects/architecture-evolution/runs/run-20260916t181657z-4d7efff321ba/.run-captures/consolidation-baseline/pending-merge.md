# 待冻结后合并的成果草稿（不提交）

基线：Owner `COM-d6b78fdc-f63e-4517-96e5-9f73dbe3a888`；reader L1 r3、section r4、overview r5、document r5。本文仅准备后续更新现有记录的结构，不构成 Run 结论、引用或 memory 提交。

## L1：拟追加 `owner-document-reading-results` 块

本轮把 AI reading 的候选单位收敛到正文与所属 `owner_id`，按固定身份在跨路线候选内去重。reader 选定 Owner 后逐篇读取其完整现有文稿；渐进式读取每个 Owner、每页只交付一个正文段，读完后跳过仍处于 pending 的段。图片、L0 和 Run 默认只保留固定引用，按需展开。最终 handoff 仍交付一份研究式 reading note，主 Agent 不接收逐轮候选或完整诊断包。

工作区设置提供 `reading.context.max_owners` 和 `note_max_tokens`：前者限制可完整阅读的 Owner 数，后者限制最终 note 的估算 token。新 Owner-document 模式以每个 operation 的 engineering Ledger 保护资源，内部搜索和诊断不占 AI 输出预算；既有 legacy 会话的累计 Ledger 语义保持不变。两项不替换 RS 授权、固定来源、超时及运行资源保护。旧 RS 与手动查询保持其原有语义，已有会话不因新默认策略被改写。估算和遗漏必须可见；宿主并不因此获得自动压缩上下文、模型可用性或额外材料权限。

Run 尚待冻结，以下只作待核对的事实草稿，不能成为结论或引用：后端 84 个不同用例、Owner 19、设置 18、组件 11、浏览器 2、扩展旧工作区 setup 19 均有通过记录。实际终态以首批 1 Owner / 320 字 note 运行：`result_limit=10`、`rerank_candidate_limit=30` 未降低，耗时 88.743 秒；Cross-encoder 对长正文仍发生窗口回退。正常完整 `research_process` 已读，note 补入公式、Run 与图引用。冻结后必须以真实回执核对计数、状态、固定来源和适用边界；不写性能改善、业务阅读质量、总费用或端到端延迟结论。

## Section / overview / document 拟处理

- 现有 `子Agent阅读与主Agent交接` 章节保留全部历史块；仅追加本轮 L1 固定引用及一段范围说明。
- overview 保留旧预算诊断、失败与未优化边界；增补 owner-document 模式和双预算语义，但不得把“candidate 内部去重”写为全阅读流程或全库重复消除。
- document 沿用两个现有 section refs：`MEM-50f66b7c-7953-5715-8b70-5ae7705176ab` 与 `MEM-a042188a-244a-5d15-843e-359b7d7f87f6`；后者与阅读笔记工作台入口无本轮实质关系，必须保留且不修改。

## 已知历史影响与本轮范围排除

当前 `document-impact` 报告的旧依据修订包括 `MEM-afa98edf…`、`MEM-472e4d18…`、`MEM-7df3c088…` 及 reader L1 自身历史 r1/r2→r3。它们已由 r5 文稿作为既有演进的一部分保留；本轮不因新 Owner 文稿阅读功能而重审或替换这些历史固定引用。

不扩展至 Owner 的其余 17 条未覆盖 L1、全库检索质量、历史浮点材料科学结论、性能优化、第二物理机验收或发布。
