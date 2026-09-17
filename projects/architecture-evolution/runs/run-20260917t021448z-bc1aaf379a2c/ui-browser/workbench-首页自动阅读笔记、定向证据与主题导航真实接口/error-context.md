# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workbench.spec.ts >> 首页自动阅读笔记、定向证据与主题导航真实接口
- Location: e2e\workbench.spec.ts:230:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText(/panelreading 前提：绝对温度/)
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByText(/panelreading 前提：绝对温度/) with timeout 5000ms
  - waiting for getByText(/panelreading 前提：绝对温度/)

```

```yaml
- complementary:
  - link "研 研发工作台 材料 · 证据 · 联系":
    - /url: "#/home"
  - navigation:
    - link "◫ 工作台":
      - /url: "#/home"
    - link "▦ 材料查询":
      - /url: "#/materials"
    - link "◇ 材料关系":
      - /url: "#/relations"
    - link "▤ 证据与影响":
      - /url: "#/evidence"
    - link "▥ 系统记忆":
      - /url: "#/memory"
    - link "◷ 任务与监测":
      - /url: "#/tasks"
    - link "⚙ 工作区设置":
      - /url: "#/settings"
  - text: 本机工作区 原始记录可追溯
- banner:
  - text: AI 研发工作区
  - group: 观察与环境
  - text: ○ 按需分析
- text: 合成测试沙盒 · 全部样例为虚构，不属于正式业务证据
- heading "当前笔记的证据与影响" [level=1]
- link "浏览全库证据":
  - /url: "#/evidence"
- heading "当前阅读笔记的固定依据" [level=2]
- paragraph: RS-74616932-ebf8-415b-aa1b-cd0d4c0f9478
- paragraph: 以下仅列出已保存理解引用的材料。层级、来源版本与复核结论分别保留。
- heading "L0 原始材料" [level=3]
- paragraph: 当前笔记及一层显式来源中暂无此类记录。
- heading "L1 技术单元" [level=3]
- paragraph: 当前笔记及一层显式来源中暂无此类记录。
- heading "L2 研究经过" [level=3]
- paragraph: 当前笔记及一层显式来源中暂无此类记录。
- heading "L3 经验" [level=3]
- paragraph: 当前笔记及一层显式来源中暂无此类记录。
- heading "L4 整体概览" [level=3]
- paragraph: 当前笔记及一层显式来源中暂无此类记录。
- heading "其他引用记录" [level=3]
- article:
  - heading "证据面板完整文稿" [level=4]
  - link "在系统记忆中查看当前记录":
    - /url: "#/memory?owner=RES-SYNTHETIC&record=MEM-29e6e7ea-bf66-5319-85f2-7e7ecf85aadf"
  - paragraph: 以下为固定版本 r1 · MEM-29e6e7ea-bf66-5319-85f2-7e7ecf85aadf
  - heading "显式固定来源" [level=4]
  - list:
    - listitem:
      - strong: RUN-SYNTHETIC
      - text: · owner · 无修订号
      - paragraph: 未提供定位
      - text: SHA256：0d05ee95c2f8e0e8edb43aefa3a70881d2249c3ebdcdae65a61f5fcde2c2b0b5
  - group: 固定来源与结论复核依据
- heading "其他固定来源与运行证据" [level=3]
- article:
  - heading "RUN-SYNTHETIC" [level=4]
  - paragraph: owner · 未提供定位
  - paragraph: SHA256：0d05ee95c2f8e0e8edb43aefa3a70881d2249c3ebdcdae65a61f5fcde2c2b0b5
- heading "合成温漂测试" [level=3]
- paragraph: 身份：RUN-SYNTHETIC
- paragraph: 原生记录：
- code: "{ \"artifacts\": [ { \"path\": \"runs/synthetic-base/result.txt\", \"sha256\": \"2dfdac35ebe7b071c0d19d296836329458f648ab2ad36dfbe03043d5b7532cfb\" } ], \"claims\": [ { \"claim_id\": \"CLM-SYNTHETIC\", \"evidence_refs\": [ { \"locator\": \"row 2\", \"relation\": \"input\", \"sha256\": \"80547393f25b3100ce0153adf55d948401296b31ffdbcc8e3e02205893e458a3\", \"target\": \"data/catalog/synthetic-measurement.csv\" } ], \"kind\": \"calculation\", \"record_reason\": \"用于验证来源哈希变化后下游报告显示风险\", \"review\": { \"status\": \"not-reviewed\" }, \"review_history\": [], \"scope\": \"synthetic:only\", \"statement\": \"合成计算偏移为 1.4 ms\" } ], \"code\": {}, \"dependencies\": [], \"environment\": {}, \"inputs\": [ { \"path\": \"data/catalog/synthetic-measurement.csv\", \"sha256\": \"80547393f25b3100ce0153adf55d948401296b31ffdbcc8e3e02205893e458a3\" }, { \"path\": \"core-algorithms/synthetic-drift/README.md\", \"sha256\": \"34fce9612f64d404d29c2c4d3dd8f7eaa03b9a15446493923c6cca433d243c82\" } ], \"module_ids\": [ \"MOD-SYNTHETIC\" ], \"parent_run_ids\": [], \"quality_results\": [], \"question\": \"测试引用与失效传播\", \"record_reason\": \"跨模块软件测试样例\", \"review\": { \"status\": \"not-reviewed\" }, \"run_id\": \"RUN-SYNTHETIC\", \"status\": \"running\", \"title\": \"合成温漂测试\" }"
- group: "读取范围与缺口 [ { \"target_id\": \"RUN-SYNTHETIC\", \"code\": \"UNRESOLVED_REFERENCE\", \"affected_ids\": [ \"RUN-SYNTHETIC\" ] }, { \"target_id\": \"RUN-SYNTHETIC\", \"code\": \"UNRESOLVED_REFERENCE\", \"affected_ids\": [ \"RUN-SYNTHETIC\" ] }, { \"target_id\": \"RUN-SYNTHETIC\", \"code\": \"UNRESOLVED_REFERENCE\", \"affected_ids\": [ \"RUN-SYNTHETIC\" ] } ]"
- article:
  - heading "证据面板完整文稿" [level=3]
  - paragraph: 层级未提供 · 笔记固定出处（需按需展开）
  - paragraph: record · MEM-29e6e7ea-bf66-5319-85f2-7e7ecf85aadf · r1
  - paragraph: SHA256：614f8f728882d01c863a43d17cc1639864315ad32a2c0fd09723b00a8df60991
  - group: 固定原记录路径
```

# Test source

```ts
  152 |     await testInfo.attach("navigation-metrics", {
  153 |       body: JSON.stringify({ firstNoteMs, requests: calls }),
  154 |       contentType: "application/json",
  155 |     });
  156 |   } finally {
  157 |     app.process.kill();
  158 |   }
  159 | });
  160 | 
  161 | test("三模式会话显式保存方向、重新载入与快速覆盖提示真实接口", async ({
  162 |   page,
  163 |   request,
  164 | }, testInfo) => {
  165 |   const app = await server(false, true);
  166 |   try {
  167 |     await page.goto(app.url + "#/home");
  168 |     await page.getByText("阅读模式与联想方向", { exact: true }).click();
  169 |     const mode = page.getByLabel("当前阅读模式");
  170 |     await expect(mode).toHaveValue("standard");
  171 |     await mode.selectOption("quick");
  172 |     await page
  173 |       .getByLabel("联想搜索文本（可选）")
  174 |       .fill("温度偏置与量化误差的联系");
  175 |     await page
  176 |       .getByRole("button", { name: "保存阅读模式与方向", exact: true })
  177 |       .click();
  178 |     await expect(page.getByText(/尚未启动搜索/)).toBeVisible();
  179 |     await page.reload();
  180 |     await page.getByText("阅读模式与联想方向", { exact: true }).click();
  181 |     await expect(mode).toHaveValue("quick");
  182 |     await expect(page.getByLabel("联想搜索文本（可选）")).toHaveValue(
  183 |       "温度偏置与量化误差的联系",
  184 |     );
  185 |     await page.locator('nav a[href="#/home"]').click();
  186 |     await expect(
  187 |       page.getByText("快速阅读：笔记依据已交付的召回文本，不代表全文覆盖。", {
  188 |         exact: true,
  189 |       }),
  190 |     ).toBeVisible();
  191 |     await expect(
  192 |       page.getByRole("link", { name: "选择阅读会话", exact: true }),
  193 |     ).toHaveCount(0);
  194 |     await mode.selectOption("associative");
  195 |     await page
  196 |       .getByRole("button", { name: "保存阅读模式与方向", exact: true })
  197 |       .click();
  198 |     await expect(page.getByText(/尚未启动搜索/)).toBeVisible();
  199 |     const sessions = await request.post(
  200 |       app.url + "api/v1/materials/reading-list",
  201 |       {
  202 |         headers: { Origin: new URL(app.url).origin },
  203 |         data: { owner_id: "RES-SYNTHETIC", offset: 0, limit: 20 },
  204 |       },
  205 |     );
  206 |     const id = (await sessions.json()).value.items[0].session_id;
  207 |     const result = await request.post(
  208 |       app.url + "api/v1/materials/reading-view",
  209 |       {
  210 |         headers: { Origin: new URL(app.url).origin },
  211 |         data: { session_id: id, notes_only: true },
  212 |       },
  213 |     );
  214 |     const saved = (await result.json()).value;
  215 |     expect(saved.strategy).toBe("associative");
  216 |     expect(saved.association.enabled).toBe(true);
  217 |     expect(saved.association_text).toBe("温度偏置与量化误差的联系");
  218 |     await testInfo.attach("reading-configured", {
  219 |       body: JSON.stringify(saved, null, 2),
  220 |       contentType: "application/json",
  221 |     });
  222 |     await page.screenshot({
  223 |       path: testInfo.outputPath("reading-three-modes.png"),
  224 |       fullPage: true,
  225 |     });
  226 |   } finally {
  227 |     app.process.kill();
  228 |   }
  229 | });
  230 | test("首页自动阅读笔记、定向证据与主题导航真实接口", async ({ page }) => {
  231 |   const app = await server(false, true);
  232 |   try {
  233 |     await page.goto(app.url);
  234 |     await expect(
  235 |       page.getByText("合成阅读理解：保留前提", { exact: true }),
  236 |     ).toBeVisible();
  237 |     await expect(page.getByRole("link", { name: /打开材料关系/ })).toHaveCount(
  238 |       0,
  239 |     );
  240 |     await page
  241 |       .getByRole("link", { name: "查看证据与影响", exact: true })
  242 |       .click();
  243 |     await expect(
  244 |       page.getByRole("heading", { name: "当前笔记的证据与影响" }),
  245 |     ).toBeVisible();
  246 |     await expect(page.getByText("正在读取固定依据及一层显式来源…")).toHaveCount(
  247 |       0,
  248 |     );
  249 |     await expect(
  250 |       page.getByRole("heading", { name: "L1 技术单元", exact: true }),
  251 |     ).toBeVisible();
> 252 |     await expect(page.getByText(/panelreading 前提：绝对温度/)).toBeVisible();
      |                                                          ^ Error: expect(locator).toBeVisible() failed
  253 |     await page.screenshot({
  254 |       path: resolve(
  255 |         root,
  256 |         "projects/architecture-evolution/runs/run-20260916t155857z-a3d7b61bdd32/.run-captures/home/note-evidence.png",
  257 |       ),
  258 |       fullPage: true,
  259 |     });
  260 |     await page.getByRole("link", { name: "◫ 工作台", exact: true }).click();
  261 |     await expect(page.getByRole("heading", { name: "材料导航" })).toBeVisible();
  262 |     await page.screenshot({
  263 |       path: resolve(
  264 |         root,
  265 |         "projects/architecture-evolution/runs/run-20260916t155857z-a3d7b61bdd32/.run-captures/home/home-wide.png",
  266 |       ),
  267 |       fullPage: true,
  268 |     });
  269 |     await page.setViewportSize({ width: 760, height: 1000 });
  270 |     await expect(
  271 |       page.getByRole("heading", { name: "当前阅读笔记" }),
  272 |     ).toBeVisible();
  273 |     await page.screenshot({
  274 |       path: resolve(
  275 |         root,
  276 |         "projects/architecture-evolution/runs/run-20260916t155857z-a3d7b61bdd32/.run-captures/home/home-narrow.png",
  277 |       ),
  278 |       fullPage: true,
  279 |     });
  280 |   } finally {
  281 |     app.process.kill();
  282 |   }
  283 | });
  284 | async function server(
  285 |   scale = false,
  286 |   reading = false,
  287 | ): Promise<{ process: ChildProcess; url: string }> {
  288 |   const process = spawn(
  289 |     resolve(root, "services/qdrant/runtime/python.exe"),
  290 |     [
  291 |       resolve(root, "automation/tests/serve_workbench_test.py"),
  292 |       ...(scale ? ["--scale"] : []),
  293 |       ...(reading ? ["--reading"] : []),
  294 |     ],
  295 |     { cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
  296 |   );
  297 |   return new Promise((ok, fail) => {
  298 |     let output = "";
  299 |     const timer = setTimeout(() => {
  300 |       process.kill();
  301 |       fail(Error("测试服务启动超时"));
  302 |     }, 30000);
  303 |     process.stdout!.on("data", (chunk) => {
  304 |       output += chunk;
  305 |       for (const line of output.split("\n")) {
  306 |         try {
  307 |           const value = JSON.parse(line);
  308 |           if (value.url) {
  309 |             clearTimeout(timer);
  310 |             ok({ process, url: value.url });
  311 |             return;
  312 |           }
  313 |         } catch {}
  314 |       }
  315 |     });
  316 |     process.stderr!.on("data", (c) => {
  317 |       output += c;
  318 |     });
  319 |     process.on("exit", (code) => {
  320 |       clearTimeout(timer);
  321 |       fail(Error(`服务退出 ${code}: ${output}`));
  322 |     });
  323 |   });
  324 | }
  325 | test("完整导航、关系、证据、候选和摘要", async ({ page }) => {
  326 |   const app = await server();
  327 |   const errors: string[] = [];
  328 |   page.on("pageerror", (e) => errors.push(e.message));
  329 |   try {
  330 |     await page.goto(app.url);
  331 |     await expect(
  332 |       page.getByRole("heading", { name: "把材料连接到问题" }),
  333 |     ).toBeVisible();
  334 |     await page.screenshot({
  335 |       path: resolve(root, "tmp/workbench-home.png"),
  336 |       fullPage: true,
  337 |     });
  338 |     // 首页按用户要求只保留note证据入口；关系功能仍从侧栏进入。
  339 |     await page.locator('nav a[href="#/relations"]').click();
  340 |     await page
  341 |       .getByRole("checkbox", { name: "原生导航（未分层）", exact: true })
  342 |       .check();
  343 |     await page.getByRole("checkbox", { name: "L2 过程", exact: true }).check();
  344 |     await expect(
  345 |       page.getByRole("heading", { name: "从问题出发，看见联系" }),
  346 |     ).toBeVisible();
  347 |     await expect(page.getByRole("img", { name: "材料关系图" })).toBeVisible();
  348 |     await page.getByLabel("查找中心材料").fill("CLM-SYNTHETIC");
  349 |     await page.getByRole("button", { name: /结论 合成计算偏移/ }).click();
  350 |     await page.getByRole("button", { name: "以此为中心", exact: true }).click();
  351 |     await page.getByRole("button", { name: "加入分析选择" }).click();
  352 |     await page.getByLabel("候选标题").fill("检查共同温度来源");
```