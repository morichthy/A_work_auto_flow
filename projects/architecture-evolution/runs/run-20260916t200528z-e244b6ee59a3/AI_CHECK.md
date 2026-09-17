# 三种阅读策略：实际 AI 合成验收

日期：2026-09-17。本记录区分程序校验、实际 AI 阅读自查与现实科学验证。材料为隔离合成的 phase_case；没有现实仪器实验，不证明真实业务检索效果或模型适用性。

## 执行身份与信息边界

标准阶段由先前独立 reader 实际读取 RES-MQ-A 的完整文稿并写笔记，保存到 `RS-123e4567-e89b-42d3-a456-426614174000` r4。本次 reading_backend AI 从 r4 的公开 handoff 承接；没有重新把 A 全文交给主 Agent，也没有声称本次 reader 亲自重读 A 全文。

本次 reader 只读取 `AI_FIXTURE.json` 的路径/Owner/目标信息、material-query Skill，以及公开 reading 接口实际返回。没有读取 ai_driver.py，也没有读取初始化 fixture 的材料源。所有 note 均由实际 reader 根据其收到的正文、片段或前一 reader 的底稿亲自撰写，通过公开 reading-note/reading-synthesize 保存；没有程序生成笔记，也没有直接修改 HEAD。

主 Agent只通过 handoff接收笔记。本次 reader 的代码开发上下文与此前联想阅读存在于同一子 Agent中，因此 quick 是独立 RS 和独立交付范围的验收，并非盲测或不同模型的质量对照。quick 笔记的引用和内容限定在其实际召回片段；未借此前完整文稿扩展其阅读覆盖。

## 标准 → 联想加深：同 RS 完整执行

会话：`RS-123e4567-e89b-42d3-a456-426614174000`。

| 阶段 | 修订 | 实际动作和结果 |
|---|---:|---|
| 标准阅读基线 | r4 | 前一独立reader完整读取A并保存note；本次handoff取得小时间误差模型、单位、示例及过零检测阈值线索。 |
| 说明缺口 | r5 | decide expand：A只解释时间到相位，尚缺时间偏移上游机制。 |
| 配置联想 | r6 | configure associative；enabled=true、max_rounds=3；association_text保存“过零检测 阈值波动 采样时刻误差 phase_case”。 |
| 联想召回 | r7 | 原授权 ceiling 不变，direct scope使用获准A、B；使用上述真实子问题及匹配中英文查询，记录A根文稿clue_sources。召回B。 |
| 完整读B | r8 | reading-read(PRJ-MQ-B)返回完整research_process，complete=true；当前reader实际读到电压扰动—时间模型及失败边界。 |
| B底稿 | r9 | reader保存B研究式note，含变量单位、模型条件、代入示例、S接近零/非线性反例和电源归因缺口。 |
| 跨Owner综合 | r10 | reader亲自综合A底稿与B全文，用两段关系形成条件性代数推断；不认定电源根因。 |
| 结束和交接 | r11 | decide finish、handoff；synthesis_included=true，1份综合note完整交付，0漏稿，估算4817/16000 UTF-8字节。 |

实际形成的综合推断为：

\[
dt\approx\frac{dv}{S},\qquad d\phi=2\pi f\,dt,
\qquad d\phi\approx\frac{2\pi f\,dv}{S}.
\]

其中 \(dv\) 为阈值电压扰动（V），\(S\) 为检测点电压斜率（V/s），\(dt\) 为时间偏移（s），\(f\) 为频率（Hz），\(d\phi\) 为相位误差（rad）。合成代入为1 mV、1000 V/s、1000 Hz，对应1 μs和约0.006283 rad。组合式是此次AI的代数综合，不是新增实测结论。

仅使用1轮联想；没有为耗尽3轮上限继续搜索。最终phase=finish，但接口status=partial、complete=false，原因包括A同类文稿不止一份、dense未配置、部分词法命中没有展示片段。进一步从供电追到阈值仍需独立测量，保存为待验证方向。

固定公开回执：`ai-receipts/010-reading-handoff.json`（基线r4）、`015-reading-recall.json`（成功联想）、`016-reading-read.json`（B全文）、`017-reading-note.json`、`018-reading-synthesize.json`、`020-reading-handoff.json`（最终r11）。主Agent另有r11 handoff回读029。

## 快速阅读：不读取全文，逐条判断后保存同质量笔记

独立会话：`RS-123e4567-e89b-42d3-a456-426614174001`；最终r10、phase=finish。使用相同目标，max_owners=3、note_max_tokens=16000，仅在这个合成fixture显式reranking=off；没有修改真实工作区设置。

| 阶段 | 修订 | 实际动作和结果 |
|---|---:|---|
| start | r1 | quick；scope与ceiling均限获准A、B；声明仅召回片段。 |
| recall | r2 | 实际交付A和B各一条phase相关文本，每条携带candidate_id和3个固定block定位。 |
| 逐条接受 | r3、r4 | 当前reader分别判断A换算/边界与B上游机制有用，保存独立理由。 |
| page | r5 | 实际交付A、B各一条通用控制量定义；has_more=false。 |
| 逐条拒绝 | r6、r7 | 当前reader判断通用e_k/u_k/K定义缺少与phase_case的实际连接，逐条useful=false。 |
| 保存笔记 | r8、r9 | 亲自撰写A、B两份研究式note，只引用各自接受片段；定义、公式、单位、例子、限制、下一步和联想线索均保留。 |
| finish/handoff | r10 | 两份note完整交付，0漏稿，0尚未记笔记候选；估算7596/16000 UTF-8字节。 |

公开回执核对quick的reading-read调用数为0。实际四条候选均有判断：2接受、2拒绝；accepted来源分别为A `MEM-c9deeddf-4732-57ec-b745-1656291533ff`和B `MEM-7bce9502-eb77-5467-aeea-a68903f1622b` 的definitions/result/optional固定块。note和handoff保留block locator与“未完整阅读Owner文稿”限制。没有引用此前联想RS的完整文稿根ID。

当前候选窗口结束不是全库穷尽，最终handoff仍为partial，保留dense不可用及词法片段展示缺口。无需额外翻页或全文阅读即可形成有细节、可续接、明确覆盖范围的笔记；这不证明快速模式在一般任务中与全文阅读质量等价。

固定回执：`023-reading-recall.json`、`024/025-reading-assess.json`、`026-reading-page.json`、`027/028-reading-assess.json`、`030/031-reading-note.json`、`032-reading-decide.json`、`033-reading-handoff.json`。

## 验收发现、接口失败与修正

1. helper实际要求`--request`后跟JSON文件路径。最初按文字JSON调用失败于路径解析，未执行阅读动作。随后保存请求文件并调用公开接口。
2. 普通沙箱允许发起读取但拒绝在Run目录写回执；首次handoff回执保存报PermissionError。按授权使用require_escalated继续调用，不更改ACL、不改数据授权。
3. 联想首次引用A已完整交付根文稿时，被程序以“笔记来源ID未在本Owner实际交付”拒绝（014回执，revision仍r6）。原因是clue_sources校验使用parts交付来源，却漏并入full_delivered的root_refs。修复只补已完整交付根引用，保持部分文稿/未读来源限制；重试原request_id成功r7。强化既有集成用例，未增加测试目录中的方法数量。
4. 两个亲写JSON请求中的LaTeX反斜杠未正确转义，解析失败，未写入RS。只修复JSON编码后重新提交；公式内容不变。最终实际解码LaTeX单反斜杠已由主Agent确认，工具嵌套JSON显示的双斜杠不是笔记错误。
5. quick start最初仍返回legacy通用GUIDANCE，提示reading-read，与quick策略冲突；本reader以实际strategy/Skill和后续recall的assess指引执行，没有误读全文。已修为quick专用逐条判断/片段note指引，并在既有真实start集成测试断言含reading-assess且不含reading-read。

## 末轮软件回归与结论层级

- 根文稿引用修正后，`automation/python.ps1 -m unittest discover -s automation/tests -p test_reading_three_modes.py -v`：13项通过，98.848秒；日志`association-root-retest.log`。
- 再修quick start指引后，同命令13项通过，51.694秒；日志`association-final-retest.log`。保留首次日志，不覆盖过程。
- 实际AI自查：本reader核对了自己笔记中的公式、单位、例子、条件、反例、source ID和未读边界；主Agent按handoff消费，无新增固定审核Agent。
- 科学/业务验证：未执行现实实验、人工验收或一般检索质量基准；均不得由上述程序与合成AI结果替代。
