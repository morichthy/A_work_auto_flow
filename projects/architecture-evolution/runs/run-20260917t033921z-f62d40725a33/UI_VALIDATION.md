# 对象记忆筛选与结论复核展示验证

执行日期：2026-09-17。执行者：本任务 UI 子 Agent。环境：本机 Windows x64、现有 Node/npm、仓库锁定前端依赖及 Python 运行时。全部软件场景为隔离合成数据；不证明真实浮点研究结论，也未进行第二台物理机验收。

## 改动及边界

- `automation/frontend/src/Memory.tsx`：主要筛选仅 L0、L1、L2、L3、L4、研究文稿六类；独立章节归入研究文稿。旧 event/map 仍在对应 L2/L4 可找到。目标、问题、检查点、复核、策略等必要工作流记录从主筛选移至折叠的辅助记录入口，保留查看、编辑适用记录、历史版本与按选中集合导出；没有删除或改写存储类型。
- `automation/scripts/material_query/evidence_navigation.py`：详情读取所选结论所属 Owner 的已保存 review，返回逐 claim 状态、范围、复核者、原因和时间；核对复核的内容指纹和 claim 指纹。不同版本不显示为当前已确认；复核不可完整读取时显示不可读取，不能误报未复核。目标 claim 已随选中记录授权，复核其他来源继续核对访问边界。没有运行全库科学证据图，也不把已保存确认等同当前依赖全部有效。
- `automation/frontend/src/EvidenceBrowser.tsx`：展示上述独立复核区；无 claim 的材料明确显示未登记可独立复核结论。保存、执行成功、已确认、实时证据有效性继续分别表达。
- 扩展现有组件、证据内容、E01 复核 API、浏览器导航用例，未新增测试 ID。构建资源和源码指纹已更新；没有依赖/模型/安装器或目录扫描逻辑变更。

## 实际验证

| 命令（工作区根，另有说明除外） | 结果 |
|---|---|
| `.\automation\python.ps1 -m unittest discover -s automation/tests -p test_evidence_content.py -v` | 最终 8/8 通过；包含版本不匹配、不存在复核、不可访问复核的状态边界 |
| `.\automation\python.ps1 -m unittest discover -s automation/tests -p test_memory_evidence.py -v` | 17/17 通过；E01 增加真实提交/复核后详情显示 accepted 与 not-reviewed 的逐结论区分 |
| 前端目录 `npm test -- --run src/Memory.test.tsx src/Evidence.test.tsx` | 7/7 通过；六类筛选、章节归类、旧层级兼容、辅助记录按需可见，以及确认/未确认/陈旧复核展示 |
| 前端目录 `npm run build` | 通过，包括 contracts、TypeScript 检查、Vite 构建和清单；仅保留既有大于 500 kB chunk 提示 |
| 前端目录 Playwright 指定 `e2e/workbench.spec.ts`，grep 正则为下方命令 | 最终实际无头 Edge 2/2 通过，17.8 秒；详情/六类筛选、文稿、图片实际解码、引用跳转及窄屏导航 |

```powershell
node node_modules/@playwright/test/cli.js test e2e/workbench.spec.ts --grep '记忆摘要进入|最近问题重开'
```

构建最终输出保存为 `UI_BUILD.log`，最终 Playwright JSON 保存为 `UI_E2E.json`。截图 `UI_EVIDENCE.png` 已由 AI 实际打开检查：确认状态在正文前可见，标题、正文、上下文、引用、影响均按区块显示，无可见截断或重叠。此为合成页面；真实更新后浮点记录另由主 Agent 检查。

## 首次失败与后续复验

1. 普通权限执行 Vitest 时，现有 `node_modules/.vite-temp` 写入报 EPERM，尚未开始测试；获自动审批的本机测试/构建调用后，同一 7 项全部通过。不是业务功能失败，也未修改权限或安装依赖。
2. 首轮浏览器 2 项在服务启动时被源码指纹保护拒绝：构建后补充了 `e2e/workbench.spec.ts` 断言，清单未更新。完成格式化及清单刷新后 2/2 通过；随后对不可读取复核状态补充边界文案、再次完整构建，最终 2/2 再通过。未降低指纹保护。
3. 阅读真实授权代码发现 Catalog 对 claim 引用只定位原生 claim，故不能直接将 memory review 的自引用交给该旧分支。本次对已授权的目标 claim 单独核对内容/claim 绑定，复核其余来源仍执行授权。真实 E01 存储/API 回归证明通过；没有将来源授权失败当作已确认。

## 真实材料预检发现与追加修正

在 generation 15 的真实浮点记录隔离副本中打开 9 条 L2/L3/L4/文稿，页面均可加载、没有 JS 错误或横向溢出，但 AI 实际看截图发现结构化字段仍有 `stages`、`situation`、`outcome` 等内部英文键，完整正文后又重复分项内容。已修正：补充中文标签和分类值；L2/L3/L4 已有完整正文时以正文为主，将结构化字段放入默认折叠的“结构化记录字段”，仍可展开阅读；确认状态保持可见，来源缺口仍在关键上下文。无完整正文时仍以结构化字段生成正文，避免隐藏历史内容。

相应组件增加折叠展开行为断言；真实 E01 API 增加正文与结构字段分别保留的断言。追加后 7 项组件、8 项证据内容与 17 项证据复核回归通过，TypeScript/构建通过。主 Agent 审查另指出辅助记录选中时“清空类型”仍可能保留辅助项，已改为同时清空两种选择，组件断言覆盖了展开辅助后清空不再显示辅助记录。

预检副本首次缺少 `retrieval/config.json`，导致顶栏环境信息报错；已将此最小配置加入受控复制范围，不修改正式工作区配置。文稿图片采用延迟加载，浏览器验收已改为逐图滚动并等待 `decode()` 后检查实际解码，不能把尚未进入视口误报图片损坏。中间版截图仅存在 tmp，最终材料验收单独固定，不能用旧版预检代替最终验收。

### 作者引用编号保护

L3 r6 实际截图进一步暴露：作者明确的 `[1]` 对应精确方法，但引用渲染按 sources 和 payload 合并顺序另生成的自动 `[1]` 对应另一份 L2，形成双编号。已修复：正文有明确“[n]…固定 ID”依据清单时保留作者局部编号，ID 转为精确的“固定版本 rN”链接，不附加冲突的第二套编号参考文献。未定位的引用仍在独立引用面板保留，不猜进正文编号；同 ID 多修订按显式 rN 匹配，仍歧义或缺版本则原文保留并显示缺口。代码、公式、已有 Markdown 链接及 URL 不改写。扩展既有引用回归后 8/8 通过，没有新增测试 ID。

## 最终真实浮点页面验收

固定原 Owner HEAD：`COM-fcaee2c0-43b4-4cd3-972d-96f508dde638`，generation 19。使用当前产品代码、生产构建资源和实际保存记录的隔离副本，**不是合成浮点内容**。仅复制浮点子树、其来源登记和 workspace/retrieval 配置；复制前后 HEAD 一致，验收结束原 HEAD 仍未改变。正式 PID 60740 服务及其锁未操作；测试服务已退出。

执行命令（从工作区根）：

```powershell
node projects/architecture-evolution/runs/run-20260917t033921z-f62d40725a33/ui-acceptance/floating_ui_check.cjs projects/architecture-evolution/runs/run-20260917t033921z-f62d40725a33/ui-acceptance/final
```

12 条页面全部成功：3 份 L0 r1、5 份 L2（r4/r5）、1 份 L3 r6、1 份 L4 r6、2 份文稿 r2。均无页面 JS 错误、顶栏/详情错误或横向溢出，确认状态区均可见。完整文稿 4 张图逐一实际解码，宽度为 2040、2040、2040、1955 像素，全部 complete=true。记录可见文本未出现新“固定引用缺口”。此结果证明本机固定材料的展示与导航可读，不代表重新进行科学确认。

实际使用 view_image 目视检查了下列代表截图：

- `ui-acceptance/final/floating-10-narrative-top.png`：L2 问题背景、输入条件、公式、研究经过和确认区。
- `ui-acceptance/final/floating-02-experience-top.png`、`-table.png`、`-collapsed.png`：L3 背景、实际证据结果表、边界、作者编号固定依据及默认折叠结构字段；确认区和正文分开。
- `ui-acceptance/final/floating-04-source-top.png`：L0 原件身份、位置、覆盖范围、如何读字段和使用边界。
- `ui-acceptance/final/floating-06-overview-top.png`：L4 对象背景、目标、研究路线与当前认识。
- `ui-acceptance/final/floating-07-document-formula.png`：完整文稿的基准及 Kahan 公式，无公式裁切或重叠。

脚本、完整页面图、首屏/表格/公式/折叠位置图、可见正文 txt 均保留在 `ui-acceptance/`。`final/FLOATING_UI_SNAPSHOT.json` 保存隔离副本绝对路径、原 HEAD、逐文件 SHA256、登记数量和所测 ID/修订；`final/FLOATING_UI_BROWSER.json` 保存每页结果、原 HEAD 未变化标志和临时服务器日志。临时服务地址仅为执行回执，已停止，不作为可长期访问链接。`tmp/` 与 `.local/` 均被 .gitignore 排除；归档脚本可从工作区根重跑，使用 `RDWORK_UI_ROOT` 可显式指定根目录。

## 实际页面启动

工作区根可使用 Python 直接调用现有启动函数，避免打开系统浏览器：

```powershell
.\automation\python.ps1 -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('automation/scripts').resolve())); import workbench; workbench.serve(Path.cwd(), open_browser=False)"
```

启动 stdout 会输出 JSON 的 `url` 字段，为带随机路径的本机回环地址。把 `#/evidence?id=<MEM-ID>&revision=<N>` 追加到该地址即可查看固定修订。需使用新进程加载本轮后端；本任务没有关闭用户既有工作台。若以 Start-Process 启动，必须 `-WindowStyle Hidden` 并把 stdout/stderr 保存到明确日志路径。
