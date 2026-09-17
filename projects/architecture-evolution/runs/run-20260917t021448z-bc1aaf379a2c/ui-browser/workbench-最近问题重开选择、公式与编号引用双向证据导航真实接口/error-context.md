# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workbench.spec.ts >> 最近问题重开选择、公式与编号引用双向证据导航真实接口
- Location: e2e\workbench.spec.ts:65:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByLabel('选中证据详情').getByRole('heading', { name: '面板固定方法', exact: true })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByLabel('选中证据详情').getByRole('heading', { name: '面板固定方法', exact: true }) with timeout 5000ms
  - waiting for getByLabel('选中证据详情').getByRole('heading', { name: '面板固定方法', exact: true })

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
- paragraph: 证据 / 来源与影响
- heading "查看依据，检查影响" [level=1]
- button "刷新证据"
- paragraph: 按标题、结论或整体概览、ID搜索；只读取选中记录的详情。此处展示保存的元数据，未重新核验全部外部原件。
- complementary "证据搜索列表":
  - text: 搜索证据
  - textbox "搜索证据":
    - /placeholder: 标题、结论、整体概览或ID
  - button "搜索"
  - paragraph: 找到10条记录
  - link "document 证据面板完整文稿":
    - /url: "#/evidence?id=MEM-c3e0b321-284d-5bbc-88b8-3f1abb3ee6d7"
    - text: document
    - strong: 证据面板完整文稿
  - link "document_section 证据面板固定章节 本章固定说明。":
    - /url: "#/evidence?id=MEM-e0abb7f9-82b6-5c64-bbdd-4fa203d49e2d"
    - text: document_section
    - strong: 证据面板固定章节
    - text: 本章固定说明。
  - link "详细研究 证据面板合成技术单元 必要定义 ONLY_DEFINITION；$T$ 的单位为 K。 完整过程 ONLY_FULL_RESULT：$T=t+273.15$。 ![合成图](figure:0) 未选择的 OPTIONAL_BLOCK。":
    - /url: "#/evidence?id=MEM-a9d2bbdb-a0a7-555c-a38a-b205efe7d863"
    - text: 详细研究
    - strong: 证据面板合成技术单元
    - text: 必要定义 ONLY_DEFINITION；$T$ 的单位为 K。 完整过程 ONLY_FULL_RESULT：$T=t+273.15$。 ![合成图](figure:0) 未选择的 OPTIONAL_BLOCK。
  - link "overview 面板固定方法 panelreading 前提：绝对温度，偏置为273.15；这是合成展示资料，未验证现实方法。":
    - /url: "#/evidence?id=MEM-58e57760-afe0-5911-8697-c8d9b8201f87"
    - text: overview
    - strong: 面板固定方法
    - text: panelreading 前提：绝对温度，偏置为273.15；这是合成展示资料，未验证现实方法。
  - link "工具 合成检查工具":
    - /url: "#/evidence?id=TOOL-SYNTHETIC"
    - text: 工具
    - strong: 合成检查工具
  - link "实验 合成温漂测试":
    - /url: "#/evidence?id=RUN-SYNTHETIC"
    - text: 实验
    - strong: 合成温漂测试
  - link "研究 合成温漂研究":
    - /url: "#/evidence?id=RES-SYNTHETIC"
    - text: 研究
    - strong: 合成温漂研究
  - link "项目 合成交付聚合":
    - /url: "#/evidence?id=PRJ-SYNTHETIC"
    - text: 项目
    - strong: 合成交付聚合
  - link "core-algorithm 合成温漂（虚构）":
    - /url: "#/evidence?id=MOD-SYNTHETIC"
    - text: core-algorithm
    - strong: 合成温漂（虚构）
  - link "结论 合成计算偏移为 1.4 ms 合成计算偏移为 1.4 ms":
    - /url: "#/evidence?id=CLM-SYNTHETIC"
    - text: 结论
    - strong: 合成计算偏移为 1.4 ms
    - text: 合成计算偏移为 1.4 ms
  - status: 部分旧式依赖没有已登记证据身份；仅显示声明，不读取未登记原件。
- region "选中证据详情":
  - heading "证据面板完整文稿" [level=2]
  - text: 完整研究文稿 panelreading
  - status: 已检查当前访问边界；未重新复核科学结论。
  - heading "完整文稿" [level=3]
  - heading "证据面板固定章节" [level=2]
  - paragraph: 本章固定说明。
  - heading "证据面板合成技术单元" [level=3]
  - paragraph:
    - text: 必要定义 ONLY_DEFINITION；
    - math: T
    - text: 的单位为 K。
  - paragraph:
    - text: 完整过程 ONLY_FULL_RESULT：
    - math: T = t + 273.15
    - text: 。
  - figure "图 1 合成受控图片":
    - img "合成受控图片"
    - text: 图 1 合成受控图片
  - heading "retrieval_description" [level=2]
  - paragraph:
    - strong: applicable
  - paragraph: 摄氏温标的合成输入
  - paragraph:
    - strong: key_findings
  - paragraph: 只证明合成流程可读
  - paragraph:
    - strong: 限制
  - paragraph: 未验证传感器误差
  - paragraph:
    - strong: 方法
  - paragraph: 按温度基准和单位换算
  - paragraph:
    - strong: not_applicable
  - paragraph: 不得直接用于华氏温标或现实测量
  - paragraph:
    - strong: 问题
  - paragraph: 合成温标换算的定义
  - heading "unit_type" [level=2]
  - paragraph: method
  - heading "读者" [level=2]
  - paragraph: 研究人员
  - heading "目的" [level=2]
  - paragraph: 验证合成研究文档
  - heading "范围" [level=2]
  - paragraph: 仅合成软件验收
  - heading "参考文献" [level=3]
  - paragraph:
    - text: "[1]"
    - link "合成温漂测试":
      - /url: "#/evidence?id=RUN-SYNTHETIC&sha256=0d05ee95c2f8e0e8edb43aefa3a70881d2249c3ebdcdae65a61f5fcde2c2b0b5&locator="
  - paragraph:
    - text: "[2]"
    - link "固定来源":
      - /url: "#/evidence?id=MEM-a9d2bbdb-a0a7-555c-a38a-b205efe7d863&revision=1&sha256=7cf5f8364a7097245880dc841ae7355effeec3755668be444f62b2998a81e793&locator="
  - paragraph:
    - text: "[3]"
    - link "synthetic-panel.png":
      - /url: "#/evidence?id=SRC-PANEL-FIGURE&sha256=be28fc62c371fb199f20cbe58728d75c36a8dbbb988e73a82fd92fb316fc7d49&locator="
  - heading "关键上下文" [level=3]
  - term: 记录层级
  - definition: 未提供
  - term: 保存原因
  - definition:
    - paragraph: 面板端到端测试
  - term: 对象概览
  - definition: 未提供
  - heading "引用与依据" [level=3]
  - list:
    - listitem:
      - text: 归属
      - link "合成温漂研究":
        - /url: "#/evidence?id=RES-SYNTHETIC"
    - listitem:
      - text: 引用
      - link "固定来源":
        - /url: "#/evidence?id=MEM-e0abb7f9-82b6-5c64-bbdd-4fa203d49e2d&revision=1&sha256=60c5b1deea2b9f31a799cffeab2442ec0a6b3f4e63506d7a5efbe178502b2f12&locator="
    - listitem:
      - text: 引用支持依据
      - link "合成温漂测试":
        - /url: "#/evidence?id=RUN-SYNTHETIC&sha256=0d05ee95c2f8e0e8edb43aefa3a70881d2249c3ebdcdae65a61f5fcde2c2b0b5&locator="
    - listitem:
      - text: 引用
      - link "固定来源":
        - /url: "#/evidence?id=MEM-a9d2bbdb-a0a7-555c-a38a-b205efe7d863&revision=1&sha256=7cf5f8364a7097245880dc841ae7355effeec3755668be444f62b2998a81e793&locator="
    - listitem:
      - text: 引用支持依据
      - link "synthetic-panel.png":
        - /url: "#/evidence?id=SRC-PANEL-FIGURE&sha256=be28fc62c371fb199f20cbe58728d75c36a8dbbb988e73a82fd92fb316fc7d49&locator="
  - heading "下游影响" [level=3]
  - paragraph: 当前登记关系中未发现直接下游影响。
  - group: 固定版本与技术信息
```

# Test source

```ts
  22  |     await expect(
  23  |       page.getByRole("heading", { name: "对象整体概览", exact: true }),
  24  |     ).toBeVisible();
  25  |     await page.getByLabel("搜索证据").fill("证据面板完整文稿");
  26  |     await page.getByRole("button", { name: "搜索", exact: true }).click();
  27  |     await page.getByRole("link", { name: /证据面板完整文稿/ }).click();
  28  |     const detail = page.getByLabel("选中证据详情");
  29  |     await expect(
  30  |       detail.getByRole("heading", { name: "完整文稿", exact: true }),
  31  |     ).toBeVisible();
  32  |     await expect(
  33  |       detail.getByRole("heading", { name: "证据面板固定章节", exact: true }),
  34  |     ).toBeVisible();
  35  |     await expect(
  36  |       detail.getByRole("heading", { name: "参考文献", exact: true }),
  37  |     ).toHaveCount(1);
  38  |     const figure = detail.locator("img").first();
  39  |     await expect(figure).toBeVisible();
  40  |     await expect
  41  |       .poll(() =>
  42  |         figure.evaluate((image: HTMLImageElement) => image.naturalWidth),
  43  |       )
  44  |       .toBeGreaterThan(0);
  45  |     await page.screenshot({
  46  |       path: testInfo.outputPath("evidence-complete-document.png"),
  47  |       fullPage: true,
  48  |     });
  49  |     await page.goto(app.url + "#/evidence?id=SRC-PANEL-FIGURE");
  50  |     const sourceImage = page.getByLabel("选中证据详情").locator("img");
  51  |     await expect(sourceImage).toBeVisible();
  52  |     await expect
  53  |       .poll(() =>
  54  |         sourceImage.evaluate((image: HTMLImageElement) => image.naturalWidth),
  55  |       )
  56  |       .toBeGreaterThan(0);
  57  |     await page.screenshot({
  58  |       path: testInfo.outputPath("evidence-source-image.png"),
  59  |       fullPage: true,
  60  |     });
  61  |   } finally {
  62  |     app.process.kill();
  63  |   }
  64  | });
  65  | test("最近问题重开选择、公式与编号引用双向证据导航真实接口", async ({
  66  |   page,
  67  | }, testInfo) => {
  68  |   const app = await server(false, true);
  69  |   const calls: string[] = [];
  70  |   page.on("request", (request) => calls.push(new URL(request.url()).pathname));
  71  |   const started = Date.now();
  72  |   try {
  73  |     await page.goto(app.url);
  74  |     const picker = page.getByLabel("最近24小时阅读问题");
  75  |     await expect(picker.locator("option")).toHaveCount(3);
  76  |     await expect(
  77  |       page.getByText("合成阅读理解：保留前提", { exact: true }),
  78  |     ).toBeVisible();
  79  |     const firstNoteMs = Date.now() - started;
  80  |     await expect(page.locator(".katex").first()).toBeVisible();
  81  |     await expect(page.getByText(/未重新核验证据；用于继续研究/)).toBeVisible();
  82  |     expect(calls.some((path) => path.endsWith("/api/state"))).toBe(false);
  83  |     expect(calls.some((path) => path.endsWith("/evidence/search"))).toBe(false);
  84  |     const auxiliary = await picker
  85  |       .locator("option")
  86  |       .filter({ hasText: "辅助合成问题" })
  87  |       .getAttribute("value");
  88  |     await picker.selectOption(auxiliary!);
  89  |     await expect(
  90  |       page.getByText("第二问题的独立理解", { exact: true }),
  91  |     ).toBeVisible();
  92  |     await page.reload();
  93  |     await expect(picker).toHaveValue(auxiliary!);
  94  |     await expect(
  95  |       page.getByText("第二问题的独立理解", { exact: true }),
  96  |     ).toBeVisible();
  97  |     const main = await picker
  98  |       .locator("option")
  99  |       .filter({ hasText: "合成阅读会话" })
  100 |       .getAttribute("value");
  101 |     await picker.selectOption(main!);
  102 |     await expect(
  103 |       page.getByText("合成阅读理解：保留前提", { exact: true }),
  104 |     ).toBeVisible();
  105 |     await page.screenshot({
  106 |       path: testInfo.outputPath("recent-note-formulas.png"),
  107 |       fullPage: true,
  108 |     });
  109 |     await page.locator(".katex-display").first().scrollIntoViewIfNeeded();
  110 |     await page.screenshot({
  111 |       path: testInfo.outputPath("note-formula-detail.png"),
  112 |       fullPage: true,
  113 |     });
  114 |     const citation = page
  115 |       .locator('[aria-label="当前阅读笔记全文"] a[href^="#/evidence?id=MEM-"]')
  116 |       .first();
  117 |     await expect(citation).toBeVisible();
  118 |     await citation.click();
  119 |     const detail = page.getByLabel("选中证据详情");
  120 |     await expect(
  121 |       detail.getByRole("heading", { name: "面板固定方法", exact: true }),
> 122 |     ).toBeVisible();
      |       ^ Error: expect(locator).toBeVisible() failed
  123 |     await expect(
  124 |       detail.getByRole("heading", { name: "关键上下文", exact: true }),
  125 |     ).toBeVisible();
  126 |     await detail
  127 |       .locator(".evidence-links")
  128 |       .getByRole("link", { name: "合成温漂测试", exact: true })
  129 |       .click();
  130 |     await expect(
  131 |       detail.getByRole("heading", { name: "合成温漂测试", exact: true }),
  132 |     ).toBeVisible();
  133 |     await detail
  134 |       .getByRole("link", { name: "面板固定方法", exact: true })
  135 |       .click();
  136 |     await expect(
  137 |       detail.getByRole("heading", { name: "面板固定方法", exact: true }),
  138 |     ).toBeVisible();
  139 |     await page.screenshot({
  140 |       path: testInfo.outputPath("evidence-record-relations.png"),
  141 |       fullPage: true,
  142 |     });
  143 |     await page.goBack();
  144 |     await expect(
  145 |       detail.getByRole("heading", { name: "合成温漂测试", exact: true }),
  146 |     ).toBeVisible();
  147 |     await page.setViewportSize({ width: 760, height: 1000 });
  148 |     await page.screenshot({
  149 |       path: testInfo.outputPath("evidence-narrow.png"),
  150 |       fullPage: true,
  151 |     });
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
```