# 分层记录独立可读性与证据展示

日期：2026-09-17。状态：修订与针对性验证完成。归属：架构演进；业务修订范围：research/floating-point-summation。

## 目标与约束

每条 L0–L4 记录离开聊天、列表和相邻记录后，仍能从自身背景与正文理解对象、问题、条件、本条内容、结果和限制。L2 交代背景、实际经过与简单结论；L3 给出可使用的认识和适用边界。固定引用负责核验，不能代替必要解释。保留旧版本和真实复核状态，AI 补写不构成人工确认。

同时补齐证据详情的确认状态；对象记忆的常用类型收敛到 L0–L4 和研究文稿，必要的管理、复核、章节及历史类型保留后端用途。

## 工作分工与依据

- 主 Agent：记录标准、生成 Skill、其他 Owner 要求与文档一致性、集成检查和最终结果。
- UI 子 Agent：证据详情复核状态、对象记忆筛选、相关代码与测试、预构建资源。
- 记录子 Agent：公开接口阅读全文、逐条更新浮点记录、维护文稿关系并回读。
- 只读审查子 Agent（gpt-5.6-terra，低推理）：各 Owner 生成路径与必要记录类型盘点。

已读入口：context/START_HERE、NOW、work-loop、material-query、development-checks、consolidate-results；已定位 RESEARCH_RECORDING、CORE、MEMORY_STORAGE_EXPLAINED、ARCHITECTURE、相关 AGENTS 和历史 D09–D11/D24。当前机制已允许各 Owner 保存全部层级，缺口主要是写作约束未明确要求单条脱离上下文后可用。

初始工作树有历史未提交变化，包括浮点三份旧提交文件、架构项目记录、来源登记、生成索引和其他任务文件；本轮保留，不恢复或将其归为本次修改。

## 验证与进度

- [x] 各 Owner 生成要求及真实保存入口核对：所有八类共用 policy/work-loop/MEM，无另一个自动生成器；公司算法准入与 knowledge 身份采用仍保留。v4 读取只交正文，payload 完整不证明正文独立。
- [x] 单条独立可读性规则与相关 Skill 同步：RESEARCH_RECORDING 增加逐层要求和 Owner 映射，MEMORY_REQUESTS、work-loop、context-maintenance、semantic-maintenance、consolidate-results 及算法专项参考衔接。
- [x] 浮点当前记录及完整文稿审阅、公开提交、固定回读。
- [x] 证据状态与类型筛选测试、真实浏览器阅读检查。
- [x] 前端类型检查、构建与指纹；按实际影响选择 Windows 升级检查。
- [x] refresh-index、validate、文档处置与最终限制记录。

软件检查、AI 内容自查、科学复核和用户验收分别记录。当前未作新的浮点实验，不把文字补全当作新实测或自动确认。

## 已完成的界面验证

验证 Run：[RUN-20260917T033921Z-F62D40725A33](../runs/run-20260917t033921z-f62d40725a33/README.md)。7 项组件、8 项证据内容、17 项证据复核、2 项实际 Edge 合成浏览器检查通过，类型检查和构建完成。首次浏览器检查因构建后修改测试源码导致指纹不符，重新构建后通过；详见 UI_VALIDATION。正式旧服务仍在运行，新代码不能热加载；本次真实记录页面检查使用隔离快照，不关闭用户服务或绕过锁。

文档处置：README、ARCHITECTURE、CORE、docs/README、DOCUMENTATION_MAINTENANCE、TESTING 及记录/请求/存储/证据/记忆手册已按本次影响维护。material-query 的 note 不是规范记录，既有读取与独立写作分工已核对，无需改其检索逻辑；development-checks、发现入口与安装登记无需变更。没有新增动作、依赖、模型、Owner 种类或规范记录 schema 字段；证据详情增加只读复核状态和辅助结构正文返回字段，前端及测试同次适配。
