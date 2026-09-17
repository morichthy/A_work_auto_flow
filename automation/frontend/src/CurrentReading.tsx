import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, download } from "./api";
import { readingNoteName } from "./readingNoteName";
import { ResearchMarkdown } from "./ResearchDocument";
import { ReadingMode } from "./ReadingMode";
import type { ReadingEvidenceData } from "./ReadingEvidence";
export type Reading = ReadingEvidenceData & {
  mode?: "owner_document" | "legacy";
  strategy?: "standard" | "associative" | "quick";
  association?: { enabled: boolean; max_rounds: number };
  association_text?: string;
  revision: number;
  owner_id?: string | null;
  goal?: string;
  context_markdown: string;
  phase: string;
  archived: boolean;
  gaps: string[];
  notes_count?: number;
  updated_at?: string;
  generated_at?: string;
  verification?: string;
  warnings?: string[];
  workspace_id?: string;
};
export type Session = {
  session_id: string;
  revision: number;
  owner_id: string | null;
  goal: string;
  phase: string;
  archived: boolean;
  note_count?: number;
  updated_at?: string;
};
export type Listing = {
  items: Session[];
  next_offset: number | null;
  unavailable_count: number;
};
export type Result<T> = {
  status?: string;
  message?: string;
  code?: string;
  warnings?: string[];
  value: T | null;
};
export function failureMessage(value: unknown, fallback = "阅读记录不可用") {
  const wrapped = value as {
    materialResult?: Result<unknown>;
    message?: string;
  };
  const result = wrapped?.materialResult || (value as Result<unknown>);
  return (
    [result?.code, ...(result?.warnings || [])].filter(Boolean).join("：") ||
    wrapped?.message ||
    fallback
  );
}
type Context = {
  reading: Reading | null;
  busy: boolean;
  error: string;
  warning: string;
  select: (id: string) => Promise<Reading | null>;
  clear: () => void;
  refresh: () => Promise<void>;
  accept: (value: Reading) => void;
  recent: Session[];
  moreRecent: () => Promise<void>;
  hasMoreRecent: boolean;
};
const CurrentReadingContext = createContext<Context | null>(null);
export function useCurrentReading() {
  return useContext(CurrentReadingContext);
}
/** 当前选择只在工作台内存共享；晚到请求不可覆盖新选择，失败立即撤下旧正文。 */
export function CurrentReadingProvider({ children }: { children: ReactNode }) {
  const [reading, setReading] = useState<Reading | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [warning, setWarning] = useState("");
  const generation = useRef(0),
    selected = useRef("");
  const [recent, setRecent] = useState<Session[]>([]);
  const [nextRecent, setNextRecent] = useState<number | null>(null);
  const workspace = useRef("");
  // Storage failures (private mode/quota) must never prevent reading a note.
  const storageKey = () => "reading-selection:" + workspace.current;
  function remember(id: string) {
    if (!workspace.current) return;
    try {
      localStorage.setItem(storageKey(), id);
    } catch {
      /* Session still works in memory. */
    }
  }
  function clear() {
    generation.current++;
    selected.current = "";
    setReading(null);
    setError("");
    setWarning("");
    setBusy(false);
  }
  async function select(id: string) {
    selected.current = id;
    const token = ++generation.current;
    setReading(null);
    setBusy(true);
    setError("");
    try {
      const value = await api<Reading>("reading-notes/snapshot", {
        session_id: id,
      });
      if (token !== generation.current) return null;
      if (!value?.session_id) throw Error("阅读快照不可用");
      const snapshot = {
        ...value,
        candidates: value.candidates ?? [],
        gaps: value.gaps ?? [],
        archived: value.archived ?? false,
      };
      setReading(snapshot);
      remember(id);
      return snapshot;
    } catch (e) {
      if (token === generation.current) setError(failureMessage(e));
      return null;
    } finally {
      if (token === generation.current) setBusy(false);
    }
  }
  async function refresh() {
    const token = ++generation.current;
    setBusy(true);
    setError("");
    setWarning("");
    try {
      const result = await api<{
        workspace_id: string;
        items: Session[];
        warnings: string[];
        next_offset?: number | null;
      }>("reading-notes/recent", { limit: 50 });
      if (token !== generation.current) return;
      if (!Array.isArray(result.items) || !result.workspace_id)
        throw Error("最近问题列表不可用");
      if (workspace.current && workspace.current !== result.workspace_id)
        selected.current = "";
      workspace.current = result.workspace_id;
      setRecent(result.items);
      setNextRecent(result.next_offset ?? null);
      setWarning((result.warnings || []).join("；"));
      let remembered = "";
      try {
        remembered = localStorage.getItem(storageKey()) || "";
      } catch {
        /* Do not broaden to another workspace. */
      }
      // A remembered selection may be beyond the first 50 results. Resolve it
      // within this same recent window, rather than treating pagination as expiry.
      const desired = selected.current || remembered;
      let cursor = result.next_offset ?? null;
      while (
        desired &&
        !result.items.some((item) => item.session_id === desired) &&
        cursor !== null
      ) {
        const page = await api<{
          workspace_id: string;
          items: Session[];
          next_offset: number | null;
        }>("reading-notes/recent", { limit: 50, offset: cursor });
        if (token !== generation.current) return;
        if (page.workspace_id !== workspace.current)
          throw Error("工作区身份已变化，请刷新最近问题。");
        result.items.push(...page.items);
        if (page.next_offset !== null && page.next_offset <= cursor)
          throw Error("最近问题分页未前进，请刷新重试。");
        cursor = page.next_offset;
      }
      setRecent([...result.items]);
      setNextRecent(cursor);
      const id =
        [selected.current, remembered].find((candidate) =>
          result.items.some((row) => row.session_id === candidate),
        ) || result.items[0]?.session_id;
      if (id) await select(id);
      else {
        selected.current = "";
        setReading(null);
        setBusy(false);
      }
    } catch (e) {
      if (token === generation.current) {
        setReading(null);
        setError(failureMessage(e));
        setBusy(false);
      }
    }
  }
  // 配置保存已回读 HEAD；仅接受当前选择，防止旧会话的写入响应污染新选择。
  function accept(value: Reading) {
    if (selected.current === value.session_id) setReading(value);
  }
  async function moreRecent() {
    if (nextRecent === null || busy) return;
    const token = ++generation.current;
    setBusy(true);
    try {
      const result = await api<{
        workspace_id: string;
        items: Session[];
        next_offset: number | null;
      }>("reading-notes/recent", { limit: 50, offset: nextRecent });
      if (token !== generation.current) return;
      if (result.workspace_id !== workspace.current)
        throw Error("工作区身份已变化，请刷新最近问题。");
      setRecent((old) => [
        ...new Map(
          [...old, ...result.items].map((item) => [item.session_id, item]),
        ).values(),
      ]);
      setNextRecent(result.next_offset);
    } catch (e) {
      if (token === generation.current) setError(failureMessage(e));
    } finally {
      if (token === generation.current) setBusy(false);
    }
  }
  useEffect(() => {
    void refresh();
    return () => {
      generation.current++;
    };
  }, []);
  return (
    <CurrentReadingContext.Provider
      value={{
        reading,
        busy,
        error,
        warning,
        select,
        clear,
        refresh,
        accept,
        recent,
        moreRecent,
        hasMoreRecent: nextRecent !== null,
      }}
    >
      {children}
    </CurrentReadingContext.Provider>
  );
}
export function CurrentReadingNote() {
  const current = useCurrentReading();
  return (
    <section className="card">
      <h2>当前阅读笔记</h2>
      <label className="field">
        最近24小时阅读问题
        <select
          aria-label="最近24小时阅读问题"
          value={current?.reading?.session_id || ""}
          onChange={(e) => void current?.select(e.target.value)}
          disabled={!current?.recent.length}
        >
          <option value="" disabled>
            选择最近更新的问题
          </option>
          {current?.recent.map((item) => (
            <option key={item.session_id} value={item.session_id}>
              {item.goal || "未命名问题"} ·{" "}
              {item.updated_at
                ? new Date(item.updated_at).toLocaleString()
                : "时间未提供"}
            </option>
          ))}
        </select>
      </label>
      {current?.hasMoreRecent && (
        <button
          disabled={current.busy}
          onClick={() => void current.moreRecent()}
        >
          加载更多最近问题
        </button>
      )}
      {current?.busy && <p role="status">正在读取当前笔记…</p>}
      {current?.error && <p role="alert">{current.error}</p>}
      {current?.warning && <p role="status">{current.warning}</p>}
      {current?.reading ? (
        <>
          <p>{current.reading.goal || "未命名问题"}</p>
          <p className="muted">
            更新：
            {current.reading.updated_at
              ? new Date(current.reading.updated_at).toLocaleString()
              : "时间未提供"}{" "}
            · 快照 r{current.reading.revision}
          </p>
          {current.reading.verification === "snapshot_only" && (
            <p className="muted">
              已保存的展示快照，未重新核验证据；用于继续研究前请由阅读 agent
              核验交接。
            </p>
          )}
          {current.reading.warnings
            ?.filter(
              (warning) =>
                current.reading?.verification !== "snapshot_only" ||
                warning !==
                  "此为已保存阅读快照，仅检查当前访问边界；未重新核验证据内容。AI继续使用必须调用reading-handoff。",
            )
            .map((warning) => (
              <p key={warning} role="status">
                {warning}
              </p>
            ))}
          <details>
            <summary>会话与快照详情</summary>
            <p className="id">
              {current.reading.session_id} · 归属：
              {current.reading.owner_id || "未绑定"}
            </p>
            <p>快照读取时间：{current.reading.generated_at || "未提供"}</p>
          </details>
          {current.reading.mode === "owner_document" && (
            <details>
              <summary>阅读模式与联想方向</summary>
              <ReadingMode
                key={current.reading.session_id}
                reading={current.reading}
                onSaved={current.accept}
              />
              <p>
                <a href="#/settings">设置新会话的默认阅读模式</a>
              </p>
            </details>
          )}
          {current.reading.strategy === "quick" && (
            <p role="status">
              快速阅读：笔记依据已交付的召回文本，不代表全文覆盖。
            </p>
          )}
          {current.reading.gaps.map((gap) => (
            <p role="status" key={gap}>
              {gap}
            </p>
          ))}
          <div
            style={{ maxHeight: "60vh", overflow: "auto" }}
            aria-label="当前阅读笔记全文"
            tabIndex={0}
          >
            <ResearchMarkdown text={current.reading.context_markdown} />
          </div>
          <button
            onClick={() =>
              download(
                readingNoteName(
                  current.reading!.goal,
                  current.reading!.session_id,
                  current.reading!.revision,
                ),
                current.reading!.context_markdown,
              )
            }
          >
            导出当前笔记
          </button>
        </>
      ) : (
        !current?.busy &&
        !current?.error && (
          <p>
            最近24小时暂无已保存的阅读笔记。历史会话与固定笔记仍保留，可通过阅读接口续接。
          </p>
        )
      )}
      <div className="row">
        <button
          disabled={current?.busy}
          onClick={() => void current?.refresh()}
        >
          刷新当前笔记
        </button>
        <a href="#/evidence?scope=reading">查看证据与影响</a>
      </div>
    </section>
  );
}
