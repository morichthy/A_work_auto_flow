# 工作区设置

子Agent开关由reading-delegate直接消费：auto且宿主提供工具时委派独立低成本reader，off/无能力时单Agent。主Agent通过reading-handoff只收研究式笔记。新Owner模式主要控制阅读Owner数与最终note估算token，内部搜索/诊断不占note额度；`settings.reading.strategy` 固定为 standard、associative 或 quick，association 另保存 enabled/max_rounds。旧RS仍按原累计预算和字符交接上限工作。宿主派工和外部AI token见[AI阅读](AI_READING.md)。

在工作台侧栏打开“工作区设置”，修改后点击“保存设置”。“恢复默认值到草稿”不立即落盘；并发修改时保留草稿，读取最新配置并核对后再保存。设置属于当前工作区，重新启动仍保留，升级旧工作区不会覆盖。没有设置文件时使用程序内默认值，不要求手动创建文件。

## 可调整项

| 范围 | 选项与含义 |
|---|---|
| 协作 | `auto`：任务合适且宿主支持时可用子Agent；`off`：遵循工作区工作流的AI由主Agent独立完成 |
| 子Agent能力要求 | 自由文本指定能力、模型或推理深度偏好；默认低成本、较低能力、低推理深度，由宿主选择可用模型 |
| 材料查询 | 新打开查询页面的默认结果数、累计读取量、输出字符、活动执行时间、候选与模型/图预算 |
| AI阅读主要控制 | `reading.context.max_owners`：最多选中阅读Owner数，默认10、范围1–100；`note_max_tokens`：最终note保守估算token，默认6000、范围512–50000 |
| 默认阅读模式 | `reading.strategy`：standard（完整阅读相关Owner）、associative（受限联想召回后完整阅读）、quick（仅评判实际召回片段）；`reading.association.enabled/max_rounds` 控制联想，轮次范围1–20 |
| AI阅读检索 | 新模板的每路结果数、重排模式与候选池；候选数不等于最终Owner数 |
| AI阅读高级资源保护 | `reading.budget`：新Owner模式单次操作的读取量、输出字符、活动时间、模型/图等工程保护；旧RS维持原累计含义 |

出厂材料查询结果数20；AI阅读每路结果数10、重排auto、候选池30。工程资源默认值由程序统一提供，工作台显示当前值和上限，`workspace-settings show`返回完整结构；Skill不复制另一组预算。Owner阅读note以UTF-8字节数作保守token估算代理，不是宿主精确token；中文和大量引用时偏保守，可按任务调整，但不能改变宿主窗口。handoff整份note保留或省略，超限公开报告，不截断公式。

候选池越大，可能有更多相关候选进入重排，也增加回源和推理量。读取/输出预算太小会显式停止或缺项；模型预算不足时auto报告降级，required停止。上限控制最大消耗，不保证请求一定花完预算，也不是质量保证。各预算是整数；工作台MiB/秒可使用能精确换算为整数字节/毫秒的小数。活动时间必须大于零，其余预算允许零。

## 生效范围与兼容

程序加载经过校验的配置，进程内缓存，不在每次检索时让AI读取JSON。常驻工作台的缓存命中只核验路径/文件stat并复制小对象；外部修改或保存后下一次读取失效。独立CLI进程每次启动仍需首次读取文件，没有后台服务；这不能消除模型冷启动、索引或回源成本。

新查询页面与新阅读模板采用当前设置。显式请求字段优先，已经打开的查询草稿不会被后台改写，切回新查询页面才载入新默认；已有Q/RS保持原范围及该模式固定的参数。会话页用带CAS的 reading-configure 保存策略与可选联想搜索文本，并回读HEAD；保存不启动搜索、后台AI或reader。quick 的笔记明确只覆盖实际交付片段，不能替代完整Owner阅读。`materials/capabilities`返回`default_result_limit/default_budget/workspace_policy/settings_revision`供调用者消费；直接构造的完整请求不会被服务端静默替换。旧search/CTX兼容入口继续使用各自参数。

子Agent是AI宿主能力，检索后端本身不依赖它。work-loop在任务开始或用户修改设置后读取精简策略，off禁止工作区工作流委派，auto没有能力时按单Agent执行。本开关不能从项目程序层面禁用不遵循工作区规则的外部宿主工具；用户当前明确要求仍优先。

“子Agent能力要求”对应`settings.collaboration.subagent_requirements`，支持1–2000字符的非空文本。例如可写“优先gpt-5.6-terra，low推理；不可用时选择相近的低成本模型”，也可指定更强能力。程序直接缓存并传递原文，不增加AI解析配置的调用。`workspace-settings policy`返回该偏好，`reading-delegate`通过`model_preference.requirements`和`worker_brief.model_requirements`交给宿主；不会用固定low覆盖自定义要求。模型不可用时由宿主说明替代选择；该文本不能启用被关闭的协作，也不授予额外工具或材料权限。

旧schema1文件缺少subagent_requirements或reading.context时，只在读取结果中补默认，磁盘原文和revision保持不变。下次从show或页面保存完整设置时写入新字段；缺字段的旧写入请求会被拒绝，避免默默清除已经设置的偏好。

## 程序接口

```powershell
.\workbench.cmd workspace-settings show
.\workbench.cmd workspace-settings policy
.\workbench.cmd workspace-settings set --request "设置请求.json"
```

show返回`{revision,settings,defaults,limits}`；set请求为`{expected_revision,settings}`，settings必须是show返回结构的完整副本，只修改所需值，不复制defaults/limits为请求字段。版本过期返回VERSION_CONFLICT及非零退出码，锁占用返回LOCKED；未知字段、损坏JSON、非法数值明确拒绝。不要删除其他进程持有的锁来强行保存。HTTP为GET/POST `api/v1/settings`，沿用工作台本机token地址及Origin/Host保护。

配置只保存在根目录`workspace-settings.json`，是用户状态，不随公共源码包复制。正常修改使用工作台或CLI；原子保存采用同目录临时文件与版本比较。它不保存凭据、源文件路径或内容，不替代材料访问授权。架构与缓存边界见[ARCHITECTURE](../ARCHITECTURE.md)，开发验证见[TESTING](TESTING.md)。

首次保存前可能没有这个文件：出厂值定义在`automation/scripts/workspace_settings.py`的`_defaults()`中，随源码推送和发布。保存后的`workspace-settings.json`被根`.gitignore`忽略，发行收集器也不打包它；升级保留接收工作区的自定义值。因此接收端会获得程序默认值及设置页面，而不会收到开发者的私人设置。
