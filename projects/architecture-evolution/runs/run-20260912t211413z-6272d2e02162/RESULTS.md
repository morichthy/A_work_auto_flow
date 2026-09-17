# 统一工作流：实现与一致性审查

本次Run：RUN-20260912T211413Z-6272D2E02162。按2026-09-13用户授权实施统一工作流计划；实施前114份文件及Git工作树状态逐字节核对后封存在before.zip与before-manifest.json。保留此前已存在的业务修改，不把它们算作本次迁移。

## 交付内容

- 默认work-loop处理归属、执行记录、保存与续接，material-query独立。7个活跃发现入口，research-loop/workspace-context仅保留短兼容方法；run-execute是公开工具。
- Research、Project、核心算法、Tool、Data、Knowledge、Report、Run都允许按有用内容保存L0–L4，缺层正常，文稿按需；默认normal、auto_summary=false，显式对象策略不改写。普通脚本仍不能成为公司核心算法。
- RS仍是独立持久阅读状态。新增list/view/bind/archive公开动作；Owner与固定检查点绑定不扩授权。view重新核验来源、累计读取预算，不伪造新语义修订；归档可恢复且保留历史。列表是有界目录窗口，不建第二份数据库。
- 工作台系统记忆的“阅读记录”按对象查看目标、候选、已读理解、必要细节与链接，可打开固定原文、刷新和导出标明版本的Markdown。全局列表包含未绑定旧会话。列表/查看不重新搜索；后台不会替AI自动产生理解。
- 是否补查由AI按当前方向、失败、成本与用户偏好判断。已ask_user仍必须记录真实意见；范围、排除、权限和累计预算保留。
- setup只对已知旧发现文件精确指纹执行备份后更新/退休，保留目录附属文件和用户自定义Skill；旧规则差异明确提示合并。源码、前端资源配套；无依赖/模型变化。

## Skill逐项处置与接口核对

| Skill | 处置 | 核对内容与证据 |
|---|---|---|
| work-loop | 新增短主入口 | list-owners/inspect/resume、Run执行登记、validate-draft/commit/checkpoint；独立AI实际调用与固定回读 |
| material-query | 精简 | reading-template/start/recall/read/note/decide/list/view/bind/archive/resume；CLI发现、HTTP浏览器、跨进程和撤权测试 |
| research-loop | 退出默认发现、保留兼容 | 只跳转work-loop；历史Run/身份不迁移；精确旧入口退休/恢复测试 |
| workspace-context | 退出默认发现、保留兼容 | 通用部分并入work-loop/material-query，公司算法定义优先和CTX两级兼容限制移按需参考 |
| context-maintenance | 精简为批量接入 | adopt-owner、ingest-preview/apply、固定来源、按需索引核对；普通记录统一入口 |
| development-checks | 按影响维护 | 六文档/全Skill全审由全局整合、发布或明确要求触发；实际升级、前端、权限/版本边界未取消 |
| evidence-inspection | 修正引用、其余保留 | inspect/raw-materials/raw-material、formal、review/impact、source-lineage与只读监测；公开help和现有回归 |
| association-exploration | 修正公开动作及转入入口 | associations-propose/associations-decide替代不存在的笼统命令；导航与科学认可分开 |
| semantic-maintenance | 完整阅读后无需修改 | maintenance-plan/review/apply与v4迁移、实际审查/幂等/固定来源一致；本次未减少语义审核要求 |

方法源、安装器NAMES/COMPAT_NAMES、.agents发现入口及导航逐项对照。安装预览7项通过；所有默认入口均链接真实方法源。旧受控文件备份在.local/upgrades/，完整原方法另在本Run before.zip中。没有按名称删除用户内容。

## 六文档及持续维护文件

| 入口 | 处置 |
|---|---|
| README | 完整阅读并更新统一入口、内容记录、阅读UI、目录与维护方式 |
| ARCHITECTURE | 完整阅读并更新READ职责、RS单一真源/绑定/计量/UI，保留G模块依赖与稳定边界 |
| CORE | 完整阅读并更新记录与阅读伪代码，保留G01–G12定义/交接；详细参数仍放手册 |
| docs/README | 完整阅读并补公共动作与7+2入口导航，保留当前/历史分类 |
| DOCUMENTATION_MAINTENANCE | 完整阅读并改为影响选择/全局全审，保留固定证据与逐项处置要求 |
| TESTING | 完整阅读后无需改文案；实际新增行为与基线维护落catalog，不重复维护另一套测试清单 |

同时更新根/Project模板/Research/Tool规则、START_HERE、NOW、Project入口、DEVELOPMENT_HISTORY D24、记录标准、实体存储说明、MEMORY_USAGE、AI_READING、WORKFLOW_ACTIONS、MATERIAL_QUERY、KNOWLEDGE_FACETS、RUNTIME_STATUS和UPGRADE_TESTING等。旧D22强制二次询问的理由保留，由D24明确替代；冻结设计、历史Run、不可变规范修订不因改名而改字节。派生上下文包在收口时重新生成。

## 深查发现与修复

1. 旧浏览器用例仍按map/event筛选，后又发现L4总结仍按旧地图草案填写，缺当前概览的问题/阶段。更新用例使用现行入口与真实必填内容，保留旧固定fixture兼容测试，不放松schema。
2. 升级合成fixture循环遗留Owner导致RS绑定超出硬上限，改为实际研究Owner，损坏登记/缺入口拒绝继续保留。恢复比对另外发现测试预期LF、实际旧文件CRLF，改为与升级前实际字节比较；真实setup预览、升级、重复升级及恢复已通过。
3. UI固定原文读取会推进RS修订；若导出沿用新编号却保留旧Markdown会误标版本。独立保留快照版本；下一次写操作仍用服务器返回CAS版本。
4. 来源拒绝和切换对象时清除旧展示；读取错误保留接口code/warnings。列表不输出不可读会话身份/目标，预算消耗回执真实返回。
5. 独立AI初测没找出工具经验；对照发现经验引用两个Run，原scope_ceiling没包含它们。允许真实依赖后固定原文可完整返回。未改旧RS预算/范围；调用参考补明确Run是独立Owner。save_checkpoint疑点经真实提交消除，原错误报告保留。
6. 一次浏览器合成数据创建遇到Windows文件访问拒绝；原失败保留，重跑越过该步骤。不能将这次失败记成首次通过。

## 实际AI与效果边界

独立AI不看父计划或diff，只使用Skill和按需公开说明，实际完成：未执行文档方法保存/固定回读；标准库CSV工具开发、3行合法运行与4行数据拒绝（失败Run保留）；完整阅读两条材料并保存必要细节；新进程恢复；目标/检查点提交与RS绑定；极小--help前后文件哈希无变化。Followup修正初次判断并记录所有真实拒绝、partial和成功。完整合成工作区、请求/回执和报告封存在ai-forward.zip；不是人工业务验收。

RULE_LOAD记录初测请求读取规则29044字符（含按需手册，不含全部注入/代码/回执，不是精确token）；静态Skill前后字符数见skill-size.json。没有旧流程的同题实际AI时间/质量对照，因此不宣称提速比例或总体检索质量提升。八Owner合成回归证明可按正文用途命中16条L3/L4、无L1/L2仍可回原文；真实dense的现有软件回归另列，不等于此AI场景配置了向量。

## 限制

列表最多10000个RS目录、每页目录窗口1–50；筛选后空页可能仍有下一页，归档不减少目录。view/原文读取消耗会话原预算，预算不足需明确报告。旧会话不猜Owner，须显式绑定。绑定带更广依赖的检查点仍可能被原范围拒绝。静态导出不是实时状态或新的授权。

本机Windows x64隔离验证与第二台物理机/真实业务/人工认可分开；历史检索质量未通过、万条规模暂缓仍保留。没有提交Git、发布Release或更换模型包。本次为框架开发组织与验收记录，不为凑层另造技术经验或双文稿。

## 验证结果

| 检查 | 实际结果及回执 |
|---|---|
| 后端全量 | 598项，1965.601秒，首轮报告5处失败（涉及4个方法，其中Owner测试2个子案例）；[原日志](verification/unified-backend-full.txt)不可改写为通过 |
| 全量失败处置 | 旧升级fixture Owner绑定：18项复验中已通过；旧换行预期随后修正，[真实setup单项](verification/unified-setup-verified.txt)通过；自动总结默认值旧断言：[Owner接口2项](verification/unified-owner-service-verified.txt)通过；既有B01冻结基线仍失败。合并复验仅剩B01，未声称重新整轮全绿 |
| 阅读行为 | 15项定向通过，且进入全量；[回执](verification/unified-reading-tests.txt)，包括Owner/检查点、归档/恢复、撤权、版本、预算、已读笔记和跨进程 |
| 八Owner完整链路 | 1项参数化合成测试覆盖8类对象、16条记录、正文用途词命中及原件回读；[回执](verification/unified-owner-tests.txt)；已有Owner/策略/旧版本回归进入全量 |
| Windows升级 | 18项不同检查全部获得通过证据：17项见[升级回归](verification/unified-upgrade-final.txt)，最后真实setup预览/升级/重复/恢复见上述单项回执。原失败和保护断言保留 |
| 前端 | [38项组件](verification/unified-vitest-final.txt)通过；[类型检查与最终构建](verification/unified-build-last.txt)通过，资源指纹与源码一致 |
| 普通浏览器 | 16项不同场景全部通过：材料查询5项见[第一组](verification/unified-e2e-verified.txt)，工作台含阅读3项见[第二组](verification/unified-e2e-retry.txt)，记忆8项见[最终组](verification/unified-memory-browser-last.txt)。前两组其他旧失败保留，不合成一次全绿执行；未运行暂缓的一万规模场景 |
| 清单与入口 | catalog r71、655项登记/653项静态发现、40项基线，[审计](verification/unified-catalog-audit-r71.txt)通过；6项相关基线复审，成员不减。7个默认Skill发现与安装预览一致 |
| 工作区 | validate为0错误、8个既有历史链接警告；更新索引与派生上下文。Windows换行规则下diff --check通过，未归一化旧固定字节 |
| 实际AI | 独立上下文公开调用、固定回读与后续纠错；完整证据见[ai-forward.zip](ai-forward.zip)，与软件结果及人工认可分开 |

新增审查修正：八Owner旧公开只读测试仍要求Research/Project自动总结；按新默认统一验证retain、normal、auto_summary=false，同时保留只读不创建档案与旧v2内容兼容。没有通过删除断言隐藏默认值变化。

封存输入见[source-fingerprints.json](source-fingerprints.json)、[source.zip](source.zip)与[before.zip](before.zip)，实际代码仍为脏工作树，未伪称全部改动来自一个已提交版本。前后快照文件不直接作为当前文档入口；before.zip逐项核验114份原字节，展开副本移至.local保留，避免副本相对链接产生113条伪现行警告。源注册、正文授权、规范旧修订均未借此修改。
