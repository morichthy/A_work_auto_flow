# 已有工作区升级测试

升级目标通常已经被用户扩展。测试必须同时回答“新增目录是否仍能被正确校验”和“升级是否保留用户已有内容”。不以少数固定路径存在或进程退出 0 替代这两项检查。

## 共享场景

`automation/tests/upgrade_fixture.py` 在临时目录生成合成材料，供普通升级集成测试和完整依赖发布验收共用。当前包含七类业务目录的多层分支、中文空格路径、空目录、包目录/脚本集合/单文件工具、自定义 Skill、automation 用户扩展，以及应剪枝的 node_modules 和 .local 缓存。生成的数据不进入 Git 或公共依赖包。

fixture 返回每个受保护文件的 SHA-256 和需要保留的目录集合。预览、升级、重复升级、恢复后逐项核对；登记表和旧配置也纳入保护。新增框架文件可以写入，因此不简单比较升级前后整棵树是否完全相同。

历史 Run 搬迁场景保留不存在的旧路径、现位置文件及带固定 SHA-256 的 `relocated_from` 来源登记；每轮保护核对还实际解析旧引用，确保升级后历史内容仍可读取。

Run 自动登记场景还包括 `.run-captures/` 内的登记回执、失败日志、多层结果和空目录，以及名为 `outputs/run.json` 的非元数据原始文件。此保留容器不作为业务卡或常规知识正文扫描，升级仍逐项保护其字节；父 Run 与普通业务目录的真实损坏继续报错。

材料查询场景通过公开维护入口创建未审查计划，将`.local/material-query/plans/`中的实际固定上下文、交付回执和不可覆盖计划版本加入保护清单。这些用户维护进度与可重建索引缓存分开，预览、升级、重复升级及恢复均逐项核对原字节；合成计划不标记为实际AI审查通过。

当前 fixture 还通过真实创建/提交入口覆盖八类对象内 Run：目录型 owner 使用自己的 runs，单文件 owner 使用 memory_home.runtime/runs，工具使用 tools/runtime 下的 runs。记忆保护包含 owner/HEAD、不可变提交、幂等回执及故障现场；v1/v2 历史、旧 L1 正文和 map 编排继续按固定版本读取。另有 v3 方法技术单元、稳定块依赖、独立章节及 research_process/research_report 双文稿，升级后的读取检查核对固定 SHA 和必需定义闭包。它们是合成软件场景，不提供业务模型有效性的证明。

## 按变更选择验证

阅读会话场景通过公开 reading-template/start/decide 创建真实 RS 目标、条件、下一步与修订历史，将 `.local/reading-sessions/` 的 HEAD/历史文件纳入同一保护清单；预览、升级、重复升级及恢复须逐项保留字节。它不是可重建索引缓存。会话含真实owner_id绑定。

阅读副本同时保护 `context/reading-notes/` 中的现有 Markdown、中文路径和空目录；新版安装器不能把开发机的私人笔记复制到目标。升级补齐 Git 排除但保留用户原规则；源码归档也排除该目录。副本不进入普通知识发现或通用上下文注入，原 RS 仍是唯一会话状态。

术语库场景将用户修改的`retrieval/query-terms.json`纳入完整保护清单；真实setup升级/重复升级/恢复保留字节。另验证缺失时由`automation/templates/query-terms.default.json`补种、回滚恢复原不存在状态。发行源不复制开发工作区的私人词库，公共包仅含受控模板；模板用LF保持Windows/Git指纹一致。

受控Skill退休场景核对旧入口精确LF/CRLF指纹：默认research-loop/workspace-context只移除发现文件，保留用户附属文件；新版不再分发旧方法源；新版活跃入口更新进入同一备份回执。用户修改的同名入口保持字节，未知版本不自动处理。真实setup预览不写入、升级退休、重复无变动、rollback恢复原字节；新增work-loop随受控源码发现入口补缺。

| 变更 | 必须关注的回归 |
|---|---|
| 普通代码修改 | 受影响模块的功能和失败边界；不能用仅匹配实现文本的测试代替行为测试 |
| validate、工具入口、扫描/缓存边界 | 文件和目录均接受；真实缺失和损坏业务 JSON 仍失败；目录中的内容不因是用户扩展就全被跳过 |
| 框架清单、安装、升级、恢复 | 真实 Windows setup.cmd 的预览、升级、重复升级及恢复；全部保护文件和空目录保持 |
| 源码发行边界 | 核对实际 git archive 清单：规则、模板、当前文档和受控测试输入齐全，Project/研究/核心算法/Run 实例按 export-ignore 排除 |
| Python/模型或完整依赖路径 | 在同一共享场景上运行真实离线安装、升级、接收端再次打包及恢复 |
| 前端代码 | 另跑前端相关测试，更新并验证预构建资源；使用端无 Node 的检查保留 |

普通升级集成测试已纳入 `unittest discover`，Windows 下不会因没有模型而跳过；它使用 core 安装流程，避免每次小改动都复制大型模型。完整依赖测试显式运行，不能把 core 测试当成 full 模型验收。

发行 ZIP 与完整开发 checkout 是不同范围。Project 实例中的计划/影响图不进入公共源码；[通用文档维护约定](DOCUMENTATION_MAINTENANCE.md) 和公共 Skill 入口应在包内可用，不能靠发布被排除的实例补齐必需链接。升级清单也不应把新版目录的开发实例复制成旧工作区业务记录。

```powershell
# 日常相关变更：升级/数据保留集成测试
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_deployment_workbench.py -v

# 完整回归
.\automation\python.ps1 -m unittest discover -s automation/tests -v

# 依赖/模型或完整部署链路变更
.\automation\python.ps1 automation/tests/verify_dependency_release.py --bundle dist/dependencies-windows-x64.zip
```

## 从故障补用例

可选Cross-encoder加入依赖链后，`test_dependency_bundle.py`核对旧包兼容、内层模型损坏拒绝、整组件残留清理/恢复、自定义配置保护及PowerShell引导白名单；`verify_dependency_release.py`核对真实离线安装、扩展旧工作区升级、接收端再次打包和恢复后模型/manifest逐文件指纹。模型可选性不能靠跳过存在但损坏的组件实现；core安装通过不代替这一全链验证。

先用最小测试复现，再把相应对象加入共享旧工作区，并确认真实升级流程经过该检查。例如 v0.1.0 的入口只接受文件，原有单文件工具 fixture 无法暴露问题；共享场景现在同时登记包目录和脚本集合目录。只加入“目录存在”的断言不足以防止复发，必须让安装后的 validate 实际读取这份登记。

未知目录并不自动无效，也不自动可信。业务目录的坏 JSON、真实缺失入口仍须报错；已有缓存排除规则单独测试。目录存在不代表工具可以导入、执行或产生正确业务结果。

验收只使用合成材料，记录实际程序版本、场景规模、完整性结果及跳过项。同机中文路径验证不等于另一台物理机和真实业务验证。

现有测试代码说明“可检查什么”；实际是否通过取决于对应版本的执行记录。main 保留程序与合成配方，不保证包含每次历史验收的固定 Run/完整日志。缺少产物时注明不能据当前源码复核该历史结果，不以新文档替代旧证据或把人工待审算作通过。
