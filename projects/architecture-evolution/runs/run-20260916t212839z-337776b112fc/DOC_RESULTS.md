# 文档处置

已更新 AI_READING、EVIDENCE_VIEW_MONITOR、WORKFLOW_ACTIONS、README、ARCHITECTURE、CORE、docs索引、文档维护、测试选择、开发历史以及相关阅读/工作/证据 Skill。

边界：recent仅24小时展示且不删除历史；snapshot只展示；主Agent仍handoff重验；证据详情metadata-only；编号引用保留固定身份；公式使用`$...$`或`$$...$$`。

上述测试已由执行回执完成，最终数字与限制统一见RESULTS.md；文档核对本身不算软件测试通过。

## 只读一致性核对

核对了 README、ARCHITECTURE、CORE、AI_READING、EVIDENCE_VIEW_MONITOR、WORKFLOW_ACTIONS、DOCUMENTATION_MAINTENANCE、TESTING、DEVELOPMENT_HISTORY，以及8项活跃Skill的方法源和`.agents/skills`发现入口。未见将snapshot_only或metadata_only写为已重新核验、已测试通过的现行表述。`reading-list`仍是CLI/历史发现入口，不与recent展示接口冲突；主Agent仍明确使用handoff。

已修正文档漂移：CORE改为证据先轻量搜索、选中后按需读取详情；ARCHITECTURE已去除重复的recent/snapshot段。未改UI/backend/catalog。
