# 最近问题笔记、公式及证据详情：前端实施验证

2026-09-17，reading_ui子agent。环境：Windows x64，Node 22.11.0（C:/nvm4w/nodejs/node.exe），已有依赖；无联网安装、生产偏好修改或历史RS改写。

## 实现

- 首页从reading-notes/recent读取最近24小时问题，使用snapshot展示正文。最新优先列表支持加载更多，重开时也能恢复第二页内的合法选择；localStorage按后端workspace_id隔离，过期/其他工作区选择不恢复。选择、分页与快照具有晚到响应隔离。
- 显示问题、更新时间、快照修订及一处未重新核验证据说明；RS身份及快照读取时间折叠，真实额外警告和缺口保留。旧三模式编辑仍通过原CAS接口保存并回读真实HEAD。
- ResearchMarkdown修复# /evidence路由链接被当成文内anchor阻止的问题。支持标准LaTeX括号分隔符\\(...\\)、\\[...\\]，沿用$和$$；解析Markdown位置保护行内/围栏代码，不猜测未定界普通表达式。
- Evidence在首次进入时才挂载，不再首页预载全库state。左侧轻量搜索标题/摘要/ID并分页；右侧只取选中记录正文、标签和可读上下文，引用与影响以标题和关系跳转。固定版本深链保留revision/hash/locator，非法revision拒绝且不静默改读当前版；晚到详情不会覆盖新选择。
- ReadingPanel合成fixture经后端agent明确移交后更新：两个真实公开RS、带公式note、MEM固定来源引用RUN；用于真实浏览器导航，不代表科学结果。

## 先红后绿与修正

新增公式/深链、最近问题快照、单证据详情测试在对应实现前运行：公式仅渲染1个而预期3个，最近问题仍调用旧接口，证据仍请求state且不显示深链详情，均失败。首版公式测试另有字符串语法错误，修正后才得到有效行为失败。

实现后旧4个CurrentReading测试因旧MQ envelope mock失败，适配新普通JSON接口且保留既有跨面板复用/失败/晚到行为断言。初次真实双向导航因同标题同时出现在正文参考文献和引用列表而定位器歧义，改为精确引用列表定位后通过。

扩展旧“完整导航、关系、证据、候选和摘要”浏览器暴露CLM-SYNTHETIC无法搜索，已向后端报告；最终后端截图列表已包含claim，但该扩展场景尚待单独复验，不列为通过。中间修正重复NOTICE时后续fixture启动命中源码/构建指纹不一致；重建后最终四项全部通过。

Evidence旧文件普通替换因文件权限拒绝，经自动审批写入薄入口，新实现位于EvidenceBrowser.tsx。未借权限问题停工或修改访问边界。

## 最终验证

在automation/frontend目录：

```powershell
node node_modules/vitest/vitest.mjs run src/CurrentReading.test.tsx src/Evidence.test.tsx src/ResearchDocument.test.tsx src/ReadingSessions.test.tsx src/ReadingEvidence.test.tsx src/WorkspaceSettings.test.tsx
node node_modules/typescript/bin/tsc --noEmit
node node_modules/vite/bin/vite.js build
node node_modules/@playwright/test/cli.js test e2e/workbench.spec.ts --grep '最近问题重开|证据页首次|三模式会话|对象阅读清单'
```

实际node使用上列绝对路径。44项组件通过：CurrentReading 9、Evidence 3、ResearchDocument 8、ReadingSessions 10、ReadingEvidence 2、WorkspaceSettings 12。类型检查通过；最终build更新预构建指纹，JS为index-DWqv3ODE.js，保留500kB chunk提示。

最终4项真实Edge浏览器全部通过（20.0秒）：

1. 最近问题切换、重新载入保留、真实KaTeX、编号→MEM→RUN→下游MEM→返回、窄屏。
2. 既有三模式保存、重载及快速覆盖提示。
3. 证据页首次进入才搜索、离页再进入复用搜索结果、无旧state请求。
4. Owner阅读面板、固定原文及版本导出。

首屏笔记500ms（从page.goto前计时至合成主note可见，隔离小fixture，仅本次观测，不能推广真实大库性能）。机器回执与请求列表位于`.run-captures/ui/e2e-results.json`。

截图已视检：`recent-note-formulas.png`、`note-formula-detail.png`展示问题选择、独立note与可读行内/展示公式；`evidence-record-relations.png`、`evidence-narrow.png`展示左右/窄屏详情及关系。截图不代表业务结论验证。

## 限制与交接

- 无定界符的旧普通文本公式不自动猜测为数学；真实历史note格式修改由主agent按正式流程处理。
- 当前浏览器localStorage是同浏览器origin内持久化，并额外按workspace_id隔离；若重启改变浏览器origin/端口，其存储边界不由此键穿越。
- 可读context已隐藏顶层技术字段，但RUN inputs的嵌套sha256仍显示，属于呈现小项，已报告主agent；避免扰动升级窗口，最后构建后停止源码写入。
- 本范围不是实际AI阅读质量、全库性能或第二物理机验收；发布/Windows升级/catalog由主agent整合。

## 后端claim兼容完成后的旧导航复验

后端恢复claim metadata搜索后，仅复跑此前失败的“完整导航、关系、证据、候选和摘要”：1项通过（用例6.7秒，总8.6秒，exit=0）。本次没有修改源码或重新构建。首次锚定grep未匹配Playwright完整标题、没有执行测试，改为唯一标题子串后实际执行通过。

独立证据：`.run-captures/ui/legacy-navigation-recheck.log`和`legacy-navigation-recheck.json`。因此本范围最终有5项不同真实浏览器场景通过，前述CLM搜索失败已复验解决；此前失败记录保留。
