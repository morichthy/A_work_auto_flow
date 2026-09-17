# 真实阅读计时收口

2026-09-16，AI一致性自查。用户要求的查询、AI交互、note和主上下文接受已实际测量；两次预算失败与独立最小闭环诊断均固定保存。性能优化尚未实施，材料语义覆盖仍partial，不把文稿组装complete解释为所有候选/图像已读。

## 保存与复核

- 三Run公开登记成功，状态依次failed、failed、succeeded（第三仅指最小流程完成）；登记artifact数32、23、52。原实验、准备错误、外层交互和独立profile均保留。
- 固定manifest逐项复验36、27、58项输入/产物哈希，484个framework ZIP文件指纹核对通过；阶段墙钟合计470.011秒通过。实际回执为.run-captures/freeze-verification.json。第一次stdin验证只启动Python REPL，未当作通过；随后用.run-captures/verify-freeze.py物理脚本实际执行通过。
- refresh-index退出0；validate退出0，0错误、21个既有警告。日志为.run-captures/closure-refresh-index.log和closure-validate.log。没有重跑或冒称产品完整测试/真实setup迁移验收。
- 主Agent实际收到并读完r5 handoff，正文1901字符；context_received至accepted为17.006秒，不能解释为模型内部prefill。该最小诊断虽配100k字符/32MiB上限，第一次handoff后实际计量仅33686字符/7394076字节，均低于原默认额度；不能把成功归因于提高预算。

## 文稿与固定身份

起始HEAD generation41/COM-0b448366-3b80-49a1-94b3-7a93b47296e8；结束generation44/COM-03105bc0-e652-405f-82b7-4273317b8ec6，manifest 3414dd5cb01beb39876c4f3611e0d86ae8a7c55aa1667899368d8852db920459。三批均经过公开预检、CAS提交和固定回读；FTS与vector均indexed至44。

| 内容 | ID / revision | record_hash |
| --- | --- | --- |
| reader技术单元 | MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b r2 | 1df804130728e6619ebfb2c63920cb51e4875769265ad7b00fac3d7add52efe9 |
| 章节 | MEM-50f66b7c-7953-5715-8b70-5ae7705176ab r3 | d526670cbb8f2e4ec5b5cc6e23db19089184addd16199f7b58873be4da037d89 |
| 概览 | MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155 r3 | 288d3061e4c5f85e91b3a4b296ba2284822fc90904f645a21210103088f6e613 |
| 完整文稿 | MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r3 | c0da626069a72099223023d62da266e4e653d1a8c0ea02a2f950e067749f8df2 |

完整阅读了当前及更新后的概览/文稿，新增latency-results保留本次数字和限制，历史reader-results与requirements-results保留原内容。旧概览“本轮未重跑”加能力偏好阶段标签，现行阶段明确测量完成/优化未实施。原约90.7%字符减少仍只适用于旧合成场景，不扩展为本次token、费用或速度收益。

最终文稿来源independent、组装complete=true，无正文source_issues。覆盖中的17个其他历史L1不属本次reader测量；impact七条是原六条设置r1→r2历史路径加reader r1→r2历史prose依据，全部按历史语境保留。两个version hints对应reader r1与设置文稿r1，有明确保留理由；新现行内容使用reader r2与设置单元r2。详见.run-captures/memory-closure/BASELINE_REVIEW.md、FINAL_REVIEW.md、固定完整回执。

**本阶段完整成果已同步（范围：真实浮点材料reader分阶段计时及优化诊断；文稿MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r3；AI一致性自查）。** 这不代表全Project历史成果同步、科学结论复核、默认配置已可用或性能优化完成。

后续优先实施AI返回体图片按需加载与预算处理/交付分账及交接预留，再做请求内闭包校验去重、搜索分路共享与确定性编排。须保留撤权、固定指纹和并发边界，并以同条件质量/延迟/上下文测试验收。
