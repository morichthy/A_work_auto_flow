# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workbench.spec.ts >> 对象阅读清单、完整原文和版本导出真实接口
- Location: e2e\workbench.spec.ts:611:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('heading', { name: '面板固定方法', exact: true })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByRole('heading', { name: '面板固定方法', exact: true }) with timeout 5000ms
  - waiting for getByRole('heading', { name: '面板固定方法', exact: true })

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
    - /url: "#/evidence?id=MEM-fb915303-da11-529f-a0ac-611a29d18029"
    - text: document
    - strong: 证据面板完整文稿
  - link "document_section 证据面板固定章节 本章固定说明。":
    - /url: "#/evidence?id=MEM-654cb2a7-4933-5481-8a6e-aa1478caa222"
    - text: document_section
    - strong: 证据面板固定章节
    - text: 本章固定说明。
  - link "详细研究 证据面板合成技术单元 必要定义 ONLY_DEFINITION；$T$ 的单位为 K。 完整过程 ONLY_FULL_RESULT：$T=t+273.15$。 ![合成图](figure:0) 未选择的 OPTIONAL_BLOCK。":
    - /url: "#/evidence?id=MEM-111c12ce-caa0-5819-84f9-15bf6bbe6fe1"
    - text: 详细研究
    - strong: 证据面板合成技术单元
    - text: 必要定义 ONLY_DEFINITION；$T$ 的单位为 K。 完整过程 ONLY_FULL_RESULT：$T=t+273.15$。 ![合成图](figure:0) 未选择的 OPTIONAL_BLOCK。
  - link "overview 面板固定方法 panelreading 前提：绝对温度，偏置为273.15；这是合成展示资料，未验证现实方法。":
    - /url: "#/evidence?id=MEM-8d9b1ba7-0583-5b61-82a5-ccc7a9e90c99"
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
      - /url: "#/evidence?id=MEM-111c12ce-caa0-5819-84f9-15bf6bbe6fe1&revision=1&sha256=1c287e70480b2b69f7f365024e2a02c15a7f2b757d32dab7d92e4809291fb6bf&locator="
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
        - /url: "#/evidence?id=MEM-654cb2a7-4933-5481-8a6e-aa1478caa222&revision=1&sha256=7e44e17b708308d49fda5ed63442e12b6f54e20ab817754eba289f550d11db2d&locator="
    - listitem:
      - text: 引用支持依据
      - link "合成温漂测试":
        - /url: "#/evidence?id=RUN-SYNTHETIC&sha256=0d05ee95c2f8e0e8edb43aefa3a70881d2249c3ebdcdae65a61f5fcde2c2b0b5&locator="
    - listitem:
      - text: 引用
      - link "固定来源":
        - /url: "#/evidence?id=MEM-111c12ce-caa0-5819-84f9-15bf6bbe6fe1&revision=1&sha256=1c287e70480b2b69f7f365024e2a02c15a7f2b757d32dab7d92e4809291fb6bf&locator="
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
  548 |       new Set(await page.locator(".material-row .eyebrow").allTextContents())
  549 |         .size,
  550 |     ).toBeGreaterThan(2);
  551 |     await page
  552 |       .getByRole("checkbox", { name: "分类：结论", exact: true })
  553 |       .check();
  554 |     await expect(
  555 |       page.getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true }),
  556 |     ).toBeChecked();
  557 |     await page
  558 |       .getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true })
  559 |       .uncheck();
  560 |     await assertExport(["RES-SYNTHETIC"]);
  561 |     await page.getByRole("button", { name: "清空勾选", exact: true }).click();
  562 |     await expect(page.locator(".graph-main")).toContainText(
  563 |       `显示 ${catalog.nodes.length} 个节点`,
  564 |     );
  565 |   } finally {
  566 |     app.process.kill();
  567 |   }
  568 | });
  569 | 
  570 | test("一万节点十万关系下局部图和轻量状态响应", async ({ page, request }) => {
  571 |   const app = await server(true);
  572 |   try {
  573 |     await page.goto(app.url + "#/relations");
  574 |     await expect(page.getByRole("img", { name: "材料关系图" })).toBeVisible();
  575 |     await page
  576 |       .getByRole("checkbox", { name: "原生导航（未分层）", exact: true })
  577 |       .check();
  578 |     await page.getByLabel("查找中心材料").fill("合成材料 0");
  579 |     await page.locator('[data-material-id="N0"] button').click();
  580 |     const start = Date.now();
  581 |     await page.getByRole("button", { name: "以此为中心", exact: true }).click();
  582 |     await expect(page.locator(".graph-main")).toContainText("显示 21 个节点");
  583 |     await page.getByRole("button", { name: "适应画面", exact: true }).click();
  584 |     const elapsed = Date.now() - start;
  585 |     expect(elapsed).toBeLessThan(3000);
  586 |     await page
  587 |       .getByRole("button", { name: "全范围结构聚类", exact: true })
  588 |       .click();
  589 |     const t = Date.now();
  590 |     const response = await request.get(app.url + "api/v1/capabilities");
  591 |     expect(response.ok()).toBeTruthy();
  592 |     const apiMs = Date.now() - t;
  593 |     expect(apiMs).toBeLessThan(500);
  594 |     console.log(
  595 |       JSON.stringify({
  596 |         scaleNodes: 10000,
  597 |         scaleEdges: 100000,
  598 |         localInteractionMs: elapsed,
  599 |         statusMs: apiMs,
  600 |       }),
  601 |     );
  602 |     await page.screenshot({
  603 |       path: resolve(root, "tmp/workbench-scale.png"),
  604 |       fullPage: true,
  605 |     });
  606 |   } finally {
  607 |     app.process.kill();
  608 |   }
  609 | });
  610 | 
  611 | test("对象阅读清单、完整原文和版本导出真实接口", async ({ page }) => {
  612 |   const app = await server(false, true);
  613 |   const errors: string[] = [];
  614 |   page.on("pageerror", (e) => errors.push(e.message));
  615 |   try {
  616 |     await page.goto(app.url + "#/memory?tab=reading&owner=RES-SYNTHETIC");
  617 |     await expect(page).toHaveURL(/#\/home$/);
  618 |     // 进入即加载现有笔记，不需要点击会话，更不应自动读取固定原文。
  619 |     await expect(
  620 |       page.getByText("合成阅读理解：保留前提", { exact: true }),
  621 |     ).toBeVisible();
  622 |     await expect(
  623 |       page.getByRole("heading", {
  624 |         name: "细节、参数、单位与边界",
  625 |         exact: true,
  626 |       }),
  627 |     ).toBeVisible();
  628 |     await expect(
  629 |       page.getByText("绝对温度偏置273.15", { exact: true }),
  630 |     ).toBeVisible();
  631 |     await page
  632 |       .getByRole("button", { name: "刷新当前笔记", exact: true })
  633 |       .click();
  634 |     await expect(
  635 |       page.getByText("合成阅读理解：保留前提", { exact: true }),
  636 |     ).toBeVisible();
  637 |     const event = page.waitForEvent("download");
  638 |     await page.getByRole("button", { name: "导出当前笔记" }).click();
  639 |     expect((await event).suggestedFilename()).toMatch(
  640 |       /^合成阅读会话-RS-[a-f0-9]{12}-r4\.md$/,
  641 |     );
  642 |     await page
  643 |       .locator('[aria-label="当前阅读笔记全文"] a[href^="#/evidence?id=MEM-"]')
  644 |       .first()
  645 |       .click();
  646 |     await expect(
  647 |       page.getByRole("heading", { name: "面板固定方法", exact: true }),
> 648 |     ).toBeVisible();
      |       ^ Error: expect(locator).toBeVisible() failed
  649 |     await page.screenshot({
  650 |       path: resolve(root, ".local/unified-reading-panel.png"),
  651 |       fullPage: true,
  652 |     });
  653 |     expect(errors).toEqual([]);
  654 |   } finally {
  655 |     app.process.kill();
  656 |   }
  657 | });
  658 | 
```