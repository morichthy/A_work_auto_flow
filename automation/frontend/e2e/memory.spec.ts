import {
  test,
  expect as baseExpect,
  type APIRequestContext,
} from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { resolve } from "node:path";
import { readFile, appendFile } from "node:fs/promises";

test("L0统一材料、无来源条目的Run、固定原件预览与清单导出", async ({
  page,
  request,
}) => {
  await open(page);
  const owner = "RUN-SYN-THERMAL";
  const before = (await post(request, "inspect", { owner_id: owner })).value;
  expect(
    Object.values(before.records).filter(
      (record: any) => record.kind === "source",
    ),
  ).toHaveLength(0);
  const listed = (await post(request, "raw-materials", { owner_id: owner }))
    .value;
  const native = listed.items.find((item: any) =>
    item.origins.some((origin: any) => origin.role === "current_run_metadata"),
  );
  expect(native).toBeTruthy();
  const study = (
    await post(request, "raw-materials", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  expect(
    study.items.some((item: any) => item.material_id === native.material_id),
  ).toBe(true);
  expect(new Set(study.items.map((item: any) => item.material_id)).size).toBe(
    study.total,
  );
  await page.getByLabel("记忆归属对象").selectOption(owner);
  await page.getByRole("button", { name: "生成对象记忆", exact: true }).click();
  await filterTypes(page, ["source"]);
  await expect(page.locator(".memory-list article")).toHaveCount(0);
  const card = page.getByTestId("raw-material").filter({
    has: page.getByRole("heading", { name: "run.json", exact: true }),
  });
  await card.getByRole("button", { name: "核验并查看原件" }).click();
  await expect(card.locator(".raw-preview pre")).toContainText(owner);
  const exported = page.waitForResponse((response) =>
    response.url().endsWith("/memory/export"),
  );
  await page.getByRole("button", { name: "导出 json", exact: true }).click();
  const download = JSON.parse((await (await exported).json()).content);
  expect(
    download.manifest.raw_materials.items.some(
      (item: any) => item.material_id === native.material_id,
    ),
  ).toBe(true);
  expect(download.records).toHaveLength(0);
  expect(
    (await post(request, "inspect", { owner_id: owner })).value.head,
  ).toEqual(before.head);
});
const root = resolve("../..");
const expect = baseExpect.configure({ timeout: 30000 });
let process: ChildProcess;
let base: string;
let mapping: Record<string, string>;
let fixtureRoot: string;
let sourcePaths: Record<string, string>;

test.describe.configure({ mode: "serial", timeout: 180000 });
test.use({ actionTimeout: 30000 });
test.setTimeout(180000);
test.beforeAll(async () => {
  process = spawn(
    resolve(root, "services/qdrant/runtime/python.exe"),
    [resolve(root, "automation/tests/serve_memory_test.py")],
    { cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
  );
  await new Promise<void>((ok, fail) => {
    let output = "";
    const timer = setTimeout(() => {
      process.kill();
      fail(Error("记忆测试服务启动超时: " + output));
    }, 150000);
    process.stdout!.on("data", (chunk) => {
      output += chunk;
      for (const line of output.split("\n")) {
        try {
          const value = JSON.parse(line);
          if (value.mapping) {
            mapping = value.mapping;
            fixtureRoot = value.root;
            sourcePaths = value.source_paths;
          }
          if (value.url) {
            base = value.url;
            clearTimeout(timer);
            ok();
            return;
          }
        } catch {
          /* Non-JSON diagnostics are retained for startup failure. */
        }
      }
    });
    process.stderr!.on("data", (chunk) => {
      output += chunk;
    });
    process.on("exit", (code) => {
      clearTimeout(timer);
      fail(Error(`记忆服务退出 ${code}: ${output}`));
    });
  });
});
test.afterAll(() => process?.kill());
test("系统记忆默认研究经过，按需生成对象记忆且保持子页结果", async ({
  page,
}) => {
  const inspectRequests: string[] = [];
  const documentRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/memory/inspect"))
      inspectRequests.push(request.url());
    if (request.url().endsWith("/memory/document"))
      documentRequests.push(request.url());
  });
  await page.goto(base + "#/memory");
  await expect(
    page.getByRole("heading", { name: "系统记忆", exact: true }),
  ).toBeVisible();
  const tabLabels = await page.locator(".memory-tabs button").evaluateAll(
    (buttons) => buttons.slice(0, 3).map((button) => button.textContent?.trim()),
  );
  expect(tabLabels).toEqual(["研究经过", "对象记忆", "关联导航"]);
  await page.getByLabel("记忆归属对象").selectOption("RES-SYN-THERMAL");
  // Selecting an owner or opening its records must remain read-only until the
  // user explicitly requests a generated object-memory view.
  expect(inspectRequests).toHaveLength(0);
  await page.getByRole("button", { name: "对象记忆", exact: true }).click();
  expect(inspectRequests).toHaveLength(0);
  const inspected = page.waitForRequest((request) =>
    request.url().endsWith("/memory/inspect"),
  );
  await page.getByRole("button", { name: "生成对象记忆", exact: true }).click();
  await inspected;
  expect(inspectRequests).toHaveLength(1);

  await page.getByRole("button", { name: "研究经过", exact: true }).click();
  const document = page.waitForRequest((request) =>
    request.url().endsWith("/memory/document"),
  );
  await page.getByRole("button", { name: "读取研究经过", exact: true }).click();
  await document;
  await expect(page.locator(".research-empty")).toContainText(
    "尚未编排研究报告",
  );
  await page.getByRole("button", { name: "对象记忆", exact: true }).click();
  await page.getByRole("button", { name: "关联导航", exact: true }).click();
  await page.getByRole("button", { name: "研究经过", exact: true }).click();
  // Returning to the retained research panel does not request the document again.
  expect(documentRequests).toHaveLength(1);
  await expect(page.locator(".research-empty")).toContainText(
    "尚未编排研究报告",
  );
});
async function post(
  request: APIRequestContext,
  action: string,
  value: unknown,
) {
  const response = await request.post(base + "api/v1/memory/" + action, {
    data: value,
    headers: { Origin: new URL(base).origin },
  });
  return { status: response.status(), value: await response.json() };
}
async function open(page: import("@playwright/test").Page) {
  await page.goto(base + "#/memory");
  await expect(
    page.getByRole("heading", { name: "系统记忆", exact: true }),
  ).toBeVisible();
  await page.getByLabel("记忆归属对象").selectOption("RES-SYN-THERMAL");
  await page.getByLabel("记忆执行者类型").selectOption("ai");
  await page
    .getByLabel("记忆执行者", { exact: true })
    .fill("SYNTHETIC browser acceptance");
  await page.getByRole("button", { name: "对象记忆", exact: true }).click();
  await page.getByRole("button", { name: "生成对象记忆", exact: true }).click();
  await filterTypes(page, ["experience"]);
  await expect(page.locator(".memory-list article").first()).toBeVisible();
}

// 通过可见勾选组操作任意组合，不借助内部状态改变筛选。
async function filterTypes(
  page: import("@playwright/test").Page,
  types: string[],
) {
  await page.getByRole("button", { name: "清空类型", exact: true }).click();
  const group = page.getByRole("group", { name: "按层级或类型筛选" });
  for (const type of types) {
    // 辅助工作流对象不再与 L0–L4/文稿并列为主筛选项；需要时通过
    // 明确的折叠入口读取，避免测试绕过用户实际可见交互。
    if (type === "question") {
      const auxiliary = page.locator("details").filter({
        hasText: "辅助工作流记录",
      });
      if (!(await auxiliary.evaluate((element) => element.open)))
        await auxiliary.locator("summary").click();
      await auxiliary
        .getByLabel("显示辅助工作流记录", { exact: true })
        .check();
      continue;
    }
    // 历史fixture仍保存map/event；界面只显示现行统一层级入口。
    const visible =
      type === "map" ? "overview" : type === "event" ? "narrative" : type;
    await group.locator(`input[value="${visible}"]`).check();
  }
}

// 编辑与逐结论复核属于记录管理动作，产品将其折叠以保持对象记忆列表
// 以阅读为主。测试必须先执行同样的可见交互，不能依赖折叠内容可查询。
async function openRecordManagement(
  page: import("@playwright/test").Page,
) {
  const details = page.locator(".memory-list article > details");
  const count = await details.count();
  for (let index = 0; index < count; index++) {
    const detail = details.nth(index);
    if (!(await detail.evaluate((element) => element.open)))
      await detail.locator("summary").click();
  }
}

test("四层记录、真实编辑冲突、索引待补偿与安全导出", async ({
  page,
  context,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  // 文本中的外链只能作为材料显示。即使实现回归触发加载，也由测试
  // 在本机拦截，避免向外部服务器发送请求，并保留可断言的加载次数。
  const injectedRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("memory-injection.invalid"))
      injectedRequests.push(req.url());
  });
  await page.route("https://memory-injection.invalid/**", (route) =>
    route.abort(),
  );
  await open(page);
  await filterTypes(page, ["source", "map", "experience"]);
  await expect(page.locator(".memory-list article")).toHaveCount(2);
  await expect(page.getByTestId("raw-material").first()).toBeVisible();
  await filterTypes(page, []);
  await expect(page.locator(".memory-list article")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "导出 json", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "全选类型", exact: true }).click();
  await expect(
    page
      .getByRole("group", { name: "按层级或类型筛选" })
      .locator("input:not(:checked)"),
  ).toHaveCount(0);
  for (const type of ["source", "map", "experience"]) {
    await filterTypes(page, [type]);
    if (type === "source") {
      await expect(page.locator(".memory-list article")).toHaveCount(0);
      await expect(page.getByTestId("raw-material").first()).toBeVisible();
    } else await expect(page.locator(".memory-list article")).toHaveCount(1);
  }
  await openRecordManagement(page);
  await page.getByRole("button", { name: "编辑记录", exact: true }).click();
  const second = await context.newPage();
  await open(second);
  await openRecordManagement(second);
  await second.getByRole("button", { name: "编辑记录", exact: true }).click();
  await page.getByLabel("记忆标题").fill("SYNTHETIC 新版本预热边界");
  await page
    .getByLabel("记忆正文")
    .fill(
      '<script>window.injected=1</script>\n<img src=x onerror="window.injected=2">\n<script src="https://memory-injection.invalid/payload.js"></script>\n[外部来源](https://memory-injection.invalid/source)\npowershell -Command "window.injected=3"\n中文🙂边界仍保留。',
    );
  await page
    .getByLabel("记忆保存原因")
    .fill("SYNTHETIC 浏览器冲突与注入显示检查");
  await page.getByRole("button", { name: "保存记忆", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "记录已保存，索引待更新",
    { timeout: 60000 },
  );
  await second.getByLabel("记忆标题").fill("SYNTHETIC 待比较的草稿");
  await second.getByLabel("记忆保存原因").fill("保留冲突草稿");
  await second.getByRole("button", { name: "保存记忆", exact: true }).click();
  await expect(second.getByRole("status")).toContainText("版本冲突", {
    timeout: 60000,
  });
  await expect(second.getByLabel("记忆标题")).toHaveValue(
    "SYNTHETIC 待比较的草稿",
  );
  await expect(second.getByRole("alert")).toContainText(
    "SYNTHETIC 新版本预热边界",
  );
  expect(
    await page.evaluate(
      () => (window as unknown as { injected?: number }).injected,
    ),
  ).toBeUndefined();
  expect(injectedRequests).toEqual([]);
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 json", exact: true }).click();
  const file = await (await downloading).path();
  const exported = JSON.parse(await readFile(file!, "utf8"));
  expect(exported.records).toHaveLength(1);
  expect(exported.records[0].revision).toBe(2);
  expect(exported.records[0].payload.prohibited.length).toBeGreaterThan(0);
  await page.screenshot({
    path: resolve(root, "tmp/memory-records.png"),
    fullPage: true,
  });
  await second.screenshot({
    path: resolve(root, "tmp/memory-conflict.png"),
    fullPage: true,
  });
  await second.close();
  expect(errors).toEqual([]);
  const beforeCompensation = (
    await post(context.request, "inspect", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  await page.getByRole("button", { name: "补偿索引", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("已执行索引补偿", {
    timeout: 60000,
  });
  const afterCompensation = (
    await post(context.request, "inspect", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  expect(afterCompensation.head).toEqual(beforeCompensation.head);
  expect(afterCompensation.index_details.fts).toBe("indexed");
  // Exercise the actual continuation/clipboard path. A success label alone
  // cannot prove that the fixed packet reached the clipboard unchanged.
  await page.getByRole("button", { name: "暂停与续接", exact: true }).click();
  const continuation = page.waitForResponse((r) =>
    r.url().endsWith("/memory/resume"),
  );
  await page.getByRole("button", { name: "生成续接内容", exact: true }).click();
  const resumed = await (await continuation).json();
  expect(resumed.context_text.length).toBeGreaterThan(0);
  await expect(page.getByTestId("memory-packet")).toHaveText(
    resumed.context_text,
  );
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: new URL(base).origin,
  });
  await page.getByRole("button", { name: "复制续接内容", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("已复制续接内容");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    resumed.context_text,
  );
  const afterResume = (
    await post(context.request, "inspect", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  expect(afterResume.head).toEqual(afterCompensation.head);
});

test("连续研究报告、固定图示、目录路由和窄屏阅读", async ({
  page,
  request,
}) => {
  await open(page);
  await page.getByRole("button", { name: "研究经过", exact: true }).click();
  await page.getByRole("button", { name: "读取研究经过", exact: true }).click();
  await expect(page.getByText(/尚未编排研究报告/)).toBeVisible();
  await expect(page.locator(".research-paper")).toHaveCount(0);

  // Use only the public API to revise the isolated synthetic fixture. The
  // report pins the returned detail revision; no production HEAD is touched.
  let state = (await post(request, "inspect", { owner_id: "RES-SYN-THERMAL" }))
    .value;
  const original = Object.values(state.records).find(
    (value: any) => value.kind === "detail",
  ) as any;
  const audit = new Set([
    "record_id",
    "revision",
    "previous_revision",
    "record_hash",
    "content_hash",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
  ]);
  const draft = Object.fromEntries(
    Object.entries(original).filter(([key]) => !audit.has(key)),
  ) as any;
  draft.body_markdown = `# ${original.title}\n\n## 可复核过程\n\n合成参数的项数为 3。\n\n| 参数 | 值 | 说明 |\n|---|---|---|\n| n | 3 | 合成输入 |\n\n$$\ns=\\sum_{i=1}^{n}x_i\n$$\n\n![固定像素图](figure:0)\n\n这里只验证界面展示，不判断现实算法有效性。`;
  draft.change_reason = "合成连续报告浏览器验收";
  const detailSaved = await post(request, "commit", {
    schema_version: 2,
    request_id: crypto.randomUUID(),
    owner_id: original.owner_id,
    expected_head: state.head.commit_id,
    actor: { kind: "workflow", id: "synthetic-browser-report" },
    operations: [
      {
        op: "put_record",
        record_id: original.record_id,
        expected_revision: original.revision,
        draft,
      },
    ],
  });
  expect(detailSaved.value.save_status, JSON.stringify(detailSaved.value)).toBe(
    "committed",
  );
  state = (await post(request, "inspect", { owner_id: original.owner_id }))
    .value;
  const detail = state.records[original.record_id];
  const ref = {
    target_kind: "record",
    target_id: detail.record_id,
    revision: detail.revision,
    sha256: detail.record_hash,
    locator: "body_markdown",
    relation: "references",
  };
  const secondSaved = await post(request, "commit", {
    schema_version: 2,
    request_id: crypto.randomUUID(),
    owner_id: original.owner_id,
    expected_head: state.head.commit_id,
    actor: { kind: "workflow", id: "synthetic-browser-report" },
    operations: [
      {
        op: "put_record",
        client_key: "second-detail",
        draft: {
          ...draft,
          title: "SYNTHETIC 第二实验",
          body_markdown:
            "## 后续观察\n\n上一轮留下边界问题，因此增加这轮合成观察。旧版图示未内嵌，应只补显一次。",
        },
      },
    ],
  });
  expect(secondSaved.value.save_status, JSON.stringify(secondSaved.value)).toBe(
    "committed",
  );
  state = (await post(request, "inspect", { owner_id: original.owner_id }))
    .value;
  const secondDetail =
    state.records[secondSaved.value.record_results[0].record_id];
  const secondRef = {
    ...ref,
    target_id: secondDetail.record_id,
    revision: secondDetail.revision,
    sha256: secondDetail.record_hash,
  };
  const map = {
    schema_version: 2,
    owner_id: original.owner_id,
    kind: "map",
    title: "合成报告编排",
    body_markdown: "以固定修订组织合成阅读场景。",
    keywords: [],
    record_reason: "合成连续报告浏览器验收",
    change_reason: "首次编排",
    sources: [],
    provenance_gap: "仅为软件测试，不是科学研究结论",
    sensitivity: "internal",
    discovery: "owner_only",
    payload: {
      topic: "合成阅读",
      goal_refs: [],
      route_refs: [],
      result_refs: [],
      question_refs: [],
      conflict_refs: [],
      next_steps: [],
      coverage: {
        owner_ids: [original.owner_id],
        source_versions: [],
        missing: [],
      },
      report: {
        version: 1,
        title: "SYNTHETIC 连续研究报告",
        sections: [
          {
            section_id: "methods",
            title: "共同方法",
            role: "methods",
            blocks: [
              {
                type: "prose",
                markdown: "## 方法定义\n\n先规定相同的计算符号。",
                evidence_refs: [],
              },
            ],
          },
          {
            section_id: "experiment",
            title: "设计、计算与观察",
            role: "experiment",
            blocks: [
              {
                type: "prose",
                markdown:
                  "沿用[共同方法](#report-methods)，因此开展下面的计算。",
                evidence_refs: [ref],
              },
              { type: "detail", ref },
            ],
          },
          {
            section_id: "second-experiment",
            title: "后续实验",
            role: "experiment",
            blocks: [{ type: "detail", ref: secondRef }],
          },
          {
            section_id: "discussion",
            title: "讨论与局限",
            role: "discussion",
            blocks: [
              {
                type: "prose",
                markdown: "## 适用边界\n\n综合讨论在实验后，合成结果不能外推。",
                evidence_refs: [ref],
              },
            ],
          },
          {
            section_id: "conclusion",
            title: "结论与后续工作",
            role: "conclusion",
            blocks: [
              {
                type: "prose",
                markdown: "仍需真实材料验证。",
                evidence_refs: [ref],
              },
            ],
          },
        ],
      },
    },
  };
  const saved = await post(request, "commit", {
    schema_version: 2,
    request_id: crypto.randomUUID(),
    owner_id: original.owner_id,
    expected_head: state.head.commit_id,
    actor: { kind: "workflow", id: "synthetic-browser-report" },
    operations: [{ op: "put_record", client_key: "report", draft: map }],
  });
  expect(saved.value.save_status, JSON.stringify(saved.value)).toBe(
    "committed",
  );
  await page.getByRole("button", { name: "读取研究经过", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "SYNTHETIC 连续研究报告", exact: true }),
  ).toBeVisible();
  const retainedDocumentRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/memory/document"))
      retainedDocumentRequests.push(request.url());
  });
  await page.getByRole("button", { name: "对象记忆", exact: true }).click();
  await page.getByRole("button", { name: "关联导航", exact: true }).click();
  await page.getByRole("button", { name: "研究经过", exact: true }).click();
  // The already generated report survives child-tab navigation without a
  // second load. This is a visible state guarantee, not just cached markup.
  expect(retainedDocumentRequests).toHaveLength(0);
  await expect(
    page.getByRole("heading", { name: "SYNTHETIC 连续研究报告", exact: true }),
  ).toBeVisible();
  const paper = page.locator(".research-paper");
  await expect(paper.locator(":scope > section > h2")).toHaveText([
    "1. 共同方法",
    "2. 设计、计算与观察",
    "3. 后续实验",
    "4. 讨论与局限",
    "5. 结论与后续工作",
  ]);
  await expect(
    paper.getByRole("heading", { name: "可复核过程", level: 3 }),
  ).toBeVisible();
  await expect(
    paper.getByRole("heading", { name: "适用边界", level: 3 }),
  ).toBeVisible();
  await expect(
    paper.getByRole("heading", { name: original.title, exact: true }),
  ).toHaveCount(0);
  await expect(paper.locator(".katex-display")).toHaveCount(1);
  await expect(paper.locator("table")).toHaveCount(1);
  await expect(
    paper.getByText("合成参数的项数为 3。", { exact: true }),
  ).toHaveCount(1);
  await expect(
    paper.locator(".research-meta,.research-level,.research-fields"),
  ).toHaveCount(0);
  const figure = paper
    .getByRole("img", {
      name: "SYNTHETIC 固定像素图，仅验证图像读取",
      exact: true,
    })
    .first();
  await expect(figure).toHaveJSProperty("naturalWidth", 1);
  await expect(paper.locator("figure")).toHaveCount(2);
  await expect(paper.locator("figcaption").nth(0)).toContainText("图 1");
  await expect(paper.locator("figcaption").nth(1)).toContainText("图 2");
  await expect(paper.locator("figcaption").first()).toContainText(
    "仅验证图像读取",
  );
  const contents = page.getByRole("navigation", { name: "研究文稿目录" });
  const documentUrl = page.url();
  await contents.getByRole("link", { name: "讨论与局限", exact: true }).click();
  await expect(page).toHaveURL(documentUrl);
  await expect(page.locator("#report-discussion > h2")).toBeInViewport();
  await contents
    .getByRole("link", { name: "设计、计算与观察", exact: true })
    .click();
  await expect(page.locator("#report-experiment > h2")).toBeInViewport();
  await paper.getByRole("link", { name: "共同方法", exact: true }).click();
  await expect(page).toHaveURL(documentUrl);
  await expect(page.locator("#report-methods > h2")).toBeInViewport();
  await page.screenshot({
    path: resolve(root, "tmp/memory-report-desktop.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await contents
    .getByRole("link", { name: "设计、计算与观察", exact: true })
    .click();
  await expect(page).toHaveURL(documentUrl);
  await expect(page.locator("#report-experiment > h2")).toBeInViewport();
  // Long tables/formulas remain scrollable inside the reading column; the
  // report itself must fit the viewport rather than force horizontal panning.
  const bounds = await paper.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(391);
  expect(
    await paper
      .locator("table")
      .evaluate((element) => getComputedStyle(element).overflowX),
  ).toBe("auto");
  expect(
    await paper
      .locator(".katex-display")
      .evaluate((element) => getComputedStyle(element).overflowX),
  ).toBe("auto");
  await page.screenshot({
    path: resolve(root, "tmp/memory-report-narrow.png"),
    fullPage: true,
  });
  await page.getByText(/^记录与来源（/).click();
  const archiveRecord = page
    .locator(".research-record")
    .filter({ hasText: original.title });
  await archiveRecord.locator("summary").first().click();
  await expect(archiveRecord.locator(".research-meta")).toContainText(
    "首次保存于",
  );
  await expect(archiveRecord.locator(".research-meta")).toContainText(
    "本次修订于",
  );
  await expect(archiveRecord.locator(".research-meta")).not.toContainText(
    "发生时间：发生时间未知",
  );
});
test("研究、Run、知识与报告真实记录及辅助对象可区分", async ({
  page,
  request,
}) => {
  // Seed only through the public API and then browse those exact receipts.
  const listed = (await post(request, "list-owners", {})).value.owners;
  for (const type of ["run", "knowledge", "report"]) {
    let owner = listed.find((value: any) => value.owner_type === type);
    if (owner.temporary)
      owner = (
        await post(request, "adopt-owner", {
          native_ref: owner.native_ref,
          expected_hash: owner.fingerprint,
          actor: { kind: "ai", id: "SYNTHETIC browser acceptance" },
        })
      ).value;
    const inspected = (
      await post(request, "inspect", { owner_id: owner.owner_id })
    ).value;
    const draft = {
      owner_id: owner.owner_id,
      kind: "map",
      title: "SYNTHETIC 同名研究地图",
      body_markdown: "SYNTHETIC 各对象独立保存的地图",
      keywords: [],
      record_reason: "SYNTHETIC 八类归属界面验证",
      change_reason: "SYNTHETIC 首次保存地图",
      sources: [],
      provenance_gap: "合成界面任务设定，无业务证据",
      sensitivity: "internal",
      discovery: "owner_only",
      payload: {
        topic: "合成地图",
        goal_refs: [],
        route_refs: [],
        result_refs: [],
        question_refs: [],
        conflict_refs: [],
        next_steps: ["补充依据"],
        coverage: {
          owner_ids: [owner.owner_id],
          source_versions: [],
          missing: [],
        },
      },
    };
    const saved = await post(request, "commit", {
      schema_version: 1,
      request_id: crypto.randomUUID(),
      owner_id: owner.owner_id,
      expected_head: inspected.head?.commit_id || null,
      actor: { kind: "ai", id: "SYNTHETIC browser acceptance" },
      operations: [{ op: "put_record", client_key: "map", draft }],
    });
    expect(saved.value.save_status, JSON.stringify(saved.value)).toBe(
      "committed",
    );
    await page.goto(base + "#/memory");
    // Adoption happened outside this already-mounted view; reload to obtain
    // its new stable owner ID instead of reusing the earlier temporary option.
    await page.reload();
    await page.getByLabel("记忆归属对象").selectOption(owner.owner_id);
    await page.getByRole("button", { name: "对象记忆", exact: true }).click();
    await page.getByRole("button", { name: "生成对象记忆", exact: true }).click();
    await filterTypes(page, ["map"]);
    const card = page
      .locator(".memory-list article")
      .filter({
        has: page.getByRole("link", {
          name: "SYNTHETIC 同名研究地图",
          exact: true,
        }),
      });
    await expect(card).toContainText("SYNTHETIC 同名研究地图");
    await expect(card.locator(".badge")).toHaveText("L4 整体概览");
    await expect(
      card.getByRole("link", { name: "查看完整内容与依据", exact: true }),
    ).toHaveAttribute("href", new RegExp(saved.value.record_results[0].record_id));
  }
  await open(page);
  // 问题是辅助工作流记录，已不提供与 L0–L4 并列的新建按钮；通过
  // 公共接口预置后，验证用户可在折叠辅助入口中读取它。
  const thermal = (
    await post(request, "inspect", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  const questionSaved = await post(request, "commit", {
    schema_version: 2,
    request_id: crypto.randomUUID(),
    owner_id: "RES-SYN-THERMAL",
    expected_head: thermal.head.commit_id,
    actor: { kind: "ai", id: "SYNTHETIC browser acceptance" },
    operations: [
      {
        op: "put_record",
        client_key: "auxiliary-question",
        draft: {
          schema_version: 2,
          owner_id: "RES-SYN-THERMAL",
          kind: "question",
          title: "SYNTHETIC 待调查问题",
          body_markdown:
            "本问题用于验证辅助工作流记录的可见性，不构成研究结论。",
          keywords: [],
          record_reason: "SYNTHETIC 未解决问题保留",
          change_reason: "首次保存合成辅助问题",
          sources: [],
          provenance_gap: "合成界面任务设定，无业务证据",
          sensitivity: "internal",
          discovery: "owner_only",
          payload: {
            question: "新的样本是否满足原有条件？",
            status: "open",
            decision_affected: "是否复用旧参数",
            missing_evidence: ["新样本的实际验证"],
            resolution_refs: [],
            replacement_ref: null,
            reopen_reason: null,
          },
        },
      },
    ],
  });
  expect(questionSaved.value.save_status, JSON.stringify(questionSaved.value)).toBe(
    "committed",
  );
  await page.getByRole("button", { name: "生成对象记忆", exact: true }).click();
  await filterTypes(page, ["question"]);
  await expect(page.locator(".memory-list article")).toContainText(
    "SYNTHETIC 待调查问题",
  );
  await expect(page.locator(".memory-list article .badge")).toHaveText("问题");
});

test("缺范围复核被拒绝并保留逐结论状态", async ({ page, request }) => {
  await open(page);
  const before = (
    await post(request, "inspect", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  await openRecordManagement(page);
  await page
    .getByRole("button", { name: "复核此结论", exact: true })
    .first()
    .click();
  await page.getByLabel("记忆复核范围").fill("");
  await page.getByLabel("记忆复核原因").fill("SYNTHETIC 缺范围负例");
  await page.getByRole("button", { name: "提交复核", exact: true }).click();
  await expect(page.getByRole("status")).not.toContainText("已保存");
  await expect(page.getByRole("status")).not.toBeEmpty();
  const after = (
    await post(request, "inspect", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  expect(after.head).toEqual(before.head);
  expect(after.claim_states).toEqual(before.claim_states);
  await page.getByLabel("复核状态", { exact: true }).selectOption("disputed");
  await page
    .getByLabel("记忆复核原因")
    .fill("SYNTHETIC 只争议第一条结论，第二条保持未复核");
  await page.getByRole("button", { name: "提交复核", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("记录已保存", {
    timeout: 60000,
  });
  await expect(page.locator(".memory-claim").nth(0)).toContainText("disputed");
  await expect(page.locator(".memory-claim").nth(1)).toContainText(
    "not-reviewed",
  );
  await page.getByRole("button", { name: "关闭复核", exact: true }).click();
  const runBefore = (
    await post(request, "inspect", { owner_id: "RUN-SYN-THERMAL" })
  ).value.owner.native_data;
  await openRecordManagement(page);
  await page
    .locator(".memory-claim")
    .nth(1)
    .getByRole("button", { name: "复核此结论", exact: true })
    .click();
  await page.getByLabel("复核状态", { exact: true }).selectOption("accepted");
  await page.getByLabel("记忆复核范围").fill("SYNTHETIC browser only");
  await page
    .getByLabel("记忆复核原因")
    .fill("SYNTHETIC 仅验证本地界面的逐结论复核，不表示现实模型成立");
  await page.getByRole("button", { name: "提交复核", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("记录已保存", {
    timeout: 60000,
  });
  await expect(page.locator(".memory-claim").nth(0)).toContainText("disputed");
  await expect(page.locator(".memory-claim").nth(1)).toContainText("accepted");
  await expect(page.locator(".memory-claim").nth(2)).toContainText(
    "not-reviewed",
  );
  const runAfter = (
    await post(request, "inspect", { owner_id: "RUN-SYN-THERMAL" })
  ).value.owner.native_data;
  expect(runAfter).toEqual(runBefore);
  expect(mapping["MEM-EXP-THERMAL"]).toBeTruthy();
});

test("跨研究材料回填L3与L4，并采纳有边界的导航关联", async ({
  page,
  request,
}) => {
  await open(page);
  for (const level of ["L3 经验", "L4 整体概览"]) {
    await page.getByRole("button", { name: "跨项目总结", exact: true }).click();
    await page
      .getByRole("textbox", { name: "总结问题", exact: true })
      .fill("SYNTHETIC 共同前置条件与不同操作");
    await page.getByRole("checkbox", { name: /RES-SYN-THERMAL/ }).check();
    await page.getByRole("checkbox", { name: /RES-SYN-PRESSURE/ }).check();
    await page
      .getByRole("button", { name: "准备总结材料包", exact: true })
      .click();
    await expect(page.getByTestId("memory-packet")).toContainText(
      "RES-SYN-PRESSURE",
    );
    await page
      .getByRole("button", { name: "回填 " + level, exact: true })
      .click();
    await page
      .getByLabel("记忆正文")
      .fill(
        "两个研究都要求先满足前置条件。预热时间和预载次数不能互换；原结论仍需独立复核。",
      );
    if (level.startsWith("L3")) {
      await page
        .getByLabel("共同问题结构", { exact: true })
        .fill("前置状态尚未稳定时不能直接沿用结果");
      await page
        .getByLabel("建议", { exact: true })
        .fill("先核对各研究的稳定条件");
      await page
        .getByLabel("适用条件", { exact: true })
        .fill("仅适用于这两个合成材料的比较");
      await page
        .getByLabel("禁止迁移条件", { exact: true })
        .fill("不交换预热时间与预载次数");
    } else {
      // 新概览使用真实问题和当前阶段；旧map的空topic草案不能冒充完整v4输入。
      await page
        .getByLabel("问题内容", { exact: true })
        .fill("共同前置条件与不可迁移参数是什么");
      await page
        .getByLabel("当前阶段", { exact: true })
        .fill("已比较两份合成材料，尚未验证迁移");
    }
    await page
      .getByLabel("记忆保存原因")
      .fill("SYNTHETIC 比较原材料后的新解释");
    const saved = page.waitForResponse((r) =>
      r.url().endsWith("/memory/summaries-save"),
    );
    await page.getByRole("button", { name: "保存记忆", exact: true }).click();
    const receipt = await (await saved).json();
    expect(receipt.save_status, JSON.stringify(receipt)).toBe("committed");
    await expect(page.getByRole("status")).toContainText("记录已保存", {
      timeout: 60000,
    });
  }
  const before = (
    await post(request, "inspect", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  await page.getByRole("button", { name: "关联导航", exact: true }).click();
  await page.getByLabel("作为起点的记录 ID").fill(mapping["MEM-MAP-THERMAL"]);
  await page.getByRole("button", { name: "查找相关候选", exact: true }).click();
  await page
    .getByRole("button", { name: "解释并处理关联", exact: true })
    .first()
    .click();
  await page
    .getByLabel("共同问题结构", { exact: true })
    .fill("合成研究均需明确适用边界");
  await page
    .getByLabel("不可迁移内容", { exact: true })
    .fill("相似性不能作为科学支持；不迁移参数");
  await page.getByRole("button", { name: "采纳导航关联", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("记录已保存", {
    timeout: 60000,
  });
  const after = (
    await post(request, "inspect", { owner_id: "RES-SYN-THERMAL" })
  ).value;
  expect(after.claim_states).toEqual(before.claim_states);
  expect(
    Object.values(after.records).some(
      (r: any) => r.kind === "association" && r.payload.status === "accepted",
    ),
  ).toBe(true);
});

test("逐层读取固定原件、返回已读版本，并识别原件变化", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "跨研究检索", exact: true }).click();
  await page.getByLabel("记忆检索问题").fill("预热");
  await page.getByRole("button", { name: "检索记忆", exact: true }).click();
  const result = page
    .locator(".proposal")
    .filter({ hasText: mapping["MEM-EXP-THERMAL"] });
  await result
    .getByRole("button", { name: "展开固定来源", exact: true })
    .click();
  await page.getByRole("button", { name: /^继续展开 RUN-SYN-THERMAL/ }).click();
  await expect(page.getByTestId("memory-packet")).toContainText(
    "RUN-SYN-THERMAL",
  );
  await page
    .getByRole("button", { name: /^继续展开 CLM-/ })
    .first()
    .click();
  const fileButton = page
    .getByRole("button", { name: /^继续展开 SRC-/ })
    .first();
  const label = await fileButton.textContent();
  const sourceId = label!
    .replace(/^继续展开 /, "")
    .split(" · ")[0]
    .trim();
  await fileButton.click();
  await expect(page.getByTestId("memory-packet")).toContainText("固定来源");
  const original = await page.getByTestId("memory-packet").textContent();
  await page
    .getByRole("button", { name: "返回上一层（已读取版本）", exact: true })
    .click();
  await expect(page.getByTestId("memory-packet")).toContainText("CLM-");
  // The path was returned by this synthetic fixture process; only its sandbox
  // copy is modified. No application endpoint gains arbitrary file writes.
  const target = resolve(fixtureRoot, sourcePaths[sourceId]);
  expect(target.startsWith(fixtureRoot + "\\")).toBe(true);
  await appendFile(
    target,
    "\nSYNTHETIC U05 source revision after first read.\n",
    "utf8",
  );
  await page
    .getByRole("button", { name: /^继续展开 SRC-/ })
    .first()
    .click();
  await expect(page.getByTestId("memory-packet")).not.toHaveText(original!);
  await page.getByText("范围、版本、预算与遗漏清单", { exact: true }).click();
  await expect(
    page.getByText("范围、版本、预算与遗漏清单").locator(".."),
  ).toContainText("STALE_BASIS");
  await page.screenshot({
    path: resolve(root, "tmp/memory-source-changed.png"),
    fullPage: true,
  });
});

test("独立双文稿、必要定义、章节上下文与固定修订影响", async ({
  page,
  request,
  context,
}) => {
  const owner = "RES-SYN-THERMAL";
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  async function save(
    kind: string,
    title: string,
    payload: unknown,
    sources: unknown[] = [],
  ) {
    const state = (await post(request, "inspect", { owner_id: owner })).value;
    const result = await post(request, "commit", {
      schema_version: 1,
      request_id: crypto.randomUUID(),
      owner_id: owner,
      expected_head: state.head.commit_id,
      actor: { kind: "workflow", id: "synthetic-documents-browser" },
      operations: [
        {
          op: "put_record",
          client_key: kind,
          draft: {
            schema_version: 3,
            owner_id: owner,
            kind,
            title,
            keywords: ["合成文稿"],
            body_markdown: "",
            payload,
            sources,
            provenance_gap: sources.length
              ? null
              : "隔离合成方法，不代表科学验证",
            record_reason: "浏览器实际操作验收",
            sensitivity: "internal",
            discovery: "owner_only",
          },
        },
      ],
    });
    expect(result.value.save_status, JSON.stringify(result.value)).toBe(
      "committed",
    );
    const saved = (await post(request, "inspect", { owner_id: owner })).value
      .records[result.value.record_results[0].record_id];
    return {
      record: saved,
      ref: {
        target_kind: "record",
        target_id: saved.record_id,
        revision: saved.revision,
        sha256: saved.record_hash,
        locator: "",
        relation: "references",
      },
    };
  }
  const unit = await save("detail", "SYNTHETIC 稳定技术单元", {
    unit_type: "method",
    retrieval_description: {
      question: "如何保证长度比较一致",
      method: "先定义单位",
      key_findings: ["单位必须一致"],
      applicable: ["合成长度"],
      not_applicable: ["温度"],
      limitations: ["未执行实验"],
    },
    run_ref: null,
    evidence_refs: [],
    figures: [],
    missing_refs: [],
    blocks: [
      {
        block_id: "definitions",
        role: "definitions",
        markdown: "必要定义：$x$ 为长度，单位米。",
        requires_block_ids: [],
      },
      {
        block_id: "method",
        role: "methods",
        markdown: "本章所选方法：比较前统一长度单位。",
        requires_block_ids: ["definitions"],
      },
      {
        block_id: "appendix",
        role: "appendix",
        markdown: "未选中的技术附录，不应出现在本章。",
        requires_block_ids: [],
      },
    ],
  });
  const chapter = await save(
    "document_section",
    "SYNTHETIC 方法章",
    {
      section_key: "method",
      title: "稳定方法章",
      role: "methods",
      blocks: [{ type: "unit", ref: unit.ref, block_ids: ["method"] }],
      watch_refs: [],
      missing_refs: [],
    },
    [unit.ref],
  );
  const brief = await save(
    "document_section",
    "SYNTHETIC 简版结果章",
    {
      section_key: "brief",
      title: "简版结论",
      role: "conclusion",
      blocks: [
        {
          type: "prose",
          markdown: "简版结论：固定单位后再比较；仅用于合成方法。",
          evidence_refs: [unit.ref],
        },
      ],
      watch_refs: [],
      missing_refs: [],
    },
    [unit.ref],
  );
  for (const [type, section, title] of [
    ["research_process", chapter, "SYNTHETIC 完整独立过程"],
    ["research_report", brief, "SYNTHETIC 精简独立报告"],
  ] as const)
    await save(
      "document",
      title,
      {
        document_type: type,
        purpose: "说明固定方法",
        audience: "验收读者",
        scope: "合成长度",
        common_refs: [],
        section_refs: [section.ref],
        watch_refs: [],
        missing_refs: [],
      },
      [section.ref],
    );
  await open(page);
  await page.getByRole("button", { name: "研究经过", exact: true }).click();
  await page.getByRole("button", { name: "读取研究经过" }).click();
  await expect(
    page.getByRole("heading", { name: "SYNTHETIC 完整独立过程" }),
  ).toBeVisible();
  await expect(page.locator(".research-paper")).toContainText("必要定义：");
  await expect(page.locator(".research-paper")).not.toContainText(
    "未选中的技术附录",
  );
  const before = (await post(request, "inspect", { owner_id: owner })).value
    .head;
  const packetPromise = page.waitForResponse((r) =>
    r.url().endsWith("/memory/section-context"),
  );
  await page.getByRole("button", { name: "读取本章写作上下文" }).click();
  const packet = await (await packetPromise).json();
  await expect(page.locator(".research-sources > pre")).toHaveText(
    packet.context_text,
  );
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: new URL(base).origin,
  });
  await page.getByRole("button", { name: "复制章节上下文" }).click();
  await expect
    // Windows converts LF to CRLF through the native clipboard. Compare the
    // actual text with only newline normalization; preserve every other byte.
    .poll(() =>
      page.evaluate(async () =>
        (await navigator.clipboard.readText()).replace(/\r\n/g, "\n"),
      ),
    )
    .toBe(packet.context_text.replace(/\r\n/g, "\n"));
  await page.getByRole("button", { name: "检查文稿更新影响" }).click();
  await expect(page.getByText("固定依据未发现更新。")).toBeVisible();
  expect(
    (await post(request, "inspect", { owner_id: owner })).value.head,
  ).toEqual(before);
  await page.getByLabel("文稿类型").selectOption("research_report");
  await page.getByRole("button", { name: "读取研究经过" }).click();
  await expect(
    page.getByRole("heading", { name: "SYNTHETIC 精简独立报告" }),
  ).toBeVisible();
  await expect(page.locator(".research-paper")).toContainText("简版结论：");
  await expect(page.locator(".research-paper")).not.toContainText(
    "本章所选方法：",
  );
  expect(errors).toEqual([]);
});
