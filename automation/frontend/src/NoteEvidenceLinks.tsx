import type { ReadingEvidenceData } from "./ReadingEvidence";

/** A saved citation is navigation, not a request to expand every linked record.
 * Preserve fixed coordinates in the URL; the selected detail verifies them. */
export function NoteEvidenceLinks({
  reading,
}: {
  reading: ReadingEvidenceData | null;
}) {
  const cited =
    reading?.candidates.filter(
      (candidate) =>
        candidate.has_note === true ||
        (candidate.has_note === undefined && candidate.status === "已记录理解"),
    ) || [];
  return (
    <section className="card">
      <h2>当前阅读笔记的固定依据</h2>
      <p className="muted">选择已引用材料，查看完整内容、来源和下游影响。</p>
      {!cited.length && <p>此笔记尚无已保存理解的固定引用。</p>}
      {cited.map((candidate) => {
        const ref = candidate.ref;
        const params = ref
          ? new URLSearchParams({
              id: ref.id,
              ...(ref.revision ? { revision: String(ref.revision) } : {}),
              ...(ref.sha256 ? { sha256: ref.sha256 } : {}),
              ...(ref.locator ? { locator: ref.locator } : {}),
            })
          : null;
        return (
          <article className="proposal" key={candidate.candidate_id}>
            <h3>
              {params ? (
                <a href={"#/evidence?" + params.toString()}>
                  {candidate.title}
                </a>
              ) : (
                candidate.title
              )}
            </h3>
            {ref?.revision && <p className="muted">固定版本 r{ref.revision}</p>}
            {candidate.stale && (
              <p role="status">来源已变化，请按固定版本核对。</p>
            )}
            {!ref && <p>此条未保存可导航的固定出处。</p>}
          </article>
        );
      })}
    </section>
  );
}
