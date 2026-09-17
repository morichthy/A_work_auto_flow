# 证据台账

整理日期：2026-09-12。固定分析 Run：`RUN-20260911T220732Z-537995938D50`。

| 依据 | 范围/用途 | 限制 |
|---|---|---|
| [用户原方案](runs/run-20260911t220732z-537995938d50/user-proposal.txt) | 原 A/B/C/D 基线，保存原始字节 | 需求与想法，不是效果证据 |
| [先前讨论快照](runs/run-20260911t220732z-537995938d50/discussion-before-research.md) | 初始建议、用户纠正、当前接口缺口 | 快照中的相对链接沿用原位置，不表示新路径可直接跳转；当前入口见 README |
| [讨论经过和取舍](runs/run-20260911t220732z-537995938d50/discussion-decisions.md) | 当前用户原话、路线变动及采纳/暂缓理由 | AI 事后整理，非全量聊天原文 |
| [一手来源阅读笔记](runs/run-20260911t220732z-537995938d50/primary-source-notes.md) | S1–S9：论文/官方方法事实、适用及不能推断的内容 | 固定笔记而非远端全文；S8 只读摘要 |
| [索引实现快照](runs/run-20260911t220732z-537995938d50/memory-index.py)、[技术单元快照](runs/run-20260911t220732z-537995938d50/technical-units.py)、[查询协调快照](runs/run-20260911t220732z-537995938d50/material-query-coordinator.py) | 核对正文投影和当前公开检索能力 | 静态证据，不是本地漏检率或性能实验 |

七个文件已通过 run-register 固定 SHA-256，并逐文件登记到来源目录，供规范记录回源。L0 可用 memory raw-materials 查看；使用时仍核对权限、来源和指纹。

## v0.1时点证据判断（保留原依据）

- 来源事实：背景补充、Small2Big、语料反馈和多层/图查询分别作用于不同阶段；具体细节见来源笔记。
- 本地静态事实：v3 detail 的普通发现主要使用检索说明；当前 MQ 的公开能力未登记 dense 提供器。
- 待验证推断：多层独立正文发现可能减少高层未命中漏检；必须以固定案例与基线对照确认。
- 用户选择：明确同意初检反馈扩展查询；其他增强未最终选型。

## 保存与核验

v0.1规范记录、文稿完整性、索引和校验结果见[原保存回执](RECORDS_v0.1.md)。该阶段未执行真实检索对照，无数字成绩或科学验收。完整来源可访问性以后如有变化，不能沿用本笔记假称已重新读取。

## v0.2基础专项新增依据

固定Run：`RUN-20260912T021858Z-B6E2DA1386D3`，物理归属架构项目，本研究固定引用复用。

- [实施与验证](../../projects/architecture-evolution/runs/run-20260912t021858z-b6e2da1386d3/RESULTS.md)：原用户授权、正文漏检前后对照、最终81项定向、18项真实升级及四题语义测量。来源`SRC-RETRIEVAL-FOUNDATION-20260912-RESULTS`。
- [最终程序指纹](../../projects/architecture-evolution/runs/run-20260912t021858z-b6e2da1386d3/final-code-manifest.json)：代码/测试/模型清单快照及实际运行依赖版本。来源`SRC-RETRIEVAL-FOUNDATION-20260912-CODE-MANIFEST`。
- 原始输入、失败/通过日志及实际AI查询由Run登记；公共raw-materials与raw-material核验。旧B01失败没有删除或改成通过，小样本成绩不能推广到业务或大库。
- L1、L2及概览、经验和双文稿固定修订见[v0.2保存回执](RECORDS_v0.2.md)。保持not-reviewed的科学复核状态；实际软件检查与AI阅读自查分别描述。

## v0.3阅读工作流新增依据

固定Run：`RUN-20260912T195347Z-39FFE0EE7711`，物理归属架构项目，本研究复用。

- [实施与验证](../../projects/architecture-evolution/runs/run-20260912t195347z-39ffe0ee7711/RESULTS.md)：来源`SRC-AI-READING-20260913-RESULTS`；56项不重复行为与18项升级测试，保留初始失败及范围纠正。
- [实际阅读笔记](../../projects/architecture-evolution/runs/run-20260912t195347z-39ffe0ee7711/READING_NOTE.md)：来自公开会话恢复响应，AI实际阅读并写回，未复算原浮点实验。
- [固定记录回执](RECORDS_v0.3.md)：L1实现、L2经过、L4和双文稿；原L3复审保留，无新增普遍业务质量结论。
