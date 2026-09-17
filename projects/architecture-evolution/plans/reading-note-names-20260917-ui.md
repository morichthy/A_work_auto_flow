# 阅读笔记可读名称：前端结果

2026-09-17。只调整对外显示和下载名，不更改RS身份、目录、状态或后端。会话名称使用已保存goal（阅读问题/目标），没有聊天标题绑定，不冒称聊天标题。

共享helper `automation/frontend/src/readingNoteName.ts` 为首页及阅读面板生成 `清洗截短的问题名-RS-12位短标识-rN.md`；示例 `合成阅读会话-RS-a8f812d7d8f9-r4.md`。清洗Windows非法文件名字符和控制字符、合并替代连字符、截短到48个Unicode字符，空名回退“阅读笔记”。短RS后缀区分相同问题名；完整身份仍保存在RS与页面折叠详情中。

ReadingSessions继续主显示goal，长RS ID移至“会话标识与版本”折叠详情；独立显示笔记快照修订。打开固定原文后，导出仍使用实际笔记快照修订而非自行推算的新版本。

验证（Node C:/nvm4w/nodejs/node.exe，在automation/frontend）：

```powershell
node node_modules/vitest/vitest.mjs run src/CurrentReading.test.tsx src/ReadingSessions.test.tsx
node node_modules/typescript/bin/tsc --noEmit
node node_modules/vite/bin/vite.js build
node node_modules/@playwright/test/cli.js test e2e/workbench.spec.ts --grep '对象阅读清单、完整原文和版本导出真实接口'
```

19项相关组件通过；typecheck通过；build及指纹更新通过（保留既有500kB chunk提示）。真实浏览器下载场景1项通过，用例4.2秒，总6.2秒；断言实际下载名匹配 `合成阅读会话-RS-[a-f0-9]{12}-r4.md`。既有组件测试中补充首页名称、非法字符、空名、截短、折叠及实际笔记版本断言，未增加catalog项。

首次清洗用例因预期连字符计数不一致失败，随后统一合并替代连字符并去除尾部标点，复验全绿。最后framework_files只读核验通过。未改后端、文档或上次Run固定证据；本文件是本次独立结果。
