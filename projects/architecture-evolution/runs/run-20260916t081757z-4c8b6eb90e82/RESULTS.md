# 子Agent能力要求：实现与验证

Run：RUN-20260916T081757Z-4C8B6EB90E82。2026-09-16，本机Windows x64；本轮尚未推送或发布。

## 实际行为

工作台“工作区设置→协作策略”增加“子 agent 能力要求”文本框。字段为`settings.collaboration.subagent_requirements`，默认“优先使用低成本、较低能力的可用模型，采用低推理深度；须能完成材料检索、完整阅读和结构化笔记。”可填写具体模型、推理深度或能力偏好；去首尾空白后校验1–2000个Unicode字符，保存原文。关闭协作时仍可预配文本，保存不会打开协作。

程序缓存配置，policy/capabilities返回偏好，reading-delegate同时放入model_preference.requirements与worker_brief.model_requirements。宿主负责选择实际可用模型并调用派工工具；API仍返回dispatched=false，不谎称已经派工。移除固定cost/reasoning=low，避免与用户填写高能力要求矛盾。off或宿主不支持继续同RS单Agent；文本不扩大材料、工具权限或预算。

旧schema1磁盘文件仅缺新字段时内存补默认，文件字节及内容hash revision不变；新set请求必须提供完整字段，防止旧客户端漏字段清空偏好。已有RS范围与预算继续固定。未引入后台服务、模型SDK、依赖或额外AI配置解析调用。

## 文件与发布边界

用户配置在工作区根`workspace-settings.json`；首次保存前可能不存在，正式工作区本轮仍未创建或改动该文件。内置默认位于`automation/scripts/workspace_settings.py`，它属于受控源码并随版本分发。根.gitignore忽略本地配置，git ls-files无该路径；分发收集器不包含它，升级保留接收端设置。本Run最终源码快照和manifest再次用真实framework_files收集器核验。

## 实际验证

| 范围 | 结果与证据 |
| --- | --- |
| 修改前基线 | 13项设置、9项委派、9项设置组件通过；backend-baseline-*.log、component-baseline.log |
| 后端相关 | 15项设置/集成与10项委派通过；覆盖旧文件只读补缺、严格写入、文本边界/原文、CLI/HTTP/policy、能力传递、off、预算及权限旧防线 |
| 前端组件 | 10项通过；保存、恢复默认、非空/Unicode限制、关闭预配、busy、导航/冲突保留草稿 |
| 真实Edge浏览器 | 2项通过，实际HTTP保存与重载、409草稿；新增文本框截图已AI检查，无溢出 |
| 构建 | contracts、TypeScript、Vite构建通过；保留既有大chunk警告，最终source_fingerprint为9f219223002fb16528ee025c7b6e9dce9a60a67e936daf8566ee8e097c0abdec |
| Windows升级 | 18项不同用例获得通过证据：首次17通过/1失败，唯一失败在前端重建时命中源码/构建指纹不一致，最终冻结后单项复验通过。真实setup扩展旧工作区预览、升级、重复升级、恢复及自定义能力要求字节保护通过 |
| 测试目录 | revision88；新登记后端3项和组件1项；旧文件无损兼容/严格写入两项加入基线，其余按影响执行。audit通过，743发现/745清单，无未分类/缺失/错误 |
| 工作区校验 | 记录更新前refresh-index/validate通过，0错误、21既有警告；收口后回执单独补存 |

首次浏览器2项因控件可访问名称定位失败，给控件添加明确aria-label后2项通过；原始失败与browser-final复验均保留。首次只读memory inspect因重定向先创建空JSON被扫描而返回INTEGRITY_ERROR；改为先取得内存结果再写文件后成功，失败回执和retry并存。没有通过改测试断言或跳过用例掩盖失败。

## 文档与已有成果处理

README、ARCHITECTURE、CORE、docs/README、TESTING已同步；DOCUMENTATION_MAINTENANCE按范围核对，职责未变，无需修改。WORKSPACE_SETTINGS、AI_READING、WORKFLOW_ACTIONS、DEVELOPMENT_HISTORY及work-loop/material-query方法源同步；两项轻量发现入口继续引用原方法路径，无需修改。其他Skill不消费新字段，未更换入口或权限契约。新增配置含义只在现行说明维护，旧Run与旧MEM固定修订不改。

独立terra/low reader完整读取设置和委派报告/概览及影响列表，主侧取得baseline/READING_NOTE.md与固定回执。基线HEAD为generation38；两份document-impact无变化，组装完整；每份全Project覆盖仍各缺18个L1，包含另一份报告单元及17个其他历史单元，不能宣称全Project同步。本次演进沿用设置单元/章节/文稿/概览ID，并更新受影响委派章节/文稿/概览；原历史块和固定Run保持，追加本次能力配置及验证结果。最终版本与全文检查记在CLOSURE.md。

## 适用边界

宿主须实际支持子Agent并遵守策略；填写模型名称不保证宿主提供该模型，也不会自行安装。没有重新验证任意宿主或真实业务的模型质量。前阶段设置微测p95约0.7553ms及独立reader约90.7%材料响应字符减少保留为当时证据，本轮不把它们当新版本实测，更不等同于总费用/端到端速度改善。未更换依赖/模型，未重做离线依赖打包；本机合成升级通过不等于第二物理机或人工业务认可。
