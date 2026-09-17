import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api, download } from "./api";
import { useState } from "react";
import { CurrentReadingProvider, CurrentReadingNote } from "./CurrentReading";
import { ReadingSessions } from "./ReadingSessions";
vi.mock("./api", () => ({ api: vi.fn(), download: vi.fn() }));
const call = vi.mocked(api);
it("重开可恢复最近问题第二页中的合法选择", async () => {
  localStorage.setItem("reading-selection:workspace-a", "RS-page2");
  call.mockImplementation(async (path, payload) => {
    if (path === "reading-notes/recent")
      return {
        ...recent(
          (payload as { offset?: number }).offset
            ? [{ ...items[0], session_id: "RS-page2" }]
            : items,
        ),
        next_offset: (payload as { offset?: number }).offset ? null : 50,
      };
    return { ...reading, session_id: "RS-page2" };
  });
  render(
    <CurrentReadingProvider>
      <CurrentReadingNote />
    </CurrentReadingProvider>,
  );
  await screen.findByText("已保存的正文");
  expect(screen.getByLabelText("最近24小时阅读问题")).toHaveValue("RS-page2");
  expect(call).toHaveBeenCalledWith("reading-notes/recent", {
    limit: 50,
    offset: 50,
  });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  localStorage.clear();
});
const reading = {
  mode: "owner_document",
  session_id: "RS-owner",
  owner_id: "PRJ-owner",
  goal: "已选择的研究",
  revision: 4,
  context_markdown: "## 当前理解\n已保存的正文",
  phase: "proceed",
  archived: false,
  gaps: [],
  candidates: [],
  verification: "snapshot_only",
};
it("最近问题可加载第二页且不改变当前笔记", async () => {
  call.mockImplementation(async (path, payload) =>
    path === "reading-notes/recent"
      ? {
          ...recent(
            (payload as { offset?: number }).offset
              ? [{ ...items[0], session_id: "RS-page2", goal: "第51条问题" }]
              : items,
          ),
          next_offset: (payload as { offset?: number }).offset ? null : 50,
        }
      : reading,
  );
  render(
    <CurrentReadingProvider>
      <CurrentReadingNote />
    </CurrentReadingProvider>,
  );
  await screen.findByText("已保存的正文");
  fireEvent.click(screen.getByText("加载更多最近问题"));
  await screen.findByRole("option", { name: /第51条问题/ });
  expect(screen.getByLabelText("最近24小时阅读问题")).toHaveValue("RS-owner");
  expect(call).toHaveBeenCalledWith("reading-notes/recent", {
    limit: 50,
    offset: 50,
  });
});
const items = [
  {
    session_id: "RS-owner",
    goal: "已选择的研究",
    note_count: 1,
    updated_at: "2026-09-17T00:00:00Z",
  },
];
const recent = (rows = items, workspace_id = "workspace-a") => ({
  workspace_id,
  items: rows,
  warnings: [],
  window_hours: 24,
});
it("最近24小时问题使用快照且按工作区恢复合法选择", async () => {
  localStorage.setItem("reading-selection:workspace-a", "RS-second");
  call.mockImplementation(async (path, payload) =>
    path === "reading-notes/recent"
      ? recent([
          ...items,
          { ...items[0], session_id: "RS-second", goal: "已有选择" },
        ])
      : {
          ...reading,
          session_id: (payload as { session_id: string }).session_id,
        },
  );
  render(
    <CurrentReadingProvider>
      <CurrentReadingNote />
    </CurrentReadingProvider>,
  );
  await screen.findByText("已保存的正文");
  expect(screen.getByLabelText("最近24小时阅读问题")).toHaveValue("RS-second");
  expect(screen.getByText(/未重新核验证据/)).toBeVisible();
  expect(
    screen.queryByRole("link", { name: "选择阅读会话" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看证据与影响" })).toHaveAttribute(
    "href",
    "#/evidence?scope=reading",
  );
  expect(screen.getByLabelText("当前阅读模式")).toBeInTheDocument();
  fireEvent.click(screen.getByText("导出当前笔记"));
  expect(download).toHaveBeenCalledWith(
    "已选择的研究-RS-second-r4.md",
    reading.context_markdown,
  );
  expect(call).toHaveBeenCalledWith("reading-notes/snapshot", {
    session_id: "RS-second",
  });
  expect(
    call.mock.calls.some(([path]) => path === "materials/reading-view"),
  ).toBe(false);
});
it("首页进入阅读面板沿用同一会话快照，不重复读取或消费原文预算", async () => {
  call.mockImplementation(async (path) =>
    path === "reading-notes/recent"
      ? recent()
      : path === "materials/reading-list"
        ? { value: { items, next_offset: null, unavailable_count: 0 } }
        : reading,
  );
  function Journey() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <CurrentReadingNote />
        <button onClick={() => setOpen(true)}>进入阅读面板</button>
        {open && <ReadingSessions ownerId="PRJ-owner" />}
      </>
    );
  }
  render(
    <CurrentReadingProvider>
      <Journey />
    </CurrentReadingProvider>,
  );
  await screen.findByText("已保存的正文");
  fireEvent.click(screen.getByText("进入阅读面板"));
  await waitFor(() =>
    expect(screen.getAllByText("已保存的正文")).toHaveLength(2),
  );
  expect(
    call.mock.calls.filter(([path]) => path === "reading-notes/snapshot"),
  ).toHaveLength(1);
  expect(screen.getByRole("link", { name: "查看证据与影响" })).toHaveAttribute(
    "href",
    "#/evidence?scope=reading",
  );
});
it("首页默认排除归档，显示Markdown与缺口并可从空状态重试", async () => {
  let populated = false;
  call.mockImplementation(async (path) =>
    path === "reading-notes/recent"
      ? {
          ...recent(populated ? items : []),
          warnings: ["部分阅读记录当前不可读取"],
        }
      : reading,
  );
  render(
    <CurrentReadingProvider>
      <CurrentReadingNote />
    </CurrentReadingProvider>,
  );
  expect(await screen.findByText(/最近24小时暂无已保存/)).toBeVisible();
  expect(screen.getByText(/部分阅读记录当前不可读取/)).toBeVisible();
  populated = true;
  fireEvent.click(screen.getByText("刷新当前笔记"));
  expect(
    await screen.findByRole("heading", { name: "当前理解" }),
  ).toBeVisible();
  expect(call).toHaveBeenCalledWith("reading-notes/recent", { limit: 50 });
  expect(
    call.mock.calls.some(([path]) => path === "materials/reading-read"),
  ).toBe(false);
});
it("全局默认列表晚到不能覆盖归属对象选定的当前笔记", async () => {
  let finish!: (value: unknown) => void;
  call.mockImplementation(async (path) => {
    if (path === "reading-notes/recent")
      return new Promise((resolve) => {
        finish = resolve;
      });
    if (path === "materials/reading-list")
      return { value: { items, next_offset: null, unavailable_count: 0 } };
    return reading;
  });
  render(
    <CurrentReadingProvider>
      <CurrentReadingNote />
      <ReadingSessions ownerId="PRJ-owner" />
    </CurrentReadingProvider>,
  );
  await waitFor(() =>
    expect(screen.getAllByText("已保存的正文")).toHaveLength(2),
  );
  finish(recent([{ ...items[0], session_id: "RS-wrong" }]));
  await waitFor(() =>
    expect(call).not.toHaveBeenCalledWith("reading-notes/snapshot", {
      session_id: "RS-wrong",
    }),
  );
});
it("刷新失败撤下正文，重试仍是同一会话而非重新选择全局最新", async () => {
  let denied = false;
  call.mockImplementation(async (path) => {
    if (path === "reading-notes/recent") return recent();
    if (denied) throw Error("来源撤权");
    return reading;
  });
  render(
    <CurrentReadingProvider>
      <CurrentReadingNote />
    </CurrentReadingProvider>,
  );
  await screen.findByText("已保存的正文");
  denied = true;
  fireEvent.click(screen.getByText("刷新当前笔记"));
  expect(await screen.findByRole("alert")).toHaveTextContent("来源撤权");
  expect(screen.queryByText("已保存的正文")).not.toBeInTheDocument();
  denied = false;
  fireEvent.click(screen.getByText("刷新当前笔记"));
  expect(await screen.findByText("已保存的正文")).toBeVisible();
});
it("跨工作区和过期选择不得恢复其他问题", async () => {
  localStorage.setItem("reading-selection:workspace-a", "RS-other");
  localStorage.setItem("reading-selection:workspace-b", "RS-expired");
  call.mockImplementation(async (path) =>
    path === "reading-notes/recent" ? recent(items, "workspace-b") : reading,
  );
  render(
    <CurrentReadingProvider>
      <CurrentReadingNote />
    </CurrentReadingProvider>,
  );
  await screen.findByText("已保存的正文");
  expect(call).toHaveBeenCalledWith("reading-notes/snapshot", {
    session_id: "RS-owner",
  });
  expect(localStorage.getItem("reading-selection:workspace-a")).toBe(
    "RS-other",
  );
});
it("问题选择的旧快照晚到不覆盖新问题", async () => {
  let finish!: (value: unknown) => void;
  call.mockImplementation(async (path, payload) => {
    if (path === "reading-notes/recent")
      return recent([
        ...items,
        { ...items[0], session_id: "RS-second", goal: "第二问题" },
      ]);
    if ((payload as { session_id: string }).session_id === "RS-owner")
      return new Promise((resolve) => {
        finish = resolve;
      });
    return {
      ...reading,
      session_id: "RS-second",
      context_markdown: "第二问题正文",
    };
  });
  render(
    <CurrentReadingProvider>
      <CurrentReadingNote />
    </CurrentReadingProvider>,
  );
  const select = await screen.findByLabelText("最近24小时阅读问题");
  await waitFor(() => expect(select).toBeEnabled());
  fireEvent.change(select, { target: { value: "RS-second" } });
  await screen.findByText("第二问题正文");
  finish(reading);
  await waitFor(() =>
    expect(screen.queryByText("已保存的正文")).not.toBeInTheDocument(),
  );
  expect(localStorage.getItem("reading-selection:workspace-a")).toBe(
    "RS-second",
  );
});
