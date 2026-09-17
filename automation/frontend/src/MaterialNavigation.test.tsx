import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { MaterialNavigation } from "./MaterialNavigation";
vi.mock("./api", () => ({ api: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("同名主题保留不同Owner链接，独立运行默认折叠", async () => {
  vi.mocked(api).mockResolvedValue({
    owners: [
      {
        owner_id: "RES-a",
        owner_type: "research",
        native_data: { title: "同名主题" },
      },
      {
        owner_id: "PRJ-b",
        owner_type: "project",
        native_data: { title: "同名主题" },
      },
      {
        owner_id: "RUN-c",
        owner_type: "run",
        native_data: { title: "合成运行" },
      },
    ],
  });
  render(<MaterialNavigation />);
  const links = await screen.findAllByRole("link", { name: "同名主题" });
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    "#/memory?owner=RES-a",
    "#/memory?owner=PRJ-b",
  ]);
  expect(screen.getByText("独立运行").closest("details")).not.toHaveAttribute(
    "open",
  );
});
it("按类型列出实际主题并将记录定位到对应Owner，不请求文件目录", async () => {
  vi.mocked(api).mockImplementation(async (path) =>
    path === "memory/list-owners"
      ? {
          owners: [
            {
              owner_id: "PRJ-a",
              owner_type: "project",
              native_data: { title: "热传导研究" },
            },
          ],
        }
      : {
          records: {
            "REC-a": { record_id: "REC-a", title: "边界条件", kind: "detail" },
          },
        },
  );
  render(<MaterialNavigation />);
  expect(
    await screen.findByRole("link", { name: "热传导研究" }),
  ).toHaveAttribute("href", "#/memory?owner=PRJ-a");
  expect(api).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "查看主题记录" }));
  expect(await screen.findByRole("link", { name: "边界条件" })).toHaveAttribute(
    "href",
    "#/memory?owner=PRJ-a&record=REC-a",
  );
  expect(api).toHaveBeenCalledWith("memory/inspect", { owner_id: "PRJ-a" });
});
