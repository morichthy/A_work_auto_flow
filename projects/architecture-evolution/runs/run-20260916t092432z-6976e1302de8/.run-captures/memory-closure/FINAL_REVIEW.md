# Reader计时成果固定回读与一致性检查

审查者：Codex 子Agent，AI一致性自查。三批公开 validate-draft/commit 成功，退出码0；没有修改已冻结脚本、RESULTS、metrics或旧Run，也没有使用修复wrapper。

## 保存身份

| 内容 | 固定版本 | record_hash |
| --- | --- | --- |
| reader技术单元 | MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b r2 | 1df804130728e6619ebfb2c63920cb51e4875769265ad7b00fac3d7add52efe9 |
| reader章节 | MEM-50f66b7c-7953-5715-8b70-5ae7705176ab r3 | d526670cbb8f2e4ec5b5cc6e23db19089184addd16199f7b58873be4da037d89 |
| reader概览 | MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155 r3 | 288d3061e4c5f85e91b3a4b296ba2284822fc90904f645a21210103088f6e613 |
| reader完整文稿 | MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r3 | c0da626069a72099223023d62da266e4e653d1a8c0ea02a2f950e067749f8df2 |

起始HEAD generation41 `COM-0b448366-3b80-49a1-94b3-7a93b47296e8`；终止HEAD generation44 `COM-03105bc0-e652-405f-82b7-4273317b8ec6`，manifest `3414dd5cb01beb39876c4f3611e0d86ae8a7c55aa1667899368d8852db920459`。三批回执均committed/indexed；最后FTS、vector均indexed，indexed_generation/vector_generation/target_generation均44，error=null，无待补偿项。

## 实际阅读全文与概览

已逐块完整读取 `final-document.json` 的全部prose与resolved_blocks（历史reader-results、新latency-results、历史requirements-results），以及 `02-section-overview-overview-readback.json` 的全部概览字段。最终文稿 `report.complete=true`。原reader-results与基线逐字比较相同，原context字符减少约90.7%仍限原合成场景；新计时470.011秒墙钟和71.932秒dispatch使用不同边界，不相加。默认/限流失败、放宽预算和暖上下文诊断、图像data_url截断与未解码、profile干扰和优化未实施均在新块保留。

概览已给“本轮没有重跑实际材料阅读质量/费用基准”加能力偏好历史阶段标签；current_stage明确本次计时完成、两次失败、最小诊断闭环仍partial及优化未实施。正文内历史阶段和新计时有过渡说明；后续能力要求历史块保持原版本，并非将其旧验证当本轮新执行。

## 旧引用与覆盖处置

- `report_version_hints` 有reader unit r1→r2及设置document r1→r2两项：保留。reader r1在历史prose/概览支撑原实现和字符测量；新unit r2已实际展开reader-results及latency-results。设置r1支撑原reader阶段基线；设置r2的requirements-results已单独展开。提示不是遗漏新计时正文。
- `final-document-impact.json` 的7条NEW_REVISION由4个不同目标组成：原设置document/unit/section的6条两路径提示继续保留，新增reader unit历史引用提示1条。均为已审查历史依据，不机械替换；当前展开关系已指向新reader单元及章节。`uncovered_unit_ids=[]`、`scientific_review=not_evaluated`。
- `report_coverage` 仍包含reader和settings两个L1，17个其他历史L1未纳入。基线已逐项列名，其范围为架构、表示查询、重排、来源恢复和项目比较；本次计时未修改这些材料，也不借本轮实验重评其科学结论。保留未覆盖，不声称全Project同步。

本阶段完整成果已同步（范围：本次reader真实计时测量；文稿r3、概览r3、技术单元r2；AI一致性自查）。这不证明材料覆盖完整、优化已完成或科学复核有效；主任务仍应结合当前工作清单与最终工作区校验收口。
