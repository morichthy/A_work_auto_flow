# 子 Agent 阅读与有界笔记交接

目标：将搜索、候选筛选、完整阅读、阅读笔记写入放在独立低成本上下文；主 Agent 仅接受固定 RS 的有界 reading note，再推进任务。归属 PRJ-ARCHITECTURE-EVOLUTION；Run：RUN-20260916T060608Z-6199BA92B86E。

## 工作清单

- [x] 核对现有 RS、设置开关、权限、累计预算和 Skill 入口；现有 resume 同时返回全文式笔记、候选与轮次诊断，缺委派交接接口。
- [x] 固定缺失功能基线与负例测试。
- [x] 新增 reading-delegate 精简任务包及 reading-handoff 仅笔记交接；CLI/HTTP/capabilities 同步。
- [x] 工作流实际使用宿主子 Agent；关闭/不可用同 RS 单 Agent 回退。
- [x] 验证边界及真实独立上下文阅读；记录主侧输出成本，不能以字符减少证明准确率或总费用降低。
- [x] 维护受影响文档与全部 Skill 调用者；登记测试与固定结果。
- [ ] 保存技术结果、编排并回读完整报告，refresh-index/validate。

## 设计与边界

沿用 RS 唯一状态，不增加代理任务数据库。delegate 是宿主调度建议与最小任务包，返回 dispatched=false；宿主真正调用 spawn 才是已委派。auto/off 由程序缓存读取，不让 AI 读设置文件。低成本/低推理是偏好，宿主选择可用模型；独立上下文，不复制整个主会话、不递归派工，同 RS 一次一位 reader。

handoff 再授权并校验可选 expected_revision，沿用固定累计 Ledger，读取不增加语义 revision。仅输出笔记、必要细节、固定来源和缺口；整条笔记装入 max_chars，超长整条省略，不截断公式。主 Agent 默认 JSON 交接，保留 complete/partial/ask_user/遗漏计数。外部宿主模型 token 不可由检索程序观测，不能声称累计 Ledger 覆盖它；由宿主另控任务与输出成本。

测试范围：阅读相关软件回归、CLI/HTTP路由、权限/旧预算/修订/超长与陈旧来源；真实低成本独立 Agent 走公开阅读接口，主侧仅回读handoff。此次不改前端、依赖模型或安装机制；核对 Windows x64 源码分发及旧RS兼容，不重复无关前端构建。若实现触及安装/缓存边界再补真实setup测试。

## 当前依据与处置

基线：现有统一设置报告 MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152 r1 与概览 MEM-67e69e5f-8de7-5c24-b8bc-eb41299f8eaf r1，前轮已完整读回；本轮收口前核对固定版本和影响，旧性能与验证保持历史时点。

读取实现：reading.py note/resume/reauthorize、reading_catalog.py、CLI/capabilities、workspace_settings；阅读材料与查询的所有权/预算不变。新技术单元独立说明委派边界，不把宿主调度声明写成内置后台 AI 服务。

软件：原41项与新增11项不同阅读测试通过，catalog revision87审计通过。首轮新fixture无候选与纯测试导入错误已修，保留原日志。CLI/真实HTTP与旧RS边界验证通过，本轮无前端/依赖/安装逻辑变化，不重复无关升级测试。

真实AI：gpt-5.6-terra/low独立上下文reader完成三材料阅读，主线只读取handoff；r7漏了不确定度公式等必要细节，经独立原文核对后同RS修订为r8，无预算重置。最终3652字符value、两次handoff共8080字符，对应reader9响应86788字符；覆盖partial保留，不推断总费用或语义准确率。见Run/RESULTS.md和独立v1/v2复核。

文档：README/ARCHITECTURE/CORE/docs索引/TESTING及阅读/设置/公共动作/实体手册/历史已更新；DOCUMENTATION_MAINTENANCE无职责改动。8活跃Skill+8wrapper已完整核对，仅work-loop/material-query改动；补技术逐块语义覆盖及交接预算预留要求。

固定基线已读回：设置报告/概览r1 hash与前轮一致，HEAD COM-1f5353c7-d2a7-4127-8fa4-a57cfa9547e4，document完整/impact无变化。旧稿保留设置时点，本轮新增独立完整子阅读报告；17条其他历史技术内容范围外。当前进入规范技术结果/文稿保存、全文回读与最终校验。
