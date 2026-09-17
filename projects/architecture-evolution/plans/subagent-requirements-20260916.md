# 子Agent能力偏好配置

归属：PRJ-ARCHITECTURE-EVOLUTION；Run：RUN-20260916T081757Z-4C8B6EB90E82。

目标：说明用户配置与发行默认值的边界，在工作台新增可保存的子Agent能力/模型要求，默认选择较低能力、低成本与低推理深度；不增加逐次AI配置解析。

## 实施清单

- [x] 读取work-loop/development-checks、现行设置与委派契约；当前policy为auto，正式工作区未生成设置文件。
- [x] 运行既有设置基线；增加`collaboration.subagent_requirements`及严格校验。
- [x] 旧schema1仅缺新字段时内存补默认，保持原字节与CAS；新保存必须完整。
- [x] 委派任务/精简policy消费配置，off优先，宿主决定实际可用模型；自定义高能力要求不能与硬编码low冲突。
- [x] 工作台输入、保存/重载、恢复默认与冲突草稿；构建及资源指纹。
- [x] 后端相关边界、组件和真实浏览器；Windows真实setup扩展旧工作区预览/升级/重复/恢复保护自定义文本。
- [x] 更新相关文档/Skill、测试catalog；固定结果与源码版本，回读原成果并同步本范围变化。
- [x] refresh-index/validate；说明尚未发布和实际宿主选择边界。

## 决策与范围

沿用schema1的加性读取兼容，不另建模型调用SDK或后台配置服务。新字段为1–2000个字符的非空文本，只提供模型选择偏好，不扩展材料授权/工具权限。Python直接加载和缓存字符串；只在宿主派工时由宿主按可用模型选择。内置默认随源码发行；根目录用户配置受Git忽略及升级保护，不分发私人配置。

本轮不更换召回/重排模型，不改变既有RS预算，不宣称检索速度或总AI费用改善。已有低成本reader真实阅读验收保留为历史证据；本轮重点验证配置从保存到派工任务的传递。

## 文档与成果核对

六份现行入口按影响核对：README/ARCHITECTURE/CORE/TESTING更新；docs/README与DOCUMENTATION_MAINTENANCE检查既有入口和职责。WORKSPACE_SETTINGS/AI_READING/WORKFLOW_ACTIONS及work-loop/material-query方法源同步。规范基线为设置文稿MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152 r1、委派文稿MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r1，保留当时结果，不把新增功能写回旧Run。

进度与验证回执保存在本Run。主Agent整合判断；后端与界面由GPT-6低推理独立实施；基线全文与分发事实由terra低推理只读核对。

## 完成与变化处置

25项后端、10项设置组件、2项真实浏览器及18项Windows不同用例有通过证据；首次失败/复验均保留。最终校验0错误、21既有警告。两份完整报告与概览均沿用ID到r2，主Agent全文回读完成；generation38→41，FTS/向量均indexed。委派稿中3个历史依赖的6条路径提示已逐项确认保留，因为它们支撑旧阶段证据，现行配置已引用新增r2块。全Project其他17个历史单元不在本轮同步范围。

设置文稿MEM-afa98edf-0a9e-57cd-aba6-56d9c3681152 r2；委派文稿MEM-bd121869-a0b9-59e3-af23-8e8675374a63 r2。完整修订/hash、辅助记录请求修正及限制见[收口](../runs/run-20260916t081757z-4c8b6eb90e82/CLOSURE.md)。本范围完整成果已同步（AI一致性自查），未推送发布。
