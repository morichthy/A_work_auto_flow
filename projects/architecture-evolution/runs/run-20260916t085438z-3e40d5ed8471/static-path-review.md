# 材料阅读全链路：静态性能候选审查

范围：仅审阅当前源码，未查询任何真实材料、未启动向量/重排模型或索引，也未改动源码和既有 Run。本文件列出的是**可能的耗时来源**，不是实测结论；应由同一输入、冷/热进程分组的计时 driver 核实。固定版本、当前授权、来源闭包与撤权检查是正确性/安全边界，不能为了提速直接关闭。

## 路径与可疑重复工作

| 阶段 | 静态路径 | 候选成本 | 为什么可能重复 |
|---|---|---|---|
| 每个 CLI 动作 | `material_query/cli.py:24-25` | 新建 `Coordinator`；Python 进程导入与解释器启动不在此文件内但会落入每个独立 CLI 调用 | `template/start/delegate/recall/read/note/decide/handoff` 若各为一个进程，均重复冷启动；`Coordinator` 自身还新建两个线程工作者（`coordinator.py:180-188`）。 |
| template | `reading.py:110-123` | 读取工作区设置、构造默认请求/UUID | 很小，但独立 CLI 的启动成本可能掩盖它。 |
| start | `reading.py:204-233` | `_new` 契约解析；`check_binding` 可解析 Owner/检查点；写入并 `fsync` RS `HEAD.json` | `check_binding` 经 `reader.owner` 可能触发 Owner 全扫描；若有 checkpoint，还会固定读取/来源授权。 |
| 所有既有 RS 动作（含 delegate/handoff） | `reading.py:149-191`、`235-257` | 会话锁、读并验证整个 RS JSON/digest、每次执行 `reauthorize`；非 view 类还会原子写 + `fsync` | `delegate` 和 `handoff` 虽不读候选正文，仍会逐候选和 contributor 重做当前权限、固定版本与来源闭包复核。RS 接近 4 MiB 或候选/依赖很多时可见。 |
| Owner 解析 | `memory/owners.py:208-359`、`369-373`；`reader.py:145-159` | `list_owners` 扫八类业务目录、读取/哈希元数据、枚举目录且完成前重检；`resolve_owner` 每次调用重新扫描 | `Reader.locate/owner` 为记录和闭包中的每个 Owner 使用此路径。单个 Reader 的 `owner_cache` 能减轻同一进程内重复，但跨 CLI 进程不复用。目录规模、中文/长路径和防链接/大小写检查会影响此项。 |
| recall | `reading.py:359-490` | 查询规划后，对 3 个 lane × 每条 query route 建状态并同步 `_run_search`；每个 route 独立召回 | 这是高优先级候选：默认 LANES 是 3 (`reading.py:27-28`)，每路都走 Coordinator/Reader/索引通道；无论最终只保留少数候选，均有前置检索与候选组装。 |
| recall 的候选交付 | `reading.py:434-480`、`303-314` | 每个候选 `packet` 创建 Reader/Assembler，固定读取记录、依赖和链接；返回 packet/hits/query diagnostics | 默认 off 时仍会为每 lane 的前 `result_limit` 个候选组包。相同固定记录若跨 lane 命中，RS 级无 packet 缓存；每次 `packet()` 都新建 Reader，进程内记录缓存也随之失去。 |
| fixed ref / 来源闭包 | `reader.py:161-183`、`195-274`、`302-313` | 每 record 读当前和固定修订、HEAD；递归 `sources/payload`，文件做当前可读检查；claim 可查询 SQLite 和回溯历史修订；最终 basis 再读各 Owner HEAD | 这是刻意的 current-access + fixed-version 保障。`reading.reauthorize`、组包和 `note` 都可再次进入；闭包深度、跨 Owner 数、历史 claim 回溯与文件数决定放大程度。 |
| read | `reading.py:507-524` | 每个已选候选重新以 full 定义组包，回读全部正文及 contributor | recall 已交付的技术候选可能是 section/unit digest；完整阅读必需重取。即使原先已 full，当前实现仍再次 `packet`，因此可测是否存在可安全复用的同版本完整 packet 的机会。 |
| note | `reading.py:526-550` | 为验证 `block_ids` 再 `reader.record`，且外层通用 `reauthorize` 已跑完 | `note` 本身没有重新交付正文，但会再固定读取该记录/闭包；这是安全校验和字段验证的额外成本候选。 |
| decide | `reading.py:552-568` | 外层通用 `reauthorize` + 读/写 RS；方法体只更新阶段/决定 | 对纯状态转换而言，前置全候选复核很可能主导；是否可在不降低撤权语义的前提下采用更窄的验证需先以数据和威胁模型审查。 |
| delegate | `reading.py:570-580`、`reading_delegation.py:17-46` | 外层全量 reauth 后读取设置、构造 brief、序列化计量 | `delegate_value` 明确不 spawn/不读正文；若此项慢，首要查通用 reauth、冷进程和 owner 扫描，而非 brief 构造。实际外部子 Agent 启动/模型时间不在该 CLI 内。 |
| handoff | `reading.py:582-590`、`reading_delegation.py:118-197` | 外层 reauth 后遍历笔记构造 Markdown，逐次 JSON 序列化以满足 512–30000 字符上限 | 12k 默认返回体和 JSON 序列化可计入；更大 `max_chars`、笔记数及 details 数会放大。它有意不返回全文/候选历史。 |
| optional rerank | `reading.py:401-429`、`reranking.py:72-150` | 先为候选窗完整组包，再按进程延迟加载 ONNX provider、分词和推理 | auto/required 才触发；每个新 CLI recall 进程都不共享 provider，`model_load_ms` 已在回执诊断中可观测。不要把 rerank 与纯 reading 流程混在一组计时。 |

## 计时解读建议

1. 先分别报告**子进程墙钟**和动作内已有的 `consumed.wall_ms`/recall route `elapsed_ms`/rerank `model_load_ms` 与 `inference_ms`。前者含解释器与 import，后者更接近服务逻辑；两者差值才是冷启动等固定开销的候选代理。
2. 为每个动作记录 RS 规模（字节、candidate/note/contributor 数）、Owner 数、lane×route 数、候选数/正文字符数、来源闭包节点数、是否 rerank、以及 handoff 字符数。否则同名动作不可横比。
3. 对 `recall` 区分 lexical/identity/dense、每 lane/route；对 `read` 区分原候选 reading form 是否已 full；对 `note/decide/delegate/handoff` 单列 reauthorize 时间。现有代码尚未给这些子段打点，driver 的外部总时只能先定位，不能归因。
4. 做至少冷进程与连续常驻服务两组。若冷进程差显著，优先评估可复用服务/批处理边界；若 reauth/闭包占主导，优化必须保持“当前授权 + 固定引用 + 并发 HEAD 观察”的等价保证。

## 不应从本静态审查直接得出的结论

- 不能断言 Owner 扫描、递归闭包、模型加载或返回体已经是瓶颈；没有真实输入和计时证据。
- 不能以缓存替代当前撤权、`record_hash`、来源闭包或最终 HEAD basis 检查；任何缓存设计须定义失效条件、跨进程边界及并发一致性。
- `delegate` 的程序回执不等于实际子 Agent 已派工；外部 Agent 与宿主模型时间须独立测量。
