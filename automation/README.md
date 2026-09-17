# 工作区自动化

统一入口：根目录 `setup.cmd` 安装/升级/命令注册，`workbench.cmd` 打开工作台，`workbench.cmd test-data` 生成 Git 忽略的跨模块合成沙盒。参数、数据保留和恢复见 [一键部署手册](../docs/SETUP_WORKBENCH.md)。

核心 CLI 创建全局核心算法、对象内 Run 与可选项目；无归属轻量任务才使用根 runs，旧布局按稳定身份兼容。文件与记忆检索共用 SQLite 文件和本地 Qdrant/FastEmbed 基础设施，表、向量集合、回执和默认策略仍有区别。文件上下文使用 focus/investigate/wide 与 CTX 反馈，记忆使用 QMEM 查询和 PKT 材料包；选择入口见 [检索手册](../docs/RETRIEVAL.md)。

`workflows/` 保存方法正文，work-loop、context-maintenance、evidence-inspection、development-checks、material-query、association-exploration、semantic-maintenance、consolidate-results 八项已登记轻量入口；具体分工见[工作流索引](workflows/README.md)。research-loop 和 workspace-context 已退休，由 work-loop 统一承接。安装器默认预览，--apply 新建缺失入口，已有不同内容保留并输出合并差异；受控旧入口按升级回执退休，自定义内容保留。

## 维护边界

- `scripts/memory/store.py` 和 `service.py` 维护对象 HEAD、不可变提交和专用动作；普通编辑器不直接改规范记忆。
- `memory/index.py/search.py/packets.py` 维护可重建索引、规范身份排名与预算；SQLite/Qdrant 不是规范正文的权威来源。
- `memory/technical_units.py/documents.py` 维护 L1 技术块与独立完整过程/简版文稿；L4 地图和旧 map.report 兼容有明确边界。
- `scripts/workbench_app/` 与 `frontend/` 维护展示和交互，文件检索由 `retrieval.py/context_engine.py` 保留；AI 行为由规则和 Skill 指导，不由相似度分数自动决定。

具体数据流见 [架构说明](../ARCHITECTURE.md)，同步范围见 [文档维护手册](../docs/DOCUMENTATION_MAINTENANCE.md)。

## 命令

环境健康、逐结论复核、正式 Run 封存与跨文档失效已接入现有 CLI，详见 [证据准入手册](../docs/EVIDENCE_CONTROLS.md)。`doctor` 报告实际组件状态，`verify --profile full` 不允许跳过必要集成测试。

证据工作台使用 `evidence-view --serve`，只监听本机并展示依据/复核/报告影响；省略 --serve 可生成离线 HTML。`evidence-monitor --dry-run` 预览变化，去掉 --dry-run 保存观察基线与维护候选，不修改原件或可信状态。监测可交给已配置的定时器重复调用。见 [查看与监测手册](../docs/EVIDENCE_VIEW_MONITOR.md)。

```powershell
# 检查目录、JSON、链接、疑似秘密和大文件。
.\automation\workspace.ps1 validate

# 从模板创建对象；默认拒绝覆盖。
.\automation\workspace.ps1 new-project <slug> --title "项目名"
.\automation\workspace.ps1 new-research <slug> --title "研究问题"
.\automation\workspace.ps1 new-run --title "分析目的"
.\automation\workspace.ps1 new-run --owner RES-ID --title "中文标题" --keyword "温漂"
.\automation\workspace.ps1 search-runs "温漂" --project <slug> --limit 10
.\automation\workspace.ps1 review-run RUN-ID --status disputed --reviewer "用户" --reason "发现新反证"

# 派生索引与任务上下文。
.\automation\workspace.ps1 refresh-index
.\automation\workspace.ps1 build-context --project <slug> --task "任务描述"

# 先预览会发生什么。
.\automation\workspace.ps1 new-project <slug> --title "项目名" --dry-run
```

需要直接运行 Python 核心算法或测试时，使用解释器发现包装：

```powershell
.\automation\python.ps1 -m unittest discover -s automation/tests -v
```

## 自动化边界

- `search-runs` 即时读取 Run 源元数据并计算已登记依赖影响；关键词由 AI/用户填写，不自动调用模型提词。
- `review-run` 原子保存复核前后历史；accepted 要求 evidence/scope，superseded 要求 replacement。命令不认证证据与身份；同一 Run 的复核应串行执行。
- `refresh-index` 另生成 `run-index.json`，主导航只放最近 20 项。修改复核后先刷新再共享快照；旧上下文不会自动更新。
- `context/generated/` 是派生视图，可随时重建，不能覆盖人工事实源。
- 创建命令不会覆盖现有对象。
- `build-context` 只加载配置允许的导航层和显式核心算法/项目/研究入口，不扫描共享盘或大产物。
- `validate` 的警告不代表公司级合规审计通过；它只是尽早发现结构性错误。

## 推荐节奏

- 每次结构性变更：`refresh-index` + `validate`。
- 复杂任务：维护计划；产生独立分析证据时建 Run，结束时保存必要记录，满足复核条件才晋升知识。
- 每周：整理 `inbox/`、检查 open Run 和未决行动。
- 每月：填写 `knowledge/reviews/REVIEW_TEMPLATE.md` 的实例，评估文档漂移和自动化机会。

配置支持 SQLite FTS5 与本地 Qdrant 混合召回，当前副本的依赖和模型能力由 doctor 实测。`memory search` 缺省 vector=auto，`memory context` 内部查询缺省 off；文件检索按配置启用向量。派生索引 pending 或模型不可用时读取具体回执，不能把结果存在当作全链路就绪。其他平台按实际需要选择，保留业务对象 ID 与开放文件格式。

核心算法导航使用 `build-context --module <slug>`，这里接收目录短名；语义材料问答用 `retrieve-context --module MOD-ID`，这里接收稳定 ID。
