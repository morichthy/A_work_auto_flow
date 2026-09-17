# Owner 压缩发现索引与互补筛选包：实施结果

日期：2026-09-18。Owner：`PRJ-ARCHITECTURE-EVOLUTION`。本次完成软件实现、升级验证、现行文档与 Skill 同步；未发布。

## 已实现

- 新增独立 `memory_discovery_entries`、`memory_discovery_fts`、`memory_discovery_index_state` 和独立 Qdrant collection。投影只含 Owner 元数据、L4/L3、L2 紧凑内容与 L1 `retrieval_description`，排除 L1 blocks、文稿、L0 和 RS note。
- 规范提交先将受影响 Owner 的 discovery 水位置为 `pending`；`rebuild-discovery` 使用固定 `owner_id + expected_head + projection_version` 幂等重建，词法/向量分别记录状态。旧 HEAD、撤权或固定来源变化不会借旧投影返回。
- identity、lexical、dense 在信号族内各对每个 Owner 投一票，保留查询变体、通道、定位和 fixed refs，再做 Owner 级融合。每 Owner 生成通常 2–3、硬上限 4 个互补筛选窗。
- CE 输入公开上限为 512 token；超长项围绕真实命中确定性截窗。`auto` 只让失败窗口保留原排序，其他窗口继续评分；`required` 继续显式失败。
- `reading-recall` 默认交付 Owner 筛选包；`reading-assess-owners` 保存 relevant/uncertain/irrelevant 和包摘要。standard/associative 只完整分页读取 relevant Owner；quick 只使用实际发现片段。
- `reading-recall-fulltext` 是独立用户动作，复用原会话、冻结范围、查询计划、预算和版本。发现不可用、覆盖不完整、结果不足或 AI uncertain 都不会自动调用它。
- CLI、HTTP、JSON Schema、生成 TypeScript、工作台 Owner 卡片、状态提示、显式补偿按钮和设置均已接入。设置默认每 Owner 3 窗、硬上限 4、每批 10 Owner、CE 512-token 命中中心窗；旧设置只在内存补默认，写入仍要求完整 CAS 快照。

## 既有 Owner 处置

低等级模型按固定 HEAD 审核三个现有长期 Owner：`PRJ-ARCHITECTURE-EVOLUTION`、`RES-AI-EXPERIENCE-CONTEXT`、`RES-FLOATING-POINT-SUMMATION`。三者均已有 L4 和 L1 检索说明，确定性缺口只有 `DISCOVERY_INDEX_NOT_READY`，因此没有生成无必要的规范内容修订。

随后逐 Owner 重建独立发现索引：架构 Owner 36 个词法条目/51 个向量点，AI 经验 Owner 15/17，浮点 Owner 12/27；三者词法与向量水位均为 indexed。重建使用 `owner-discovery-minilm-v1` 和独立 collection `memory_discovery_v1_8a65f36bacb3`。详细回执见 `DISCOVERY_REBUILD.md`。

审核时发现浮点 generation 19 manifest 引用的一个不可变 commit 目录在工作树中被删除；从当前 Git HEAD 恢复了该确切历史目录后再重建。没有改变浮点当前 HEAD、规范记录、review 或原件。

## 验证

- 改造前基线：7 个既有文件共 104 项通过。
- 最终 Python 定向回归：17 个测试文件共 202 项通过，覆盖 discovery 隔离/水位/权限、全文兼容、Owner 融合、筛选包、CE 单窗、Owner 三态判断、完整分页、三模式、笔记证据、设置和 HTTP。
- 前端：TypeScript 通过；15 个组件文件共 87 项通过；Vite 生产构建 336 modules 通过并更新预构建资源。保留既有大 chunk 警告。
- 真实接口：实际 HTTP/socket 链路 `start → recall → assess-owners → recall-fulltext` 通过；真实浏览器设置保存/重载 2 项通过。
- Windows 升级：`test_deployment_workbench.py` 19 项通过，覆盖真实 `setup.cmd` 在扩展旧工作区上的预览、升级、重复升级、回滚、损坏拒绝和自定义内容保护。
- 测试目录：revision 125；877 个已发现测试、879 个 catalog 条目，0 未分类、0 缺失、0 错误。索引隔离、撤权/陈旧拒绝、派生重建不写规范内容和未经用户选择不全文补偿已进入 quick 基线。
- 8 个活跃 Skill 均通过 `quick_validate.py`；生成契约检查无漂移；76 个 memory/material-query Python 文件只读 AST 解析通过。
- `refresh-index` 和 `validate` 已执行，0 错误；首次收口校验中的本 Run `RESULTS.md` 未创建链接警告由本文件补齐，其他警告为既有历史链接或大模型文件提示。

`compileall` 首次尝试因既有 `__pycache__` 属主导致无法写 `.pyc`；改用只读 AST 校验，并由实际导入执行的 202 项 Python 回归覆盖变更模块。这是工作区权限现象，不是产品语法失败。

## 与开发共识核对

| 开发共识 | 实现状态 |
| --- | --- |
| 默认以压缩发现面找尽可能多的 Owner | 完成；独立 FTS/向量投影，不是全文索引 level 过滤 |
| 先按 Owner 融合，再交付少量互补筛选片段 | 完成；信号族单票、保留 provenance，通常 2–3、最多 4 窗 |
| CE 不直接处理完整文稿，超长不拖累整批 | 完成；512-token 命中中心窗与逐窗降级 |
| AI 一次判断一批 Owner，相关者再完整阅读 | 完成；三态 assessment，relevant Owner 全部当前正文稳定分页 |
| quick 小细节查询无需全文重读 | 完成；只使用实际交付发现片段 |
| 全库全文补偿由用户决定 | 完成；独立动作和按钮，无自动触发 |
| L0–L4 作为所有 Owner 的压缩/发现层级，长期 Owner 有自足 L4 | 文档和相关 Skill 已同步；结构缺口工具只做确定性判断 |
| 旧 Owner 发现缺口要实际修复或直接建索引 | 完成当前范围；三个 Owner 无正文缺口，直接重建，不制造修订 |
| 单独建立发现索引，实际减少默认索引面 | 完成结构隔离；本轮未测候选/延迟等收益 |

## 保留边界

- 按用户约定没有测 Owner 召回率、延迟、候选数量、CE 成本、上下文占用或错误联想率；功能回归不能证明检索质量或性能改善。
- 现有长期 Owner 中没有“非空 L1 检索说明但语义覆盖不足”的自然样本，因此没有一次真实语义修订案例；相关 Skill 已规定实际阅读、MEM CAS、回读和逐 Owner 重建流程。
- 升级验证在本机 Windows x64 隔离合成旧工作区完成，不是第二台物理机或真实业务验收。
- 本次没有发布、推送或科学结论复核。
