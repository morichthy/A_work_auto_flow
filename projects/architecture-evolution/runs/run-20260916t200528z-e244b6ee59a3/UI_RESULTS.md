# 三模式设置与工作台验证

本范围由 reading_ui 子agent实施，2026-09-17。本机 Windows x64，Node 22.11.0（`C:/nvm4w/nodejs/node.exe`），使用已有依赖，无联网安装；未修改生产 workspace-settings.json。

## 行为

- 工作区 reading.strategy 默认 standard，association 默认 enabled=true/max_rounds=3。max_rounds 严格整数1..20；旧磁盘配置在内存补字段，原字节/CAS不变，写请求仍须完整字段。
- 设置页选择标准阅读、联想加深、快速阅读，并保存不足时联想开关与轮次。仅影响后续会话。
- 当前会话显式保存模式与可选联想搜索文本；CAS冲突保留草稿，可读取最新版本后核对。显式联想模式启用本会话联想并保留轮次上限；不会重置已用轮次。
- ReadingMode组件按会话ID隔离，卸载后的晚到保存不能刷新新会话。保存成功后回读HEAD，显示尚未启动搜索；没有后台AI。
- 快速阅读提示仅召回文本覆盖。Owner面板合成fixture使用公开recall/read(owner_id)/research_note及真实document_refs。

## 先红后绿

实施前新增设置后端测试失败于缺少strategy；设置组件失败于缺少“默认阅读模式”；会话组件失败于缺少“当前阅读模式”。这些失败发生在对应实现前。

初次命令还有两个环境问题：Python模块路径不适用，改用unittest discover；Vite临时文件写入受沙盒限制，获工具自动审批后正常运行。它们不算产品失败测试。

首次浏览器设置2项通过，会话fixture失败于Owner默认模式已不返回candidate_id。修复fixture为Owner完整读取后，旧面板断言“关键细节”更新为研究式note实际标题“细节、参数、单位与边界”。测试源码修改后首次启动触发源码指纹不匹配，重新构建/更新指纹后通过。期间空会话HTTP启动试验未带Origin，模板不可用，撤回该试验并复用已修复Owner fixture；最终浏览器核查POST均带正确Origin。

## 最终命令与结果

工作区根目录：

```powershell
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_workspace_settings.py -v
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_workspace_settings_integration.py -v
```

15设置单元 + 4设置集成通过。涵盖默认、旧文件无损读取、严格写入、CAS、真实HTTP、CLI、已有RS保持快照。

以下在 automation/frontend 运行，node均为上述绝对路径：

```powershell
node node_modules/vitest/vitest.mjs run src/WorkspaceSettings.test.tsx src/ReadingSessions.test.tsx src/CurrentReading.test.tsx
node node_modules/typescript/bin/tsc --noEmit
node scripts/contracts.mjs
node node_modules/vite/bin/vite.js build
node node_modules/@playwright/test/cli.js test e2e/settings.spec.ts e2e/workbench.spec.ts --grep '真实HTTP保存配置|设置草稿|三模式会话|对象阅读清单'
```

24组件通过（12设置、8会话、4当前笔记），typecheck通过，最终构建通过并更新asset-manifest；构建保留大于500kB chunk提示。4浏览器用例全部通过（10.0秒）：真实设置保存/重载、草稿导航及冲突、三模式保存/重载/首页快速覆盖提示、Owner笔记固定原文及导出。

本范围为合成数据软件验证，不代表真实AI笔记质量、现实模型有效性或第二物理机验收。Windows升级/整体验证由主agent统筹；未发布。

## 最终契约静态整合复核及历史界面修复

逐项核对最终reading_strategy/reading_owner/reading后端：设置默认只影响新模板；已建会话保存仅发送strategy/association_text与可选association，未修改目标/授权/预算；空association_text允许保存，召回由reader提供实际问题；显式associative启用本会话但不重置轮次；CAS冲突保草稿、刷新回读版本、晚到响应按会话隔离。Owner历史RS缺策略字段仍由后端返回standard与独立兼容联想设置。

复核发现legacy历史RS后端禁止configure，但前端仍显示编辑器。经主agent追加授权，修复为仅mode=owner_document显示模式编辑；legacy或缺mode显示旧流程说明，保留笔记/原文。增加显式legacy及缺字段两项组件行为测试，14项受影响组件通过（10会话+4当前笔记）；设置12项沿用前次通过，累计相关26项。typecheck与最终build重新通过，未机械重跑已绿浏览器。此构建发生于本机04:25–04:26，部署测试若与构建并发需主agent核对受影响用例。

修复前已独立核对61个前端源码与65个构建产物SHA256，且扫描未登记源码：零不一致。修复后build已重新生成完整指纹。

随后测试发现器不支持 it.each，按现有发现契约将两项历史会话用例拆成静态 it 名称，共享断言不变。两项定向测试再次通过；catalog revision 109 登记并审计通过（816 discovered、818 catalog，无缺失/未分类/错误）。只改测试声明，产品 JS 仍为 index-B1kUsl80.js；构建与指纹再次更新。这一步发生在真实 setup 补测通过之后，最终来源/构建一致性另由证据固定过程检查。
