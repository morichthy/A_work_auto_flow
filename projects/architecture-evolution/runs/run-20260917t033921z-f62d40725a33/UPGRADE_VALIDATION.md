# Windows 升级与测试登记核对

2026-09-17，本机 Windows x64。主 Agent 运行现有合成旧工作区回归：

```powershell
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_deployment_workbench.py -v
```

实际进程退出 0，19 项全部通过，unittest 报告耗时 343.541 秒。覆盖真实 setup.cmd 的 Windows ZIP 升级/恢复、扩展业务文件与目录保护、重复升级、损坏和入口缺失拒绝、来源与旧文稿固定读取、注册及本机 HTTP 边界。八类 Owner 的 Run 布局以隔离合成材料核对。本次没有依赖/模型变更，不执行全量依赖打包；结果不代表第二台物理机或真实业务验收。

测试目录 catalog 从 revision111 更新至112，扩展既有确认状态与筛选断言，不新增 quick 成员。运行 `workbench.cmd testing audit` 返回 passed，discovered_count=855，catalog_count=857，unclassified/missing/errors 均空。

以上为实际工具输出的摘要，非完整 stdout 副本；UI 详细日志另见 UI_VALIDATION.md。软件通过不能证明浮点结论正确或 AI 记录独立性。
