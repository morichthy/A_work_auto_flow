import { afterEach, describe, expect, it, vi } from "vitest";
import {
  act,
  waitFor,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { Memory } from "./Memory";
import { api } from "./api";

vi.mock("./api", () => ({ api: vi.fn(), download: vi.fn() }));
vi.mock("./RawMaterials", () => ({ RawMaterials: () => null }));
afterEach(cleanup);

describe("统一记忆层级入口", () => {
  it("每层只有一个筛选和新建入口，其他对象未迁移的内容仍可找到", async () => {
    const records = Object.fromEntries(
      ["event", "narrative", "map", "overview"].map((kind) => [
        kind,
        {
          record_id: kind,
          revision: 1,
          owner_id: "RES-SYNTHETIC",
          kind,
          title: `合成 ${kind}`,
          body_markdown: `保存的 ${kind} 正文`,
          record_reason: "仅软件回归",
          payload: { claims: [] },
          sources: [],
        },
      ]),
    );
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "memory/list-owners")
        return {
          owners: [
            { owner_id: "RES-SYNTHETIC", native_data: { title: "合成研究" } },
          ],
        } as never;
      if (path === "memory/inspect")
        return {
          records,
          head: null,
          claim_states: {},
          policy: {},
          index_status: "indexed",
        } as never;
      throw new Error(`未预期请求：${path}`);
    });
    vi.mocked(api).mockClear();
    render(<Memory />);
    await screen.findByRole("option", { name: /合成研究/ });
    expect(screen.getByRole("button", { name: "研究经过" })).toHaveClass(
      "primary",
    );
    expect(
      vi.mocked(api).mock.calls.some(([path]) => path === "memory/inspect"),
    ).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "对象记忆" }));
    expect(
      vi.mocked(api).mock.calls.some(([path]) => path === "memory/inspect"),
    ).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "生成对象记忆" }));
    await screen.findByRole("heading", { name: "合成 overview" });
    expect(screen.getByRole("link", { name: "合成 overview" })).toHaveAttribute(
      "href",
      expect.stringContaining("#/evidence?id=overview"),
    );
    expect(screen.queryByText("结构、固定来源与版本")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "研究经过" }));
    fireEvent.click(screen.getByRole("button", { name: "对象记忆" }));
    expect(
      vi.mocked(api).mock.calls.filter(([path]) => path === "memory/inspect"),
    ).toHaveLength(1);
    const filters = screen.getByRole("group", { name: "按层级或类型筛选" });
    expect(within(filters).getAllByLabelText("L2 研究经过")).toHaveLength(1);
    expect(within(filters).getAllByLabelText("L4 整体概览")).toHaveLength(1);
    expect(screen.queryByText("L2 事件记录（兼容）")).not.toBeInTheDocument();
    expect(screen.queryByText("L4 主题地图")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "新增L2 研究经过" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "新增L4 整体概览" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "清空类型" }));
    fireEvent.click(within(filters).getByLabelText("L4 整体概览"));
    expect(
      screen.getByRole("heading", { name: "合成 overview" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "合成 map" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "合成 event" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "合成 narrative" }),
    ).not.toBeInTheDocument();
  });
});

it("总结重新准备时保留旧包但禁止回填，完成后只采用新依据", async () => {
  vi.mocked(api).mockReset();
  let finish: ((value: unknown) => void) | undefined;
  let prepared = 0;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "memory/list-owners")
      return {
        owners: [{ owner_id: "RES-ONE", native_data: { title: "合成对象" } }],
      } as never;
    if (path === "memory/summaries-prepare") {
      if (++prepared === 1)
        return {
          context_text: "旧材料正文",
          manifest: {},
          basis_heads: { "RES-ONE": "old-head" },
        } as never;
      return (await new Promise<unknown>((resolve) => {
        finish = resolve;
      })) as never;
    }
    if (path === "memory/summaries-save")
      return { save_status: "committed", index_status: "indexed" } as never;
    if (path === "memory/inspect")
      return {
        records: {},
        claim_states: {},
        head: { commit_id: "new-head" },
        index_status: "indexed",
      } as never;
    throw new Error(`未预期请求：${path}`);
  });
  render(<Memory />);
  await screen.findByRole("option", { name: /合成对象/ });
  fireEvent.click(screen.getByRole("button", { name: "跨项目总结" }));
  fireEvent.change(screen.getByRole("textbox", { name: "总结问题" }), {
    target: { value: "合成总结" },
  });
  fireEvent.click(screen.getByRole("checkbox", { name: /RES-ONE/ }));
  fireEvent.click(screen.getByRole("button", { name: "准备总结材料包" }));
  await screen.findByText("旧材料正文");
  fireEvent.click(screen.getByRole("button", { name: "准备总结材料包" }));
  expect(screen.getByText("旧材料正文")).toBeVisible();
  expect(screen.getByRole("button", { name: "回填 L3 经验" })).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "回填 L4 整体概览" }),
  ).toBeDisabled();
  await act(async () => {
    finish!({
      context_text: "新材料正文",
      manifest: {},
      basis_heads: { "RES-ONE": "new-head" },
    });
  });
  expect(screen.getByRole("button", { name: "回填 L3 经验" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "回填 L3 经验" }));
  expect(screen.getByRole("button", { name: "保存记忆" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "保存记忆" }));
  await waitFor(() =>
    expect(vi.mocked(api)).toHaveBeenCalledWith(
      "memory/summaries-save",
      expect.objectContaining({ basis_heads: { "RES-ONE": "new-head" } }),
    ),
  );
});
