import { describe, it, expect, vi, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
  cleanup,
} from "@testing-library/react";
import { ResearchMarkdown, ResearchDocument } from "./ResearchDocument";
import { layerGraph } from "./graph-model";
import { api } from "./api";
vi.mock("./api", () => ({ api: vi.fn() }));
afterEach(cleanup);
it("围栏代码中的公式定界符不转换，普通未定界表达式不猜测", () => {
  const content = [
    "```text",
    String.raw`\[code=1\]`,
    "```",
    "s_0=0，s_i=fl(s_{i-1}+x_i)",
  ].join("\n");
  const view = render(<ResearchMarkdown text={content} />);
  expect(view.container.querySelector("code")?.textContent).toContain(
    String.raw`\[code=1\]`,
  );
  expect(view.container.querySelectorAll(".katex")).toHaveLength(0);
});

it("兼容LaTeX括号分隔符且保留代码，编号证据链接交给路由", () => {
  const view = render(
    <ResearchMarkdown
      text={[
        String.raw`行内 \(x^2\)，展示 \[y=\frac{1}{2}\]。`,
        "原有 $z=3$。",
        "`\\(code\\)`",
        "[1](#/evidence?id=MEM-ONE&revision=2)",
      ].join("\n\n")}
    />,
  );
  expect(view.container.querySelectorAll(".katex")).toHaveLength(3);
  expect(view.container.querySelector("code")?.textContent).toBe(
    String.raw`\(code\)`,
  );
  const link = screen.getByRole("link", { name: "1" });
  expect(link).toHaveAttribute("href", "#/evidence?id=MEM-ONE&revision=2");
  expect(fireEvent.click(link)).toBe(true);
});

const record = {
  record_id: "MEM-DETAIL",
  owner_id: "RES-R",
  kind: "detail",
  revision: 2,
  title: "合成计算步骤",
  created_at: "2026-09-09",
  updated_at: "2026-09-10",
  record_hash: "abc",
  sources: [],
  body_markdown:
    "# 合成计算步骤\n\n## 可复核过程\n\n样本项数为 3。\n\n| 参数 | 值 |\n|---|---|\n| n | 3 |\n\n$$\ns=\\sum_i x_i\n$$\n\n![误差比较图](figure:0)\n\n结果为 3；不代表全部输入稳定。",
  payload: {
    question: "求和问题",
    method: "补偿求和",
    steps: ["先固定输入", "再计算误差"],
    inputs: [],
    parameters: [
      { name: "n", value: 3, unit: "1", description: "不应重复的结构化参数" },
    ],
    formulas: [
      {
        latex: "s=\\sum_i x_i",
        variables: [{ symbol: "s", meaning: "求和结果", unit: "1" }],
      },
    ],
    figures: [
      {
        caption: "误差比较图",
        ref: { target_kind: "file", target_id: "SRC-1" },
      },
    ],
    results: "不应重复的结构化结果",
    limitations: ["不应重复的结构化限制"],
  },
};
const item = { id: record.record_id, level: "L1", record, source_issues: [] };
const ref = {
  target_kind: "record",
  target_id: record.record_id,
  revision: 2,
  sha256: "abc",
  relation: "references",
  locator: "",
};
const report = {
  version: 1,
  title: "合成误差研究报告",
  record_id: "MEM-MAP",
  revision: 1,
  complete: true,
  sections: [
    {
      section_id: "scope",
      title: "问题与范围",
      role: "introduction",
      blocks: [
        {
          type: "prose",
          markdown: "从共同问题开始。",
          evidence_refs: [],
          source_issues: [],
        },
      ],
    },
    {
      section_id: "experiment",
      title: "实验设计与观察",
      role: "experiment",
      blocks: [
        {
          type: "prose",
          markdown: "因此需要下面的具体计算。",
          evidence_refs: [ref],
          source_issues: [],
        },
        { type: "detail", ref, item, source_issues: [] },
      ],
    },
    {
      section_id: "discussion",
      title: "讨论与边界",
      role: "discussion",
      blocks: [
        {
          type: "prose",
          markdown: "跨实验讨论必须放在实验后。",
          evidence_refs: [ref],
          source_issues: [],
        },
      ],
    },
  ],
};
function mockDocument(value: unknown) {
  vi.mocked(api).mockImplementation(
    async (route) =>
      (route === "memory/figure"
        ? { data_url: "data:image/png;base64,iVBORw0KGgo=" }
        : value) as never,
  );
}
const document = {
  owner_id: "RES-R",
  title: "合成研究",
  items: [item],
  report,
  missing: [],
  metrics: { elapsed_ms: 5, read_memory_owners: 1, records: 1 },
};

describe("研究报告的连续阅读与证据边界", () => {
  it("keeps delayed fixed images mounted across parent status refreshes", async () => {
    let complete: (value: unknown) => void = () => {};
    vi.mocked(api).mockReset();
    vi.mocked(api).mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }) as never,
    );
    const props = {
      text: "![固定图](figure:0)",
      record: record as never,
      normalize: true,
    };
    const { rerender } = render(
      <ResearchMarkdown {...props} titles={["固定标题"]} />,
    );
    expect(api).toHaveBeenCalledTimes(1);
    rerender(<ResearchMarkdown {...props} titles={["固定标题"]} />);
    rerender(<ResearchMarkdown {...props} titles={["固定标题"]} />);
    expect(api).toHaveBeenCalledTimes(1);
    complete({ data_url: "data:image/png;base64,iVBORw0KGgo=" });
    await screen.findByRole("img", { name: "误差比较图" });
  });
  it("reads independent documents with selected unit blocks and chapter context", async () => {
    const selected = {
      ...record,
      body_markdown: "",
      payload: {
        ...record.payload,
        blocks: [
          { block_id: "definitions", markdown: "变量单位为米。" },
          { block_id: "result", markdown: "实际选择结果。" },
          { block_id: "other", markdown: "未选择的附录。 ![](figure:0)" },
        ],
      },
    };
    const value = {
      ...document,
      document_source: "independent",
      document: {
        record_id: "MEM-DOC",
        revision: 2,
        purpose: "解释计算",
        audience: "研究员",
        scope: "构造输入",
      },
      report: {
        ...report,
        sections: [
          {
            section_id: "MEM-SECTION",
            title: "独立结果章",
            role: "experiment",
            blocks: [
              {
                type: "unit",
                ref,
                item: { ...item, record: selected },
                resolved_blocks: selected.payload.blocks.slice(0, 2),
                source_issues: [],
              },
            ],
          },
        ],
      },
    };
    vi.mocked(api).mockImplementation(async (route, request) => {
      if (route === "memory/section-context")
        return { context_text: "章节固定上下文：变量单位为米。" } as never;
      if (route === "memory/document-impact")
        return {
          changes: [
            { message: "技术单元已有新修订", section_ids: ["MEM-SECTION"] },
          ],
          uncovered_unit_ids: [],
        } as never;
      return {
        ...value,
        report: {
          ...value.report,
          title:
            (request as { document_type: string }).document_type ===
            "research_report"
              ? "简版文稿"
              : "完整文稿",
        },
      } as never;
    });
    const { container } = render(<ResearchDocument ownerId="RES-R" />);
    fireEvent.click(screen.getByRole("button", { name: "读取研究经过" }));
    await screen.findByRole("heading", { name: "完整文稿" });
    expect(screen.getByText("变量单位为米。")).toBeVisible();
    expect(screen.queryByText(/未选择的附录/)).toBeNull();
    expect(container.querySelector("figure")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "读取本章写作上下文" }));
    await screen.findByText("章节固定上下文：变量单位为米。");
    fireEvent.click(screen.getByRole("button", { name: "检查文稿更新影响" }));
    await screen.findByText("技术单元已有新修订");
    fireEvent.change(screen.getByRole("combobox", { name: "文稿类型" }), {
      target: { value: "research_report" },
    });
    expect(screen.getByRole("heading", { name: "完整文稿" })).toBeVisible();
    expect(screen.getByText(/当前保留上次读取/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "读取研究经过" }));
    await screen.findByRole("heading", { name: "简版文稿" });
    expect(screen.queryByText("章节固定上下文：变量单位为米。")).toBeNull();
    expect(selected.body_markdown).toBe("");
  });
  it("renders equations and tables without HTML execution or arbitrary images", () => {
    const { container } = render(
      <ResearchMarkdown
        text={
          "## 合成方法\n\n计算 $s=\\sum_i x_i$。\n\n| 参数 | 值 |\n|---|---|\n| n | 3 |\n\n<script>window.bad=1</script>\n\n![禁止自动下载](https://invalid.example/x.png)\n\n[坏链接](javascript:alert(1))\n\n$$\\href{javascript:alert(1)}{x}$$"
        }
      />,
    );
    expect(screen.getByRole("heading", { name: "合成方法" })).toBeVisible();
    expect(screen.getByRole("table")).toBeVisible();
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    cleanup();
  });
  it("reads authored order once, embeds a controlled figure, and keeps metadata in the archive", async () => {
    mockDocument(document);
    const { container } = render(<ResearchDocument ownerId="RES-R" />);
    fireEvent.click(screen.getByRole("button", { name: "读取研究经过" }));
    await screen.findByRole("heading", { name: "合成误差研究报告" });
    const paper = container.querySelector(".research-paper")!;
    expect(
      [...paper.querySelectorAll("section > h2")].map(
        (node) => node.textContent,
      ),
    ).toEqual(["1. 问题与范围", "2. 实验设计与观察", "3. 讨论与边界"]);
    expect(paper.querySelectorAll(".katex-display")).toHaveLength(1);
    expect(paper.querySelectorAll("table")).toHaveLength(1);
    expect(paper).not.toHaveTextContent("不应重复");
    expect(paper).not.toHaveTextContent("合成计算步骤");
    expect(paper.querySelector("h3")).toHaveTextContent("可复核过程");
    expect(paper.querySelector(".research-meta")).toBeNull();
    await waitFor(() =>
      expect(
        within(paper as HTMLElement).getByRole("img", { name: "误差比较图" }),
      ).toHaveAttribute("src", expect.stringContaining("data:image/png")),
    );
    expect(paper.querySelectorAll("figure")).toHaveLength(1);
    // Metadata and duplicate archival bodies do not mount until requested.
    expect(container.querySelector(".research-record")).toBeNull();
    fireEvent.click(screen.getByText("记录与来源（1 条记录）"));
    await screen.findByText("L1 · 合成计算步骤 · r2");
    fireEvent.click(screen.getByText("L1 · 合成计算步骤 · r2"));
    await waitFor(() =>
      expect(
        container.querySelector(".research-record .research-meta"),
      ).toHaveTextContent(
        "首次保存于 2026-09-09 · 本次修订于 2026-09-10 · 发生时间未知",
      ),
    );
    cleanup();
  });
  it("labels an uncomposed legacy object and appends its unplaced registered figure once", async () => {
    mockDocument({
      ...document,
      report: null,
      items: [
        {
          ...item,
          record: { ...record, body_markdown: "旧版正文，图示尚无内嵌占位。" },
        },
      ],
    });
    const { container } = render(<ResearchDocument ownerId="RES-R" />);
    fireEvent.click(screen.getByRole("button", { name: "读取研究经过" }));
    await screen.findByText(/尚未编排研究报告/);
    expect(container.querySelector(".research-paper")).toBeNull();
    fireEvent.click(screen.getByText("记录与来源（1 条记录）"));
    fireEvent.click(await screen.findByText("L1 · 合成计算步骤 · r2"));
    await screen.findByRole("img", { name: "误差比较图" });
    expect(container.querySelectorAll("figure")).toHaveLength(1);
    cleanup();
  });
  it("filters raw/legacy graph nodes before traversal; higher layers are opt-in", () => {
    const graph = {
      schema_version: 1,
      fingerprint: "x",
      generated_at: "synthetic",
      errors: [],
      coverage: {},
      nodes: ["L0", "L1", "L2", "L3", "L4", null].map((level, i) => ({
        id: String(i),
        title: "row",
        kind: "memory",
        level,
        path: "",
        fingerprint: "x",
        keywords: [],
        review: {},
        risks: [],
      })),
      edges: [],
    } as Parameters<typeof layerGraph>[0];
    expect(layerGraph(graph, ["L1"]).nodes.map((v) => v.level)).toEqual(["L1"]);
    expect(
      layerGraph(graph, ["L1", "L3", "native"]).nodes.map((v) => v.level),
    ).toEqual(["L1", "L3", null]);
  });
});
