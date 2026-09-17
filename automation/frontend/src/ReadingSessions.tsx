import { useEffect, useRef, useState } from "react";
import { api, download } from "./api";
import { readingNoteName } from "./readingNoteName";
import { ResearchMarkdown } from "./ResearchDocument";
import { MaterialPacket } from "./MaterialPacket";
import { ReadingMode } from "./ReadingMode";
import { OwnerDiscovery } from "./OwnerDiscovery";
import type {
  MaterialPacket as Packet,
  OwnerFulltextRecallRequest,
} from "./generated/material-query";
import {
  useCurrentReading,
  failureMessage,
  type Session,
  type Listing,
  type Reading,
  type Result,
} from "./CurrentReading";

/** Read the live RS through the public API; never cache private notes across owners. */
export function ReadingSessions({ ownerId }: { ownerId: string }) {
  const current = useCurrentReading();
  const [items, setItems] = useState<Session[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [reading, setReading] = useState<Reading | null>(null);
  const [snapshotRevision, setSnapshotRevision] = useState(0);
  const [packet, setPacket] = useState<Packet | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const selected = useRef("");
  const [offset, setOffset] = useState(0);
  const [warning, setWarning] = useState("");

  async function list(offset = 0, refresh = false) {
    const token = ++generation.current;
    setBusy(true);
    setError("");
    if (refresh) setReading(null);
    setPacket(null);
    try {
      const response = await api<Result<Listing>>("materials/reading-list", {
        ...(ownerId ? { owner_id: ownerId } : {}),
        offset,
        limit: 20,
        include_archived: true,
      });
      if (token !== generation.current) return;
      if (!response.value)
        throw Error(failureMessage(response, "阅读清单不可用"));
      setItems(response.value.items);
      setNext(response.value.next_offset);
      setOffset(offset);
      setWarning(
        response.value.unavailable_count
          ? "部分记录当前不可读取；请检查来源或权限。"
          : "",
      );
      // 清单与正文独立：翻页不改变选择，显式刷新重读当前HEAD。
      const chosen =
        selected.current ||
        response.value.items.find(
          (item) => !item.archived && (item.note_count || 0) > 0,
        )?.session_id ||
        response.value.items.find((item) => (item.note_count || 0) > 0)
          ?.session_id ||
        response.value.items[0]?.session_id;
      if (chosen && (refresh || !selected.current)) await view(chosen);
    } catch (e) {
      if (token === generation.current) {
        setItems([]);
        setNext(null);
        setReading(null);
        current?.clear();
        setError(failureMessage(e));
      }
    } finally {
      if (token === generation.current) setBusy(false);
    }
  }

  async function view(id: string) {
    const token = ++generation.current;
    setBusy(true);
    setError("");
    setReading(null);
    setPacket(null);
    selected.current = id;
    try {
      const response = current
        ? { value: await current.select(id) }
        : await api<Result<Reading>>("materials/reading-view", {
            session_id: id,
            notes_only: true,
          });
      if (token !== generation.current) return;
      if (!response.value) throw Error(failureMessage(response));
      setReading(response.value);
      setSnapshotRevision(response.value.revision);
    } catch (e) {
      if (token === generation.current) setError(failureMessage(e));
    } finally {
      if (token === generation.current) setBusy(false);
    }
  }

  async function openSource(candidateId: string) {
    if (!reading) return;
    const token = ++generation.current;
    setBusy(true);
    setError("");
    setPacket(null);
    try {
      const response = await api<
        Result<{
          revision: number;
          readings: { packet: Packet }[];
          gaps: string[];
        }>
      >("materials/reading-read", {
        session_id: reading.session_id,
        expected_revision: reading.revision,
        request_id: crypto.randomUUID(),
        candidate_ids: [candidateId],
      });
      if (token !== generation.current) return;
      if (!response.value) throw Error(failureMessage(response, "原文不可用"));
      setPacket(response.value.readings[0]?.packet || null);
      // 下一次打开沿用服务器新修订，避免浏览器自行推算版本。
      setReading({ ...reading, revision: response.value.revision });
      if (response.value.gaps.length) setError(response.value.gaps.join("；"));
    } catch (e) {
      if (token === generation.current) {
        setReading(null);
        current?.clear();
        setError(failureMessage(e));
      }
    } finally {
      if (token === generation.current) setBusy(false);
    }
  }

  async function recallFulltext() {
    if (!reading) return;
    const token = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const request: OwnerFulltextRecallRequest = {
        session_id: reading.session_id,
        expected_revision: reading.revision,
        request_id: crypto.randomUUID(),
      };
      const response = await api<
        Result<
          Pick<
            Reading,
            | "revision"
            | "discovery"
            | "owner_packets"
            | "fulltext_compensation_available"
            | "fulltext_compensation_reason"
            | "gaps"
          >
        >
      >("materials/reading-recall-fulltext", request);
      if (token !== generation.current) return;
      if (!response.value)
        throw Error(failureMessage(response, "全文补偿召回不可用"));
      const next = { ...reading, ...response.value };
      setReading(next);
      setSnapshotRevision(next.revision);
      current?.accept(next);
    } catch (e) {
      if (token === generation.current) setError(failureMessage(e));
    } finally {
      if (token === generation.current) setBusy(false);
    }
  }

  useEffect(() => {
    setItems([]);
    setNext(null);
    setReading(null);
    setPacket(null);
    selected.current =
      current?.reading && (!ownerId || current.reading.owner_id === ownerId)
        ? current.reading.session_id
        : "";
    if (selected.current && current?.reading) {
      setReading(current.reading);
      setSnapshotRevision(current.reading.revision);
    } else current?.clear();
    // 从首页进入时沿用已授权的当前快照；只有显式刷新再读HEAD。
    void list(0, !selected.current);
    return () => {
      generation.current++;
    };
  }, [ownerId]);
  // 首页刷新同一选择后，面板沿用同一份服务器快照，不保留另一份旧正文。
  useEffect(() => {
    if (!current) return;
    if (current.busy || current.error) {
      setReading(null);
      setPacket(null);
    } else if (current.reading?.session_id === selected.current) {
      setReading(current.reading);
      setSnapshotRevision(current.reading.revision);
    }
  }, [current?.reading, current?.busy, current?.error]);
  return (
    <section className="card">
      <h2>阅读记录</h2>
      <p className="muted">
        {ownerId
          ? `归属对象：${ownerId}。以下为该对象的阅读会话`
          : "全部可访问会话（含未绑定的旧记录）"}
        。打开或刷新时读取最新状态；不会自动重新检索。
      </p>
      <button disabled={busy} onClick={() => void list(offset, true)}>
        刷新阅读清单
      </button>
      {(current?.error || error) && (
        <p role="alert">{current?.error || error}</p>
      )}
      {warning && <p role="status">{warning}</p>}
      {busy && <p role="status">正在读取阅读记录…</p>}
      {!busy && !items.length && (
        <p>本页没有可显示的会话。{next !== null ? "仍有下一页。" : ""}</p>
      )}
      <ul>
        {items.map((item) => (
          <li key={item.session_id}>
            <button
              aria-pressed={selected.current === item.session_id}
              disabled={busy}
              onClick={() => void view(item.session_id)}
            >
              {item.goal}
            </button>
            <span>
              {" "}
              · r{item.revision} · {item.archived ? "已归档" : "工作记录"}
              {item.note_count !== undefined && ` · ${item.note_count} 条笔记`}
              {!ownerId && ` · 归属：${item.owner_id || "未绑定"}`}
            </span>
          </li>
        ))}
      </ul>
      {offset > 0 && (
        <button
          disabled={busy}
          onClick={() => void list(Math.max(0, offset - 20))}
        >
          上一页阅读会话
        </button>
      )}
      {next !== null && (
        <button disabled={busy} onClick={() => void list(next)}>
          下一页阅读会话
        </button>
      )}
      {reading && (
        <article>
          <h3>当前阅读会话</h3>
          {reading.goal && <p>{reading.goal}</p>}
          <p className="muted">笔记快照 r{snapshotRevision}</p>
          <details>
            <summary>会话标识与版本</summary>
            <p className="id">
              {reading.session_id} · r{snapshotRevision}
            </p>
          </details>
          {reading.mode === "owner_document" ? (
            <ReadingMode
              key={reading.session_id}
              reading={reading}
              onSaved={(value) => {
                if (selected.current !== value.session_id) return;
                setReading(value);
                setSnapshotRevision(value.revision);
                current?.accept(value);
              }}
            />
          ) : (
            <p className="muted">
              此历史会话使用旧版逐候选阅读流程，保留原有笔记与原文查看；三模式设置仅适用于新的Owner阅读会话。
            </p>
          )}
          <div className="row">
            <button
              disabled={busy}
              onClick={() => void view(reading.session_id)}
            >
              刷新当前阅读记录
            </button>
            <button
              onClick={() =>
                download(
                  readingNoteName(
                    reading.goal,
                    reading.session_id,
                    snapshotRevision,
                  ),
                  reading.context_markdown,
                )
              }
            >
              导出此版本笔记
            </button>
          </div>
          {reading.gaps.map((gap) => (
            <p role="status" key={gap}>
              {gap}
            </p>
          ))}
          <OwnerDiscovery
            reading={reading}
            busy={busy}
            onFulltext={() => void recallFulltext()}
          />
          <ResearchMarkdown text={reading.context_markdown} />
          <h3>打开固定原文</h3>
          <ul>
            {reading.candidates.map((item) => (
              <li key={item.candidate_id}>
                <button
                  disabled={busy || reading.archived}
                  onClick={() => void openSource(item.candidate_id)}
                >
                  {item.title} · 读取原文
                </button>
              </li>
            ))}
          </ul>
          <MaterialPacket packet={packet} />
        </article>
      )}
    </section>
  );
}
