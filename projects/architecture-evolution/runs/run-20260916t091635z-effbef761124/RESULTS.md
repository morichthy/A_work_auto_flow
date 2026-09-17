# 浮点阅读候选限流：独立失败对照

2026-09-16，Windows x64。Run：RUN-20260916T091635Z-EFFBEF761124；RS-0c4b1942-a4ec-4a32-8cae-4014e6d4a68f。保留上一默认实验，以相同问题、来源、三条中英文查询计划、80,000字符/16 MiB/300秒预算建立明确独立实验。

只将每层result_limit与Cross-encoder候选窗改为2/2，auto不变。新gpt-5.6-terra/low/fork none reader；查询计划已由首轮准备并通过保护项检查，因此端到端差异不能全部归因于候选限流。

| 动作 | 程序dispatch秒 | 结果 |
| --- | ---: | --- |
| reading-template | 0.009239 | ok |
| reading-start | 1.328903 | ok |
| reading-delegate | 1.302966 | ok |
| reading-view | 1.280830 | ok |
| reading-recall | 67.427888 | BUDGET，未交付候选 |

最终累计output_chars=79,954、read_bytes=6,235,277、候选计量36、model_calls=11、rerank_items=4。未到达完整阅读、note、decide或handoff；不是一个较快成功样本。没有重试清零或抬高本RS预算。仅调小候选窗不足以让这个真实案例在原预算内闭环。

原始请求/回执、outer时序、timeline与summary均在.run-captures/latency。完整后续诊断和优化建议见RUN-20260916T092432Z-6976E1302DE8/RESULTS.md。此Run保持failed，保留真实失败。
