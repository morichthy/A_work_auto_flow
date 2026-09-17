# AI 工作流入口

需要归属、工作记录或交接的任务默认由[work-loop](work-loop/SKILL.md)处理，方法由AI按任务判断；当前源码、配置、默认参数或命令状态的简单直接检查不启动流程。各Owner共用按内容组合的L0–L4，不强制每轮补层或双文稿。

| 活跃Skill | 何时使用 |
|---|---|
| [work-loop](work-loop/SKILL.md) | 有产物、结论或复用价值的工作；极小操作可不新增记录 |
| [consolidate-results](consolidate-results/SKILL.md) | 整理更新当前成果；重要结论保存、阶段总结/交接与实质变化后的完整文稿和上下文一致性检查 |
| [material-query](material-query/SKILL.md) | 查本地材料、完整阅读和维护阅读记录 |
| [context-maintenance](context-maintenance/SKILL.md) | 批量接入、来源整理与文档代码映射 |
| [development-checks](development-checks/SKILL.md) | 开发验证及受影响文档/接口维护 |
| [association-exploration](association-exploration/SKILL.md) | 专门跨领域结构分析 |
| [evidence-inspection](evidence-inspection/SKILL.md) | 复核/依据追溯和显式监测 |
| [semantic-maintenance](semantic-maintenance/SKILL.md) | 新依据对下游内容的实际语义修订 |

默认发现/安装8项。research-loop和workspace-context已退休并删除方法目录，统一使用work-loop；不再提供旧名安装。旧CTX/CF/MQ/QMEM/PKT各自兼容，不能改名混用。主Skill不复制参数手册；公共动作见[参考](../../docs/WORKFLOW_ACTIONS.md)。

单独安装器只补缺失入口，冲突输出差异；setup升级只对精确匹配已登记旧指纹的受控入口更新/退休，进入同一可恢复备份。用户修改/未知版本继续保留，需按差异合并。旧受控发现入口退休需验证指纹并保留备份；不能按旧名称批量删除自定义Skill。升级仍用setup.cmd，不以单装Skill替代升级。开发全局整合时核对全部活跃入口与退休迁移与实际工具调用。
