# Reader自查与来源ID校验：后端验证

本轮仅改`reading_delegation.py`、`reading_owner.py`和`test_reading_owner_document.py`；根代理负责文档、Skill、计划及Run记录。未改旧冻结Run。

## 行为与边界

- Owner worker brief明确要求阅读时提取相关公式/变量/单位/条件/假设/反例与实验—图—Run—来源对应；同一reader在note写作前后核对、补齐或明确材料缺口。引用未展开不得冒充独立阅读或复算。无额外AI调用/审核agent/主侧强制复检，也不把自查清单附加到handoff。
- 新note保存先进行既有授权/版本复核和sources规范化，再检查understanding、logic、details中显式MEM-/RUN-/SRC- ID。未知前缀身份的suffix限ASCII字母数字及连字符/下划线；大小写精确匹配。中文标点、Markdown反引号、@revision支持；不校验正文@revision是否与固定ref一致。
- 其他已交付record/file/representation ID若含`-`或`_`，按实际ID精确匹配；RS/RES/PRJ导航排除。未知非标准ID、地址、自然语言“图1”、公式语义完整性不在程序检查范围。
- question、conditions、limitations、next_steps不作为断言证据扫描；http(s)普通ASCII URL token排除，遇Markdown括号/反引号、中文文字/标点止步，保留链接标签与链接后的来源检查。不是通用IRI/Markdown解析器。
- 正文ID必须来自已交付集合且登记在本note.sources；无需全量引用。仅新note保存触发，不追审旧persisted note/handoff。
- 拒绝不改notes/revision/requests/历史revision文件/笔记快照；既有HEAD.consumed仍记录实际IO用量（资源审计），storage_digest随之更新，不声称拒绝时磁盘完全零写入。

## 先红测再实现

1. `reader-note-id-red.log`：2测试中漏登Run/图片、伪造ID、已知ID前缀伪装四个子用例失败；合法输入基线通过。
2. `reader-note-id-storage-red.log`：公开API旧实现接受伪造Run并写入新revision，1失败。
3. 实现后全Owner回归`reader-note-id-owner-green.log`为23测试、1失败：新增测试要求HEAD字节完全不变，实际既有审计仅更新consumed；调整测试以检查其余语义状态与所有历史文件/快照严格不变，未修改资源审计逻辑。
4. 父代理审查URL贪婪边界后先补负例：`reader-note-id-url-red.log`为1测试中Markdown链接/反引号后的两个子用例失败，再修URL边界。
5. `reader-note-id-owner-final.log`第二次23项仍有1失败：存储断言还漏除了由consumed派生的storage_digest。`reader-note-id-storage-final.log`随后单测因测试暂态误写字段名fingerprint为1错误；修正为真实storage_digest后再跑完整23项。以上均是新增测试断言修正，没有为使测试通过而放宽产品校验或取消资源审计。

## 最终软件验证

命令统一使用`.\automation\python.ps1 -m unittest discover -s automation/tests -p <文件> -v`。

- `test_reading_owner_document.py`：最终结果见`reader-note-id-owner-passed.log`（23项，含新增4项）。
- `test_reading_delegation.py`：10项通过，`reader-note-id-delegation-green.log`。
- 最后URL边界修订后`-k OwnerBudgetTests`：7项通过，`reader-note-id-final-green.log`（包含前述4项中的3项，不重复计数）。

这些软件测试不证明真实reader必然正确提取/自查，也不证明公式科学有效或业务阅读质量。合成AI验收由根代理独立记录。无前端、依赖或安装边界变更，不新增全库/升级回归。
