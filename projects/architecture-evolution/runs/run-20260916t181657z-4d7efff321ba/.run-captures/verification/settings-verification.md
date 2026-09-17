# 设置验证记录

日期：2026-09-17。以下为本子任务实际工具执行结果摘要；早期输出保留在本对话工具回执，未伪造逐行stdout。运行环境为现有Windows工作区，未新增依赖。所有服务测试使用合成隔离目录，不修改私人工作区设置。

## 实际命令与结果

根目录执行：

```powershell
.\automation\python.ps1 -m unittest discover -s automation/tests -p 'test_workspace_settings*.py' -q
```

- 基线15项通过。
- 最终18项通过，0.931秒，exit 0；包含context严格边界、旧配置只读兼容、Owner新模板消费与既有会话固定，以及原CAS/缓存/HTTP/CLI。
- 初次错误使用模块路径automation.tests，但嵌入Python不识别automation包；改为既有discover入口后通过。
- 开发过程中一次reading_owner模块尚未落盘引入失败；另一次新默认owner_document使旧RS测试resume正常返回partial。旧RS测试明确设置mode=legacy，同时新增独立Owner context测试，最终通过。

在automation/frontend执行：

```powershell
npm test -- --run src/WorkspaceSettings.test.tsx
npm run typecheck
npm run build
npm run e2e -- settings.spec.ts
node scripts/manifest.mjs
```

- 组件基线10项通过；修改后11项通过，2.47秒，exit 0。
- 类型检查exit 0。
- build（含contracts、typecheck、vite与指纹）exit 0。存在既有超过500kB chunk提示，未宣称消除该体积问题。
- 最后一次e2e 2项通过，6.1秒，exit 0：真实HTTP保存/重载Owner和note预算，材料及工程预算保留；导航草稿、版本冲突、显式重读后保存。
- 首次浏览器冲突用例失败：现有全API mock不能满足当前页面预载依赖；修复为只mock settings，其余请求使用真实隔离HTTP服务，路由统一#/settings。测试源码修改后曾触发正确的源码指纹不匹配启动拒绝；刷新manifest后重跑通过。
- 最终manifest刷新exit 0。现有node_modules缓存/构建产物权限需要require_escalated执行；未改变全局文件权限。

已人工查看工具显示的全页截图，主要Owner数/note预算清楚可见，工程预算默认折叠，无遮挡：
`automation/frontend/test-results/settings-真实HTTP保存配置并在页面重新载入后保持/settings-real-http.png`。

## 软件边界

reading.context默认max_owners=10、note_max_tokens=6000。严格整数范围分别1..100、512..50000；note token为保守估算而非宿主精确token。旧schema1文件缺context时只读补默认，原字节/revision与用户自定义不变，新写入仍需完整快照。materials不变，旧reading.budget保留。

后端同伴确认Owner模式兼容原candidate_ids读取原文及packet响应，故本次未改ReadingSessions等组件。无新增依赖，前端预构建资源已更新。

真实setup扩展旧工作区测试另外写入setup-tests.log；以该日志的实际结果和EXIT_CODE为准，不以此摘要预先宣称通过。未进行第二台物理机验收；组件/浏览器通过不代表实际AI语义正确。

最终只读SHA256核验：manifest列出的60份前端源码与65份资源全部匹配，mismatches=[]，exit 0；未额外重建。浏览器实际JSON报告及截图已复制到同目录settings-e2e.json、settings-real-http.png。真实setup测试最终exit 0；完整计数与耗时见setup-tests.log的unittest summary。
