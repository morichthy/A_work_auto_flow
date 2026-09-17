# 工作台监测范围与页面状态修复结果

Run：RUN-20260916T154043Z-CFB59D215DFF。执行：2026-09-16至17日（Asia/Shanghai）。归属PRJ-ARCHITECTURE-EVOLUTION；本地修改，未推送发布。源码基线89ad307为已有工作树基线而非本次完成提交；实际修复版本固定在source-fingerprints.json。

## 修复结果

1. 监测限定Owner记录目录、身份卡与记忆HEAD；Run引用的dist依赖ZIP、外部原件、缓存不再进入周期哈希。证据图的间接Run核验也使用有界哈希器，正式证据核验默认行为不变。范围外产物明确未核验，不伪称指纹变化或正式可用。
2. 文件不可读/超限以页面诊断返回，其他有效证据仍可显示；不完整监测快照不覆盖旧基线。工作台启动预载证据，显示读取中与重试入口，切页不重复请求。
3. 顶层功能首次访问后保留组件，记忆子功能保留已读文章、查询、筛选和草稿；隐藏关系页暂停轮询。研究文稿类型只是下次读取参数，新文稿成功后才替换并清除旧章节上下文/影响检查。切换Owner隔离旧请求，清除旧对象复核/关联表。
4. 对象记忆只在点击“生成对象记忆”后读取；点击搜索候选属于用户显式打开操作。系统记忆默认研究经过，前三项为研究经过、对象记忆、关联导航。
5. 检查同类状态问题时修复总结与续接材料包相互覆盖，以及重新准备总结时仍能用旧依据回填的竞态：保留旧正文，但准备中禁用回填；完成后使用新依据。

## 验证与真实边界

| 范围 | 实际结果 | 固定回执 |
|---|---|---|
| 后端证据/监测/HTTP | 40/40通过，mock确认ZIP不被任意间接哈希；正式默认核验仍受原测试保护 | verification/evidence-tests.txt |
| 真实工作区只读观察 | 911文件、38节点、errors为空、dist为空；一次32.61秒 | verification/evidence-collect.txt |
| TypeScript与组件 | 初版51项通过；新增总结竞态后Memory 2项通过，共52个不同组件用例；最终类型检查通过 | verification/frontend-components.log、frontend-summary-race.log、frontend-typecheck-summary-race.log |
| Edge真实浏览器 | 四条工作台、九条记忆、五条材料查询，共18个不同用例有通过证据 | verification/browser.txt、browser-final.txt、browser-summary-recheck.txt |
| Windows升级与保护 | 18个不同用例通过证据齐全；真实setup扩展旧工作区预览、升级、重复升级、恢复和逐项哈希保护通过 | verification/upgrade.txt、upgrade-final.txt、assets-final.txt |
| 生产构建 | 最终构建及源码/资源指纹核对通过；保留Vite大chunk提示 | verification/frontend-build-summary-race.txt、assets-final.txt |
| 工作区 | refresh-index完成，validate为0错误/21既有警告；测试登记audit无未分类/缺失 | verification/refresh-index.txt、validate.txt、catalog-audit.txt |

首次失败均保留：前端脚本入口stdin未转发，因此旧代码检查不计本次通过；浏览器旧用例未显式生成导致等待，按新流程修正但保留原断言；测试文件纳入资源指纹，修改后未立即重建曾导致启动/发行清单拒绝，重建后复验通过；总结新包读取中旧结果仍可点击造成真实STALE_BASIS，修复按钮禁用并加延迟组件测试后原浏览器链路通过。另一次定向unittest模块路径不被便携Python识别，改用discover -k；npm.cmd转发筛选表达式把竖线解释为管道，改为直接调用Playwright。相关失败回执保留，不计作通过。

当前视图保留只覆盖同一浏览标签页，刷新浏览器不恢复；切换Owner清理对应结果，避免错归属。MQ游标TTL和授权核验不改变。正式工作区32.61秒只是单次观察，不承诺瞬时首载或性能收益。未执行万节点规模、本机完整依赖重打包、第二物理机或用户业务验收；依赖和模型未变，本次软件验证不代表科学结论复核。

## 文档、记录与交付

六份现行入口按影响核对：README、ARCHITECTURE、CORE、TESTING更新；docs/README和DOCUMENTATION_MAINTENANCE职责/入口保持，无须改动。WORKBENCH_DEVELOPMENT、EVIDENCE_VIEW_MONITOR、evidence-inspection方法源与D32决策同步；Skill发现文件指向方法源，未新增命令/权限。测试catalog 88→93保存旧版与每次登记原因；新增用例按影响执行，既有基线保留。

本次成果载体为本RESULTS和[工作清单](../../plans/workbench-state-fixes-20260916.md)，无既有本故障专属规范文稿；未改写旧研究报告和冻结Run。已按consolidate-results对本范围计划、结果与相关现行说明全文回读和一致性自查，历史验证缺口保留。代码、日志和登记分别可核对，不表示用户已验收。

生效操作：结束旧工作台服务，再从原工作区运行workbench.cmd，浏览器刷新。关闭标签页本身不会停止旧Python服务。
