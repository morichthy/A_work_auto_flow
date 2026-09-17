import { usePanelActive } from "./RetainedPanel";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, download, kindNames, relationNames } from "./api";
import type { MaterialGraph } from "./generated/contracts";
import { GraphPanel, Modal } from "./components";
import {
  selectGraph,
  summary,
  topicGroups,
  layerGraph,
  type Mode,
} from "./graph-model";
import type { ClusterResult } from "./cluster";

type SavedView = {
  positions?: Record<string, { x: number; y: number }>;
  groups?: { name: string; members: string[] }[];
  center?: string;
  excluded?: string[];
  mode?: Mode;
};
type Proposal = {
  id: string;
  kind: string;
  title: string;
  explanation: string;
  refs: { id: string; fingerprint: string; locator: string }[];
  actor: string;
  status: string;
  stale: boolean;
  history: unknown[];
};
export function Relations({
  revision,
  error,
  launch,
}: {
  revision: number;
  error: (s: string) => void;
  launch: (
    kind: string,
    seeds?: string[],
    excluded?: string[],
  ) => Promise<void>;
}) {
  const active = usePanelActive();
  const [catalog, setCatalog] = useState<MaterialGraph | null>(null);
  const [center, setCenter] = useState("");
  const [mode, setMode] = useState<Mode>("radial");
  const [hops, setHops] = useState(1);
  const [search, setSearch] = useState("");
  const [materialKinds, setMaterialKinds] = useState<string[]>([]);
  const [levels, setLevels] = useState<string[]>(["L1"]);
  const [query, setQuery] = useState("");
  const [excluded, setExcluded] = useState<string[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [edgeSelected, setEdgeSelected] = useState(false);
  const [seeds, setSeeds] = useState<string[]>([]);
  const [candidates, setCandidates] = useState(false);
  const [extra, setExtra] = useState<MaterialGraph["edges"]>([]);
  const [offset, setOffset] = useState(0);
  const [history, setHistory] = useState<string[]>([]);
  const [positions, setPositions] = useState<SavedView["positions"]>({});
  const [groups, setGroups] = useState<NonNullable<SavedView["groups"]>>([]);
  const [groupName, setGroupName] = useState("");
  const [preview, setPreview] = useState<{
    path: string;
    text: string;
    truncated: boolean;
  } | null>(null);
  const [clusters, setClusters] = useState<ClusterResult | null>(null);
  const [busy, setBusy] = useState(false);
  const worker = useRef<Worker | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [draft, setDraft] = useState("");
  const [importing, setImporting] = useState(false);
  const [proposalTitle, setProposalTitle] = useState("");
  const [proposalNote, setProposalNote] = useState("");
  const [showExport, setShowExport] = useState("");
  const [layoutVersion, setLayoutVersion] = useState(0);
  const reloadProposals = () =>
    api<{ candidates: Proposal[] }>("candidates").then((x) =>
      setProposals(x.candidates),
    );
  useEffect(() => {
    api<SavedView>("view")
      .then((v) => {
        setPositions(v.positions || {});
        setGroups(v.groups || []);
        setCenter(v.center || "");
        setExcluded(v.excluded || []);
        setMode(v.mode || "radial");
      })
      .catch((e) => error(e.message));
    return () => worker.current?.terminate();
  }, []);
  useEffect(() => {
    api<MaterialGraph>("catalog")
      .then(async (g) => {
        setCatalog(g);
        api<ClusterResult>("clusters")
          .then((saved) => {
            if (saved.fingerprint === g.fingerprint) setClusters(saved);
          })
          .catch((e) => error(e.message));
        const values =
          await api<
            Record<
              string,
              { fingerprint: string; edges: MaterialGraph["edges"] }
            >
          >("analysis");
        setExtra(
          Object.values(values)
            .filter((v) => v.fingerprint === g.fingerprint)
            .flatMap((v) => v.edges),
        );
        if (Object.values(values).some((v) => v.fingerprint !== g.fingerprint))
          error("部分候选缓存已过期，请按需重新分析。");
      })
      .catch((e) => {
        setCatalog(null);
        error(e.message);
      });
    reloadProposals().catch((e) => error(e.message));
  }, [revision]);
  useEffect(() => {
    // 隐藏时停止轮询，返回恢复新鲜度核对。
    if (!active) return;
    const check = () =>
      api<{ changed_files: string[] }>("freshness")
        .then((result) => {
          if (result.changed_files.length)
            error("发现材料变化，当前视图及候选可能过期；请刷新材料视图。");
        })
        .catch((e) => error(e.message));
    check();
    const timer = setInterval(check, 30000);
    return () => clearInterval(timer);
  }, [active]);
  const base = useMemo(
    () =>
      catalog
        ? layerGraph(
            {
              ...catalog,
              edges: [...catalog.edges, ...(candidates ? extra : [])],
            },
            levels,
          )
        : null,
    [catalog, candidates, extra, levels],
  );
  const graph = useMemo(
    () =>
      base
        ? selectGraph(base, center, hops, excluded, mode, types, offset, seeds)
        : null,
    [base, center, hops, excluded, mode, types, offset, seeds],
  );
  const topics = useMemo(() => (base ? topicGroups(base) : []), [base]);
  const visualGroups = useMemo(
    () => [
      ...groups.map((g, i) => ({ ...g, id: `custom:${i}` })),
      ...topics,
      ...(clusters && catalog && clusters.fingerprint === catalog.fingerprint
        ? clusters!.clusters.map((c) => ({
            id: c.id,
            name: c.title,
            members: c.members,
          }))
        : []),
    ],
    [groups, topics, clusters, catalog],
  );
  const node = catalog?.nodes.find((n) => n.id === selected);
  const edge = base?.edges.find((e) => e.id === selected);
  const matches = useMemo(
    () =>
      (base?.nodes || [])
        .filter(
          (n) =>
            !excluded.includes(n.id) &&
            (!materialKinds.length || materialKinds.includes(n.kind)) &&
            (!search ||
              (n.title + n.id).toLowerCase().includes(search.toLowerCase())),
        )
        .slice(0, 60),
    [base, search, excluded, materialKinds],
  );
  function focus(id: string) {
    setSeeds([]);
    setHistory((h) => [...h, center]);
    setCenter(id);
    setSelected(id);
    setEdgeSelected(false);
    setOffset(0);
  }
  function choose(id: string) {
    // Return to the first page so a small checked subgraph is never hidden by
    // the previous all-materials page offset. List filters preserve selection.
    setOffset(0);
    setCenter("");
    setSeeds((old) =>
      old.includes(id)
        ? old.filter((x) => x !== id)
        : old.length < 50
          ? [...old, id]
          : old,
    );
  }
  async function saveView() {
    await api("view", { positions, groups, center, excluded, mode });
    error("视图已保存，仅记录展示偏好。");
  }
  function runCluster(semantic: boolean, global = false) {
    if (!graph) return;
    worker.current?.terminate();
    setBusy(true);
    // 使用当前可见选择，与导出/排除完全一致；大范围通过全局聚合逐批选择。
    const w = new Worker(new URL("./cluster.worker.ts", import.meta.url), {
      type: "module",
    });
    worker.current = w;
    w.onmessage = (event) => {
      setBusy(false);
      if (event.data.error) error(event.data.error);
      else {
        setClusters(event.data.result);
        api("clusters", event.data.result).catch((e) => error(e.message));
      }
      w.terminate();
    };
    w.onerror = (event) => {
      setBusy(false);
      error(event.message);
      w.terminate();
    };
    const blocked = new Set(excluded);
    const input =
      global && base
        ? {
            ...base,
            nodes: base.nodes.filter((n) => !blocked.has(n.id)),
            edges: base.edges.filter(
              (e) => !blocked.has(e.source) && !blocked.has(e.target),
            ),
            selection: { excluded, scope: "all-authorized-materials" },
          }
        : graph;
    w.postMessage({ graph: input, semantic });
  }
  async function saveProposal(
    title = proposalTitle,
    explanation = proposalNote,
    ids = seeds,
    kind = "relation",
  ) {
    if (!catalog) return;
    const refs = ids
      .map((id) => catalog.nodes.find((n) => n.id === id))
      .filter((n) => n !== undefined)
      .map((n) => ({
        id: n.id,
        fingerprint: n.fingerprint,
        locator: n.locator || n.path || "元数据",
      }));
    await api("candidate", { kind, title, explanation, refs, actor: "user" });
    await reloadProposals();
    setProposalTitle("");
    setProposalNote("");
  }
  async function copy() {
    if (!graph) return;
    const text = summary(graph, query);
    try {
      await navigator.clipboard.writeText(text);
      error("关联摘要已复制。");
    } catch {
      setShowExport(text);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">材料关系 / 可重建视图</p>
          <h1>从问题出发，看见联系</h1>
        </div>
        <div className="row">
          <button onClick={() => launch("freshness")}>检查版本</button>
          <button className="primary" onClick={() => launch("refresh")}>
            构建 / 刷新材料视图
          </button>
        </div>
      </div>
      {!catalog || !graph ? (
        <section className="empty card">
          <h2>建立第一份材料视图</h2>
          <p>
            从已登记材料读取关系，原文和复核记录保持原样。构建期间可以继续浏览其他页面。
          </p>
        </section>
      ) : (
        <>
          <div className="row toolbar">
            <input
              aria-label="当前问题"
              placeholder="本次要解决的问题（用于关联摘要）"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button onClick={copy}>复制关联摘要</button>
            <button
              onClick={() =>
                download(
                  "material-relations.json",
                  JSON.stringify({ question: query, graph }, null, 2),
                )
              }
            >
              导出 JSON
            </button>
            <button onClick={() => saveView().catch((e) => error(e.message))}>
              保存视图
            </button>
          </div>
          <div className="row toolbar">
            <div className="segmented">
              {(
                [
                  ["radial", "问题辐射"],
                  ["groups", "主题聚合"],
                  ["evidence", "证据链"],
                ] as const
              ).map(([v, t]) => (
                <button
                  className={mode === v ? "active" : ""}
                  key={v}
                  onClick={() => {
                    setMode(v);
                    setOffset(0);
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
            <select
              aria-label="展开深度"
              value={hops}
              onChange={(e) => {
                setHops(Number(e.target.value));
                setOffset(0);
              }}
            >
              <option value={1}>一跳关联</option>
              <option value={2}>两跳关联</option>
            </select>
            <select
              aria-label="关系类型"
              value={types[0] || ""}
              onChange={(e) => setTypes(e.target.value ? [e.target.value] : [])}
            >
              <option value="">全部关系类型</option>
              {Object.entries(relationNames).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <label>
              <input
                type="checkbox"
                checked={candidates}
                onChange={(e) => setCandidates(e.target.checked)}
              />
              显示候选
            </label>
            <button
              onClick={() => {
                setSeeds([]);
                setCenter(history.at(-1) || "");
                setHistory((h) => h.slice(0, -1));
                setOffset(0);
              }}
              disabled={!history.length}
            >
              返回上个中心
            </button>
            <button onClick={() => focus("")}>全部材料</button>
          </div>
          <div className="graph-layout">
            <aside className="card material-list">
              <h2>材料与主题</h2>
              <fieldset className="material-kind-options">
                <legend>记录层级</legend>
                {[
                  ["L1", "L1 详细研究"],
                  ["L2", "L2 过程"],
                  ["L3", "L3 经验"],
                  ["L4", "L4 地图"],
                  ["native", "原生导航（未分层）"],
                ].map(([level, label]) => (
                  <label key={level}>
                    <input
                      type="checkbox"
                      aria-label={label}
                      checked={levels.includes(level)}
                      onChange={() => {
                        setLevels((old) =>
                          old.includes(level)
                            ? old.filter((v) => v !== level)
                            : [...old, level],
                        );
                        setCenter("");
                        setSeeds([]);
                        setSelected("");
                        setOffset(0);
                      }}
                    />
                    {label}
                  </label>
                ))}
                <small>L0 原始证据通过固定来源按需追溯。</small>
              </fieldset>
              <input
                aria-label="查找中心材料"
                placeholder="搜索标题或 ID"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <fieldset className="material-kind-options">
                <legend>材料分类（可多选）</legend>
                {Object.entries(kindNames).map(([kind, name]) => (
                  <label
                    key={kind}
                    className={
                      materialKinds.includes(kind)
                        ? "kind-option active"
                        : "kind-option"
                    }
                  >
                    <input
                      type="checkbox"
                      aria-label={`分类：${name}`}
                      checked={materialKinds.includes(kind)}
                      onChange={() =>
                        setMaterialKinds((old) =>
                          old.includes(kind)
                            ? old.filter((value) => value !== kind)
                            : [...old, kind],
                        )
                      }
                    />
                    <span>{name}</span>
                  </label>
                ))}
                <span className="muted">未勾选时显示全部分类</span>
              </fieldset>
              {mode === "groups" && (
                <div className="topic-list">
                  {topics.map((t) => (
                    <details key={t.id}>
                      <summary>
                        {t.name} · {t.members.length}
                      </summary>
                      <button onClick={() => focus(t.id)}>展开主题</button>
                      {t.members.slice(0, 60).map((id) => (
                        <button key={id} onClick={() => focus(id)}>
                          {catalog.nodes.find((n) => n.id === id)?.title || id}
                        </button>
                      ))}
                    </details>
                  ))}
                  {groups.map((g, i) => (
                    <details key={i}>
                      <summary>{g.name} · 视图分组</summary>
                      {g.members.map((id) => (
                        <button key={id} onClick={() => focus(id)}>
                          {catalog.nodes.find((n) => n.id === id)?.title || id}
                        </button>
                      ))}
                      <button
                        onClick={() =>
                          setGroups((old) => old.filter((_, j) => j !== i))
                        }
                      >
                        移除展示分组
                      </button>
                    </details>
                  ))}
                </div>
              )}
              <p className="muted">
                已选 {seeds.length}/50 · 最多列出 60 个搜索结果
              </p>
              {seeds.length > 0 && (
                <button
                  onClick={() => {
                    setSeeds([]);
                    setOffset(0);
                  }}
                >
                  清空勾选
                </button>
              )}
              <div className="scroll-list">
                {matches.map((n) => (
                  <div
                    className="material-row"
                    key={n.id}
                    data-material-id={n.id}
                  >
                    <input
                      aria-label={`选择 ${n.title}`}
                      type="checkbox"
                      checked={seeds.includes(n.id)}
                      onChange={() => choose(n.id)}
                    />
                    <button
                      className={selected === n.id ? "item active" : "item"}
                      onClick={() => {
                        setSelected(n.id);
                        setEdgeSelected(false);
                      }}
                      onDoubleClick={() => focus(n.id)}
                    >
                      <span className="eyebrow">
                        {kindNames[n.kind] || n.kind}
                      </span>
                      <strong>{n.title}</strong>
                      <small className="id">{n.id}</small>
                      {n.risks.length > 0 && (
                        <span className="risk">存在风险</span>
                      )}
                    </button>
                  </div>
                ))}
              </div>
              <details>
                <summary>自定义视觉分组</summary>
                <input
                  aria-label="分组名称"
                  placeholder="分组名称"
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                />
                <button
                  disabled={!groupName.trim() || !seeds.length}
                  onClick={() => {
                    setGroups((g) => [
                      ...g,
                      { name: groupName, members: seeds },
                    ]);
                    setGroupName("");
                  }}
                >
                  将选择保存为分组
                </button>
              </details>
            </aside>
            <main className="graph-main">
              <GraphPanel
                key={layoutVersion}
                graph={graph}
                mode={mode}
                center={center}
                positions={positions || {}}
                groups={visualGroups}
                onSelect={(id, isEdge) => {
                  setSelected(id);
                  setEdgeSelected(isEdge);
                }}
                onPositions={setPositions}
              />
              <div className="row spread">
                <p className="muted">
                  {seeds.length
                    ? `勾选 ${seeds.length} 个材料及其${hops === 1 ? "一" : "两"}跳关联 · `
                    : ""}
                  显示 {graph.nodes.length} 个节点 / {graph.edges.length} 条边 ·
                  当前范围另有 {graph.omitted_nodes} 个节点、
                  {graph.omitted_edges} 条边未显示
                </p>
                <div>
                  <button
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - 300))}
                  >
                    上一页
                  </button>
                  <button
                    disabled={!graph.omitted_nodes || graph.nodes.length < 300}
                    onClick={() => setOffset(offset + 300)}
                  >
                    下一页
                  </button>
                  <button
                    onClick={() => {
                      setPositions({});
                      setLayoutVersion((v) => v + 1);
                      setCenter("");
                      setOffset(0);
                    }}
                  >
                    重置布局
                  </button>
                </div>
              </div>
              <details className="card">
                <summary>读取范围与缺口</summary>
                <pre>
                  {JSON.stringify(
                    {
                      generated_at: catalog.generated_at,
                      coverage: catalog.coverage,
                      errors: catalog.errors,
                      excluded,
                    },
                    null,
                    2,
                  )}
                </pre>
                <button onClick={() => setExcluded([])}>
                  清空本视图排除项
                </button>
              </details>
            </main>
            <aside className="card detail-panel">
              <h2>{edgeSelected ? "为什么相连" : "材料详情"}</h2>
              {edgeSelected && edge ? (
                <>
                  <h3>{relationNames[edge.type] || edge.type}</h3>
                  <p className="id">
                    {edge.source} → {edge.target}
                  </p>
                  <p>{edge.origin}</p>
                  <p>{edge.locator || "未提供片段定位"}</p>
                  <p>
                    {edge.candidate
                      ? "候选，尚非正式关系"
                      : edge.derived
                        ? "由现有记录派生"
                        : "已记录的关系；结论需分别复核"}
                  </p>
                  <pre>{JSON.stringify(edge, null, 2)}</pre>
                  <button onClick={() => focus(edge.source)}>查看起点</button>
                  <button onClick={() => focus(edge.target)}>查看终点</button>
                </>
              ) : node ? (
                <>
                  <span className="badge">
                    {kindNames[node.kind] || node.kind}
                  </span>
                  <h3>{node.title}</h3>
                  <p className="id">{node.id}</p>
                  <p>{node.statement}</p>
                  <p>{node.record_reason || "未单独记录保存理由"}</p>
                  <dl>
                    <dt>复核</dt>
                    <dd>{node.review.status || "not-reviewed"}</dd>
                    <dt>执行</dt>
                    <dd>{node.execution_status || "未提供"}</dd>
                    <dt>适用范围</dt>
                    <dd>{node.scope || "未提供"}</dd>
                    <dt>来源</dt>
                    <dd className="id">{node.path}</dd>
                  </dl>
                  {node.risks.map((x) => (
                    <p className="risk" key={x}>
                      {x}
                    </p>
                  ))}
                  <button className="primary" onClick={() => focus(node.id)}>
                    以此为中心
                  </button>
                  <button
                    onClick={() =>
                      api<{ path: string; text: string; truncated: boolean }>(
                        `preview?id=${encodeURIComponent(node.id)}&fingerprint=${node.fingerprint}`,
                      )
                        .then(setPreview)
                        .catch((e) => error(e.message))
                    }
                  >
                    预览原件
                  </button>
                  <button
                    onClick={() => {
                      setExcluded((x) => [...x, node.id]);
                      setSeeds((s) => s.filter((id) => id !== node.id));
                      if (center === node.id) setCenter("");
                    }}
                  >
                    本次排除
                  </button>
                  <button onClick={() => choose(node.id)}>
                    {seeds.includes(node.id) ? "取消选择" : "加入分析选择"}
                  </button>
                </>
              ) : (
                <p className="muted">
                  点击节点查看材料，点击连线查看依据。列表支持键盘操作。
                </p>
              )}
            </aside>
          </div>
          <section className="card">
            <div className="row spread">
              <h2>发现潜在联系</h2>
              <div className="row">
                <button
                  disabled={!seeds.length}
                  onClick={() => launch("keywords", seeds, excluded)}
                >
                  共享关键词
                </button>
                <button
                  disabled={!seeds.length}
                  onClick={() => launch("semantic", seeds, excluded)}
                >
                  本地语义相似
                </button>
                <button disabled={busy} onClick={() => runCluster(false)}>
                  结构聚类
                </button>
                <button disabled={busy} onClick={() => runCluster(false, true)}>
                  全范围结构聚类
                </button>
                <button
                  disabled={busy || !candidates}
                  onClick={() => runCluster(true)}
                >
                  候选聚类
                </button>
                {busy && (
                  <button
                    onClick={() => {
                      worker.current?.terminate();
                      setBusy(false);
                    }}
                  >
                    取消聚类
                  </button>
                )}
              </div>
            </div>
            <p className="muted">
              相似分析在允许范围内寻找近邻；默认聚类针对当前可见选择，全范围聚类覆盖未排除材料。候选结果不会提高证据可信等级。
            </p>
            {clusters && (
              <>
                <p>
                  {clusters.method} · {clusters.note}
                </p>
                <div className="cluster-grid">
                  {clusters.clusters.slice(0, 100).map((c) => (
                    <details key={c.id}>
                      <summary>
                        {c.title} · {c.members.length}
                      </summary>
                      {c.members.slice(0, 60).map((id) => (
                        <button key={id} onClick={() => focus(id)}>
                          {catalog.nodes.find((n) => n.id === id)?.title || id}
                        </button>
                      ))}
                    </details>
                  ))}
                </div>
                <p className="muted">
                  共 {clusters.clusters.length} 个组；页面最多列出 100 组，每组
                  60 个成员。导出包含全部聚类成员。
                </p>
                <h3>跨组连接</h3>
                {clusters.bridges.map((e) => (
                  <button
                    key={e.id}
                    onClick={() => {
                      setSelected(e.id);
                      setEdgeSelected(true);
                    }}
                  >
                    {catalog.nodes.find((n) => n.id === e.source)?.title} →{" "}
                    {catalog.nodes.find((n) => n.id === e.target)?.title}
                  </button>
                ))}
                <h3>待研究的主题组合</h3>
                {clusters.questions.map((q, i) => (
                  <div className="row" key={i}>
                    <span>{q.title}</span>
                    <button
                      onClick={() =>
                        saveProposal(
                          q.title,
                          clusters.note,
                          q.refs,
                          "bridge-question",
                        ).catch((e) => error(e.message))
                      }
                    >
                      保存为待核对问题
                    </button>
                  </div>
                ))}
                <button
                  onClick={() =>
                    download(
                      "clusters.json",
                      JSON.stringify(
                        {
                          ...clusters,
                          refs: catalog.nodes
                            .filter((n) =>
                              clusters.clusters.some((c) =>
                                c.members.includes(n.id),
                              ),
                            )
                            .map((n) => ({
                              id: n.id,
                              fingerprint: n.fingerprint,
                              locator: n.locator || n.path,
                            })),
                        },
                        null,
                        2,
                      ),
                    )
                  }
                >
                  导出聚类供 AI 命名
                </button>
              </>
            )}
          </section>
          <section className="card">
            <h2>关联建议</h2>
            <div className="row">
              <input
                aria-label="候选标题"
                placeholder="针对所选材料提出一个关联建议"
                value={proposalTitle}
                onChange={(e) => setProposalTitle(e.target.value)}
              />
              <input
                aria-label="候选解释"
                placeholder="依据与待核对内容"
                value={proposalNote}
                onChange={(e) => setProposalNote(e.target.value)}
              />
              <button
                disabled={!seeds.length || !proposalTitle || !proposalNote}
                onClick={() => saveProposal().catch((e) => error(e.message))}
              >
                保存候选
              </button>
              <button onClick={() => setImporting(true)}>导入 AI 候选</button>
            </div>
            {proposals.map((p) => (
              <article className="proposal" key={p.id}>
                <div className="row spread">
                  <h3>{p.title}</h3>
                  <span className="badge">
                    {p.status}
                    {p.stale ? " · 版本已过期" : ""}
                  </span>
                </div>
                <p>{p.explanation}</p>
                <p className="muted">
                  提出者：{p.actor} · {p.kind}
                </p>
                {p.kind === "cluster-name" && (
                  <button
                    disabled={p.stale || p.status === "dismissed"}
                    onClick={() => {
                      setGroups((old) => [
                        ...old,
                        {
                          name: `${p.title}（${p.actor} 建议）`,
                          members: p.refs.map((r) => r.id),
                        },
                      ]);
                      setMode("groups");
                      error(
                        "已应用展示名称；可保存视图保留此分组。候选复核状态保持原样。",
                      );
                    }}
                  >
                    用于展示分组
                  </button>
                )}
                <details>
                  <summary>依据与处理历史</summary>
                  <pre>
                    {JSON.stringify(
                      { refs: p.refs, history: p.history },
                      null,
                      2,
                    )}
                  </pre>
                </details>
                <button
                  onClick={() => {
                    setProposalTitle(p.title);
                    setProposalNote("处理说明：");
                    setDraft(p.id);
                  }}
                >
                  处理此候选
                </button>
                {draft === p.id && (
                  <div className="row">
                    <input
                      aria-label="处理说明"
                      value={proposalNote}
                      onChange={(e) => setProposalNote(e.target.value)}
                    />
                    {(["handled", "dismissed", "pending"] as const).map(
                      (s, i) => (
                        <button
                          key={s}
                          onClick={() =>
                            api("resolve", {
                              id: p.id,
                              status: s,
                              actor: "user",
                              note: proposalNote,
                            })
                              .then(reloadProposals)
                              .then(() => setDraft(""))
                              .catch((e) => error(e.message))
                          }
                        >
                          {["标记已处理", "驳回", "恢复待处理"][i]}
                        </button>
                      ),
                    )}
                  </div>
                )}
              </article>
            ))}
          </section>
        </>
      )}
      {preview && (
        <Modal title={preview.path} close={() => setPreview(null)}>
          <pre>{preview.text}</pre>
          {preview.truncated && <p>仅展示前 64 KiB。</p>}
        </Modal>
      )}
      {showExport && (
        <Modal title="复制以下关联摘要" close={() => setShowExport("")}>
          <textarea readOnly value={showExport} aria-label="关联摘要" />
        </Modal>
      )}
      {importing && (
        <Modal
          title="导入 AI 候选（单条 JSON）"
          close={() => setImporting(false)}
        >
          <p>
            字段：kind（relation / cluster-name /
            bridge-question）、title、explanation、actor、refs。每个 ref 必须含
            id、fingerprint、locator。
          </p>
          <textarea
            aria-label="AI 候选 JSON"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button
            onClick={() => {
              try {
                api("candidate", JSON.parse(draft))
                  .then(reloadProposals)
                  .then(() => {
                    setImporting(false);
                    setDraft("");
                  })
                  .catch((e) => error(e.message));
              } catch (e) {
                error(String(e));
              }
            }}
          >
            核对并保存候选
          </button>
        </Modal>
      )}
    </>
  );
}
