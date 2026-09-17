import { useEffect, useState } from "react";
import { api } from "./api";

type Owner = {
  owner_id: string;
  owner_type: string;
  native_data?: { title?: string };
};
type RecordItem = { record_id: string; title: string; kind: string };
const labels: Record<string, string> = {
  project: "项目",
  research: "研究",
  core_algorithm: "核心算法",
  algorithm: "核心算法",
  run: "独立运行",
  "core-algorithm": "核心算法",
  knowledge: "知识",
  report: "报告",
  data: "数据",
  tool: "工具",
};
const kindLabels: Record<string, string> = {
  source: "L0 原始材料",
  detail: "L1 技术单元",
  narrative: "L2 研究经过",
  event: "L2 研究经过",
  experience: "L3 经验",
  overview: "L4 整体概览",
  map: "L4 整体概览",
  document: "研究文稿",
  document_section: "独立章节",
  goal: "目标",
  question: "问题",
  checkpoint: "检查点",
  route: "路线",
  policy: "积累策略",
  review: "结论复核",
  association: "导航关联",
  representation: "检索表示",
  feedback: "使用反馈",
  consolidation: "阶段巩固",
};

/** 导航只读取公开记忆接口；按需展开一个对象，不扫描文件名或装载全库正文。 */
export function MaterialNavigation() {
  const [owners, setOwners] = useState<Owner[]>([]);
  const [expanded, setExpanded] = useState("");
  const [records, setRecords] = useState<Record<string, RecordItem[]>>({});
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    api<{ owners: Owner[] }>("memory/list-owners")
      .then((v) => {
        if (live) setOwners(v.owners);
      })
      .catch((e) => {
        if (live) setError(String(e));
      });
    return () => {
      live = false;
    };
  }, []);
  async function expand(id: string) {
    setExpanded(expanded === id ? "" : id);
    if (records[id]) return;
    try {
      const value = await api<{ records: Record<string, RecordItem> }>(
        "memory/inspect",
        { owner_id: id },
      );
      setRecords((current) => ({
        ...current,
        [id]: Object.values(value.records),
      }));
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <section className="card">
      <h2>材料导航</h2>
      {error && <p role="alert">{error}</p>}
      {!owners.length && !error && (
        <p className="muted">暂无已登记主题对象。</p>
      )}
      {[...new Set(owners.map((o) => o.owner_type))]
        .sort((a, b) => Number(a === "run") - Number(b === "run"))
        .map((type) => (
          <details key={type} open={type !== "run"}>
            <summary>{labels[type] || `其他主题（${type}）`}</summary>
            {owners
              .filter((o) => o.owner_type === type)
              .map((owner) => (
                <article className="proposal" key={owner.owner_id}>
                  <div className="row spread">
                    <a
                      href={`#/memory?owner=${encodeURIComponent(owner.owner_id)}`}
                    >
                      {owner.native_data?.title || owner.owner_id}
                    </a>
                    <small className="id">{owner.owner_id}</small>
                    <button
                      onClick={() => expand(owner.owner_id)}
                      aria-expanded={expanded === owner.owner_id}
                    >
                      查看主题记录
                    </button>
                  </div>
                  {expanded === owner.owner_id &&
                    (records[owner.owner_id] ? (
                      <ul>
                        {records[owner.owner_id].map((record) => (
                          <li key={record.record_id}>
                            <a
                              href={`#/memory?owner=${encodeURIComponent(owner.owner_id)}&record=${encodeURIComponent(record.record_id)}`}
                            >
                              {record.title}
                            </a>{" "}
                            <small>
                              {kindLabels[record.kind] || record.kind}
                            </small>
                          </li>
                        ))}
                        {!records[owner.owner_id].length && (
                          <li>此对象尚无记忆记录。</li>
                        )}
                      </ul>
                    ) : (
                      <p role="status">正在读取主题记录…</p>
                    ))}
                </article>
              ))}
          </details>
        ))}
    </section>
  );
}
