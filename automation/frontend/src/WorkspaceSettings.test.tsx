import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { WorkspaceSettings, type SettingsReceipt } from "./WorkspaceSettings";
import type { Budget } from "./generated/material-query";

vi.mock("./api", () => ({ api: vi.fn() }));
const mockApi = vi.mocked(api);
const budget: Budget = {
  wall_ms: 300000,
  read_bytes: 16777216,
  output_chars: 80000,
  candidates: 100,
  graph_nodes: 50,
  graph_edges: 100,
  graph_hops: 2,
  model_tokens: 512,
  model_calls: 1,
  model_input_tokens: 512,
  model_output_tokens: 0,
  rerank_items: 0,
};
const receipt: SettingsReceipt = {
  revision: "first",
  settings: {
    collaboration: { subagents: "auto", subagent_requirements: "现有能力要求" },
    materials: { result_limit: 10, budget },
    reading: {
      strategy: "standard",
      association: { enabled: true, max_rounds: 3 },
      context: { max_owners: 10, note_max_tokens: 6000 },
      result_limit: 10,
      budget,
      reranking: { mode: "auto", candidate_limit: 30 },
    },
  },
  defaults: {
    collaboration: { subagents: "off", subagent_requirements: "默认能力要求" },
    materials: { result_limit: 6, budget },
    reading: {
      strategy: "standard",
      association: { enabled: true, max_rounds: 3 },
      context: { max_owners: 10, note_max_tokens: 6000 },
      result_limit: 6,
      budget,
      reranking: { mode: "auto", candidate_limit: 30 },
    },
  },
  limits: {
    ...budget,
    wall_ms: 600000,
    read_bytes: 33554432,
    output_chars: 100000,
    candidates: 2000,
    model_tokens: 200000,
    model_calls: 20,
    rerank_items: 200,
  },
};
const materialResult = () => screen.getAllByLabelText("默认结果数")[0];
async function ready() {
  render(<WorkspaceSettings />);
  await screen.findByText("协作策略");
}
beforeEach(() =>
  mockApi.mockReset().mockResolvedValue(structuredClone(receipt)),
);
afterEach(cleanup);

describe("workspace settings", () => {
  it("saves the default strategy and bounded association policy", async () => {
    await ready();
    fireEvent.change(screen.getByLabelText("默认阅读模式"), {
      target: { value: "quick" },
    });
    fireEvent.click(screen.getByLabelText("允许不足时联想加深"));
    fireEvent.change(screen.getByLabelText("最多联想轮次"), {
      target: { value: "4" },
    });
    fireEvent.click(screen.getByText("保存设置"));
    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith(
        "settings",
        expect.objectContaining({
          expected_revision: "first",
          settings: expect.objectContaining({
            reading: expect.objectContaining({
              strategy: "quick",
              association: { enabled: false, max_rounds: 4 },
            }),
          }),
        }),
      ),
    );
  });
  it("validates independent Owner and note budgets and keeps engineering limits", async () => {
    await ready();
    expect(screen.getByText(/token采用保守估算/)).toBeInTheDocument();
    expect(
      screen.getByText("高级资源保护（单次操作）").closest("details"),
    ).not.toHaveAttribute("open");
    for (const [label, value] of [
      ["最多Owner数", "0"],
      ["最多Owner数", "101"],
      ["最终note估算token", "511"],
      ["最终note估算token", "50001"],
      ["最终note估算token", "1.5"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
      fireEvent.click(screen.getByText("保存设置"));
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(mockApi).toHaveBeenCalledTimes(1);
      fireEvent.change(screen.getByLabelText("最多Owner数"), {
        target: { value: "10" },
      });
      fireEvent.change(screen.getByLabelText("最终note估算token"), {
        target: { value: "6000" },
      });
    }
    fireEvent.change(screen.getByLabelText("最多Owner数"), {
      target: { value: "100" },
    });
    fireEvent.change(screen.getByLabelText("最终note估算token"), {
      target: { value: "50000" },
    });
    fireEvent.click(screen.getByText("保存设置"));
    await screen.findByText(/设置已保存/);
    expect(mockApi.mock.calls[1][1]).toMatchObject({
      settings: {
        reading: {
          context: { max_owners: 100, note_max_tokens: 50000 },
          budget: receipt.settings.reading.budget,
        },
        materials: receipt.settings.materials,
      },
    });
  });
  it("validates requirements and preserves exact text while collaboration is off", async () => {
    await ready();
    const input = screen.getByLabelText("子 agent 能力要求");
    fireEvent.change(screen.getByLabelText("子 agent", { exact: true }), {
      target: { value: "off" },
    });
    expect(input).toBeEnabled();
    for (const value of ["", " \n\t", "能".repeat(2001)]) {
      fireEvent.change(input, { target: { value } });
      fireEvent.click(screen.getByText("保存设置"));
      expect(screen.getByRole("alert")).toHaveTextContent("1到2000");
      expect(mockApi).toHaveBeenCalledTimes(1);
    }
    // 非 BMP 字符计数与后端一致；边界字符数和首尾空白均须原样保存。
    const text = "  " + "🧠".repeat(2000) + "\n";
    fireEvent.change(input, { target: { value: text } });
    mockApi.mockResolvedValueOnce({
      ...receipt,
      settings: {
        ...receipt.settings,
        collaboration: { subagents: "off", subagent_requirements: text },
      },
    });
    fireEvent.click(screen.getByText("保存设置"));
    await screen.findByText(/设置已保存/);
    expect(mockApi.mock.calls[1][1]).toMatchObject({
      settings: {
        collaboration: { subagents: "off", subagent_requirements: text },
      },
    });
    expect(input).toHaveValue(text);
  });
  it("rejects zero timeout and display fractions that are not whole base units", async () => {
    await ready();
    for (const value of ["0", "0.0001"]) {
      fireEvent.change(screen.getAllByLabelText("活动超时（秒）")[0], {
        target: { value },
      });
      fireEvent.click(screen.getByText("保存设置"));
      expect(screen.getByRole("alert")).toHaveTextContent("整数预算");
      expect(mockApi).toHaveBeenCalledTimes(1);
    }
  });
  it("offers an explicit retry after initial load failure without creating a draft save", async () => {
    mockApi.mockRejectedValueOnce(new Error("读取暂时失败"));
    render(<WorkspaceSettings />);
    expect(await screen.findByRole("alert")).toHaveTextContent("读取暂时失败");
    expect(screen.queryByText("保存设置")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("重新读取设置"));
    await screen.findByText("协作策略");
    expect(mockApi.mock.calls).toEqual([["settings"], ["settings"]]);
  });
  it("loads once on opening and preserves edits across navigation", async () => {
    const view = render(<WorkspaceSettings active={false} />);
    expect(mockApi).not.toHaveBeenCalled();
    view.rerender(<WorkspaceSettings active />);
    await screen.findByText("协作策略");
    fireEvent.change(materialResult(), { target: { value: "12" } });
    view.rerender(<WorkspaceSettings active={false} />);
    view.rerender(<WorkspaceSettings active />);
    expect(materialResult()).toHaveValue("12");
    expect(mockApi).toHaveBeenCalledTimes(1);
  });
  it("restores defaults as a draft and posts a complete revisioned settings object", async () => {
    await ready();
    fireEvent.click(screen.getByText("恢复默认值到草稿"));
    expect(materialResult()).toHaveValue("6");
    expect(screen.getByLabelText("子 agent 能力要求")).toHaveValue(
      "默认能力要求",
    );
    expect(mockApi).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("保存设置"));
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(2));
    expect(mockApi.mock.calls[1]).toEqual([
      "settings",
      { expected_revision: "first", settings: receipt.defaults },
    ]);
    await screen.findByText(/设置已保存/);
  });
  it("rejects empty, fractional and non-finite integers without issuing POST", async () => {
    await ready();
    for (const value of ["", "1.5", "Infinity", "-1", "101"]) {
      fireEvent.change(materialResult(), { target: { value } });
      fireEvent.click(screen.getByText("保存设置"));
      expect(screen.getByRole("alert")).toHaveTextContent("整数");
      expect(mockApi).toHaveBeenCalledTimes(1);
    }
  });
  it("retains draft on conflict and explicitly fetches current revision before retry", async () => {
    await ready();
    fireEvent.change(materialResult(), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("子 agent 能力要求"), {
      target: { value: "低成本模型，低推理深度" },
    });
    mockApi.mockRejectedValueOnce(new Error("版本冲突"));
    fireEvent.click(screen.getByText("保存设置"));
    expect(await screen.findByRole("alert")).toHaveTextContent("草稿已保留");
    expect(materialResult()).toHaveValue("12");
    expect(screen.queryByText(/设置已保存/)).not.toBeInTheDocument();
    mockApi.mockResolvedValueOnce({ ...receipt, revision: "second" });
    fireEvent.click(screen.getByText("读取最新配置（保留草稿）"));
    await screen.findByText(/已读取最新配置/);
    expect(materialResult()).toHaveValue("12");
    fireEvent.click(screen.getByText("保存设置"));
    await waitFor(() =>
      expect(mockApi.mock.calls[3][1]).toMatchObject({
        expected_revision: "second",
        settings: {
          collaboration: { subagent_requirements: "低成本模型，低推理深度" },
        },
      }),
    );
  });
  it("converts displayed MiB and seconds, and blocks duplicate saves while pending", async () => {
    await ready();
    fireEvent.change(screen.getAllByLabelText("读取量（MiB）")[0], {
      target: { value: "20" },
    });
    fireEvent.change(screen.getAllByLabelText("活动超时（秒）")[0], {
      target: { value: "350" },
    });
    let resolve!: (value: SettingsReceipt) => void;
    mockApi.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const button = screen.getByText("保存设置");
    fireEvent.click(button);
    fireEvent.click(button);
    expect(mockApi).toHaveBeenCalledTimes(2);
    expect(button).toBeDisabled();
    expect(screen.getByLabelText("子 agent 能力要求")).toBeDisabled();
    expect(mockApi.mock.calls[1][1]).toMatchObject({
      settings: {
        materials: { budget: { read_bytes: 20971520, wall_ms: 350000 } },
      },
    });
    resolve(receipt);
    await screen.findByText(/设置已保存/);
  });
  it("validates rerank candidate window before writing", async () => {
    await ready();
    fireEvent.change(screen.getByLabelText("重排候选池"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByText("保存设置"));
    expect(screen.getByRole("alert")).toHaveTextContent("不能小于");
    expect(mockApi).toHaveBeenCalledTimes(1);
  });
  it("preserves exact integer bytes and milliseconds through fractional display units", async () => {
    await ready();
    fireEvent.change(screen.getAllByLabelText("读取量（MiB）")[0], {
      target: { value: "0.5" },
    });
    fireEvent.change(screen.getAllByLabelText("活动超时（秒）")[0], {
      target: { value: "1.001" },
    });
    fireEvent.click(screen.getByText("保存设置"));
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(2));
    expect(mockApi.mock.calls[1][1]).toMatchObject({
      settings: {
        materials: { budget: { read_bytes: 524288, wall_ms: 1001 } },
      },
    });
  });
});
