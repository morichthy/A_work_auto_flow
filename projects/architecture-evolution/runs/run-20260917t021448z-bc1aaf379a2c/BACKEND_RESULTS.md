# 阅读内容与证据详情：后端实施结果

## 实际根因与改动

1. SRC 图片旧 detail 只有登记摘要，没有返回图片；L1 的 `figure:N` 也未交付对应媒体。现在只对选中、登记允许的工作区 PNG/JPEG/WebP 读取字节（单图最多 8 MiB），核固定 SHA256，读取后再查登记，返回受控 data URL。登记撤权、Owner 越界、指纹变化均拒绝。普通文字详情仍不扫描/哈希全库原件。
2. 实际无关警告来自 `TOOL-WORKSPACE-001`：索引 native_ref 指向 `tools/registry.json`，身份 `tool_id` 实在 `tools[]` 成员，旧代码错误检查根对象字段。现在按明确 ID 精确选择唯一工具成员，普通卡仍检查根身份；真正失效项隔离，不将全局目录警告附到无关详情。修复后实际工具标题为 workspace-cli，Catalog warnings 为空。
3. 旧详情只拼 `body_markdown` 和简单 blocks，漏掉 document 的 section_refs 与 section 中 type=unit 的固定技术单元。现在依次固定展开 document→section→unit，按 block_ids 加必要依赖块，不改用最新版本；排除检索投影 retrieval_description/unit_type，不把机器字段堆进正文。L0–L4 其余保存知识字段保留为分段文字，Run 输入、参数、执行、结果等保留在 context。
4. 每个子记录的 figure:0 原本各有命名空间；响应为它们分配唯一图片编号，保留 record_id/ref，防止多个技术单元的图互相错配。完整正文供前端一次渲染，sections 供结构导航。
5. 引用标题从实际授权的固定修订取得，索引未覆盖也不显示不必要的“固定来源”。结构 section_refs/嵌入 unit 不冒充科学依据；有真实块级 evidence_refs 才标“本段依据”，旧记录只有记录级来源则只保留文末来源，不猜句子位置。同 ID 不同版本/定位仍分开。[MEM-ID] 兼容单编号，代码、公式、既有链接保护不变。
6. Owner、quick 综合与 legacy 笔记正文不再拼问题、派工决定、理由、状态。question 仍是内部契约字段，next_steps 有内容才显示“可选的下一步建议”；clue.reason 为“关联依据”，next_query 不混知识正文且允许空字符串。编排历史留 RS/reading-view；handoff 保留 phase/gaps/needs_user_input，长决定不再制造假缺口或占正文容量。worker 明确主 Agent 负责联想问题和关键词，reader 不自定扩搜。派生快照格式升到 4。

## 接口与文件

`evidence/detail` 保留原字段，新增 `level`、`record`、`sections`、`images`、`media`。images 包含 index/caption/data_url/sha256/ref/record_id；SRC 图片 media 为 type=image/data_url/sha256/caption。record 是授权后固定规范记录，供已有类型呈现；不是新状态源。

主要代码：material_query/evidence_navigation.py、reading_owner.py、reading_delegation.py、reading_citations.py、reading_notes.py。公开 web 路由不变。

测试：新增 test_evidence_content.py、test_note_knowledge_body.py；调整 test_reading_handoff_view.py 和 test_reading_delegation.py 的预期；reading_panel_fixture.py 通过公开提交增加固定文稿与 64×64 蓝黄棋盘 PNG。未改历史规范数据、全局 catalog 或前端构建资源。

## 先失败再修复与回归

- 初次测试入口导入错误保留在 backend-evidence-red.log；修正入口后真实契约失败分别保存 backend-evidence-contract-red.log（结构来源误当引用）、backend-evidence-api-red.log（document 漏技术正文）、backend-tool-red.log（工具登记适配）、backend-note-red.log（正文混编排）、backend-clue-red.log（公开 note 拒绝空 next_query）、backend-bracket-red.log（双括号编号）。导入失败不作为功能失败证明。
- 证据 helper + 公开 API **8 项通过，3.105 秒**：backend-evidence-visual-final.log。包括固定文稿内容和依赖选择、两个独立 figure:0、SRC 图片、撤权/窄域拒绝、登记工具、引用位置、payload 知识。
- 新 note 公开空 next_query 保存及当时纯测试 **4 项通过，65.962 秒**：backend-note-final.log。末尾新增 [ID] 回归和长决定检查后，纯 **4 项通过，0.005 秒**：backend-note-final-pure.log。
- recent 引用/预算/时间纯测试 **4 项通过，0.003 秒**：backend-citation-final.log。
- legacy handoff 定向 **3 项通过，0.036 秒**：backend-handoff-local.log。最后全部代码停笔后的委派整组 **10 项通过，94.770 秒**：backend-delegation-final.log。
- 父任务负责整体阅读、UI、真实 Windows 升级及 validate；本文件不替代它们的实际结果。

## 实际浮点样例

只读结果保留 backend-live-detail.log、backend-live-document-final.log。

- SRC-SUMMATION-FIGURE-R01：固定图片核验成功，data URL 112,006 字符，约 2.803 秒。
- MEM-c52df8fb-ca9e-53a7-a49b-342592884a50：L1 详情 3,137 字符、1 图、11 固定关系，约 2.686 秒。真实旧三块没有块级 evidence_refs 或来源 ID，因此不伪造块/句归属；figure:0 的图源明确。
- MEM-ab9db095-2545-594c-9e94-f72bab43c464：实际文稿展开 18,802 字符、4 图、34 固定关系，约 4.051 秒。正常返回不证明所有科学来源重新复核；只有展示图片实际核了原件 hash，规范记录按固定版本校验。

本轮没有覆盖或修补既有历史 MEM 哈希。其他历史对象若完整性不符，仍拒绝或保留明确缺口；本机软件通过不等于科学结论复核。
