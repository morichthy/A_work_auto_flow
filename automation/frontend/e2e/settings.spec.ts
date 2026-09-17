import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { resolve } from "node:path";
import type { SettingsReceipt } from "../src/WorkspaceSettings";

// 浏览器验收最终预构建资源。设置HTTP被限定为合成数据，
// 验证真实页面导航/输入/错误呈现；后端持久化由独立集成测试负责。
let server: ChildProcess;
let base: string;
test.beforeAll(async () => {
  const root = resolve("../..");
  server = spawn(
    resolve(root, "services/qdrant/runtime/python.exe"),
    [resolve(root, "automation/tests/serve_workbench_test.py")],
    { cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
  );
  base = await new Promise<string>((done, fail) => {
    let output = "";
    const timer = setTimeout(() => {
      server.kill();
      fail(Error("设置沙盒启动超时：" + output));
    }, 30000);
    server.stdout!.on("data", (chunk) => {
      output += chunk;
      for (const line of output.split("\n")) {
        try {
          const value = JSON.parse(line);
          if (value.url) {
            clearTimeout(timer);
            done(value.url);
            return;
          }
        } catch {
          /* 等待完整JSON行。 */
        }
      }
    });
    server.stderr!.on("data", (chunk) => {
      output += chunk;
    });
    server.on("exit", (code) => {
      clearTimeout(timer);
      fail(Error(`设置沙盒退出${code}：${output}`));
    });
  });
});
test.afterAll(async () => {
  server?.kill();
});

test("真实HTTP保存配置并在页面重新载入后保持", async ({
  page,
  request,
}, testInfo) => {
  // 此用例不拦截任何API：直接证明设置页面→HTTP→工作区文件→重新读取。
  const before = await request.get(base + "api/v1/settings");
  expect(before.ok()).toBeTruthy();
  const previous = (await before.json()) as SettingsReceipt;
  const next = previous.settings.materials.result_limit === 12 ? 11 : 12;
  await page.goto(base + "#/settings");
  const result = page.getByLabel("默认结果数", { exact: true }).first();
  await expect(result).toHaveValue(
    String(previous.settings.materials.result_limit),
  );
  await result.fill(String(next));
  await page.getByLabel("最多Owner数", { exact: true }).fill("8");
  await page.getByLabel("最终note估算token", { exact: true }).fill("7000");
  await page.getByLabel("默认阅读模式").selectOption("quick");
  await page.getByLabel("允许不足时联想加深").uncheck();
  await page.getByLabel("最多联想轮次").fill("4");
  await expect(page.getByText("高级资源保护（单次操作）")).toBeVisible();
  const requirements = "  gpt-5.6-luna，low 推理深度；完整阅读并保留来源。\n";
  await page.getByLabel("子 agent", { exact: true }).selectOption("off");
  const capability = page.getByLabel("子 agent 能力要求", { exact: true });
  await expect(capability).toBeEnabled();
  await capability.fill(requirements);
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.getByText(/设置已保存/)).toBeVisible();
  const after = await request.get(base + "api/v1/settings");
  const saved = (await after.json()) as SettingsReceipt;
  expect(saved.settings.materials.result_limit).toBe(next);
  expect(saved.settings.reading.strategy).toBe("quick");
  expect(saved.settings.reading.association).toEqual({
    enabled: false,
    max_rounds: 4,
  });
  expect(saved.settings.collaboration).toEqual({
    subagents: "off",
    subagent_requirements: requirements,
  });
  expect(saved.revision).not.toBe(previous.revision);
  await page.reload();
  await expect(page.getByLabel("默认阅读模式")).toHaveValue("quick");
  await expect(page.getByLabel("最多联想轮次")).toHaveValue("4");
  await expect(page.getByLabel("允许不足时联想加深")).not.toBeChecked();
  await expect(
    page.getByLabel("默认结果数", { exact: true }).first(),
  ).toHaveValue(String(next));
  await expect(capability).toHaveValue(requirements);
  await expect(page.getByLabel("最多Owner数", { exact: true })).toHaveValue(
    "8",
  );
  await expect(
    page.getByLabel("最终note估算token", { exact: true }),
  ).toHaveValue("7000");
  expect(saved.settings.reading.context).toEqual({
    max_owners: 8,
    note_max_tokens: 7000,
  });
  expect(saved.settings.reading.budget).toEqual(
    previous.settings.reading.budget,
  );
  await page.screenshot({
    path: testInfo.outputPath("settings-real-http.png"),
    fullPage: true,
  });
  await testInfo.attach("settings-receipt", {
    body: JSON.stringify(saved, null, 2),
    contentType: "application/json",
  });
});

test("设置草稿跨导航保留，冲突不清空，显式重读后保存", async ({ page }) => {
  const budget = {
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
  const initial = {
    collaboration: {
      subagents: "auto" as const,
      subagent_requirements: "默认低成本能力要求",
    },
    materials: { result_limit: 10, budget: { ...budget } },
    reading: {
      strategy: "standard" as const,
      association: { enabled: true, max_rounds: 3 },
      context: { max_owners: 10, note_max_tokens: 6000 },
      result_limit: 10,
      budget: { ...budget },
      reranking: { mode: "auto" as const, candidate_limit: 30 },
    },
  };
  let receipt: SettingsReceipt = {
    revision: "v1",
    settings: initial,
    defaults: structuredClone(initial),
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
  let saves = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/settings")) {
      if (route.request().method() === "POST") {
        saves += 1;
        const body = route.request().postDataJSON();
        if (saves === 1) {
          receipt = { ...receipt, revision: "v2" };
          await route.fulfill({
            status: 409,
            json: { error: { code: "CONFLICT", message: "版本冲突" } },
          });
          return;
        }
        expect(body.expected_revision).toBe("v2");
        expect(body.settings.materials.result_limit).toBe(12);
        expect(body.settings.collaboration.subagent_requirements).toBe(
          "检索与结构化笔记，低推理深度",
        );
        receipt = { ...receipt, revision: "v3", settings: body.settings };
      }
      await route.fulfill({ json: receipt });
    } else {
      // 仅模拟设置冲突；导航依赖由真实隔离工作区提供，避免不完整全局mock掩盖页面行为。
      await route.continue();
    }
  });
  await page.goto(base + "#/settings");
  await expect(page.getByRole("heading", { name: "工作区设置" })).toBeVisible();
  await page.getByLabel("默认结果数", { exact: true }).first().fill("12");
  await page
    .getByLabel("子 agent 能力要求", { exact: true })
    .fill("检索与结构化笔记，低推理深度");
  await page.locator('nav a[href="#/home"]').click();
  await page.locator('nav a[href="#/settings"]').click();
  await expect(
    page.getByLabel("默认结果数", { exact: true }).first(),
  ).toHaveValue("12");
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("草稿已保留");
  await expect(
    page.getByLabel("子 agent 能力要求", { exact: true }),
  ).toHaveValue("检索与结构化笔记，低推理深度");
  await expect(
    page.getByLabel("默认结果数", { exact: true }).first(),
  ).toHaveValue("12");
  await page.getByRole("button", { name: "读取最新配置（保留草稿）" }).click();
  await expect(page.getByText(/已读取最新配置/)).toBeVisible();
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.getByText(/设置已保存/)).toBeVisible();
  expect(saves).toBe(2);
});
