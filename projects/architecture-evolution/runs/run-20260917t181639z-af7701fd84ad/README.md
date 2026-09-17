# RUN-20260917T181639Z-AF7701FD84AD：实现Owner压缩发现索引与互补筛选包

## 问题与成功标准

- 问题：把既定的 Owner 压缩发现方案从文档目标实现为可调用、可升级、可验证的软件能力，同时保持旧会话、权限、固定版本和预算边界。
- 假设：独立 discovery 投影、Owner 级融合和互补筛选包可以作为现有全文检索之外的明确默认路径；全文补偿必须由用户显式触发。
- 成功标准：独立索引与水位、Owner 融合、筛选包、CE 单窗处理、Owner 判断、显式全文补偿、旧 Owner 缺口/重建接口、设置和工作台入口均有实现及针对性测试；Skill 和现行文档与代码一致。
- 本轮不评价：Owner 召回率、延迟、候选数量收益、CE 成本、上下文占用和错误联想率。

## 输入与范围

- 数据资产/版本/指纹：当前工作树（起始 Git HEAD `ffbad496c7b902c667b4d7fa031b29a68e05d28b`，工作树已有其他未提交修改）；固定计划 `projects/architecture-evolution/plans/owner-discovery-retrieval-20260918.md`。
- 时间窗与字段：Owner 当前 HEAD；发现面限 Owner 元数据、L4、L3、L2 紧凑结构和 L1 `retrieval_description`。
- 排除条件：L1 blocks、完整文稿、L0、RS note 不进入 discovery 投影；不自动修订旧 Owner 的语义内容；不执行检索效果评估或对外发布。

## 方法与参数

先固定改造前回归，再按独立 discovery 投影、Owner 召回、筛选包、产品入口顺序实现。并行修改按文件边界拆分，最终由主 Agent 做接口整合、回归、升级与文档/Skill 核对。

## 结果与验证

- 改造前基线：`test_memory_index`、`test_material_recall`、`test_reading_query_plan`、`test_reading_reranking`、`test_reading_reranking_integration`、`test_reading_owner_document`、`test_reading_workflow` 共 104 项通过。计划原先的模块名命令因 `automation` 不是 Python package 而失败，已改用逐文件 discovery。
- 最终 Python 定向回归 202 项、前端组件 87 项、真实 `setup.cmd` 扩展旧工作区 19 项、浏览器设置 2 项和真实 HTTP/socket 阅读链路均通过。
- 测试 catalog 审计 0 未分类/0 缺失/0 错误；8 个活跃 Skill 校验通过；三个长期 Owner 的独立发现索引已重建并达到词法/向量 indexed。
- 完整文件、验证明细、共识核对和限制见 [RESULTS.md](RESULTS.md)，旧 Owner 重建见 [DISCOVERY_REBUILD.md](DISCOVERY_REBUILD.md)。

## 结论、限制与下一步

- 结论：独立 Owner 发现、Owner 级融合、互补筛选包、CE 单窗处理、三态判断、完整分页、quick 边界、显式全文补偿、工作台入口和旧 Owner 重建均已完成。
- 限制：本轮不评价召回质量、延迟、候选数量、CE 成本、上下文占用或错误联想率；本机升级与功能回归不等于第二物理机或真实业务验收。
- 当前工作树包含用户先前工作；本 Run 只归纳本次实际修改和验证，不宣称其他变化由本 Run 产生。
