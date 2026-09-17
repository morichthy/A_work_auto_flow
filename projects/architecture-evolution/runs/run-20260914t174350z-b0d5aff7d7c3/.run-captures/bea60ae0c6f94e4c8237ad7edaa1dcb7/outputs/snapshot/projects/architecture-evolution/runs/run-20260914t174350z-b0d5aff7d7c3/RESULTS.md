# 中英查询计划与术语扩展：实施结果

日期：2026-09-15。Run：RUN-20260914T174350Z-B0D5AFF7D7C3。功能已实施；软件验证、实际AI合成自查和业务质量分别记录。

## 已交付

- reading-recall接受少量AI生成等义变体、领域、语言依据和保护项，保留原问题及独立身份通道。词法用紧凑词项，dense用完整语句；按语言补同义词，关联单跳低权重检索。
- 每层按加权RRF融合，按固定记录修订/指纹去重，保留命中块及query_plan_id/query_sources。来源诊断压缩为定位字段，完整输入留在coverage.query_plan。
- 词库为retrieval/query-terms.json，含8条信息检索领域种子；用户按实际材料维护领域、中英词、别名、关联词和出处。公共模板单独保存，只在缺失时补种；用户词库不随公共包分发，升级保留已有内容，rollback可恢复原不存在状态。
- material-query规则要求技术/明显文献依赖或可靠英文来源时补英文词与句；AI做语料语言、等义性和条件核对，程序不自行翻译、不将关联当成科学支持。候选条件保持pending，实际判断和依据写阅读笔记。
- 新增计划/诊断消耗原输出预算；续页固定原计划和词库指纹，不通过重建RS重置预算。实际自查发现CLI在value=null错误回执下崩溃，已修复为结构化JSON与非零退出。

## 软件验证

| 检查 | 实际结果 |
|---|---|
| `unittest discover -s automation/tests -p test_reading*.py -q`（最后CLI用例加入前） | 23项通过，84.357秒；含8项新增双语/词库/来源/续页/预算用例 |
| 后补公开CLI预算错误回执用例 | 1项通过，54.827秒；真实子进程输出BUDGET、value=null、非零，无traceback |
| `test_material_recall.py` | 16项通过，42.354秒；固定版本/预算/权限/来源降级等回归 |
| `test_deployment_workbench.py` | 18项通过，163.478秒；真实Windows setup预览、升级、重复升级、恢复、完整保护清单及词库补种/恢复，见stderr日志 |
| 生成类型检查 | generate_types.py --check：passed，无漂移；通用QueryRequest与前端未改 |
| 测试清单盘点 | 9项新增测试已登记，catalog r76；665个发现项，无未登记或缺失；五项既有相关基线复审并保留 |
| 工作区校验 | refresh-index完成，validate为0错误、8警告；均为既有历史快照中的相对链接警告 |
| 发行属性 | 用户词库export-ignore已设置；公共模板可发行且明确LF |

合计58项软件测试通过，不把实际AI自查或静态盘点重复计入。最后CLI修正仅处理错误回执，相关单项补测通过；此前升级测试后未再修改部署逻辑。未运行全库回归、第二物理机或真实业务验收；已知冻结B01问题未在本轮改写/重验为通过。阅读与基础召回时长来自实际工具输出，升级完整日志保存在本Run。

## 实际AI自查（合成，非独立业务评测）

通过公开CLI建立RS-97a3e089-e45d-46d1-a2ff-2cf6292f6c96，范围仅RES-MQ-A；固定合成原文身份见ai-fixture.json。AI填写中文问题、英文等义句、领域、来源依据和保护项X200、v2.1、≤0.5 mm。词库命中query-expansion/cross-lingual-retrieval两项，关联路独立执行。

首轮未接入向量模型，返回partial并报告dense降级；AI随后reading-read完整读取两份英文材料，在两次reading-note中实际核对：v2.1符合合成查询方法条件；v2.0版本冲突且方法会丢失数字条件，不能作为直接答案。注意“保留≤0.5 mm的查询条件”不证明实际设备达到该误差，X200为明示虚构系统。

随后借用本机离线模型建立隔离向量索引（22个点），同一RS记录expand并沿原范围/预算重查。最终回执ai-recall-vector-result.json显示：4次实际编码、128输入token，累计候选消费28、输出字符42020；技术层v2.1排第一、v2.0第二，命中同时包含中英dense/lexical及related来源。另返回两条反馈控制主题短材料，AI阅读后判断与本问题无直接关系，不采纳。结果仍为partial，明确报告部分候选因范围、来源或版本省略；不能将它改写为全库覆盖。

源码最终诊断计量加强前的首轮回执保留当时完整query_sources；第二轮使用压缩来源字段并计量。两者不能直接作为延迟/输出开销的严格A/B实验。

最后reading-view --markdown导出超过同一RS的80k累计输出预算，旧CLI错误处理产生过AttributeError。最小修复后相同会话返回明确BUDGET JSON（ai-view-budget-result.json），未抬高预算、未重建会话绕过。AI_READING_SNAPSHOT.md是该次失败留下的空文件，不是成功导出；可核对ai-note-good/wrong请求、完整读取回执和本摘要。该场景表明多轮诊断/回看仍有上下文成本，需在真实任务中按需阅读，不宣称已解决所有效率问题。

## 维护与限制

已更新README、ARCHITECTURE、CORE、docs索引、AI_READING、MATERIAL_QUERY、MEMORY_STORAGE_EXPLAINED、UPGRADE_TESTING、DEVELOPMENT_HISTORY（D25）、material-query Skill与QUERY_TERMS。DOCUMENTATION_MAINTENANCE、TESTING已核对，现行规则无需更改。通用MQ/前端未新增自动翻译，使用新策略走AI阅读入口。

种子覆盖范围有限，后续每次查询按实际语料维护更多专业术语；无匹配就显式留缺口，不能假装已获得相关扩展。真实召回率、错误关联、延迟和上下文成本仍需固定业务题集检验。没有更换模型/依赖、外发内部材料或发布Release。

本Run最终run-execute只负责固定已发生回执和源码快照，其成功不替代上述软件测试或业务复核。复核状态保持not-reviewed；首次夹具路径被隔离规则拒绝、两次错误的--root调用、CLI回执故障及测试调用修正均保留为开发经过，未被当成业务失败或隐去。
