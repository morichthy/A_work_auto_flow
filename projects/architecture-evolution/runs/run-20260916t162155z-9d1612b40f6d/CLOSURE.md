# 预算逐笔诊断收口

本Run的实际召回失败（rejected/BUDGET），工程计量一致性检查通过。固定结果见RESULTS.md；不代表产品修复、全库验收或AI阅读/note完成。

## 固定证据

公开登记11 inputs、24 artifacts共35项指纹通过；99个当前Python源码与ZIP/manifest核对一致。成功扣费合计99,986与账本一致；33次part=17成功+6去重+10预算省略，唯一尝试正文8,634。42条融合诊断matched_text固定引用/文本hash均核对到先前搜索输出。回执与检查见.run-captures/freeze-verification.json。

固定run.json SHA256：1598f8f34580b6af53835a2ca52d034ddd45f347a700976b7a11a9e4b54f0eb7。其后文稿维护回执另存，不再变更Run身份或已登记文件。

## 归档纠错与并发维护

最初capture_memory_baseline.py将记录和组装文稿都命名document.json，不可覆盖保护正确拒绝，未生成完整manifest。原7个已登记基线文件和脚本保留。辅助Agent早先声称“基线回执全部完成”不准确，以实际文件/命令结果为准。第一次重采复现同名问题；第二次将document-assembled.json分开保存，得到generation45的完整基线。

期间另一任务经generation45→47新增阅读笔记/工作台修复单元、章节，并更新同一文稿与概览到r4；不能用旧r3覆盖。主Agent接管，确认没有遗留归档Python进程，读取最新基线baseline-current（generation47），完整阅读旧三块、过渡正文、概览以及新增工作台章节；新内容与本次预算诊断不同，保留原固定引用和验证边界。最初主Agent恢复尝试因HEAD变化拒绝、旧同名head-before回执拒绝，均发生在本次提交前。最终采用独立root-apply回执目录。

本次只追加同一reader技术单元的budget-trace-results、更新原reader章节及概览/文稿引用。另一任务的章节/单元和正文保持；17个其他历史L1不属于本次范围。基线11条impact是历史设置/reader依据经不同路径抵达，仍按历史语境保留，不机械替换所有旧引用。输出预算结论以本次逐笔trace为准，旧三Run数字保持不变。

## 最终回读与校验

本次从已实际重读的generation47开始，以公开预检/CAS提交三批，generation48/49/50均save_status=committed、index_status=indexed。结束HEAD为COM-d6b78fdc-f63e-4517-96e5-9f73dbe3a888，manifest ce6d3b606e5bf55ccd22ce0cb912a8bcdbb1627872c2cdd157b4e54a2ca7916f。

| 记录 | 最新版本 | record_hash |
| --- | --- | --- |
| reader技术单元 MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b | r3 | 09d72b77690d58ddd07ad5c86b84f970de0d8b2e7ee6e0a178aee1614f8c1472 |
| 原reader章节 MEM-50f66b7c-7953-5715-8b70-5ae7705176ab | r4 | 62ce88c050451a7a031bff6b9d9a59efc72fa4215f7a683df5fc78dabcfb2b1e |
| 概览 MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155 | r5 | 93a8827bb9163f9f217a475f5d902e70153c2a4236fa3c486908a6806a9ae1a4 |
| 文稿 MEM-bd121869-a0b9-59e3-af23-8e8675374a63 | r5 | dc93c95f5c217f8b18b7f4f1d91e7cfedf9c1422b3ea18101b97c072f071b16b |

主Agent已完整阅读基线旧三块、全部过渡、概览及并发新增的工作台章节，实际读取最终组装结果：complete=true、两个章节无source_issues。基线9段正文在最终11段中全部原样保留，新加诊断正文与已阅读RESULTS.md逐字符一致；新增过渡与最新概览另行实际阅读。上述程序比对用于验证保留/纳入，不替代AI正文审查。报告、概览和工作清单均明确召回失败/trace核对通过/产品未修复。

最终13条impact路径和3个版本提示对应历史设置依据、reader r1/r2历史引用；在已阅读的历史语境中保留。另一任务的新章节保留固定r1引用；17个未覆盖L1维持本次范围外，不宣称全Project历史同步。完整回执在.run-captures/memory-closure/root-apply/。

refresh-index退出0；validate退出0，0错误/21既有警告。主Agent最后再次核对35项已登记指纹与Run SHA256，全部一致；只新增Run仪表/记录，未冒称执行产品回归或Windows升级验收。最终HEAD回读仍为generation50。

**本阶段完整成果已同步（范围：每路10/重排30的真实召回逐笔预算诊断；文稿r5；主Agent AI一致性自查）。** 此标记不是科学结论复核或性能修复完成。
