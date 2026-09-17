# 三种阅读策略后端验证

2026-09-17，子任务 reading_backend。全部输入为隔离合成材料；这些软件测试不证明真实AI理解质量或业务结论。

## 先红后绿

先新增 `automation/tests/test_reading_three_modes.py` 的四个策略边界测试，再实现 `reading_strategy.py`。首次执行因测试未加载fixture而找不到material_query；补齐fixture导入后再次执行，明确因不存在reading_strategy失败，之后才开始实现。

命令：`automation/python.ps1 -m unittest discover -s automation/tests -p test_reading_three_modes.py -v`。

- 初版四个纯策略边界测试全部通过。
- 初版八项集成中一项因测试调用了强制成功的fixture recall helper，无法断言预期拒绝；改为直接call后八项通过，37.785秒。
- 补到十一项后跨Owner测试发现合成Owner的research_process存在真实交付缺口。拒绝整稿ref是正确行为；改为引用实际交付正文parts，并使综合稿允许实际已交付部分正文，仍不放开standard Owner note的完整交付要求。
- 最终十三项全部通过，61.974秒。随后仅补综合稿依据Owner映射：无candidate的expanded file/Run以实际Owner progress记录计数，保存basis_owner_ids。主任务将统一跑reading整组覆盖最终快照。

其他定向回归：

- `automation/python.ps1 -m unittest discover -s automation/tests -p test_reading_owner_document.py -v`：23项通过，172.845秒（实施中间版本）。
- `automation/python.ps1 -m unittest discover -s automation/tests -p test_reading_delegation.py -v`：10项通过，49.186秒，含既有真实HTTP兼容。

## 实现范围

- `reading_strategy.py`：策略配置与旧RS只读兼容、联想真实查询与轮数、逐条判断、实际接受来源、跨Owner综合稿及累计Owner限制。
- `reading.py`：新请求字段、CAS/幂等动作接入、默认策略、派生快照更新。
- `reading_owner.py`：quick片段出处/判断/分页/笔记，实际正文交付refs，线索引用合并，综合稿优先交接和失效提示，Owner额度和全文门槛。
- `reading_delegation.py`：宿主brief传递策略，明确quick不自动读全文。
- `reading_catalog.py`：综合稿计入笔记数量。
- `cli.py`：三个新动作注册。`api.py`与`workbench_app/web.py`原有reading/materials前缀动态派发已覆盖新动作，无需改写。

## 关键边界

mode继续只表示legacy/owner_document存储兼容；strategy为standard/associative/quick。旧RS缺字段按standard、association.enabled=false解释，不读取设置追写旧记录。configure不改变phase、原query、授权、账本、历史；ask_user仍不能继续recall。

quick仅接受实际回执中的固定片段，逐条assessment绑定来源指纹；新增片段需重新判断，撤回判断使旧quick笔记及综合稿失效。标准模式仍完整交付才允许Owner note。quick note后可继续page同Owner材料；全文读取与Owner选择分开记录。

综合稿仅能引用完整正文根、实际交付parts、明确expanded来源或quick接受片段；声明引用清单不等于已读。绑定Owner底稿和接受来源指纹；变化后不能静默交接。context.max_owners按累计选中Owner并集限制read/note/synthesize；切策略不会重置。

exploration_clues为对象数组，每项text/reason/sources/next_query/limitations；固定来源并入note.sources参与后续校验。软件校验不能识别自然语言中没有显式来源标记的虚假论断，实际reader必须自查语义和阅读覆盖。

## 实际AI验收追加修正与最终回归

本reader已实际完成同RS标准底稿续接→一轮联想→B完整阅读→跨Owner综合→finish/handoff，以及独立quick的recall→page→4条逐条判断→2份片段note→finish/handoff。见同目录 `AI_CHECK.md`；主Agent已分别消费最终handoff，不加载全部原文。

- 标准/联想最终：`RS-123e4567-e89b-42d3-a456-426614174000` r11，synthesis_included=true，综合稿4817/16000估算字节，partial缺口保留。
- quick最终：`RS-123e4567-e89b-42d3-a456-426614174001` r10，2份note、7596/16000估算字节；reading-read调用为0，实际2接受/2拒绝，固定block定位和未读全文限制保留。

真实AI执行发现两处产品缺陷并修复：

1. 已完整阅读文稿根引用可用于note，却被联想clue_sources误拒。reading_owner仅在full_delivered为真时补入root_refs，继续拒绝未交付来源；强化既有 `test_association_real_query_and_round_limit`，测试数量不变。13项通过98.848秒，`association-root-retest.log`。
2. quick start仍返回提示reading-read的通用文案。reading.py改quick专用逐条assessment与片段note指引；强化既有 `test_cross_owner_synthesis_and_quick_owner_limit` 的start回执断言。最终13项通过51.694秒，`association-final-retest.log`。

最后两项变更仅后端阅读校验和启动指导，不改UI、安装器、依赖或模型。此前主任务全reading93项已通过；本轮局部修正采用上述相关13项复验，没有机械重复全组。全部结果仍是合成软件/实际AI流程验证，不等于现实科学或业务正确性。
