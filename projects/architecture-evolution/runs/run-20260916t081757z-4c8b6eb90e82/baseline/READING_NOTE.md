# 能力偏好扩展：既有规范与分发基线阅读说明

读取时点为 2026-09-16 08:20Z；Owner `PRJ-ARCHITECTURE-EVOLUTION` 的公开 API HEAD 为 `COM-ac1bd612-307a-49e1-a9d1-703f4781a032`（generation 38，manifest `c6a82cb5838aef370fdc525ed9a41225c8cbe944011e575c0c2740f820d63988`）。以下仅记录只读事实，不改变任何旧 Run 或规范 MEM。

## 已完整读取的固定内容

| 项目 | 固定版本与哈希 | 完整性 |
| --- | --- | --- |
| 设置完整报告 | `MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152` r1，`039bf59d7e92f80067b2c299f0c696719ae418c7adce5b3213f5557bd57c648f` | `document` 的 `report.complete=true` |
| 设置概览 | `MEM-67e69e5f-8de7-5c24-b8bc-eb41299f8eaf` r1，`d8ba36ed48af94e8dece307a8c9b51ba12dc5fcd222e0c4c1892cbe2b3b9bdd9` | 已由 `inspect-*-retry.json` 完整回读 |
| 委派完整报告 | `MEM-bd121869-a0b9-59e3-af23-8e8675374a63` r1，`8f943445fda90acab96cae1c5e013b43eb7f54f888fa11e50f7492f987ed8779` | `document` 的 `report.complete=true` |
| 委派概览 | `MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155` r1，`5f4c0893d4660491c3c4a44fd4773ad2f3dcd2b6c26d75e10199ad5358e7e0fb` | 已由 `inspect-*-retry.json` 完整回读 |

两份 `document-impact` 都以相同 HEAD 运行，均返回 `changes=[]`、`affected_section_ids=[]`、`uncovered_unit_ids=[]`、`scientific_review=not_evaluated`、`writes=0`。最初 `inspect-*.json` 是 shell 重定向先创建空 JSON 后被业务扫描的 `INTEGRITY_ERROR` 回执，保留为失败证据；同名 `*-retry.json` 均在 API 成功返回字符串后才写入。

## 随 `collaboration.subagent_requirements` 改变而应更新的现行内容

1. 设置契约/CLI/HTTP/UI 的 `collaboration.subagent_requirements` 默认、校验与可见说明；它是自由文本偏好，用户自定义优先于程序缺省，不能扩大工具、材料或来源权限。
2. `work-loop` 的派工说明：读取一次精简 policy，按这段偏好选择宿主实际可用的模型与推理深度；无用户自定义时才使用低成本、较低能力和低推理深度的默认偏好。
3. `material-query` 的委派说明与 `reading-delegate` 任务包：只传最小任务包，使用宿主实际可派工能力；`auto` 仍须同时满足宿主支持和任务适合，`off` 或缺能力仍沿同一 RS 单 Agent 回退。
4. 设置/委派两份现行报告和概览的“默认偏好”表述需更新为新要求，但不应倒改其历史实现、当时实际 reader（`gpt-5.6-terra`, `low`）或验证证据。

## 必须保留为历史范围的验证数字与边界

- 设置阶段：cold `3.1212 ms`；2000 次 warm p50 `0.38795 ms`、p95 `0.7553 ms`；13 项设置集成、41 项阅读/重排、48 项组件、2 项浏览器、18 项真实 setup 升级检查均是当时的实际结果。它们不证明端到端检索加速、宿主硬禁用、第二物理机或业务相关性。
- 委派阶段：既有 41 项阅读测试、9 项委派集成、2 项 handoff 语义、合计 52 项不同阅读行为的通过证据；真实合成 reader 的 9 次 API 响应 `86,788` 字符和主侧两次 handoff `8,080` 字符得到约 `90.7%` 的序列化字符体积对比。它不等于 token、总费用或端到端延迟；首版笔记漏项、dense 不可用、候选窗口未完及 `complete=false` 覆盖缺口必须保留。

## 文稿覆盖范围

两个独立文稿各含一个 L1 单元（设置：`MEM-472e4d18-f18d-5d13-84e3-28d3d5ae211a`；委派：`MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b`）。报告组装完整不等同于覆盖整个 Project：每份 `report_coverage` 仍列 18 个未覆盖 L1，且两份集合互相包含对方新单元。不得据任一报告宣称 Project 全体历史内容已同步。

## 工作区设置与分发边界（只读）

- 根 `workspace-settings.json` 在读取时不存在；`.gitignore` 明确排除它、锁文件与临时文件。`git -c safe.directory=... ls-files -- workspace-settings.json` 无输出，因此它既不在当前工作区也不受 Git 跟踪。
- `automation/scripts/workspace_settings.py` 的内置 `_defaults()` 是公共代码，当前 SHA-256 `48e29834073fbf41517315bbdebe35e0a83ebd8bdc495eb248a937f1acb24ab6`；缺文件时由该代码解释完整默认而不落盘。
- `automation/scripts/deployment.py` 的 `framework_files()` 遍历 `automation/` 的 `.py`，因此会将 `workspace_settings.py` 及 CLI 纳入框架分发；`seed_files()` 又明确排除 `workspace-settings.json`，升级不会复制开发机偏好。一次 `framework_files(Path('.'))` 静态探测因相对路径触发 `THIRD_PARTY.txt` 的 `relative_to` 异常，未重试，也没有遇到或掩盖资源指纹错误。
