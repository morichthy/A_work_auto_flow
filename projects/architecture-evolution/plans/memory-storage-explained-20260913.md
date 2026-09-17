# 记录与检索实体说明整理

日期：2026-09-13。用户要求把本次问答按直白、关键字段及实体链接、不过度展开的标准整理为CORE按需补充，并规定相关开发主动维护。

交付：docs/MEMORY_STORAGE_EXPLAINED.md；CORE保存/检索两节链接；docs/README索引；DOCUMENTATION_MAINTENANCE维护触发；DEVELOPMENT_HISTORY记录选择原因。不改变程序、依赖、运行模型、规范memory、Run或既有用户修改。

六份必读前后核对：README、ARCHITECTURE、TESTING已检查无需修改（概念、模块及验证策略不变）；CORE、docs/README、DOCUMENTATION_MAINTENANCE已修改。DEVELOPMENT_HISTORY已重读并新增D21。细节按RESEARCH_RECORDING、MEMORY_USAGE/REQUESTS、contracts/service/store/index/retrieval及MQ召回代码核对。

逐项Skill语义审查（包括使用时机、方法/公开接口、发现入口、安装登记）：

| Skill | 结论与理由 |
|---|---|
| workspace-context | 已检查无需修改：仍按固定记录/技术正文核对；新增说明从CORE发现 |
| context-maintenance | 已检查无需修改：Run登记与source、草案/提交/回读分工一致 |
| evidence-inspection | 已检查无需修改：保存/执行/复核边界及L0入口一致 |
| research-loop | 已检查无需修改：技术块、Run绑定与独立文稿定义一致 |
| development-checks | 已检查无需修改：已要求读取维护手册，本次触发集中维护在那里 |
| material-query | 已检查无需修改：词法/显式dense及正文块入口一致，不改变公开行为 |
| association-exploration | 已检查无需修改：实际比较与导航采纳不等于科学支持 |
| semantic-maintenance | 已检查无需修改：实际审查、公共提交、固定回读与历史保留一致 |

8项方法源、安装器NAMES、发现目录及工作流README一一对应；无新增/退休/重装Skill，不涉及全局插件。Windows x64可迁移性：新增说明使用相对链接，不嵌入本机绝对路径；明确公共包缺少研究实例和本地索引，集合路径不绑定某次编码版本。无代码/模型/安装逻辑修改，无需运行真实setup回归。

验证选择：纯文档新增，核对本次链接与含义，执行refresh-index和validate；不重跑数值实验、检索质量或完整软件回归。结果在完成后补记。

验证结果：refresh-index成功；validate退出码0，0错误、8警告。警告均在本次未修改的历史architecture-snapshot及discussion-before-research链接，保持历史文件原样。新增说明29个本地链接逐一检查存在，无缺失；CORE第2/3节入口与目标标题核对一致。完成说明页回读，未修改代码或冻结业务记录。校验不等于重新验证样例科学结论或检索质量。
