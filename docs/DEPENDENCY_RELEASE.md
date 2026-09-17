# 依赖包与 Release

源码和运行依赖分开分发。源码包含 Python 程序、规则、模板和已构建的前端；依赖 ZIP 包含 Windows x64 CPU 环境。依赖未变化时可在多个源码版本间复用，安装器仍逐项核对锁定版本和模型清单。

## 使用者：下载后一个命令

下载同一 Release 的源码 ZIP、`dependencies-windows-x64.zip` 和 `dependencies-windows-x64.zip.sha256`。完整解压源码，把后两份文件放到 `setup.cmd` 旁边。

首次安装：

```powershell
.\setup.cmd --register --open
```

升级旧工作区，在新版源码目录执行：

```powershell
.\setup.cmd --target "D:\研发\旧工作区" --register --open
```

也可保留依赖包在下载目录，显式指定位置：

```powershell
.\setup.cmd --bundle "D:\下载\dependencies-windows-x64.zip" --target "D:\研发\旧工作区"
```

带依赖包时强制离线；不需要系统 Python、Node、pip 安装、Docker 或 Qdrant 服务端。首次会解压本机引导副本、核验真实环境、导入目标，再完成结构检查和索引。引导缓存位于用户临时目录 `rdwork-deps/<包哈希前缀>/`，避免深目录导致 Windows DLL 加载失败；目标暂存和备份位于 `.local/`。不添加环境变量或后台服务。只有显式 `--register` 才使用已有的幂等命令注册机制。安装进程结束后引导缓存可由系统临时文件清理机制回收；重复使用前重新核对所有文件。

## 维护者：直接打包当前环境

预览及正式生成：

```powershell
.\setup.cmd --pack-dependencies
.\setup.cmd --pack-dependencies --apply
```

输出位于 `dist/`，不进入 Git；不覆盖已有包，重复生成需指定新路径：

```powershell
.\setup.cmd --pack-dependencies --output "dist\dependencies-windows-x64-next.zip" --apply
```

打包器只读取已安装环境，不联网重新解析依赖。打包前检查精确锁版本、Python 来源、包 RECORD 和模型文件指纹；运行真实嵌入、OCR 与临时 Qdrant 写入/搜索。Python 来源优先对照原始嵌入 ZIP；接收者未保留下载缓存时，可依据安装时保存的 `services/qdrant/dependency-distribution.json` 再次打包。来源凭据缺失或已登记文件被修改时失败并指出对象，不把混合环境当作可靠发行包。

| 内容 | 处理方式 |
|---|---|
| Python 3.12.10、DLL、标准库 | 对照本机保留的官方嵌入包复制；使用相对 `_pth` |
| 锁定 Python 包和传递依赖 | 按发行 RECORD 复制、校验；保留许可证，重建可迁移 RECORD |
| Qdrant | 包含 qdrant-client local；没有服务端进程或 Docker 镜像 |
| 嵌入模型 | 只复制 model-manifest.json 登记的标准模型文件 |
| OCR 模型 | 随 rapidocr_onnxruntime 发行包复制并核对指纹 |
| 前端第三方框架 | 编译资源及许可证已在源码 ZIP；使用端不需要 node_modules |
| 开发工具链 | 不进入使用端依赖包；前端开发仍用 package-lock.json + npm ci |
| 数据库、业务材料、来源授权、查询/反馈、下载缓存 | 不进入公共依赖包；目标数据库按原来源重建 |

ZIP 内 `dependency-manifest.json` 记录版本、平台和逐文件 SHA-256，`THIRD_PARTY.md` 列出第三方依赖。ZIP 外 `.sha256` 校验完整包；它是完整性记录，不是数字签名，应从信任的发布位置下载两者。

## GitHub Release 分发

Release 可附加二进制文件，每个附件须小于 2 GiB，见 [GitHub 官方说明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。上传独立依赖 ZIP 及 `.sha256`，源码使用该 Release 对应提交通过 `git archive` 生成的 ZIP，作为独立源码附件上传；`.gitattributes` 的 `export-ignore` 排除研究、项目、核心算法和 Run 实例，仅保留规则与模板。不要用整个 checkout 压缩代替发行打包。本地retrieval/sources.json、context/NOW.md、工作清单和工具记忆/运行目录也排除；setup仅在缺失时补空来源登记和初始状态，升级不覆盖已有数据。发布说明应写明兼容 Windows x64、依赖包 ID、检查记录和已知限制。

源码应同时包含当前 v1/v2/v3 兼容契约、记忆服务、技术文稿读取、测试程序和 [通用文档维护约定](DOCUMENTATION_MAINTENANCE.md)。Project 实例内的开发计划与影响图只在完整 checkout 或获批私人副本中保留，公共手册及 Skill 的必需入口不能依赖它们。源码中的受控合成 fixture 是可复用测试输入；运行产生的业务记忆、验收 Run、本机日志和真实来源登记不是依赖附件，也不应随实例排除规则外泄。

先将配套源码提交并推送到准备发布的版本，执行 `git archive --format=zip --output=framework-source.zip HEAD`，解包核对无业务实例且规则、模板、前端资源齐全，再创建 Release 并附加源码 ZIP、依赖 ZIP 和校验文件。打包命令不自动提交、打标签或上传。普通 `portable.cmd pack` 会保留业务历史，不能用于公共依赖发布。

本框架使用的 Qdrant local 不需要服务端，依据见 [Qdrant Python Client](https://github.com/qdrant/qdrant-client/blob/master/README.md)。更换为服务器部署、GPU 或自定义模型属于不同环境契约，不能假设本 ZIP 兼容。

## 升级与恢复

正文重排的可选组件为`services/reranker/model`及`services/reranker/model-manifest.json`。标准模型为`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`的固定revision ONNX，清单列明六个受控文件和SHA-256；复用锁定的onnxruntime/tokenizers/numpy，不另装Python包。源码不包含模型权重或本机配置；`--pack-dependencies --apply`在模型完整且实际离线自检通过时收入依赖ZIP，没有该组件的旧包仍兼容。

新包通过Python及无Python的PowerShell引导白名单、外层包与内层模型指纹双重检查；模型文件和manifest分别备份、切换及恢复，不能用整目录扫描混入缓存。缺CE的旧包不删除已安装CE。无reranker配置时标准manifest自动发现；provider=off继续禁用，自定义provider/路径与标准组件冲突则拒绝覆盖。接收端保留分发清单，可以无下载缓存再次打包。模型评分与向量维度无关，安装CE不重建原384维召回索引；它不放宽任意embedding模型的迁移限制。

升级前关闭目标目录的工作台、索引和实验进程。框架文件备份进入 `.local/upgrades/<批次>/`，依赖组件进入 `.local/dependency-backups/<批次>/`。程序不会覆盖业务材料、检索配置、来源登记或用户规则；旧规则中的自定义内容需由用户按新版说明合并。

保留范围包括对象内 Run、`.run-captures/`、各 owner 的规范记忆和完整历史。v3 技术块、独立章节、research_process/research_report 文稿与旧 v1/v2 记录按各自固定引用读取；源码升级不批量搬迁 Run，也不自动把旧 map 编排改写成新文稿。全文、向量和记忆索引属于可重建投影，补偿方法见 [记忆使用指南](MEMORY_USAGE.md)，具体路径见 [对象保存逻辑](OBJECT_RUN_STORAGE.md)。

依赖暂存复制并核验后，整组件切换，避免旧包残留。切换异常自动恢复；随后模型自检、结构校验或索引失败会返回非零并留下回执，不能视为完整安装成功。若需恢复，关闭目标进程，从独立新版源码目录执行：

```powershell
.\setup.cmd --bundle "D:\下载\dependencies-windows-x64.zip" --rollback-dependencies "D:\研发\旧工作区\.local\dependency-backups\实际批次"
.\setup.cmd --rollback "D:\研发\旧工作区\.local\upgrades\实际批次"
```

依赖恢复核对备份及安装后状态；用户后来修改过依赖文件会拒绝覆盖。恢复后的索引可重建，不恢复或抹除业务编辑。依赖回执不含数据库。首次安装失败仍可修正缺失输入后重试；重复导入相同组件不会重复备份。

标准包仅替换标准模型目录，自定义模型配置冲突时停止，需单独迁移获准的模型文件。当前自动迁移限定已验证的标准模型名称、相对路径和兼容维度，现行自检为 384 维；仅更新源码不会自动替换已存在的旧模型，模型更新版本必须交付匹配模型文件、指纹清单和依赖包。新旧锁不匹配或标准模型清单不一致时，应换用配套 Release；不会静默联网升级或切换检索提供者。

## 验证

轻量回归验证损坏、路径边界、版本不匹配、数据保留和恢复冲突：

```powershell
.\automation\python.ps1 -m unittest discover -s automation/tests -p test_dependency_bundle.py -v
```

真实环境验收需事先生成依赖包，再运行：

```powershell
.\automation\python.ps1 automation/tests/verify_dependency_release.py --bundle dist/dependencies-windows-x64.zip
```

该检查仅在 `.local/release-validation/` 创建中文路径隔离环境，执行无系统 Python/Node 查找的离线安装、升级和恢复，保留本机日志。验证通过不等同于已在第二台物理机、不同硬件或真实公司材料上验收。

验证程序随源码保留，不等于历史运行产物也在公共包中；引用历史检查时须给出实际版本、记录位置及本次可核验范围。更新文档或重新打包不会把“本机隔离检查通过”改成“第二台物理机已验收”，也不重新确认业务结论。

发行核验必须针对实际git archive内的文件字节检查前端source/assets指纹，不能只核对工作树。材料查询契约生成器按UTF-8/LF字节生成和检查，避免Windows换行在Git打包时改变指纹。

Windows组件切换遇到短暂访问/共享占用时进行有上限的重试；非对应错误或重试耗尽仍抛出错误并执行既有恢复，不能把失败当作成功。本机发布实测曾出现复制完成后立即重命名被拒绝、稍后同路径可切换的情况。
