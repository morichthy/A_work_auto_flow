import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { Memory } from "./Memory";
vi.mock("./api", () => ({ api: vi.fn(), download: vi.fn() }));
vi.mock("./RawMaterials", () => ({ RawMaterials: () => null }));
const shared = vi.hoisted(() => ({
  reading: null as { owner_id: string } | null,
}));
vi.mock("./CurrentReading", () => ({ useCurrentReading: () => shared }));
afterEach(() => {
  cleanup();
  location.hash = "";
  vi.resetAllMocks();
  shared.reading = null;
});
it("旧阅读记录入口转向当前笔记且系统记忆不再显示阅读标签", async () => {
  location.hash = "#/memory?tab=reading&owner=PRJ-note";
  vi.mocked(api).mockResolvedValue({ owners: [] });
  render(<Memory />);
  await waitFor(() => expect(location.hash).toBe("#/home"));
  expect(
    screen.queryByRole("button", { name: "阅读记录" }),
  ).not.toBeInTheDocument();
});
it("晚到当前笔记只更新默认Owner，用户已选Owner保持不变", async () => {
  location.hash = "#/memory";
  vi.mocked(api).mockResolvedValue({
    owners: [
      { owner_id: "PRJ-first", native_data: { title: "首对象" } },
      { owner_id: "PRJ-note", native_data: { title: "笔记对象" } },
    ],
  });
  const view = render(<Memory />);
  const owner = await screen.findByRole("combobox", { name: "记忆归属对象" });
  shared.reading = { owner_id: "PRJ-note" };
  view.rerender(<Memory />);
  await waitFor(() => expect(owner).toHaveValue("PRJ-note"));
  fireEvent.change(owner, { target: { value: "PRJ-first" } });
  shared.reading = null;
  view.rerender(<Memory />);
  shared.reading = { owner_id: "PRJ-note" };
  view.rerender(<Memory />);
  expect(owner).toHaveValue("PRJ-first");
});
it("首页记录深链接直接定位目标Owner与记录，不被首个Owner覆盖", async () => {
  location.hash = "#/memory?owner=PRJ-target&record=REC-target";
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "memory/list-owners")
      return {
        owners: [
          { owner_id: "PRJ-first", native_data: { title: "首对象" } },
          { owner_id: "PRJ-target", native_data: { title: "目标对象" } },
        ],
      };
    if (path === "memory/inspect")
      return {
        records: {
          "REC-target": {
            record_id: "REC-target",
            title: "目标技术说明",
            owner_id: "PRJ-target",
            kind: "overview",
            revision: 1,
            body_markdown: "具体固定内容",
            sources: [],
            payload: { claims: [] },
          },
        },
        head: null,
        claim_states: {},
        policy: {},
        index_status: "indexed",
      };
    return {};
  });
  render(<Memory />);
  expect(
    await screen.findByRole("heading", { name: "目标技术说明" }),
  ).toBeVisible();
  expect(api).toHaveBeenCalledWith("memory/inspect", {
    owner_id: "PRJ-target",
  });
  expect(
    vi
      .mocked(api)
      .mock.calls.some(
        ([path, data]) =>
          path === "memory/inspect" &&
          (data as { owner_id: string }).owner_id === "PRJ-first",
      ),
  ).toBe(false);
});
