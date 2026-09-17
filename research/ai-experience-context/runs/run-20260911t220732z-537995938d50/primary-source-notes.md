# 一手来源阅读笔记（v0.1）

整理时间：2026-09-12，Asia/Shanghai。性质：AI 对已访问论文/官方文档的机制摘记，不是逐字原文或系统综述。网页可能更新；下列固定登记只保证本笔记的字节，未固定整份远端网页。未执行本地检索质量实验。文献观察、迁移推断和用户偏好分开。

| 编号及来源 | 实际核对范围与方法事实 | 对本研究的启发及不能推出的结论 |
|---|---|---|
| S1 [RAPTOR，ICLR 2024，v1](https://arxiv.org/html/2401.18059v1) | 阅读查询方法与比较段；递归聚类摘要树支持逐层遍历和 collapsed-tree 全层检索，论文在 QASPER 小规模消融后选择后者 | 多层摘要不必成为唯一的逐级门槛。本地 L1–L4 是人工/AI 写作职责，不等同自动聚类树；没有理由直接重建一棵 RAPTOR 树 |
| S2 [Elastic hybrid search](https://www.elastic.co/docs/solutions/search/hybrid-search)、[ranking](https://www.elastic.co/docs/solutions/search/ranking) | 官方介绍全文与向量融合、RRF 及重排在搜索链条中的位置 | 精确词与语义候选可互补；融合排序不是相关性证明，不能推断本地固定 Top-K 或模型收益 |
| S3 [Microsoft Advanced RAG / Small2Big](https://learn.microsoft.com/ar-sa/azure/developer/ai/advanced-retrieval-augmented-generation#chunking-strategy) | 阅读 chunking strategy；细粒度检索后可返回邻近句子或完整段落以恢复语境 | 检索粒度与阅读粒度可不同；展开规则还须保留变量定义、步骤和适用条件，不能只靠相邻字数保证完整 |
| S4 [Anthropic Contextual Retrieval，2024-09-19](https://www.anthropic.com/engineering/contextual-retrieval) | 给块生成针对该块的文档背景，在建索引前附加，供嵌入和 BM25 使用；文中同时讨论候选规模和重排 | 解决孤立块缺少主体、时间和文档语境的发现困难；这与命中后的展开是不同阶段。AI 背景应可回源重建，不替代正文或自动变成事实；论文自己的组合收益不能移植为本地承诺 |
| S5 [CSQE，EACL 2024](https://aclanthology.org/2024.eacl-short.34/) | 阅读摘要及论文入口；利用初检语料中相关句子和模型生成知识扩展查询 | 初次结果提供本库用语，原查询需保留；初检错误可造成漂移，生成内容是检索假设，不是证据 |
| S6 [Query2doc，EMNLP 2023](https://aclanthology.org/2023.emnlp-main.585/) | 阅读摘要及方法介绍；先生成伪文档再用于扩展 | 可作未命中时的探索候选，但本研究优先语料反馈。伪文档没有实际来源，不得作为答案依据 |
| S7 [Self-RAG，ICLR 2024](https://arxiv.org/abs/2310.11511) | 阅读论文摘要；通过训练反思 token 支持按需检索及评价 | 借鉴检索是否必要的控制问题；普通 Skill 指令不等于实现该训练模型，自评不能单独证明材料充分 |
| S8 [RAG or Long-Context LLMs? / Self-Route，EMNLP Industry 2024，v2](https://arxiv.org/abs/2407.16833v2) | 本轮只核对摘要：在该论文的模型/题集与充足资源设置中，长上下文平均表现优于 RAG，而 RAG 成本较低；提出路由组合 | 必须把有界全文阅读列为比较基线。未逐项复核完整实验，不推断当前模型、中文业务材料或任意长全文的胜负 |
| S9 [Microsoft GraphRAG Query Engine](https://microsoft.github.io/graphrag/query/overview/) | 本轮阅读官方查询概览：local 联合实体关系与原始块，global 汇总社区报告，DRIFT 用社区信息扩展查询，另保留 basic vector RAG 对照 | 问题类型应影响路线。跨材料关系/全局综合值得比较图方法；查局部操作步骤不因此必须建图 |

S1–S7 在此前本次讨论中已访问，本笔记事后归并；S8–S9 本轮扩展范围时访问。没有全量检索最新论文、没有保证文献集合完整。下一轮如依赖具体算法或性能数字，应精读对应固定论文版本和实验设置。
