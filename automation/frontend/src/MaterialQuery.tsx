import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { MaterialStructure, ownerTypeNames } from "./MaterialStructure";
import { MaterialMaintenance } from "./MaterialMaintenance";
import {
  FixedReferences,
  groupTitles,
  MaterialPacket,
  ResultStatus,
  type MaterialRequest,
} from "./MaterialPacket";
import type {
  AssociationProposal,
  Budget,
  Candidate,
  DeepenReceipt,
  FixedRef,
  MaterialPacket as Packet,
  QueryJob,
  QueryRequest,
  RepresentationDefinition,
  Result,
  Scope,
  SearchReceipt,
  TreeNode,
} from "./generated/material-query";
import "./material-query.css";

export const emptyScope = (): Scope => ({
  owner_ids: [],
  levels: null,
  kinds: null,
  roles: null,
  outcomes: null,
  review_states: null,
  validities: null,
  include_unknown: false,
  excluded_refs: [],
  excluded_owner_ids: [],
  recorded_from: null,
  recorded_before: null,
});
export const defaultBudget: Budget = {
  wall_ms: 300000,
  read_bytes: 16777216,
  output_chars: 80000,
  candidates: 100,
  graph_nodes: 50,
  graph_edges: 100,
  graph_hops: 2,
  model_tokens: 0,
  model_calls: 0,
  model_input_tokens: 0,
  model_output_tokens: 0,
  rerank_items: 0,
};
type MaterialCapabilities = {
  enabled: boolean;
  definitions_version: string;
  association: { modes: string[]; strategy: string; version: string };
  deepening: { modes: string[]; strategy: string; version: string };
  maintenance: { task_package: boolean };
  default_budget: Budget;
  default_result_limit?: number;
  limits: Budget;
  channels?: string[];
};

/** Fetch failures retain a structured material Result when the server supplied
 * one. Network errors remain errors instead of invented success envelopes. */
export const materialRequest: MaterialRequest = async <T,>(
  route: string,
  data?: unknown,
) => {
  try {
    return await api<Result<T>>(route, data);
  } catch (cause) {
    const error = cause as {
      materialResult?: Result<T>;
      responseBody?: Result<T>;
    };
    const envelope = error.materialResult || error.responseBody;
    if (
      envelope &&
      typeof envelope.status === "string" &&
      "consumed" in envelope
    )
      return envelope;
    throw cause;
  }
};
const list = (value: string) =>
  value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
const realizationNames = {
  direct: "直接可用",
  assemblable: "可组装",
  needs_generation: "需要生成草案",
  stale: "版本已变化",
  unsupported: "不支持",
};

function expirationLabel(timestamp: string) {
  const date = new Date(timestamp);
  return Number.isNaN(date.valueOf())
    ? timestamp
    : `${date.toLocaleString("zh-CN", { hour12: false })}（本机时间）`;
}

function ScopeList({
  title,
  value,
  update,
}: {
  title: string;
  value: string[] | null;
  update: (value: string[] | null) => void;
}) {
  const [text, setText] = useState(value?.join(", ") || "");
  const emitted = useRef(JSON.stringify(value));
  const key = JSON.stringify(value);
  useEffect(() => {
    if (key !== emitted.current) {
      setText(value?.join(", ") || "");
      emitted.current = key;
    }
  }, [key, value]);
  // Preserve a trailing comma during typing. Only the parsed request is
  // normalized; external tree selections still replace the visible text.
  return (
    <div className="scope-field">
      <label>
        <input
          type="checkbox"
          checked={value !== null}
          onChange={(event) => update(event.target.checked ? [] : null)}
        />
        限制{title}
      </label>
      {value !== null && (
        <label>
          {title}（逗号分隔，留空表示空集合）
          <input
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              const next = list(event.target.value);
              emitted.current = JSON.stringify(next);
              update(next);
            }}
          />
        </label>
      )}
    </div>
  );
}

export function MaterialQuery() {
  const [capabilities, setCapabilities] = useState<MaterialCapabilities | null>(
    null,
  );
  const [scope, setScope] = useState<Scope>(emptyScope);
  const [readDependencies, setReadDependencies] = useState(true);
  const [question, setQuestion] = useState("");
  const [keywords, setKeywords] = useState("");
  const [definition, setDefinition] = useState<QueryRequest["definition"]>({
    key: "full",
    version: "1",
  });
  const [purpose, setPurpose] =
    useState<QueryRequest["purpose"]>("exploration");
  const [freshness, setFreshness] =
    useState<QueryRequest["freshness"]>("current");
  const [contentSource, setContentSource] = useState<
    NonNullable<QueryRequest["content_source"]>
  >("overview_experience");
  const [association, setAssociation] =
    useState<QueryRequest["association"]["mode"]>("off");
  const [associationCount, setAssociationCount] = useState(5);
  const [associationShare, setAssociationShare] = useState(0.2);
  const [budget, setBudget] = useState<Budget>(defaultBudget);
  const [limit, setLimit] = useState(20);
  const [channels, setChannels] = useState<
    NonNullable<QueryRequest["channels"]>
  >(["identity", "lexical"]);
  const [dialect, setDialect] =
    useState<NonNullable<QueryRequest["dialect"]>>("plain");
  const [applicability, setApplicability] = useState("");
  const [receipt, setReceipt] = useState<SearchReceipt | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [packet, setPacket] = useState<Packet | null>(null);
  const [outputResult, setOutputResult] = useState<Result<unknown> | null>(
    null,
  );
  const [outputTitle, setOutputTitle] = useState("材料包");
  const outputPanel = useRef<HTMLElement | null>(null);
  const [result, setResult] = useState<Result<unknown> | null>(null);
  const [proposals, setProposals] = useState<AssociationProposal[]>([]);
  const [deepening, setDeepening] = useState<DeepenReceipt | null>(null);
  const [deepMode, setDeepMode] = useState<"source_mapping" | "bounded_graph">(
    "source_mapping",
  );
  const [direction, setDirection] = useState<"forward" | "reverse" | "both">(
    "both",
  );
  const [relations, setRelations] = useState(
    "contains, depends_on, supports, contradicts",
  );
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  const runningId = useRef<string | null>(null);
  const decisionIds = useRef<Record<string, string>>({});
  const draftRevision = useRef(0);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api<MaterialCapabilities>("materials/capabilities"),
      materialRequest<RepresentationDefinition[]>(
        "representations/definitions",
      ),
    ])
      .then(([caps, defs]) => {
        if (!alive) return;
        setCapabilities(caps);
        // Do not overwrite a user who started configuring the form while the
        // capabilities request was in flight.
        if (!draftRevision.current) {
          setBudget(caps.default_budget);
          setLimit(caps.default_result_limit ?? 20);
          const preferred =
            defs.value?.find((value) => value.ref.key === "full") ||
            defs.value?.[0];
          if (preferred) setDefinition(preferred.ref);
        }
        if (defs.status !== "ok") setResult(defs);
      })
      .catch((cause) => {
        if (alive) setError(String(cause));
      });
    return () => {
      alive = false;
      sequence.current++;
      if (runningId.current)
        void materialRequest("materials/cancel", {
          query_id: runningId.current,
        }).catch(() => {});
    };
  }, []);

  function invalidate() {
    draftRevision.current++;
    sequence.current++;
    setBusy(false);
    setStale(Boolean(receipt));
    setSelected([]);
    setPacket(null);
    setOutputResult(null);
    setProposals([]);
    setDeepening(null);
    const previous = runningId.current;
    runningId.current = null;
    if (previous)
      void materialRequest("materials/cancel", { query_id: previous }).catch(
        () => {},
      );
  }
  function changeScope(patch: Partial<Scope>) {
    invalidate();
    setScope((value) => ({ ...value, ...patch }));
  }
  function choose(node: TreeNode | null, ownerId?: string) {
    if (!node) changeScope({ owner_ids: null, levels: null, include_refs: [] });
    else if (node.kind === "owner")
      changeScope({
        owner_ids: [node.node_id],
        levels: null,
        include_refs: [],
      });
    else if (node.kind === "layer")
      changeScope({
        owner_ids: [node.node_id.split("::")[0]],
        levels: node.layer ? [node.layer] : null,
        include_refs: [],
      });
    else if (node.ref)
      changeScope({
        ...(ownerId ? { owner_ids: [ownerId] } : {}),
        levels: null,
        include_refs: [node.ref],
      });
  }
  function buildRequest(): QueryRequest {
    return {
      definition,
      content_source: contentSource,
      question,
      keywords: list(keywords),
      scope,
      // 筛选对象不是依赖授权边界：默认读取其已登记必要依据。排除项始终
      // 传递，服务端仍核验来源授权；用户可显式收紧到当前所选对象。
      scope_ceiling: readDependencies
        ? {
            ...emptyScope(),
            owner_ids: null,
            excluded_owner_ids: scope.excluded_owner_ids,
            excluded_refs: scope.excluded_refs,
            exclude_ids: scope.exclude_ids,
          }
        : scope,
      purpose,
      association: {
        mode: association,
        strategy: capabilities?.association.strategy || "existing-relations",
        strategy_version: capabilities?.association.version || "1",
        max_items: associationCount,
        output_share: associationShare,
        supplement_scope: null,
      },
      budget,
      freshness,
      result_limit: limit,
      missing_policy: "reject",
      fallback_definitions: [],
      applicability,
      channels,
      dialect,
      ranking_strategy: "topic-evidence-v2",
      ranking_version: "1",
      allow_index_repair: false,
      max_staleness_seconds: null,
    };
  }
  async function search() {
    invalidate();
    const token = ++sequence.current;
    setBusy(true);
    setError("");
    setReceipt(null);
    setPacket(null);
    setResult(null);
    setStale(false);
    try {
      const start = await materialRequest<QueryJob>(
        "materials/start",
        buildRequest(),
      );
      if (token !== sequence.current) {
        if (start.value)
          void materialRequest("materials/cancel", {
            query_id: start.value.query_id,
          }).catch(() => {});
        return;
      }
      setResult(start);
      if (!start.value || !["ok", "partial"].includes(start.status)) return;
      runningId.current = start.value.query_id;
      while (token === sequence.current) {
        const polled = await materialRequest<SearchReceipt>("materials/poll", {
          query_id: start.value.query_id,
        });
        if (token !== sequence.current) return;
        setResult(polled);
        if (polled.value) setReceipt(polled.value);
        if (polled.code !== "RUNNING") break;
        await new Promise((resolve) => setTimeout(resolve, 400));
      }
    } catch (cause) {
      if (token === sequence.current) setError(String(cause));
    } finally {
      if (token === sequence.current) {
        setBusy(false);
        runningId.current = null;
      }
    }
  }
  async function cancel() {
    const id = runningId.current || receipt?.query_id;
    sequence.current++;
    runningId.current = null;
    setBusy(false);
    setStale(Boolean(receipt));
    setSelected([]);
    setPacket(null);
    if (id)
      try {
        setResult(await materialRequest("materials/cancel", { query_id: id }));
      } catch (cause) {
        setError(String(cause));
      }
  }
  async function act<T>(
    route: string,
    data: unknown,
    consume: (value: T) => void,
  ) {
    const token = sequence.current;
    // 每次操作先撤下前一份输出，避免失败后仍把旧材料包留在右侧当作新结果。
    setPacket(null);
    setOutputResult(null);
    setOutputTitle(
      route === "materials/documents"
        ? "完整文稿"
        : route === "materials/deepen"
          ? "深化关联结果"
          : route === "materials/expand"
            ? "展开结果"
            : "材料包",
    );
    setDeepening(null);
    setBusy(true);
    setError("");
    try {
      const response = await materialRequest<T>(route, data);
      if (token !== sequence.current) return;
      setResult(response);
      setOutputResult(response);
      requestAnimationFrame(() =>
        outputPanel.current?.scrollIntoView?.({
          behavior: "smooth",
          block: "nearest",
        }),
      );
      if (response.value) consume(response.value);
    } catch (cause) {
      if (token === sequence.current) setError(String(cause));
    } finally {
      if (token === sequence.current) setBusy(false);
    }
  }
  function showPacket(value: Packet | null | undefined, title = "材料包") {
    setPacket(value || null);
    setOutputTitle(title);
    // 更新 DOM 后定位右侧结果标题。宽屏结果列固定在视口内；窄屏滚动到结果。
    requestAnimationFrame(() =>
      outputPanel.current?.scrollIntoView?.({
        behavior: "smooth",
        block: "nearest",
      }),
    );
  }
  function expandSelected(target: "process" | "technical") {
    if (!receipt) return;
    void act<DeepenReceipt>(
      "materials/expand",
      {
        query_id: receipt.query_id,
        candidate_ids: selected,
        expected_request_digest: receipt.request_digest,
        target,
        include_packet: true,
      },
      (value) => {
        mergeCandidates(value.candidates);
        setDeepening(value);
        showPacket(
          value.packet,
          target === "process" ? "展开研究经过" : "展开技术内容",
        );
      },
    );
  }
  function deepenSelected() {
    if (!receipt) return;
    void act<DeepenReceipt>(
      "materials/deepen",
      {
        query_id: receipt.query_id,
        candidate_ids: selected,
        mode: deepMode,
        relation_kinds: list(relations),
        direction,
        strategy: capabilities?.deepening.strategy || "bounded-bfs",
        strategy_version: capabilities?.deepening.version || "1",
        cursor: deepening?.next_cursor || null,
      },
      (value) => {
        mergeCandidates(value.candidates);
        setDeepening(value);
        setProposals(value.proposals);
      },
    );
  }
  function mergeCandidates(incoming: Candidate[]) {
    setReceipt((current) =>
      current
        ? {
            ...current,
            candidates: [
              ...new Map(
                [...current.candidates, ...incoming].map((value) => [
                  value.candidate_id,
                  value,
                ]),
              ).values(),
            ],
          }
        : current,
    );
  }
  const selectedCandidates =
    receipt?.candidates.filter((candidate) =>
      selected.includes(candidate.candidate_id),
    ) || [];
  const fixedRefs = [
    ...new Map(
      selectedCandidates
        .flatMap((candidate) => candidate.refs)
        .map((ref) => [
          `${ref.kind}:${ref.id}:${ref.revision}:${ref.sha256}:${ref.locator}`,
          ref,
        ]),
    ).values(),
  ] as FixedRef[];
  const unavailable = !receipt || stale || busy || selected.length === 0;

  return (
    <div className="material-query">
      <div className="page-heading">
        <div>
          <p className="eyebrow">分层材料 / 固定依据</p>
          <h1>材料查询</h1>
          <p>先选择范围，再寻找材料。关联建议与待维护草案保留独立状态。</p>
        </div>
      </div>
      <div className="material-columns">
        <MaterialStructure
          request={materialRequest}
          scope={scope}
          onChoose={choose}
          onTypesChange={(owner_types) =>
            changeScope({
              owner_types,
              owner_ids: null,
              levels: null,
              include_refs: [],
            })
          }
          onClear={() =>
            changeScope({ owner_ids: [], levels: null, include_refs: [] })
          }
        />
        <main className="material-search">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void search();
            }}
          >
            <h2>查找与组装</h2>
            <p className="scope-summary">
              查询范围：
              {scope.owner_ids === null
                ? "全局获准范围"
                : scope.owner_ids.length
                  ? scope.owner_ids.join("、")
                  : "空范围，请选择归属对象"}
              {scope.levels && ` · ${scope.levels.join("、") || "空层级"}`}
              {scope.owner_types &&
                ` · 类型：${scope.owner_types.map((kind) => ownerTypeNames[kind] || kind).join("、") || "空集合"}`}
              {scope.include_refs?.length
                ? ` · 固定引用 ${scope.include_refs.length} 项`
                : ""}
            </p>
            <label>
              问题
              <textarea
                aria-label="问题"
                value={question}
                onChange={(event) => {
                  invalidate();
                  setQuestion(event.target.value);
                }}
                placeholder="希望材料帮助回答什么？"
              />
            </label>
            <label>
              关键词
              <input
                value={keywords}
                onChange={(event) => {
                  invalidate();
                  setKeywords(event.target.value);
                }}
                placeholder="逗号分隔"
              />
            </label>
            <div className="material-form-grid">
              <label>
                内容来源
                <select
                  aria-label="内容来源"
                  value={contentSource}
                  onChange={(event) => {
                    invalidate();
                    setContentSource(
                      event.target.value as typeof contentSource,
                    );
                  }}
                >
                  <option value="overview_experience">概览与经验</option>
                  <option value="process">研究经过</option>
                  <option value="technical">技术内容</option>
                  <option value="all">所有来源</option>
                </select>
              </label>
              <label>
                查询用途
                <select
                  aria-label="查询用途"
                  value={purpose}
                  onChange={(event) => {
                    invalidate();
                    setPurpose(event.target.value as typeof purpose);
                  }}
                >
                  <option value="exploration">探索</option>
                  <option value="formal">正式使用</option>
                  <option value="audit">审计</option>
                </select>
              </label>
            </div>
            <label>
              记录版本
              <select
                aria-label="记录版本"
                value={freshness}
                onChange={(event) => {
                  invalidate();
                  setFreshness(event.target.value as typeof freshness);
                }}
              >
                <option value="current">仅最新记录（默认）</option>
                <option value="allow_stale">包含历史记录</option>
                <option value="fixed">固定本次版本</option>
              </select>
            </label>
            <p className="muted">
              读取时间预算：{budget.wall_ms / 60000} 分钟；只计算实际处理时间。
            </p>
            <label>
              <input
                type="checkbox"
                checked={readDependencies}
                onChange={(event) => {
                  invalidate();
                  setReadDependencies(event.target.checked);
                }}
              />
              读取所选材料引用的必要依据（可跨对象，遵守排除与来源授权）
            </label>
            <p className="muted">
              直接读取已有正文；可从所选概览或经验沿已保存的关联展开研究经过、技术内容。
            </p>
            <details>
              <summary>高级范围与查询约束</summary>
              <ScopeList
                title="归属对象"
                value={scope.owner_ids}
                update={(owner_ids) => changeScope({ owner_ids })}
              />
              {(
                [
                  ["levels", "层级"],
                  ["kinds", "记录类型"],
                  ["roles", "角色"],
                  ["outcomes", "结果"],
                  ["review_states", "复核状态"],
                  ["validities", "有效性"],
                  ["source_ids", "来源"],
                  ["confidence_levels", "置信等级"],
                ] as const
              ).map(([key, title]) => (
                <ScopeList
                  key={key}
                  title={title}
                  value={scope[key] ?? null}
                  update={(value) => changeScope({ [key]: value })}
                />
              ))}
              <label>
                排除归属对象
                <input
                  value={scope.excluded_owner_ids.join(", ")}
                  onChange={(event) =>
                    changeScope({
                      excluded_owner_ids: list(event.target.value),
                    })
                  }
                />
              </label>
              <label>
                排除记录 ID
                <input
                  value={(scope.exclude_ids || []).join(", ")}
                  onChange={(event) =>
                    changeScope({ exclude_ids: list(event.target.value) })
                  }
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={scope.include_unknown}
                  onChange={(event) =>
                    changeScope({ include_unknown: event.target.checked })
                  }
                />
                包含未知属性
              </label>
              <label>
                记录时间起点（含，ISO 8601）
                <input
                  value={scope.recorded_from || ""}
                  onChange={(event) =>
                    changeScope({ recorded_from: event.target.value || null })
                  }
                />
              </label>
              <label>
                记录时间终点（不含，ISO 8601）
                <input
                  value={scope.recorded_before || ""}
                  onChange={(event) =>
                    changeScope({ recorded_before: event.target.value || null })
                  }
                />
              </label>
              <label>
                适用条件
                <input
                  value={applicability}
                  onChange={(event) => {
                    invalidate();
                    setApplicability(event.target.value);
                  }}
                />
              </label>
              <fieldset>
                <legend>检索通道</legend>
                {(
                  ["identity", "lexical", "dense", "sparse", "graph"] as const
                ).map((channel) => (
                  <label key={channel}>
                    <input
                      type="checkbox"
                      checked={channels.includes(channel)}
                      disabled={
                        !(
                          capabilities?.channels || ["identity", "lexical"]
                        ).includes(channel)
                      }
                      onChange={(event) => {
                        invalidate();
                        setChannels((values) =>
                          event.target.checked
                            ? [...values, channel]
                            : values.filter((value) => value !== channel),
                        );
                      }}
                    />
                    {
                      {
                        identity: "精确标识",
                        lexical: "词法",
                        dense: "向量",
                        sparse: "稀疏",
                        graph: "关系",
                      }[channel]
                    }
                  </label>
                ))}
              </fieldset>
              <label>
                词法语法
                <select
                  aria-label="词法语法"
                  value={dialect}
                  onChange={(event) => {
                    invalidate();
                    setDialect(event.target.value as typeof dialect);
                  }}
                >
                  <option value="plain">普通文本</option>
                  <option value="phrase" disabled>
                    短语（当前未开放）
                  </option>
                  <option value="boolean" disabled>
                    布尔查询（当前未开放）
                  </option>
                </select>
              </label>
              <label>
                返回候选数量
                <input
                  type="number"
                  min={1}
                  max={capabilities?.limits.candidates || 2000}
                  value={limit}
                  onChange={(event) => {
                    invalidate();
                    setLimit(Number(event.target.value));
                  }}
                />
              </label>
            </details>
            <details>
              <summary>关联补充与预算</summary>
              <label>
                关联补充
                <select
                  aria-label="关联补充"
                  value={association}
                  onChange={(event) => {
                    invalidate();
                    setAssociation(event.target.value as typeof association);
                  }}
                >
                  <option value="off">关闭</option>
                  <option
                    value="existing_only"
                    disabled={
                      !capabilities?.association.modes.includes("existing_only")
                    }
                  >
                    已有关系
                  </option>
                  <option
                    value="explore_structural"
                    disabled={
                      !capabilities?.association.modes.includes(
                        "explore_structural",
                      )
                    }
                  >
                    结构探索
                  </option>
                </select>
              </label>
              {!capabilities?.association.modes.includes(
                "explore_structural",
              ) && (
                <p className="muted">
                  当前服务未开放结构探索；已有关系仅作为导航建议。
                </p>
              )}
              <label>
                关联候选上限
                <input
                  type="number"
                  min={0}
                  max={200}
                  value={associationCount}
                  onChange={(event) => {
                    invalidate();
                    setAssociationCount(Number(event.target.value));
                  }}
                />
              </label>
              <label>
                关联输出占比
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={associationShare}
                  onChange={(event) => {
                    invalidate();
                    setAssociationShare(Number(event.target.value));
                  }}
                />
              </label>
              <p className="muted">
                补充材料受当前范围上限约束。预算按同一查询累计。
              </p>
              <div className="material-form-grid">
                {(
                  [
                    ["wall_ms", "时间（毫秒）"],
                    ["read_bytes", "读取字节"],
                    ["output_chars", "输出字符"],
                    ["candidates", "候选数"],
                    ["graph_nodes", "图节点"],
                    ["graph_edges", "图边"],
                    ["graph_hops", "图跳数"],
                    ["model_tokens", "模型令牌"],
                    ["model_calls", "模型调用次数"],
                    ["model_input_tokens", "模型输入令牌"],
                    ["model_output_tokens", "模型输出令牌"],
                    ["rerank_items", "重排条目"],
                  ] as const
                ).map(([key, title]) => (
                  <label key={key}>
                    {title}
                    <input
                      type="number"
                      min={0}
                      max={capabilities?.limits[key]}
                      value={budget[key] || 0}
                      onChange={(event) => {
                        invalidate();
                        setBudget((value) => ({
                          ...value,
                          [key]: Number(event.target.value),
                        }));
                      }}
                    />
                  </label>
                ))}
              </div>
            </details>
            <div className="material-actions">
              <button type="submit" disabled={busy || !capabilities?.enabled}>
                开始查询
              </button>
              {busy && (
                <button type="button" onClick={() => void cancel()}>
                  取消查询
                </button>
              )}
            </div>
          </form>
          {error && <p role="alert">{error}</p>}
          {busy && <p role="status">正在处理查询…</p>}
          <ResultStatus result={outputResult ? null : result} />
          {receipt && (
            <section aria-label="查询候选">
              <h3>查询候选（{receipt.candidates.length}）</h3>
              {stale && (
                <p role="alert">
                  查询已失效或条件已变化，下方是上一次结果；请重新查询后操作。
                </p>
              )}
              <p className="muted">
                固定查询有效期至 {expirationLabel(receipt.expires_at)}
              </p>
              {receipt.gaps.length > 0 && (
                <ul className="material-gaps">
                  {receipt.gaps.map((gap, i) => (
                    <li key={i}>{gap}</li>
                  ))}
                </ul>
              )}
              <div
                className="material-selection-actions"
                aria-label="所选材料操作"
              >
                <strong>已选 {selected.length} 条</strong>
                <button
                  disabled={busy || stale}
                  onClick={() => {
                    setSelected(
                      receipt.candidates.map((item) => item.candidate_id),
                    );
                    setPacket(null);
                    setOutputResult(null);
                  }}
                >
                  全选候选
                </button>
                <button
                  disabled={busy || !selected.length}
                  onClick={() => {
                    setSelected([]);
                    setPacket(null);
                    setOutputResult(null);
                  }}
                >
                  清空选择
                </button>
                <div className="material-actions">
                  <button
                    disabled={unavailable}
                    onClick={() => expandSelected("process")}
                  >
                    展开研究经过
                  </button>
                  <button
                    disabled={unavailable}
                    onClick={() => expandSelected("technical")}
                  >
                    展开技术内容
                  </button>
                  <button
                    disabled={unavailable}
                    onClick={() =>
                      void act<Packet>(
                        "materials/assemble",
                        {
                          query_id: receipt.query_id,
                          candidate_ids: selected,
                          expected_request_digest: receipt.request_digest,
                        },
                        (value) => showPacket(value),
                      )
                    }
                  >
                    组装所选材料（{selected.length}）
                  </button>
                  <button
                    disabled={unavailable}
                    onClick={() =>
                      void act<Packet>(
                        "materials/documents",
                        {
                          query_id: receipt.query_id,
                          candidate_ids: selected,
                          expected_request_digest: receipt.request_digest,
                          document_type: "research_process",
                        },
                        (value) => showPacket(value, "完整文稿"),
                      )
                    }
                  >
                    返回完整文稿
                  </button>
                  <button disabled={unavailable} onClick={deepenSelected}>
                    {deepening?.next_cursor ? "继续深化" : "深化所选材料"}
                  </button>
                </div>
                <p className="muted">
                  展开同时读取正文、必要上下文和已启用的补充；完整文稿按命中所属对象查找，同一篇只返回一次。
                </p>
              </div>
              {(["direct", "required_context", "association"] as const).map(
                (group) => (
                  <section key={group}>
                    <h4>{groupTitles[group]}</h4>
                    {receipt.candidates
                      .filter((candidate) => candidate.group === group)
                      .map((candidate) => (
                        <article
                          className="material-candidate"
                          key={candidate.candidate_id}
                          data-testid="material-candidate"
                        >
                          <label>
                            <input
                              type="checkbox"
                              disabled={stale || busy}
                              checked={selected.includes(
                                candidate.candidate_id,
                              )}
                              onChange={(event) => {
                                setSelected((values) =>
                                  event.target.checked
                                    ? [...values, candidate.candidate_id]
                                    : values.filter(
                                        (value) =>
                                          value !== candidate.candidate_id,
                                      ),
                                );
                                setPacket(null);
                                setOutputResult(null);
                                setDeepening(null);
                              }}
                            />
                            {candidate.title}
                          </label>
                          <p>{candidate.excerpt}</p>
                          {candidate.is_latest !== undefined &&
                            candidate.is_latest !== null && (
                              <p className="candidate-state">
                                {candidate.is_latest ? "最新记录" : "历史记录"}{" "}
                                · 修订 {candidate.refs[0]?.revision}
                              </p>
                            )}
                          {candidate.knowledge_type && (
                            <p className="candidate-state">
                              认识性质：
                              {
                                {
                                  observation: "观察",
                                  conclusion: "结论",
                                  hypothesis: "原因假设",
                                  recommendation: "建议",
                                }[candidate.knowledge_type]
                              }
                            </p>
                          )}
                          <p className="candidate-state">
                            {realizationNames[candidate.realization.state]} ·{" "}
                            {["not-reviewed", "unreviewed"].includes(
                              candidate.evidence_status,
                            )
                              ? "尚未复核"
                              : candidate.evidence_status === "not-assessed"
                                ? "本次未评估复核"
                                : candidate.evidence_status}
                          </p>
                          {candidate.realization.missing_selectors.length >
                            0 && (
                            <p>
                              缺失字段：
                              {candidate.realization.missing_selectors.join(
                                "、",
                              )}
                            </p>
                          )}
                          <details>
                            <summary>命中来源与固定引用</summary>
                            <p>通道：{candidate.channels.join("、")}</p>
                            <FixedReferences refs={candidate.refs} />
                            {candidate.hits?.map((hit, i) => (
                              <p key={i}>
                                {hit.channel} · {hit.provider} ·{" "}
                                {hit.score_meaning} · 名次 {hit.rank}
                              </p>
                            ))}
                          </details>
                        </article>
                      ))}
                  </section>
                ),
              )}
              {receipt.next_cursor && (
                <button
                  disabled={busy || stale}
                  onClick={() =>
                    void act<SearchReceipt>(
                      "materials/resume",
                      {
                        query_id: receipt.query_id,
                        cursor: receipt.next_cursor,
                      },
                      (value) => {
                        mergeCandidates(value.candidates);
                        setReceipt((current) =>
                          current
                            ? {
                                ...current,
                                next_cursor: value.next_cursor,
                                gaps: value.gaps,
                              }
                            : value,
                        );
                      },
                    )
                  }
                >
                  继续读取候选
                </button>
              )}
              <details>
                <summary>沿所选材料深化</summary>
                <label>
                  深化方式
                  <select
                    aria-label="深化方式"
                    value={deepMode}
                    onChange={(event) => {
                      setDeepMode(event.target.value as typeof deepMode);
                      setDeepening(null);
                    }}
                  >
                    <option value="source_mapping">来源映射</option>
                    <option
                      value="bounded_graph"
                      disabled={
                        !capabilities?.deepening.modes.includes("bounded_graph")
                      }
                    >
                      有界关系展开
                    </option>
                  </select>
                </label>
                <label>
                  关系方向
                  <select
                    aria-label="关系方向"
                    value={direction}
                    onChange={(event) => {
                      setDirection(event.target.value as typeof direction);
                      setDeepening(null);
                    }}
                  >
                    <option value="both">双向</option>
                    <option value="forward">向下游</option>
                    <option value="reverse">向上游</option>
                  </select>
                </label>
                <label>
                  关系类型（逗号分隔）
                  <input
                    value={relations}
                    onChange={(event) => {
                      setRelations(event.target.value);
                      setDeepening(null);
                    }}
                  />
                </label>
                {deepening && (
                  <>
                    <p>
                      关系边：{deepening.edges.length}；新增候选：
                      {deepening.candidates.length}
                    </p>
                    <ul>
                      {deepening.gaps.map((gap, i) => (
                        <li key={i}>{gap}</li>
                      ))}
                    </ul>
                    <details>
                      <summary>关系依据</summary>
                      {deepening.edges.map((edge) => (
                        <p key={edge.edge_id}>
                          {edge.source.id} → {edge.kind} → {edge.target.id} ·{" "}
                          {edge.state}
                        </p>
                      ))}
                    </details>
                  </>
                )}
              </details>
              <button
                disabled={unavailable || association === "off"}
                onClick={() =>
                  void act<AssociationProposal[]>(
                    "materials/associations",
                    {
                      query_id: receipt.query_id,
                      seed_candidate_ids: selected,
                      profile: null,
                    },
                    setProposals,
                  )
                }
              >
                查看关联建议
              </button>
              {proposals.map((proposal) => (
                <article
                  className="association-proposal"
                  key={proposal.proposal_id}
                >
                  <h4>{proposal.common_structure}</h4>
                  <p>
                    状态：{proposal.state} · 方法：{proposal.method}
                  </p>
                  <p>差异：{proposal.differences.join("；")}</p>
                  <p>迁移条件：{proposal.transfer_conditions.join("；")}</p>
                  <p>待验证：{proposal.verification_hint}</p>
                  <FixedReferences refs={proposal.target} />
                  {(
                    [
                      ["accept_navigation", "接受为导航"],
                      ["reject", "拒绝建议"],
                    ] as const
                  ).map(([decision, title]) => (
                    <button
                      key={decision}
                      disabled={busy || stale || proposal.state !== "temporary"}
                      onClick={() => {
                        const key = `${receipt.query_id}:${proposal.proposal_id}:${decision}`;
                        const requestId = (decisionIds.current[key] ||=
                          crypto.randomUUID());
                        void act<AssociationProposal>(
                          "materials/association-decision",
                          {
                            query_id: receipt.query_id,
                            proposal_id: proposal.proposal_id,
                            decision,
                            reason: "用户在材料查询界面审查关联建议",
                            request_id: requestId,
                          },
                          (value) =>
                            setProposals((values) =>
                              values.map((item) =>
                                item.proposal_id === value.proposal_id
                                  ? value
                                  : item,
                              ),
                            ),
                        );
                      }}
                    >
                      {title}
                    </button>
                  ))}
                </article>
              ))}
            </section>
          )}
        </main>
        <aside
          className="material-output"
          ref={outputPanel}
          aria-label="查询返回结果"
        >
          <h2>{outputTitle}</h2>
          <ResultStatus result={outputResult} />
          {busy && <p role="status">正在读取所选结果…</p>}
          <MaterialPacket packet={packet} />
          {!packet && deepening && (
            <section aria-label="深化返回材料">
              <p>
                返回 {deepening.candidates.length} 条材料、
                {deepening.edges.length} 条固定关联。
              </p>
              {deepening.candidates.map((item) => (
                <article key={item.candidate_id}>
                  <h3>{item.title}</h3>
                  <p>{item.excerpt}</p>
                  <FixedReferences refs={item.refs} />
                </article>
              ))}
              {deepening.gaps.length > 0 && (
                <ul>
                  {deepening.gaps.map((gap, i) => (
                    <li key={i}>{gap}</li>
                  ))}
                </ul>
              )}
            </section>
          )}
          {capabilities?.maintenance.task_package && (
            <MaterialMaintenance
              request={materialRequest}
              refs={stale ? [] : fixedRefs}
              scope={scope}
            />
          )}
        </aside>
      </div>
    </div>
  );
}
