# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: settings.spec.ts >> 设置草稿跨导航保留，冲突不清空，显式重读后保存
- Location: e2e\settings.spec.ts:96:1

# Error details

```
Test timeout of 60000ms exceeded.
```

```
Error: locator.fill: Test timeout of 60000ms exceeded.
Call log:
  - waiting for getByLabel('子 agent 能力要求', { exact: true })

```

# Test source

```ts
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
  168 |         },
  169 |       });
  170 |     } else if (path.endsWith("/jobs"))
  171 |       await route.fulfill({ json: { jobs: [] } });
  172 |     else await route.fulfill({ json: { api_version: 1 } });
  173 |   });
  174 |   await page.goto(base + "#settings");
  175 |   await expect(page.getByRole("heading", { name: "工作区设置" })).toBeVisible();
  176 |   await page.getByLabel("默认结果数", { exact: true }).first().fill("12");
  177 |   await page
  178 |     .getByLabel("子 agent 能力要求", { exact: true })
> 179 |     .fill("检索与结构化笔记，低推理深度");
      |      ^ Error: locator.fill: Test timeout of 60000ms exceeded.
  180 |   await page.locator('nav a[href="#/home"]').click();
  181 |   await page.locator('nav a[href="#/settings"]').click();
  182 |   await expect(
  183 |     page.getByLabel("默认结果数", { exact: true }).first(),
  184 |   ).toHaveValue("12");
  185 |   await page.getByRole("button", { name: "保存设置", exact: true }).click();
  186 |   await expect(page.getByRole("alert")).toContainText("草稿已保留");
  187 |   await expect(
  188 |     page.getByLabel("子 agent 能力要求", { exact: true }),
  189 |   ).toHaveValue("检索与结构化笔记，低推理深度");
  190 |   await expect(
  191 |     page.getByLabel("默认结果数", { exact: true }).first(),
  192 |   ).toHaveValue("12");
  193 |   await page.getByRole("button", { name: "读取最新配置（保留草稿）" }).click();
  194 |   await expect(page.getByText(/已读取最新配置/)).toBeVisible();
  195 |   await page.getByRole("button", { name: "保存设置", exact: true }).click();
  196 |   await expect(page.getByText(/设置已保存/)).toBeVisible();
  197 |   expect(saves).toBe(2);
  198 | });
  199 | 
```