# 材料查询、阅读与维护

工作台新查询页面从[工作区设置](WORKSPACE_SETTINGS.md)取得默认结果数和预算；可在本次查询进一步明确调整。已经打开的草稿、进行中的查询与旧RS不被设置变更覆盖。程序直接读取配置缓存，不调用AI解释设置。

AI阅读入口可选正文/必要定义、离线Cross-encoder与显式条件重排，详见[AI_READING](AI_READING.md)。这一阶段只接入reading工作流；本手册通用材料查询及其RRF/主题排序不自动启用新模型，Foundation显式词面重排接口保持原契约。

AI围绕同一问题的默认多路检索、完整阅读、必要细节笔记和跨进程续接，使用新增 `reading-*` 动作，见[AI 阅读手册](AI_READING.md)。2026-09-13补充list/view/bind/archive及工作台系统记忆内的Owner阅读入口；补查次数不再强制人工门槛，但已提出的问题仍待真实意见。下文手动查询及原 MQ 临时游标继续兼容；RS 工作记录与 MQ 查询身份不互换。

材料查询把“找哪些材料”和“怎样呈现这些材料”分开。工作台导航的**材料查询**提供范围树、内容来源、用途、候选选择、固定展开、组包及维护计划。规范内容仍保存在原有 MemoryStore（v4 聚合兼容契约）；一次查询不会改写原件、创建科学结论或替换历史版本。

## 主要概念

| 概念 | 含义与使用方式 |
|---|---|
| 内容来源 content_source | overview_experience（默认，L4/L3）、process（L2）、technical（L1）、all（所有获准已登记类型，含来源、文稿、章节和原生 Run）。直接读取已有正文，不生成摘要 |
| 表示类型 Definition（兼容入口） | 一版阅读规则，如全文或摘要；不绑定具体材料。当前六类为 original、full、section、unit_digest、topic、domain |
| 表示实例 Realization | 固定材料按该类型可提供什么。direct可直接读，assemblable可组合已有字段，needs_generation缺少内容，stale表示过期，unsupported不支持 |
| 固定引用 FixedRef | 身份、修订与SHA256绑定材料；旧版不会随HEAD自动换新。文件以登记来源身份定位，不能传任意路径 |
| 查询 SearchReceipt | 保存范围、请求摘要、候选、缺口和到期时间；同一查询共享累计预算 |
| 材料包 MaterialPacket | 所选候选的直接材料、必要上下文、联想补充与缺口；canonical=false，不冒充规范记录 |
| 维护计划 MaintenancePlan | 把变化来源、受影响内容、阅读材料、建议动作及审查声明固定下来；通过预检后才可提交 |

L0–L4是规范知识层级，章节与完整/精简文稿使用独立类型，不强行分层。工作台每层只有一个入口，旧事件/地图须实际整理并保存新修订、更新索引，才成为新内容查询的经过/概览；不会仅靠显示名称转换类型。单元摘要来自已有检索说明或经验字段；旧表示中的主题与领域材料仍按原规则组合地图/文稿。需要新的统一解释时交给实际AI研究或审查，不能仅凭模板拼接标为已综合。

语义维护的可编辑类型包含 narrative、overview 与 v4 experience，并允许统一写服务支持的两条层级迁移路径。依旧必须交付和审查固定来源，不能放宽范围或伪造读取回执。计划暂不能完整交付的原生 Run/二进制依赖保持缺口；独立阅读并整理后，可通过已有 memory 预检/提交入口保存获准草案，在本次 Run 单列实际阅读、修订与回读，不把独立迁移写成维护计划已完成。

## 在工作台使用

AI按语料选择中英查询、技术问题英文补查以及每轮同义/关联扩词，使用[AI_READING](AI_READING.md)中的reading-recall计划入口；维护词库见[QUERY_TERMS](QUERY_TERMS.md)。下列手动界面保留普通查询行为，不在后台自动翻译；两者共用基础召回与固定来源边界。

1. 先按标准类型单选/多选并查找对象名称，选择归属对象或明确选择全局。默认空范围；高级筛选的null表示不限，[]表示没有匹配项。默认勾选“读取所选材料引用的必要依据”，允许在获准全局范围读取固定必要依赖；取消后上限收紧为所选范围。显式排除始终优先。
2. 填写问题，选内容来源和用途。探索可提供未复核候选；正式用途须说明具体适用范围，并逐claim核验当前来源与复核状态。
3. 开始查询后可取消。先检查候选、内容类型和缺口，再勾选组装。查询后改变条件会使旧选择失效，需重新查询。
4. 在候选上方选择组装、返回完整文稿、展开研究经过、展开技术内容或深化。展开只沿作者固定的 process_refs/technical_refs，旧经验可复用原有固定技术来源；L3 可直接到 L1。展开返回正文时包含必要上下文，以及明确启用且范围允许的已有联想补充；不扫描同 Owner 推断关联。所有动作沿用原query_id、排除项、范围上限和累计预算。
5. 阅读包中固定来源与省略内容。预算不足时保留完整块，避免把公式、变量定义或适用条件截断后当完整内容引用。

已有关系联想只提供导航。相似、共同术语或accepted_navigation不能替代正式支持。默认开放identity与lexical；高级选项可同时启用dense，复用本机标准384维多语言模型，与词法按RRF融合。sparse与独立graph召回通道仍未注册，短语/布尔不静默按普通关键词处理。旧记忆检索能力继续在原入口使用。

技术单元的检索说明和稳定正文块均可召回；正文命中的 `hits.representation_refs` 使用固定记录修订、SHA256及 `block:<block_id>` 定位，候选本身仍指向完整技术单元，组装时读取完整块及必要定义。词法和向量先按记录截取窗口，每记录最多保留四条实际命中诊断，不因多窗口/多表示重复加分。BM25越低越相关，向量余弦越高越相关；原分数不直接相加，也不作为科学可信度。

dense输入由已安装模型的tokenizer计量，最多512 token；默认预算允许一次查询编码、512输入token及512总token，输出token为0。超长或预算不足不会截断后悄悄继续；缺模型、存储占用、旧编码版本或向量水位不足返回partial并保留其他通道。capabilities的dense_provider说明内置召回实现，通用Foundation模型/分词策略仍未注册。向量读取最多返回候选预算个记录组，但本地相似度计算和SQL排序仍随获准索引规模增长；单次本地推理结束后检查取消与时间预算。

查询状态在当前服务进程内默认存活15分钟。服务重启或TTL到期返回EXPIRED；用户阅读时间不计执行墙钟。读取字节、输出文本、候选、图节点/边/跳数跨阶段累计。取消不能重置账本；新查询是新的操作，不能伪装成原查询无成本续接。

默认活动执行预算为300,000毫秒（5分钟）、读取16 MiB、输出80,000字符。界面可查看累计消耗和调整新查询预算，服务端仍施加各维上限。图像实际字节计入读取预算，正文/说明计入文本预算；图片base64传输不计作正文字符。重复组装也会核验当前权限和版本，缓存不绕过预算。

默认 freshness=current：只召回当前记录，组装及缓存回读也核验当前修订。显式允许历史时使用 allow_stale，旧修订有版本标记；历史扫描有界，不声称已检索无限历史。fixed 保持既定引用读取，不主动扫描历史。父文稿中的旧固定引用不会自动换新，无法满足当前版本条件时返回具体缺口。

“返回完整文稿”按命中所属的已有完整/精简文稿归并，同一篇仅显示一次。按原章节顺序展开规范技术块，并显示各块受控图表、固定来源和缺口；没有文稿时明确报告，不自动编写。请求不会把文稿变成新的规范记录。正式用途仍需逐结论核验，当前文稿整篇正式输出不支持时明确拒绝。

## 内容来源请求与兼容

新主入口在原 QueryRequest 中设置 `content_source` 为上述四个值，同时使用 `definition:{"key":"full","version":"1"}`、`fallback:"reject"`。省略 content_source 仍按旧表示查询。scope.owner_types 筛标准类型；scope 控制直接选择范围，scope_ceiling 控制依赖读取上限，来源选择只控制直接召回种类。旧 event/map 不进入新经过/概览，尚未整理时如实返回缺口。

`POST api/v1/materials/expand` 请求含 `query_id`、`candidate_ids`、`expected_request_digest` 和 `target:"process"|"technical"`；候选必须属于原查询。返回候选、边与缺口，继续在同一查询选择并 assemble。权限撤销、来源变化、排除、取消和预算同样约束展开。

expand 可设 `include_packet:true`，同时返回组装正文；`POST api/v1/materials/documents` 使用相同查询和候选身份返回完整文稿包。documents 列表的 part_indices 保留该篇文稿在 packet.parts 中的有序块位置，不能把不同技术单元的 figure:0 混为一张图。AssemblyPart.figures 携带经授权、核验与计量的图片引用、说明和data URL；客户端按块渲染。

CLI 一次调用可 `material-query search --request .local/query.json --expand technical --assemble`，只展开本页全部候选；交互挑选仍用工作台。没有关联不回退成原候选技术正文，展开失败返回非零。

## 给AI与脚本的入口

常用提示：

- “用 material-query 按这些归属检索方法全文，先看缺口再组包。”
- “用 association-exploration 比较这两份固定材料的机制、差异和迁移条件。”
- “用 semantic-maintenance 实际阅读这个维护包，逐项判断并保存可复核草案。”

方法源在 `automation/workflows/<名称>/SKILL.md`，发现入口在 `.agents/skills/<名称>/SKILL.md`。安装器只补缺，遇到用户修改保留并提示差异。需要安装新入口时运行：

```powershell
.\automation\python.ps1 automation/scripts/install_workspace_skills.py --name material-query --name association-exploration --name semantic-maintenance --apply
.\workbench.cmd material-query --help
.\workbench.cmd material-query definitions
.\workbench.cmd material-query search --request .local/query.json --assemble
```

请求字段取自[运行JSON Schema](../automation/schemas/material-query.schema.json)与[Python契约](../automation/scripts/material_query/contracts.py)。CLI输出JSON；partial、拒绝、失败返回非零。`--assemble`显式选择本页全部候选，不隐式翻页；进程退出后该查询不能续接。交互式挑选/加深使用工作台HTTP会话。

HTTP沿用工作台随机前缀、localhost Host/Origin校验，动作使用POST JSON：`api/v1/materials/start`、`poll`、`resume`、`cancel`、`assemble`、`expand`、`documents`、`deepen`、`associations`、`association-decision`、`structure`及`maintenance-plan/review/apply/status`。只读类型列表为`api/v1/representations/definitions`，能力为`api/v1/materials/capabilities`。客户端不能注入授权Context或剩余预算。

底层适配使用 `POST api/v1/materials/foundation/<action>`，`foundation/capabilities` 返回逐方法映射及动作列表。读取、验证、提交和索引动作绑定实际query_id，在同一会话内执行。CLI可用 `material-query foundation-capabilities` 查看，或以 `material-query foundation --request request.json` 执行单次动作；文件为 `{ "query": <QueryRequest>, "action": "describe", "request": { "refs": [<FixedRef>] } }`，query_id由该进程建立并注入。跨步骤计划与提交使用持久HTTP会话。

旧定义名使用无材料读取的 `POST api/v1/materials/foundation/definition-resolve`：请求为 `{"source_contract_version":"0.1","key":"topic_synthesis","target_definition_version":"1"}`，返回带 `mapping_version` 的 `topic/1`；`domain_synthesis` 对应 `domain/1`，其余四个原名称保持。将返回的 `definition` 用于新查询，来源、回退和生成边界仍按原请求核验。此动作不需要query_id；未知名称/版本明确拒绝，不按相近字符串猜测。能力回执的 `model_providers=[]`、`tokenizers=[]` 明示当前没有已注册模型或分词计量策略，四个模型预算维度只是各自的硬上限。

图关系同时保留 `references`、`input`、`same_entity`、`mentions` 和新版关系。同一固定端点对之间的不同关系分别返回；`legacy_relation` 保留原关系字段，`evidence_relations` 与固定证据按序对应。图节点按固定身份去重，同名不会自动合并；未登记的规范关系作为缺口报告。导航关系与科学复核仍分别处理。

主范围决定候选和输出，scope_ceiling.owner_ids与服务端权限的交集决定依赖正文的读取硬上限。必要依赖在硬上限外时，父材料也会被省略并报告缺口；扩大主范围不会自动扩大硬上限，显式排除始终优先。来源文件另受登记授权约束，owner范围不替代文件授权。

每次读取的basis包含固定引用、owner HEAD、索引水位、observed_at与basis_id。它记录实际观察，跨owner不表示全局同时快照。issues把局部问题拆为code、message、affected_refs和retry；只有已授权读取的对象才附固定引用。retry区分原请求重试、重新计划、等待外部条件变化和不可重试，warnings仍保留供阅读。

## 语义维护的责任边界

计划先交付实际正文context_items及read_receipt，默认动作defer。read_receipt只证明交付，不证明理解。人工或AI需要真正阅读、比较影响，填真实身份、reviewer_kind、说明和已读引用，再提交maintenance-review。AI不得把自己的判断标为人工意见。

review固定依据、原文和摘要，检查草案；apply按owner使用原服务的CAS和幂等request_id写新修订。旧版保留，撤回通过既有复核记录表达。跨owner不承诺全局原子性；分别检查已提交项、待办、索引状态与恢复回执。HEAD冲突后重新读取差异，不覆盖后来修改。索引失败不改变已提交事实，也不能报告整个维护完成。

需要新的摘要解释或重新综合时，首期由实际AI/人工在计划项的 `draft_json` 中提出符合现行 memory-v4 聚合契约的完整草案，再走 `maintenance-review → maintenance-apply → 固定版本读回`。review只保存不可变审查计划，apply之后才有新的规范内容身份。这是已有内容的外部AI维护路径；底层表示builder只组合已存字段，其 `content_proposals=[]` 不代表自动生成了新解释。

## 开发与迁移

`automation/scripts/material_query/`维护运行契约、预算、读取、策略和应用编排；`memory/`继续负责规范schema、存储和事务。生成器`material_query/generate_types.py`输出JSON/TypeScript契约，`--check`检查漂移。前端在`automation/frontend/`，构建资源及指纹在`automation/ui/workbench-assets/`；使用端无需Node。

为保留旧分类与关系语义，memory-v3兼容增加可选knowledge_facets以及same_entity/mentions引用关系；旧记录无需补字段或改写历史字节。分类中的尝试结果、知识角色和所声明置信度分别保存，不能从复核状态推断。缺分类的旧材料仍为unknown，允许纳入时在候选上标出未知维度。

分类字段、六种支持的v3内容、固定评估目标、旧数据映射及条件筛选边界见[知识分类手册](KNOWLEDGE_FACETS.md)。当前条件数组只匹配明确标签，不代替旧完整Applicability请求的业务时间与目标版本条件。

本功能不变更Python依赖或384维模型。前端开发新增的Node类型声明只用于构建，不进入Python依赖包。升级仍从独立新版目录执行`setup.cmd --target "旧工作区路径" --register --open`，保留旧工作数据、自定义Skill和回滚记录；不能直接覆盖旧目录。

基础召回的technical-blocks v4投影/编码版本需要重建派生索引；旧HEAD相同不能证明正文或新向量已覆盖。通过 `memory rebuild` 提交 `{"vector":"auto"}` 请求，或既有索引维护入口补齐；检查每Owner回执，模型不可用时词法可独立完成，向量保持缺口。不修改规范记录、外部原件或历史复核，不要求更新模型文件。

v0.1目标与43方法的继承关系见[继承映射](design/representation-query-v0.2/INHERITANCE.md)。实现验证、未注册策略、历史冻结fixture及尚待人工/第二台物理机验收的限制，在本轮固定Run和当前状态中分别记录；合成软件回归不证明真实业务模型有效。
