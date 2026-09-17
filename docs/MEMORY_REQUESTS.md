# 记忆请求示例：按任务读取

本页是 [版本记忆使用指南](MEMORY_USAGE.md) 的字段补充，按 2026-09-10 当前实现核对（保留旧版本示例）。只读当前任务需要的小节：保存记录看 1–3，研究续接看 4，材料包与总结看 5，复核纠错看 6，阶段巩固与使用反馈看 7–8，独立文稿与局部修改看 9。示例没有业务结论，也不是用户验收答案。修改请求字段时按 [文档维护约定](DOCUMENTATION_MAINTENANCE.md) 同步契约、使用指南与 Skill。

所有“替换为…”、示例修订号和 UUID 都是占位值，不能照抄提交。ID、HEAD、来源版本和指纹必须来自当前工作区的真实回执；新逻辑请求生成新 UUID，重试原请求保留原 UUID 与内容。正文公式使用 LaTeX 并定义变量与单位。

普通 `target_kind: "record"` 引用必须固定 `revision`，`sha256` 可为 null 或该修订的 `record_hash`；v3 技术单元的 evidence_refs、文稿的章节/技术块及 prose 依据要求实际 SHA-256，不能沿用 null。`content_hash` 用于内容去重及复核绑定，不是完整记录引用的指纹。其他目标类型按对应来源/结论指纹填写。

## 1. 公共入口与 CommitRequest

从工作区根目录使用 UTF-8 JSON 请求文件。动作签名以 [api.py](../automation/scripts/memory/api.py)、[cli.py](../automation/scripts/memory/cli.py) 为准；当前字段见 [v4 聚合 schema](../automation/schemas/memory-v4.schema.json) 和 [contracts.py](../automation/scripts/memory/contracts.py)。新 narrative/overview 默认 v4，分类 experience 显式用 v4，L1/独立文稿仍 v3；新记录按类型明确 `draft.schema_version`。未指定版本的旧 detail 形状、含 `report` 的旧 map 按 v2 解释；历史保持原字节，不靠改 level 或重新计算旧哈希迁移。

同一 ID 的类型迁移只允许 `event→narrative`、`map→overview`：`put_record` 保留 `record_id` 与实际 `expected_revision`，draft 必须是完整 v4 正文，有 `change_reason`，且 `sources` 含指向上一修订的 `target_kind:"record"`、ID、revision、`sha256:上一修订record_hash`、`relation:"references"`。HEAD 与来源检查照常生效；既有普通草案不会自动迁移。新经过的可选 `occurred_at`、`failure` 及研究关联用于保留实际时间与失败边界。

提交封套的 `schema_version` 当前接受 1/2/3，与每条 draft 的记录版本分别校验。下面封套使用 3；旧封套可兼容，不会因此把旧正文改成 v3 技术块。

```powershell
.\workbench.cmd memory list-owners
.\workbench.cmd memory inspect RES-实际对象ID
.\workbench.cmd memory validate-draft --request .local/request.json
.\workbench.cmd memory commit --request .local/request.json --dry-run
.\workbench.cmd memory commit --request .local/request.json
```

下面是完整可解析形状，尚需换成实际对象与内容。`expected_head` 从 inspect 的 `head.commit_id` 取得；只有该对象确实尚无 HEAD 才使用 null。`actor` 是声明的执行者，不是身份认证，AI 不填写为 human。服务生成记录 ID、时间、修订与哈希。

```json
{
  "schema_version": 3,
  "request_id": "11111111-1111-4111-8111-111111111111",
  "actor": {
    "kind": "ai",
    "id": "替换为实际执行者"
  },
  "owner_id": "RES-替换为实际对象ID",
  "expected_head": null,
  "operations": [
    {
      "op": "put_record",
      "client_key": "local-experience",
      "draft": {
        "schema_version": 3,
        "owner_id": "RES-替换为实际对象ID",
        "kind": "experience",
        "title": "替换为本次记录标题",
        "body_markdown": "替换为可独立阅读的完整正文：对象和问题背景、输入与适用条件、实际认识或做法、关键依据、简单结论与限制。不要只在payload补充这些信息；未知如实说明。",
        "keywords": [
          "输入条件"
        ],
        "payload": {
          "problem_structure": "比较结果受输入条件影响",
          "recommendation": "比较前核对输入版本与适用范围",
          "applicable": [
            "已核对的输入与环境"
          ],
          "prohibited": [
            "未经验证的其他输入与环境"
          ],
          "failure_modes": [
            "输入版本不一致导致无法比较"
          ],
          "retry_conditions": [
            "获得一致输入后重试"
          ],
          "claim_refs": [],
          "claims": [],
          "missing_refs": []
        },
        "sources": [],
        "provenance_gap": "示例尚未绑定实际来源；提交前补齐或如实说明缺口",
        "record_reason": "保留后续选择方法所需的依据与边界",
        "discovery": "owner_only",
        "sensitivity": "internal",
        "level": "L3"
      }
    }
  ]
}
```

更新时将 operation 的 `client_key` 换成 `record_id` 和 `expected_revision`，保留完整草案并填写 `change_reason`；不要提交旧记录中的服务字段（如 record_hash、created_at）。一个批次只写一个 owner。可先分次提交目标、路线，再用回执固定引用建立检查点；不要猜测尚未生成的 MEM ID。

### 新 L2–L4 草案

所有 Owner 的正文先满足[单条独立可读要求](RESEARCH_RECORDING.md#每条记录必须独立可读可以正确复用)，再填写结构字段。以下是内容组织提示，不是必须照抄的标题或可直接提交的业务结论：

L0–L4 是通用内容压缩与发现层，不要求材料必须具有研究过程。新建或实质更新后预期长期复用的 Owner 至少准备一条自足 L4；简短经验可只有 L4，并把完整内容直接写入 `body_markdown`。生成前除主体目标外，还要检查可迁移方法、失败/反例、版本/参数/工况限制和偶然发现：独立判断写 L3，方法/定义/计算细节写 L1 `retrieval_description` 与 blocks。没有相应内容时不补空层。

- L2：本条问题背景、对象与输入条件；实际尝试/选择及理由；关键观察、失败或转折；简单结论与未解决问题。说明当事者及来源，事后补写不冒充当时记录。
- L3：具体问题和适用前提；可复用观察/结论/假设/做法；支撑事实与固定出处；反例、不适用范围及必要验证条件。
- L4：对象用途和问题范围；主要方法与必要定义；已有结果和当前阶段；限制和未决事项。

正文必须承载上述必要上下文；不得仅在 payload 中写全，再提交一句“结果见前文”。固定来源不能代替关键事实的解释。AI 在同一次任务中逐条脱离聊天及相邻记录回读、补齐后提交；结构校验通过不证明独立性或科学正确性。`process_refs`/`technical_refs`/`experience_refs` 是展开关系，`supports`/`input` 是依据关系，association 是导航关系；相似、同一 Owner 或联想候选不能自动改写为证据。

沿用上述公共 metadata 和提交封套；draft 指定 `schema_version:4`，kind/level 分别为 narrative/L2、experience/L3、overview/L4。三类都要求非空完整 `body_markdown`，结构字段与正文一致。具体字段与写作职责见 [记录标准](RESEARCH_RECORDING.md#新经过经验与概览的写作及展开)。

narrative payload 至少含 claims、question、stages、limitations、process_refs、technical_refs、experience_refs；stages 每项含 situation/action/reason/outcome/evidence_refs。overview payload 至少含 claims、question、methods、results、current_stage、limitations、open_questions 及上述三类 refs。experience 沿用原 payload 并增加 knowledge_type、process_refs、technical_refs。无已保存关联时用空数组；有引用时必须实际回读正整数 revision 和 SHA-256，不能使用下方旧通用引用示例的 null 指纹。

旧 event/map 不直接改 kind 或 level；先实际整理正文，另存 narrative/overview 并固定引用旧依据。保存成功不继承来源的复核状态。

## 2. 固定引用与来源指纹

每个 Ref 都有下列六个字段。普通 MEM 引用固定正整数 revision，可以使用 sha256=null；这是规范记录的版本身份。第 3 节 v3 技术单元依据和第 9 节文稿引用另要求真实 record_hash。

```json
{
  "target_kind": "record",
  "target_id": "MEM-替换为已保存记录ID",
  "revision": 1,
  "sha256": null,
  "locator": "正文",
  "relation": "references"
}
```

`target_kind=file` 使用登记的 source_id、revision=null、获准原文件字节的 SHA-256。`owner` 与 `claim` 使用 revision=null、回源规范 SHA-256；原生对象由 EvidenceGraph 规范化后计算，不能把 inspect/list-owners 的原文件 fingerprint 当成这个哈希。后者仅适用于 adopt-owner 的 expected-hash。

优先直接保留真实 `search.candidates[i].source_ref`、材料包 `manifest.source_refs` 或 `manifest.navigation_refs` 的完整 Ref，再交给 expand 回源检查。不要从标题猜 ID，或在来源变化后静默替换旧引用的哈希。

下面的 Python 片段说明回执结构，变量代表已经取得的真实结果，不是额外 CLI 动作：

```python
# commit_result 来自成功保存；用 client_key 找到对应项。
saved = next(x for x in commit_result["record_results"]
             if x["client_key"] == "local-experience")
fixed = {"target_kind": "record", "target_id": saved["record_id"],
         "revision": saved["revision"], "sha256": None,
         "locator": "正文", "relation": "references"}
# search_result 为真实 search 回执；保留其版本，不从当前文件补造。
source_ref = dict(search_result["candidates"][0]["source_ref"])
# 原生 Run → CLM → 文件的一跳导航同样使用回执里的完整固定引用。
next_refs = packet["manifest"]["navigation_refs"]
```

实际构造方式见 [导航回归](../automation/tests/test_memory_navigation.py) 与 [证据回归](../automation/tests/test_memory_evidence.py)。实现侧需要规范 claim 指纹时使用 `EvidenceAdapter(service).resolve_claim(claim_id)["sha256"]`；它不是 inspect 的文件哈希。普通用户无需调用内部函数。

`sources` 说明正文来源；`supports`/`input` 用作依据，`background`/`references` 不提升可信状态。已存在原生 Run 时直接引用它，不把同一次执行再复制为 MEM event。确有新的观察或决策才另记事件并链接原 Run。

## 3. 按记录类型填写 payload

下列各段只展示 payload，须放入第 1 节草案并同步 kind。保留共有字段 owner_id/title/body_markdown/sources/record_reason/discovery/sensitivity；没有来源时如实填写 provenance_gap，有实际来源时填固定 Ref。关键词帮助发现，不能代替来源。

### source：来源摘录

```json
{
  "source_ref": {
    "target_kind": "record",
    "target_id": "MEM-替换为已保存记录ID",
    "revision": 1,
    "sha256": null,
    "locator": "正文",
    "relation": "references"
  },
  "acquisition": "original_link",
  "completeness": "unknown",
  "acquired_at": null
}
```

示例 source_ref 需换为实际原文 Ref。original_link 只记录原文链接；verbatim_export 要提供准确 lines:/chars: 定位并逐字校验正文；excerpt 表示受控摘录；摘要写 experience，不能称为逐字原文。OCR 结果需如实记录获取方式和缺口，不能添加不存在的 acquisition 枚举。completeness 保留完整、部分或未知的真实情况，acquired_at 未知可为 null。

### detail：完整技术单元（L1）

新写作使用 `schema_version:3`、`kind:"detail"`、`level:"L1"`、`body_markdown:""`，正文只保存在 payload.blocks。`unit_type` 区分 experiment/method/derivation/analysis。下面是尚无实验结果的方法草案 payload；放入第 1 节完整 draft 时，应同步标题、保存原因和真实 sources，若目前没有依据则显式填写 provenance_gap。

```json
{
  "unit_type": "method",
  "retrieval_description": {
    "question": "替换为该方法需要回答的问题",
    "method": "替换为实际方法和选择理由",
    "key_findings": ["尚无经过实验核验的发现；此处仅示范请求结构"],
    "applicable": ["替换为已知的适用条件；未知时明确待核对"],
    "not_applicable": ["不能把本草案当作已执行实验的结果"],
    "limitations": ["尚需补齐实际依据与适用性验证"]
  },
  "run_ref": null,
  "evidence_refs": [],
  "blocks": [
    {
      "block_id": "definitions",
      "role": "definitions",
      "markdown": "## 定义与前提\n替换为真实变量、单位、适用假设和固定依据。",
      "requires_block_ids": []
    },
    {
      "block_id": "method",
      "role": "methods",
      "markdown": "## 方法\n说明可核验的方法步骤、选择原因和限制；未执行时不补造数值结果。",
      "requires_block_ids": ["definitions"]
    }
  ],
  "figures": [],
  "missing_refs": []
}
```

`retrieval_description` 的六项必须明确填写，用于发现候选；不能代替完整正文。block_id 在同一单元内唯一、无 `#`，修改时保持稳定；requires_block_ids 只引用同单元必需块，不重复、不成环。块的 role 可为 introduction/definitions/methods/inputs/derivation/results/discussion/limitations/appendix。完整正文保留参数、公式、可核验步骤、结果和限制，不只给日志链接。

实验 `unit_type:"experiment"` 必须提供真实 `run_ref`；方法、推导和分析没有执行时可为 null，但须有固定依据或显式来源缺口。`run_ref` 使用原生 Run 的 owner Ref 和证据对象规范指纹，不使用 list-owners 的原文件 fingerprint。evidence_refs 每项必须带真实 SHA；记录引用还固定 revision。图表使用已登记附件及 `payload.figures`，正文 `![图注](figure:0)` 对应该单元第一个图示，不能借占位符声称已取得图像。

[v2 detail 请求](../automation/schemas/memory-detail-v2.example.json) 仅供维护旧记录：其 question/method/steps/inputs/parameters/formulas/results 等字段与 body_markdown 继续按 v2 校验；它不是当前新技术单元模板。完整写作、兼容和回读标准见 [研究分层记录](RESEARCH_RECORDING.md)。

### experience：经验与迁移边界（L3）

```json
{
  "problem_structure": "比较结果受输入条件影响",
  "recommendation": "比较前核对输入版本与适用范围",
  "applicable": [
    "已核对的输入与环境"
  ],
  "prohibited": [
    "未经验证的其他输入与环境"
  ],
  "failure_modes": [
    "输入版本不一致导致无法比较"
  ],
  "retry_conditions": [
    "获得一致输入后重试"
  ],
  "claim_refs": [],
  "claims": []
}
```

### event：决策、事件与失败

以下是保留的旧事件示例，payload 配合 `kind="event"`、`level="L2"`，v2 历史形状也兼容。跨 Run 决策将比较观察写入 observation、选择与理由写入 decision，并在 run_refs/sources 固定参与 Run 或经验；无失败时 failure=null。它记录本次决策，不复制原 Run 的完整输入输出，也不表示再次执行原实验。

```json
{
  "occurred_at": null,
  "question_refs": [],
  "goal_ref": null,
  "route_ref": null,
  "action": "核对一份已登记材料",
  "observation": {
    "value": null,
    "reason": "not_acquired",
    "note": "尚未取得，需要后续核对"
  },
  "decision": null,
  "decision_refs": [],
  "run_refs": [],
  "failure": {
    "category": "insufficient_evidence",
    "tested_scope": "本次实际读取的材料范围",
    "result": "缺少对照输入，不能完成比较",
    "cannot_infer": "不能推断方法无效或其他输入下的结果",
    "retry_conditions": [
      "补齐获准的对照输入"
    ]
  },
  "claims": []
}
```

failure.category 分别为 execution（程序未完成）、no_improvement（执行成功但没有改善）、counterexample（发现反例）、insufficient_evidence（证据不足）；result、tested_scope、cannot_infer、retry_conditions 都要按真实结果写。不能把结论撤回改写成历史执行失败。

用户要求保留一次失败经过时，应保存上述结构化 failure；experience.failure_modes 适合经验风险提示，不能单独代替失败经过。Research阶段结束检查L0–L4覆盖，已有经验/地图可以更新而不重建；无法提炼经验时说明证据缺口，不编造规律。

observation 和 budget_remaining 的未知值使用 UnknownValue：value=null，reason 为 unknown/not_acquired/not_applicable，note 解释原因。时间字段允许的 null 表示未知时间，不能据此虚构发生顺序。未知余额不能改成 0，也不能直接给 budget_remaining=null。

需要单独复核的断言放入 event/experience 的 claims 数组，每项如下。claim_id 需按实际对象的身份管理分配并保持唯一；不能借用已有 CLM 表达另一个断言。没有断言可保持空数组。

```json
{
  "claim_id": "CLM-替换为本次唯一断言ID",
  "statement": "替换为可独立检验的具体断言",
  "kind": "inference",
  "scope": "替换为实际适用范围",
  "evidence_refs": []
}
```

## 4. 问题、目标、路线与续接

以下也是 payload；goal_ref 必须指向已保存的 goal，route_refs 指向 route，question_refs 指向 question，不能因为 Ref 形状正确就引用其他 kind。

### question：问题

```json
{
  "question": "现有依据能否支持本次方法选择？",
  "status": "open",
  "decision_affected": "是否继续使用当前方法",
  "missing_evidence": [
    "缺少当前输入下的比较"
  ],
  "resolution_refs": [],
  "replacement_ref": null,
  "reopen_reason": null
}
```

### goal：目标

```json
{
  "objective": "查清当前输入下的差异原因",
  "constraints": [
    "仅使用获准材料"
  ],
  "success_criteria": [
    "能追溯到固定输入和比较结果"
  ],
  "previous_goal_ref": null,
  "change_impact": "首次设置；尚无旧目标"
}
```

### route：路线

```json
{
  "goal_ref": {
    "target_kind": "record",
    "target_id": "MEM-替换为已保存记录ID",
    "revision": 1,
    "sha256": null,
    "locator": "正文",
    "relation": "references"
  },
  "hypothesis": "差异可能与输入条件有关",
  "status": "planned",
  "attempt_refs": [],
  "blocker": null,
  "next_step": "核对输入版本",
  "reopen_condition": "获得新的输入或反证",
  "replacement_ref": null
}
```

### checkpoint：暂停检查点

```json
{
  "goal_ref": {
    "target_kind": "record",
    "target_id": "MEM-替换为已保存记录ID",
    "revision": 1,
    "sha256": null,
    "locator": "正文",
    "relation": "references"
  },
  "route_refs": [],
  "completed_refs": [],
  "question_refs": [],
  "next_step": "补齐输入后继续比较",
  "prerequisites": [
    "取得获准的对照输入"
  ],
  "stop_reason": "等待输入",
  "budget_remaining": {
    "value": null,
    "reason": "not_acquired",
    "note": "尚未取得，需要后续核对"
  }
}
```

question 状态为 open/investigating/blocked/resolved/superseded。resolved 必须有固定答案/决策 resolution_refs；superseded 必须引用另一个问题。已结束问题重开到 open/investigating 要写 reopen_reason；后续用 question-validity 检查解决依据是否仍有效，历史 resolved 不自动保证当前有效。

goal 更新必须将 previous_goal_ref 固定到自身上一修订，并说明 change_impact。保存 goal 时 store 更新 `manifest.pointers.goal`，policy 没有 current_goal_ref。旧路线保留旧 goal_ref；更换目标建立新路线。route 状态为 planned/active/blocked/closed/superseded；blocked 写 blocker，active/closed 不保留未解决 blocker，重开 active 需要新固定来源和 change_reason，原 attempt_refs 不删除。

读取经过与续接分别用 `history` 和 `resume`。history 分页保存第一次响应的 basis_heads 后原样传回；HEAD 变化需重新读取，不拼接不同快照。resume 只装配暂停材料，不执行下一步。

动作 `history`：

```json
{
  "owner_id": "RES-实际对象ID",
  "offset": 0,
  "limit": 50
}
```

动作 `resume`：

```json
{
  "owner_id": "RES-实际对象ID",
  "budget": 8000
}
```

动作 `question-validity`：

```json
{
  "question_ref": {
    "target_kind": "record",
    "target_id": "MEM-替换为已保存记录ID",
    "revision": 1,
    "sha256": null,
    "locator": "正文",
    "relation": "references"
  },
  "scope": "实际适用范围"
}
```

## 5. 材料包、阶段地图与跨对象总结

`context` 是公共材料包动作；不存在 memory build-context、deepen 或 formal-projection CLI。探索与正式读取都用 purpose，formal 必须给 scope。

```json
{
  "query": "当前任务的问题结构",
  "purpose": "exploration",
  "stage": "focus",
  "owner_ids": [
    "RES-实际对象ID"
  ],
  "include_ids": [],
  "full_ids": [],
  "exclude_ids": [],
  "budget": 8000
}
```

owner_only 记录需要显式选择所属 owner_id/owner_ids；仅传固定 refs 不会扩大其可发现范围。读取 context_text，并检查 manifest 的 missing、required_not_full、basis_heads 与 budget；来源未入正文不能因为出现在元数据里就声称已读。预算按 Unicode 码点计算；不能手删边界以挤入正文。

继续扩展时仍调用 context，请求为 `{"feedback_from": 上次完整材料包或manifest}`；该写法是结构说明，保存为 JSON 时放入真实对象。系统继承范围、排除、目的和预算，由 focus→investigate→wide 最多两次。只读取指定固定版本用 `expand`：

```json
{
  "refs": [
    {
      "target_kind": "record",
      "target_id": "MEM-替换为已保存记录ID",
      "revision": 1,
      "sha256": null,
      "locator": "正文",
      "relation": "references"
    }
  ],
  "selection": {
    "owner_id": "RES-实际对象ID",
    "exclude_ids": [],
    "full_ids": []
  },
  "budget": 8000
}
```

### map：阶段地图

```json
{
  "topic": "当前问题及证据导航",
  "goal_refs": [],
  "route_refs": [],
  "result_refs": [],
  "question_refs": [],
  "conflict_refs": [],
  "next_steps": [
    "补齐当前缺口"
  ],
  "coverage": {
    "owner_ids": [],
    "source_versions": [],
    "missing": [
      "尚未纳入其他对象"
    ]
  }
}
```

### representation：检索表示

```json
{
  "target": {
    "target_kind": "record",
    "target_id": "MEM-替换为已保存记录ID",
    "revision": 1,
    "sha256": null,
    "locator": "正文",
    "relation": "references"
  },
  "slot": "boundary",
  "text": "仅用于已核对输入；其他输入待验证",
  "boundary_refs": []
}
```

map 的 coverage 应列出真正纳入的 owner_ids、source_versions 与 missing；不得用“全局总结”掩盖未读对象。representation 只表示 target 的固定版本，text 保留适用/禁用边界，不能当第二份事实或独立复核依据。

先 `summaries-prepare` 固定选中对象，再由人/AI 阅读正文形成 experience 或 map：

```json
{
  "query": "比较所选对象中的条件与差异",
  "owners": [
    "RES-实际对象A",
    "RES-实际对象B"
  ],
  "budget": 8000,
  "selection": {
    "exclude_ids": [],
    "full_ids": []
  }
}
```

准备响应不等于总结完成。`summaries-save` 请求字段如下：request_id、actor、owner_id、expected_head、draft、basis_heads，可带 schema_version/dry_run；更新还需 record_id、expected_revision。draft 是完整 experience/map 草案，sources 取准备回执的 source_refs；basis_heads 原样保留准备回执的整个映射（无 HEAD 使用服务给出的字符串 "none"），不要换成新 HEAD 绕过冲突。

```python
summary_request = {
    "request_id": new_request_uuid, "actor": actor,
    "owner_id": destination_owner_id, "expected_head": destination_head,
    "draft": completed_summary_draft,
    "basis_heads": prepared["basis_heads"],
}
```

无新增来源但有新解释也可以保存，更新应写 change_reason。新总结与新 CLM 不继承来源的 accepted；STALE_BASIS 时重新准备、阅读并核对解释。

## 6. 复核、反证与影响检查

通过专用 review 动作复核某个 CLM，不能直接 put_record review 或在经验里手写 accepted。下面是 MEM claim 的请求形状；expected_content_hash 取承载该断言的 inspect.record.content_hash，既不是 record_hash，也不是 claim Ref 的 sha256。evidence_refs 要替换为本次实际复核依据，accepted 要有 supports/input 依据且满足 scope、来源与上游有效性。

```json
{
  "request_id": "22222222-2222-4222-8222-222222222222",
  "actor": {
    "kind": "ai",
    "id": "实际执行者"
  },
  "owner_id": "RES-实际对象ID",
  "expected_head": "实际COM-ID",
  "target_claim_id": "CLM-实际断言ID",
  "expected_content_hash": "替换为承载记录content_hash",
  "state": "disputed",
  "reason": "新证据与原断言冲突，待核对",
  "scope": "实际适用范围",
  "evidence_refs": [],
  "replacement_claim_id": null
}
```

人工或已授权且适用的流程才提供复核依据；actor 字段本身不授予权限。状态包括 not-reviewed/accepted/disputed/retracted/superseded。superseded 需 replacement_claim_id，其他状态不填替代 ID。原生 Run 的 CLM 由同一 review 动作转交既有证据系统，不创建重复 MEM 事件；其目标指纹规则由原生证据入口负责，不套用上面的 MEM expected_content_hash。

发现依据失效后，先读取反向影响，不自动重写所有下游记录：

```json
{
  "changed_ids": [
    "CLM-实际变化断言ID"
  ]
}
```

核对来源独立性用 `source-lineage`：

```json
{
  "target_ids": [
    "MEM-实际记录ID"
  ]
}
```

据实际情况标记 disputed/retracted/superseded，保留原记录、旧执行状态和复核历史；受影响问题用 question-validity 查看，报告和地图按影响范围另行修订。查询次数与引用次数不能增加科学可信度。

## 7. prepare → consolidate

`prepare` 只准备当前对象自上次巩固以来的变化、外部影响和未处理事项：

```json
{
  "owner_id": "RES-实际对象ID",
  "trigger": "manual"
}
```

可选 since_commit 使用实际 COM-ID。保存原样 basis（包含 basis_hash、basis_heads、source_states）；不要自行重算或删减。`consolidate` 的请求构造如下：

```python
request = {
    "request_id": new_request_uuid, "actor": actor,
    "owner_id": owner_id, "expected_head": current_head,
    "basis": prepared_basis,
    "reason": "说明本次巩固依据与范围",
    "decisions": [{"target": fixed_item_from_basis,
                   "action": "defer", "reason": "尚缺输入，保留待办"}],
    "operations": [],
}
```

decisions 只能处置 basis.changed/affected/remaining 中的固定对象，action 为 retain/revise/defer。retain 保留且结束本次处置，defer 与未处置项进入 remaining。revise 的 target 指向本批实际新修订（旧 revision+1），同批 operations 必须包含 record_id/expected_revision 与完整新草案。跨 owner 影响保留到对方的处理清单，不能在本批越界写入。来源或 HEAD 变化则重新 prepare。巩固保存不自动完成复核，也不自动执行 next_steps。

## 8. 检索后的真实使用反馈

`feedback` 使用实际 search 回执的 query_id（QMEM-UUID）；它与 context 的 feedback_from 扩展不同。target 可以是实际命中，也可以是后来发现的漏检固定记录。

```json
{
  "request_id": "33333333-3333-4333-8333-333333333333",
  "actor": {
    "kind": "ai",
    "id": "实际执行者"
  },
  "owner_id": "RES-实际对象ID",
  "expected_head": "实际COM-ID",
  "query_id": "QMEM-44444444-4444-4444-8444-444444444444",
  "target": {
    "target_kind": "record",
    "target_id": "MEM-替换为已保存记录ID",
    "revision": 1,
    "sha256": null,
    "locator": "正文",
    "relation": "references"
  },
  "label": "missing",
  "note": "说明实际漏检及其与当前问题的关系",
  "adopted_in": null
}
```

label 为 missing/irrelevant/invalid_analogy/lost_boundary/stale/adopted/outcome；outcome 必须用 adopted_in 引用实际后续 Run 或 event，不能用计划代替执行。反馈记录不改 CLM 复核状态。

## 9. 独立文稿、章节与局部修改

新文稿用 `document` 和 `document_section`，两者 `schema_version:3`、`level:null`、`body_markdown:""`。新 L4 用 overview 保存概览，旧 map 保留知识地图；`map.payload.report` 只保留旧编排兼容，不用于新文稿。完整过程为 `research_process`，精简报告为 `research_report`，分别维护目的、读者、范围与有序章节，共用固定证据。

### 先保存单元，再保存章节和文稿

L1 通过普通 `commit` 保存并 `inspect` 回读。下面的 `unit`、`section_record` 是实际回读记录，`owner_id` 是真实归属；片段展示 draft 构造，不是额外的 CLI 动作。将每个 draft 分别放入第 1 节 CommitRequest，使用当前 HEAD 提交，回读后再固定引用下一层，不能用空 SHA 连接未保存的草案。

```python
# unit 来自 inspect.record；完整 record_hash 固定整条修订与来源。
fixed_unit = {
    "target_kind": "record", "target_id": unit["record_id"],
    "revision": unit["revision"], "sha256": unit["record_hash"],
    "locator": "完整技术单元", "relation": "references",
}
section_draft = {
    "schema_version": 3, "owner_id": owner_id,
    "kind": "document_section", "level": None,
    "title": "替换为实际章节标题", "body_markdown": "", "keywords": [],
    "payload": {
        "section_key": "method", "title": "替换为实际章节标题", "role": "methods",
        "blocks": [
            {"type": "prose", "markdown": "替换为实际背景、选择理由及与相邻章节的衔接。",
             "evidence_refs": [fixed_unit]},
            # 省略 block_ids 读取该固定单元的全部正文；按需可选真实块 ID。
            {"type": "unit", "ref": fixed_unit},
        ],
        "watch_refs": [], "missing_refs": [],
    },
    "sources": [fixed_unit], "provenance_gap": None,
    "record_reason": "替换为编排本章的实际原因",
    "discovery": "owner_only", "sensitivity": "internal",
}
```

章节 block 只能为 prose 或 unit。unit 省略 block_ids 表示读取固定单元全部正文；对 v3 单元显式给非空 block_ids 时，按原顺序返回所选块和 requires_block_ids 的前提闭包。空数组、重复 ID、缺失块或循环依赖会被拒绝；v2 detail 没有稳定块，省略选择字段读取原正文。同一章节不能重复插入同一个单元修订，合并其所选块即可。

```python
# section_record 是上一步已保存并回读的章节；不可从章节标题猜 ID。
fixed_section = {
    "target_kind": "record", "target_id": section_record["record_id"],
    "revision": section_record["revision"], "sha256": section_record["record_hash"],
    "locator": "完整章节", "relation": "references",
}
document_draft = {
    "schema_version": 3, "owner_id": owner_id,
    "kind": "document", "level": None,
    "title": "替换为实际研究过程题名", "body_markdown": "", "keywords": [],
    "payload": {
        "document_type": "research_process",
        "purpose": "替换为本文要解释的问题和用途",
        "audience": "替换为目标读者", "scope": "替换为证据覆盖范围",
        "common_refs": [], "section_refs": [fixed_section],
        "watch_refs": [], "missing_refs": [],
    },
    "sources": [fixed_section], "provenance_gap": None,
    "record_reason": "替换为保存本次文稿的实际原因",
    "discovery": "owner_only", "sensitivity": "internal",
}
```

一章仅示范结构；实际文稿按问题、方法、技术单元、讨论、结论组织。section_key 在同一文稿内唯一，section_refs 不重复；实验章节位于 discussion/conclusion 之前。精简报告另存 `document_type:"research_report"` 并编写适合其读者的章节，不能只改名称。prose、common_refs、section_refs 与 unit Ref 都固定真实 SHA；缺失事实不能用占位段落充当完成。

### 回读、目录与章节材料包

`document` 和 `outline` 的请求可用下面的形状；省略 document_type 时默认 research_process。同类型多份文稿按最近更新时间选择，确定修改目标后用实际 document_id 固定它；需要历史时再加正整数 revision，revision 必须与 document_id 同用。

```json
{"owner_id":"RES-实际归属ID","document_type":"research_process"}
```

```powershell
.\workbench.cmd memory document --request .local/document-request.json
.\workbench.cmd memory outline --request .local/document-request.json
```

下例中的 section_id 取 outline.sections 返回的章节记录 ID，不是 section_key 或标题。该动作 budget 使用 max_chars 对象；普通 context/expand 的 budget 仍为整数。

```json
{
  "owner_id": "RES-实际归属ID",
  "document_id": "MEM-实际文稿ID",
  "section_id": "MEM-实际章节ID",
  "selection": {"include_ids": [], "full_ids": [], "exclude_ids": []},
  "budget": {"max_chars": 20000}
}
```

```powershell
.\workbench.cmd memory section-context --request .local/section-request.json
```

读取 context_text，并检查 manifest.read_refs、omitted、missing、required_not_full、budget 和 basis_heads。选择规则保留排除项与必要定义；预算按输出字符计算，不证明底层仅解析一个章节。默认 max_chars=20000，可设 1–1000000；它不是 token 数量。

### 变化关注、影响与兼容

`document-impact` 请求使用真实 owner_id，可带 document_id/revision 或 document_type。它比较固定引用、watch_refs 和两类文稿所用版本；返回 changes、affected_section_ids、uncovered_unit_ids，scientific_review 为 not_evaluated。新修订提示不等于旧结论错误，新增单元也不自动进入文稿。

watch_refs 可为 revision（record_id、baseline_revision、baseline_record_hash）或 new_unit（owner_id、baseline_head、baseline_unit_ids）。所有基线必须来自实际观察；可从 outline.watch_baseline 取得当前对象 HEAD 与单元集合。它们是变化关注，不能当作 supports/input 证据边或读取授权。

修改时先 outline → section-context → document-impact，按实际影响修订必要章节，再修订文稿的 section_refs。两类文稿可以共享单元，但同时引用同一单元的不同修订会出现 DOCUMENT_BASIS_MISMATCH；核对后局部更新，不自动换成最新来源。

保存后用 document 通读，检查 document_source、report.complete、report_coverage、report_version_hints 与 source_issues。complete 只表示本次组装的来源检查，没有替代科学复核或读者验收。include_records:true 可显式附加规范记录卡，默认不重复加入全文。

缺少独立过程文稿时，document 可回退到旧 `map.payload.report`，report_record_id 仅供该回退路径选择旧地图；它不覆盖已选中的独立文稿。缺少独立 research_report 时返回未编排及 DOCUMENT_MISSING，不把旧长文当简报。v1/v2 历史、旧地图和固定哈希原样保留。详细写作与图示规范见 [报告编排](RESEARCH_RECORDING.md#连贯报告的编排)。

## 10. 如何理解结果与失败

| 结果或错误 | 含义与下一步 |
| --- | --- |
| valid / dry_run | 预检结果；尚未保存，不代表现实结论有效 |
| save_status=committed / no_change | 已提交或语义未变化；仍检查 index_status 和证据状态 |
| INDEX_PENDING（退出码 3） | 索引待处理；按回执确认是否已保存，使用 reconcile，不重复创造记录 |
| INVALID_ARGUMENT / INVALID_SCHEMA（2） | 参数/字段错误；按 errors 中的定位修正 |
| NOT_FOUND / UNRESOLVED_REFERENCE（2） | 对象或固定来源未找到；核对登记、版本与权限，不补造 ID |
| ACCESS_DENIED / UNSAFE_PATH（4） | 权限或路径边界拒绝；不扩大读取范围 |
| VERSION_CONFLICT / STALE_BASIS / IDEMPOTENCY_CONFLICT（5） | HEAD、来源或请求身份冲突；重新读实际版本，保留原草稿与回执 |
| LOCKED（6） | 存在事务锁；检查 recover，不直接删锁 |
| INTEGRITY_ERROR / STORAGE_ERROR（7/8） | 指纹、存储或完整性异常；保留现场与恢复回执 |
| EVIDENCE_INELIGIBLE / INVALID_TRANSITION（9） | 证据或状态转换不成立；补实际依据或改为允许的状态 |
| CAPABILITY_UNAVAILABLE（10） | 可选能力不可用；按真实降级结果说明限制 |

UnknownValue 是业务记录里的明确未知，不是工具执行失败。正文为空、formal 无可用断言或材料包有 missing 也不能自行解释为“没有问题”。最终交付说明保存 ID/修订、实际验证、尚存缺口，避免把字段校验通过写成业务或用户验收通过。
