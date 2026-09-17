# AI 经验检索与上下文组织方案研究

研究 ID：`RES-AI-EXPERIENCE-CONTEXT`。状态：进行中；敏感等级：internal。最新整理：2026-09-13。

目标是比较如何发现和阅读历史经验、保留局部技术细节，并维持同问题的有效上下文。用户原 A/B/C/D 方案作为基线，比较已加入有界全文、技术块、多层独立召回、查询反馈与关系/全局综合。基础召回与用户选定的多路阅读工作流已实施；实际任务质量、规模成本与可推广性继续研究。

- [完整研究过程 v0.3](RESEARCH_PROCESS_v0.3.md)、[精简报告 v0.3](RESEARCH_REPORT_v0.3.md)：新增用户阅读策略与程序实施，保留此前阶段；[固定保存回执](RECORDS_v0.3.md)。
- [阅读工作流实施与验证](../../projects/architecture-evolution/runs/run-20260912t195347z-39ffe0ee7711/RESULTS.md)、[实际浮点阅读笔记](../../projects/architecture-evolution/runs/run-20260912t195347z-39ffe0ee7711/READING_NOTE.md)：56项不重复行为与18项升级测试通过，并完成实际AI读写及跨进程恢复；不代表普遍解决质量已验证。

- [完整研究过程 v0.2](RESEARCH_PROCESS_v0.2.md)：原机制比较、跨层效率及基础实施验证；由规范文稿固定回读导出。
- [精简报告 v0.2](RESEARCH_REPORT_v0.2.md)：当前能力、验证限制和未决策略；[保存回执](RECORDS_v0.2.md)。原[完整过程 v0.1](RESEARCH_PROCESS_v0.1.md)与[精简报告 v0.1](RESEARCH_REPORT_v0.1.md)保留当时事实。
- [研究计划](PLAN.md)、[证据台账](EVIDENCE_LEDGER.md)、[结论状态](SYNTHESIS.md)。
- [后续讨论](DISCUSSIONS.md)：跨层召回效率，以及已核对并修复的 L1 正文索引覆盖问题。
- [跨材料潜在联系调研笔记（2026-09-17）](work-context-latent-links-20260917.md)：文献发现、机制陈述、图检索与实验关联的来源导航及候选建议；未实施，未做本地效果验证，非规范成果整体更新。
- [基础专项实施与验证](../../projects/architecture-evolution/runs/run-20260912t021858z-b6e2da1386d3/RESULTS.md)：81项最终定向、18项真实升级通过；小样本语义测量、失败和适用边界均保留。
- [本轮分析 Run](runs/run-20260911t220732z-537995938d50/run.json)：固定来源及字节指纹；不是检索性能实验。
- [先前方案讨论](../../projects/architecture-evolution/plans/ai-experience-context-skill-design-20260911.md)：保留最初建议及修订理由。
- [所属架构项目](../../projects/architecture-evolution/README.md)。

规范内容通过 memory 公共入口保存：L0 登记材料、L1 技术单元、L2 研究经过、L3 暂定建议、L4 概览，另有独立完整/精简文稿。导出文件方便阅读，后续修改先修订规范记录和文稿再重新导出。保存、索引、AI 自查和用户认可分别记录。

后续继续阅读本页、PLAN、证据台账及公共 memory resume 检查点。正文独有词漏检已复现并修复，阅读记录跨进程恢复已验证；关键未知仍是真实题集上的漏检与解决效果、大库性能及AI停止判断的质量。尚无高层方案可推广的已验证结论。
