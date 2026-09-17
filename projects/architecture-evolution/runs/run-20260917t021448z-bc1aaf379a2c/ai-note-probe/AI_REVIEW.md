# 实际 AI 材料笔记验收

2026-09-17。由写作规范子 Agent 实际读取公开 reading-read 的合成完整文稿与新 worker_brief 后撰写 draft-note.json；准备脚本只生成合成输入、提交记忆和调用公开接口，不自动生成 note。没有额外启动审核 Agent，也没有把本验收变为产品主 Agent 的固定复检流程。

材料限定 `.local/writing-note-probe-20260917/synthetic-attempt-02`，复用共享 fixture 构造函数，没有修改测试 fixture 源文件或实际业务记忆。未配置/启动向量模型、未检索业务全库。合成来源通过 MemoryService 实际提交，版本与哈希由公开读取取得，不是随手伪造的固定引用。

## 实际结果

公开 template/start/delegate/recall/read → AI写作/同任务自查 → note/view/decide/handoff 已完成。最终 RS-2417fd8d-07bf-4f6d-b937-9cb5956d2df4 r6，phase=finish，1份note、0遗漏，UTF-8保守估算2481/6000。完整请求/回执、AI草稿及可读NOTE.md保存在本目录。

正文保留电压到温度的反算、摄氏到开尔文的固定偏移、0–80 °C范围、0.75 V→25 °C→298.15 K示例、不确定度公式与校准参数无误差假设、95 °C外推反例。材料建议仅为扩展温区前加入独立边界样本，标题是“可选的下一步建议”，未写成实际已执行实验。

note.question 保存绑定搜索词readingfixture但不显示在正文。reader 的决定“交回主Agent”只在decide回执，不进入材料正文。association_text为空，线索保留温标平移机制与适用限制；next_query为空，实际保存成功，正文不显示后续查询、没有编造联想关键词或发起联想召回。公式与编号引用均保留；文末[1]对应文稿 MEM-9ba4fafb-f8b1-5afc-86b5-5cb4532762a9 r1，SHA-256 `37ed58315083826cf2ec25d063549b0073de5dcc2e3eac8fdf66a58f95659b2e`。

## 首次失败与修正

- 初次准备在普通沙箱保存Run回执被拒绝；隔离材料留在synthetic目录，改用获准执行并另建attempt-02，没有覆盖首次目录。
- start首请求把reranking误放进query，被公开校验拒绝；原请求/回执以start-first-rejected开头保留，修正到start外层后成功。未放宽校验。
- AI草稿初次手写JSON的LaTeX转义不合法，在提交API前本地解析发现并修正；属于草稿序列化错误，不当产品故障。
- 首个成功note r4使用[MEM-ID]，替换后正文成为[[1]]；首次草稿/note/handoff回执以first-前缀保留。同一AI将引用改为裸ID后新note r5、finish r6，最终显示[1]。材料内容和证据没有修改。语法边界已告知后端。

## 限制

handoff complete=false，明确保留Owner有未交付记录、dense未配置、部分词法命中缺固定片段三个缺口。读取该篇research_process完整不等于Owner全覆盖；未展开原始文件，不声称现实校准有效。此为本机合成实际AI写作及公开接口一次验收，不证明未来AI必然无遗漏、科学结论正确、真实检索质量或第二物理机兼容。

checks.json只是对公开回执的可观察字段/内容检查；本页人工式材料对照为AI自查，两者分开，不把字符串断言称为语义证明。
