import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { MaterialQuery, defaultBudget, materialRequest } from "./MaterialQuery";
import type {
  Candidate,
  Result,
  SearchReceipt,
} from "./generated/material-query";

vi.mock("./api", () => ({ api: vi.fn(), download: vi.fn() }));
const mockApi = vi.mocked(api);
const ref = {
  kind: "record" as const,
  id: "MEM-SYN-ONE",
  revision: 1,
  sha256: "a".repeat(64),
  locator: null,
};
const candidate: Candidate = {
  candidate_id: "C-1",
  refs: [ref],
  title: "合成压力材料",
  excerpt: "固定版本摘录",
  channels: ["lexical"],
  score: 1,
  realization: {
    definition: { key: "full", version: "1" },
    refs: [ref],
    state: "direct",
    missing_selectors: [],
    generator_version: null,
  },
  evidence_status: "unreviewed",
  group: "direct",
};
const receipt: SearchReceipt = {
  query_id: "Q-1",
  request_digest: "digest-1",
  candidates: [candidate],
  next_cursor: null,
  expires_at: "2026-09-10T12:00:00Z",
  gaps: [],
};
function ok<T>(value: T): Result<T> {
  return {
    status: "ok",
    value,
    code: null,
    warnings: [],
    consumed: defaultBudget,
    stop_reason: null,
    basis: null,
  };
}
function defaultResponse(route: string) {
  if (route === "materials/capabilities")
    return {
      enabled: true,
      definitions_version: "1",
      association: {
        modes: ["off", "existing_only"],
        strategy: "existing-relations",
        version: "1",
      },
      deepening: {
        modes: ["source_mapping", "bounded_graph"],
        strategy: "bounded-bfs",
        version: "1",
      },
      maintenance: { task_package: true },
      default_budget: defaultBudget,
      limits: { ...defaultBudget, candidates: 2000 },
      channels: ["identity", "lexical"],
    };
  if (route === "representations/definitions")
    return ok([
      {
        ref: { key: "full", version: "1" },
        title: "全文",
        purpose_description: "完整记录",
        rules: [],
        output_sections: [],
        generation: "never",
      },
    ]);
  if (route === "materials/structure")
    return ok({
      nodes: [
        {
          ref: null,
          node_id: "RES-SYN",
          parent_id: null,
          title: "合成研究",
          kind: "owner",
          layer: null,
          has_children: false,
          storage_role: "canonical",
          registered_path: null,
        },
      ],
      next_cursor: null,
    });
  if (route === "materials/start")
    return ok({ query_id: "Q-1", state: "running" });
  if (route === "materials/poll") return ok(receipt);
  if (route === "materials/cancel")
    return { ...ok(null), status: "cancelled", code: "CANCELLED" };
  throw Error(`Unexpected route: ${route}`);
}
beforeEach(() => {
  mockApi.mockImplementation(async (route) => defaultResponse(route) as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
async function start() {
  fireEvent.click(await screen.findByRole("button", { name: /合成研究/ }));
  fireEvent.change(screen.getByLabelText("问题"), {
    target: { value: "压力" },
  });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "开始查询" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "开始查询" }));
  await screen.findByText("合成压力材料");
}

describe("材料查询固定范围与回执", () => {
  it("新查询采用工作区设置的结果数与预算", async () => {
    mockApi.mockImplementation(async (route) => {
      const value = defaultResponse(route);
      return (route === "materials/capabilities"
        ? { ...value, default_result_limit: 7, default_budget: { ...defaultBudget, output_chars: 4000 } }
        : value) as never;
    });
    render(<MaterialQuery />);
    await start();
    const request = mockApi.mock.calls.find(([route]) => route === "materials/start")![1] as any;
    expect(request.result_limit).toBe(7);
    expect(request.budget.output_chars).toBe(4000);
  });

  it("标准类型可单选多选，所有来源与旧版显式选择，默认预算五分钟", async () => {
    render(<MaterialQuery />);
    await screen.findByRole("button", { name: /合成研究/ });
    expect(screen.getByLabelText("记录版本")).toHaveValue("current");
    expect(screen.getByText(/读取时间预算：5 分钟/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "清空类型" }));
    fireEvent.click(screen.getByLabelText("类型：Research 研究"));
    fireEvent.click(screen.getByLabelText("类型：Project 项目"));
    fireEvent.change(screen.getByLabelText("内容来源"), {
      target: { value: "all" },
    });
    fireEvent.change(screen.getByLabelText("记录版本"), {
      target: { value: "allow_stale" },
    });
    fireEvent.change(screen.getByLabelText("问题"), {
      target: { value: "压力" },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始查询" }));
    await screen.findByText("合成压力材料");
    const request = mockApi.mock.calls.find(
      ([route]) => route === "materials/start",
    )![1] as any;
    expect(request.scope.owner_types).toEqual(["research", "project"]);
    expect(request.scope.owner_ids).toBeNull();
    expect(request.content_source).toBe("all");
    expect(request.freshness).toBe("allow_stale");
    expect(request.budget.wall_ms).toBe(300000);
  });

  it("完整文稿按钮位于候选上方，后续失败清除旧正文并在右侧说明", async () => {
    mockApi.mockImplementation(async (route) => {
      if (route === "materials/documents")
        return ok({
          packet_id: "P-DOC",
          query_id: "Q-1",
          definition: { key: "full", version: "1" },
          parts: [
            {
              group: "direct",
              heading: "章节正文",
              markdown: "作者编排的完整正文\n\n![图示](figure:0)",
              refs: [ref],
              selectors: [],
              omitted: [],
              figures: [
                {
                  index: 0,
                  caption: "固定图示",
                  ref,
                  data_url: "data:image/png;base64,AAAA",
                },
              ],
            },
          ],
          contributors: [ref],
          complete: true,
          canonical: false,
          documents: [
            {
              ref,
              title: "完整合成文稿",
              candidate_ids: ["C-1"],
              complete: true,
              part_indices: [0],
            },
          ],
        }) as never;
      if (route === "materials/assemble")
        return {
          ...ok(null),
          status: "rejected",
          code: "STALE",
          warnings: ["固定记录已更新"],
        } as never;
      return defaultResponse(route) as never;
    });
    render(<MaterialQuery />);
    await start();
    const candidateControl = screen.getByRole("checkbox", {
      name: "合成压力材料",
    });
    fireEvent.click(candidateControl);
    const action = screen.getByRole("button", { name: "返回完整文稿" });
    expect(
      action.compareDocumentPosition(candidateControl) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.click(action);
    const output = screen.getByRole("complementary", { name: "查询返回结果" });
    await within(output).findByText("作者编排的完整正文");
    expect(
      within(output).getByRole("img", { name: "固定图示" }),
    ).toHaveAttribute("src", "data:image/png;base64,AAAA");
    expect(mockApi).toHaveBeenCalledWith("materials/documents", {
      query_id: "Q-1",
      candidate_ids: ["C-1"],
      expected_request_digest: "digest-1",
      document_type: "research_process",
    });
    fireEvent.click(screen.getByRole("button", { name: "组装所选材料（1）" }));
    await within(output).findByText("固定记录已更新");
    expect(
      within(output).queryByText("作者编排的完整正文"),
    ).not.toBeInTheDocument();
  });

  it("默认查概览与经验，展开沿用固定查询；取消树选择不扩大范围", async () => {
    mockApi.mockImplementation(async (route) =>
      route === "materials/expand"
        ? (ok({
            candidates: [],
            edges: [],
            proposals: [],
            next_cursor: null,
            gaps: ["无固定关联"],
          }) as never)
        : (defaultResponse(route) as never),
    );
    render(<MaterialQuery />);
    expect(screen.getByLabelText("内容来源")).toHaveValue(
      "overview_experience",
    );
    expect(screen.queryByLabelText("表达形式")).not.toBeInTheDocument();
    await start();
    const request = mockApi.mock.calls.find(
      ([route]) => route === "materials/start",
    )![1] as any;
    expect(request.content_source).toBe("overview_experience");
    expect(request.scope.levels).toBeNull();
    expect(request.definition.key).toBe("full");
    fireEvent.click(screen.getByRole("checkbox", { name: "合成压力材料" }));
    fireEvent.click(screen.getByRole("button", { name: "展开技术内容" }));
    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith("materials/expand", {
        query_id: "Q-1",
        candidate_ids: ["C-1"],
        expected_request_digest: "digest-1",
        target: "technical",
        include_packet: true,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /合成研究/ }));
    expect(screen.getByText(/空范围，请选择归属对象/)).toBeVisible();
    expect(screen.getByRole("button", { name: "展开技术内容" })).toBeDisabled();
  });
  it("显式区分空范围、全局范围和树中所选归属，不隐式扩大查询", async () => {
    render(<MaterialQuery />);
    // 用户可把依赖读取显式收紧到所选范围；默认跨对象依赖由分类用例覆盖。
    fireEvent.click(screen.getByLabelText(/读取所选材料引用的必要依据/));
    expect(screen.getByLabelText("结构视图")).toHaveValue("logical");
    expect(screen.getByText(/空范围，请选择归属对象/)).toBeVisible();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "开始查询" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "开始查询" }));
    await screen.findByText("合成压力材料");
    const empty = mockApi.mock.calls.find(
      ([route]) => route === "materials/start",
    )![1] as any;
    expect(empty.scope.owner_ids).toEqual([]);
    expect(empty.scope_ceiling.owner_ids).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "全局获准范围" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "开始查询" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "开始查询" }));
    await screen.findByText("合成压力材料");
    const first = mockApi.mock.calls.filter(
      ([route]) => route === "materials/start",
    )[1][1] as any;
    expect(first.scope.owner_ids).toBeNull();
    expect(first.scope_ceiling.owner_ids).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /合成研究/ }));
    expect(screen.getByText(/下方是上一次结果/)).toBeVisible();
    expect(screen.getByRole("button", { name: /组装所选材料/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "开始查询" }));
    await waitFor(() =>
      expect(
        mockApi.mock.calls.filter(([route]) => route === "materials/start"),
      ).toHaveLength(3),
    );
    const second = mockApi.mock.calls.filter(
      ([route]) => route === "materials/start",
    )[2][1] as any;
    expect(second.scope.owner_ids).toEqual(["RES-SYN"]);
    expect(second.scope_ceiling).toEqual(second.scope);
    expect(second.definition.version).toBe("1");
  });

  it("候选选择传递查询摘要，材料包四区独立保留部分结果与缺口", async () => {
    mockApi.mockImplementation(async (route) =>
      route === "materials/assemble"
        ? ({
            ...ok({
              packet_id: "P-1",
              query_id: "Q-1",
              definition: { key: "full", version: "1" },
              parts: [
                {
                  group: "direct",
                  heading: "压力依据",
                  markdown: "正文 $p=F/A$",
                  refs: [ref],
                  selectors: ["body"],
                  omitted: [],
                },
                {
                  group: "gaps",
                  heading: "审查缺口",
                  markdown: "尚未完成现实检验",
                  refs: [],
                  selectors: [],
                  omitted: ["review"],
                },
              ],
              contributors: [ref],
              complete: false,
              canonical: false,
            }),
            status: "partial",
            code: "BUDGET_EXCEEDED",
            stop_reason: "output_chars",
            warnings: ["输出达到预算"],
          } as never)
        : (defaultResponse(route) as never),
    );
    render(<MaterialQuery />);
    await start();
    fireEvent.click(screen.getByRole("checkbox", { name: "合成压力材料" }));
    fireEvent.click(screen.getByRole("button", { name: "组装所选材料（1）" }));
    await screen.findByText("压力依据");
    expect(mockApi).toHaveBeenCalledWith("materials/assemble", {
      query_id: "Q-1",
      candidate_ids: ["C-1"],
      expected_request_digest: "digest-1",
    });
    const packet = screen.getByRole("region", { name: "材料包" });
    for (const name of ["直接材料", "必要上下文", "关联建议", "缺口与限制"])
      expect(within(packet).getByRole("region", { name })).toBeVisible();
    expect(screen.getByText("部分完成")).toBeVisible();
    expect(screen.getByText("停止原因：output_chars")).toBeVisible();
    expect(screen.getByText("尚未完成现实检验")).toBeVisible();
    expect(packet.querySelector(".katex")).not.toBeNull();
  });

  it("条件改变后迟到的轮询不能覆盖新查询", async () => {
    let resolveOld!: (value: unknown) => void;
    let starts = 0;
    mockApi.mockImplementation(async (route, data: any) => {
      if (route === "materials/start")
        return ok({ query_id: `Q-${++starts}`, state: "running" }) as never;
      if (route === "materials/poll" && data.query_id === "Q-1")
        return (await new Promise<unknown>((resolve) => {
          resolveOld = resolve;
        })) as never;
      if (route === "materials/poll")
        return ok({
          ...receipt,
          query_id: "Q-2",
          candidates: [{ ...candidate, title: "新查询材料" }],
        }) as never;
      return defaultResponse(route) as never;
    });
    render(<MaterialQuery />);
    fireEvent.click(await screen.findByRole("button", { name: /合成研究/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始查询" }));
    await waitFor(() => expect(resolveOld).toBeTypeOf("function"));
    fireEvent.change(screen.getByLabelText("问题"), {
      target: { value: "新条件" },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始查询" }));
    await screen.findByText("新查询材料");
    resolveOld(ok(receipt));
    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith("materials/cancel", {
        query_id: "Q-1",
      }),
    );
    expect(screen.queryByText("合成压力材料")).not.toBeInTheDocument();
  });

  it("HTTP 非成功仍保留材料拒绝、预算与固定依据", async () => {
    const rejected = {
      ...ok(null),
      status: "rejected",
      code: "STALE_CURSOR",
      stop_reason: "source_changed",
      warnings: ["固定来源已变化"],
    };
    mockApi.mockRejectedValueOnce(
      Object.assign(Error("HTTP 409"), { responseBody: rejected }),
    );
    expect(await materialRequest("materials/resume", {})).toEqual(rejected);
  });
  it("取消组装会取消同一固定查询并使迟到材料包失效", async () => {
    let finish!: (value: unknown) => void;
    mockApi.mockImplementation(async (route) =>
      route === "materials/assemble"
        ? ((await new Promise<unknown>((resolve) => {
            finish = resolve;
          })) as never)
        : (defaultResponse(route) as never),
    );
    render(<MaterialQuery />);
    await start();
    fireEvent.click(screen.getByRole("checkbox", { name: "合成压力材料" }));
    fireEvent.click(screen.getByRole("button", { name: "组装所选材料（1）" }));
    await waitFor(() => expect(finish).toBeTypeOf("function"));
    fireEvent.click(screen.getByRole("button", { name: "取消查询" }));
    await screen.findByText("已取消");
    expect(mockApi).toHaveBeenCalledWith("materials/cancel", {
      query_id: "Q-1",
    });
    finish(
      ok({
        packet_id: "late-packet",
        query_id: "Q-1",
        definition: { key: "full", version: "1" },
        parts: [],
        contributors: [],
        complete: true,
        canonical: false,
      }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /组装所选材料/ }),
      ).toBeDisabled(),
    );
    expect(
      screen.queryByRole("region", { name: "材料包" }),
    ).not.toBeInTheDocument();
  });
});
