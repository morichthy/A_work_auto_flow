import { createElement, memo, useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import Markdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkParse from "remark-parse";
import { unified } from "unified";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import "./research-document.css";
import { api } from "./api";
import type { MemoryRecord, Ref } from "../../schemas/memory-v4";

type SourceIssue = {
  target_id?: string;
  code: string;
  message?: string;
  record_id?: string;
};
type DocumentItem = {
  id: string;
  level: string;
  record: MemoryRecord;
  source_issues: SourceIssue[];
};
type ReportBlock =
  | {
      type: "prose";
      markdown: string;
      evidence_refs: Ref[];
      source_issues: SourceIssue[];
    }
  | {
      type: "detail" | "unit";
      ref: Ref;
      item: DocumentItem | null;
      resolved_blocks?: { block_id: string; markdown: string }[];
      source_issues: SourceIssue[];
    };
type ResolvedReport = {
  version: 1;
  title: string;
  record_id: string;
  revision: number;
  complete: boolean;
  sections: {
    section_id: string;
    title: string;
    role: string;
    blocks: ReportBlock[];
  }[];
};
type DocumentResult = {
  document_source?: string;
  document?: {
    record_id: string;
    revision: number;
    purpose: string;
    audience: string;
    scope: string;
  };
  owner_id: string;
  title: string;
  items: DocumentItem[];
  report?: ResolvedReport | null;
  missing: SourceIssue[];
  report_coverage?: {
    included_detail_ids: string[];
    uncovered_detail_ids: string[];
  };
  report_version_hints?: {
    record_id: string;
    revision: number;
    current_revision: number;
  }[];
  metrics: { elapsed_ms: number; read_memory_owners: number; records: number };
};
const headings: Record<string, string> = {
  L1: "详细研究与计算",
  L2: "尝试、观察与决策",
  L3: "经验与适用边界",
  L4: "研究地图与综合",
};

/** location.hash belongs to the workbench router, never to report anchors.
 * Preserve #/memory and keyboard navigation while moving the reading position. */
function scrollDocumentAnchor(event: MouseEvent<HTMLAnchorElement>) {
  event.preventDefault();
  const target = event.currentTarget.ownerDocument.getElementById(
    (event.currentTarget.getAttribute("href") || "").slice(1),
  );
  if (target) {
    target.scrollIntoView({ block: "start" });
    target.focus({ preventScroll: true });
  }
}

type MarkdownNode = {
  type: string;
  value?: string;
  url?: string;
  alt?: string;
  depth?: number;
  children?: MarkdownNode[];
  position?: { start: { offset?: number }; end: { offset?: number } };
};

/** Normalize common LaTeX delimiters before Markdown consumes their escapes.
 * Parser offsets protect literal inline/fenced/indented code byte for byte.
 * Existing dollar math and escaped currency are left to remark-math. */
function normalizeMathDelimiters(source: string) {
  const tree = unified().use(remarkParse).parse(source) as MarkdownNode;
  const protectedRanges: [number, number][] = [];
  function visit(node: MarkdownNode) {
    if (["code", "inlineCode"].includes(node.type)) {
      const start = node.position?.start.offset,
        end = node.position?.end.offset;
      if (start !== undefined && end !== undefined)
        protectedRanges.push([start, end]);
    } else node.children?.forEach(visit);
  }
  visit(tree);
  const convert = (text: string) =>
    text
      .replace(
        /\\\[([\s\S]*?)\\\]/g,
        (_match, formula: string) => `\n\n$$\n${formula.trim()}\n$$\n\n`,
      )
      .replace(
        /\\\(([^\n]*?)\\\)/g,
        (_match, formula: string) => `$${formula.trim()}$`,
      );
  let cursor = 0,
    result = "";
  for (const [start, end] of protectedRanges.sort((a, b) => a[0] - b[0])) {
    result += convert(source.slice(cursor, start)) + source.slice(start, end);
    cursor = end;
  }
  return result + convert(source.slice(cursor));
}
type ReadingOptions = {
  titles: string[];
  figureCount: number;
  normalize: boolean;
  figureStart: number;
  figureNumbers: Record<number, number>;
  appendUnplacedFigures: boolean;
};
const headingText = (node: MarkdownNode): string =>
  node.value || node.children?.map(headingText).join("") || "";
const titleKey = (text: string) => text.trim().replace(/\s+/g, "");

/** Work on parsed Markdown, so headings or image syntax in code fences are
 * untouched. Shared report titles appear once; nested headings retain relative
 * hierarchy. Only registered figures lacking an actual image node are appended. */
function readingMarkdown(options: ReadingOptions) {
  return (tree: MarkdownNode) => {
    const nodes = tree.children || [];
    if (
      options.normalize &&
      nodes[0]?.type === "heading" &&
      options.titles.some(
        (title) => titleKey(title) === titleKey(headingText(nodes[0])),
      )
    )
      nodes.shift();
    const headingsFound: MarkdownNode[] = [];
    const used = new Set<number>();
    const registerFigure = (index: number) => {
      if (index >= 0 && index < options.figureCount && !used.has(index)) {
        options.figureNumbers[index] = options.figureStart + used.size;
        used.add(index);
      }
    };
    const walk = (node: MarkdownNode) => {
      if (node.type === "heading") headingsFound.push(node);
      if (node.type === "image" && /^figure:\d+$/.test(node.url || ""))
        registerFigure(Number(node.url!.slice(7)));
      node.children?.forEach(walk);
    };
    walk(tree);
    if (options.normalize && headingsFound.length) {
      const base = Math.min(...headingsFound.map((node) => node.depth || 1));
      headingsFound.forEach((node) => {
        node.depth = Math.min(6, 3 + (node.depth || 1) - base);
      });
    }
    for (
      let index = 0;
      options.appendUnplacedFigures && index < options.figureCount;
      index++
    ) {
      if (!used.has(index)) {
        registerFigure(index);
        nodes.push({
          type: "paragraph",
          children: [{ type: "image", url: `figure:${index}`, alt: "" }],
        });
      }
    }
  };
}

/** Images can only reach the fixed-figure endpoint. Preserve precisely the
 * figure:N pseudo URL for image nodes; all other URLs use Markdown's sanitizer.
 * KaTeX trust=false also rejects URL/HTML commands embedded in equations. */
export const ResearchMarkdown = memo(
  function ResearchMarkdown({
    text,
    record,
    titles = [],
    normalize = false,
    figureStart = 1,
    appendUnplacedFigures = true,
    images,
  }: {
    text: string;
    record?: MemoryRecord;
    titles?: string[];
    normalize?: boolean;
    figureStart?: number;
    appendUnplacedFigures?: boolean;
    images?: readonly { index: number; caption: string; data_url: string }[];
  }) {
    const figures =
      record?.kind === "detail"
        ? (record.payload as { figures: { caption: string; ref: Ref }[] })
            .figures
        : [];
    // This render-local map is filled by the synchronous Markdown transform in
    // actual image order. It is not shared React state or a cross-render counter.
    const figureNumbers: Record<number, number> = {};
    return (
      <div className="research-markdown">
        <Markdown
          skipHtml
          remarkPlugins={[
            remarkGfm,
            remarkMath,
            [
              readingMarkdown,
              {
                titles,
                figureCount: figures.length,
                normalize,
                figureStart,
                figureNumbers,
                appendUnplacedFigures,
              },
            ],
          ]}
          rehypePlugins={[
            [
              rehypeKatex,
              {
                trust: false,
                strict: "warn",
                throwOnError: false,
                maxExpand: 1000,
              },
            ],
          ]}
          urlTransform={(url, key) =>
            key === "src" && /^figure:\d+$/.test(url)
              ? url
              : defaultUrlTransform(url)
          }
          components={{
            // A figure is a block element; avoid invalid <p><figure> nesting when
            // Markdown places an image inside a paragraph beside its explanation.
            p: ({ node, children }) =>
              createElement(
                node?.children.some(
                  (child) =>
                    child.type === "element" && child.tagName === "img",
                )
                  ? "div"
                  : "p",
                { className: "research-paragraph" },
                children,
              ),
            img: ({ src, alt }) => {
              const index = /^figure:\d+$/.test(src || "")
                ? Number(src!.slice(7))
                : -1;
              const embedded = images?.find((image) => image.index === index);
              if (
                embedded &&
                /^data:image\/(png|jpeg|webp);base64,/.test(embedded.data_url)
              )
                return (
                  <figure className="research-figure">
                    <img
                      src={embedded.data_url}
                      alt={embedded.caption}
                      loading="lazy"
                    />
                    <figcaption>
                      图 {index + 1}　{embedded.caption}
                    </figcaption>
                  </figure>
                );
              return record && figures[index] ? (
                <FixedFigure
                  record={record}
                  index={index}
                  caption={figures[index].caption}
                  number={figureNumbers[index]}
                  description={alt}
                />
              ) : (
                <span className="research-image-note">
                  {alt || "图片"}（未关联可读取的固定图示）
                </span>
              );
            },
            a: ({ href, children }) =>
              href?.startsWith("#/") ? (
                <a href={href}>{children}</a>
              ) : href?.startsWith("#") ? (
                <a href={href} onClick={scrollDocumentAnchor}>
                  {children}
                </a>
              ) : /^https?:\/\//i.test(href || "") ? (
                <a href={href} target="_blank" rel="noreferrer noopener">
                  {children}
                </a>
              ) : (
                <span>{children}</span>
              ),
          }}
        >
          {normalizeMathDelimiters(text)}
        </Markdown>
      </div>
    );
  },
  (previous, next) =>
    // The workbench polls status every five seconds. Preserving this subtree
    // keeps in-flight fixed-image requests mounted when only status changes.
    // Compare title values: callers naturally construct a new array per render.
    previous.text === next.text &&
    previous.record === next.record &&
    previous.images === next.images &&
    previous.normalize === next.normalize &&
    previous.figureStart === next.figureStart &&
    previous.appendUnplacedFigures === next.appendUnplacedFigures &&
    JSON.stringify(previous.titles || []) === JSON.stringify(next.titles || []),
);

function FixedFigure({
  record,
  index,
  caption,
  number,
  description,
}: {
  record: MemoryRecord;
  index: number;
  caption: string;
  number: number;
  description?: string;
}) {
  const [value, setValue] = useState<{ data_url: string } | null>(null);
  const [failure, setFailure] = useState("");
  useEffect(() => {
    let active = true;
    setValue(null);
    setFailure("");
    api<{ data_url: string }>("memory/figure", {
      owner_id: record.owner_id,
      record_id: record.record_id,
      revision: record.revision,
      figure_index: index,
    })
      .then((result) => {
        if (active) setValue(result);
      })
      .catch((error) => {
        if (active) setFailure(String(error));
      });
    return () => {
      active = false;
    };
  }, [record.owner_id, record.record_id, record.revision, index]);
  return (
    <figure className="research-figure">
      {value ? (
        <img src={value.data_url} alt={caption} loading="lazy" />
      ) : (
        <p role={failure ? "alert" : "status"}>
          {failure || "正在核对固定图片…"}
        </p>
      )}
      <figcaption>
        图 {number}　{caption}
        {description && !titleKey(caption).includes(titleKey(description)) && (
          <span className="research-figure-description">{description}</span>
        )}
      </figcaption>
    </figure>
  );
}

function Issues({
  issues,
  title = "来源版本或覆盖缺口",
}: {
  issues: SourceIssue[];
  title?: string;
}) {
  return issues.length ? (
    <aside className="research-warning">
      <strong>{title}</strong>
      <ul>
        {issues.map((issue, index) => (
          <li key={index}>
            {issue.message || issue.code}
            {issue.target_id || issue.record_id
              ? ` · ${issue.target_id || issue.record_id}`
              : ""}
          </li>
        ))}
      </ul>
    </aside>
  ) : null;
}

function FixedSources({ ownerId, refs }: { ownerId: string; refs: Ref[] }) {
  const [trace, setTrace] = useState("");
  const unique = refs.filter(
    (ref, i) =>
      refs.findIndex(
        (other) => JSON.stringify(other) === JSON.stringify(ref),
      ) === i,
  );
  return (
    <details className="research-sources">
      <summary>固定来源（{unique.length}）</summary>
      <ul>
        {unique.map((ref, i) => (
          <li key={i}>
            <code>
              {ref.target_id}
              {ref.revision ? ` · r${ref.revision}` : ""}
            </code>
            <button
              onClick={() =>
                api<{ context_text: string }>("memory/expand", {
                  refs: [ref],
                  selection: {
                    owner_id: ownerId,
                    purpose: "exploration",
                    budget: 16000,
                  },
                })
                  .then((result) => setTrace(result.context_text))
                  .catch((error) => setTrace(String(error)))
              }
            >
              读取固定来源
            </button>
          </li>
        ))}
      </ul>
      {trace && <pre className="memory-body">{trace}</pre>}
    </details>
  );
}

function recordRefs(record: MemoryRecord): Ref[] {
  const refs = [...record.sources];
  const collect = (value: unknown) => {
    if (Array.isArray(value)) value.forEach(collect);
    else if (value && typeof value === "object") {
      if ("target_kind" in value) refs.push(value as Ref);
      else Object.values(value).forEach(collect);
    }
  };
  collect(record.payload);
  return refs;
}

/** Schema v3 keeps technical prose in stable blocks. Earlier records retain
 * their original Markdown body and hashes; rendering does not migrate them. */
export function recordMarkdown(record: MemoryRecord): string {
  const blocks = (record.payload as { blocks?: { markdown?: string }[] })
    .blocks;
  return record.kind === "detail" && Array.isArray(blocks)
    ? blocks.map((block) => block.markdown || "").join("\n\n")
    : record.body_markdown;
}

function selectedFigureCount(text: string, total: number): number {
  const used = new Set<number>();
  const walk = (node: MarkdownNode) => {
    if (node.type === "image" && /^figure:\d+$/.test(node.url || "")) {
      const index = Number(node.url!.slice(7));
      if (index < total) used.add(index);
    }
    node.children?.forEach(walk);
  };
  // Parse actual image nodes; examples inside fenced code do not allocate numbers.
  walk(unified().use(remarkParse).use(remarkGfm).parse(text) as MarkdownNode);
  return used.size;
}

/** The narrative comes from the fixed detail revision. Structured metadata is
 * retained in the archive but is never mechanically repeated around its prose. */
function DetailBody({
  item,
  sectionTitle,
  figureStart,
  resolvedBlocks,
}: {
  item: DocumentItem;
  sectionTitle: string;
  figureStart: number;
  resolvedBlocks?: { block_id: string; markdown: string }[];
}) {
  // A selected block projection is display-only; never mutate the fixed record.
  const text = resolvedBlocks
    ? resolvedBlocks.map((block) => block.markdown).join("\n\n")
    : recordMarkdown(item.record);
  return (
    <div className="research-detail" data-record-id={item.record.record_id}>
      {text.trim() ? (
        <ResearchMarkdown
          text={text}
          record={item.record}
          titles={[item.record.title, sectionTitle]}
          normalize
          figureStart={figureStart}
          appendUnplacedFigures={!resolvedBlocks}
        />
      ) : (
        <p className="research-warning">
          此固定修订尚无可阅读正文，需补充研究记录。
        </p>
      )}
      <Issues issues={item.source_issues} />
    </div>
  );
}

function RecordArchive({ item }: { item: DocumentItem }) {
  const record = item.record;
  const p = record.payload as Record<string, unknown>;
  const [opened, setOpened] = useState(false);
  return (
    <details
      className="research-record"
      onToggle={(event) => setOpened(event.currentTarget.open)}
    >
      <summary>
        {item.level} · {record.title} · r{record.revision}
      </summary>
      {opened && (
        <div>
          <p className="research-meta">
            修订 {record.revision} · 首次保存于 {record.created_at}
            {record.updated_at ? ` · 本次修订于 ${record.updated_at}` : ""}
            {typeof p.occurred_at === "string" && p.occurred_at.trim()
              ? ` · 发生时间：${p.occurred_at}`
              : " · 发生时间未知"}
          </p>
          <ResearchMarkdown
            text={recordMarkdown(record)}
            record={record.kind === "detail" ? record : undefined}
            normalize
          />
          <Issues issues={item.source_issues} />
          <FixedSources ownerId={record.owner_id} refs={recordRefs(record)} />
          <details>
            <summary>结构化字段与修订标识</summary>
            <pre className="memory-body">
              {JSON.stringify(
                {
                  record_id: record.record_id,
                  revision: record.revision,
                  record_hash: record.record_hash,
                  payload: record.payload,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </div>
      )}
    </details>
  );
}

export function ResearchDocument({ ownerId }: { ownerId: string }) {
  const [document, setDocument] = useState<DocumentResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [documentType, setDocumentType] = useState("research_process");
  const [loadedType, setLoadedType] = useState("");
  const [contextText, setContextText] = useState("");
  const [contextManifest, setContextManifest] = useState<{
    complete?: boolean;
    omitted?: unknown[];
    missing?: unknown[];
    required_not_full?: unknown[];
    budget?: { max_chars: number; used_chars: number };
  } | null>(null);
  const [impact, setImpact] = useState<{
    changes: { message: string; section_ids: string[] }[];
    uncovered_unit_ids: string[];
  } | null>(null);
  const sequence = useRef(0);
  // Allocate each resolved detail's registered figures in authored block order.
  // Individual Markdown transforms determine order inside their own body.
  const figureStarts = new Map<ReportBlock, number>();
  let nextFigure = 1;
  document?.report?.sections.forEach((section) =>
    section.blocks.forEach((block) => {
      if (block.type !== "prose" && block.item) {
        figureStarts.set(block, nextFigure);
        const total = (block.item.record.payload as { figures: unknown[] })
          .figures.length;
        nextFigure +=
          block.type === "unit"
            ? selectedFigureCount(
                (block.resolved_blocks || [])
                  .map((value) => value.markdown)
                  .join("\n\n"),
                total,
              )
            : total;
      }
    }),
  );
  useEffect(() => {
    sequence.current++;
    setDocument(null);
    setError("");
    setBusy(false);
    setArchiveOpen(false);
    setContextText("");
    setContextManifest(null);
    setImpact(null);
    setLoadedType("");
    // 文稿类型是下一次显式读取的参数，切换它不丢弃当前已读文章。
  }, [ownerId]);
  async function load() {
    const current = ++sequence.current;
    setBusy(true);
    setError("");
    try {
      const value = await api<DocumentResult>("memory/document", {
        owner_id: ownerId,
        document_type: documentType,
      });
      if (current === sequence.current) {
        setDocument(value);
        setLoadedType(documentType);
        setContextText("");
        setContextManifest(null);
        setImpact(null);
        setArchiveOpen(false);
      }
    } catch (reason) {
      if (current === sequence.current) setError(String(reason));
    } finally {
      if (current === sequence.current) setBusy(false);
    }
  }
  async function inspectDocument(
    action: "section-context" | "document-impact",
    sectionId?: string,
  ) {
    if (!document?.document) return;
    const current = sequence.current;
    try {
      const result = await api<{
        context_text: string;
        manifest: typeof contextManifest;
        changes: { message: string; section_ids: string[] }[];
        uncovered_unit_ids: string[];
      }>(`memory/${action}`, {
        owner_id: ownerId,
        document_id: document.document.record_id,
        revision: document.document.revision,
        ...(sectionId
          ? { section_id: sectionId, budget: { max_chars: 20000 } }
          : {}),
      });
      if (current !== sequence.current) return;
      if (action === "section-context") {
        setContextText(result.context_text);
        setContextManifest(result.manifest);
      } else setImpact(result);
    } catch (reason) {
      if (current === sequence.current) setError(String(reason));
    }
  }
  return (
    <section className="research-document">
      <h2>研究经过</h2>
      <p>阅读已编排的研究报告，按需追溯实验记录与固定来源。</p>
      <label>
        文稿类型{" "}
        <select
          aria-label="文稿类型"
          disabled={busy}
          value={documentType}
          onChange={(event) => setDocumentType(event.target.value)}
        >
          <option value="research_process">完整研究过程</option>
          <option value="research_report">精简研究报告</option>
        </select>
      </label>
      <button disabled={busy || !ownerId} onClick={load}>
        {busy ? "正在读取研究报告…" : "读取研究经过"}
      </button>
      {document && loadedType !== documentType && (
        <p className="muted">
          当前保留上次读取的
          {loadedType === "research_process" ? "完整研究过程" : "精简研究报告"}
          ，点击“读取研究经过”后更新。
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {document && (
        <>
          {document.report ? (
            <>
              <header className="research-title">
                <h1>{document.report.title}</h1>
                {document.document && (
                  <p>
                    {document.document.purpose} · 读者：
                    {document.document.audience} · 范围：
                    {document.document.scope}
                  </p>
                )}
              </header>
              {document.document && (
                <button onClick={() => inspectDocument("document-impact")}>
                  检查文稿更新影响
                </button>
              )}
              {impact && (
                <aside className="research-warning">
                  <strong>文稿更新检查</strong>
                  {impact.changes.length ? (
                    <ul>
                      {impact.changes.map((change, index) => (
                        <li key={index}>{change.message}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>固定依据未发现更新。</p>
                  )}
                  {!!impact.uncovered_unit_ids.length && (
                    <p>
                      尚未编入的技术单元：{impact.uncovered_unit_ids.join("、")}
                    </p>
                  )}
                </aside>
              )}
              {!document.report.complete && (
                <p className="research-warning">
                  报告存在未能读取或未覆盖的依据，请结合下方提示阅读。
                </p>
              )}
              <div className="research-layout">
                <nav aria-label="研究文稿目录">
                  <strong>目录</strong>
                  <ol>
                    {document.report.sections.map((section) => (
                      <li key={section.section_id}>
                        <a
                          href={`#report-${section.section_id}`}
                          onClick={scrollDocumentAnchor}
                        >
                          {section.title}
                        </a>
                      </li>
                    ))}
                  </ol>
                </nav>
                <div className="research-paper">
                  {document.report.sections.map((section, index) => (
                    <section
                      id={`report-${section.section_id}`}
                      key={section.section_id}
                      tabIndex={-1}
                      data-role={section.role}
                    >
                      <h2>
                        <span className="research-section-number">
                          {index + 1}.
                        </span>{" "}
                        {section.title}
                      </h2>
                      {document.document && (
                        <button
                          onClick={() =>
                            inspectDocument(
                              "section-context",
                              section.section_id,
                            )
                          }
                        >
                          读取本章写作上下文
                        </button>
                      )}
                      {section.blocks.map((block, blockIndex) => (
                        <div key={blockIndex} className="research-block">
                          {block.type === "prose" ? (
                            <ResearchMarkdown
                              text={block.markdown}
                              titles={[section.title]}
                              normalize
                            />
                          ) : block.item ? (
                            <DetailBody
                              item={block.item}
                              sectionTitle={section.title}
                              figureStart={figureStarts.get(block) || 1}
                              resolvedBlocks={
                                block.type === "unit"
                                  ? block.resolved_blocks || []
                                  : undefined
                              }
                            />
                          ) : (
                            !block.source_issues.length && (
                              <Issues
                                issues={[
                                  {
                                    code: "固定实验正文不可读取",
                                    target_id: block.ref.target_id,
                                  },
                                ]}
                              />
                            )
                          )}
                          <Issues issues={block.source_issues} />
                        </div>
                      ))}
                    </section>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <p className="research-empty">
              尚未编排研究报告。可展开下方记录与来源查看已保存内容。
            </p>
          )}
          <Issues issues={document.missing} title="报告覆盖与依据提示" />
          {contextText && (
            <details open className="research-sources">
              <summary>章节写作上下文</summary>
              {contextManifest && (
                <p>
                  {contextManifest.complete
                    ? "所选上下文完整。"
                    : "存在未读或省略内容，请核对清单后写作。"}
                  {contextManifest.budget
                    ? ` 字符 ${contextManifest.budget.used_chars}/${contextManifest.budget.max_chars}`
                    : ""}
                </p>
              )}
              <button
                onClick={() =>
                  navigator.clipboard
                    .writeText(contextText)
                    .catch((reason) => setError(String(reason)))
                }
              >
                复制章节上下文
              </button>
              <pre className="memory-body">{contextText}</pre>
              {contextManifest && (
                <details>
                  <summary>阅读范围、遗漏与依据</summary>
                  <pre className="memory-body">
                    {JSON.stringify(contextManifest, null, 2)}
                  </pre>
                </details>
              )}
            </details>
          )}
          {document.report &&
            !!document.report_coverage?.uncovered_detail_ids.length && (
              <aside className="research-warning">
                <strong>尚未纳入报告的详细记录</strong>
                <ul>
                  {document.report_coverage.uncovered_detail_ids.map((id) => (
                    <li key={id}>
                      {document.items.find((item) => item.id === id)?.record
                        .title || id}
                    </li>
                  ))}
                </ul>
              </aside>
            )}
          {!!document.report_version_hints?.length && (
            <aside className="research-warning">
              <strong>报告保留固定修订</strong>
              <ul>
                {document.report_version_hints.map((hint, index) => (
                  <li key={index}>
                    {hint.record_id}：正文使用 r{hint.revision}，现有 r
                    {hint.current_revision}；未自动替换。
                  </li>
                ))}
              </ul>
            </aside>
          )}
          <details
            className="research-archive"
            onToggle={(event) => setArchiveOpen(event.currentTarget.open)}
          >
            <summary>记录与来源（{document.items.length} 条记录）</summary>
            {archiveOpen && (
              <>
                <p>
                  此处保留分层记录及修订信息。报告中的固定引用以报告指定版本为准；正式结论有效性须单独复核。
                </p>
                {document.report && (
                  <details className="research-report-sources">
                    <summary>报告编排与段落来源</summary>
                    <p className="research-meta">
                      {document.report.record_id} · r{document.report.revision}
                    </p>
                    {document.report.sections.map((section) => (
                      <div key={section.section_id}>
                        <h3>{section.title}</h3>
                        {section.blocks.map((block, index) => (
                          <FixedSources
                            key={index}
                            ownerId={ownerId}
                            refs={
                              block.type === "prose"
                                ? block.evidence_refs
                                : [block.ref]
                            }
                          />
                        ))}
                      </div>
                    ))}
                  </details>
                )}
                {Object.entries(headings).map(([level, title]) => (
                  <section key={level}>
                    <h3>
                      {level} {title}
                    </h3>
                    {document.items
                      .filter((item) => item.level === level)
                      .map((item) => (
                        <RecordArchive key={item.id} item={item} />
                      ))}
                  </section>
                ))}
              </>
            )}
          </details>
        </>
      )}
    </section>
  );
}
