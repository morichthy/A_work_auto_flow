# 工作与记录：公共动作参考

2026-09-13，按当前CLI/API核对。主Skill为work-loop；这里按需要查动作，不要求每次全文加载。Owner、Run、MEM、RS是不同身份，不能互换。示例中的ID/路径须替换为真实回执；所有命令从工作区根执行。

## 找归属、读取与继续

```powershell
.\workbench.cmd memory list-owners
.\workbench.cmd memory inspect 实际OwnerID
.\workbench.cmd memory inspect 实际OwnerID --record-id MEM-ID --revision 1
.\workbench.cmd memory resume --request resume.json
.\workbench.cmd material-query reading-list --owner 实际OwnerID
.\workbench.cmd material-query reading-handoff --session RS-ID
```

resume.json最小形状为`{"owner_id":"实际OwnerID"}`。它恢复规范目标/检查点；reading-handoff只返回阅读子任务的有界笔记、必要细节与固定出处，保留partial/遗漏/等待状态，不执行新搜索。阅读副本和recent/snapshot只供当前界面展示，主Agent继续必须使用handoff的当前授权与固定来源核验。reading-view保留完整检查用途，含候选和覆盖诊断。未绑定旧RS可先reading-list列出，再用reading-bind绑定。

任务开始或用户调整设置后，用`workbench.cmd workspace-settings policy`读取一次精简协作策略；off由主Agent完成，auto仅在宿主支持且任务适合时委派。按返回的`subagent_requirements`选择可用模型和推理深度，默认偏低成本、较低能力；无需AI打开配置文件。工作台修改与完整CLI见[工作区设置](WORKSPACE_SETTINGS.md)。

需要新依据：reading-template取得完整请求（程序已应用工作区默认数量/预算/重排），设置实际query范围、goal、conditions及owner_id，用户显式要求优先，reading-start创建；reading-delegate核对开关和宿主能力，返回最小任务包，由宿主实际委派独立低成本reader，关闭/无能力则主Agent沿同RS执行。新模板固定owner_document，并保存 standard/associative/quick 策略。standard/associative 召回后以reading-read逐Owner读现有文稿；associative 仅在不足时以实际联想搜索文本追加受限召回。quick 以reading-assess逐条判断实际片段，不能读取全文或声称全文覆盖。reading-note保存理解，reading-synthesize保存跨Owner综合，reading-decide决定下一步；模式变更走带CAS的reading-configure，保存本身不启动搜索或AI。旧RS仍用旧字段，主Agent只回读handoff。写入使用当前revision和唯一request_id；冲突不覆盖。完整请求见[AI阅读](AI_READING.md)。

scope选直接候选，scope_ceiling限必要依据。Run有独立Owner身份：即使文件放在Project下，只允许该Project也不会自动允许其Run。工具经验引用两个Run时，两者都须在获准的依据上限内；否则父材料可能被省略。按真实引用核对缺口，不把查无结果解释为全库没有资料，不借新RS绕过授权或阅读数限制；旧RS累计预算仍不清零。

无稳定身份的已有文件，按list-owners返回native_ref/fingerprint用`memory adopt-owner`（见--help）；批量来源采用context-maintenance。不为普通工具建立MOD。

## 用户可见的工作上下文清单

这是一份由执行工作的AI持续编辑的Markdown工作文件；不是RS导出，也没有后台自动更新程序。持续或多步任务维护，极小无复用价值操作可省略。先比较Owner的目标、概览、成果和未解问题；同一目标的继续/子任务沿用，主题相似只引用，独立交付另建。选择理由在清单写一句即可。

优先在本任务已有计划中维护“当前工作上下文”，不要再建同内容清单。没有计划时，在所属对象的工作目录新建 `work-context-任务名.md`；Project/Research可放其plans目录，工具放 `tools/runtime/TOOL-ID/`，其他对象选择其已有可写工作目录并记明实际路径。不要放入程序源码目录、服务管理的memory/commits或缓存；不从Owner ID猜原生路径，先查native_ref/memory_home和对象说明。并行任务各用自己的文件，不共享覆盖一个Owner全局清单。

清单按任务缩放，至少让下一位读者看懂：

- Owner与选择理由、当前目标、条件及完成标准。
- 当前输入和召回材料的可打开链接、已读/待读/失效状态、用途；规范材料保留固定版本，RS标明身份与已查看revision。
- 当前理解、可用经验、间接连接和必要细节；区分事实与推断，保留参数、边界和反例，不复制完整正文。
- 已尝试什么、真实结果和缺口；下一步做什么、为什么继续或补查。

获得重要材料、完成尝试、改变目标/方向或交接时更新，并记录更新时间；不逐条抄命令日志。已有RS的笔记仍用reading-note/decide保存，清单引用其身份和查看入口，只综合当前任务需要的部分。没有本地召回也要记录用户材料、代码、Run或当前产物。首次建立及交接给用户文件链接，并从Owner的README或任务入口链接；若对象没有可编辑入口，至少在已有任务入口及交付消息保留实际路径。

续接先读此文件，再按需resume/reading-view核验固定依据、阅读状态和未完成项。用户最新指示优先；发现清单过期或与新回执冲突，明确差异后更新，不能把旧摘要当成最新事实。清单维护当前工作，Owner检查点保存交接时点，RS维护阅读子任务；它们不各自维护一份互相竞争的当前总计划。

需要固定证据时，先另存带日期/版本的快照，再按用途run-register或提交规范内容；已登记指纹的文件不再覆盖。可变清单不能直接登记成固定产物后继续改写。Markdown本身没有CAS或自动同步：写前重读，遇到他人修改先合并；历史重要决定保留简短变更说明或固定快照。清单不是自动纳入规范索引的经验记录，可复用成果仍走memory提交。

补查没有固定阈值：相关材料缺细节时读完整正文和固定依赖；路线失败且关键本地经验仍可能缺失时，依据失败原因改写问题或扩大获准范围；对历史依赖低且已有可验证方向时先实验/推进。低相关性不等于无价值，高相似度不等于足够；间接连接写清假设。决策由AI完成，已有reading-decide负责保存，不增加“相关性评分”接口，不按第二轮次数强制问人。

## 执行和材料登记

```powershell
.\workbench.cmd new-run --owner 实际OwnerID --title "本次独立分析"
.\workbench.cmd run-execute RUN-ID --request execution.json
.\workbench.cmd run-register RUN-ID --input "实际输入文件" --artifact "实际产物文件"
.\workbench.cmd memory raw-materials --request materials.json
```

execution.json示意：`{"script":"实际脚本.py","inputs":["实际输入.csv"],"args":["{input0}","{output_dir}"],"timeout_seconds":3600}`。args按脚本接口填写，非固定模板。当前run-execute只执行获准Python脚本；其他语言/软件完成后用run-register登记。materials.json使用`{"owner_id":"实际OwnerID"}`，回读实际清单后按material_id调用raw-material；详见[执行手册](RUN_CAPTURE.md)。

工具源码留tools/scripts或packages；工具自身验证在tools/runtime/TOOL-ID/runs，通用方法/经验在tools/memory/TOOL-ID。工具处理业务数据时Run通常归业务Owner，记录真实工具和代码版本引用。

## 保存有用内容

有用中间记录可由 AI 自主提交，不等逐次指令；重要成果保存、阶段总结/交接或实质变化由 [consolidate-results](../automation/workflows/consolidate-results/SKILL.md) 负责完整阅读、差异盘点和文稿/上下文同步。下面的保存动作不自动完成该流程。

```powershell
.\workbench.cmd memory validate-draft --request commit.json
.\workbench.cmd memory commit --request commit.json
.\workbench.cmd memory inspect 实际OwnerID --record-id MEM-ID --revision 1
```

commit.json封套使用schema_version=3、request_id、actor={kind:"ai",id:实际执行者}、owner_id、expected_head及operations。新内容用`op:"put_record"`、client_key、draft；更新增加record_id和expected_revision。字段不可用时读[请求示例](MEMORY_REQUESTS.md)，不要直接写memory目录。草案版本与提交封套分开：L1和文稿v3，narrative/overview及分类experience v4。

所有Owner按有用内容组合L0–L4；缺层正常。L1的未执行方法用unit_type=method、run_ref=null及真实来源；discovery常用owner_only或workspace_summary；v4 experience的knowledge_type为observation/conclusion/hypothesis/recommendation（方法步骤归L1），精确可选分类见[知识分类](KNOWLEDGE_FACETS.md)。L3来源主张/AI推断/本次观察在正文与分类中标明，不能冒充本次验证。L4也可直接固定引用原文，无须伪造L1/L2。完整层级语义见[记录标准](RESEARCH_RECORDING.md)。

提交回执分开核对save_status、index_status。已committed但INDEX_PENDING时用`memory reconcile --request`（owner_id）补偿；不要换请求ID重复创建。复用引用用record_hash、固定revision和locator，不用content_hash替代完整记录指纹。

## 交接与文稿

交接通过commit中的`save_checkpoint`保存，goal_ref、completed_refs、next_step等使用实际内容，未知预算明确未知；save_checkpoint是CommitRequest操作，仍需client_key和kind=checkpoint的draft，服务按操作映射校验后统一保存；精确payload见[请求示例](MEMORY_REQUESTS.md)。没有需要继续的独立工作，不必创建检查点。

RS可用owner_id和可选checkpoint_ref（材料查询FixedRef）说明对应哪次交接；关联存在RS中，Owner查看时按owner_id列出，不向MEM的证据数组写RS-ID。Owner检查点保存该次顶层目标/下一步，RS只记录阅读尝试；持续工作按上节维护清单，交接时同步实际结果与下一步，不将旧检查点解释为最新进展。

文稿按实际用途组织：outline/section-context读取已有结构，document-impact检查依据变化，再提交必要章节与document，最后memory document固定回读。完整/精简是可选独立文稿，不要求每次工作都生成两份。归档阅读用reading-archive，保留状态和历史；归档不撤回规范结论。
