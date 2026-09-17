# 子Agent材料阅读与有界笔记交接

Run：RUN-20260916T060608Z-6199BA92B86E；Owner：PRJ-ARCHITECTURE-EVOLUTION。2026-09-16，本机Windows x64开发与验证；未发布。

## 目标与实现

将材料搜索、查询改写、候选筛选、完整阅读和reading note写入放在独立低成本reader上下文，主Agent通过固定RS接收有界笔记后推进任务。沿用现有统一设置auto/off，无新增模型依赖、凭据或后台AI服务。

新增公开CLI/HTTP动作reading-delegate与reading-handoff，capabilities的reading_workflow版本4。delegate读取程序缓存中的协作策略，结合宿主声明生成最小任务包和低成本/低推理偏好；返回dispatched=false，真实派工由宿主工具执行。Skill默认使用独立上下文、不继承整个主会话、不递归派工；关闭或宿主无工具时沿同一RS单Agent执行。

handoff只返回一份笔记Markdown与状态，包括理解、连接链、必要细节、不确定性、固定ID/revision/hash/链接。无原始packet、全候选列表、逐轮检索诊断。默认max_chars=12000，允许512–30000；按完整JSON value字符数计长，标准外层envelope另有开销。整条笔记纳入或省略，不切断公式、单位、条件；选择排除/过长/陈旧笔记明示遗漏。极小窗口若连元数据也容不下，返回预算错误，不输出破碎内容。

两动作沿用RS授权、范围上限和累计Ledger；可选expected_revision冲突拒绝，读取不增加语义修订，但实际读取/输出计费。撤权拒绝旧笔记，来源新修订后不交付过期理解。最近一轮检索限制按类别去重传递，候选当前包缺口同样保留；历史失败仍存RS，后续补查解决后不会永久阻止当前交接。complete只描述本次交接，不能证明全库/历史查询或科学研究完整。主Agent检查partial/遗漏/needs_user_input，不能因阅读阶段finish就忽略覆盖限制。

## 核心基线与软件验证

改动前公开阅读动作没有delegate/handoff，resume/view包含笔记、候选与覆盖诊断。最早静态检查固定了缺口，初次执行命令因导入路径失败；后续集成红测发现新fixture查询词无候选导致StopIteration，未将这些错误冒充产品缺陷或功能通过。显式构造可搜索的固定合成技术单元与两条经验后复验。

- 原有41项阅读测试全部通过（查询规划、完整读/笔记、授权、预算、重排与分页）。同轮48项还包含当时新增7项，其中4个fixture错误已保留；修正后仅复验受影响新增测试。
- 最终9项委派集成测试通过，89.054秒：真实CLI.execute、带token本机HTTP、auto/off/宿主回退、只读revision、同RS跨进程预算、撤权、真实来源新修订、未知候选/严格类型、超限零泄漏。
- 2项纯交接语义测试通过：公式/单位/不确定性/固定hash整体保留或整体省略；历史问题解决后恢复当前完整性，最新旧诊断未知与dense缺口仍partial。初次独立导入失败及修复后日志分别保留。
- 合计52项不同阅读行为测试获得通过证据，分上述相关执行，不冒充一次完整全库回归。测试目录revision87，audit：739 discovered/741 catalog，未登记/缺失/错误均0。

日志：verification/reading-regression.log、delegation-baseline.log、delegation-current.log、delegation-final.log、handoff-view.log、handoff-view-final.log、catalog-final.json。前期fixture输入role误写method也被合法校验拒绝，修正为methods后准备完成；未放宽产品校验。

## 实际独立AI验收

真实宿主spawn使用gpt-5.6-terra、low、fork_turns=none。准备者仅给目标、RS、授权与驱动入口，未代替reader生成笔记。隔离合成Owner RES-MQ-A，RS-63e9e661-d62e-42b2-a3d7-a7ffd76f0e51；原预算16MiB读取/80,000输出字符，未重建清零。主材料正文18,843字符，另有两条干扰材料；输入与核对点在verification/ai-fixture固定保存。

reader通过真实公开API完成中英查询、三份完整reading-read、三份reading-note和reading-decide，首版r7/finish；仅回RS/revision/状态给主Agent。主Agent实际只用reading-handoff读取笔记，测试请求max_chars=6000，返回3条笔记、0整条遗漏、0未记笔记候选。独立复核随后发现主方法笔记遗漏独立误差传播公式/假设、部分不确定度单位、精确温标平移关系与合成输入数值，不能由“0整条遗漏”推断语义完整。

同一reader依据已交付材料补齐原note为r8，原预算未提高或重建；原始note修订、v1自查与独立失败复核均保留。主Agent再次通过handoff回读，三条笔记均交付；RS输出累计77,987/80,000字符。Skill补入逐块核对公式/误差假设、单位、条件、反例、关键输入及输出，要求在剩余预算中预留交接。独立语义复核见verification/ai-independent-review.md及ai-independent-review-v2.md，reader自身也保留v1/v2自查，均不是用户或科学认可。

本例reader含修正共9次API响应累计86,788字符；主侧两次handoff完整响应分别3,899和4,181字符（合计8,080），最终value为3,652字符。相对把reader这些响应全部输入主上下文，含一次修正的材料交接响应减少约90.7%。这是序列化字符体积对比，未计初始delegate任务包、提示词、Skill、父任务上下文、独立审查成本及宿主隐藏开销，不能当token/总费用/端到端延迟测量。子Agent仍消耗自己的上下文和推理资源；首轮压缩遗漏也说明短不等于充分。

handoff返回partial、complete=false：dense不可用且technical候选窗口未完；即使reader阶段finish仍保留覆盖缺口。三份已交付材料完整阅读不等于全库覆盖；本次仅合成AI自查，既不是用户认可，也不证明现实工程适用性或真实业务准确率。

## 文档、Skill与兼容

维护README、ARCHITECTURE、CORE、docs索引、TESTING、AI_READING、WORKSPACE_SETTINGS、WORKFLOW_ACTIONS、MEMORY_STORAGE_EXPLAINED与DEVELOPMENT_HISTORY。DOCUMENTATION_MAINTENANCE已核对，无职责变更。8个活跃Skill与8个发现wrapper全文审查：仅work-loop/material-query修改默认阅读/交接流程及主reader职责；其他入口继续引用material-query，无需新增Skill或改发现注册。

Windows x64实际CLI/HTTP与旧RS兼容路径通过；分发收集纳入新增Python模块，前端源和预构建指纹保持不变。本轮不改前端、第三方依赖、模型、安装/恢复及缓存机制，故未重复前端构建或真实setup升级套件；此前设置阶段的真实升级结果保留其原范围，不冒充本轮新执行。源码快照与文件哈希另存verification，不公开临时会话或业务数据。

固定基线为设置报告MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152 r1（hash039bf59d7e92f80067b2c299f0c696719ae418c7adce5b3213f5557bd57c648f）和设置概览MEM-67e69e5f-8de7-5c24-b8bc-eb41299f8eaf r1（hashd8ba36ed48af94e8dece307a8c9b51ba12dc5fcd222e0c4c1892cbe2b3b9bdd9）。已由独立复核者通过公开接口完整读回，complete=true、impact无变化；旧稿明确当时未做子Agent阅读，作为历史设置范围保留，本轮独立编排新完整报告。此前17条其他历史技术内容不属于本次范围，不宣称Project全体已同步。

## 限制与后续

宿主必须提供实际子Agent工具；程序的route建议不保证外部宿主执行。外部AI token不可由RS模型账本观测。输出字符上限不是模型上下文窗口，笔记压缩可能遗漏语义，需要固定出处、必要细节与独立核对；复杂推理/工程认可仍交主Agent或人。当前RS单reader顺序执行，未实现并发读写任务调度或独立模型服务。其他宿主、第二物理机和真实业务阅读质量/延迟/总成本尚待验收。
