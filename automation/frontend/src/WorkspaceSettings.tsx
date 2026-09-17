import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import "./workspace-settings.css";
import type { Budget } from "./generated/material-query";

export type WorkspaceSettingsValue = {
  collaboration: { subagents: "auto" | "off"; subagent_requirements: string };
  materials: { result_limit: number; budget: Budget };
  reading: {
    strategy: "standard" | "associative" | "quick";
    association: { enabled: boolean; max_rounds: number };
    context: { max_owners: number; note_max_tokens: number };
    result_limit: number;
    reranking: { mode: "off" | "auto" | "required"; candidate_limit: number };
    budget: Budget;
  };
};
export type SettingsReceipt = {
  revision: string;
  settings: WorkspaceSettingsValue;
  defaults: WorkspaceSettingsValue;
  limits: Budget;
};
type Draft = Record<string, string>;
type BudgetField = {
  key: keyof Budget;
  title: string;
  scale?: number;
  advanced?: boolean;
};
const fields: BudgetField[] = [
  { key: "read_bytes", title: "读取量（MiB）", scale: 1024 * 1024 },
  { key: "output_chars", title: "输出字符上限" },
  { key: "wall_ms", title: "活动超时（秒）", scale: 1000 },
  { key: "candidates", title: "累计候选预算" },
  { key: "model_tokens", title: "模型总 token" },
  { key: "model_calls", title: "模型调用次数" },
  { key: "rerank_items", title: "重排条数" },
  { key: "model_input_tokens", title: "模型输入 token", advanced: true },
  { key: "model_output_tokens", title: "模型输出 token", advanced: true },
  { key: "graph_nodes", title: "图节点数", advanced: true },
  { key: "graph_edges", title: "图边数", advanced: true },
  { key: "graph_hops", title: "图深度", advanced: true },
];

function toDraft(value: WorkspaceSettingsValue): Draft {
  const out: Draft = {
    subagents: value.collaboration.subagents,
    subagent_requirements: value.collaboration.subagent_requirements,
    mode: value.reading.reranking.mode,
    strategy: value.reading.strategy ?? "standard",
    association_enabled: String(value.reading.association?.enabled ?? true),
    association_rounds: String(value.reading.association?.max_rounds ?? 3),
    candidate_limit: String(value.reading.reranking.candidate_limit),
    max_owners: String(value.reading.context.max_owners),
    note_max_tokens: String(value.reading.context.note_max_tokens),
  };
  for (const group of ["materials", "reading"] as const) {
    out[group + ".result_limit"] = String(value[group].result_limit);
    for (const field of fields)
      out[group + "." + field.key] = String(
        (value[group].budget[field.key] ?? 0) / (field.scale ?? 1),
      );
  }
  return out;
}

// 草稿保留字符串，空值/小数/Infinity不会因Number('')或浏览器number输入被悄悄改成0。
function integer(
  draft: Draft,
  key: string,
  title: string,
  maximum: number,
  minimum = 0,
  scale = 1,
): number {
  const raw = draft[key];
  const syntax = scale === 1 ? /^\d+$/ : /^\d+(?:\.\d+)?$/;
  if (!syntax.test(raw) || raw.length > 100)
    throw new Error(`${title}须为有效数字，换算后的预算须为有限整数。`);
  // 十进制按整数分子/分母换算，避免1.001秒在浮点运算下误判为1000.999…ms。
  const [whole, fraction = ""] = raw.split(".");
  const numerator = BigInt(whole + fraction) * BigInt(scale);
  const denominator = 10n ** BigInt(fraction.length);
  const value = Number(numerator / denominator);
  if (
    numerator % denominator !== 0n ||
    !Number.isSafeInteger(value) ||
    value < minimum ||
    value > maximum
  )
    throw new Error(`${title}换算后须为${minimum}到${maximum}之间的整数预算。`);
  return value;
}

function fromDraft(
  draft: Draft,
  receipt: SettingsReceipt,
): WorkspaceSettingsValue {
  const value = structuredClone(receipt.settings);
  value.collaboration.subagents = draft.subagents as "auto" | "off";
  // 与后端按 Unicode 字符计数一致；只用 trim 校验，保存时保留用户原文。
  const requirements = draft.subagent_requirements;
  const requirementLength = [...requirements.trim()].length;
  if (requirementLength < 1 || requirementLength > 2000)
    throw new Error("子 agent 能力要求去除首尾空白后须为1到2000个字符。");
  value.collaboration.subagent_requirements = requirements;
  value.reading.strategy =
    draft.strategy as WorkspaceSettingsValue["reading"]["strategy"];
  value.reading.association = {
    enabled: draft.association_enabled === "true",
    max_rounds: integer(draft, "association_rounds", "最多联想轮次", 20, 1),
  };
  value.reading.context = {
    max_owners: integer(draft, "max_owners", "最多Owner数", 100, 1),
    note_max_tokens: integer(
      draft,
      "note_max_tokens",
      "最终note估算token",
      50000,
      512,
    ),
  };
  value.reading.reranking.mode = draft.mode as "off" | "auto" | "required";
  for (const group of ["materials", "reading"] as const) {
    // 两类预算分别编辑；即使调用方复用了同一个默认对象，也不能互相覆盖。
    value[group].budget = { ...value[group].budget };
    const title = group === "materials" ? "材料查询" : "AI阅读";
    value[group].result_limit = integer(
      draft,
      group + ".result_limit",
      title + "结果数",
      100,
      1,
    );
    for (const field of fields) {
      const scale = field.scale ?? 1;
      const maximum = receipt.limits[field.key] ?? 0;
      value[group].budget[field.key] = integer(
        draft,
        group + "." + field.key,
        title + field.title,
        maximum,
        field.key === "wall_ms" ? 1 : 0,
        scale,
      );
    }
  }
  value.reading.reranking.candidate_limit = integer(
    draft,
    "candidate_limit",
    "重排候选池",
    100,
    1,
  );
  if (
    value.reading.reranking.mode !== "off" &&
    value.reading.reranking.candidate_limit < value.reading.result_limit
  )
    throw new Error("重排候选池不能小于AI阅读结果数。");
  return value;
}

export function WorkspaceSettings({ active = true }: { active?: boolean }) {
  const [receipt, setReceipt] = useState<SettingsReceipt | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  // 同步锁覆盖两次点击落在React重渲染前的间隙；不让并发保存覆盖版本。
  const pending = useRef(false);
  const loaded = useRef(false);
  async function load(keepDraft = false) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      const next = await api<SettingsReceipt>("settings");
      setReceipt(next);
      if (!keepDraft) setDraft(toDraft(next.settings));
      setMessage(
        keepDraft
          ? "已读取最新配置，草稿保留。请核对服务端当前值，再决定保存。"
          : "",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    if (active && !loaded.current) {
      loaded.current = true;
      void load();
    }
  }, [active]);
  async function save() {
    if (pending.current || !receipt) return;
    setError("");
    setMessage("");
    let settings: WorkspaceSettingsValue;
    try {
      settings = fromDraft(draft, receipt);
    } catch (e) {
      setError(String(e));
      return;
    }
    pending.current = true;
    setBusy(true);
    try {
      const next = await api<SettingsReceipt>("settings", {
        expected_revision: receipt.revision,
        settings,
      });
      setReceipt(next);
      setDraft(toDraft(next.settings));
      setMessage(
        "设置已保存。新查询和新阅读会话使用这些默认值，已有会话保留原预算。",
      );
    } catch (e) {
      // 冲突与网络错误保留输入和旧revision；不得把失败当成功或自行覆盖新版。
      setError(
        String(e) +
          " 草稿已保留；如配置已被其他窗口修改，请读取最新配置后核对。",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  const update = (key: string, value: string) => {
    setDraft((old) => ({ ...old, [key]: value }));
    setMessage("");
  };
  const numberInput = (
    key: string,
    title: string,
    maximum: number,
    minimum = 0,
    scaled = false,
  ) => (
    <label key={key} className="field">
      {title}
      <input
        type="text"
        inputMode={scaled ? "decimal" : "numeric"}
        aria-label={title}
        value={draft[key] ?? ""}
        onChange={(event) => update(key, event.target.value)}
        disabled={busy}
      />
      <small className="muted">
        {scaled ? "换算后须为整数字节或毫秒" : "整数"}，{minimum}–{maximum}
      </small>
    </label>
  );
  const dirty =
    receipt &&
    JSON.stringify(draft) !== JSON.stringify(toDraft(receipt.settings));
  return (
    <div className="workspace-settings" hidden={!active}>
      <div className="page-heading">
        <div>
          <p className="eyebrow">本机工作区 / 默认行为</p>
          <h1>工作区设置</h1>
        </div>
      </div>
      {error && (
        <p role="alert" className="risk">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {!receipt ? (
        <section className="card">
          <p>{busy ? "正在读取设置…" : "设置尚未载入。"}</p>
          <button disabled={busy} onClick={() => load()}>
            重新读取设置
          </button>
        </section>
      ) : (
        <>
          <section className="card">
            <h2>协作策略</h2>
            <label className="field">
              子 agent
              <select
                aria-label="子 agent"
                value={draft.subagents}
                disabled={busy}
                onChange={(e) => update("subagents", e.target.value)}
              >
                <option value="auto">自动：按任务及宿主能力使用</option>
                <option value="off">关闭：仅由主 agent 执行</option>
              </select>
            </label>
            <p className="muted">
              自动模式依赖宿主支持；没有子 agent 时仍可由单 agent
              完成。此项控制工作区协作策略，不能禁止宿主中的所有工具。
            </p>
            <label className="field capability-field">
              子 agent 能力要求
              <textarea
                aria-label="子 agent 能力要求"
                aria-describedby="subagent-requirements-help"
                value={draft.subagent_requirements}
                disabled={busy}
                rows={4}
                onChange={(e) =>
                  update("subagent_requirements", e.target.value)
                }
              />
            </label>
            <p id="subagent-requirements-help" className="muted">
              描述所需能力、成本偏好，也可填写具体模型和推理深度，由宿主选择可用模型。
              去除首尾空白后须为1–2000个字符。关闭协作时仍可预先编辑，保存要求不会启用委派。
            </p>
          </section>
          {(["materials", "reading"] as const).map((group) => (
            <section className="card" key={group}>
              <h2>{group === "materials" ? "材料查询" : "AI阅读"}</h2>
              {group === "materials" &&
                numberInput(group + ".result_limit", "默认结果数", 100, 1)}
              {group === "reading" && (
                <>
                  <label className="field">
                    默认阅读模式
                    <select
                      aria-label="默认阅读模式"
                      value={draft.strategy}
                      disabled={busy}
                      onChange={(e) => update("strategy", e.target.value)}
                    >
                      <option value="standard">标准阅读</option>
                      <option value="associative">联想加深</option>
                      <option value="quick">快速阅读</option>
                    </select>
                  </label>
                  <p className="muted">
                    标准阅读按检索、Owner、完整文稿形成note；联想加深沿已有note线索继续阅读；快速阅读逐条判断召回文本并形成note，不代表全文覆盖。
                  </p>
                  <label>
                    <input
                      type="checkbox"
                      aria-label="允许不足时联想加深"
                      checked={draft.association_enabled === "true"}
                      disabled={busy}
                      onChange={(e) =>
                        update("association_enabled", String(e.target.checked))
                      }
                    />
                    允许不足时联想加深
                  </label>
                  {numberInput("association_rounds", "最多联想轮次", 20, 1)}
                  <div className="form-grid">
                    {numberInput("max_owners", "最多Owner数", 100, 1)}
                    {numberInput(
                      "note_max_tokens",
                      "最终note估算token",
                      50000,
                      512,
                    )}
                  </div>
                  <p className="muted">
                    控制一次阅读的Owner数量和最终交给主agent的note大小。token采用保守估算，
                    不是宿主模型的精确token计数，也不是宿主整个上下文窗口大小。
                  </p>
                  <details>
                    <summary>高级资源保护（单次操作）</summary>
                    <p className="muted">
                      以下兼容工程字段限制单次读取或检索；旧阅读会话仍按已固定的累计预算执行。输出字符上限不是AI阅读上下文总预算。
                    </p>
                    {numberInput(
                      group + ".result_limit",
                      "单次检索结果数",
                      100,
                      1,
                    )}
                    <label className="field">
                      重排模式
                      <select
                        value={draft.mode}
                        disabled={busy}
                        onChange={(e) => update("mode", e.target.value)}
                      >
                        <option value="off">关闭</option>
                        <option value="auto">自动：不可用时明确降级</option>
                        <option value="required">必需：不可用时停止</option>
                      </select>
                    </label>
                    {numberInput("candidate_limit", "重排候选池", 100, 1)}
                    <div className="form-grid">
                      {fields.map((field) =>
                        numberInput(
                          group + "." + field.key,
                          field.key === "candidates"
                            ? "单次候选预算"
                            : field.title,
                          (receipt.limits[field.key] ?? 0) / (field.scale ?? 1),
                          field.key === "wall_ms" ? 0.001 : 0,
                          !!field.scale,
                        ),
                      )}
                    </div>
                  </details>
                </>
              )}
              {group === "materials" && (
                <>
                  <div className="form-grid">
                    {fields
                      .filter((field) => !field.advanced)
                      .map((field) =>
                        numberInput(
                          group + "." + field.key,
                          field.title,
                          (receipt.limits[field.key] ?? 0) / (field.scale ?? 1),
                          field.key === "wall_ms" ? 0.001 : 0,
                          !!field.scale,
                        ),
                      )}
                  </div>
                  <details>
                    <summary>高级预算</summary>
                    <div className="form-grid">
                      {fields
                        .filter((field) => field.advanced)
                        .map((field) =>
                          numberInput(
                            group + "." + field.key,
                            field.title,
                            receipt.limits[field.key] ?? 0,
                          ),
                        )}
                    </div>
                  </details>
                </>
              )}
            </section>
          ))}
          <section className="card">
            <p>{dirty ? "有未保存的草稿。" : "当前草稿与已保存设置一致。"}</p>
            <div className="row">
              <button
                className="primary"
                disabled={busy || !dirty}
                onClick={save}
              >
                {busy ? "处理中…" : "保存设置"}
              </button>
              <button
                disabled={busy}
                onClick={() => {
                  setDraft(toDraft(receipt.defaults));
                  setMessage("默认值已填入草稿，尚未保存。");
                  setError("");
                }}
              >
                恢复默认值到草稿
              </button>
              <button disabled={busy} onClick={() => load(true)}>
                读取最新配置（保留草稿）
              </button>
            </div>
            <details>
              <summary>服务端当前值（用于冲突核对）</summary>
              <pre>{JSON.stringify(receipt.settings, null, 2)}</pre>
            </details>
          </section>
        </>
      )}
    </div>
  );
}
