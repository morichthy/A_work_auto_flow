# 最近阅读与证据导航：后端结果

## 实现范围

- 四个普通 JSON POST：`reading-notes/recent`、`reading-notes/snapshot`、`evidence/search`、`evidence/detail`。共享实现位于 material_query，workbench_app 只转发；核心不反向依赖 HTTP 层。
- 最近入口使用语义 updated_at 的闭区间 `[now−24h, now]`，排除未来和归档，按实际时间降序，支持 offset/limit/total/next_offset；Owner 过滤不污染全局 context 导航。浏览不改变 RS 修订或更新时间。
- 签名 sidecar 绑定格式、MD hash、权限元数据和本 RS HEAD stat；业务权限变化重新检查，HEAD 更新而快照写入中断时按需重建选中 RS。热读不调用强 reauthorize、EvidenceGraph 或原件 SHA。保存快照始终明确“未重新核验证据”。
- 服务端显示稿提供编号引用和参考文献，FixedRef 完整保留在 references/deep link。不同 revision/hash/locator 不合并，不替换代码、公式或已有链接；未知 ID 不编造出处。AI 交接采用短编号避免 URL 开销挤掉原可交付笔记，UI 的 30,000 字符显示预算独立于 AI note 预算。
- 证据搜索覆盖合法 native Owner/Run、MEM 和兼容 claim；详情支持已登记 SRC 摘要及定位信息，原件内容不读、不哈希。固定版本/哈希不符明确拒绝；引用及反向影响使用已授权 metadata。损坏对象隔离并给 warnings。
- reader guidance 明确要求 `$...$` / `$$...$$` 数学分隔符。共享升级 fixture 增加 sidecar 与 recent.md 保护项。

## 测试过程与证据

先写关键测试，首跑因缺少 `workbench_app.reading_notes` 导入失败；实现后初次 7 项通过。扩展 payload-only 结论检索负例时暴露旧索引压住当前记录，修复为根据 manifest hash 判断索引是否可用，保留 canonical fallback。

- `python -m unittest discover -s automation/tests -p test_recent_notes_evidence.py -v`：最终 **10 项通过，59.898 秒**，见 `backend-recent-evidence-final.log`。覆盖 24h 边界、未来、时区排序、临近 AI 预算、固定引用、禁止慢调用、撤权、MD 篡改、HEAD 单独更新、全局导航过滤、payload-only 搜索、SRC 与版本约束。此前 10 项 58.983 秒日志保留于 `backend-recent-evidence.log`。
- `python -m unittest discover -s automation/tests -p test_reading_handoff_view.py -v`：**3 项通过，0.033 秒**，见 `backend-handoff-regression.log`。
- 父任务执行更广阅读与 Windows 升级回归，此处不重复宣称其结果。

## 实际性能

同机、同一业务库、真实 RS `RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b` r8，脚本及完整数据见 `measure_reading_navigation.py`、`navigation-performance.log`。

| 操作 | 秒 |
|---|---:|
| 原 reading-list | 51.769 |
| 原 reading-view（选中 RS） | 15.110 |
| 新 recent 首次调用 | 1.107 |
| 新 snapshot | 0.178 |
| 新 recent 热读 | 0.233 |
| 新 snapshot 热读 | 0.224 |
| native Run 搜索 | 2.700 |
| native Run 详情 | 2.980 |

首次单独重建该旧 RS 显示稿为 1.689 秒；完整显示 7,478 字符、1 份 note、0 份省略、11 条固定引用，公式文本实际存在。原 view 2,180 字符；显示装饰未修改 canonical note。上述为本机观测，不代表其他磁盘或库规模保证。

## 真实强交接观察边界

最初 CLI 观察到 INTERNAL“材料完整性检查失败”，后端也复现一次（`handoff-cli-diagnostic.json`）。独立新进程 Coordinator + reading-handoff 得到 partial（14.381 秒；`live-handoff-fresh.log`），r8 一份 note、缺口为重排正文超过模型窗口；此前另一次为 19.045 秒（`live-handoff-final.log`）。保持公开 API 校验的诊断重跑及父任务重跑随后也成功，未捕获 MemoryError；失败与成功均使用提升执行权限，不能归因为权限或缓存顺序。运行差异尚未定位，保留原始失败回执，不宣称其原因已经修复。

父任务随后通过正常公开 reading-note API 保存纯公式排版修订 r9，并验证 21 个 KaTeX 公式和 11 条固定引用。后端没有修订历史哈希、修改该 RS 或绕过强核验。诊断脚本仅位于本 Run，未修改框架源码；按父任务要求停止进一步诊断。

静态 recent.md 只在列表/写入刷新，不会自行随时钟变化；证据详情 metadata_only 与笔记 snapshot_only 都不构成业务证据重验。
