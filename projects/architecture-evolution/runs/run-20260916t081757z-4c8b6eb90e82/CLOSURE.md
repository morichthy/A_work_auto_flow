# 能力偏好配置收口

2026-09-16，Codex AI一致性自查。功能、验证与文稿更新完成；没有推送或发布。

## 固定版本与全文检查

起始HEAD：COM-ac1bd612-307a-49e1-a9d1-703f4781a032，generation38。
结束HEAD：COM-0b448366-3b80-49a1-94b3-7a93b47296e8，generation41，manifest cf3b584147ce35eb01c40b8ecc70163afd567a5ebc185d7b941c0cb15427224f。

| 成果 | 本次固定修订 |
| --- | --- |
| 设置技术单元 | MEM-472e4d18-f18d-5d13-84e3-28d3d5ae211a r2；e421bec016052de61a0a00987c55a1de43af44f4a5b96939ba0b258f0ddf115f |
| 设置完整文稿 | MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152 r2；72e03d5cec22fe9581650625d2043750cd44e4a0763bd07423150cf64eba9904 |
| 委派完整文稿 | MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r2；c73493f68b64d93112b50f46fbf5d9c4365bfd6186bca9916a1994f471cb82cc |
| 设置概览 | MEM-67e69e5f-8de7-5c24-b8bc-eb41299f8eaf r2 |
| 委派概览 | MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155 r2 |

两个章节亦沿用ID更新到r2。完整ID/hash见memory-update-v2/identities.json；三批均committed/indexed，FTS与vector均generation41、error=null。原委派单元MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b r1保留不变。

主Agent实际阅读全文：settings-document.json与reader-document.json中所有prose及resolved_blocks；完整读取两份r2概览和两份document-impact。两份文稿document_source=independent、report.complete=true。新配置字段、默认/自定义优先、off/无宿主回退、旧文件读取兼容、私人设置发布边界、测试数量与失败复验均与现行实现/结果一致。旧性能、真实reader与压缩数字明确标历史，未扩展为本版本或科学验证结论。

## 变化处置

- 设置单元r1→r2：保留原settings-results字节，追加requirements-results，绑定本次固定Run；原阶段Run及固定来源保留。
- 设置章节/文稿r1→r2：同一unit的两个块合并在一次unit引用中，按顺序完整交付；概览保留r1历史引用并新增r2现行引用。
- 委派章节/文稿r1→r2：保留旧reader单元及历史证据，明确旧固定low只是历史行为；追加设置单元r2的新能力配置块；概览同样补入现行要求。
- 设置impact为空。委派impact报告6条路径提示，归并为3个既有历史依赖（设置文稿、设置单元、设置章节r1均已有r2）；逐项保留旧引用，因为它们支撑前阶段固定验证。当前章节已新增r2现行依据并标明历史范围，不能把历史Run的固定源静默换成后来版本。唯一report_version_hint是设置文稿r1→r2，同此理由保留，不是遗漏当前配置。
- 设置全文未覆盖18个其他L1；其中委派L1由其专门文稿覆盖，其余17个历史单元不属于本次设置能力扩展。委派全文未覆盖同17个历史L1。两份impact均uncovered_unit_ids为空，不据此宣称全Project历史已经同步。

## 保存过程与最终验证

辅助记录脚本先将record schema4误作CommitRequest版本，预检拒绝且未提交；补充v2脚本改用请求版本3，保留记录各自版本。随后章节预检拒绝同section两次引用同unit；第一批已保存，第二批尚未提交，原失败请求另存。v3补充脚本合并block_ids并复用第一批，三批最终均成功。第一次v3启动因隔离Python不自动加入脚本目录而导入失败，改用显式importlib文件加载后完成。未改写已登记的原脚本、旧Run、失败请求或已成功的技术内容；补充脚本/回执由closure-manifest单独固定。

本Run登记50个产物与2个输入，484份受控源码进入快照；原始测试失败及复验同时保留。最终refresh-index与validate通过：0错误、21既有警告（历史断链及本地重排模型大小），见final-refresh.log/final-validate.log。校验不代表旧科学结论通过。正式工作区仍无workspace-settings.json，默认值由程序提供；所有测试偏好写入隔离工作区。

本阶段完整成果已同步（范围：子Agent能力偏好配置及其对设置/阅读委派两份现行报告的影响；文稿版本：上述r2；AI一致性自查）。尚未公开发布，第二物理机、其他宿主模型可用性和真实业务质量/费用仍按RESULTS的限制保留。
