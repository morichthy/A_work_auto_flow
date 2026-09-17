# v0.4.0 发布准备与验收结果

2026-09-17。状态：本地发布准备完成，等待用户确认具体公开仓库；尚未推送或发布。

## 发行内容与边界

发行源码提交 `4c20ea22d2c15c66615395879f9714f4572de295`，分支 `codex/release-v0.4.0`。本地工作提交 `ffbad49` 保留研究实例与验收记录；发行分支从源码父提交c3e7902提取同等框架改动，不把本轮浮点记录/Run加入公开Git历史，不改写本地main或强推。

发行包含独立L0–L4记录要求、逐结论确认状态、六类主筛选、三种阅读模式、最近笔记与详情导航、工作区偏好和可选离线正文重排。六份核心文档与全部8项活跃Skill前后完整阅读，修正automation/README退休入口文案；发现入口、公开动作、安装登记及替代路径一致，见docs-skills-audit.md。该审查后的最终改动仅为浏览器测试及对应构建指纹，六文档/Skill字节未变。

实际git archive有568文件，必要规则、模板、测试与预构建资源齐全；研究实例、来源登记、私人配置和本机产物排除。源码和依赖分别校验，不用整个工作目录压缩。

| 附件 | SHA-256 |
|---|---|
| framework-source-v0.4.0.zip | dd94ad1a829990e0463d2bd38ea026f72c8bf4463a6700feaa441b60f6115c8e |
| dependencies-windows-x64.zip | 90216697586c48921d3f729c983ed74cfae4b1f60d310a0af0e6dc804819fc82 |

ZIP及各自.sha256在dist/release-v0.4.0。源码3405977字节，依赖454246919字节。依赖4092文件、锁和两类模型清单一致；包清单身份59ee7484e6ac824e38b505b85a720bf04e4b605a9d979c3fc1a169cd3c4a3850。

## 验证结果

- 后端实际unittest discovery共745项，逐ID去重744通过、1既有B01失败、0错误/跳过/缺失。主进程694项终态后，沙箱临时目录WinError5阻止下一用例；单次mkdir复现后受控停止，仅用获准权限续跑剩余51项，全部通过。以backend-coverage-ledger.json为最终统计，不沿用过程中的静态估计。
- catalog857项由745 Python、85组件、25浏览器及2个特殊检查组成；audit发现855是跨栈数，不代表855个unittest。万节点规模场景暂缓，常规浏览器24项另计。
- B01完整ID为 `test_memory_fixture.MemoryFixtureTests.test_b01_frozen_plan_self_test_leaves_assets_unchanged`，独立复验test_memory_fixture.py:50仍为1!=0，内部错误为“fixture manifest mismatch: 输入或数量与冻结清单不同”。实际数量一致，仅records.json、acceptance.json、work-packages.json三文件哈希与冻结清单不同；三文件和清单本身均与v0.3.0源码逐字节一致，确为既有失败，不改历史fixture来消除失败。
- 前端85组件、类型检查及最终构建通过。常规浏览器24个用例按首轮和定向复验去重全部有通过记录，最终memory9/9、material-query5/5。首次12过/2失败/10未执行及中间失败保留，原因包括Windows目录改名拒绝、旧测试未展开管理区/辅助入口，以及修改测试后未及时更新构建指纹。修复只涉及测试交互，未改产品代码。
- 实际源码414912候选离线安装109.781秒、旧工作区升级103.688秒、接收端再打包48.828秒、依赖恢复40.546秒均通过，226文件/227目录完整保护；重排模型安装/升级/再打包/恢复逐文件一致。
- 最终4c20ea源码与上述候选逐文件比较，仅memory.spec.ts和asset-manifest的测试source指纹变化；安装器、模型、后端及前端运行资源字节不变。最终实际ZIP又通过全部source/assets哈希和4092文件依赖预览。复用离线全链证据的准确边界见final-source-comparison.json。

AI内容自查沿用此前浮点generation19的完整回读与12页真实页面检查，范围见上一Run及浮点RECORD_UPDATE_20260917；本发布不重新确认浮点结论。单机隔离软件通过不等于第二物理机、业务质量或科学验收；万节点规模暂缓，不保证任意长文重排或模型迁移。

## 权限与下一步

当前凭据对morichthy/A_work_auto_flow有写权限，对livky/A_work_auto_flow无写权限。向morichthy推送被自动审批拒绝，理由是本轮可信用户内容尚未明确授权此具体公开目的地；已向用户询问，未绕过拒绝、未推送、未公开Release。

用户确认后，以固定源码和四个附件创建草稿，核对远端大小和SHA-256后公开v0.4.0，再回读标签提交和下载链接。发布说明见release-notes.md；执行脚本保留在.local/release-20260917，后续字节变化需重新核验。
