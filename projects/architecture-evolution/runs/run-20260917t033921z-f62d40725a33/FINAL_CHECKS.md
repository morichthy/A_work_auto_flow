# 最终集成检查

2026-09-17，Codex 执行。本文件是软件与记录维护回执，不是浮点结论的科学确认。

- `automation/workspace.ps1 refresh-index`：成功。
- `automation/workspace.ps1 validate`：退出码0，0错误、21个既有警告；20条历史链接警告及1条模型文件大于25 MiB警告，无本轮Run记录不完整或快照链接警告。
- `workbench.cmd testing audit`：passed；发现855、登记857，未归类、缺失和错误均为空。
- 本轮代码、Skill与文档范围的 `git diff --check`：退出码0；采用兼容CRLF的空白规则，未改写历史记录换行。
- 其他针对性软件检查、19项Windows升级/恢复和最终12页真实快照结果见 UI_VALIDATION.md、UPGRADE_VALIDATION.md 与 RESULTS.md。

初次集成校验为0错误、176警告：本轮Run尚缺输入/质量结果，且复制的Markdown快照被当作现行导航扫描。已补齐真实输入与质量结果；快照保持原始字节，Markdown文件仅追加 `.snapshot` 扩展名，SOURCE_MANIFEST_v2.json记录原路径、保存路径、大小与SHA-256。修正后重新刷新和校验得到上述21个既有警告。

SOURCE_MANIFEST.json固定27个相关已修改文件的验证状态，其中可能包含此前未提交变化，不表示本轮独占这些修改。科学复核仍为not-reviewed，正式工作台旧服务未关闭，加载新后端需重启。

清单补充保存路径时，登记入口拒绝覆盖已固定版本；随后通过公开回滚撤销最新输入登记，按原哈希恢复第一版清单，新映射单独保存为SOURCE_MANIFEST_v2.json并重新登记。原登记版本与历史回执均保留。
