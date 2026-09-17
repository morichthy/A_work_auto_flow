import type { FixedRef } from "./generated/material-query";
import { useEffect, useState } from "react";
import { api } from "./api";
import { ResearchMarkdown, recordMarkdown } from "./ResearchDocument";
import type { MemoryRecord, Ref } from "../../schemas/memory-v4";

const layers = {
  source: "L0 原始材料",
  detail: "L1 技术单元",
  narrative: "L2 研究经过",
  event: "L2 研究经过",
  experience: "L3 经验",
  overview: "L4 整体概览",
  map: "L4 整体概览",
};
type Expansion = {
  context_text?: string;
  manifest: {
    items: { owner_id: string; canonical_id: string; ref: Ref }[];
    missing: unknown[];
    omitted: unknown[];
  };
};

export type ReadingEvidenceData = {
  session_id: string;
  candidates: {
    candidate_id: string;
    title: string;
    status: string;
    ref?: FixedRef;
    link?: string;
    stale?: boolean;
    level?: string;
    has_note?: boolean;
  }[];
  unnoted_candidate_ids?: string[];
};
/** 仅按已保存笔记关联的候选固定引用展示依据，不把同Owner或全库记录当成引用。 */
export function ReadingEvidence({
  reading,
}: {
  reading: ReadingEvidenceData | null;
}) {
  const [records, setRecords] = useState<MemoryRecord[]>([]);
  const [gaps, setGaps] = useState<unknown[]>([]);
  const [busy, setBusy] = useState(false);
  const [otherEvidence, setOtherEvidence] = useState<Expansion[]>([]);
  useEffect(() => {
    let live = true;
    setRecords([]);
    setGaps([]);
    setOtherEvidence([]);
    const refs: Ref[] = (reading?.candidates || [])
      .filter((c) => c.has_note || c.status === "已记录理解")
      .flatMap((c) =>
        c.ref?.kind === "record"
          ? [
              {
                target_kind: "record" as const,
                target_id: c.ref.id,
                revision: c.ref.revision,
                sha256: c.ref.sha256,
                locator: c.ref.locator || "",
                relation: "references" as const,
              },
            ]
          : [],
      );
    if (!refs.length) {
      setBusy(false);
      return;
    }
    setBusy(true);
    // 固定展开用于解析归属；仅加载明确引用，禁止将同Owner全部记录当成依据。
    const load = async (selected: Ref[]) => {
      if (!selected.length) return [];
      const packet = await api<Expansion>("memory/expand", {
        refs: selected,
        budget: 20000,
      });
      if (!live) return [];
      if (
        packet.manifest.items.some((item) => item.ref.target_kind !== "record")
      )
        setOtherEvidence((previous) => [...previous, packet]);
      setGaps((previous) => [
        ...previous,
        ...(packet.manifest.missing || []),
        ...(packet.manifest.omitted || []),
      ]);
      const result = await Promise.allSettled(
        packet.manifest.items
          .filter((item) => item.ref.target_kind === "record")
          .map(async (item) => {
            const value = await api<{ record: MemoryRecord }>(
              "memory/inspect",
              {
                owner_id: item.owner_id,
                record_id: item.canonical_id,
                revision: item.ref.revision,
              },
            );
            if (
              value.record.revision !== item.ref.revision ||
              value.record.record_hash !== item.ref.sha256
            )
              throw Error(`固定版本指纹不一致：${item.canonical_id}`);
            return value;
          }),
      );
      const loaded: MemoryRecord[] = [];
      for (const row of result) {
        if (row.status === "fulfilled") loaded.push(row.value.record);
        else if (live) setGaps((previous) => [...previous, String(row.reason)]);
      }
      return loaded;
    };
    void (async () => {
      const direct = await load(refs);
      if (!live) return;
      const known = new Set(
        refs.map((ref) => `${ref.target_id}:${ref.revision}`),
      );
      const sources = direct
        .flatMap((record) => record.sources)
        .filter((ref) => {
          const key = `${ref.target_id}:${ref.revision}`;
          if (known.has(key)) return false;
          known.add(key);
          return true;
        });
      const linked = await load(sources);
      if (live) setRecords([...direct, ...linked]);
    })()
      .catch((error) => {
        if (live) setGaps([String(error)]);
      })
      .finally(() => {
        if (live) setBusy(false);
      });
    return () => {
      live = false;
    };
  }, [reading]);
  const candidates =
    reading?.candidates.filter(
      (candidate) =>
        candidate.has_note === true ||
        (candidate.has_note === undefined && candidate.status === "已记录理解"),
    ) || [];
  return (
    <section className="card">
      <h2>当前阅读笔记的固定依据</h2>
      {!reading ? (
        <p>当前没有可读取的阅读笔记，请先在工作台选择阅读记录。</p>
      ) : (
        <>
          <p className="id">{reading.session_id}</p>
          <p className="muted">
            以下仅列出已保存理解引用的材料。层级、来源版本与复核结论分别保留。
          </p>
          {!candidates.length && <p>此笔记尚无已保存理解的固定引用。</p>}
          {busy && <p role="status">正在读取固定依据及一层显式来源…</p>}
          {[
            "L0 原始材料",
            "L1 技术单元",
            "L2 研究经过",
            "L3 经验",
            "L4 整体概览",
            "其他引用记录",
          ].map((layer) => {
            const items = records.filter(
              (record) =>
                (layers[record.kind as keyof typeof layers] ||
                  "其他引用记录") === layer,
            );
            return (
              <section key={layer}>
                <h3>{layer}</h3>
                {!items.length ? (
                  <p className="muted">
                    当前笔记及一层显式来源中暂无此类记录。
                  </p>
                ) : (
                  items.map((record) => (
                    <article
                      className="proposal"
                      key={`${record.record_id}:${record.revision}`}
                    >
                      <h4>{record.title}</h4>
                      <a
                        href={`#/memory?owner=${encodeURIComponent(record.owner_id)}&record=${encodeURIComponent(record.record_id)}`}
                      >
                        在系统记忆中查看当前记录
                      </a>
                      <p className="id">
                        以下为固定版本 r{record.revision} · {record.record_id}
                      </p>
                      <ResearchMarkdown text={recordMarkdown(record)} />
                      {!!record.sources.length && (
                        <>
                          <h4>显式固定来源</h4>
                          <ul>
                            {record.sources.map((ref, index) => (
                              <li key={index}>
                                <strong>{ref.target_id}</strong> ·{" "}
                                {ref.target_kind} ·{" "}
                                {ref.revision == null
                                  ? "无修订号"
                                  : `r${ref.revision}`}
                                <p>{ref.locator || "未提供定位"}</p>
                                <small className="id">
                                  SHA256：{ref.sha256 || "未固定指纹"}
                                </small>
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                      <details>
                        <summary>固定来源与结论复核依据</summary>
                        <pre>
                          {JSON.stringify(
                            {
                              sources: record.sources,
                              payload: record.payload,
                            },
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    </article>
                  ))
                )}
              </section>
            );
          })}
          {otherEvidence.map((packet, index) => (
            <section key={index}>
              <h3>其他固定来源与运行证据</h3>
              {packet.manifest.items
                .filter((item) => item.ref.target_kind !== "record")
                .map((item) => (
                  <article key={item.canonical_id}>
                    <h4>{item.canonical_id}</h4>
                    <p>
                      {item.ref.target_kind} ·{" "}
                      {item.ref.locator || "未提供定位"}
                    </p>
                    <p className="id">SHA256：{item.ref.sha256}</p>
                  </article>
                ))}
              <ResearchMarkdown
                text={
                  packet.context_text ||
                  "接口未交付可读正文，请查看固定引用与读取缺口。"
                }
              />
            </section>
          ))}
          {!!gaps.length && (
            <details open>
              <summary>读取范围与缺口</summary>
              <pre>{JSON.stringify(gaps, null, 2)}</pre>
            </details>
          )}
          {candidates.map((candidate) => (
            <article className="proposal" key={candidate.candidate_id}>
              <h3>{candidate.title}</h3>
              <p>
                {candidate.level ||
                  layers[
                    records.find(
                      (record) => record.record_id === candidate.ref?.id,
                    )?.kind as keyof typeof layers
                  ] ||
                  "层级未提供"}{" "}
                · {candidate.status}
              </p>
              {candidate.stale && (
                <p className="risk">来源已变化，当前笔记引用的是旧版本。</p>
              )}
              {candidate.ref ? (
                <>
                  <p className="id">
                    {candidate.ref.kind} · {candidate.ref.id} ·{" "}
                    {candidate.ref.revision == null
                      ? "文件指纹"
                      : `r${candidate.ref.revision}`}
                  </p>
                  <p className="id">SHA256：{candidate.ref.sha256}</p>
                  {candidate.ref.locator && <p>{candidate.ref.locator}</p>}
                </>
              ) : (
                <p>未提供固定引用详情。</p>
              )}
              {candidate.link && (
                <details>
                  <summary>固定原记录路径</summary>
                  <p className="id">{candidate.link}</p>
                </details>
              )}
            </article>
          ))}
        </>
      )}
    </section>
  );
}
