# 阅读笔记与工作台入口成果收口

2026-09-17（Asia/Shanghai），执行/一致性审阅者：AI，codex-reading-note-closure。范围仅本轮阅读笔记 Markdown 派生副本、授权兼容与会话发现、当前笔记、定向证据及主题导航；不代表全 Project 历史成果同步或科学复核。

**本阶段完整成果已同步（范围：上述 UI/storage 修复；文稿 MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r4；AI 一致性自查）。**

## 保存与固定版本

起始 HEAD：COM-03105bc0-e652-405f-82b7-4273317b8ec6，generation 44。结束 HEAD：COM-620058f3-4a6b-44b1-98cd-e9fd7f8dd967，generation 47。三次 commit 均通过公开预检/提交，保存状态 committed；没有直接修改 HEAD、commits 或旧 Run。

| 记录 | 新版本 | record_hash |
| --- | --- | --- |
| 新 L1：MEM-39924234-1937-5c36-bbf2-cf8d9600b0c9 | r1 | 850077171bea9e4d4b5c585ce9354058830b93a7c87f7bedeeab705043425183 |
| 新章节：MEM-a042188a-244a-5d15-843e-359b7d7f87f6 | r1 | 05247c81db6408eac446df9d4e4d8f153b0dfb8d60e86ec1edcb4d586333760c |
| 概览：MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155 | r3→r4 | b4cdd8ae59dc9f4e1c28d10552669dcca3f4ba9d8ec43e0b101315e31826b953 |
| 完整文稿：MEM-bd121869-a0b9-59e3-af23-8e8675374a63 | r3→r4 | d8682cb6eb6f9fc2c8efd59056c2ab0f462e9a875cd93d632300c9693ba5683f |

新 L1 固定引用已登记 RUN-20260916T155857Z-A3D7B61BDD32 的公开规范 owner 指纹（fixed-run.json），完整保存其最终 RESULTS 正文。Run 的源码/测试包、RESULTS 和输入输出未再改写；memory-closure 回执不混入既有固定包，避免自引用。

旧 reader 技术单元 MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b r2、旧章节 MEM-50f66b7c-7953-5715-8b70-5ae7705176ab r3 未更新。原委派、配置、字符体积、470.011秒计时、默认预算失败和partial诊断等历史正文与固定引用保留。概览只追加本次结果和边界；文稿只追加独立章节及相应common/source refs。

## 实际阅读与一致性检查

1. baseline-owner/outline/document/impact 固定起始版本，已完整读取概览及旧文稿六个有序块，包括 reader-results、latency-results、requirements-results 的完整技术正文；不是只读检索摘要或截断 JSON。
2. 每次 commit 后用公开 inspect 指定实际 ID/revision 固定回读；final-document 重新组装独立文稿，complete=true、missing=[]。
3. 已逐字节比较旧组装章节与新文稿第一章完全一致，复用先前已完整读过的相同固定版本；新章节全部正文已再次实际阅读，存 new-assembled-section.md。概览r4全文再次读取，旧正文前缀与旧technical_refs全部保留。
4. readback-checks.json 的10项检查均通过：完整性、无缺失、旧章节/引用/概览保留、coverage未扩大冒充、HEAD一致、索引就绪等。它是软件结构检查，全文衔接与数字/限制仍由本次AI阅读核对。
5. final-document-impact 返回11行 NEW_REVISION，按 code/ID/旧新版本/path 去重后与基线同为7条路径、无新增差异。实际是4种旧依据的有意历史版本保留：reader r1→r2、设置文稿r1→r2、设置L1 r1→r2、设置章节r1→r2；旧文稿已有历史边界说明，当前计时与能力要求正文亦已在原章，不机械升级历史基线。
6. report_version_hints 仍为原 reader r1及设置报告r1两项历史提示；report_coverage 的17个其他L1与基线完全相同，均不属本次UI/storage范围。document-impact 的 uncovered_unit_ids=[] 不被解释为全Project无遗漏。
7. 最终 outline/document/impact 的 basis_heads 均指向generation47；当前工作清单与本次验证数字、限制和后续一致。未发现本范围需另行改写的检查点。

## 验证与限制

- 本轮固定产品证据：后端31项、组件17项通过；浏览器最终6项中5项通过，既有规模N0超时保留，因此Run仍为failed。升级19个唯一用例均有通过证据，真实setup链145.727秒；前端60源码/65资产指纹一致。
- 非record来源展示有组件验证；真实浏览器合成fixture覆盖record来源，不冒称真实业务全部来源端到端通过。原浮点RS仍r5/partial，2条候选未记笔记；未重新执行浮点实验或认可科学内容。
- 列表5项约20.266秒仍慢。本次修复不是总体性能优化、token/费用降低或业务正确率证明；第二物理机、业务人工验收未执行，源码未发布。
- 三次保存的fts/vector均indexed；最终indexed_generation/vector_generation/target_generation均47。没有将成功保存混同科学复核，document-impact scientific_review=not_evaluated。
- root在本次概览/文稿提交后再次执行refresh-index及validate：0错误、21条既有警告。回执位于 ../final-validate.log；未重复无关全套产品测试。

## 失败保留与后续

第一次章节预检误用 role=results，公开schema明确拒绝，未发生章节提交；section-request-invalid-role.json 与 section-validation-error.json 保留。随后按照实际枚举使用methods、新request ID，预检和提交通过。已保存L1沿原回执幂等续接，没有重建重复记录或放宽契约。

后续继续修复既有规模N0和列表来源复核延迟需另立明确验证范围；复用本轮阅读副本前仍须经公开接口重新核验权限、来源与版本。当前同步状态只针对上述固定版本，不承诺后续变化自动同步。
