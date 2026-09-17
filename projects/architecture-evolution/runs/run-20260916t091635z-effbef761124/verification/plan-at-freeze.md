# 浮点材料阅读全链路计时

Run：RUN-20260916T085438Z-3E40D5ED8471，归属PRJ-ARCHITECTURE-EVOLUTION。用户要求选择任意主题，逐次记录查询材料、AI交互、笔记生成、主上下文加载时间，识别可优化位置；本轮先测量分析，不改变产品行为。

## 范围与口径

主题：浮点求和中顺序求和、Kahan补偿与math.fsum在强抵消输入上的差异和失效边界。仅查询既有RES-FLOATING-POINT-SUMMATION研究的获准固定记录，不新造答案材料、不写其业务结论。新阅读RS绑定架构演进任务，单独计账。

使用出厂设置（auto、低成本/较低能力/低推理，阅读10项、重排auto/候选30、原累计预算）。由独立terra/low reader真实检索、完整阅读、生成note；主Agent只取handoff。本次脚本开发/测试、成果归档与用户沟通另列，不算检索服务本体。

每个API动作保存UTC时间、进程内单调计时、imports/Coordinator/dispatch/close/序列化及日志开销、完整输入输出及字符/字节数、已有coverage阶段耗时。宿主工具调用外层时间另记；两个API动作之间的间隔包括AI判断、文本生成、工具交互与排队，不能当作纯模型推理时间。主Agent收到handoff后记录context_received，实际阅读后记录context_accepted；模型内部prefill/KV加载时间当前不可观测。

## 清单

- [x] 选真实浮点研究与Owner；读取work-loop/material-query，确认auto及默认能力偏好。
- [x] 建立最小计时driver与固定查询协议，检查事件时间/返回体积计量；不改产品代码。
- [x] 执行prepare/policy/template/start/delegate，真正派出独立reader。
- [x] reader逐次recall/read/note/decide，每次保存输入输出与计时；失败和预算缺口保留。
- [x] 主Agenthandoff→上下文接收→阅读接受，检查笔记必要细节和来源。
- [x] 分解耗时，独立profile复验handoff；不把profile时间混入正常时序。
- [ ] 据实测给出优先优化项、收益上限、权衡和复测建议；保存固定Run与结果。

模型调度：辅助脚本由GPT-6低推理实现；静态路径检查与真实材料reader由terra低推理负责；主Agent负责范围、计时口径和分析整合。静态猜测不作为性能结论；一次查询不是p95或全库性能基准。

## 2026-09-16 测量进展

默认实验 RS-427b0ea5-0b73-4ba7-9417-bede5b623fc5：第一次等义查询因中文保护项未原样出现在英文变体被VALIDATION拒绝；修正后真实召回79.706秒，以BUDGET失败。累计output_chars=79972/80000、read_bytes=7023917、候选计量60、rerank_items=7；未交付候选，未生成note。保留原RS及全部失败，不重置预算。reader首轮有驱动路径和本地写权限试错，均保留在外层时间，不作为程序检索服务时间。

为完成用户要求的note与主上下文阶段，建立明确独立对照Run RUN-20260916T091635Z-EFFBEF761124，RS-0c4b1942-a4ec-4a32-8cae-4014e6d4a68f。仅覆盖每层result_limit=2、重排candidate_limit=2，auto模式、同一总预算、问题、授权与三条中英文查询计划保持。使用首轮已经构造并通过保护项校验的查询计划；仍采用新terra/low、fork none reader，所以端到端差异不是候选数量的严格单变量效果。两个实验分别报告，不以新RS冒充原会话续查。

第二实验67.428秒后仍BUDGET失败，output79954。第三独立Run RUN-20260916T092432Z-6976E1302DE8在服务器允许上限100k字符/32MiB、每层1/1、中文+1英文和温热reader条件下完成最小闭环；最初越过服务器额度的prepare失败保留且未创建RS。第三RS-47e7e8ce-9f60-4fd0-af4d-a7580a69cb04 r5/finish，note1、unnoted2、coveragepartial；主侧真实读完1901字符note，图未解码限制保留。

测量结论：第三有效prepare发出至上下文接受470.011秒，其中API内71.932秒。召回39.947秒，分路29.113秒/正文准备8.443秒/CE推理0.089秒；read原JSON332692字符包含327792图data_url并实际发生工具截断。handoff正常5.950秒，独立profile11.602秒中reauthorize11.561秒，重复固定来源/路径处理是明确热路径。结果见第三Run/RESULTS.md、verification/stage-timeline.csv和call-timeline.csv。产品性能优化未实施。

收口基线：reader文稿MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r2、概览MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155 r2，Owner HEAD generation41。AI已完整阅读；六条impact提示为三个历史设置对象经两路径重复到达，保留历史；17个其他历史L1不属本次。将沿用reader单元身份追加latency-results，维护同一章节/文稿/概览，不替换历史数字。固定Run登记、公开memory提交、全文回读和最终校验尚待完成，不提前宣称同步。
