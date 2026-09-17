import type { OwnerScreeningPacket, Reading } from "./CurrentReading";

const statusText: Record<NonNullable<Reading["discovery"]>["status"], string> =
  {
    ready: "发现索引已就绪",
    unavailable: "发现索引不可用",
    incomplete: "发现覆盖不完整",
    insufficient: "压缩发现未找到足够结果",
  };

function OwnerCard({ packet }: { packet: OwnerScreeningPacket }) {
  return (
    <article className="material-candidate" data-testid="owner-discovery-card">
      <h4>{packet.title || packet.owner_id}</h4>
      {packet.title && <p className="id">{packet.owner_id}</p>}
      {packet.overview && <p>{packet.overview}</p>}
      {packet.assessment && (
        <p className="candidate-state">
          当前判断：{packet.assessment.status} · {packet.assessment.reason}
        </p>
      )}
      <p className="candidate-state">
        来源：
        {packet.retrieval_source === "fulltext_compensation"
          ? "用户选择的全文补偿"
          : "压缩发现索引"}
        {packet.coverage &&
          ` · ${packet.coverage.complete ? "筛选包覆盖完整" : "筛选包有缺口"}`}
      </p>
      {(packet.windows || []).map((window, index) => (
        <section key={`${packet.owner_id}:${index}`}>
          <p>{window.text}</p>
          <p className="muted">
            {[window.source_level, ...(window.channels || []), window.locator]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {!!window.matched_protected_terms?.length && (
            <p className="muted">
              保留条件：
              {window.matched_protected_terms.join("、")}
            </p>
          )}
        </section>
      ))}
      {!!packet.coverage?.gaps.length && (
        <ul className="material-gaps">
          {packet.coverage.gaps.map((gap) => (
            <li key={gap}>{gap}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

/**
 * 只显示后端已经固定的Owner筛选包。按钮回调必须来自一次真实用户点击；
 * 本组件不在挂载、翻页或uncertain状态下自动发起全文补偿。
 */
export function OwnerDiscovery({
  reading,
  busy,
  onFulltext,
}: {
  reading: Reading;
  busy: boolean;
  onFulltext: () => void;
}) {
  const discovery = reading.discovery;
  const packets = reading.owner_packets || [];
  if (!discovery && !packets.length && !reading.fulltext_compensation_available)
    return null;
  return (
    <section aria-label="Owner发现结果">
      <h3>Owner发现结果</h3>
      {discovery && (
        <p role="status">
          {statusText[discovery.status]}
          {discovery.projection_version
            ? ` · 投影 ${discovery.projection_version}`
            : ""}
        </p>
      )}
      {discovery?.reasons?.map((reason) => (
        <p className="muted" key={reason}>
          {reason}
        </p>
      ))}
      {packets.map((packet) => (
        <OwnerCard
          key={`${packet.owner_id}:${packet.packet_digest || "current"}`}
          packet={packet}
        />
      ))}
      {!!reading.screening_omitted_owner_count && (
        <p role="status">
          另有 {reading.screening_omitted_owner_count}{" "}
          个完整筛选包未在本页展开。
        </p>
      )}
      {reading.fulltext_compensation_available && (
        <div>
          <p className="muted">
            {reading.fulltext_compensation_reason ||
              "可以扩大到全文索引继续查找；这会增加读取范围和候选量。"}
          </p>
          <button
            type="button"
            disabled={busy || reading.archived}
            onClick={onFulltext}
          >
            开启全文补偿召回
          </button>
        </div>
      )}
    </section>
  );
}
