# 当前笔记与证据内容前端验证

2026-09-17；隔离合成资料，Windows x64、已安装 Node `C:/nvm4w/nodejs/node.exe`、Edge/Playwright。没有安装依赖、修改生产设置或业务历史记录。

## 本次行为

- 当前笔记移除“选择阅读会话”，保留最近问题选择；“查看证据与影响”放在笔记操作行，首页不再重复入口。
- 三模式编辑和联想方向放在当前笔记的折叠区，仍显式保存、保留 CAS/草稿隔离逻辑；提供默认阅读模式设置链接。
- 系统记忆移除阅读记录标签；旧 `#/memory?tab=reading` 转向首页。记忆对象列表仅展示最多 240 字摘要，标题进入固定版本 Evidence 详情；管理动作折叠保留。
- Evidence 按 L0–L4、Run、文稿显示对应标题。Run 上下文按输入、配置环境、执行状态、结果产物、限制分组，技术字段隐藏在正文上下文之外。
- 完整文稿直接显示后端装配的完整 Markdown，保留根正文、固定章节及唯一编号参考文献。使用响应统一图片编号，不重新分配子章节 figure:0。
- 当前笔记的定向证据入口仅列已引用材料的固定链接，不预读全部全文、不重复呈现原始 Run JSON；点击进入统一详情。

## 先失败再修复

- `ui-key-tests-red.log`：CurrentReading、MemoryNavigation、Memory 的关键入口断言 3 项失败。
- `ui-evidence-red.log`：完整章节及来源图片关键用例 1 项失败。
- `ui-reading-evidence-red.log`：定向证据不预读/raw 字段用例 1 项失败。
- `ui-browser.log` / `ui-browser.json`：首轮 2 通过、3 失败。新 fixture 的首引用从 overview 变为完整文稿，旧浏览器断言仍写死原标题；同时发现旧定向证据页会堆出原始 Run 字段。已修复入口并迁移相关断言，原失败证据未覆盖。

## 最终验证

在 `automation/frontend` 执行：

```powershell
& 'C:/nvm4w/nodejs/node.exe' node_modules/vitest/vitest.mjs run src/CurrentReading.test.tsx src/MemoryNavigation.test.tsx src/Memory.test.tsx src/Evidence.test.tsx src/ReadingSessions.test.tsx src/WorkspaceSettings.test.tsx src/ResearchDocument.test.tsx src/ReadingEvidence.test.tsx
& 'C:/nvm4w/nodejs/node.exe' node_modules/typescript/bin/tsc --noEmit
& 'C:/nvm4w/nodejs/node.exe' node_modules/vite/bin/vite.js build
& 'C:/nvm4w/nodejs/node.exe' node_modules/@playwright/test/cli.js test --grep '记忆摘要进入|三模式会话|对象阅读清单|最近问题重开|首页自动阅读'
```

- `ui-components-final2.log`：8 文件、52 项通过。
- `ui-typecheck-final.log`：类型检查通过，退出码 0。
- `ui-build-final.log`：一次临时 EPERM 无法 unlink manifest；原样重试成功，见 `ui-build-retry.log`。最终主资源 `index-C5uqjULU.js`，仅现有大 chunk 提示。
- `ui-browser-retest.log` / `ui-browser-retest.json`：5 项通过，40.9 秒。覆盖首页 quick/associative 保存与刷新、联想启用、旧入口跳转、实际下载文件名、近期问题恢复、KaTeX、编号引用→文稿→Run→下游记录→返回、Memory 摘要→完整文稿、内嵌图及 SRC 原图 `naturalWidth > 0`。
- `ui-framework-fingerprint.log`：`deployment.framework_files(Path.cwd())` 通过，共 511 个受控文件；前端源码与资源指纹一致。

新增静态用例供根任务登记：MemoryNavigation 的旧阅读记录入口跳转；Evidence 的完整文稿与来源图片、Run 分组；ReadingEvidence 的定向固定链接无预读；e2e 的记忆摘要进入完整文稿与来源图片证据。此分支未改全局 catalog。

## 截图

最终截图位于 `ui-browser-retest/`：

- `workbench-记忆摘要进入完整文稿与来源图片证据/evidence-complete-document.png`
- `workbench-记忆摘要进入完整文稿与来源图片证据/evidence-source-image.png`
- `workbench-三模式会话显式保存方向、重新载入与快速覆盖提示真实接口/reading-three-modes.png`
- `workbench-最近问题重开选择、公式与编号引用双向证据导航真实接口/evidence-record-relations.png`
- `workbench-最近问题重开选择、公式与编号引用双向证据导航真实接口/evidence-narrow.png`

图片 fixture 初版为极小合成 PNG；浏览器验证真实解码成功，不等同真实科研图片视觉验收。完整文稿后端附带的少数字段标题已反馈后端完善中文呈现。旧独立 ReadingEvidence 组件及测试保留兼容，公开入口使用新的 NoteEvidenceLinks。

## 后端呈现修复后的限定复验

后端排除文稿中的检索元字段、修正引用标题和图片说明后，仅复跑“记忆摘要进入完整文稿与来源图片证据”：1 项通过，9.3 秒；日志/JSON 为 `ui-browser-visible.log`、`ui-browser-visible.json`。本次未修改前端源码或重新构建。

另用 Run 内独立探针 `ui-visible-image-check.mjs` 验证真实浏览器图像解码：文稿内图与 SRC 图均为 **64×64**，满足 `naturalWidth > 1`；见 `ui-visible-image-result.json`。最终 `ui-visible-document.png` 与 `ui-visible-source.png` 已人工视觉查看，蓝黄棋盘图实际可见；文稿检索元字段及“固定来源”占位标题已消失，SRC 正文说明与已展示图片一致。此前极小 PNG 的限制仅适用于首轮证据。
