# 写作规范与固定文稿盘点

2026-09-17，AI 自查。本次只维护现行规范并诊断历史引用；没有提交或改写规范 memory、旧 Run 或旧文稿。软件与实际 AI 验证由本 Run 的其他回执分别记录。

## 现行规范

已阅读并修改、回读 material-query、work-loop、association-exploration、consolidate-results 四份方法源，以及 docs/AI_READING.md、docs/RESEARCH_RECORDING.md。note 只承载材料中对搜索有用的知识，允许保留材料自身研究演进，不重复当前搜索问题，不写 reader 操作的下一步、理由或执行结果。材料的有据建议用“可选的下一步建议”；主 Agent 制定联想问题和关键词，reader 按给定文本检索并报告线索。

L0–L4、Run 和独立文稿关键判断须就近引用固定依据并与文末来源对应。已有契约支持块级关系才使用 evidence_refs，不虚构字段；历史无具体位置时保留缺口，不按来源列表顺序猜句级或块级映射。公式保持可解析 LaTeX，实际依据和未读来源分开。

本分工未修改六份主文档或软件代码。PowerShell 普通写入两份 docs 曾被文件权限拒绝，改用 apply_patch 及获准的范围内写入完成。git diff 检查在当前受限 shell 返回非 Git 工作区，未算通过；文本回读已完成，整体 Git/软件检查由主任务执行。

## 真实 L1 引用诊断

通过公开 memory inspect 完整读取 RES-FLOATING-POINT-SUMMATION 的 MEM-c52df8fb-ca9e-53a7-a49b-342592884a50 r3，record_hash 为 `c9ab320069397e5219eca068d85e33fd7636368db676026a7f9d3f1f68863c20`。

- body_markdown 为空，正文在 inputs、trace、results 三个稳定块。三块均没有 MEM/RUN/SRC 显式 ID，也没有编号引用 `[n]`。
- 每块只有 block_id、markdown、requires_block_ids、role，没有块级 evidence_refs。记录级 sources 和 payload.evidence_refs 各有 10 项，无法确定每条句子的支持来源。
- “共同方法”“独立方法章”只是自然语言，未给出具体位置。不能据此猜成某个方法记录。
- 唯一可确定的图映射在 results：`figure:0` 对应 payload.figures[0]，固定来源为 SRC-SUMMATION-FIGURE-R01，SHA-256 `043d9bc1c51b300a97a2b915b5c53af73553f1d726b9936c9315a074220fbea8`。

因此界面可以展示记录级依据和上述图引用，但不能宣称已经恢复其句级引用。已向主 Agent 与后端 Agent 同步；未修改这条历史记录。

## r7 完整阅读与影响检查

公开 outline/document/document-impact 请求固定 Owner PRJ-ARCHITECTURE-EVOLUTION、文稿 MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r7。基线 HEAD：COM-71d22958-3510-4d7d-8a3f-2948ed45ef92。请求及原始 document 回执暂存 `.local/writing-report-request.json`、`.local/writing-report-response.json`。

完整读取两章：MEM-50f66b7c-7953-5715-8b70-5ae7705176ab r6（子Agent阅读与主Agent交接）及 MEM-a042188a-244a-5d15-843e-359b7d7f87f6 r1（阅读笔记可读副本与工作台入口）。初次重复 JSON 正文输出截断，随后通过公开 document 回执的 prose/resolved_blocks 提取阅读正文，并单独完整补读 latency-results、budget-trace-results；没有把截断当作完成。

document_source=independent、report.complete=true、missing=[]。document coverage 包含 3 个 L1，另列 17 个未纳入 L1；impact 的 uncovered_unit_ids=[] 只表示其基线/关注关系未发现新增单元，不能推出全 Project 已覆盖。scientific_review=not_evaluated。

impact 返回 15 条 NEW_REVISION 路径，归并后是下列 6 组版本差异。两章均被部分路径列为受影响；引用没有自动替换。

| 固定依据 | 旧→当前 | 处置建议及理由 |
|---|---|---|
| 委派/计时单元 MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b | r1→r5 | r1明确用于最初委派和固定low历史；保留旧证据，现行要求另写新增段 |
| 同上 | r2→r5 | r2对应当时真实计时与预算失败；不能把后来的Owner阅读预算行为倒填为旧实验 |
| 同上 | r3→r5 | r3对应逐笔预算trace及对前次推断的校正；r5新增Owner阅读并修正RS ID，不使旧实验消失 |
| 设置报告 MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152 | r1→r2 | r1是当时尚无子Agent阅读的固定设置基线；当前能力偏好已有独立段落，保留基线说明 |
| 设置技术单元 MEM-472e4d18-f18d-5d13-84e3-28d3d5ae211a | r1→r2 | 旧版通过历史设置报告间接引用；新能力偏好单元r2已经在正文编排，不能只因提示重复替换历史来源链 |
| 设置章节 MEM-7df3c088-504b-532d-ad74-b459bed75ba4 | r1→r2 | 同属旧设置报告的间接固定链；需要重写当前设置报告时再实际审查，不机械修改本报告历史依据 |

这些建议基于本次读到的 r7 正文、固定引用与 impact；没有另行宣称所有历史来源逐字复核或科学认可。

## r7 之后尚未同步的范围

已读以下 Run 的完整 RESULTS（最后一项读 README），并与 r7 正文核对。它们是当前范围的重要新增成果，但尚未编入本报告，不应因 impact 无新单元就忽略。

| Run | r7 后的新增内容 | 本轮建议 |
|---|---|---|
| RUN-20260916T195725Z-16CDCD28570D | reader 默认提取/同任务自查及显式来源ID漏登/未知拒绝；23项Owner、10项委派和合成首稿验证，非真实RS端到端 | 将当前要求写入现行规范；后续文稿新增质量章节，保留验证口径 |
| RUN-20260916T200528Z-E244B6EE59A3 | standard/associative/quick、综合note与策略切换；93项阅读回归及后续13项复验、合成AI与升级 | 后续文稿新增策略章节；其“reader生成子问题”是当时历史，本轮改为主Agent制定，不改旧Run |
| RUN-20260916T201935Z-6C6692A35C2A | 叙事深度与JSON/Markdown职责解释；固定样例v2和真实召回失败仍保留 | 后续文稿区分固定样例通过与实时RS失败；当前不宣称存储迁移 |
| RUN-20260916T212839Z-337776B112FC | 最近24小时问题选择、展示与强证据核验分开、公式/编号/详情导航 | README明确最终数值以RESULTS为准，本分工未据README复核最终软件数量 |
| RUN-20260917T021448Z-BC1AAF379A2C | 当前六项修复及写作/引用职责明确 | 待主任务固定最终软件/AI证据；本文件不是实施成功回执 |

当前交付聚焦六项修复及现行 docs/Skill，不扩展为重写全 Owner 历史文稿。建议未来同步时新增现行行为说明与各阶段固定证据，保留上述历史块，更新文稿范围和概览并全文回读。本次 **历史规范报告完整成果待同步**，未进行 memory commit，不标记全阶段完整同步。
