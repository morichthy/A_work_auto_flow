# Owner阅读独立集成审查

2026-09-17。范围：reading_owner.py、reading.py、assembly.py、reading_snapshot.py、reading_catalog.py，以及ReadingSessions/CurrentReading/ReadingEvidence的公开交接。只读审查；未改后端、文档、Skill或规范memory。后端在并行迭代，以下按实际核对时状态区分，不能当完整安全证明。

## 已发现并直接通知后端的必须修问题

1. **预算省略note仍展示其出处，已纳入note的证据页反而为空。** 原source_candidates遍历全部非stale owner_notes，与handoff实际纳入集合无关；其status新文本也不满足ReadingEvidence的has_note/已记录理解过滤。已回读修复：handoff返回included_owner_ids，execute/snapshot据此过滤，candidate带has_note。实际纯函数复现：512预算、900字符理解，notes_count=0、omitted_note_count=1、included=[]、source_buttons=0、within_budget=True。该复测通过。
2. **Markdown副本隐藏遗漏。** write_snapshot原来仅写context_markdown，未输出value.gaps，Owner预算遗漏或未完成没有出现在current.md，而提示声称遗漏见下文。后端已通知补写gaps；需后端回归覆盖实际副本内容。
3. **图片缺少可展开映射。** ReferenceAssembler去掉figures二进制时同时去掉caption/index/ref映射；拼接正文中的figure:0在多个技术单元间冲突。已回读read.references包含figure index/caption/record_ref/block_ids/ref/expanded；后端正补唯一marker（record+局部index），应以最终代码/测试确认正文marker能对应该字段。仅扁平sources不足以验证图的身份。
4. **展开Run/Owner后未来版本闭包丢失。** expand_sources原contributors过滤排除了owner，随后root record的authorize_sources对owner只检查访问权限不检查native指纹；因此Run已展开、note引用后修改run.json，handoff可能继续返回旧理解。已回读修复：expanded owner进入contributors，reauthorize的owner分支调用reader.native；该行为应有实际Run变更/撤权回归。
5. **已选Owner没写note仍complete=true。** 当前纯函数复现：已有OWNER-1 note，另OWNER-2 selected=True，phase=finish且无其他gap，返回unnoted=1、complete=True、gaps=[]。已直接告知后端，必须把已选但未note加入明确gap；尚待其修复复验。不能用仅有计数字段冒充完整交接。

## 其他核对结论

- Owner模式使用OperationLedger，旧缺mode的会话继续原累计Ledger；旧start缺mode仍legacy，新模板显式owner_document。权限先can_access，再逐候选固定来源reauthorize；原scope ceiling不随设置扩大。
- 完整阅读按实际固定研究过程优先、报告回退；多个同类文稿仅选最新且报告gap，缺文稿真实记录回退也明确gap。packet不完整不能通过note的full_delivered前置检查。此为完整交付校验，不证明AI已理解全文。
- note全局窗口按问题/条件/最近决定与整份Owner note合并后计UTF-8字节保守估算，不截断公式。最终JSON中的诊断/metadata仍受单次工程output_chars控制，两者不是同一额度。
- 前端openSource沿candidate_ids并读取readings[0].packet；后端保留此兼容路径。证据页必须与实际纳入note集合一致，见问题1。
- Run按需展开调用reader.native返回原生登记正文，不能解释为读取README/RESULTS或自动生成完整研究报告。空结论/缺文稿必须保留缺口。
- listing的Owner note_count统计与旧notes分支区分；目录查看仍重新授权，不能用清单替代正文权限核验。

## 文档与Skill只读核对

AI_READING.md与material-query Skill当前精简版总体匹配新模板、新Owner read/note、delegate宿主边界、默认handoff note预算及legacy累计预算。没有发现旧mode被文档自动迁移的表述。

建议root在最终接口稳定后补一条精确图片说明：read.references的marker、caption、record_ref、block_ids与ref如何对应，source_refs必须复制其中固定ref；仅引用时不返回data_url，显式展开才交付图像。说明Run展开是固定原生登记，非自动完整总结。主要预算沿settings/context；legacy handoff的12000字符不可混称token。不要在映射修复尚未复验前声称所有图片与Run来源已完整核对。

## 验证边界

本审查执行了上述handoff/source_candidates合成纯函数复现并读了接口调用链；未运行全库扫描、未进行真实业务权限渗透测试、未以当前源码替代后端agent的完整回归结果。最终must-fix复验以其后续固定日志为准。

## 最终专项复核：规范/字节双指纹与未note完整性

本节更新上文问题4、5的最终状态，不删除此前实际发现与复现。

- `read_native_reference`首先用`reader.owner(ref.id)`检查同一Owner身份。Reader的权限来自可信ACL与不可变scope_ceiling交集，同时应用排除和当前restricted状态；替换sha256不改变ref.id/kind/revision/locator。
- `expand_sources`仍在调用helper前要求每个完整FixedRef的digest存在于该已交付Owner的sources；不能提供另一个Run或自行改版本/算法值来增加可读来源。
- MQ字节指纹分支直接reader.native(ref)。MEM规范指纹分支把临时调用hash置为当前Owner字节指纹后仍调用reader.native：真实文件路径受safe_path约束，读取字节SHA256与当前登记一致，解析后再次校验当前敏感性及来源闭包；最后evidence.fingerprint(native)必须等于调用者原固定规范hash，失配返回STALE。并未仅信任缓存native_data或跳过读取。
- expanded owner仍保存在contributors，后续reauthorize调用同一helper。代码检查未发现双算法绕过撤权、换Run或内容版本检查的路径。规范算法既有规则会忽略review/review_history/finalization/finalization_history，这表示这些事件不改变规范内容版本，不能据此宣称科学结论复核通过；当前权限检查没有被忽略。
- Run展开现在仅提供已存在title/conclusion/limitations摘要；无conclusion明确gap，未自动读日志。这更新上文“返回原生登记正文”的早期实现说明。

实际专项测试（根目录，2026-09-17）：

```powershell
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_reading_owner_document.py -k 'test_declared_run_reference_expands_summary_only_and_rechecks_version' -v
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_reading_owner_document.py -k 'test_finish_with_selected_unnoted_owner_remains_partial' -v
```

第一项1/1通过，33.988秒，exit 0：实际MEM规范指纹Run引用按需展开，修改Run结论后handoff返回STALE、value=None。第二项新增puretest 1/1通过，0.000秒，exit 0：selected未note返回unnoted=1且complete=False，并报告尚未保存笔记。上文问题5已修复，不再是未完成must-fix。

本轮未发现新增必须修问题。授权边界结论来自调用链核对，专项实际测试证明的是Run内容变更拒绝与未note完整性，不夸大为双算法全部组合或所有撤权场景已独立穷举。
