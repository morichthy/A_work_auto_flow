# 文稿回读与结构校验完成

2026-09-16，Codex AI一致性自查。范围仅为本次正文、条件、Cross-encoder重排实施；新增设置页需求已记入现行计划，尚未实施。

**本阶段完整成果已同步（范围：2026-09-16召回排序演进；文稿：MEM-5c827f1d-99ff-5a60-a150-ac28ad89c877 r1；AI一致性自查）。**

- 技术正文：MEM-a3c10076-e900-5ff5-adfb-f3949a3fa285 r1，SHA256 `99b75b70d7efbc31f3ff4dc17c38ea8f34529e875873e017886589d7ddb872e0`。
- 固定章节：MEM-2c32da6d-6ddc-5fbd-9947-92dde975b240 r1，SHA256 `8ea83d522ab2422ae9217eb6826b2d877692e833e515097aa021d9689770176c`。
- 完整文稿：MEM-5c827f1d-99ff-5a60-a150-ac28ad89c877 r1，SHA256 `35490052295d59e2c0ed99997d97b341a26822a4cf95059731195981b8268d97`。
- 当前概览：MEM-3227e150-36dd-5d01-825d-38c7362989b2 r1，SHA256 `993d53cbbddeb4279b7cd9efd7eb47873d738d7afaef91e008c24cb694fc60ea`。
- Project起止HEAD：COM-d48e7ebe-bbb7-48f9-9494-ed27c7c93cef → COM-05193f16-a923-43c1-9897-859c60658115，generation 30。

章节角色原请求使用了契约不支持的results，预检拒绝且没有写入；改用methods后通过。原失败请求及验证结果保留。中断发生在文稿HEAD已发布、回执未归档时；用同一个request_id重放取得回执，没有重复创建规范内容。保存脚本v1/v2及v3恢复脚本分别保留，不改已登记脚本指纹。

已通过公开document/outline/document-impact回读，并完整阅读组装正文和概览。document_source=independent，complete=true，missing=[]，version_hints=[]，impact changes=[]；本轮技术单元已覆盖。coverage中其他16条旧技术内容属于既有表示查询设计、实施、来源修复或项目比较，不属于本次重排报告范围，保留旧稿固定编排，不将其遗漏解释为已同步整个Project历史。

新文稿内容与RESULTS、现行计划、Project概览及NOW中的结果和限制一致。全文明确保留小样本、自然语言条件unknown、512 token窗口、冷启动加载成本、业务与第二物理机待验收，未晋升科学复核状态。FTS与vector均已索引至generation 30，最新保存回执无错误。

`refresh-index`成功。`validate`通过：0个错误、21个警告。20项为既有历史快照/已删除材料的链接警告；1项是新增本地CE权重超过25 MiB的提示，权重在运行依赖目录、已被Git忽略，离线包按显式组件与哈希校验。没有为了消除警告改写历史材料或放宽校验。

已完成的测试包括阅读40项、材料查询200项、重排单元11项（与阅读有重叠）、基线4项、依赖13项、真实setup扩展旧工作区18项，以及真实模型/CLI阅读和离线安装、升级、再打包、恢复。详细结果及限制见[RESULTS](RESULTS.md)。

本补充回执及保存回读文件独立留档。Run元数据已作为技术正文的固定来源，不在保存完成后反向改动其指纹；新增文件指纹见closure-manifest.json。
