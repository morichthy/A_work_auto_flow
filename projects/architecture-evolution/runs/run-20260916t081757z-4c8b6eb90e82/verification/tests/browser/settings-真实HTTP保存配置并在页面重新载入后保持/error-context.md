# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: settings.spec.ts >> 真实HTTP保存配置并在页面重新载入后保持
- Location: e2e\settings.spec.ts:51:1

# Error details

```
Test timeout of 60000ms exceeded.
```

```
Error: locator.selectOption: Test timeout of 60000ms exceeded.
Call log:
  - waiting for getByLabel('子 agent', { exact: true })

```

# Test source

```ts
  1   | import { test, expect } from "@playwright/test";
  2   | import { spawn, type ChildProcess } from "node:child_process";
  3   | import { resolve } from "node:path";
  4   | import type { SettingsReceipt } from "../src/WorkspaceSettings";
  5   | 
  6   | // 浏览器验收最终预构建资源。设置HTTP被限定为合成数据，
  7   | // 验证真实页面导航/输入/错误呈现；后端持久化由独立集成测试负责。
  8   | let server: ChildProcess;
  9   | let base: string;
  10  | test.beforeAll(async () => {
  11  |   const root = resolve("../..");
  12  |   server = spawn(
  13  |     resolve(root, "services/qdrant/runtime/python.exe"),
  14  |     [resolve(root, "automation/tests/serve_workbench_test.py")],
  15  |     { cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
  16  |   );
  17  |   base = await new Promise<string>((done, fail) => {
  18  |     let output = "";
  19  |     const timer = setTimeout(() => {
  20  |       server.kill();
  21  |       fail(Error("设置沙盒启动超时：" + output));
  22  |     }, 30000);
  23  |     server.stdout!.on("data", (chunk) => {
  24  |       output += chunk;
  25  |       for (const line of output.split("\n")) {
  26  |         try {
  27  |           const value = JSON.parse(line);
  28  |           if (value.url) {
  29  |             clearTimeout(timer);
  30  |             done(value.url);
  31  |             return;
  32  |           }
  33  |         } catch {
  34  |           /* 等待完整JSON行。 */
  35  |         }
  36  |       }
  37  |     });
  38  |     server.stderr!.on("data", (chunk) => {
  39  |       output += chunk;
  40  |     });
  41  |     server.on("exit", (code) => {
  42  |       clearTimeout(timer);
  43  |       fail(Error(`设置沙盒退出${code}：${output}`));
  44  |     });
  45  |   });
  46  | });
  47  | test.afterAll(async () => {
  48  |   server?.kill();
  49  | });
  50  | 
  51  | test("真实HTTP保存配置并在页面重新载入后保持", async ({
  52  |   page,
  53  |   request,
  54  | }, testInfo) => {
  55  |   // 此用例不拦截任何API：直接证明设置页面→HTTP→工作区文件→重新读取。
  56  |   const before = await request.get(base + "api/v1/settings");
  57  |   expect(before.ok()).toBeTruthy();
  58  |   const previous = (await before.json()) as SettingsReceipt;
  59  |   const next = previous.settings.materials.result_limit === 12 ? 11 : 12;
  60  |   await page.goto(base + "#/settings");
  61  |   const result = page.getByLabel("默认结果数", { exact: true }).first();
  62  |   await expect(result).toHaveValue(
  63  |     String(previous.settings.materials.result_limit),
  64  |   );
  65  |   await result.fill(String(next));
  66  |   const requirements = "  gpt-5.6-luna，low 推理深度；完整阅读并保留来源。\n";
> 67  |   await page.getByLabel("子 agent", { exact: true }).selectOption("off");
      |                                                     ^ Error: locator.selectOption: Test timeout of 60000ms exceeded.
  68  |   const capability = page.getByLabel("子 agent 能力要求", { exact: true });
  69  |   await expect(capability).toBeEnabled();
  70  |   await capability.fill(requirements);
  71  |   await page.getByRole("button", { name: "保存设置", exact: true }).click();
  72  |   await expect(page.getByText(/设置已保存/)).toBeVisible();
  73  |   const after = await request.get(base + "api/v1/settings");
  74  |   const saved = (await after.json()) as SettingsReceipt;
  75  |   expect(saved.settings.materials.result_limit).toBe(next);
  76  |   expect(saved.settings.collaboration).toEqual({
  77  |     subagents: "off",
  78  |     subagent_requirements: requirements,
  79  |   });
  80  |   expect(saved.revision).not.toBe(previous.revision);
  81  |   await page.reload();
  82  |   await expect(
  83  |     page.getByLabel("默认结果数", { exact: true }).first(),
  84  |   ).toHaveValue(String(next));
  85  |   await expect(capability).toHaveValue(requirements);
  86  |   await page.screenshot({
  87  |     path: testInfo.outputPath("settings-real-http.png"),
  88  |     fullPage: true,
  89  |   });
  90  |   await testInfo.attach("settings-receipt", {
  91  |     body: JSON.stringify(saved, null, 2),
  92  |     contentType: "application/json",
  93  |   });
  94  | });
  95  | 
  96  | test("设置草稿跨导航保留，冲突不清空，显式重读后保存", async ({ page }) => {
  97  |   const budget = {
  98  |     wall_ms: 300000,
  99  |     read_bytes: 16777216,
  100 |     output_chars: 80000,
  101 |     candidates: 100,
  102 |     graph_nodes: 50,
  103 |     graph_edges: 100,
  104 |     graph_hops: 2,
  105 |     model_tokens: 512,
  106 |     model_calls: 1,
  107 |     model_input_tokens: 512,
  108 |     model_output_tokens: 0,
  109 |     rerank_items: 0,
  110 |   };
  111 |   const initial = {
  112 |     collaboration: {
  113 |       subagents: "auto" as const,
  114 |       subagent_requirements: "默认低成本能力要求",
  115 |     },
  116 |     materials: { result_limit: 10, budget: { ...budget } },
  117 |     reading: {
  118 |       result_limit: 10,
  119 |       budget: { ...budget },
  120 |       reranking: { mode: "auto" as const, candidate_limit: 30 },
  121 |     },
  122 |   };
  123 |   let receipt: SettingsReceipt = {
  124 |     revision: "v1",
  125 |     settings: initial,
  126 |     defaults: structuredClone(initial),
  127 |     limits: {
  128 |       ...budget,
  129 |       wall_ms: 600000,
  130 |       read_bytes: 33554432,
  131 |       output_chars: 100000,
  132 |       candidates: 2000,
  133 |       model_tokens: 200000,
  134 |       model_calls: 20,
  135 |       rerank_items: 200,
  136 |     },
  137 |   };
  138 |   let saves = 0;
  139 |   await page.route("**/api/**", async (route) => {
  140 |     const path = new URL(route.request().url()).pathname;
  141 |     if (path.endsWith("/settings")) {
  142 |       if (route.request().method() === "POST") {
  143 |         saves += 1;
  144 |         const body = route.request().postDataJSON();
  145 |         if (saves === 1) {
  146 |           receipt = { ...receipt, revision: "v2" };
  147 |           await route.fulfill({
  148 |             status: 409,
  149 |             json: { error: { code: "CONFLICT", message: "版本冲突" } },
  150 |           });
  151 |           return;
  152 |         }
  153 |         expect(body.expected_revision).toBe("v2");
  154 |         expect(body.settings.materials.result_limit).toBe(12);
  155 |         expect(body.settings.collaboration.subagent_requirements).toBe(
  156 |           "检索与结构化笔记，低推理深度",
  157 |         );
  158 |         receipt = { ...receipt, revision: "v3", settings: body.settings };
  159 |       }
  160 |       await route.fulfill({ json: receipt });
  161 |     } else if (path.endsWith("/workbench")) {
  162 |       await route.fulfill({
  163 |         json: {
  164 |           root: "synthetic-settings",
  165 |           synthetic: true,
  166 |           modules: [],
  167 |           monitor_running: false,
```