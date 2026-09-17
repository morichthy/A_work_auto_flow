# 当前状态

更新：2026-09-16。默认工作入口[work-loop](../automation/workflows/work-loop/SKILL.md)，本地查阅用material-query；小操作可不建档。各Owner按有用内容组合L0–L4，文稿按需。规则、代码和接口现状分别见[架构](../ARCHITECTURE.md)、[CORE](../docs/CORE.md)与[手册索引](../docs/README.md)。

## 当前开发

2026-09-18 [Owner压缩发现索引与互补筛选包](../projects/architecture-evolution/plans/owner-discovery-retrieval-20260918.md)已实施：独立发现FTS/向量投影和Owner双水位从L4/L3、L2紧凑内容、L1检索说明及Owner元数据发现Owner，先做Owner级跨路线融合，再交付通常2–3、最多4窗的互补筛选包；CE按单窗截取/降级，用户明确选择后才执行全库全文补偿。standard/associative只完整分页读取AI判为relevant的Owner，quick保持片段语义，legacy会话兼容。三个长期Owner经低等级模型审核均无L4/L1结构缺口，只逐Owner重建了发现索引。定向回归、前端、真实HTTP/socket与扩展旧工作区升级/恢复已验证；[完整结果](../projects/architecture-evolution/runs/run-20260917t181639z-af7701fd84ad/RESULTS.md)。L0–L4形成规则和相关Skill已同步；召回率、延迟、候选量、CE成本、上下文和错误联想效果评估按约定未做，未发布。

2026-09-17 [v0.4.0发布准备](../projects/architecture-evolution/plans/release-v0.4.0-20260917.md)已完成本地包与验收，尚未推送/公开：发行提交4c20ea2，745项后端744通过/1既有B01失败，85组件、24常规浏览器及实际离线安装升级再打包恢复通过。当前仅morichthy仓库有写权限；自动审批要求用户确认具体公开目的地，问题待答复。[完整回执](../projects/architecture-evolution/runs/run-20260917t050927z-ed84cd45d259/RESULTS.md)与固定附件已登记；确认后核验草稿附件再公开。

2026-09-17[记录独立性与确认状态](../projects/architecture-evolution/plans/record-context-independence-20260917.md)已修订：全部Owner共用逐条L0–L4独立上下文要求，浮点记录及两文稿已同步到generation19；证据页补确认状态、折叠重复结构并修复引用编号，对象记忆主筛选收敛为六类。12个真实页面、19项Windows升级/恢复及针对性回归通过。[结果与边界](../projects/architecture-evolution/runs/run-20260917t033921z-f62d40725a33/RESULTS.md)保留旧固定引用原因；无新科学确认，需重启旧工作台加载，未发布。

2026-09-17[阅读知识正文与类型详情](../projects/architecture-evolution/plans/reading-content-evidence-20260917.md)已修复：note不再混入reader编排，联想由主Agent定题；首页统一模式/笔记/证据入口，系统记忆摘要跳详情；文稿、L0–L4、Run和受控图片按类型显示。修复工具注册表成员被误判Owner损坏；真实浮点r9保持历史不变，文稿4图可读。93项阅读、10项最近笔记、52组件、5浏览器及真实扩展旧工作区升级/恢复通过，最终补验与AI验收见[本次结果](../projects/architecture-evolution/runs/run-20260917t021448z-bc1aaf379a2c/RESULTS.md)。旧无定位引用不臆造，历史规范报告r7差异已盘点但未整体同步。需重启旧服务并刷新页面，未发布。

2026-09-17[最近问题笔记与证据详情](../projects/architecture-evolution/plans/recent-notes-evidence-20260917.md)已实现：当前笔记可选最近24小时更新的问题，context/recent导航同规则；展示与正式handoff核验分开，现场热读约0.2秒。编号引用可跳记录详情/引用/下游，公式支持与旧浮点note排版r9已验证。完整验证及早期CLI异常边界见[本次Run](../projects/architecture-evolution/runs/run-20260916t212839z-337776b112fc/README.md)。需重启旧工作台加载后端，未发布；历史规范报告本轮尚未合并。

2026-09-17[三种阅读模式](../projects/architecture-evolution/plans/reading-three-modes-20260917.md)已实现：标准Owner全文、note驱动联想加深、仅召回片段的快速模式；工作台可保存默认策略、切换当前会话及编辑联想文本。93项阅读回归及最终13项局部复验、设置/界面/真实升级与合成AI流程完成，主Agent已固定接收综合稿及quick笔记，partial缺口如实保留。[完整结果](../projects/architecture-evolution/runs/run-20260916t200528z-e244b6ee59a3/RESULTS.md)。需重启运行中的工作台加载新后端，未发布；真实业务检索收益未测定。

2026-09-17 note写作要求改为可续接的简化完整文稿，讲清实际研究演进、方法/证据和认识变化；.local/JSON是会话实现选择，并非AI要求，本轮未迁移。[叙述样例与边界](../projects/architecture-evolution/runs/run-20260916t201935z-6c6692a35c2a/RESULTS.md)保留10+7项局部检查、固定全文样例，以及实时召回完整性失败；未覆盖旧笔记。

2026-09-17[reader默认质量流程](../projects/architecture-evolution/plans/note-quality-defaults-20260917.md)已补齐：提取与自查写入直接派工要求，保存note时检查显式来源漏登/未知；不加主Agent固定复检或额外AI调用。23项Owner、10项委派及一次合成AI首稿验证通过；语义完整性仍属reader职责。[结果](../projects/architecture-evolution/runs/run-20260916t195725z-16cdcd28570d/RESULTS.md)。

2026-09-17[Owner文稿阅读与note预算](../projects/architecture-evolution/plans/owner-document-reading-20260917.md)已实现并验证：逐Owner渐进候选/完整文稿、研究式note、统一设置；[结果](../projects/architecture-evolution/runs/run-20260916t181657z-4d7efff321ba/RESULTS.md)保留320字符首批和5517/6000最终note。召回仍约89秒且CE回退；软件通过不代表整体质量/提速，未发布。

2026-09-17阅读上下文与工作台入口已修复：RS JSON继续为唯一状态，新增 `context/reading-notes/<RS-ID>/current.md` 可读副本，修复列表分页/授权域兼容，首页当前笔记、主题导航与定向证据链路可用。31项阅读后端、17项组件、19项Windows升级用例有通过证据；浏览器6项5过，既有规模N0超时未修。真实浮点RS r5已回读、缺口保留，列表仍有来源核验延迟；源码未发布。见[清单](../projects/architecture-evolution/plans/reading-note-workbench-20260916.md)与[结果](../projects/architecture-evolution/runs/run-20260916t155857z-a3d7b61bdd32/RESULTS.md)。

2026-09-16至17日完成[工作台五项修复](../projects/architecture-evolution/plans/workbench-state-fixes-20260916.md)：Owner记录范围监测、ZIP间接哈希排除、证据启动预载、顶层/记忆子页结果保留、对象记忆手动生成及研究经过优先。总结刷新旧包回填竞态同步修复。40项后端、52个组件、18个浏览器与18个升级用例有通过证据；首次失败/修正、0错误21既有警告和性能边界见[结果](../projects/architecture-evolution/runs/run-20260916t154043z-cfb59d215dff/RESULTS.md)。已更新预构建资源，需重启旧服务并刷新页面；未发布。

2026-09-16设置页新增“子agent能力要求”：默认较低能力/低成本/低推理，文本由程序缓存并传给宿主选模型；旧schema1无损读取、自定义偏好升级保留。25项后端、10项设置组件、2项真实浏览器及18项Windows不同用例有通过证据（首次失败和复验保留）。见[结果](../projects/architecture-evolution/runs/run-20260916t081757z-4c8b6eb90e82/RESULTS.md)及[清单](../projects/architecture-evolution/plans/subagent-requirements-20260916.md)。默认值随源码发布，根workspace-settings.json为不分发的私人配置；未推送发布。

2026-09-16已接入[子Agent材料阅读](../projects/architecture-evolution/plans/reading-delegation-20260916.md)：低成本独立reader处理检索/完整阅读/笔记，主Agent仅接收有界handoff；沿用auto/off与同RS回退。原有41项及新增11项阅读测试通过，真实独立AI交接保留覆盖缺口；具体字符测量、失败修正与宿主边界见[结果](../projects/architecture-evolution/runs/run-20260916t060608z-6199ba92b86e/RESULTS.md)。未发布，不宣称总费用或业务正确率改善。

2026-09-16工作台新增“工作区设置”：可调子Agent协作策略、材料查询/AI阅读数量和累计预算、阅读重排模式与候选池。程序加载并缓存，新模板/页面采用设置，旧RS与显式请求保持原值；已通过设置/阅读/组件/真实浏览器及Windows升级验证。见[完整结果](../projects/architecture-evolution/runs/run-20260916t051529z-eec543c75781/RESULTS.md)与[清单](../projects/architecture-evolution/plans/workspace-settings-20260916.md)。不改变正式工作区偏好，不宣称宿主硬禁用或端到端提速，尚未发布。

2026-09-16正文/条件/CE重排已接入新AI阅读模板（auto，旧RS保持off），真实离线模型与Windows分发链已验证。见[实施结果](../projects/architecture-evolution/runs/run-20260916t035620z-93aca3a94bae/RESULTS.md)。本轮新增独立可选重排模型，不改变384维召回索引；业务效果、长文窗口与规模延迟仍待验收，尚未公开发布。

2026-09-16已将同一提交89ad307与四个原版附件同步发布到[morichthy账号的v0.3.0](https://github.com/morichthy/A_work_auto_flow/releases/tag/v0.3.0)，标签及附件哈希一致；保留origin并增加morichthy远端，未配置自动双向同步。回执追加在原发布Run中。

当前版本[v0.3.0已正式发布](https://github.com/livky/A_work_auto_flow/releases/tag/v0.3.0)，标签与推送提交89ad307一致，四个附件大小/SHA256核验通过。双语查询规划、词库升级保护和成果整理Skill已交付；后端610项中609通过、既有B01失败保留，38组件/16普通浏览器及完整离线安装升级再打包恢复通过。规模误触发超时与第二物理机待验收单列。见[发布清单](../projects/architecture-evolution/plans/release-v0.3.0-20260916.md)及[固定结果](../projects/architecture-evolution/runs/run-20260915t211906z-dc3a7c82c601/RESULTS.md)。

2026-09-16新增[整理更新当前成果Skill](../automation/workflows/consolidate-results/SKILL.md)，接入work-loop的重要成果保存/阶段交接；中间记录可自主提交。当前默认8项活跃Skill，下面2026-09-13的7项为当时实施记录。发现入口、升级验证和实际AI场景进度见[本次清单](../projects/architecture-evolution/plans/consolidate-results-skill-20260916.md)。无后台自动同步，声明已同步须实际全文和上下文检查。

上一版[发布清单](../projects/architecture-evolution/plans/release-v0.2.0-20260913.md)：用户已确认具体GitHub目的地；最终提交28f05ad已推送，v0.2.0已公开发布：https://github.com/livky/A_work_auto_flow/releases/tag/v0.2.0 。标签解析到最终提交，四个附件的大小与SHA256均已核验；发行包不含本地经验、工作记录、数据库或来源登记。既有B01测试失败和第二物理机待验收仍保留。

Owner选择、补查判断与可见工作清单的补全见[当前任务清单](../projects/architecture-evolution/plans/work-context-followup-20260913.md)。持续任务优先复用已有计划，由AI更新Markdown，RS保存阅读子任务；没有新增后台维护或工作台标签。

[统一工作流计划](../projects/architecture-evolution/plans/unified-workflow-skills-20260913.md)已实施并完成本轮一致性审查，[实际结果](../projects/architecture-evolution/runs/run-20260912t211413z-6272d2e02162/RESULTS.md)及修正复验已保存。598项后端全量执行后仅剩既有B01问题未解决；38项组件、16项普通浏览器、18项升级检查通过，实际AI合成任务另列。默认7项活跃Skill，research-loop/workspace-context已退休并删除方法目录。各Owner默认normal、auto_summary=false、允许L0–L4；既有显式策略优先。

工作台阅读入口已集中到首页“当前阅读笔记”，可选择最近24小时更新的问题并控制三种模式；“系统记忆→阅读记录”入口已移除，RS历史和公开阅读接口保留。阅读HEAD是真源，Markdown是派生展示；联想问题与关键词由主Agent制定，reader只整理材料知识。历史ask_user仍需真实意见，授权与累计预算不放宽，无后台AI。

## 当前基础能力与限制

- v4聚合契约兼容v1–v3；新L2经过、L4概览和分类经验用v4，L1/独立文稿用v3。旧修订及固定字节保留，不能批量改类型名迁移。
- 材料查询按内容来源/标准Owner筛选，身份/词法/可选本地向量召回；AI阅读分别查各层，短候选全文、L1命中块及必要定义，保留后再完整阅读。索引、完整交付、AI理解和结论复核是不同状态。
- 来源修订/撤权需回查；历史导出不可绕过当前授权。RS是私人工作数据，不能按缓存清理。Qdrant local仍有进程排他限制。
- Windows升级仍走独立新版源码的setup.cmd，保留原业务/配置和恢复回执；召回向量标准模型自动迁移限约定名称/路径与兼容384维；2026-09-16新增的CE重排模型是独立可选组件，见上方结果。

## 历史与待验收

- 层级整理与浮点迁移：[实施记录](../projects/architecture-evolution/runs/run-20260910t125056z-8d1e5d9047b1/RESULTS.md)、[后续收口](../projects/architecture-evolution/runs/run-20260910t183626z-429304f92e99/RESULTS.md)。固定研究报告保留当时定义，新工作以现行手册为准。
- 正文块索引：[2026-09-12结果](../projects/architecture-evolution/runs/run-20260912t021858z-b6e2da1386d3/RESULTS.md)；初版阅读流程：[原计划](../projects/architecture-evolution/plans/ai-reading-workflow-20260913.md)。
- 历史独立题集检索质量未通过、万条规模暂缓；真实业务质量、人工与第二物理机验收分别待审，不能用当前软件检查抵消。历史缺来源/旧指纹问题仍保留。详情见[Project](../projects/architecture-evolution/README.md)及[历史状态](../docs/design/system-memory/STATUS.md)。
- [人工检查表](../projects/architecture-evolution/runs/run-20260910t063103z-902da8123205/HUMAN_CHECKLIST.md)未填项不当作通过；无自动远程备份、通用代码影响监听器或企业连接器。
