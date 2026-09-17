import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
vi.mock("./api", () => ({ api: vi.fn() }));
import { ReadingEvidence } from "./ReadingEvidence";
import { NoteEvidenceLinks } from "./NoteEvidenceLinks";
it("定向证据仅列固定链接不预读全文或暴露原始字段", () => {
  render(
    <NoteEvidenceLinks
      reading={{
        session_id: "RS-one",
        candidates: [
          {
            candidate_id: "RC-one",
            title: "完整文稿",
            status: "已记录理解",
            ref: {
              kind: "record",
              id: "MEM-one",
              revision: 1,
              sha256: "fixed-hash",
              locator: null,
            },
          },
        ],
      }}
    />,
  );
  expect(screen.getByRole("link", { name: "完整文稿" })).toBeVisible();
  expect(api).not.toHaveBeenCalled();
  expect(screen.queryByText(/fixed-hash/)).not.toBeInTheDocument();
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("证据入口只显示当前note实际已引用候选并保留固定版本", () => {
  vi.mocked(api).mockResolvedValue({
    manifest: { items: [], missing: [], omitted: [] },
  });
  render(
    <ReadingEvidence
      reading={{
        session_id: "RS-a",
        candidates: [
          {
            candidate_id: "RC-a",
            title: "已引用技术",
            status: "已记录理解",
            ref: {
              kind: "record",
              id: "REC-a",
              revision: 3,
              sha256: "abc",
              locator: "block:method",
            },
            stale: true,
          },
          {
            candidate_id: "RC-b",
            title: "未读候选不应冒充依据",
            status: "候选，待完整阅读",
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("已引用技术")).toBeVisible();
  expect(screen.getByText(/REC-a · r3/)).toBeVisible();
  expect(screen.getByText(/来源已变化/)).toBeVisible();
  expect(screen.queryByText("未读候选不应冒充依据")).not.toBeInTheDocument();
});
it("只展开直接固定引用及一层sources，不读取同Owner无关记录或第二层", async () => {
  const source = {
    target_kind: "record",
    target_id: "REC-source",
    revision: 2,
    sha256: "hash-source",
    relation: "references",
    locator: "",
  };
  vi.mocked(api).mockImplementation(async (path, raw) => {
    const request = raw as {
      refs?: { target_id: string }[];
      record_id?: string;
    };
    if (path === "memory/expand")
      return {
        context_text: "固定运行正文：本次实验温度为300K",
        manifest: {
          items: request.refs!.map((ref) => ({
            canonical_id: ref.target_id,
            owner_id: "PRJ-one",
            ref,
          })),
          missing: [],
          omitted: [],
        },
      };
    const direct = request.record_id === "REC-note";
    return {
      record: {
        record_id: request.record_id,
        owner_id: "PRJ-one",
        kind: direct ? "experience" : "source",
        title: direct ? "固定经验内容" : "原始来源内容",
        revision: direct ? 1 : 2,
        record_hash: direct ? "hash-note" : "hash-source",
        body_markdown: direct ? "适用边界及假设" : "原始实验",
        sources: direct
          ? [source, { ...source, target_kind: "run", target_id: "RUN-fixed" }]
          : [{ ...source, target_id: "REC-third" }],
        payload: {},
      },
    };
  });
  render(
    <ReadingEvidence
      reading={{
        session_id: "RS-one",
        candidates: [
          {
            candidate_id: "RC-note",
            title: "笔记引用",
            status: "已记录理解",
            ref: {
              kind: "record",
              id: "REC-note",
              revision: 1,
              sha256: "hash-note",
              locator: null,
            },
          },
          {
            candidate_id: "RC-other",
            title: "未阅读候选",
            status: "候选，待完整阅读",
            ref: {
              kind: "record",
              id: "REC-other",
              revision: 1,
              sha256: "other",
              locator: null,
            },
          },
        ],
      }}
    />,
  );
  expect(await screen.findByText("原始来源内容")).toBeVisible();
  expect(screen.getByText("适用边界及假设")).toBeVisible();
  expect(screen.getByText("固定运行正文：本次实验温度为300K")).toBeVisible();
  const calls = vi
    .mocked(api)
    .mock.calls.filter(([path]) => path === "memory/expand");
  expect(
    calls.map(([, raw]) =>
      (raw as { refs: { target_id: string }[] }).refs.map(
        (ref) => ref.target_id,
      ),
    ),
  ).toEqual([["REC-note"], ["REC-source", "RUN-fixed"]]);
});
