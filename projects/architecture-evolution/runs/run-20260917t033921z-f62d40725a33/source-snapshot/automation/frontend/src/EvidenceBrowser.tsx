import { useEffect, useRef, useState } from "react";
import { api, kindNames, relationNames } from "./api";
import { useCurrentReading } from "./CurrentReading";
import { NoteEvidenceLinks } from "./NoteEvidenceLinks";
import { ResearchMarkdown } from "./ResearchDocument";
import type { MemoryRecord } from "../../schemas/memory-v4";

type Item = {
  id: string;
  title: string;
  kind: string;
  owner_id?: string;
  summary?: string;
  tags: string[];
  url?: string;
};
type Link = {
  id: string;
  title: string;
  relation: string;
  url: string;
  ref?: unknown;
};
type Search = {
  items: Item[];
  total: number;
  next_offset: number | null;
  warnings: string[];
};
type Detail = Item & {
  claim_reviews?: {
    claim_id: string;
    statement: string;
    state: string;
    content_matches: boolean | null;
    scope?: string;
    reviewer?: { id?: string; name?: string; type?: string } | string;
    reason?: string;
    reviewed_at?: string;
  }[];
  level?: string | null;
  record?: MemoryRecord | null;
  images?: { index: number; caption: string; data_url: string }[];
  media?: { type: string; data_url: string; caption: string } | null;
  sections?: {
    id: string;
    title: string;
    kind: string;
    level?: string | null;
    content_markdown: string;
    record?: MemoryRecord;
    images?: { index: number; caption: string; data_url: string }[];
  }[];
  content_markdown: string;
  structured_content_markdown?: string;
  context: Record<string, unknown>;
  references: Link[];
  impacts: Link[];
  fixed_ref?: unknown;
  warnings: string[];
  verification: string;
};
const displayKinds: Record<string, string> = {
  source: "L0 原始材料",
  file: "L0 原始材料",
  detail: "L1 技术单元",
  narrative: "L2 研究经过",
  event: "L2 研究经过",
  experience: "L3 可复用认识",
  overview: "L4 整体概览",
  map: "L4 整体概览",
  run: "Run 实验记录",
  document: "完整研究文稿",
  document_section: "研究章节",
};
const bodyTitles: Record<string, string> = {
  source: "材料说明与位置",
  file: "材料说明与位置",
  detail: "方法与完整技术内容",
  narrative: "研究经过",
  event: "研究经过",
  experience: "经验与适用边界",
  overview: "对象整体概览",
  map: "对象整体概览",
  run: "实验经过与结果",
  document: "完整文稿",
  document_section: "章节正文",
};
const reviewLabels: Record<string, string> = {
  "not-reviewed": "未复核",
  unavailable: "复核记录暂不可完整读取",
  accepted: "已确认",
  disputed: "有争议",
  retracted: "已撤回",
  superseded: "已被替代",
};
const technicalKeys = new Set([
  "id",
  "owner_id",
  "record_id",
  "target_id",
  "sha256",
  "fingerprint",
  "revision",
  "locator",
  "source_registration",
]);
const contextLabels: Record<string, string> = {
  owner_id: "归属对象",
  owner_title: "对象名称",
  owner_summary: "对象概览",
  source_registration: "来源登记",
  level: "记录层级",
  validity: "有效性",
  status: "状态",
  inputs: "输入",
  parameters: "参数",
  outputs: "输出",
  artifacts: "产物",
  results: "结果",
  environment: "环境",
  title: "名称",
  goal: "目标",
  question: "问题",
  conditions: "适用条件",
  summary: "摘要",
  overview: "整体概览",
  conclusion: "结论",
  limitations: "限制",
  state: "状态",
  execution_status: "执行状态",
  record_reason: "保存原因",
  scope: "适用范围",
  review: "复核",
  updated_at: "更新时间",
  path: "材料位置",
  provenance_gap: "来源缺口",
  missing_refs: "尚缺依据",
};
// Render descriptive context as terms, not a JSON blob. Exact IDs stay in details.
function ContextValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "")
    return <span className="muted">未提供</span>;
  if (Array.isArray(value))
    return (
      <ul>
        {value.map((item, index) => (
          <li key={index}>
            <ContextValue value={item} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === "object")
    return (
      <dl>
        {Object.entries(value)
          .filter(([key]) => !technicalKeys.has(key))
          .map(([key, item]) => (
            <div key={key}>
              <dt>{contextLabels[key] || key}</dt>
              <dd>
                <ContextValue value={item} />
              </dd>
            </div>
          ))}
      </dl>
    );
  return <ResearchMarkdown text={String(value)} />;
}

/** Metadata search and selected detail have independent request generations. */
export function Evidence({
  revision,
}: {
  revision: number;
  error: (message: string) => void;
}) {
  const currentReading = useCurrentReading();
  const [route, setRoute] = useState(() => location.hash);
  const params = new URLSearchParams(route.split("?")[1] || "");
  const readingScope = params.get("scope") === "reading";
  const selected = params.get("id") || "";
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<Search | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [searchBusy, setSearchBusy] = useState(false),
    [detailBusy, setDetailBusy] = useState(false);
  const [searchError, setSearchError] = useState(""),
    [detailError, setDetailError] = useState("");
  const searchGeneration = useRef(0),
    detailGeneration = useRef(0);
  useEffect(() => {
    const change = () => setRoute(location.hash);
    window.addEventListener("hashchange", change);
    return () => {
      window.removeEventListener("hashchange", change);
      searchGeneration.current++;
      detailGeneration.current++;
    };
  }, []);
  async function find(offset = 0) {
    const token = ++searchGeneration.current;
    setSearchBusy(true);
    setSearchError("");
    try {
      const value = await api<Search>("evidence/search", {
        query,
        limit: 30,
        offset,
      });
      if (token === searchGeneration.current) setSearch(value);
    } catch (e) {
      if (token === searchGeneration.current) setSearchError(String(e));
    } finally {
      if (token === searchGeneration.current) setSearchBusy(false);
    }
  }
  useEffect(() => {
    if (!readingScope) void find();
  }, [revision, readingScope]);
  useEffect(() => {
    const token = ++detailGeneration.current;
    setDetail(null);
    setDetailError("");
    if (!selected || readingScope) {
      setDetailBusy(false);
      return;
    }
    setDetailBusy(true);
    const request: {
      id: string;
      revision?: number;
      sha256?: string;
      locator?: string;
    } = { id: selected };
    const version = params.get("revision");
    if (version !== null) {
      if (
        !/^\d+$/.test(version) ||
        !Number.isSafeInteger(Number(version)) ||
        Number(version) < 1
      ) {
        setDetailError("证据链接的修订号无效，未改读当前版本。");
        setDetailBusy(false);
        return;
      }
      request.revision = Number(version);
    }
    for (const key of ["sha256", "locator"] as const) {
      const value = params.get(key);
      if (value) request[key] = value;
    }
    void api<Detail>("evidence/detail", request)
      .then((value) => {
        if (token === detailGeneration.current) setDetail(value);
      })
      .catch((e) => {
        if (token === detailGeneration.current) setDetailError(String(e));
      })
      .finally(() => {
        if (token === detailGeneration.current) setDetailBusy(false);
      });
    return () => {
      detailGeneration.current++;
    };
  }, [route, revision]);
  function links(items: Link[], empty: string) {
    return items.length ? (
      <ul className="evidence-links">
        {items.map((item, index) => (
          <li key={`${item.id}:${index}`}>
            <span className="badge">
              {relationNames[item.relation] || item.relation || "关联"}
            </span>{" "}
            <a
              href={item.url || `#/evidence?id=${encodeURIComponent(item.id)}`}
            >
              {item.title || "未命名记录"}
            </a>
          </li>
        ))}
      </ul>
    ) : (
      <p className="muted">{empty}</p>
    );
  }
  if (readingScope)
    return (
      <>
        <div className="page-heading">
          <h1>当前笔记的证据与影响</h1>
          <a className="button" href="#/evidence">
            浏览全库证据
          </a>
        </div>
        <NoteEvidenceLinks reading={currentReading?.reading || null} />
      </>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">证据 / 来源与影响</p>
          <h1>查看依据，检查影响</h1>
        </div>
        <button onClick={() => void find()} disabled={searchBusy}>
          刷新证据
        </button>
      </div>
      <p className="muted">
        按标题、结论或整体概览、ID搜索；只读取选中记录的详情。此处展示保存的元数据，未重新核验全部外部原件。
      </p>
      <div className="evidence-layout">
        <aside className="card scroll-list" aria-label="证据搜索列表">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void find();
            }}
          >
            <label className="field">
              搜索证据
              <input
                aria-label="搜索证据"
                value={query}
                placeholder="标题、结论、整体概览或ID"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <button type="submit" disabled={searchBusy}>
              搜索
            </button>
          </form>
          {searchBusy && <p role="status">正在搜索记录…</p>}
          {searchError && <p role="alert">{searchError}</p>}
          {search && <p className="muted">找到{search.total}条记录</p>}
          {search?.items.map((item) => (
            <a
              className={`item ${item.id === selected ? "active" : ""}`}
              key={item.id}
              href={item.url || `#/evidence?id=${encodeURIComponent(item.id)}`}
            >
              <span className="eyebrow">
                {displayKinds[item.kind] || kindNames[item.kind] || item.kind}
              </span>
              <strong>{item.title}</strong>
              <span>{item.summary}</span>
            </a>
          ))}
          {search?.next_offset !== null &&
            search?.next_offset !== undefined && (
              <button
                disabled={searchBusy}
                onClick={() => void find(search.next_offset!)}
              >
                下一页证据
              </button>
            )}
          {search?.warnings?.map((warning) => (
            <p role="status" key={warning}>
              {warning}
            </p>
          ))}
        </aside>
        <section className="card evidence-detail" aria-label="选中证据详情">
          {detailBusy && <p role="status">正在读取选中记录…</p>}
          {detailError && <p role="alert">{detailError}</p>}
          {detail ? (
            <>
              <h2>{detail.title}</h2>
              <div className="row">
                <span className="badge">
                  {displayKinds[detail.kind] ||
                    kindNames[detail.kind] ||
                    detail.kind}
                </span>
                {detail.tags?.map((tag) => (
                  <span key={tag} className="badge">
                    {tag}
                  </span>
                ))}
              </div>
              {detail.warnings?.map((warning) => (
                <p role="status" key={warning}>
                  {warning}
                </p>
              ))}
              <section aria-label="结论确认状态">
                <h3>结论确认状态</h3>
                {detail.claim_reviews?.length ? (
                  detail.claim_reviews.map((review) => (
                    <article key={review.claim_id}>
                      <p>
                        <strong>
                          {review.content_matches === false
                            ? "复核不适用于所选版本"
                            : reviewLabels[review.state] || review.state}
                        </strong>{" "}
                        · {review.statement}
                      </p>
                      {review.content_matches === false && (
                        <p>
                          已保存的复核状态：
                          {reviewLabels[review.state] || review.state}
                          ；其绑定内容与当前展示版本不同。
                        </p>
                      )}
                      {review.scope && <p>复核范围：{review.scope}</p>}
                      {review.reviewer && (
                        <p>
                          复核者：
                          {typeof review.reviewer === "string"
                            ? review.reviewer
                            : review.reviewer.name ||
                              review.reviewer.id ||
                              review.reviewer.type ||
                              "未提供"}
                        </p>
                      )}
                      {review.reason && <p>复核依据：{review.reason}</p>}
                      {review.reviewed_at && (
                        <p>复核记录时间：{review.reviewed_at}</p>
                      )}
                    </article>
                  ))
                ) : (
                  <p className="muted">
                    未登记可独立复核的结论；记录已保存不代表结论已确认。
                  </p>
                )}
                <p className="muted">
                  以上为已保存的复核记录；本页未重新核验支持证据的当前有效性。
                </p>
              </section>
              {/* Complete Markdown includes root prose, chapters and one bibliography.
                  Image slots are response-local, so use the top-level image map. */}
              <h3>{bodyTitles[detail.kind] || "正文"}</h3>
              <ResearchMarkdown
                text={detail.content_markdown || "暂无正文。"}
                record={detail.record || undefined}
                images={detail.images}
              />
              {detail.structured_content_markdown && (
                <details>
                  <summary>结构化记录字段</summary>
                  <p className="muted">
                    保留用于检索与整理的分项内容；其信息可能与上方完整正文重复。
                  </p>
                  <ResearchMarkdown
                    text={detail.structured_content_markdown}
                    record={detail.record || undefined}
                    images={detail.images}
                  />
                </details>
              )}
              {(detail.kind === "file" || detail.kind === "source") &&
                typeof (
                  detail.context?.source_registration as { path?: unknown }
                )?.path === "string" && (
                  <p className="muted">
                    材料位置：
                    {String(
                      (detail.context.source_registration as { path: string })
                        .path,
                    )}
                  </p>
                )}
              {detail.media?.type === "image" &&
                /^data:image\/(png|jpeg|webp);base64,/.test(
                  detail.media.data_url,
                ) && (
                  <figure>
                    <img
                      src={detail.media.data_url}
                      alt={detail.media.caption || detail.title}
                      style={{ maxWidth: "100%", height: "auto" }}
                    />
                    <figcaption>{detail.media.caption}</figcaption>
                  </figure>
                )}
              <h3>关键上下文</h3>
              {detail.kind === "run" ? (
                <div>
                  {[
                    ["输入", ["inputs"]],
                    ["配置与环境", ["parameters", "environment"]],
                    ["执行状态", ["execution_status", "status"]],
                    ["结果与产物", ["results", "outputs", "artifacts"]],
                    ["限制", ["limitations"]],
                  ].map(([title, keys]) => {
                    const values = Object.fromEntries(
                      (keys as string[])
                        .filter((key) => detail.context?.[key] !== undefined)
                        .map((key) => [key, detail.context[key]]),
                    );
                    return Object.keys(values).length ? (
                      <section key={String(title)}>
                        <h4>{title}</h4>
                        <ContextValue value={values} />
                      </section>
                    ) : null;
                  })}
                </div>
              ) : (
                <ContextValue
                  value={Object.fromEntries(
                    Object.entries(detail.context || {}).filter(
                      ([key]) =>
                        ![
                          "owner_id",
                          "record_id",
                          "sha256",
                          "fingerprint",
                          "revision",
                        ].includes(key),
                    ),
                  )}
                />
              )}
              <h3>引用与依据</h3>
              {links(detail.references || [], "未登记直接引用。")}
              <h3>下游影响</h3>
              {links(
                detail.impacts || [],
                "当前登记关系中未发现直接下游影响。",
              )}
              <details>
                <summary>固定版本与技术信息</summary>
                <p className="id">
                  {detail.id} · {detail.owner_id || "未绑定"}
                </p>
                <pre>
                  {JSON.stringify(
                    {
                      fixed_ref: detail.fixed_ref,
                      verification: detail.verification,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </>
          ) : (
            !detailBusy &&
            !detailError && (
              <p>
                选择左侧记录或打开笔记编号引用，查看正文、上下文及双向关系。
              </p>
            )
          )}
        </section>
      </div>
    </>
  );
}
