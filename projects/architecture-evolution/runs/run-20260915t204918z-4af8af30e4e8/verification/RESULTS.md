# consolidate-results 隔离实际调用与 AI 阅读检查

检查时间：2026-09-16（Asia/Shanghai）。审阅者：Codex 子代理 AI 自查，非用户认可。场景只使用合成温标材料；没有现实实验或科学有效性验收。

## 复现

在仓库根运行，seed 每次创建独立新目录，不覆盖原合成 Owner。先完成 seed 输出全文的人工/AI 阅读，再执行 consolidate。

```powershell
.\automation\python.ps1 .local/consolidate-results-check/check.py seed
.\automation\python.ps1 .local/consolidate-results-check/check.py consolidate
.\automation\python.ps1 .local/consolidate-results-check/reconcile.py
```

这是公开 MemoryService.validate_draft/commit/inspect 和 memory.api.dispatch(document/outline/document-impact/reconcile) 的实际调用，不是 CLI 端到端，也不是仅跑单测。复用 test_memory_documents_v3 的纯合成 payload helper。请求、预检、回执保留在 requests.jsonl；完整响应与固定身份在 state.json 和 before/after JSON。

## 变化与 AI 实际阅读

AI 已完整阅读旧概览、旧文稿的全部单章正文、当前 Owner 全部 5 条记录 payload、outline、impact，以及新概览和新文稿全部正文。文稿从旧定义“仅 T 单位 K”增加 t 单位 °C、t >= -273.15 °C 的适用域，再纳入 -300 °C 对应 -26.85 K 的拒绝输入反例。公式 T=t+273.15 保留。方法章节连接文字说明反例用途；概览将未决问题从输入边界改为现实传感器误差待验证，两者一致。fixture 的 ONLY_FULL_RESULT/OPTIONAL_BLOCK 是保留的可读性哨兵，不视为科学结果或正式交付文稿措辞。

|对象|版本处置|理由|
|---|---|---|
|MEM-7d6d7b76-0f30-5051-8f60-aea367a31e54|1→2|补齐单位与适用边界|
|MEM-bc46ff77-9cd1-5312-aa45-7e94598203ab|新增1，沿用1|此前未编排的独立反例|
|MEM-16d2cb05-6a19-5b24-b82e-60a97fcc1b96|1→2|固定新版定义并纳入反例；更新连接文字|
|MEM-88937726-da61-5152-ba68-7f076fcb860d|1→2|独立维护 overview technical_refs、限制和下一步|
|MEM-b1974ffc-172d-5f9a-87f5-019587f49511|1→2|固定新版章节|

重要观察：文稿没有 new_unit watch_refs 时，before-impact 的 uncovered_unit_ids 为空，仍确有新增未纳入反例。因此实际按 Skill 补查了全部当前 Owner 清单，从清单和 outline.watch_baseline 发现它；不能把空影响列表当作全部覆盖证明。

## 固定结果与检查

- 起始文稿基线 HEAD：COM-22e85f1a-398b-440a-b7d4-92d75faab331；新材料生成后 HEAD：COM-9d5b3972-bae8-4681-8700-13e1dd64f9e9。
- 最终 HEAD：COM-c0a2a7d0-b753-4e08-b53a-d795bff84389，generation=9。
- 最终 document：MEM-b1974ffc-172d-5f9a-87f5-019587f49511 revision=2，record_hash=e92860797e51c9821180bf9d9e379839000e086072d051e1730e77fd51343aa1。
- document_source=independent；report.complete=true；report_coverage 含两个技术单元且 uncovered_detail_ids=[]；report_version_hints=[]；missing=[]；最终 document-impact changes=[]，scientific_review=not_evaluated。
- 重新读取旧文稿 revision=1 的所有章节，与更新前完全一致；旧技术单元 revision=1 对象完全一致。旧固定版本没有跟随 HEAD 改写。
- 对未变化技术单元 revision=2 再提交完整相同内容，validate-draft 和 commit 返回 no_change；revision、HEAD 均不增加。
- 全部实际预检与提交成功；公开 reconcile 已执行，FTS indexed generation=9，但 vector pending（CAPABILITY_UNAVAILABLE：隔离环境未配置本地向量后端）。未安装模型、未 mock 后端、未修改配置以掩盖状态。

## 状态与限制

正文同步、固定版本保护、未变化不升版以及 AI 一致性自查已完成。**中间记录已保存，完整成果待同步：向量索引补偿未完成。** 按 Skill 的完整收口条件，不标“本阶段完整成果已同步”。后续若需要验证该条件，应在获准且配置真实向量后端的隔离环境 reconcile 后再检查；当前结果已充分验证正文流程并实际触发保守收口分支。

仅一 Owner、一章、两技术单元、小型合成场景；未验证多文稿冲突、大文稿分批、并发冲突、实际研究质量、CLI 启动路径、第二物理机。未使用或改动真实业务 memory、原始研究、框架代码。

## 规则修订后的只读复核（2026-09-16）

保留上节初次判定及原始观察。主代理根据本次任务边界修订 Skill 收口条件：正文一致性与索引就绪分别报告，未要求的可选向量不阻断文稿同步声明；明确要求的可检索通道仍须完成。此次隔离正文同步验证未要求向量检索，因此以下新判定替代上节仅由向量 pending 导致的“完整成果待同步”判定；没有改写任何索引事实。

执行 `automation/python.ps1 .local/consolidate-results-check/readonly_recheck.py`，仅通过公开 inspect/document 回读，没有重跑合成提交或修改配置。结果保存在 final-readonly-recheck.json：当前 HEAD 仍为 COM-c0a2a7d0-b753-4e08-b53a-d795bff84389；文稿仍为 MEM-b1974ffc-172d-5f9a-87f5-019587f49511 revision 2，record_hash=e92860797e51c9821180bf9d9e379839000e086072d051e1730e77fd51343aa1；新组装完整 report 与此前 AI 已全文阅读的固定 report 完全相同。complete=true，两个技术单元覆盖完整，版本提示为空，未发生并发版本变化。

**本阶段完整成果已同步（范围：单 Owner、单章、两技术单元的隔离合成正文与概览；文稿版本：MEM-b1974ffc-172d-5f9a-87f5-019587f49511 revision 2；AI 一致性自查）。**

索引独立状态：FTS generation 9 已就绪；向量仍 pending/CAPABILITY_UNAVAILABLE，本次未要求该通道，未宣称向量通过。此结论仍不代表现实实验、科学复核、CLI 全链路或第二物理机验收。
