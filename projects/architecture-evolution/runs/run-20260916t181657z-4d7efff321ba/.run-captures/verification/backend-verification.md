# Owner阅读后端验证

本次记录针对 `owner_document` 新模式；旧手写start未提供mode与旧RS仍走legacy。源码未提交。测试均使用隔离合成fixture，不代表真实AI理解或科学结论复核；真实Owner阅读由独立审计记录。

## 红测与修正

- 最先新增3项Owner契约测试并运行，工具进程24618回执：21项，90.563秒，3项新测试因start不认识mode/context而失败，18项既有legacy测试通过。初始test模块直接导入TestCase导致unittest连同18项旧测试收录，后改为模块导入。该次完整原始日志未落盘，仅工具会话有回执；本项是据实际回执保存的摘要，不是重放的红测。
- 实现后第一轮3项出现fallback因无关记录来源拒绝而失败，处理为只交付获准内容并明确缺口；随后3项通过。
- 扩展9项时发现“文稿目录存在但文稿全部不可用”未进入实际记录fallback，造成1失败2错误；保留 `owner-reading-tests.log`。修正后9项全部通过，见v2。
- Run专测初次fixture用了原生文件字节hash作为旧MEM Owner引用，规范提交拒绝STALE_BASIS；检查发现旧MEM用evidence规范内容指纹而MQ native用原始文件指纹。增加单Owner固定读取适配，保留原引用，两种算法均核对当前真实内容；失败日志保留。

## 已完成验证

| 范围 | 数量 | 结果 | 日志 |
|---|---:|---|---|
| Owner模式（候选字段、跨路线同块、真实输出计量、完整fallback、文稿优先、持久进度、引用拒绝、来源修订/撤权、图引用/展开、Owner选中上限、UI引用） | 12 | 全部通过，72.459s | owner-reading-tests-v4.log |
| Owner预算纯函数补测（含新增finish仍有已选未note） | 3，其中2项与上行重复 | 全部通过 | owner-reading-final-unit-tests.log |
| legacy阅读工作流 | 18 | 全部通过，53.607s | owner-reading-legacy-tests.log |
| delegation公开CLI/HTTP与handoff | 10 | 全部通过，42.501s | owner-reading-delegation-tests.log |
| query-plan、reranking、reranking integration、handoff view | 29 | 全部通过，97.827s | owner-reading-related-tests.log |
| 普通MQ选项/全文文稿/图片/授权与版本，覆盖Assembler默认行为 | 8 | 全部通过，53.166s | owner-reading-assembly-documents-tests.log |

上述首轮Owner文件有14项。末项Run引用/版本适配单独复验通过：1项33.489秒，见owner-reading-run-reference-tests-v2.log。上表和该专测去重共79项全部通过。后续渐进分页补全见末节。

## 接口与实现范围

- 新template带 `mode=owner_document`、固定context；start没mode保持legacy。context界限：max_owners 1..100；note_max_tokens 512..50000。
- recall候选只有owner_id/text；正文块按固定ref/selector/text去重。选中Owner不再给片段；内部搜索、重排、诊断不扣AI输出字符。工程账本按operation新建并保留原IO/时间/模型硬限制。
- read(owner_id)只读一个Owner的一篇最新完整research_process；缺少时明确回退research_report，否则真实完整记录fallback并说明缺口。不扫任意README/RESULTS。文稿定位用索引，正文以规范固定存储核对；不因direct层级条件屏蔽文稿，仍受ceiling与排除约束。
- 证据附件/Run保留声明引用，图注、所属记录、block、唯一图标记随references返回；source_refs须已交付且固定版本一致。显式Run展开只给已有title/conclusion/limitations；无总结明确缺口。未新增原生Run三lane召回。
- note按Owner保存完整研究笔记与固定输入basis，验证出处来自实际交付列表；保存回执包含保守token估计、上限与超限提示。源修订/撤权不能泄漏旧理解。
- handoff按整个Owner note装包，不截公式；UTF-8字节计数是非常保守估计，不是宿主精确token且不保证任意tokenizer严格上界。超预算笔记保留在RS，交付说明遗漏。完结但已选Owner未note仍partial。
- snapshot/notes view仅显示实际纳入note的引用按钮，gaps保存到Markdown；CLI旧candidate_ids按需读源仍兼容。普通MQ的Assembler默认不变，只有Owner模式defer_evidence。

## 可重复命令

```powershell
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_reading_owner_document.py -v
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_reading_workflow.py -v
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_reading_delegation.py -v
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_material_query_options.py -v
.\automation\python.ps1 -c 'import sys; sys.path.insert(0, "automation/tests"); import unittest; suite = unittest.defaultTestLoader.loadTestsFromNames(["test_reading_query_plan", "test_reading_reranking", "test_reading_reranking_integration", "test_reading_handoff_view"]); result = unittest.TextTestRunner(verbosity=2).run(suite); raise SystemExit(not result.wasSuccessful())'
```

普通复制到固定Run目录被Windows访问控制拒绝后，使用已授权受控提权复制测试日志；未删除锁、未改Run业务元数据、未改MEM schema、未改Git提交。

## 同Owner候选渐进分页补全

实际读者验收发现原先一次返回同Owner 11段正文，虽后续选中会停止重复，但首次已经消耗全部片段。新增渐进分页：每次recall/page每Owner最多一份去重正文，内部每路召回/重排窗口保持不变。

- 在既有candidate行保存delivery、preview.form、preview.refs、preview_round_index；不保存新的正文队列、不重复存packet。已有hits.matched_text诊断仍为内部诊断，不作为page正文真源。
- page优先按固定引用重新授权、组装pending；同Owner相同正文或已交付定义不占用本页名额，继续下一候选。
- read选中Owner后跳过其所有pending。旧Owner RS无delivery字段按此前已交付处理，不重吐旧候选。
- recall/page以及resume/view返回has_more、pending_owner_count；不完整包仍pending，未来恢复来源后继续完整回源并去重。
- 真实红测1项32.375秒失败（3!=1），见owner-reading-progressive-red.log。第一轮实现15项14过，唯一失败为测试误将原有matched_text诊断视为新pending正文复制；改为验证preview仅含form/refs以及不存在新的packet/text/body字段，保留失败日志owner-reading-progressive-tests.log。
- 补旧RS兼容后16项67.449秒全过，见owner-reading-progressive-tests-v2.log。随后增加partial pending不丢失与resume控制字段定向验证，2项37.229秒全过，见owner-reading-progressive-final-tests.log。最终新Owner文件17项全部有通过记录，本次后端不同用例去重为82项。

## 笔记来源ID简写

低成本reader实际手写长SHA出错后，仅补reading-note输入便利：research_note.sources兼容字符串ID与完整FixedRef。字符串只在该Owner progress.sources已交付集合中精确匹配；kind/revision/sha256必须唯一，同版本多个locator全部保留并去重。未知ID或多固定版本/类型拒绝，调用者可用现有完整FixedRef消除歧义。不查全库、不扩授权、不改版本；持久化始终为完整FixedRef。

- 先跑真实红测，1项33.699秒因ID字符串不被原接口认可而VALIDATION失败，见owner-reading-source-id-red.log。
- 新增ID落盘/未知ID集成测试以及多locator/多kind/多revision/多hash歧义单元测试；另定向复验原伪造引用、完整note/handoff、来源修订/撤权。5项78.452秒全部通过，见owner-reading-source-id-tests.log。最终Owner文件19项均有通过记录，累计不同后端用例84项。完成此项后后端源码冻结。
