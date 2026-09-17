# Reader默认提取、自查与引用检查

用户明确要求固化三步：reader阅读时提取相关公式/实验/图/出处对应；写完在同一任务自查补齐；程序检查可确定的引用。明确不加入主Agent固定复检，以免增加上下文和时间。

## 实施范围

- [x] Skill/接口说明明确reader责任和无固定主Agent复检。
- [x] worker_brief直接传递上述要求，不只列note字段。
- [x] reading-note本地检查正文引用是否完整登记、合法固定，不要求收集全部已读来源；不新增模型/搜索调用或状态。
- [x] 红测与定向回归、实际reader合成场景、catalog登记/audit。
- [x] 保存本次固定变更/验证摘要与限制，refresh-index/validate。

语义完整性仍属于reader的AI行为，不能由字段或字符串检查保证。存量note/handoff不回溯追加质量审核。旧版来源授权/陈旧校验仍保留；不改前端、默认预算、安装扫描、依赖或模型，按影响无需重跑构建/真实setup或全回归。相关说明维护material-query、AI_READING、CORE、ARCHITECTURE、TESTING；README/文档索引/文档职责无新入口变化，检查后无需改动。

既有固定Run RUN-20260916T181657Z-4D7EFFF321BA和文稿r7保留原时点，不将后续修正写回历史证据。

本次Run：[RUN-20260916T195725Z-16CDCD28570D](../runs/run-20260916t195725z-16cdcd28570d/run.json)。实际AI合成场景使用生成的worker_brief、线性温度校准完整文稿与固定测试引用，检查首次最终note；这是开发验收，不向产品主Agent新增审核阶段。

## 完成与边界

已完成：Owner23、委派10通过；4个新增用例登记，audit通过。合成reader首个最终note无需跟进补写，引用检查通过。来源漏登拒绝只保留既有consumed/storage_digest工程审计，note/修订/副本不变。详见[结果](../runs/run-20260916t195725z-16cdcd28570d/RESULTS.md)。本轮局部增量不重写此前冻结Run和文稿r7，未宣称全项目成果同步、语义保证或整体提速。

## 后续：叙事深度与存储职责（2026-09-17）

用户要求简化完整文稿的可读性与细节，保留相关问题如何发展/研究。已核查现有字段与渲染支持多段Markdown，局部强化reader写作要求，不改schema/存储/默认预算。现行.local JSON维护会话状态，context/current.md为可读投影；这不是AI强制，可用单MD另行设计，但本轮未请求实施迁移。不新增主Agent固定复检。

Run：[RUN-20260916T201935Z-6C6692A35C2A](../runs/run-20260916t201935z-6c6692a35c2a/run.json)。10项委派与7项Owner相关测试通过；实际固定浮点全文的叙述样例已生成，见[Markdown](../runs/run-20260916t201935z-6c6692a35c2a/NARRATIVE_NOTE.md)，估算8538；未改旧RS/冻结Run。实时新RS召回完整性失败，已留证并归档，不宣称端到端通过。并行strategy/quick开发内容保留，仅改本轮四条派工要求与相关段落。
