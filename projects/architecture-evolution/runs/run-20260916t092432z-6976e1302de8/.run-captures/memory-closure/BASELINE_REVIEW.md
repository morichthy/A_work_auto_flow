# 真实阅读计时：既有成果阅读与变化处置

审查者：Codex 子 Agent，AI 一致性自查。只读 `baseline-only` 已完成；没有执行 apply、reconcile、rebuild 或其他索引动作。本说明不认可尚未冻结的本轮数字；新测量以主任务最终 RESULTS.md、metrics.json 和三个 Run 固定元数据为准。

## 实际读取与基线

- Owner 前后 HEAD 均为 `COM-0b448366-3b80-49a1-94b3-7a93b47296e8`，generation 41，manifest `cf3b584147ce35eb01c40b8ecc70163afd567a5ebc185d7b941c0cb15427224f`；与上轮能力偏好收口 HEAD 相同。当前规范 MEM 没有该次收口之后的新提交，待归档的三个计时 Run 是本次新增证据。
- 完整读取当前 reader 文稿 r2：`baseline-document.json`。已逐块实际读完全部 prose、`reader-results`、`requirements-results`，不是仅看标题或检索摘要。`report.complete=true`、正文块无 source_issues。
- 完整读取 reader 概览 r2：`baseline-overview-record.json`；单元 r1、章节 r2、文稿根 r2 已保存独立固定 inspect 回执。
- 读取 `baseline-document-impact.json` 和候选清单。文稿包含 reader 与 settings 两个 L1；17个未覆盖 L1 属于此前架构、表示查询、重排、来源恢复及项目比较范围。本次不是全 Project 重综述，不将它们并入 reader 性能报告，不宣称全项目同步。

## 影响列表的实际判断

impact 的6条 NEW_REVISION 是3个不同目标经两条路径重复到达：设置文稿、设置单元和设置章节由 r1 演进至 r2。均来自 reader 原历史证据固定引用设置报告 r1；不是本次真实计时导致的失效。现行 reader 章节已明确旧依据为历史，并单独纳入 settings 单元 r2 的 requirements-results。

处置为 retain：保留原历史固定链及其版本提示，不能将历史基线机械切至新版。`report_version_hints` 中设置文稿 r1→r2属于同一原因。`uncovered_unit_ids=[]` 仅表示影响工具范围内没有新增未覆盖单元，不能与全文 coverage 的17个其他历史 L1混淆。

## 本轮建议的修改

1. reader L1同ID r1→r2：`reader-results`逐字保留，追加`latency-results`；三个失败/诊断Run都作为固定证据。失败是默认预算路径的真实结果，不因状态failed而排除，也不改写为成功。检索说明补充默认预算失败、放宽预算诊断和实际profile测量范围。
2. reader章节r2→r3：同一 reader unit 只引用一次，用有序`block_ids`选择历史及新增块；现有settings能力要求块保持其固定版本。过渡应区分“历史reader-results”“能力要求阶段requirements-results”“本轮latency-results”。
3. 概览r2→r3：追加真实链路阶段、耗时分解、partial覆盖、正文中data_url导致工具输出截断及未解码图像的限制；“已完成note/decide/handoff”不等于全文全部语义或所有候选已读。原限制“本轮没有重跑实际材料阅读质量/费用基准”必须加“能力偏好阶段”时点标签，避免与本轮真实计时冲突；当前阶段也应明确测量完成、优化未实施、非完整业务质量验收。
4. 文稿根r2→r3固定新section，标题范围保持reader报告、scope扩展本次计时诊断；来源和common_refs一致。原主context约90.7%字符体积下降仍只对应原合成情景，不被本轮耗时否定，也不能升级为新场景token、费用或时延下降。
5. 独立profile与正常计时分开：profile高调用次数提示授权/固定引用解析存在重复成本，但优化尚未实现。不得直接把profile的reauthorize比例当正常recall或handoff同等比例，也不得把工具等待/调用间隔等同模型推理。

## 尚待主任务完成

最终三个RESULTS/metrics与Run冻结后，主任务需实际检查上述新增数字、失败状态、原始回执和测量边界，再显式apply；保存后仍需完整阅读新文稿、概览、coverage/version hints与Owner HEAD。当前只完成基线阅读和维护建议，不宣称新成果已保存或全阶段已同步。
