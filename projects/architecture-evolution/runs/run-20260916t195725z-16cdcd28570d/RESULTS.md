# Reader默认自查与确定性引用检查

本次是Owner阅读实现的局部质量修正，沿用既有研究式note结构与预算。用户明确要求固化reader提取、自查和程序可确定检查，不增加主Agent固定复检。

## 结果

1. 真实reading-delegate的worker_brief直接要求reader围绕问题提取核心公式、变量/单位、条件/假设、反例、实验输入/结果及图/Run/原始来源对应；材料没有的部分明确记缺口。
2. 同一reader组织笔记并自查补齐后保存，来源未展开不能说已独立看图/复算。Skill同步，不再安排主Agent固定质量复检；没有新审核Agent、新模型/搜索调用、额外自查字段或交接审核包。
3. reading-note保存时在understanding/logic/details扫描显式来源ID，确认已交付且列入该note的固定sources。MEM-/RUN-/SRC-支持未知ID拒绝；其他已交付record/file/representation带分隔符ID精确匹配。中文标点、Markdown标签与@修订后缀能识别ID；HTTP(S) URL token和Owner/RS导航排除。问题/条件/限制/下一步字段不自动当作证据。

漏登/未知时同一reader收到具体ID并修正；不把所有已读来源强加给note，不回溯追审旧note/handoff。已有来源规范化、授权、固定版本、陈旧检测继续有效。程序只验证显式ID关系，不证明引用支持该句、公式数学含义、文字中声明的版本或语义覆盖完整；这不是全自动语义审核。

## 验证与首次失败

- Owner文件最终23项通过（75.265秒）；delegation10项通过（42.784秒）。额外7项纯函数复验已含于Owner数量，不重复累计。
- 先红测确认漏登/未知可穿过旧代码；公开API负例确认旧行为曾接受不完整引用。
- 补获Markdown链接或反引号结束后无空格来源ID被URL排除规则吞掉的真实红测；修正后标签与其后来源均被检查。
- 初次存储断言误认为拒绝后HEAD必须逐字不变；既有工程审计会记录已发生IO并更新consumed及storage_digest。没有为了测试取消审计；最终断言只允许这两项变化，note、revision、请求历史、修订文件及current.md均不变。
- 新增4项登记，catalog revision103；audit发现795/登记797，无遗漏/错误。目录数不等于本轮执行数。基线现有固定来源和撤权测试继续复验；新增显式引用语法用例按影响执行，不扩大为每次全库基线。
- 未改前端、安装/目录扫描/工作区validate实现或模型依赖；沿docs/UPGRADE_TESTING影响矩阵无需重跑构建、安装和全回归。Windows x64运行现有Python标准库与定向集成测试，未引入平台专属依赖。

## 实际AI合成场景

ai-probe保存从真实delegate生成的worker-brief、合成完整校准文稿和引用、低成本terra/low reader的首个最终note。没有主Agent跟进要求改写；该首稿保留温度反算式、数值示例、误差传播及单位/假设、15点Run/图/原始数组来源、80°C外推反例和未展开说明。无关风扇来源没有进入sources。root的检查是本次开发验收，不会加入产品主Agent流程。

该note经生产normalize_note_sources与validate_note_evidence_ids实际调用通过，结果见ai-probe/validation.json。局部单次11.131ms仅为这两个本地函数调用，不含模型/IO/API、不构成性能基准或整体提速证据。本场景未创建真实RS，引用/哈希是合成fixture，未访问真实图像或数据，不能当真实科学实验复核。第一、二步固化为reader默认行为要求，不能据单次通过保证所有未来AI输出无遗漏。

## 记录边界

前一冻结Run RUN-20260916T181657Z-4D7EFFF321BA和规范文稿r7保留原时点，不回写其测试或宣称其已包含本轮修正。本轮局部修正以本Run、现行代码/Skill/文档和note-quality-defaults-20260917计划记录，不另做全项目成果同步或科学复核声明。后续主Agent确需出处时可自行读取。

最终refresh-index成功；validate为0错误、21既有警告。源码/测试/方法快照与AI输入输出、红绿日志已固定登记，未发布。
