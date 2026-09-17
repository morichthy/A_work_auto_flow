# AI 按 Owner 阅读与研究式笔记

本页是 `material-query` 的按需接口说明；日常方法见 [material-query Skill](../automation/workflows/material-query/SKILL.md)。程序检索、固定读取、验证并保存，AI 负责相关性、理解和写作。笔记不自动成为规范结论。

## 术语与两个独立维度

| 术语 | 定义 |
|---|---|
| Owner | Research、Project、核心算法、知识等可独立归属规范记录的对象；完整定义见[术语表](../context/GLOSSARY.md#检索与组织术语) |
| RS（Reading Session） | 围绕一个问题保存范围、预算、进度、判断、笔记和固定来源的阅读会话；它是工作状态，不是规范知识或文稿 |
| `owner_document` | 阅读会话的处理模式：候选按 Owner 组织，相关 Owner 进入其当前可读完整正文；它不是文稿类型，也不是阅读策略 |
| `legacy` | 缺少新模式字段的兼容处理模式：围绕候选记录保存读取和笔记，并沿用跨操作累计预算；不会自动迁移为 `owner_document` |
| `strategy` | `owner_document` 内部的阅读策略，取 `standard`、`associative` 或 `quick`；策略决定是否完整阅读、是否受限补查，不改变会话的处理模式 |
| reading note | RS 内保存的材料理解、关键细节、限制和固定出处；它支持续接，但不会自动成为 Owner 的规范记录或已复核结论 |
| 互补筛选包（screening packet） | 为判断一个 Owner 是否相关而交付的少量互补命中窗口；包含通道、固定引用、位置和缺口，但不是完整正文 |
| handoff / snapshot | handoff 是重新核验授权和固定来源后给 AI 的受控笔记交接；snapshot 是供界面快速展示的快照，不能代替 handoff 的核验 |

因此，`mode` 回答“候选和进度按什么阅读模型组织”，`strategy` 回答“本次怎样阅读”。两者不能互换；`research_process`、`research_report` 等则是被读取的文稿类型。

## 使用顺序

新 `reading-template` 固定采用 `mode="owner_document"`，并保存 `strategy`：`standard`、`associative` 或 `quick`。程序从[工作区设置](WORKSPACE_SETTINGS.md)提供默认策略、联想开关/轮次、召回、重排、最多阅读 Owner 数及最终 note 上限。AI 不逐次读取配置。旧 RS 保持原处理模式与预算；旧 Owner RS 读取为 standard、关闭联想，不自动迁移。

1. 填模板的 goal、conditions、query.question、范围，必要时用 owner_id 绑定本次任务对象，再 reading-start。任务归属 Owner 与检索材料 Owner 可以不同。
2. reading-delegate 根据协作开关和宿主能力返回任务包。宿主实际派工才算启动 reader；关闭或无能力时沿同 RS 单 Agent 执行。
3. `standard` 与 `associative` 的 reading-recall 只查询独立发现投影，在路线内、跨路线分别融合 Owner，并返回每 Owner 的互补筛选包。每包通常 2–3 个窗口、硬上限 4；窗口保留通道、固定引用、位置、命中原因及 coverage/gap，不能当作完整正文。AI 通过 reading-assess-owners 把实际包判断为 `relevant`、`uncertain` 或 `irrelevant`；`uncertain` 不自动进入全文路径。发现 `unavailable`、`incomplete` 或 `insufficient` 时回执给出不同缺口和 `fulltext_compensation_available`，但不会暗中查询 blocks/documents。`quick` 同样只交付实际筛选片段，不能由候选推断全文覆盖。
4. standard/associative 中，只有判断为 `relevant` 的 Owner 可以 reading-read 指定 owner_id。已选 Owner 的其余候选无需继续判断。一次读取一个 Owner 当前全部可读的完整正文，稳定分页直至 `has_more=false`；优先 research_process，只有 research_report 或真实正文时明确回退和可能遗漏。quick 不调用 reading-read，而是对实际交付片段逐条 reading-assess；未被判为有用的片段不能作为 quick note 依据。
5. 阅读正文时保留图片、L0/Run 与其他材料的固定引用，需要时显式展开。引用存在不等于原件已经读过，更不等于内容已复核。
6. standard/associative 逐篇以 reading-note 保存研究式笔记；quick 仅用已接受片段写同质量 note，并明确它不是全文阅读。associative 可在信息不足时由主 Agent 制定新的联想问题、搜索文本和关键词，reader 只执行给定文本并报告材料线索，受会话的 enabled/max_rounds 限制；它是召回导航，不能把词语相似写成可验证联系。跨 Owner 的理解用 reading-synthesize 保存综合 note，且只引用实际交付依据。来源或其 Owner note 底稿变化后必须重新检查综合 note；不能沿用它冒充当前理解。reading-decide 记录下一步。主 Agent 只通过 reading-handoff 接收最终笔记，用于后续工作，不安排固定复检或额外审核调用。

同 RS 一次一位 reader，不递归委派，不传主对话全文。宿主自动压缩不属于本项目保证的功能；保存进度与笔记后可沿同一 RS 续接。proceed 后先推进工作，expand 写真实失败或缺口，ask_user 须等真实用户意见；不得伪造 human_decision。

## 核心请求

CLI 从工作区根运行；HTTP 使用现有带会话前缀的 POST `api/v1/materials/reading-动作`。

```powershell
.\workbench.cmd material-query reading-template
.\workbench.cmd material-query reading-start --request start.json
.\workbench.cmd material-query reading-recall --request recall.json
.\workbench.cmd material-query reading-assess-owners --request assessments.json
.\workbench.cmd material-query reading-recall-fulltext --request fulltext.json
.\workbench.cmd material-query reading-read --request read.json
.\workbench.cmd material-query reading-note --request note.json
.\workbench.cmd material-query reading-configure --request configure.json
.\workbench.cmd material-query reading-assess --request assess.json
.\workbench.cmd material-query reading-synthesize --request synthesize.json
.\workbench.cmd material-query reading-decide --request decide.json
.\workbench.cmd material-query reading-handoff --session RS-ID
```

start 使用完整模板，替换实际目标和范围；可加本次任务 owner_id、该对象固定 checkpoint_ref。不能把模板的 scope=null 解释为新的读取授权。之后的写动作带 `session_id`、`expected_revision`、唯一 `request_id`；成功后使用返回 revision，重试相同请求不重复执行，冲突不覆盖。

scope只筛直接候选，scope_ceiling约束获准必要依据；二者不能机械设成同一个Owner，否则跨Owner的Run引用可能阻断已有文稿。沿任务授权保留或明确设置依赖上限，来源授权和排除仍由程序检查。

| 动作 | 本模式额外字段 |
|---|---|
| recall | question、keywords 数组、完整 scope、reason；可选 retrieval_kind=direct/associative、association_text、clue_sources；语言规划须匹配实际子问题，reranking 见下文 |
| assess-owners | assessments 数组；每项为本轮实际 `owner_id`、`packet_digest`、`status`（relevant/uncertain/irrelevant）和 reason；包版本变化须重新判断 |
| recall-fulltext | 不接收新的查询范围或关键词；只能在该 RS 最近 discovery 轮报告补偿可用后，由用户明确选择执行，复用冻结的 scope、查询计划、预算、版本与排除 |
| page | 无；沿冻结查询继续；standard/associative 跳过已完整阅读 Owner，quick 继续交付其尚未判断的片段 |
| read | owner_id；按需可加 source_refs 数组，只接受该 Owner 阅读时已返回的固定引用 |
| note | owner_id、research_note，结构见下文；quick 可选 candidate_ids 限定已接受片段 |
| configure | strategy、association_text；可选 association={enabled,max_rounds}，CAS 保存模式与方向，不启动搜索或 reader |
| assess | candidate_id、useful、reason；只适用于 quick 且只能判断本 RS 实际交付、仍有效的片段 |
| synthesize | research_note；跨 Owner 综合，底稿与来源固定为当前实际交付内容 |
| decide | direction（proceed/expand/ask_user/finish）、reason、next_step、outcome、human_decision；最后两项可空，expand 的 outcome 必须有实际内容 |
| resume / view | 恢复笔记与阅读进度；view 只需 session_id，可用 notes_only |
| handoff | session_id，可固定 expected_revision；正常沿会话 note 上限，不另抄预算 |
| delegate | session_id、真实布尔 host_supports_subagents，可固定 expected_revision |

Owner 阅读回执的 `reading_form`、`document_refs`、`complete` 与 `gaps`说明真正读了什么。Owner 不是“该对象所有历史材料都已覆盖”的证明。来源版本变化、撤权、缺正文或未完整交付不能冒充成功阅读。详细字段权威见 [reading.py](../automation/scripts/material_query/reading.py)、[reading_owner.py](../automation/scripts/material_query/reading_owner.py)，未知字段拒绝。

`references`保留图示的正文标记、caption、所属record_ref、block_ids和固定ref，可据此选择source_refs展开；图号属于各自技术单元，不靠文件名猜对应关系。显式展开Run只返回已有title/conclusion/limitations；其他Owner返回原生登记正文，不是自动撰写研究总结。未展开图像仍只是一条引用。

### research_note

对外显示问题名称时沿用RS的研究目标`goal`：工作台列表与笔记页以名称识别问题，导出文件名带简短名称、短身份和修订号，context笔记页首也显示名称。完整RS-ID留作技术身份；目录不随名称改变，固定链接保持有效。这里的名称不是自动取得的聊天窗口标题，当前没有这种绑定。

笔记是一篇可继续研究的简化完整文稿，标题/字段用于保证要素覆盖，不要求每栏一句。understanding可以承载多段主叙事，logic/details补足方法选择、实验或推导、失败反例及认识修正，公式/变量/单位和引用写在对应论述旁；避免重复抄写。沿实际材料说明问题如何产生、为何这样研究、各轮证据怎样改变认识、当前边界与下一步。未记载的理由标为推断，缺失的过程不编造；quick只能叙述已交付片段所支持的部分。优先连贯段落，比较/步骤才用列表或表格。文本数组项同样可包含多段 Markdown 与 LaTeX，不存在每项必须短句的限制。sources可填写实际读取回执中的来源ID，程序从本RS补齐固定版本、指纹和定位；也兼容完整FixedRef。未知ID或同ID多版本歧义拒绝，不全库补查、不猜版本；有歧义时程序化复制所选完整FixedRef，不手抄SHA。可选 `exploration_clues` 每项含 text、reason、sources、next_query、limitations：它保存有用的潜在线索、条件和未知，而非已验证机制或自动晋升的结论。

```json
{
  "question": "绑定的搜索问题（兼容契约的内部元数据，不在笔记正文重复渲染）",
  "conditions": ["材料的条件、对象与适用范围"],
  "understanding": "相关核心经验和综合理解；区分原文主张、实测与推断",
  "logic": ["推理步骤、连接依据及假设"],
  "details": ["定义、公式及误差式、变量/单位、参数、输入输出、反例和决定性细节；注明对应出处"],
  "sources": ["此处替换为read实际交付的来源ID，或复制完整FixedRef对象"],
  "limitations": ["限制、未展开来源、未保留但影响理解的部分、待验证项"],
  "next_steps": ["材料中有依据的建议；无建议可用空数组，由渲染器添加可选建议标题"]
}
```

公式、条件和关键反例不能为凑长度被省略。图片/L0/Run 用实际引用 ID 或地址在相关细节处对应说明，尚未展开时明确未读。reader 默认先在阅读时建立与问题有关的公式/条件/实验/图示到来源的对应关系，写完后在同一任务内自查并补齐遗漏再保存；原文没有的内容明确为缺口，不靠编造补齐。对应关系不另作审核包交付，语义自查不新增AI请求。保存时程序检查可确定的引用完整登记与固定来源有效性，不检查数学含义；通过校验不等于AI理解必然正确。主Agent不承担固定复检轮次，实际后续工作需要来源时再展开。

保存时的确定性检查仅扫描understanding、logic、details中的显式来源ID：MEM-/RUN-/SRC-前缀，以及已交付record/file/representation中的带分隔符ID；提及的ID必须已交付且列入本note的sources。中文标点、Markdown标签可使用；HTTP(S)地址、Owner/RS导航及问题/条件/限制/下一步字段不按此规则强制当作证据。地址和自然语言引用的语义、正文声称的公式/版本含义不由字符串检查证明。引用未知或漏登时拒绝保存新笔记、不推进RS修订并指出ID，由同一reader修正；既有工程审计仍可记入已经发生的读取消耗。没有提及的来源不强制加入，存量note/handoff不回溯追加此质量检查。已有固定来源授权、版本与陈旧检查继续有效。

Run 已有 run.json 的 conclusion、limitations、登记材料及 README。它可以有自己的 Owner 文稿，但新建 Run 不会自动获得已撰写的研究总结。没有总结就明确缺口；复杂技术解释由 L1 承载并引用真实 Run，文稿再编排 L1。只有原生run.json而没有MEM正文的Run尚不进入三层阅读召回；可沿已交付的固定Run引用按需读取。不得把存在 RESULTS.md 或日志文件视为已完成总结，也不为查询现场伪造 Run 结论。

note 只保存材料中对搜索有用的知识和材料本身的研究演进，不重复当前搜索问题，不写 reader 的操作下一步、派工理由、检索决定或执行结果。上文“下一步”只指材料有依据的建议，显示标题为“可选的下一步建议”，没有则省略。联想问题、搜索文本和关键词由主 Agent 制定，reader 只按给定文本检索并报告材料线索；exploration_clues.reason 说明材料线索，next_query 只保留材料原有问题或主 Agent 已给定文本，不自行制定新方向。关键判断在正文就近引用固定依据，与文末来源对应；历史缺具体引用位置时保留缺口，不按来源排列猜测句级或块级映射。

## 子 Agent 阅读与主 Agent 交接

delegate 返回 route、dispatched=false、model_preference.requirements 和 worker_brief；实际启动由宿主工具负责。只传工作区、任务包、RS/revision 和 Skill 路径，不复制主对话。默认偏向低成本、较低能力、低推理，自定义能力要求由宿主按可用模型选择；不可用时说明替代，文本偏好不授予权限也不能越过 off。

reader 结束仅回 RS、revision、阶段与短缺口。主 Agent 固定调用 handoff，得到单份 context_markdown、覆盖/遗漏状态；不接收所有候选、路线诊断或逐轮对话。每份 note 整条纳入或省略，不截断公式和条件；省略与未完成须明确。来源撤权或陈旧理解不能当当前答案使用。

Owner 模式主要控制项为 `reading.context.max_owners` 和 `note_max_tokens`。估算方法随回执公开，它不是宿主精确 token，也不包括宿主系统提示和对话的全部消耗。内部搜索与诊断不扣最终 note 上限；程序仍有单次操作的超时、读取/模型等资源保护。设置的变更仅影响新模板，已存 RS 保留其参数。预算是上限而非压缩目标，不能为少写而丢掉研究推进逻辑；去重后仍不足时明确容量缺口。软件不能保证外部 AI 总费用、自动压缩或端到端提速；均须实际测量。

## 查询规划与重排

默认路径先查询独立的 Owner 压缩发现投影，再做 Owner 级融合和覆盖互补筛选包；投影只含 L4/L3、L2 紧凑内容、L1 `retrieval_description` 和 Owner 元数据，不复用全文索引的 level 过滤。发现索引不可用、覆盖不完整或结果不足时只返回缺口，由用户明确选择是否执行 L1 blocks、完整文稿等全文补偿召回。相关 Owner 被选中后的完整阅读仍是 standard/associative 的正常步骤，不属于全库补偿。manual MQ、legacy RS 和既有冻结查询继续使用原全文流程。详细状态、升级验证与效果评估边界见[Owner发现设计](design/OWNER_DISCOVERY_RETRIEVAL.md)。

原问题保留，AI 可在 recall 增加下列字段。程序不替 AI 翻译，也不将英文当可信度或访问权限。

| 字段 | 内容 |
|---|---|
| query_variants | 数组，每项 id、language（zh/en/other）、question、lexical_terms；含保留的 original，总数最多 3 条去重等义查询 |
| protected_terms | 必须原样保留的型号、版本、数值/单位及条件；程序文本校验不代替语义核对 |
| corpus_language / language_reason | zh/en/mixed/unknown；说明实际语言依据及英文补查原因 |
| query_domains | 领域数组，程序匹配该领域与 general 词条 |

技术/文献问题补英文关键词与完整句；词法用紧凑词项，dense 用完整问题。程序从[术语库](QUERY_TERMS.md)扩同义和别名，关联词另走单跳低权重探索。各层独立召回并融合，续页冻结计划和词库指纹。缺模型、空窗口、partial 不等于全库没有资料。

reranking 可在模板/start/recall 中指定，随轮次冻结：
```json
{"reranking":{"mode":"auto","candidate_limit":30,"conditions":[
  {"id":"device","kind":"literal","field":"型号","operator":"eq","expected":"X200"},
  {"id":"temperature","kind":"numeric","field":"温度","operator":"lt","expected":-20,"unit":"°C"}
]}}
```

mode 为 off/auto/required；候选窗启用时至少覆盖 result_limit。每层候选固定回读命中块及必要定义，离线 Cross-encoder 评分，再结合显式条件冲突分组；unknown 与满足不人为分档，低分不删除。literal 支持 eq/ne，numeric 另支持 lt/le/gt/ge；复杂句、多对象、否定歧义或单位不明保持 unknown。AI 仍判断通用语义和适用性。

标准 CE 的问题、单个筛选窗口正文与特殊 token 合计不超过 512；超长项由确定性命中中心窗口截取，保留标题、实际命中和关键条件。`auto` 只让失败窗口保持原排序，不使同批其他窗口回退；`required` 的失败、费用和账本语义仍明确失败。重排不删除 Owner，也不会在同一 Owner 的第二个窗口之前省略其他 Owner 的首窗。重排元数据在会话内部保留，不把重复命中说明当正文反复返回。模型位于 services/reranker，运行不联网下载；分发见[依赖手册](DEPENDENCY_RELEASE.md)。软件可用不能证明 Recall/nDCG 提升，需独立题集验证。

## 存储、预算与恢复

`.local`和JSON是当前工程实现选择，不是AI或Markdown的技术要求。此处保存的是阅读会话，而不只是文稿：进度、预算、请求幂等、固定来源、笔记与历史修订一起交给程序维护。JSON便于明确字段和版本校验，目录位置用于和源码、公共知识及可读上下文分开；这些能力也可另用Markdown frontmatter/日志实现，格式本身不保证可靠性。

只保留一篇当前文本时，context中的单个Markdown完全可行。当前没有这样做，是因为还需保留上述会话能力且避免手编Markdown与程序JSON各自成为互相覆盖的真源；不是JSON更擅长写文章，也不是Markdown不能可靠保存。若以后改为Markdown权威正文，需要同时明确元数据/历史/人工编辑与程序写入的关系，不能直接删除现有会话数据。此次仅改写作要求，不迁移存储。

RS 的 HEAD 与不可变修订位于 `.local/reading-sessions/`，是唯一阅读状态，保存固定来源、进度、AI 笔记与诊断。它是应保留的私人工作数据，不是可删缓存、不自动进入知识索引。锁、CAS、请求幂等和原子保存保护写入；不能抢占活跃锁或手改状态。原材料仍在规范 Owner/获准来源。

人类可读副本为 `context/reading-notes/<RS-ID>/current.md`，工作台首页与“系统记忆→阅读记录”共享选择。`reading-notes/recent`只显示最近24小时更新、未归档且有note的当前可访问会话，查看不延长更新时间；退出窗口不删除历史RS。`reading-notes/snapshot`是带时间、版本和策略的` snapshot_only`展示快照。副本由程序生成，手改不能保存新理解；主Agent仍经handoff重验，不能直接盲读副本。编号引用仍保留固定ID、revision、hash和locator。源码分发排除私人 RS/副本，升级保留。

```powershell
.\workbench.cmd material-query reading-list --owner 实际任务OwnerID
.\workbench.cmd material-query reading-view --session RS-ID --markdown
```

list 可按 owner_id、offset、limit、include_archived 筛选；目录发现有独立资源保护。bind 指定 owner_id/checkpoint_ref，只绑定任务不扩大读取域；archive 的 archived/reason 只归档不删除历史。当前授权覆盖原会话才可访问，回源仍用原 scope_ceiling 和排除；换 Agent、重启或改配置不扩大授权。

### 旧会话兼容

缺 mode 的既有 RS（以及未显式指定新模式的旧 start 请求）维持 legacy 记录流程：read 用 candidate_ids，note 用 candidate_id、summary、connection、details、uncertainties。connection 包含 kind/direct|inspiration|not_useful、explanation、chain；details 项含 text、reason、block_ids。固定来源由已读候选带入。旧模式保持原跨操作累计 Ledger，不自动清零或套新 Owner 语义。

legacy handoff 默认 12,000 字符，可用 max_chars（512–30,000）和 candidate_ids；字符不是 token，仍受旧 RS 累计预算。原始诊断/固定版本不改写。新 Owner 模式以设置的 note 上限为主；显式收紧交接窗口也不能让程序截断一份笔记。

## 与总工作清单的关系

RS 只保存阅读子任务。work-loop 的任务计划另综合用户目标、输入、产物、尝试和下一步，通过 RS/revision 引用理解。reader 不并发改总计划；主 Agent 获取 handoff 后按任务需要维护，不追加固定质量复检。可复用成果经 memory 公共入口保存，阶段收口按 consolidate-results，均不由 reading-note 自动完成。
