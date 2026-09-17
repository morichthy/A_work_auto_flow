# 工作台监测与页面状态修复

归属：PRJ-ARCHITECTURE-EVOLUTION。验证 Run：RUN-20260916T154043Z-CFB59D215DFF。

## 目标与验收

1. 持续监测限定各 Owner 记录，发布 ZIP 不进入监测哈希；局部文件异常不得阻断整个证据页面。
2. 打开工作台时自动预载证据与影响，功能切换保留现有视图；工作台服务未运行时不新增后台服务。
3. 当前浏览会话内保留研究经过及其他功能的结果、选择和草稿；切换对象必须隔离旧请求，主动读取才更新生成结果。
4. 对象记忆由用户主动生成，不在打开系统记忆时自动检索全部类型。
5. 系统记忆前三项依次为研究经过、对象记忆、关联导航。

## 执行与依据

- 已读 START_HERE、NOW、work-loop、development-checks、ARCHITECTURE、TESTING、WORKBENCH_DEVELOPMENT、UPGRADE_TESTING 及相关开发历史。
- workspace-settings policy 为 auto。后端和前端由 GPT-6 低推理独立实施；只读验证准备由 terra 低推理处理；主 Agent 负责范围判断、整合与最终验证。
- 保留当前工作树的已有未提交改动，不重置、覆盖历史或发布版本。
- 根因初查：evidence_observer 收集 Run inputs/artifacts 的任意文件；顶层与记忆子页条件渲染导致卸载。

## 检查清单

- [x] 后端范围、超限失败与完整监测基线行为测试：evidence*.py 40/40，通过日志见 Run verification/evidence-tests.txt。
- [x] 前端组件测试、类型检查与普通浏览器用户链路：52个不同组件、18个不同浏览器用例有通过证据，失败/复验分别保留。
- [x] 生产构建与资源指纹同步，最终资源一致性通过。
- [x] 真实 Windows setup 扩展旧工作区的预览、升级、重复升级、恢复；18项不同升级用例有通过证据。
- [x] 相关文档/Skill与测试登记检查，catalog到93，固定验证记录与源码指纹。
- [x] refresh-index、validate完成（0错误/21既有警告），本范围结果回读。

本次完整成果载体为本计划与 Run RESULTS；限定本轮故障修复，不改写历史研究文稿或把软件通过解释为业务结论复核。

## 阶段发现

监测清单外还有证据图的 Run 产物校验链，故仅过滤文件集合不足。最终通过可选有界哈希器约束观察路径，正式证据核验仍保留默认完整行为。实际工作区只读 collect 为911文件/38节点，errors为空且无dist文件，一次耗时32.61秒；这不是性能基准，也不宣称页面瞬时加载。

前端首次脚本尝试未落盘（PowerShell包装入口不转发stdin），此前类型检查属于旧代码，不能作为本次通过证据；改用脚本文件并核对实际源码后重新验证。没有覆盖既有工作树修改。

浏览器首次8项通过、1项旧用例未适配手动生成、4项串行后续未执行；保留browser.txt。修正测试后因测试文件也进入资源清单而触发源码/资源不匹配，保留browser-recheck.txt并重建。第三轮11项通过，但总结刷新保留旧材料包时仍允许回填，触发真实STALE_BASIS；需要在准备中禁用依赖结果操作，不能只让测试等待掩盖竞态。升级18项中17项首过，发行清单检查因同次测试文件修改失败，最终重建后单项复验通过；真实setup完整场景已通过。

六份现行文档按影响处置：README、ARCHITECTURE、CORE、TESTING同步本轮行为；docs/README与DOCUMENTATION_MAINTENANCE已核对，入口/职责未变无需改动。WORKBENCH_DEVELOPMENT、EVIDENCE_VIEW_MONITOR及evidence-inspection方法源更新；work-loop/development-checks只涉及开发流程，material-query/semantic-maintenance接口不变。

最终总结竞态已经修复并通过原浏览器场景；三条未完成链路全部通过。完整结果、失败原因及限制见[RESULTS](../runs/run-20260916t154043z-cfb59d215dff/RESULTS.md)。本轮未发布；重启服务并刷新浏览器后使用。记录检查为AI自查，用户实际使用验收待进行。
