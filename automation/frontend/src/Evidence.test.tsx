import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { Evidence } from "./Evidence";
vi.mock("./api", () => ({ api: vi.fn(), kindNames: {}, relationNames: {} }));
const call = vi.mocked(api);
it("文稿按完整章节展示且选中来源图片可见", async () => {
  location.hash = "#/evidence?id=DOC-A";
  call.mockImplementation(async (path) =>
    path === "evidence/search"
      ? { items: [], total: 0, next_offset: null, warnings: [] }
      : {
          id: "DOC-A",
          title: "完整文稿",
          kind: "document",
          tags: [],
          context: {},
          references: [],
          impacts: [],
          warnings: [],
          content_markdown:
            "文稿总体目的\n\n## 方法章节\n\n完整方法 [1](#/evidence?id=SRC-A)\n\n## 认识章节\n\n完整认识\n\n## 参考文献\n\n[1] 原始证据",
          sections: [
            {
              id: "a",
              title: "方法章节",
              kind: "detail",
              level: "L1",
              content_markdown: "完整方法 [1](#/evidence?id=SRC-A)",
            },
            {
              id: "b",
              title: "认识章节",
              kind: "experience",
              level: "L3",
              content_markdown: "完整认识",
            },
          ],
          media: {
            type: "image",
            data_url: "data:image/png;base64,aA==",
            caption: "原始证据图",
          },
        },
  );
  render(<Evidence revision={0} error={vi.fn()} />);
  expect(
    await screen.findByRole("heading", { name: "方法章节" }),
  ).toBeVisible();
  expect(screen.getByText("完整认识")).toBeVisible();
  expect(screen.getByText("文稿总体目的")).toBeVisible();
  expect(screen.getAllByText("完整认识")).toHaveLength(1);
  expect(screen.getByRole("heading", { name: "参考文献" })).toBeVisible();
  expect(screen.getByRole("img", { name: "原始证据图" })).toBeVisible();
  expect(screen.getByRole("link", { name: "1" })).toHaveAttribute(
    "href",
    "#/evidence?id=SRC-A",
  );
});
it("非法修订号深链不得静默回退当前版", async () => {
  location.hash = "#/evidence?id=MEM-A&revision=bad";
  call.mockResolvedValue({
    items: [],
    total: 0,
    next_offset: null,
    warnings: [],
  });
  render(<Evidence revision={0} error={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("修订号无效");
  expect(call.mock.calls.some(([path]) => path === "evidence/detail")).toBe(
    false,
  );
});
it("Run按输入配置执行结果限制分组且技术哈希不混入上下文", async () => {
  location.hash = "#/evidence?id=RUN-A";
  call.mockImplementation(async (path) =>
    path === "evidence/search"
      ? { items: [], total: 0, next_offset: null, warnings: [] }
      : {
          id: "RUN-A",
          title: "可复现实验",
          kind: "run",
          tags: [],
          references: [],
          impacts: [],
          warnings: [],
          content_markdown: "实验正文",
          context: {
            inputs: [{ title: "温度序列", sha256: "hidden-fingerprint" }],
            parameters: { precision: "binary64" },
            execution_status: "成功",
            results: "误差降低",
            limitations: "仅模拟数据",
          },
        },
  );
  render(<Evidence revision={0} error={vi.fn()} />);
  expect(
    await screen.findByRole("heading", { name: "配置与环境" }),
  ).toBeVisible();
  expect(screen.getByRole("heading", { name: "结果与产物" })).toBeVisible();
  expect(screen.getByText("温度序列")).toBeVisible();
  expect(screen.queryByText("hidden-fingerprint")).not.toBeInTheDocument();
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  location.hash = "";
});
it("证据深链按ID加载单条详情并可跳转引用，搜索不请求全库state", async () => {
  location.hash = "#/evidence?id=MEM-A&revision=2&sha256=abc";
  call.mockImplementation(async (path, payload) =>
    path === "evidence/search"
      ? {
          items: [
            {
              id: "MEM-A",
              title: "方法甲",
              summary: "结论摘要",
              kind: "experience",
              tags: [],
            },
          ],
          total: 1,
          next_offset: null,
          warnings: [],
        }
      : {
          id: (payload as { id: string }).id,
          title: "方法甲",
          kind: "experience",
          content_markdown: "正文 $x=2$",
          context: { question: "适用问题" },
          tags: ["温度"],
          references: [
            {
              id: "RUN-B",
              title: "实验乙",
              url: "#/evidence?id=RUN-B",
              relation: "supports",
            },
          ],
          impacts: [],
          warnings: [],
          verification: "metadata_only",
        },
  );
  render(<Evidence revision={0} error={vi.fn()} />);
  expect(await screen.findByText("适用问题")).toBeVisible();
  expect(call).toHaveBeenCalledWith("evidence/detail", {
    id: "MEM-A",
    revision: 2,
    sha256: "abc",
  });
  expect(screen.getByRole("link", { name: "实验乙" })).toHaveAttribute(
    "href",
    "#/evidence?id=RUN-B",
  );
  fireEvent.change(screen.getByLabelText("搜索证据"), {
    target: { value: "实验" },
  });
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith("evidence/search", {
      query: "实验",
      limit: 30,
      offset: 0,
    }),
  );
  expect(call.mock.calls.some(([path]) => path === "state")).toBe(false);
});
it("连续证据深链只显示最后选中的详情", async () => {
  let finish!: (value: unknown) => void;
  location.hash = "#/evidence?id=MEM-SLOW";
  call.mockImplementation(async (path, payload) => {
    if (path === "evidence/search")
      return { items: [], total: 0, next_offset: null, warnings: [] };
    if ((payload as { id: string }).id === "MEM-SLOW")
      return new Promise((resolve) => {
        finish = resolve;
      });
    return {
      id: "RUN-FAST",
      title: "最新实验",
      content_markdown: "最新结果",
      context: {},
      tags: [],
      references: [],
      impacts: [],
      warnings: [],
    };
  });
  render(<Evidence revision={0} error={vi.fn()} />);
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith("evidence/detail", { id: "MEM-SLOW" }),
  );
  location.hash = "#/evidence?id=RUN-FAST";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
  await screen.findByText("最新结果");
  finish({
    id: "MEM-SLOW",
    title: "旧详情",
    content_markdown: "不应显示",
    tags: [],
    context: {},
    references: [],
    impacts: [],
    warnings: [],
  });
  await waitFor(() =>
    expect(screen.queryByText("不应显示")).not.toBeInTheDocument(),
  );
});
