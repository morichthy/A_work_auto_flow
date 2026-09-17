# 前端组件实际执行回执

2026-09-17 00:13 Asia/Shanghai，Windows x64；命令：

```text
npm test -- CurrentReading.test.tsx ReadingSessions.test.tsx MemoryNavigation.test.tsx MaterialNavigation.test.tsx ReadingEvidence.test.tsx Memory.test.tsx
```

6 files / 17 tests passed；退出码0，Vitest 3.2.7。CurrentReading 4、ReadingSessions 5、MemoryNavigation 2、MaterialNavigation 2、ReadingEvidence 2、Memory原回归2。

早期 `npm test -- ReadingSessions.test.tsx` 在沙箱账号下因node_modules/.vite-temp写权限EPERM未能启动；授权提升运行后1项因新增notes_only参数与旧精确调用断言不符失败，已在断言中保留session_id并加入notes_only:true；其余2项通过。该调整验证新的有界笔记接口，没有取消来源撤权/导出版本保护断言。

新增行为包括：默认显示有note会话、刷新保持手选会话并更新正文、翻页保留当前正文、不自动reading-read、跨Owner迟到响应隔离、全局默认列表晚到不覆盖Owner选择、首页进入阅读面板复用同RS快照、来源撤权立即撤下正文且重试同RS。

构建包含contracts、typecheck、vite build和asset-manifest资源/source指纹生成，最终构建完整输出见build-final.log。后续homepage依据展示修正若发生，另见复验日志；本回执仅记录上述执行时的17项。

00:20最终证据展示修补后重跑ReadingEvidence 2项全部通过（evidence-components-final.log）；最后构建日志为build-evidence-fix.log。实际Node SHA256逐项复核60个源码、65个资产，mismatches=[]，source_fingerprint=46da668df3c17f35e813e39afe09dda7b7a85e1063ead71f17fdcd9e6ba730c0。

00:22阅读浏览器精确文本断言随notes-only Markdown改成“关键细节”标题+独立数值正文，保留273.15精确验证；再次构建见build-markdown-assertion.log。产品JS保持index-BL0x6A3Q.js；最终60源码/65资产hash一致，source_fingerprint=f3cb77c7455a4360318329c08658c98ef512b4b95dcf94dd55f6fa9380561b8b。

最终真实Edge运行见reading-e2e-final.log/json（npm在Windows吞掉grep，实际再次运行完整6项）：5通过、1失败。通过首页自动笔记/证据/主题导航、原完整导航、证据页保留、勾选联动、阅读自动展示/刷新/原文/版本导出；旧规模N0定位60秒超时保持失败，没有放宽断言。固定阅读截图reading-panel.png；首页宽窄和证据截图位于同Run的../home/。
