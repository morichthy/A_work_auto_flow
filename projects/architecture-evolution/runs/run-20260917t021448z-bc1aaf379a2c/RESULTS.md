# 阅读知识正文与证据详情修复结果

2026-09-17；归属 PRJ-ARCHITECTURE-EVOLUTION。本轮六项功能已实现，源码未发布。旧工作台进程需要重启并刷新页面加载新后端和资源。

## 改动与实际示例

1. Owner、综合、quick、legacy 的知识正文不再拼搜索问题和 reader 的 decision。材料建议标题统一为“可选的下一步建议”，任务状态/授权/交付缺口另行保留。主 Agent 制定联想问题与关键词，reader 可以只保存材料线索、留空 next_query。
2. 证据详情按 L0–L4、Run、document 展示；完整文稿沿固定章节与选定技术块展开，保留各图作用域；文稿不夹带检索投影字段。引用标题从授权后的固定记录解析，归属/章节关系不冒充科学文献。
3. 图片经登记权限、安全路径、固定 SHA256 检查后展示。真实 SRC-SUMMATION-FIGURE-R01 已返回核验图像；真实浮点 document r1 展开18,802字符、4图、34条固定关系，单次4.051秒（本机观察，非性能基准）。
4. 反复 Owner 警告根因是 TOOL-WORKSPACE-001 在 tools/registry.json 的 tools 数组内，旧代码却比对顶层 tool_id。适配已修，实际 Catalog 无该误警告；真实损坏仍不输出正文，无关索引问题不污染健康详情。
5. 首页统一最近问题选择、模式控制和证据入口；移除系统记忆的阅读记录页。记忆记录显示摘要并跳统一详情，旧阅读链接转向首页；RS 数据及公开接口保留。
6. Skill 和记录标准要求正文就近固定引用。真实“探索01”r3 三块只有记录级来源清单，无句级/块级位置，仅 figure:0 有明确图源。因此保留历史事实，不猜测来源对应。已有位置和 `[MEM-ID]` 写法可转可跳转编号。

实际旧 RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b 仍为 r9，HEAD 哈希不变：新快照7,330字符、11引用，原有重排窗口缺口保留；验证见 live-note-snapshot.log。没有覆盖旧记忆提交或前次 Run 的固定证据。

## 验证

| 范围 | 结果与证据 |
|---|---|
| 阅读相关完整组 | 93项通过，588.351秒；reading-regression.log |
| 最近笔记/证据旧回归 | 10项通过，80.757秒；recent-regression.log |
| 最终后端补验 | 新证据8项、引用4项、新note纯逻辑4项及公开空next_query保存通过；最后代码变更后委派10项再验通过。见 BACKEND_RESULTS.md；有重叠，不能直接累加成独立覆盖数 |
| 前端 | 52组件、类型检查、构建通过；index-C5uqjULU.js，511受控文件。见 UI_RESULTS.md |
| 实际浏览器 | 5项通过；视觉修正后文稿/图片1项再次通过，2处图片实际64×64解码并由主 Agent 看图复核 |
| Windows 升级/恢复 | 真实setup扩展旧工作区1项通过，188.683秒；windows-expanded-upgrade.log，包含业务/自定义内容/RS保留，不是空目录安装 |
| 实际 AI | 独立AI读合成全文和新worker指导后写note，经公开接口保存/交接；1 note/0遗漏，2481/6000估算。partial缺口保留；见 ai-note-probe/AI_REVIEW.md |
| 登记与工作区 | 测试发现855项、登记857项，无未登记/失踪/定位错误；刷新索引完成，validate为0错误、21项既有警告 |

长组启动后最后的 legacy 决定字段清理和引用括号修复，由最终定向委派/引用补验覆盖。首次测试失败、浏览器旧路径实际缺陷、构建权限重试与AI草稿修正均保留；不能把它们改写成首次全过。

## 文档与边界

六份现行入口已按影响维护：README、ARCHITECTURE、CORE、docs/README、DOCUMENTATION_MAINTENANCE、TESTING；AI_READING、RESEARCH_RECORDING、EVIDENCE_VIEW_MONITOR、MEMORY_STORAGE_EXPLAINED 和相关 Skill 同步。旧规范报告 r7 已阅读全文并盘点差异，未机械替换历史引用，也未宣称该历史报告已整体同步，详见 docs-review.md。

本轮没有更新依赖/模型、推送或发布；没有第二物理机验收。软件测试、合成AI写作、图片字节核验均不证明科学结论或业务检索收益。旧无定位引用仍需以后基于原材料真实审查后新增修订。最终测试目录盘点与工作区校验见 catalog-audit.log、validate.log；固定源码与回执保存到 .run-captures/final-evidence/。
