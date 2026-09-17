import { useEffect, useRef, useState } from "react";
import { api, download } from "./api";
import { RetainedPanel } from "./RetainedPanel";
import { RawMaterials } from "./RawMaterials";
import { useCurrentReading } from "./CurrentReading";
import { ResearchDocument, ResearchMarkdown } from "./ResearchDocument";
import {
  MemorySearch,
  PacketView,
  parseIds,
  type Packet,
} from "./MemorySearch";
import type { MemoryRecord, Ref, Actor, Claim } from "../../schemas/memory-v4";

type Owner = {
  owner_id: string;
  owner_type: string;
  native_data: { title?: string };
};
type Head = { commit_id: string; generation: number };
type ClaimState = {
  review_state: string;
  effective_validity: boolean;
  errors: unknown[];
};
type Inspection = {
  owner: Owner;
  head: Head | null;
  records: Record<string, MemoryRecord>;
  claim_states: Record<string, ClaimState>;
  index_status: string;
  index_details: unknown;
  policy: unknown;
};
type Receipt = {
  save_status: string;
  index_status: string;
  error?: { code: string; message: string } | null;
  record_results?: { record_id: string }[];
};
type HistoryResult = {
  items: {
    id: string;
    title: string;
    kind: string;
    occurred_label: string;
    created_at: string | null;
    revision: number | null;
    record?: MemoryRecord;
    native_data?: unknown;
    goal_ref: Ref | null;
  }[];
  next_offset: number | null;
  basis_heads: Record<string, string>;
  total: number;
  missing: unknown[];
};
type Editable = Record<string, unknown> & {
  owner_id: string;
  kind: string;
  title: string;
  body_markdown: string;
  payload: Record<string, unknown>;
  sources: Ref[];
  record_reason: string;
  change_reason: string;
};
const names: Record<string, string> = {
  source: "L0 原始材料",
  detail: "L1 技术单元",
  document: "研究文稿",
  document_section: "独立章节",
  narrative: "L2 研究经过",
  experience: "L3 经验",
  overview: "L4 整体概览",
  question: "问题",
  goal: "目标",
  route: "路线",
  checkpoint: "检查点",
  association: "导航关联",
  representation: "检索表示",
  review: "结论复核",
  consolidation: "阶段巩固",
  feedback: "使用反馈",
  policy: "积累策略",
};
// 只提供一个层级入口。其他对象尚未整理的旧记录仍可在相应层级找到，
// 不因移除按钮而隐藏用户内容；实际类型更新须经服务器显式修订。
const visibleKind = (kind: string) =>
  kind === "event"
    ? "narrative"
    : kind === "map"
      ? "overview"
      : kind === "document_section"
        ? "document"
        : kind;
// Knowledge layers are the primary reading choices. Workflow objects keep
// their own semantics and remain accessible in one optional auxiliary view.
const readingKinds = [
  "source",
  "detail",
  "narrative",
  "experience",
  "overview",
  "document",
];
// The owner list is a navigation summary; complete content has one detail page.
function recordSummary(record: MemoryRecord) {
  const payload = record.payload as unknown as Record<string, unknown>;
  const description = payload.retrieval_description as
    Record<string, unknown> | undefined;
  const value =
    description?.question ||
    payload.question ||
    payload.problem_structure ||
    payload.summary ||
    payload.objective ||
    record.body_markdown ||
    record.record_reason ||
    "暂无摘要";
  const plain = (Array.isArray(value) ? value.join("；") : String(value))
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/[#*_`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return (
    [...plain].slice(0, 240).join("") + ([...plain].length > 240 ? "…" : "")
  );
}
const evidenceLink = (record: MemoryRecord) =>
  "#/evidence?" +
  new URLSearchParams({
    id: record.record_id,
    revision: String(record.revision),
    ...(record.record_hash ? { sha256: record.record_hash } : {}),
  }).toString();
const labels: Record<string, string> = {
  current_stage: "当前阶段",
  methods: "关键方法",
  open_questions: "未解决问题",
  problem_structure: "共同问题结构",
  method: "方法与假设",
  steps: "计算与推导步骤",
  results: "计算结果",
  limitations: "限制与未验证事项",
  recommendation: "建议",
  applicable: "适用条件",
  prohibited: "禁止迁移条件",
  failure_modes: "失败模式",
  retry_conditions: "可重试条件",
  action: "执行动作",
  observation: "观察结果",
  decision: "决定",
  question: "问题内容",
  decision_affected: "影响的决定",
  missing_evidence: "尚缺证据",
  objective: "目标",
  constraints: "约束",
  success_criteria: "完成标准",
  change_impact: "目标变化影响",
  topic: "主题",
  next_steps: "下一步",
  hypothesis: "假设",
  blocker: "阻碍",
  next_step: "下一步",
  reopen_condition: "重开条件",
  prerequisites: "前置条件",
  stop_reason: "停止原因",
  explanation: "关联解释",
  shared_structure: "共同结构",
  transfer_limits: "不可迁移内容",
  reason: "原因",
  note: "说明",
  status: "状态",
};
const audit = new Set([
  "record_id",
  "revision",
  "previous_revision",
  "record_hash",
  "content_hash",
  "created_at",
  "created_by",
  "updated_at",
  "updated_by",
]);
function editable(record: MemoryRecord): Editable {
  return Object.fromEntries(
    Object.entries(record).filter(([key]) => !audit.has(key)),
  ) as Editable;
}
function ref(record: MemoryRecord): Ref {
  return {
    target_kind: "record",
    target_id: record.record_id,
    revision: record.revision,
    sha256: record.record_hash,
    locator: "",
    relation: "references",
  };
}
function fresh(kind: string, owner: string): Editable {
  const payloads: Record<string, Record<string, unknown>> = {
    detail: {
      unit_type: "analysis",
      retrieval_description: {
        question: "",
        method: "",
        key_findings: [],
        applicable: [],
        not_applicable: [],
        limitations: [],
      },
      run_ref: null,
      evidence_refs: [],
      blocks: [
        {
          block_id: "analysis",
          role: "discussion",
          markdown: "",
          requires_block_ids: [],
        },
      ],
      figures: [],
      missing_refs: [],
    },
    experience: {
      knowledge_type: "observation",
      process_refs: [],
      technical_refs: [],
      problem_structure: "",
      recommendation: "",
      applicable: [""],
      prohibited: [],
      failure_modes: [],
      retry_conditions: [],
      claim_refs: [],
      claims: [],
    },
    narrative: {
      question: "",
      stages: [
        {
          situation: "",
          action: "",
          reason: "",
          outcome: "",
          evidence_refs: [],
        },
      ],
      claims: [],
      process_refs: [],
      technical_refs: [],
      experience_refs: [],
      limitations: [],
    },
    overview: {
      question: "",
      methods: [],
      results: [],
      current_stage: "",
      limitations: [],
      open_questions: [],
      claims: [],
      process_refs: [],
      technical_refs: [],
      experience_refs: [],
    },
    event: {
      occurred_at: null,
      question_refs: [],
      goal_ref: null,
      route_ref: null,
      action: "",
      observation: { value: null, reason: "unknown", note: "尚未取得结果" },
      decision: null,
      decision_refs: [],
      run_refs: [],
      failure: null,
      claims: [],
    },
    map: {
      topic: "",
      goal_refs: [],
      route_refs: [],
      result_refs: [],
      question_refs: [],
      conflict_refs: [],
      next_steps: [],
      coverage: { owner_ids: [owner], source_versions: [], missing: [] },
    },
    question: {
      question: "",
      status: "open",
      decision_affected: "",
      missing_evidence: [],
      resolution_refs: [],
      replacement_ref: null,
      reopen_reason: null,
    },
    goal: {
      objective: "",
      constraints: [],
      success_criteria: [],
      previous_goal_ref: null,
      change_impact: "初始目标",
    },
  };
  return {
    schema_version: ["narrative", "overview", "experience"].includes(kind)
      ? 4
      : kind === "detail"
        ? 3
        : 2,
    owner_id: owner,
    kind,
    title: "",
    keywords: [],
    body_markdown: "",
    payload: payloads[kind],
    sources: [],
    provenance_gap: "尚未补充固定来源，请在复用前核对",
    record_reason: "",
    change_reason: "",
    sensitivity: "internal",
    discovery: "owner_only",
  };
}

function PayloadFields({
  value,
  change,
  validity,
}: {
  value: Editable;
  change: (value: Editable) => void;
  validity: (valid: boolean) => void;
}) {
  const [jsonText, setJsonText] = useState(
    JSON.stringify(value.payload, null, 2),
  );
  const [jsonError, setJsonError] = useState("");
  useEffect(() => {
    validity(true);
  }, [validity]);
  useEffect(() => {
    setJsonText(JSON.stringify(value.payload, null, 2));
  }, [value.payload]);
  return (
    <div className="memory-fields">
      {value.kind === "experience" && value.schema_version === 4 && (
        <label>
          认识性质
          <select
            aria-label="认识性质"
            value={String(value.payload.knowledge_type)}
            onChange={(event) =>
              change({
                ...value,
                payload: {
                  ...value.payload,
                  knowledge_type: event.target.value,
                },
              })
            }
          >
            <option value="observation">观察</option>
            <option value="conclusion">结论</option>
            <option value="hypothesis">原因假设</option>
            <option value="recommendation">建议</option>
          </select>
        </label>
      )}
      {(value.schema_version === 3 || value.schema_version === 4) && (
        <label>
          结构化内容与固定关联
          <textarea
            aria-label="结构化内容"
            rows={18}
            value={jsonText}
            onChange={(event) => {
              const text = event.target.value;
              setJsonText(text);
              try {
                const payload = JSON.parse(text);
                if (
                  !payload ||
                  Array.isArray(payload) ||
                  typeof payload !== "object"
                )
                  throw new Error("内容应为 JSON 对象");
                setJsonError("");
                validity(true);
                change({ ...value, payload });
              } catch (reason) {
                setJsonError(String(reason));
                validity(false);
              }
            }}
          />
          <small>
            技术单元正文写入 blocks；实验类型必须绑定固定
            Run。文稿和章节使用固定引用。
          </small>
          {jsonError && (
            <span role="alert">
              草稿结构尚未有效解析，请修正后保存：{jsonError}
            </span>
          )}
        </label>
      )}
      {Object.entries(value.payload)
        .filter(
          ([key, field]) =>
            labels[key] &&
            (typeof field === "string" ||
              (Array.isArray(field) &&
                field.every((item) => typeof item === "string"))),
        )
        .map(([key, field]) => (
          <label key={key}>
            {labels[key]}
            <textarea
              aria-label={labels[key]}
              value={Array.isArray(field) ? field.join("\n") : String(field)}
              onChange={(event) =>
                change({
                  ...value,
                  payload: {
                    ...value.payload,
                    [key]: Array.isArray(field)
                      ? event.target.value.split("\n").filter(Boolean)
                      : event.target.value,
                  },
                })
              }
            />
            {Array.isArray(field) && (
              <small>每行一项，保留适用与禁止条件。</small>
            )}
          </label>
        ))}
    </div>
  );
}

export function Memory() {
  const sharedReading = useCurrentReading();
  const ownerChosen = useRef(false);
  const [owners, setOwners] = useState<Owner[]>([]);
  const [ownerId, setOwnerId] = useState("");
  const [snapshot, setSnapshot] = useState<Inspection | null>(null);
  const [tab, setTab] = useState("history");
  const [timeline, setTimeline] = useState<HistoryResult | null>(null);
  // 显式选择每种类型，多选取并集；空选择表示不显示任何记录。
  const [kinds, setKinds] = useState<string[]>(() => [...readingKinds]);
  const [showAuxiliary, setShowAuxiliary] = useState(false);
  const [rawCount, setRawCount] = useState(0);
  const [selected, setSelected] = useState<MemoryRecord | null>(null);
  const [draft, setDraft] = useState<Editable | null>(null);
  const [draftTab, setDraftTab] = useState("records");
  const [payloadValid, setPayloadValid] = useState(true);
  const [editingHead, setEditingHead] = useState<string | null>(null);
  const [conflict, setConflict] = useState<MemoryRecord | null>(null);
  const [historyRevision, setHistoryRevision] = useState(1);
  const [message, setMessage] = useState("");
  const [details, setDetails] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [actor, setActor] = useState<Actor>({
    kind: "human",
    id: "workbench-user",
  });
  // 各功能独立保留材料包，避免总结覆盖续接结果。
  const [packets, setPackets] = useState<Record<string, Packet | null>>({});
  const packet = packets[tab] || null;
  const setPacket = (value: Packet | null) =>
    setPackets((current) => ({ ...current, [tab]: value }));
  const [summaryOwners, setSummaryOwners] = useState<string[]>([]);
  const [summaryQuery, setSummaryQuery] = useState("");
  const [summaryBasis, setSummaryBasis] = useState<Record<
    string,
    string
  > | null>(null);
  const [reviewClaim, setReviewClaim] = useState<Claim | null>(null);
  const [reviewState, setReviewState] = useState("accepted");
  const [reviewScope, setReviewScope] = useState("");
  const [reviewReason, setReviewReason] = useState("");
  const [associationSeeds, setAssociationSeeds] = useState("");
  const [associations, setAssociations] = useState<
    { from: Ref; to: Ref; score: number; shared?: string[] }[]
  >([]);
  const [association, setAssociation] = useState<{ from: Ref; to: Ref } | null>(
    null,
  );
  const [sharedStructure, setSharedStructure] = useState("");
  const [transferLimits, setTransferLimits] = useState("");
  const [pendingSelection, setPendingSelection] = useState<{
    owner: string;
    record: string;
  } | null>(null);
  const [recordsLoaded, setRecordsLoaded] = useState(false);
  const inspectionSequence = useRef(0);
  async function load(id = ownerId) {
    if (!id) return;
    const sequence = ++inspectionSequence.current;
    const next = await api<Inspection>("memory/inspect", { owner_id: id });
    // Rapid owner changes can finish out of order; an older response must not
    // display another owner's records under the current selection.
    if (sequence === inspectionSequence.current) {
      setSnapshot(next);
      setRecordsLoaded(true);
    }
    return next;
  }
  useEffect(() => {
    setSnapshot(null);
    api<{ owners: Owner[] }>("memory/list-owners")
      .then((value) => {
        setOwners(value.owners);
        const requested =
          new URLSearchParams(location.hash.split("?")[1]).get("owner") ||
          sharedReading?.reading?.owner_id;
        if (value.owners.length)
          setOwnerId(
            (current) =>
              current ||
              (value.owners.some((o) => o.owner_id === requested)
                ? requested!
                : value.owners[0].owner_id),
          );
      })
      .catch((error) => setMessage(String(error)));
  }, []);
  useEffect(() => {
    // 首页主题链接与检索结果共用同一个待定位选择，不另建记录状态。
    const navigate = () => {
      if (!location.hash.startsWith("#/memory?")) return;
      const params = new URLSearchParams(location.hash.split("?")[1]);
      if (params.get("tab") === "reading") {
        location.hash = "#/home";
        return;
      }
      const owner = params.get("owner");
      if (!owner) return;
      ownerChosen.current = true;
      setOwnerId(owner);
      const record = params.get("record");
      setTab(record ? "records" : "history");
      if (record) setPendingSelection({ owner, record });
    };
    navigate();
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  useEffect(() => {
    const owner = sharedReading?.reading?.owner_id;
    if (
      !ownerChosen.current &&
      owner &&
      owners.some((item) => item.owner_id === owner)
    )
      setOwnerId(owner);
  }, [sharedReading?.reading?.owner_id, owners]);
  useEffect(() => {
    if (pendingSelection?.owner !== ownerId) setPendingSelection(null);
    setSnapshot(null);
    setSelected(null);
    setDraft(null);
    setConflict(null);
    setPackets({});
    setTimeline(null);
    setDetails(null);
    // 切换对象使旧读取失效；对象记录只在用户点击生成后读取。
    inspectionSequence.current++;
    setRecordsLoaded(false);
    setAssociations([]);
    setAssociation(null);
    setReviewClaim(null);
    setReviewScope("");
    setReviewReason("");
    setSharedStructure("");
    setTransferLimits("");
    setAssociationSeeds("");
  }, [ownerId]);
  useEffect(() => {
    if (!pendingSelection || pendingSelection.owner !== ownerId) return;
    let cancelled = false;
    // 先应用归属切换/清理，再读取点击的固定候选；离开该归属时拒绝迟到结果。
    load(pendingSelection.owner)
      .then((value) => {
        if (!cancelled && value)
          setSelected(value.records[pendingSelection.record] || null);
      })
      .catch((error) => {
        if (!cancelled) setMessage(String(error));
      });
    return () => {
      cancelled = true;
      inspectionSequence.current++;
    };
  }, [ownerId, pendingSelection]);
  async function run(work: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    setDetails(null);
    try {
      await work();
    } catch (error) {
      setMessage(String(error));
      setDetails((error as { errors?: unknown }).errors);
    } finally {
      setBusy(false);
    }
  }
  function begin(record?: MemoryRecord, type = "experience") {
    setDraftTab("records");
    setSelected(record || null);
    const value = record ? editable(record) : fresh(type, ownerId);
    if (record?.kind === "goal") value.payload.previous_goal_ref = ref(record);
    setDraft(value);
    setEditingHead(snapshot?.head?.commit_id || null);
    setConflict(null);
    setSummaryBasis(null);
  }
  function receiptText(receipt: Receipt) {
    return receipt.save_status === "no_change"
      ? "内容无变化，未生成新修订。"
      : receipt.index_status === "indexed"
        ? "记录已保存，索引已更新。"
        : "记录已保存，索引待更新。可使用补偿操作。";
  }
  async function showSaved(receipt: Receipt) {
    // HEAD has already been published. A separate inspection failure must
    // preserve that receipt so the user does not repeat a successful write.
    setMessage(receiptText(receipt));
    setDetails(receipt);
    try {
      await load();
    } catch (error) {
      setMessage(`${receiptText(receipt)} 页面刷新失败：${String(error)}`);
    }
  }
  async function save(preview: boolean) {
    if (!draft) return;
    await run(async () => {
      const operation = {
        op: "put_record",
        draft,
        ...(selected
          ? {
              record_id: selected.record_id,
              expected_revision: selected.revision,
            }
          : { client_key: "edited" }),
      };
      try {
        const value =
          summaryBasis && !preview
            ? await api<Receipt>("memory/summaries-save", {
                request_id: crypto.randomUUID(),
                actor,
                owner_id: ownerId,
                expected_head: editingHead,
                draft,
                basis_heads: summaryBasis,
              })
            : await api<Receipt>(
                `memory/${preview ? "validate-draft" : "commit"}`,
                {
                  schema_version: 1,
                  request_id: crypto.randomUUID(),
                  actor,
                  owner_id: ownerId,
                  expected_head: editingHead,
                  operations: [operation],
                },
              );
        if (preview) {
          setMessage("预检通过，尚未保存。");
          setDetails(value);
        } else {
          setDraft(null);
          setSummaryBasis(null);
          await showSaved(value);
        }
      } catch (error) {
        if (
          ["VERSION_CONFLICT", "STALE_BASIS"].includes(
            (error as { code?: string }).code || "",
          )
        ) {
          const current = await load();
          if (selected)
            setConflict(current?.records[selected.record_id] || null);
          setMessage("版本冲突，草稿已保留。请对照当前版本重新编辑。");
          setDetails(error);
        } else throw error;
      }
    });
  }
  const records = Object.values(snapshot?.records || {});
  // 展示与导出共用集合，防止清空筛选后意外导出全部对象记录。
  const filteredRecords = records.filter(
    (record) =>
      record.kind !== "source" &&
      (kinds.includes(visibleKind(record.kind)) ||
        (showAuxiliary && !readingKinds.includes(visibleKind(record.kind)))),
  );
  const includesRaw = kinds.includes("source");
  const tabs = [
    ["history", "研究经过"],
    ["records", "对象记忆"],
    ["relations", "关联导航"],
    ["search", "跨研究检索"],
    ["summary", "跨项目总结"],
    ["resume", "暂停与续接"],
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">来源 · 技术 · 经过 · 经验 · 概览</p>
          <h1>系统记忆</h1>
          <p className="muted">记录依据、失败与边界，在固定版本上继续研究。</p>
        </div>
      </div>
      <section className="card">
        <div className="memory-fields">
          <label>
            归属对象（项目 / 研究 / 算法）
            <select
              aria-label="记忆归属对象"
              value={ownerId}
              disabled={busy}
              onChange={(event) => {
                ownerChosen.current = true;
                setOwnerId(event.target.value);
              }}
            >
              <option value="">选择归属对象</option>
              {owners.map((owner) => (
                <option key={owner.owner_id} value={owner.owner_id}>
                  {owner.native_data?.title || owner.owner_id} ·{" "}
                  {owner.owner_id} · {owner.owner_type}
                </option>
              ))}
            </select>
          </label>
          <label>
            执行者
            <input
              aria-label="记忆执行者"
              value={actor.id}
              onChange={(event) =>
                setActor({ ...actor, id: event.target.value })
              }
            />
          </label>
          <label>
            执行者类型
            <select
              aria-label="记忆执行者类型"
              value={actor.kind}
              onChange={(event) =>
                setActor({
                  ...actor,
                  kind: event.target.value as Actor["kind"],
                })
              }
            >
              <option value="human">用户</option>
              <option value="ai">AI</option>
              <option value="workflow">授权工作流</option>
            </select>
          </label>
        </div>
        <div className="row memory-tabs">
          {tabs.map(([id, title]) => (
            <button
              key={id}
              className={tab === id ? "primary" : ""}
              onClick={() => {
                setTab(id);
              }}
            >
              {title}
            </button>
          ))}
        </div>
        {snapshot && (
          <div className="row">
            <span>
              索引：{snapshot.index_status === "indexed" ? "已更新" : "待更新"}
            </span>
            <button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const result = await api("memory/reconcile", {
                    owner_id: ownerId,
                  });
                  setDetails(result);
                  await load();
                  setMessage("已执行索引补偿，请查看当前状态。");
                })
              }
            >
              补偿索引
            </button>
            <details>
              <summary>索引与策略详情</summary>
              <pre>
                {JSON.stringify(
                  { index: snapshot.index_details, policy: snapshot.policy },
                  null,
                  2,
                )}
              </pre>
            </details>
          </div>
        )}
      </section>
      {message && (
        <div className="alert" role="status">
          {message}
        </div>
      )}
      {details != null && (
        <details className="card" open>
          <summary>本次操作详情</summary>
          <pre>{JSON.stringify(details, null, 2)}</pre>
        </details>
      )}
      <RetainedPanel key={"records:" + ownerId} active={tab === "records"}>
        <>
          <section className="card">
            <div className="row spread">
              <h2>对象记录</h2>
              <button
                disabled={!ownerId || busy}
                onClick={() =>
                  run(async () => {
                    await load();
                  })
                }
              >
                生成对象记忆
              </button>
            </div>
            <fieldset className="memory-type-filters">
              <legend>按层级或类型筛选</legend>
              <div className="row">
                <button
                  type="button"
                  onClick={() => setKinds([...readingKinds])}
                >
                  全选类型
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setKinds([]);
                    setShowAuxiliary(false);
                  }}
                >
                  清空类型
                </button>
              </div>
              <div className="memory-type-options">
                {readingKinds.map((key) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      value={key}
                      checked={kinds.includes(key)}
                      onChange={(event) =>
                        setKinds((current) =>
                          event.target.checked
                            ? [...current, key]
                            : current.filter((value) => value !== key),
                        )
                      }
                    />
                    {names[key]}
                  </label>
                ))}
              </div>
            </fieldset>
            <details>
              <summary>辅助工作流记录</summary>
              <p className="muted">
                目标、问题、检查点、复核、策略等用于工作管理，不是知识层级；历史内容仍可查看和导出。研究章节合并到研究文稿筛选。
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={showAuxiliary}
                  onChange={(event) => setShowAuxiliary(event.target.checked)}
                />
                显示辅助工作流记录
              </label>
            </details>
            <div className="row">
              {["detail", "narrative", "experience", "overview"].map((type) => (
                <button
                  key={type}
                  disabled={!ownerId || busy || !recordsLoaded}
                  onClick={() => begin(undefined, type)}
                >
                  新增{names[type]}
                </button>
              ))}
            </div>
            {!records.length && !includesRaw && (
              <p className="muted">
                此对象尚无独立记忆记录。既有 Run 的经过可在研究经过中查看。
              </p>
            )}
            {!!records.length && !filteredRecords.length && !includesRaw && (
              <p className="muted">当前筛选没有记录，请勾选需要显示的类型。</p>
            )}
            <div className="memory-list">
              {filteredRecords.map((record) => (
                <article className="proposal" key={record.record_id}>
                  <div className="row spread">
                    <h3>
                      <a href={evidenceLink(record)}>{record.title}</a>
                    </h3>
                    <span className="badge">
                      {names[record.kind] ||
                        names[visibleKind(record.kind)] ||
                        record.kind}
                    </span>
                  </div>
                  <p>{recordSummary(record)}</p>
                  <a href={evidenceLink(record)}>查看完整内容与依据</a>
                  <details>
                    <summary>管理记录</summary>
                    <div className="row">
                      <button
                        onClick={() => {
                          setSelected(record);
                          setHistoryRevision(record.revision);
                          setDraft(null);
                        }}
                      >
                        查看历史版本
                      </button>
                      {record.kind !== "review" && (
                        <button onClick={() => begin(record)}>编辑记录</button>
                      )}
                    </div>
                    {(record.kind === "event" ||
                      record.kind === "narrative" ||
                      record.kind === "overview" ||
                      record.kind === "experience") &&
                      record.payload.claims.map((claim) => (
                        <div className="memory-claim" key={claim.claim_id}>
                          <p>{claim.statement}</p>
                          <p className="id">{claim.claim_id}</p>
                          <p>
                            复核：
                            {snapshot?.claim_states[claim.claim_id]
                              ?.review_state || "not-reviewed"}{" "}
                            · 当前依据
                            {snapshot?.claim_states[claim.claim_id]
                              ?.effective_validity
                              ? "有效"
                              : "需核对"}
                          </p>
                          <button
                            onClick={() => {
                              setReviewClaim(claim);
                              setReviewScope(claim.scope);
                            }}
                          >
                            复核此结论
                          </button>
                        </div>
                      ))}
                  </details>
                </article>
              ))}
            </div>
            {ownerId && recordsLoaded && includesRaw && (
              <RawMaterials
                key={ownerId}
                ownerId={ownerId}
                onCount={setRawCount}
              />
            )}
            <div className="row">
              {["markdown", "json", "html"].map((format) => (
                <button
                  key={format}
                  disabled={
                    (!filteredRecords.length && !(includesRaw && rawCount)) ||
                    busy
                  }
                  onClick={() =>
                    run(async () => {
                      const value = await api<{
                        filename: string;
                        content: string;
                      }>("memory/export", {
                        owner_id: ownerId,
                        include_raw_materials: includesRaw,
                        record_ids: filteredRecords.map(
                          (record) => record.record_id,
                        ),
                        format,
                      });
                      download(value.filename, value.content);
                    })
                  }
                >
                  导出 {format}
                </button>
              ))}
            </div>
          </section>
          {selected && !draft && (
            <section className="card">
              <h2>固定历史版本</h2>
              <label>
                修订号
                <input
                  type="number"
                  min="1"
                  value={historyRevision}
                  onChange={(event) =>
                    setHistoryRevision(Number(event.target.value))
                  }
                />
              </label>
              <button
                onClick={() =>
                  run(async () => {
                    setDetails(
                      await api("memory/inspect", {
                        owner_id: ownerId,
                        record_id: selected.record_id,
                        revision: historyRevision,
                      }),
                    );
                  })
                }
              >
                读取此修订
              </button>
            </section>
          )}
        </>
      </RetainedPanel>
      {draft && (
        <section className="card memory-editor" hidden={tab !== draftTab}>
          <h2>
            {selected ? "编辑记录" : "新记录"} ·{" "}
            {names[visibleKind(draft.kind)]}
          </h2>
          <label>
            标题
            <input
              aria-label="记忆标题"
              value={draft.title}
              onChange={(event) =>
                setDraft({ ...draft, title: event.target.value })
              }
            />
          </label>
          {!(draft.schema_version === 3 && draft.kind === "detail") && (
            <label>
              正文
              <textarea
                aria-label="记忆正文"
                rows={6}
                value={draft.body_markdown}
                onChange={(event) =>
                  setDraft({ ...draft, body_markdown: event.target.value })
                }
              />
            </label>
          )}
          <PayloadFields
            key={selected?.record_id || draft.kind}
            value={draft}
            change={setDraft}
            validity={setPayloadValid}
          />
          <label>
            保存或变更原因
            <input
              aria-label="记忆保存原因"
              value={draft.change_reason || draft.record_reason}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  record_reason: selected
                    ? draft.record_reason
                    : event.target.value,
                  change_reason: event.target.value,
                })
              }
            />
          </label>
          <label>
            依据缺口
            <input
              value={String(draft.provenance_gap || "")}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  provenance_gap: event.target.value || null,
                })
              }
            />
          </label>
          <label>
            关联已保存来源
            <select
              aria-label="添加记忆来源"
              value=""
              onChange={(event) => {
                const record = snapshot?.records[event.target.value];
                if (record)
                  setDraft({
                    ...draft,
                    sources: [...draft.sources, ref(record)],
                    provenance_gap: null,
                  });
              }}
            >
              <option value="">选择固定记录版本</option>
              {records
                .filter((record) => record.record_id !== selected?.record_id)
                .map((record) => (
                  <option value={record.record_id} key={record.record_id}>
                    {record.title} · r{record.revision}
                  </option>
                ))}
            </select>
          </label>
          <details>
            <summary>本次固定来源</summary>
            <pre>{JSON.stringify(draft.sources, null, 2)}</pre>
          </details>
          {conflict && (
            <div className="risk" role="alert">
              <h3>当前版本 r{conflict.revision}，你的草稿仍保留</h3>
              <p>当前标题：{conflict.title}</p>
              <pre>{conflict.body_markdown}</pre>
              <button
                onClick={() => {
                  setSelected(conflict);
                  setEditingHead(snapshot?.head?.commit_id || null);
                  setConflict(null);
                  setMessage("已选择当前版本作为比较基础，请检查草稿后预检。");
                }}
              >
                以当前版本重新预检草稿
              </button>
            </div>
          )}
          <div className="row">
            <button disabled={busy || !payloadValid} onClick={() => save(true)}>
              预检草稿
            </button>
            <button
              className="primary"
              disabled={busy || !payloadValid}
              onClick={() => save(false)}
            >
              保存记忆
            </button>
            <button
              onClick={() => {
                setDraft(null);
                setSummaryBasis(null);
              }}
            >
              关闭编辑
            </button>
          </div>
        </section>
      )}
      {reviewClaim && (
        <section className="card" hidden={tab !== "records"}>
          <h2>结论复核 · {reviewClaim.claim_id}</h2>
          <p>{reviewClaim.statement}</p>
          <label>
            复核状态
            <select
              aria-label="复核状态"
              value={reviewState}
              onChange={(event) => setReviewState(event.target.value)}
            >
              {["accepted", "disputed", "retracted", "not-reviewed"].map(
                (value) => (
                  <option key={value}>{value}</option>
                ),
              )}
            </select>
          </label>
          <label>
            复核范围
            <input
              aria-label="记忆复核范围"
              value={reviewScope}
              onChange={(event) => setReviewScope(event.target.value)}
            />
          </label>
          <label>
            复核原因
            <input
              aria-label="记忆复核原因"
              value={reviewReason}
              onChange={(event) => setReviewReason(event.target.value)}
            />
          </label>
          <button
            disabled={busy}
            onClick={() =>
              run(async () => {
                const value = await api<Receipt>("memory/review", {
                  schema_version: 1,
                  request_id: crypto.randomUUID(),
                  owner_id: ownerId,
                  expected_head: snapshot?.head?.commit_id || null,
                  actor,
                  target_claim_id: reviewClaim.claim_id,
                  state: reviewState,
                  scope: reviewScope || null,
                  reason: reviewReason,
                  evidence_refs: reviewClaim.evidence_refs,
                });
                await showSaved(value);
              })
            }
          >
            提交复核
          </button>
          <button onClick={() => setReviewClaim(null)}>关闭复核</button>
        </section>
      )}
      <RetainedPanel key={"search:" + ownerId} active={tab === "search"}>
        <MemorySearch
          ownerId={ownerId}
          open={(owner, record) => {
            ownerChosen.current = true;
            setOwnerId(owner);
            setTab("records");
            setPendingSelection({ owner, record });
          }}
        />
      </RetainedPanel>
      <RetainedPanel key={"history:" + ownerId} active={tab === "history"}>
        <section className="card">
          <ResearchDocument ownerId={ownerId} />
          <details className="research-archive">
            <summary>原始追溯与旧版本</summary>
            <p>按需读取原始记录、既有 Run 与旧修订，保留当时目标和未知时间。</p>
            <button
              disabled={busy}
              onClick={() =>
                run(async () =>
                  setTimeline(
                    await api<HistoryResult>("memory/history", {
                      owner_id: ownerId,
                    }),
                  ),
                )
              }
            >
              读取原始追溯与旧版本
            </button>
            {timeline && (
              <>
                <p>
                  共 {timeline.total} 项，已显示 {timeline.items.length} 项。
                </p>
                {timeline.items.map((item) => (
                  <article className="proposal" key={item.id}>
                    <h3>{item.title}</h3>
                    <p>
                      {names[visibleKind(item.kind)] || "既有 Run"} ·{" "}
                      {item.occurred_label}
                    </p>
                    <p className="id">
                      {item.id} · 保存于 {item.created_at || "未知"}
                    </p>
                    {item.goal_ref && (
                      <p>
                        当时目标：{item.goal_ref.target_id} · r
                        {item.goal_ref.revision}
                      </p>
                    )}
                    <ResearchMarkdown
                      text={
                        item.record?.body_markdown ||
                        "既有 Run 元数据见下方固定来源；详细计算请阅读关联 L1 记录。"
                      }
                    />
                    <details>
                      <summary>当时内容与固定来源</summary>
                      <pre>
                        {JSON.stringify(
                          item.record || item.native_data,
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  </article>
                ))}
                {timeline.next_offset !== null && (
                  <button
                    onClick={() =>
                      run(async () => {
                        const next = await api<HistoryResult>(
                          "memory/history",
                          {
                            owner_id: ownerId,
                            offset: timeline.next_offset,
                            basis_heads: timeline.basis_heads,
                          },
                        );
                        setTimeline({
                          ...next,
                          items: [...timeline.items, ...next.items],
                        });
                      })
                    }
                  >
                    读取下一页经过
                  </button>
                )}
                <details>
                  <summary>历史覆盖缺口</summary>
                  <pre>{JSON.stringify(timeline.missing, null, 2)}</pre>
                </details>
              </>
            )}
          </details>
        </section>
      </RetainedPanel>
      {tab === "resume" && (
        <>
          <section className="card">
            <h2>从保存的断点继续</h2>
            <p>
              重验当前目标、检查点、未决问题和来源变化。只生成建议，不自动启动研究。
            </p>
            <button
              disabled={busy}
              onClick={() =>
                run(async () =>
                  setPacket(
                    await api<Packet>("memory/resume", {
                      owner_id: ownerId,
                      budget: 16000,
                    }),
                  ),
                )
              }
            >
              生成续接内容
            </button>
            <button
              disabled={busy}
              onClick={() =>
                run(async () =>
                  setDetails(
                    await api("memory/prepare", {
                      owner_id: ownerId,
                      trigger: "阶段暂停",
                    }),
                  ),
                )
              }
            >
              查看巩固待办
            </button>
          </section>
          {packet && <PacketView packet={packet} />}
        </>
      )}
      {tab === "summary" && (
        <>
          <section className="card">
            <h2>跨项目总结</h2>
            <label>
              总结问题
              <input
                value={summaryQuery}
                onChange={(event) => setSummaryQuery(event.target.value)}
              />
            </label>
            <div className="memory-choices">
              {owners.map((owner) => (
                <label key={owner.owner_id}>
                  <input
                    type="checkbox"
                    checked={summaryOwners.includes(owner.owner_id)}
                    onChange={(event) =>
                      setSummaryOwners(
                        event.target.checked
                          ? [...summaryOwners, owner.owner_id]
                          : summaryOwners.filter((id) => id !== owner.owner_id),
                      )
                    }
                  />
                  {owner.native_data?.title || owner.owner_id} ·{" "}
                  {owner.owner_id}
                </label>
              ))}
            </div>
            <button
              disabled={busy || !summaryOwners.length || !summaryQuery}
              onClick={() =>
                run(async () =>
                  setPacket(
                    await api<Packet>("memory/summaries-prepare", {
                      query: summaryQuery,
                      owners: summaryOwners,
                      budget: 16000,
                    }),
                  ),
                )
              }
            >
              准备总结材料包
            </button>
            {packet && (
              <div className="row">
                {["experience", "overview"].map((type) => (
                  <button
                    key={type}
                    // 新材料包准备期间保留旧正文，但禁止以旧依据开始新草稿。
                    disabled={busy}
                    onClick={() => {
                      const value = fresh(type, ownerId);
                      value.title = summaryQuery;
                      value.sources =
                        packet.source_refs ||
                        (packet.manifest.source_refs as Ref[]) ||
                        [];
                      value.provenance_gap = value.sources.length
                        ? null
                        : "材料包尚缺固定来源";
                      setDraftTab("summary");
                      setDraft(value);
                      setSelected(null);
                      setEditingHead(snapshot?.head?.commit_id || null);
                      setSummaryBasis(
                        packet.basis_heads ||
                          (packet.manifest.basis_heads as Record<
                            string,
                            string
                          >),
                      );
                    }}
                  >
                    回填 {names[type]}
                  </button>
                ))}
              </div>
            )}
          </section>
          {packet && <PacketView packet={packet} />}
        </>
      )}
      {tab === "relations" && (
        <section className="card">
          <h2>导航关联</h2>
          <p>共同结构和相似度只用于发现线索，保留不可迁移内容。</p>
          <label>
            作为起点的记录 ID
            <input
              value={associationSeeds}
              onChange={(event) => setAssociationSeeds(event.target.value)}
              placeholder="空格分隔"
            />
          </label>
          <button
            disabled={busy}
            onClick={() =>
              run(async () => {
                // 关联提交需要当前 HEAD；只在用户主动查询关联时装载。
                await load();
                const value = await api<{ candidates: typeof associations }>(
                  "memory/associations-propose",
                  {
                    owner_id: ownerId,
                    seeds: parseIds(associationSeeds),
                    method: "keyword",
                  },
                );
                setAssociations(value.candidates);
                setMessage(
                  value.candidates.length
                    ? `找到 ${value.candidates.length} 个关联候选，请核对两端内容和适用边界。`
                    : "未找到满足共有关键词条件的候选。请核对起点及记录关键词；没有候选不表示研究之间没有联系。",
                );
              })
            }
          >
            查找相关候选
          </button>
          {associations.map((value) => (
            <article
              className="proposal"
              key={value.from.target_id + value.to.target_id}
            >
              <p>
                {value.from.target_id} → {value.to.target_id}
              </p>
              <p>
                共有词：{value.shared?.join("、")} · 相似度{" "}
                {value.score.toFixed(3)}
              </p>
              <button
                onClick={() =>
                  setAssociation({ from: value.from, to: value.to })
                }
              >
                解释并处理关联
              </button>
            </article>
          ))}
          {association && (
            <>
              <label>
                共同问题结构
                <textarea
                  value={sharedStructure}
                  onChange={(event) => setSharedStructure(event.target.value)}
                />
              </label>
              <label>
                不可迁移内容
                <textarea
                  value={transferLimits}
                  onChange={(event) => setTransferLimits(event.target.value)}
                />
              </label>
              <div className="row">
                {[
                  ["accepted", "采纳导航关联"],
                  ["rejected", "拒绝关联"],
                  ["withdrawn", "撤销关联"],
                ].map(([status, title]) => (
                  <button
                    key={status}
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const value = await api<Receipt>(
                          "memory/associations-decide",
                          {
                            request_id: crypto.randomUUID(),
                            owner_id: ownerId,
                            expected_head: snapshot?.head?.commit_id || null,
                            actor,
                            reason: sharedStructure,
                            payload: {
                              ...association,
                              relation: "analogous_to",
                              explanation: sharedStructure,
                              shared_structure: sharedStructure,
                              transfer_limits: transferLimits
                                .split("\n")
                                .filter(Boolean),
                              basis_refs: [association.from, association.to],
                              status,
                            },
                          },
                        );
                        await showSaved(value);
                      })
                    }
                  >
                    {title}
                  </button>
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </>
  );
}
