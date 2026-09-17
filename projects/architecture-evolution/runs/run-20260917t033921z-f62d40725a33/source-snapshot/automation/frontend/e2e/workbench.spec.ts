import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { resolve } from "node:path";
import { readFile } from "node:fs/promises";
const root = resolve("../..");
test("记忆摘要进入完整文稿与来源图片证据", async ({ page }, testInfo) => {
  const app = await server(false, true);
  try {
    await page.goto(app.url + "#/memory");
    await page.getByLabel("记忆归属对象").selectOption("RES-SYNTHETIC");
    await expect(
      page.getByRole("button", { name: "阅读记录", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "对象记忆", exact: true }).click();
    await page
      .getByRole("button", { name: "生成对象记忆", exact: true })
      .click();
    const link = page.getByRole("link", { name: "面板固定方法", exact: true });
    await expect(link).toBeVisible();
    await expect(
      page
        .getByRole("group", { name: "按层级或类型筛选" })
        .getByRole("checkbox"),
    ).toHaveCount(6);
    await expect(
      page.getByText("结构、固定来源与版本", { exact: true }),
    ).toHaveCount(0);
    await link.click();
    await expect(
      page.getByRole("heading", { name: "对象整体概览", exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("结论确认状态")).toContainText(
      "本页未重新核验",
    );
    await page.getByLabel("搜索证据").fill("证据面板完整文稿");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByRole("link", { name: /证据面板完整文稿/ }).click();
    const detail = page.getByLabel("选中证据详情");
    await expect(
      detail.getByRole("heading", { name: "完整文稿", exact: true }),
    ).toBeVisible();
    await expect(
      detail.getByRole("heading", { name: "证据面板固定章节", exact: true }),
    ).toBeVisible();
    await expect(
      detail.getByRole("heading", { name: "参考文献", exact: true }),
    ).toHaveCount(1);
    const figure = detail.locator("img").first();
    await expect(figure).toBeVisible();
    await expect
      .poll(() =>
        figure.evaluate((image: HTMLImageElement) => image.naturalWidth),
      )
      .toBeGreaterThan(0);
    await page.screenshot({
      path: testInfo.outputPath("evidence-complete-document.png"),
      fullPage: true,
    });
    await page.goto(app.url + "#/evidence?id=SRC-PANEL-FIGURE");
    const sourceImage = page.getByLabel("选中证据详情").locator("img");
    await expect(sourceImage).toBeVisible();
    await expect
      .poll(() =>
        sourceImage.evaluate((image: HTMLImageElement) => image.naturalWidth),
      )
      .toBeGreaterThan(0);
    await page.screenshot({
      path: testInfo.outputPath("evidence-source-image.png"),
      fullPage: true,
    });
  } finally {
    app.process.kill();
  }
});
test("最近问题重开选择、公式与编号引用双向证据导航真实接口", async ({
  page,
}, testInfo) => {
  const app = await server(false, true);
  const calls: string[] = [];
  page.on("request", (request) => calls.push(new URL(request.url()).pathname));
  const started = Date.now();
  try {
    await page.goto(app.url);
    const picker = page.getByLabel("最近24小时阅读问题");
    await expect(picker.locator("option")).toHaveCount(3);
    await expect(
      page.getByText("合成阅读理解：保留前提", { exact: true }),
    ).toBeVisible();
    const firstNoteMs = Date.now() - started;
    await expect(page.locator(".katex").first()).toBeVisible();
    await expect(page.getByText(/未重新核验证据；用于继续研究/)).toBeVisible();
    expect(calls.some((path) => path.endsWith("/api/state"))).toBe(false);
    expect(calls.some((path) => path.endsWith("/evidence/search"))).toBe(false);
    const auxiliary = await picker
      .locator("option")
      .filter({ hasText: "辅助合成问题" })
      .getAttribute("value");
    await picker.selectOption(auxiliary!);
    await expect(
      page.getByText("第二问题的独立理解", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await expect(picker).toHaveValue(auxiliary!);
    await expect(
      page.getByText("第二问题的独立理解", { exact: true }),
    ).toBeVisible();
    const main = await picker
      .locator("option")
      .filter({ hasText: "合成阅读会话" })
      .getAttribute("value");
    await picker.selectOption(main!);
    await expect(
      page.getByText("合成阅读理解：保留前提", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("recent-note-formulas.png"),
      fullPage: true,
    });
    await page.locator(".katex-display").first().scrollIntoViewIfNeeded();
    await page.screenshot({
      path: testInfo.outputPath("note-formula-detail.png"),
      fullPage: true,
    });
    const citation = page
      .locator('[aria-label="当前阅读笔记全文"] a[href^="#/evidence?id=MEM-"]')
      .first();
    await expect(citation).toBeVisible();
    await citation.click();
    const detail = page.getByLabel("选中证据详情");
    await expect(
      detail.getByRole("heading", { name: "证据面板完整文稿", exact: true }),
    ).toBeVisible();
    await expect(
      detail.getByRole("heading", { name: "关键上下文", exact: true }),
    ).toBeVisible();
    await detail
      .locator(".evidence-links")
      .getByRole("link", { name: "合成温漂测试", exact: true })
      .click();
    await expect(
      detail.getByRole("heading", { name: "合成温漂测试", exact: true }),
    ).toBeVisible();
    await detail
      .getByRole("link", { name: "面板固定方法", exact: true })
      .click();
    await expect(
      detail.getByRole("heading", { name: "面板固定方法", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("evidence-record-relations.png"),
      fullPage: true,
    });
    await page.goBack();
    await expect(
      detail.getByRole("heading", { name: "合成温漂测试", exact: true }),
    ).toBeVisible();
    await page.setViewportSize({ width: 760, height: 1000 });
    await page.screenshot({
      path: testInfo.outputPath("evidence-narrow.png"),
      fullPage: true,
    });
    await testInfo.attach("navigation-metrics", {
      body: JSON.stringify({ firstNoteMs, requests: calls }),
      contentType: "application/json",
    });
  } finally {
    app.process.kill();
  }
});

test("三模式会话显式保存方向、重新载入与快速覆盖提示真实接口", async ({
  page,
  request,
}, testInfo) => {
  const app = await server(false, true);
  try {
    await page.goto(app.url + "#/home");
    await page.getByText("阅读模式与联想方向", { exact: true }).click();
    const mode = page.getByLabel("当前阅读模式");
    await expect(mode).toHaveValue("standard");
    await mode.selectOption("quick");
    await page
      .getByLabel("联想搜索文本（可选）")
      .fill("温度偏置与量化误差的联系");
    await page
      .getByRole("button", { name: "保存阅读模式与方向", exact: true })
      .click();
    await expect(page.getByText(/尚未启动搜索/)).toBeVisible();
    await page.reload();
    await page.getByText("阅读模式与联想方向", { exact: true }).click();
    await expect(mode).toHaveValue("quick");
    await expect(page.getByLabel("联想搜索文本（可选）")).toHaveValue(
      "温度偏置与量化误差的联系",
    );
    await page.locator('nav a[href="#/home"]').click();
    await expect(
      page.getByText("快速阅读：笔记依据已交付的召回文本，不代表全文覆盖。", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "选择阅读会话", exact: true }),
    ).toHaveCount(0);
    await mode.selectOption("associative");
    await page
      .getByRole("button", { name: "保存阅读模式与方向", exact: true })
      .click();
    await expect(page.getByText(/尚未启动搜索/)).toBeVisible();
    const sessions = await request.post(
      app.url + "api/v1/materials/reading-list",
      {
        headers: { Origin: new URL(app.url).origin },
        data: { owner_id: "RES-SYNTHETIC", offset: 0, limit: 20 },
      },
    );
    const id = (await sessions.json()).value.items[0].session_id;
    const result = await request.post(
      app.url + "api/v1/materials/reading-view",
      {
        headers: { Origin: new URL(app.url).origin },
        data: { session_id: id, notes_only: true },
      },
    );
    const saved = (await result.json()).value;
    expect(saved.strategy).toBe("associative");
    expect(saved.association.enabled).toBe(true);
    expect(saved.association_text).toBe("温度偏置与量化误差的联系");
    await testInfo.attach("reading-configured", {
      body: JSON.stringify(saved, null, 2),
      contentType: "application/json",
    });
    await page.screenshot({
      path: testInfo.outputPath("reading-three-modes.png"),
      fullPage: true,
    });
  } finally {
    app.process.kill();
  }
});
test("首页自动阅读笔记、定向证据与主题导航真实接口", async ({ page }) => {
  const app = await server(false, true);
  try {
    await page.goto(app.url);
    await expect(
      page.getByText("合成阅读理解：保留前提", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: /打开材料关系/ })).toHaveCount(
      0,
    );
    await page
      .getByRole("link", { name: "查看证据与影响", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "当前笔记的证据与影响" }),
    ).toBeVisible();
    await expect(page.getByText("正在读取固定依据及一层显式来源…")).toHaveCount(
      0,
    );
    await page
      .getByRole("link", { name: "证据面板完整文稿", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "证据面板固定章节", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(
        root,
        "projects/architecture-evolution/runs/run-20260916t155857z-a3d7b61bdd32/.run-captures/home/note-evidence.png",
      ),
      fullPage: true,
    });
    await page.getByRole("link", { name: "◫ 工作台", exact: true }).click();
    await expect(page.getByRole("heading", { name: "材料导航" })).toBeVisible();
    await page.screenshot({
      path: resolve(
        root,
        "projects/architecture-evolution/runs/run-20260916t155857z-a3d7b61bdd32/.run-captures/home/home-wide.png",
      ),
      fullPage: true,
    });
    await page.setViewportSize({ width: 760, height: 1000 });
    await expect(
      page.getByRole("heading", { name: "当前阅读笔记" }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(
        root,
        "projects/architecture-evolution/runs/run-20260916t155857z-a3d7b61bdd32/.run-captures/home/home-narrow.png",
      ),
      fullPage: true,
    });
  } finally {
    app.process.kill();
  }
});
async function server(
  scale = false,
  reading = false,
): Promise<{ process: ChildProcess; url: string }> {
  const process = spawn(
    resolve(root, "services/qdrant/runtime/python.exe"),
    [
      resolve(root, "automation/tests/serve_workbench_test.py"),
      ...(scale ? ["--scale"] : []),
      ...(reading ? ["--reading"] : []),
    ],
    { cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
  );
  return new Promise((ok, fail) => {
    let output = "";
    const timer = setTimeout(() => {
      process.kill();
      fail(Error("测试服务启动超时"));
    }, 30000);
    process.stdout!.on("data", (chunk) => {
      output += chunk;
      for (const line of output.split("\n")) {
        try {
          const value = JSON.parse(line);
          if (value.url) {
            clearTimeout(timer);
            ok({ process, url: value.url });
            return;
          }
        } catch {}
      }
    });
    process.stderr!.on("data", (c) => {
      output += c;
    });
    process.on("exit", (code) => {
      clearTimeout(timer);
      fail(Error(`服务退出 ${code}: ${output}`));
    });
  });
}
test("完整导航、关系、证据、候选和摘要", async ({ page }) => {
  const app = await server();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await page.goto(app.url);
    await expect(
      page.getByRole("heading", { name: "把材料连接到问题" }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(root, "tmp/workbench-home.png"),
      fullPage: true,
    });
    // 首页按用户要求只保留note证据入口；关系功能仍从侧栏进入。
    await page.locator('nav a[href="#/relations"]').click();
    await page
      .getByRole("checkbox", { name: "原生导航（未分层）", exact: true })
      .check();
    await page.getByRole("checkbox", { name: "L2 过程", exact: true }).check();
    await expect(
      page.getByRole("heading", { name: "从问题出发，看见联系" }),
    ).toBeVisible();
    await expect(page.getByRole("img", { name: "材料关系图" })).toBeVisible();
    await page.getByLabel("查找中心材料").fill("CLM-SYNTHETIC");
    await page.getByRole("button", { name: /结论 合成计算偏移/ }).click();
    await page.getByRole("button", { name: "以此为中心", exact: true }).click();
    await page.getByRole("button", { name: "加入分析选择" }).click();
    await page.getByLabel("候选标题").fill("检查共同温度来源");
    await page.getByLabel("候选解释").fill("测试中的关联建议，未复核");
    await page.getByRole("button", { name: "保存候选", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "检查共同温度来源" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "主题聚合", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "折叠所有分组" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "全范围结构聚类", exact: true })
      .click();
    await expect(page.getByText(/Louvain; resolution=1/)).toBeVisible();
    await page.screenshot({
      path: resolve(root, "tmp/workbench-groups.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "证据链", exact: true }).click();
    const downloaded = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出 JSON", exact: true }).click();
    expect((await downloaded).suggestedFilename()).toBe(
      "material-relations.json",
    );
    await page.locator('nav a[href="#/evidence"]').click();
    await page.getByLabel("搜索证据").fill("CLM-SYNTHETIC");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page
      .getByLabel("证据搜索列表")
      .getByRole("link", { name: /合成计算偏移/ })
      .click();
    await expect(
      page
        .getByLabel("选中证据详情")
        .getByRole("heading", { name: /合成计算偏移/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "引用与依据", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(root, "tmp/workbench-evidence.png"),
      fullPage: true,
    });
    // The small navigation baseline also exercises real monitor controls and
    // environment jobs, including their observable result, without models or
    // business inputs. The fixture service is stopped in finally below.
    await page.locator('nav a[href="#/tasks"]').click();
    await page
      .getByRole("button", { name: "开启持续监测", exact: true })
      .click();
    await expect(
      page.getByText("● 只读监测运行中", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "停止持续监测", exact: true })
      .click();
    await expect(page.getByText("○ 按需分析", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: "检查环境能力", exact: true })
      .click();
    const environmentJob = page
      .locator(".proposal")
      .filter({ has: page.getByText("环境检查", { exact: true }) })
      .first();
    await expect(environmentJob.locator(".badge")).toHaveText("succeeded", {
      timeout: 60000,
    });
    await environmentJob.getByText("结果与覆盖范围", { exact: true }).click();
    await expect(environmentJob.locator("pre")).not.toHaveText("null");
    expect(errors).toEqual([]);
  } finally {
    app.process.kill();
  }
});
test("证据页首次进入加载，顶层切换复用已加载状态", async ({ page }) => {
  const app = await server();
  const stateRequests: string[] = [];
  const searchRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/state")) stateRequests.push(request.url());
    if (request.url().endsWith("/evidence/search"))
      searchRequests.push(request.url());
  });
  try {
    await page.goto(app.url);
    await expect(
      page.getByRole("heading", { name: "把材料连接到问题" }),
    ).toBeVisible();
    expect(stateRequests).toHaveLength(0);
    expect(searchRequests).toHaveLength(0);
    await page.locator('nav a[href="#/evidence"]').click();
    await expect(
      page.getByRole("heading", { name: "查看依据，检查影响" }),
    ).toBeVisible();
    await expect.poll(() => searchRequests.length).toBe(1);
    expect(stateRequests).toHaveLength(0);
    await page.locator('nav a[href="#/relations"]').click();
    await page.locator('nav a[href="#/evidence"]').click();
    await expect(
      page.getByRole("heading", { name: "查看依据，检查影响" }),
    ).toBeVisible();
    expect(searchRequests).toHaveLength(1);
    expect(stateRequests).toHaveLength(0);
  } finally {
    app.process.kill();
  }
});
test("勾选联动图与导出，分类结合搜索且保留跨分类勾选", async ({
  page,
  request,
}) => {
  const app = await server();
  try {
    await page.goto(app.url + "#/relations");
    await page
      .getByRole("checkbox", { name: "原生导航（未分层）", exact: true })
      .check();
    await page.getByRole("checkbox", { name: "L2 过程", exact: true }).check();
    await expect(page.getByRole("img", { name: "材料关系图" })).toBeVisible();
    const rawCatalog = await (
      await request.get(app.url + "api/v1/catalog")
    ).json();
    // Legacy navigation is explicit; raw Run artifacts remain trace-only even
    // in this compatibility test and cannot act as invisible graph bridges.
    const allowed = new Set(
      rawCatalog.nodes
        .filter(
          (n: { level?: string }) =>
            !n.level || n.level === "L1" || n.level === "L2",
        )
        .map((n: { id: string }) => n.id),
    );
    const catalog = {
      ...rawCatalog,
      nodes: rawCatalog.nodes.filter((n: { id: string }) => allowed.has(n.id)),
      edges: rawCatalog.edges.filter(
        (e: { source: string; target: string }) =>
          allowed.has(e.source) && allowed.has(e.target),
      ),
    };
    const expected = (ids: string[]) => {
      const selected = new Set(ids);
      for (const edge of catalog.edges) {
        if (ids.includes(edge.source)) selected.add(edge.target);
        if (ids.includes(edge.target)) selected.add(edge.source);
      }
      return [...selected].sort();
    };
    async function assertExport(ids: string[]) {
      const visible = expected(ids);
      await expect(page.locator(".graph-main")).toContainText(
        `显示 ${visible.length} 个节点`,
      );
      const pending = page.waitForEvent("download");
      await page
        .getByRole("button", { name: "导出 JSON", exact: true })
        .click();
      const file = await (await pending).path();
      const value = JSON.parse(await readFile(file!, "utf8"));
      expect(value.graph.nodes.map((n: { id: string }) => n.id).sort()).toEqual(
        visible,
      );
      expect(value.graph.selection.checked.sort()).toEqual([...ids].sort());
    }
    await page
      .getByRole("checkbox", { name: "分类：结论", exact: true })
      .check();
    await page.getByLabel("查找中心材料").fill("合成");
    expect(
      await page.locator(".material-row .eyebrow").allTextContents(),
    ).toEqual(["结论"]);
    await page
      .getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true })
      .check();
    await assertExport(["CLM-SYNTHETIC"]);
    await page
      .getByRole("checkbox", { name: "分类：研究", exact: true })
      .check();
    const shownKinds = new Set(
      await page.locator(".material-row .eyebrow").allTextContents(),
    );
    expect(shownKinds).toEqual(new Set(["结论", "研究"]));
    await page
      .getByRole("checkbox", { name: "分类：结论", exact: true })
      .uncheck();
    await expect(
      page.getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true }),
    ).toHaveCount(0);
    await page
      .locator('[data-material-id="RES-SYNTHETIC"] input[type="checkbox"]')
      .check();
    await assertExport(["CLM-SYNTHETIC", "RES-SYNTHETIC"]);
    await page
      .getByRole("checkbox", { name: "分类：研究", exact: true })
      .uncheck();
    expect(
      new Set(await page.locator(".material-row .eyebrow").allTextContents())
        .size,
    ).toBeGreaterThan(2);
    await page
      .getByRole("checkbox", { name: "分类：结论", exact: true })
      .check();
    await expect(
      page.getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true }),
    ).toBeChecked();
    await page
      .getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true })
      .uncheck();
    await assertExport(["RES-SYNTHETIC"]);
    await page.getByRole("button", { name: "清空勾选", exact: true }).click();
    await expect(page.locator(".graph-main")).toContainText(
      `显示 ${catalog.nodes.length} 个节点`,
    );
  } finally {
    app.process.kill();
  }
});

test("一万节点十万关系下局部图和轻量状态响应", async ({ page, request }) => {
  const app = await server(true);
  try {
    await page.goto(app.url + "#/relations");
    await expect(page.getByRole("img", { name: "材料关系图" })).toBeVisible();
    await page
      .getByRole("checkbox", { name: "原生导航（未分层）", exact: true })
      .check();
    await page.getByLabel("查找中心材料").fill("合成材料 0");
    await page.locator('[data-material-id="N0"] button').click();
    const start = Date.now();
    await page.getByRole("button", { name: "以此为中心", exact: true }).click();
    await expect(page.locator(".graph-main")).toContainText("显示 21 个节点");
    await page.getByRole("button", { name: "适应画面", exact: true }).click();
    const elapsed = Date.now() - start;
    expect(elapsed).toBeLessThan(3000);
    await page
      .getByRole("button", { name: "全范围结构聚类", exact: true })
      .click();
    const t = Date.now();
    const response = await request.get(app.url + "api/v1/capabilities");
    expect(response.ok()).toBeTruthy();
    const apiMs = Date.now() - t;
    expect(apiMs).toBeLessThan(500);
    console.log(
      JSON.stringify({
        scaleNodes: 10000,
        scaleEdges: 100000,
        localInteractionMs: elapsed,
        statusMs: apiMs,
      }),
    );
    await page.screenshot({
      path: resolve(root, "tmp/workbench-scale.png"),
      fullPage: true,
    });
  } finally {
    app.process.kill();
  }
});

test("对象阅读清单、完整原文和版本导出真实接口", async ({ page }) => {
  const app = await server(false, true);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await page.goto(app.url + "#/memory?tab=reading&owner=RES-SYNTHETIC");
    await expect(page).toHaveURL(/#\/home$/);
    // 进入即加载现有笔记，不需要点击会话，更不应自动读取固定原文。
    await expect(
      page.getByText("合成阅读理解：保留前提", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "细节、参数、单位与边界",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByText("绝对温度偏置273.15", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "刷新当前笔记", exact: true })
      .click();
    await expect(
      page.getByText("合成阅读理解：保留前提", { exact: true }),
    ).toBeVisible();
    const event = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出当前笔记" }).click();
    expect((await event).suggestedFilename()).toMatch(
      /^合成阅读会话-RS-[a-f0-9]{12}-r4\.md$/,
    );
    await page
      .locator('[aria-label="当前阅读笔记全文"] a[href^="#/evidence?id=MEM-"]')
      .first()
      .click();
    await expect(
      page.getByRole("heading", { name: "证据面板完整文稿", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(root, ".local/unified-reading-panel.png"),
      fullPage: true,
    });
    expect(errors).toEqual([]);
  } finally {
    app.process.kill();
  }
});
