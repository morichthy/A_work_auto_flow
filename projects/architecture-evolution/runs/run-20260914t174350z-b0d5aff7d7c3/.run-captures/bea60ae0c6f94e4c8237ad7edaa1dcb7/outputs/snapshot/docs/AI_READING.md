# AI 多路检索与阅读会话

这是 `material-query` 上的 AI 工作入口，用于围绕同一个问题找依据、读完整材料、保存理解和继续工作。它不训练模型，不生成答案，不把 AI 理解自动晋升为规范结论。现有工作台手动查询不改变默认行为；本流程通过 CLI 或 HTTP 调用，由 material-query Skill 指导 AI。

## 使用顺序

1. `reading-template` 返回开始请求模板；按实际目标填写 goal、conditions、query.question 和授权范围。模板中的 scope=null 不是扩大读取授权的理由，使用任务给定范围。
2. `reading-start --request 文件` 建立 RS 会话。开始不自动搜索；当前上下文已经足够时可以直接决定下一步。
3. `reading-recall` 每次保留原查询identity，各等义变体分别执行紧凑词法和完整自然语言dense，并分别查 L4/L3、L2、L1；每轮按领域尝试词库同义及单跳关联扩展、按排名融合。短候选完整正文返回，L1 返回命中块及声明依赖；只有摘要命中时明确返回 unit_digest，不猜正文块。每个候选带固定 ref、版本、本地链接、命中块与query来源。缺模型/索引或预算不足明确降级，不联网补齐。
4. 读完首批候选，必要时 `reading-page` 续批；它重建原范围查询并跳过已交付身份，跨进程不复活 MQ 游标，实际费用继续累计。结果的 coverage/gaps 说明未覆盖范围，不能把当前窗口结束解释为全库无资料。
5. AI 可保留直接相关或有具体连接理由的间接启发，调用 `reading-read` 读取保留材料的完整记录。涉及完整研究文稿时另用既有documents入口；要读L0原件，用memory raw-materials/raw-material沿固定来源读取。核验来源不等于已经交付原件正文，不自动展开所有引用。
6. AI **实际阅读**后调用 `reading-note` 保存压缩理解、连接步骤、必要细节、待验证处。程序只验证完整交付与定位，不证明 AI 已读或理解正确。必要细节保持公式变量、单位、参数、边界和决定性片段，并写保留原因。
7. `reading-decide` 记录可执行下一步或失败缺口。proceed 后先做事，不继续召回；expand由AI按当前失败、方向和成本判断，不按次数自动转ask_user；已明确ask_user时须记录真实人工意见后才继续。human_decision 是调用者记录的人工意见，不是认证或授权凭据，不得由 AI 伪造。
8. `reading-resume` 返回易读 Markdown：目标、条件、理解、必要细节、固定链接、尝试与下一步，以及未记笔记的候选和覆盖情况。当前对话已有足够上下文时不必反复恢复。

## 命令与请求

```powershell
.\workbench.cmd material-query reading-template
.\workbench.cmd material-query reading-start --request start.json
.\workbench.cmd material-query reading-recall --request recall.json
.\workbench.cmd material-query reading-read --request read.json
.\workbench.cmd material-query reading-note --request note.json
.\workbench.cmd material-query reading-decide --request decide.json
.\workbench.cmd material-query reading-resume --request resume.json
```

HTTP 使用已有本机带会话前缀的 POST `api/v1/materials/reading-动作`。字段由 `material_query/reading.py` 校验，QueryRequest/Scope/Budget 沿用原运行契约；不在旧 MQ 的临时状态中冒充持久身份。

start可增加owner_id与可选checkpoint_ref；后者是该Owner的固定checkpoint记录FixedRef。旧无绑定会话继续兼容。

start 字段是模板中的 `session_id`、`goal`、`conditions`、完整 `query`。除list/view外，每个后续动作都必须给 `session_id`、`expected_revision`、唯一 `request_id`，并加下表字段。每次成功返回新 revision，下一动作使用它；同请求重试不重复执行，返回 replayed，需要正文时另发 read/resume。错误不会提交笔记修改，但已发生费用仍保存。

| 动作          | 额外字段                                                                                                                                                                |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| recall        | `question`、`keywords` 数组、`scope`（完整 Scope）、`reason`                                                                                                    |
| page / resume | 无                                                                                                                                                                      |
| read          | `candidate_ids` 数组，仅接受已交付的 RC 身份                                                                                                                          |
| note          | `candidate_id`、`summary`、`connection`、`details`、`uncertainties`                                                                                           |
| decide        | `direction`（proceed/expand/ask_user/finish）、`reason`、`next_step`、`outcome`、`human_decision`；后两项允许空串，expand 的 outcome 必须写尝试结果或具体缺口 |

note 中 `connection={kind,explanation,chain}`：kind 为 direct/inspiration/not_useful，chain 为逐步连接和假设的文本数组；`details=[{text,reason,block_ids}]`：block_ids 是该记录实际技术块 ID，整记录或非技术记录可以空数组；uncertainties 为文本数组。来源固定身份由服务从已读候选带入，不能借笔记请求指定任意文件。

## 双语查询计划与术语扩展

`reading-recall`保留原有必填字段，另外接受以下可选字段。旧请求仍可执行；AI应按material-query Skill主动填写语言计划。程序不翻译、不自动判定英文来源可靠，也不将请求语言当权限或硬过滤。

| 字段 | 内容 |
|---|---|
| query_variants | 数组，每项{id,language,question,lexical_terms}；language为zh/en/other，id不能占用original；包含自动保留原查询后，去重总数最多3条 |
| protected_terms | 原问题中需逐字保留的实体/型号/版本/数值和单位文本；程序另提取常见数字/型号，拒绝变体丢失保护项或增改数字；语义/否定仍须AI核对 |
| corpus_language | zh/en/mixed/unknown，缺省unknown；依据实际获准语料判断 |
| language_reason | 选择语言、技术问题英文补查或缺乏语言依据的说明 |
| query_domains | 本次领域字符串数组；仅匹配此领域与general的启用词条 |

中文为主用中文加原英文术语/型号；英文为主用英文等义查询并保留原查询；混合/未知分别生成中英。技术问题、明显依赖大量文献或已有可靠英文来源/数据流，即使中文提问也补英文关键词和完整语句。词库维护见[QUERY_TERMS](QUERY_TERMS.md)。以下为合成示例中的额外字段，需并入完整recall请求，原question也必须包含所列保护项：

```json
{
  "query_variants": [{
    "id": "english",
    "language": "en",
    "question": "How can query expansion improve cross-lingual retrieval for X200 v2.1 while retaining the error constraint ≤ 0.5 mm?",
    "lexical_terms": ["query expansion", "cross-lingual retrieval", "X200", "v2.1"]
  }],
  "protected_terms": ["X200", "v2.1", "≤ 0.5 mm"],
  "corpus_language": "mixed",
  "language_reason": "技术问题；合成材料同时包含英文方法与中文说明，补英文检索",
  "query_domains": ["information-retrieval"]
}
```

词法使用keywords/lexical_terms与本语种同义词和别名，不加入整段question；无keywords的旧请求用既有分词。dense只使用完整question。同语种多个等义变体平分该语种权重；关联词另走较低权重词法路，不递归、不认作等义。各层内使用加权RRF并按固定记录去重，合并实际命中块；排名不是条件成立或证据可靠性判断。

coverage.query_plan保存实际变体、保护项、领域、词库SHA256、matched_entries、related_terms与语言说明；english_query_present显示是否提供英文句，translation_validation明确仅有文本保护校验。候选query_sources以query_plan_id和路由/变体id定位完整语句与词项，并保留语言、通道、类型、排名和权重，避免逐候选重复整段查询。hits带query_source与query_plan_id，重召回保留历次来源；新增计划/诊断计入输出预算。condition_check=pending要求AI对固定正文核对“满足/冲突/未说明”，并通过reading-note的details/uncertainties记下依据。库缺失或无匹配在计划中可见；存在但JSON/格式错误拒绝本轮，不能静默忽略。

续页冻结该轮query_plan，库更新不改旧计划；新一轮才重新读取。每种语言、每层的向量编码都消耗原RS预算，更多路数可能减少可用续页/阅读预算，不自动提高上限。当前词库上限1MiB/2000条、本轮最多16条匹配和32个关联词；超过上限须收窄领域或整理词项。规则保护有界执行，不是检索质量阈值。

## 存储、预算与恢复

`.local/reading-sessions/RS-…/HEAD.json` 是当前工作记录，每次成功语义写操作另保留不可变revision文件；view只保存累计消费，不改变语义revision或历史。保存目标/条件、候选固定身份与交付范围、AI 笔记、决策及累计消费；不复制原始技术正文，不进入知识索引。规范内容仍在 Owner 的 memory；可推广成果另经 memory 公开入口保存。

该目录是应保留的私人工作数据，不能当作可重建缓存清理；源码发行不包含它，升级保留它。读写使用排他锁、版本比较、请求身份和原子切换。进程崩溃留下 operation.lock 时先确认原进程停止再处理锁，不能自动抢占活跃操作；未发布的 revision 文件不成为 HEAD。

会话范围上限、原始排除、用途、预算不因重启或扩查变大。所有召回、正文、view来源重核和恢复输出共享持久账本。模板预算是5分钟活动时间、16 MiB读取、8万字符输出、12次模型调用和6144输入 token；每个分层向量请求单独计量，缺模型可降级。需要更大预算应开始前显式设置，受原服务器上限约束；耗尽后报告缺口，不自动重置。新目标/授权/预算另建明确会话，旧历史保留。

恢复重核保存材料及依赖的当前授权。来源撤权时拒绝返回相关工作记录；规范记录新修订会标记旧版理解需要复查，不能用它冒充当前结论。会话绑定构造服务时的可信授权域；人工意见字段不能扩展它。

工作台“系统记忆→阅读记录”可列出会话、查看最新笔记、打开候选固定原文和导出此版本Markdown；导出不实时更新。当前无后台AI、跨问题自动注入或自动结构关系采纳；AI是否读懂仍需实际任务验收。

## 便捷查看、绑定与归档

```powershell
.\workbench.cmd material-query reading-list --owner 实际OwnerID
.\workbench.cmd material-query reading-view --session RS-ID --markdown
```

list请求可省略，字段为owner_id、offset（默认0）、limit（1–50，默认20）、include_archived（默认false）。它按最多10000个目录排序分窗后筛选；空页仍可能有next_offset。每次使用独立有界元数据预算，不执行检索/模型，不返回笔记正文；权限不可读项目只计unavailable_count。归档标记不减少目录容量。全局列表可发现未绑定旧会话。

view只需session_id，不要求request_id/revision；返回当前revision、Markdown、带链接和固定身份的候选及已读/未读状态。它消费持久会话预算，过期来源或撤权不会直接返回旧理解。导出名字与实际显示的快照版本一致；后续打开原文会产生新的交付修订，需刷新笔记再导出新版本。

bind除通用写字段外需owner_id、checkpoint_ref（可为null）；检查Owner存在、当前授权，以及检查点属于该Owner，不改变检索范围。archive需archived布尔值、reason；归档后只可查看/恢复输出/改变归档，须恢复后继续写笔记、读取交付或重新绑定。没有自动删除或撤回来源功能。

## 与整个任务工作清单的关系

RS保存阅读子任务，不涵盖所有用户输入、开发产物和执行结果。持续任务由work-loop另在已有任务计划或工作文件维护一份可打开的Markdown当前上下文，综合材料链接、理解/经验、必要细节、尝试和下一步；已有RS通过身份与revision引用，阅读笔记仍由reading-note/decide保存。清单由AI在重要变化及交接时更新，没有后台自动同步或新增工作台标签。位置与续接见[公共动作](WORKFLOW_ACTIONS.md#用户可见的工作上下文清单)。
