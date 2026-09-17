# 既有长期 Owner discovery 重建回执

日期：2026-09-18。执行范围只包括已存在规范 memory、预期长期复用的三个 persisted Owner；临时 Run 和纯原始来源未被强制补层。

低等级模型先逐 Owner 检查当前 HEAD、L4 和 L1 `retrieval_description`。三个 Owner 都只有 `DISCOVERY_INDEX_NOT_READY`，没有 `MISSING_L4` 或 `L1_RETRIEVAL_DESCRIPTION_MISSING`，因此没有修改规范正文、review 或固定引用。

| Owner | 固定 HEAD | generation | discovery entries | lexical | vector |
|---|---|---:|---:|---|---|
| `PRJ-ARCHITECTURE-EVOLUTION` | `COM-71d22958-3510-4d7d-8a3f-2948ed45ef92` | 56 | 36 | indexed | indexed，51 points |
| `RES-AI-EXPERIENCE-CONTEXT` | `COM-8630a759-cd9d-4ab5-aaa0-2373b32a0390` | 23 | 15 | indexed | indexed，17 points |
| `RES-FLOATING-POINT-SUMMATION` | `COM-fcaee2c0-43b4-4cd3-972d-96f508dde638` | 19 | 12 | indexed | indexed，27 points |

三个 Owner 的向量都写入独立 collection `memory_discovery_v1_8a65f36bacb3`，编码契约为 `owner-discovery-minilm-v1`；lexical/vector 错误均为空，projection missing 均为空。第一次在沙箱内实际写入时因派生数据库只读失败，随后按工作区授权在真实本地写入环境重新执行并成功；规范 memory HEAD 未变化。

检查期间还发现浮点研究当前 generation 19 仍引用一个被工作树删除的不可变 generation 16 提交目录。该目录从当前 Git 提交逐字节恢复后，规范读取和 discovery dry-run 恢复；没有改写历史或创建替代记录。

本回执只证明三个固定 HEAD 的派生索引建立成功，不评价 Owner 召回率、延迟、CE 成本、上下文占用或错误联想率。
