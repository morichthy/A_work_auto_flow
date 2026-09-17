# 浮点阅读默认配置：真实预算失败基线

2026-09-16，Windows x64。Run：RUN-20260916T085438Z-3E40D5ED8471；RS-427b0ea5-0b73-4ba7-9417-bede5b623fc5。仅查询既有 RES-FLOATING-POINT-SUMMATION，绑定架构演进项目；本轮不修改产品、全局设置或浮点材料。

使用默认每层 result_limit=10、Cross-encoder auto/candidate_limit=30、80,000累计输出字符、16 MiB读取、300秒程序活动时间。独立gpt-5.6-terra/low/fork none实际执行中文原问句和两条英文等义变体。问题为顺序求和、Kahan与math.fsum在强抵消输入上的差异和失效边界。

| 动作 | 程序dispatch秒 | 结果 |
| --- | ---: | --- |
| reading-template | 0.010125 | ok |
| reading-start | 1.295108 | ok |
| reading-delegate | 1.330944 | ok，宿主随后实际派工 |
| reading-view | 1.383717 | ok |
| reading-recall首次 | 1.425139 | VALIDATION：英文变体未原样保留中文保护项 |
| reading-recall修正后 | 79.706278 | BUDGET，未交付候选 |

最终累计output_chars=79,972、read_bytes=7,023,917、候选计量60、模型调用计量11、rerank_items=7。候选计量不是去重材料数，模型计量不含宿主AI。完整读取、note、decide、handoff和主上下文接受均未到达，时间应记为未测到而非0。第二次recall外层执行/poll包络100.293秒，不等于79.706秒程序时间。

配置读取0.457毫秒；来源Owner元数据发现0.892秒。六次dispatch合计85.151秒。root派工至reader结束标记约405.702秒，其中有一次路径错误、一次本地写入PermissionError（授权执行后成功，无自动审批拒绝）、保护项修正及111.076秒无工具记录的宿主/模型混合间隔，不能称为纯模型推理。

准备仪表最初未将绑定Project纳入scope ceiling，reading-start被DENIED；未创建RS，原失败保存于verification/latency-attempt-01与scripts/latency_driver_v1.py，不混入正式基线。reader最初外层日志意外带首字符+，原文保留为reader-outer-events.invalid.txt，合法派生JSON仅去掉该字符，时间不变。

逐次程序事件、完整请求/回执和外层时序见.run-captures/latency；timeline.csv含所有记录边界。独立后续限流与最小诊断未重置这个RS；完整分析见相邻RUN-20260916T092432Z-6976E1302DE8的RESULTS.md。此Run保持failed，不以“测到了失败”冒充阅读成功。
