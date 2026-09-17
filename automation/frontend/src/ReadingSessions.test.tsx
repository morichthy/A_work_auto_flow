import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api, download } from "./api";
import { ReadingSessions } from "./ReadingSessions";
import { ReadingMode } from "./ReadingMode";
import { readingNoteName } from "./readingNoteName";
vi.mock("./api", () => ({ api: vi.fn(), download: vi.fn() }));
const call = vi.mocked(api);
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const note = {
  goal: "温度/误差：研究",
  mode: "owner_document" as const,
  session_id: "RS-one",
  revision: 4,
  context_markdown: "已读理解与必要细节 273.15",
  phase: "proceed",
  archived: false,
  gaps: [],
  candidates: [
    { candidate_id: "RC-one", title: "固定方法", status: "已记录理解" },
  ],
};
async function assertHistoricalReadOnly(mode?: "legacy") {
  call.mockImplementation(async (path) =>
    path === "materials/reading-list"
      ? {
          value: {
            items: [{ session_id: "RS-one", goal: "旧阅读" }],
            next_offset: null,
            unavailable_count: 0,
          },
        }
      : { value: { ...note, mode } },
  );
  render(<ReadingSessions ownerId="PRJ-one" />);
  expect(
    await screen.findByText(/此历史会话使用旧版逐候选阅读流程/),
  ).toBeVisible();
  expect(screen.queryByLabelText("当前阅读模式")).not.toBeInTheDocument();
  expect(screen.queryByText("保存阅读模式与方向")).not.toBeInTheDocument();
  expect(screen.getByText(note.context_markdown)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "固定方法 · 读取原文" }),
  ).toBeEnabled();
}
it("历史legacy模式仅显示说明且不暴露不可用的配置动作", async () => {
  await assertHistoricalReadOnly("legacy");
});
it("历史缺mode会话仅显示说明且不暴露不可用的配置动作", async () => {
  await assertHistoricalReadOnly();
});
it("显式联想模式启用本会话联想并保留轮次上限", async () => {
  call.mockImplementation(async (path) => ({
    value:
      path === "materials/reading-view"
        ? { ...note, revision: 5, strategy: "associative" }
        : { revision: 5 },
  }));
  render(
    <ReadingMode
      reading={{ ...note, association: { enabled: false, max_rounds: 7 } }}
      onSaved={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText("当前阅读模式"), {
    target: { value: "associative" },
  });
  fireEvent.click(screen.getByText("保存阅读模式与方向"));
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith(
      "materials/reading-configure",
      expect.objectContaining({
        association: { enabled: true, max_rounds: 7 },
      }),
    ),
  );
  expect(await screen.findByText(/尚未启动搜索/)).toBeVisible();
});
it("旧会话保存晚到不刷新新会话或覆盖其草稿", async () => {
  let finish!: (value: unknown) => void;
  call.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const saved = vi.fn();
  const view = render(<ReadingMode key="one" reading={note} onSaved={saved} />);
  fireEvent.click(screen.getByText("保存阅读模式与方向"));
  view.rerender(
    <ReadingMode
      key="two"
      reading={{
        ...note,
        session_id: "RS-two",
        association_text: "新会话方向",
      }}
      onSaved={saved}
    />,
  );
  finish({ value: { revision: 5 } });
  await waitFor(() =>
    expect(screen.getByLabelText("联想搜索文本（可选）")).toHaveValue(
      "新会话方向",
    ),
  );
  expect(saved).not.toHaveBeenCalled();
  expect(call).toHaveBeenCalledTimes(1);
});
it("保存模式使用CAS，冲突保留联想草稿且可显式重读版本", async () => {
  call.mockImplementation(async (path) =>
    path === "materials/reading-list"
      ? {
          value: {
            items: [{ session_id: "RS-one", goal: "温度研究" }],
            next_offset: null,
            unavailable_count: 0,
          },
        }
      : path === "materials/reading-configure"
        ? { value: null, code: "VERSION_CONFLICT" }
        : { value: note },
  );
  render(<ReadingSessions ownerId="PRJ-one" />);
  fireEvent.change(await screen.findByLabelText("当前阅读模式"), {
    target: { value: "quick" },
  });
  fireEvent.change(screen.getByLabelText("联想搜索文本（可选）"), {
    target: { value: "温度误差与量化边界" },
  });
  fireEvent.click(screen.getByText("保存阅读模式与方向"));
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith(
      "materials/reading-configure",
      expect.objectContaining({
        session_id: "RS-one",
        expected_revision: 4,
        strategy: "quick",
        association_text: "温度误差与量化边界",
      }),
    ),
  );
  expect(await screen.findByText(/VERSION_CONFLICT.*草稿已保留/)).toBeVisible();
  expect(screen.getByLabelText("联想搜索文本（可选）")).toHaveValue(
    "温度误差与量化边界",
  );
  fireEvent.click(screen.getByText("读取最新会话（保留草稿）"));
  await waitFor(() => expect(screen.getByText(/已读取最新版本/)).toBeVisible());
  expect(screen.getByLabelText("当前阅读模式")).toHaveValue("quick");
});
it("按对象读最新记录，打开原文后导出仍使用实际笔记快照版本", async () => {
  call.mockImplementation(async (path) =>
    path === "materials/reading-list"
      ? {
          value: {
            items: [{ session_id: "RS-one", goal: "温度研究", revision: 4 }],
            next_offset: null,
            unavailable_count: 0,
          },
        }
      : path === "materials/reading-view"
        ? { value: note }
        : { value: { revision: 5, readings: [], gaps: [] } },
  );
  render(<ReadingSessions ownerId="PRJ-one" />);
  expect(await screen.findByText("已读理解与必要细节 273.15")).toBeVisible();
  expect(call).toHaveBeenCalledWith("materials/reading-view", {
    session_id: "RS-one",
    notes_only: true,
  });
  fireEvent.click(screen.getByRole("button", { name: "固定方法 · 读取原文" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "固定方法 · 读取原文" }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "导出此版本笔记" }));
  expect(download).toHaveBeenCalledWith(
    "温度-误差：研究-RS-one-r4.md",
    note.context_markdown,
  );
  expect(readingNoteName(undefined, "RS-other", 2)).toBe(
    "阅读笔记-RS-other-r2.md",
  );
  expect(readingNoteName(' A:B*?<>|"\\\n ', "RS-12345678-90ab-cdef", 7)).toBe(
    "A-B-RS-1234567890ab-r7.md",
  );
  expect(readingNoteName("长".repeat(80), "RS-one", 4)).toBe(
    "长".repeat(48) + "-RS-one-r4.md",
  );
  expect(
    screen.getByText("会话标识与版本").closest("details"),
  ).not.toHaveAttribute("open");
});
it("换对象或来源撤权时清除之前显示的笔记", async () => {
  call.mockImplementation(async (path) =>
    path === "materials/reading-list"
      ? {
          value: {
            items: [{ session_id: "RS-one", goal: "温度研究" }],
            next_offset: null,
            unavailable_count: 0,
          },
        }
      : { value: note },
  );
  const view = render(<ReadingSessions ownerId="PRJ-one" />);
  fireEvent.click(await screen.findByRole("button", { name: "温度研究" }));
  await screen.findByText("已读理解与必要细节 273.15");
  call.mockResolvedValue({ value: null, message: "来源撤权" });
  fireEvent.click(screen.getByRole("button", { name: "刷新当前阅读记录" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("来源撤权");
  expect(
    screen.queryByText("已读理解与必要细节 273.15"),
  ).not.toBeInTheDocument();
  view.rerender(<ReadingSessions ownerId="PRJ-other" />);
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith(
      "materials/reading-list",
      expect.objectContaining({ owner_id: "PRJ-other" }),
    ),
  );
});
it("筛选后的空目录窗口仍能翻页，不报告全库无会话", async () => {
  call.mockResolvedValue({
    value: { items: [], next_offset: 20, unavailable_count: 0 },
  });
  render(<ReadingSessions ownerId="PRJ-one" />);
  fireEvent.click(
    await screen.findByRole("button", { name: "下一页阅读会话" }),
  );
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith(
      "materials/reading-list",
      expect.objectContaining({ offset: 20 }),
    ),
  );
});

it("显示Owner筛选包和发现缺口，只有用户点击才启动全文补偿", async () => {
  const discoveryNote = {
    ...note,
    discovery: {
      status: "incomplete" as const,
      reasons: ["部分Owner尚未建立L4发现面"],
      projection_version: "owner-discovery-v1",
    },
    owner_packets: [
      {
        owner_id: "RES-A",
        title: "温标换算研究",
        overview: "温标误差与适用条件",
        packet_digest: "packet-a",
        retrieval_source: "discovery" as const,
        coverage: { complete: false, gaps: ["缺少L1检索说明"] },
        windows: [
          {
            text: "换算需固定单位并保留273.15。",
            refs: [
              {
                kind: "record" as const,
                id: "MEM-A",
                revision: 1,
                sha256: "a".repeat(64),
                locator: "block:summary",
              },
            ],
            source_level: "L4",
            channels: ["lexical", "dense"],
            locator: "record:MEM-A",
            matched_protected_terms: ["273.15"],
          },
        ],
      },
    ],
    fulltext_compensation_available: true,
    fulltext_compensation_reason: "发现覆盖不足，可由用户决定扩大范围。",
  };
  call.mockImplementation(async (path) => {
    if (path === "materials/reading-list")
      return {
        value: {
          items: [{ session_id: "RS-one", goal: "温度研究", note_count: 1 }],
          next_offset: null,
          unavailable_count: 0,
        },
      };
    if (path === "materials/reading-recall-fulltext")
      return {
        value: {
          revision: 5,
          discovery: { status: "ready", reasons: [] },
          owner_packets: [
            {
              ...discoveryNote.owner_packets[0],
              retrieval_source: "fulltext_compensation",
            },
          ],
          fulltext_compensation_available: false,
          gaps: [],
        },
      };
    return { value: discoveryNote };
  });
  render(<ReadingSessions ownerId="PRJ-one" />);
  expect(await screen.findByText(/发现覆盖不完整/)).toBeVisible();
  expect(screen.getByText("温标换算研究")).toBeVisible();
  expect(screen.getByText(/换算需固定单位/)).toBeVisible();
  expect(
    call.mock.calls.filter(
      ([path]) => path === "materials/reading-recall-fulltext",
    ),
  ).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "开启全文补偿召回" }));
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith(
      "materials/reading-recall-fulltext",
      expect.objectContaining({
        session_id: "RS-one",
        expected_revision: 4,
        request_id: expect.any(String),
      }),
    ),
  );
  await waitFor(() =>
    expect(screen.getByTestId("owner-discovery-card")).toHaveTextContent(
      "用户选择的全文补偿",
    ),
  );
});

it("进入自动显示有笔记会话，清单刷新保持手选会话并更新正文，翻页不切换", async () => {
  let revision = 4;
  call.mockImplementation(async (path, payload) => {
    const args = payload as { session_id?: string; offset?: number };
    if (path === "materials/reading-list")
      return {
        value: {
          items: args.offset
            ? [{ session_id: "RS-next", goal: "下一页", note_count: 1 }]
            : [
                { session_id: "RS-empty", goal: "尚未笔记", note_count: 0 },
                { session_id: "RS-one", goal: "有笔记", note_count: 1 },
                { session_id: "RS-two", goal: "另一会话", note_count: 1 },
              ],
          next_offset: args.offset ? null : 20,
          unavailable_count: 0,
        },
      };
    return {
      value: {
        ...note,
        session_id: args.session_id,
        revision,
        context_markdown: `正文 ${args.session_id} r${revision}`,
      },
    };
  });
  render(<ReadingSessions ownerId="PRJ-one" />);
  expect(await screen.findByText("正文 RS-one r4")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "另一会话" }));
  expect(await screen.findByText("正文 RS-two r4")).toBeVisible();
  revision = 5;
  fireEvent.click(screen.getByRole("button", { name: "刷新阅读清单" }));
  expect(await screen.findByText("正文 RS-two r5")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "下一页阅读会话" }));
  await screen.findByRole("button", { name: "上一页阅读会话" });
  expect(screen.getByText("正文 RS-two r5")).toBeVisible();
  expect(
    call.mock.calls.filter(([path]) => path === "materials/reading-read"),
  ).toHaveLength(0);
});

it("换对象后旧会话迟到的正文不会泄露", async () => {
  let finish: (value: unknown) => void = () => {};
  call.mockImplementation(async (path, payload) => {
    const args = payload as { owner_id?: string };
    if (path === "materials/reading-list")
      return {
        value: {
          items:
            args.owner_id === "PRJ-one"
              ? [{ session_id: "RS-one", goal: "旧对象", note_count: 1 }]
              : [],
          next_offset: null,
          unavailable_count: 0,
        },
      };
    return await new Promise((resolve) => {
      finish = resolve;
    });
  });
  const view = render(<ReadingSessions ownerId="PRJ-one" />);
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith("materials/reading-view", {
      session_id: "RS-one",
      notes_only: true,
    }),
  );
  view.rerender(<ReadingSessions ownerId="PRJ-two" />);
  finish({ value: note });
  await screen.findByText(/本页没有可显示的会话/);
  expect(screen.queryByText(note.context_markdown)).not.toBeInTheDocument();
});
