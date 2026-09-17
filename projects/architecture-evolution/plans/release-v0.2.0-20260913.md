# v0.2.0 清理与发布工作清单

Owner：PRJ-ARCHITECTURE-EVOLUTION；2026-09-13，进行中。
目标：删除无用Skill和空目录，提交当前框架、推送并发布不含本地经验记录的Release。
归属：继续框架统一工作流与发行维护。用户已授权删除、提交、推送、发布。

依据：当前work-loop、development-checks、DEPENDENCY_RELEASE、UPGRADE_TESTING及既有开发上下文。已有明确文件定位，暂不新建RS或扩大召回。

已做：备份两个退休Skill到.local/release-20260913/retired-skills.zip，删除research-loop/workspace-context方法目录及analysis-diagnosis/core-algorithm-design/report-production空目录；保留7项活跃Skill。安装器拒绝旧名新装，旧受控入口仍按指纹退休、保留用户改写。
发行边界：git archive排除实例、来源登记与本地NOW；setup仅在缺失时创建空sources及初始NOW，不覆盖旧工作数据。实际包还需逐项盘点。
验证进行中：后端全量、真实setup升级、前端测试；本次新增安装器7项已通过。初次前端测试被Vite临时目录权限阻止，已提升权限重试。新增测试初次因Windows换行恢复字节不一致失败，改为原字节恢复后通过。
依赖：锁与模型未变化，下载v0.1.1独立依赖包并核验后复用，首次下载中断，正在续传。不要使用dist中的portable完整工作区包。

下一步：收口验证、审查源码包/依赖包内容与哈希、创建提交并推送、创建draft Release上传附件核验后发布。失败和既有B01单列，不冒称全绿。


## 当前进展（2026-09-13）

框架提交62ba75b和发行指纹修复866cd04已推送origin/main；本地业务数据未加入这两次提交。最终源码513文件，排除实例/记录/来源/NOW/根历史任务计划，保留规则、模板与合成测试。前端资源本体未变，重新构建修正material-query.ts的LF源码指纹；生成器也改为字节比较/写入，21项契约回归通过。

已验证：安装器7项、真实setup扩展旧工作区18项、前端38项、类型检查/构建、16个不同普通浏览器用例（11首次通过+5定向复验）通过；第一次浏览器复核用例超时，定向复验通过。第一次过滤未正确排除“一万节点”，后在该项未产出结果前中断；不计规模通过。源码内前端指纹逐文件匹配，源码core首次安装0错误，43条主要指向未分发历史实例的说明链接警告。Git diff按CRLF语义检查无实际空白错误。

依赖包复用v0.1.1，SHA256：7810752e15ff40b88e04bae0eedae57f20355ca2da51febba7505a787361d3a4；包ID d53325b59c213a1a229afd0caa42ee4c3c300779592fc0e09b5f31170e4987e4。逐文件与当前锁/模型清单匹配，实际384维编码、临时Qdrant写查、OCR执行通过。最终源码配套离线安装进行中。Git直接网络失败，改用系统已有代理后推送成功；凭据未写入文件。

Skill逐项处置：work-loop、material-query、context-maintenance、development-checks、association-exploration、evidence-inspection、semantic-maintenance均仍适用，方法/公开入口/发现核对保留；两个旧名删除，三个旧空目录清理，用户自定义不动。六份现行文档核对：README/docs索引改退休说明；ARCHITECTURE/CORE维持前轮实现定义；文档维护/TESTING规则无需改；发布手册、升级说明及D26更新。生成器字节修复是本次发行实测发现，不改固定历史材料。

下一步：等待全量后端与最终离线安装、草稿附件上传收口；验证Release远端SHA后公开。固定验证Run：RUN-20260912T225116Z-CEA0BB98886E。

发行追加修复：即时目录切换WinError5在提升权限及全新目录中仍复现，延时同路径移入/移回成功；依赖切换/恢复增加有限重试，10项依赖回归通过，真实完整离线首次安装114.937秒通过，扩展旧工作区升级/再打包/恢复仍在执行。并行后端启动首轮因嵌入Python忽略PYTHONPATH导致导入失败，保留日志；显式sys.path后重试。全量原通过263项、剩余337项逐ID分组执行，新依赖故障用例另测；不把启动失败计作产品用例通过。


## 本轮收口：等待具体目的地授权

最终本地提交28f05ad，前两次62ba75b/866cd04已推送；最后一次推送被自动审批两次拒绝，理由为缺少对具体GitHub目的地的用户确认。最终Release尚未公开，草稿387728000仍含866cd04源码，不能直接发布。用户确认https://github.com/livky/A_work_auto_flow后：推送28f05ad，更新草稿target_commitish及两个源码附件，核验SHA后公开v0.2.0。

601个不同后端用例已覆盖，修正旧Skill预期并复验后600通过、仅既有B01失败；没有跳过。完整离线四步通过：安装114.937s、升级134.0s、接收端再打包48.297s、恢复47.781s，219文件/221目录保护核对通过。7项Skill格式与安装预览、catalog audit通过。正式本地源码513文件及前端指纹通过，SHA256 b8e3767d146d196ce5ee68aa13d003c4a278db4da4ba7255dcbb2074d5252617。

固定结果与日志：[RESULTS](../runs/run-20260912t225116z-cea0bb98886e/RESULTS.md)，已通过run-register登记源码和验证归档。Run状态failed明确包含B01失败和发布未完成，不冒称已发布。后续只追加新回执，不能覆盖本次固定结果。


## 发布完成（2026-09-13）

用户已确认具体GitHub目的地；最终提交28f05ad已推送，v0.2.0已公开发布：https://github.com/livky/A_work_auto_flow/releases/tag/v0.2.0 。标签解析到最终提交，四个附件的大小与SHA256均已核验；发行包不含本地经验、工作记录、数据库或来源登记。既有B01测试失败和第二物理机待验收仍保留。

固定发布回执：RUN-20260912T225116Z-CEA0BB98886E / PUBLICATION.json。此前RESULTS及验证归档保留当时时点，不覆盖历史失败。
