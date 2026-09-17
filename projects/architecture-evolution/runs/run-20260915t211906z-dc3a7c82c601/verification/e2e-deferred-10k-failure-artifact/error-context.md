# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workbench.spec.ts >> 一万节点十万关系下局部图和轻量状态响应
- Location: e2e\workbench.spec.ts:254:1

# Error details

```
Test timeout of 60000ms exceeded.
```

```
Error: locator.click: Test timeout of 60000ms exceeded.
Call log:
  - waiting for locator('[data-material-id="N0"] button')

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - complementary [ref=e4]:
    - link "研 研发工作台 材料 · 证据 · 联系" [ref=e5] [cursor=pointer]:
      - /url: "#/home"
      - generic [ref=e6]: 研
      - generic [ref=e7]:
        - text: 研发工作台
        - generic [ref=e8]: 材料 · 证据 · 联系
    - navigation [ref=e9]:
      - link "◫ 工作台" [ref=e10] [cursor=pointer]:
        - /url: "#/home"
        - generic [ref=e11]: ◫
        - text: 工作台
      - link "▦ 材料查询" [ref=e12] [cursor=pointer]:
        - /url: "#/materials"
        - generic [ref=e13]: ▦
        - text: 材料查询
      - link "◇ 材料关系" [ref=e14] [cursor=pointer]:
        - /url: "#/relations"
        - generic [ref=e15]: ◇
        - text: 材料关系
      - link "▤ 证据与影响" [ref=e16] [cursor=pointer]:
        - /url: "#/evidence"
        - generic [ref=e17]: ▤
        - text: 证据与影响
      - link "▥ 系统记忆" [ref=e18] [cursor=pointer]:
        - /url: "#/memory"
        - generic [ref=e19]: ▥
        - text: 系统记忆
      - link "◷ 任务与监测" [ref=e20] [cursor=pointer]:
        - /url: "#/tasks"
        - generic [ref=e21]: ◷
        - text: 任务与监测
    - generic [ref=e22]: 本机工作区原始记录可追溯
  - generic [ref=e23]:
    - banner [ref=e24]:
      - generic [ref=e25]: AI 研发工作区
      - generic [ref=e26]: ○ 按需分析
    - generic [ref=e27]:
      - generic [ref=e28]: 合成测试沙盒 · 全部样例为虚构，不属于正式业务证据
      - generic [ref=e29]:
        - generic [ref=e30]:
          - paragraph [ref=e31]: 材料关系 / 可重建视图
          - heading "从问题出发，看见联系" [level=1] [ref=e32]
        - generic [ref=e33]:
          - button "检查版本" [ref=e34] [cursor=pointer]
          - button "构建 / 刷新材料视图" [ref=e35] [cursor=pointer]
      - generic [ref=e36]:
        - textbox "当前问题" [ref=e37]:
          - /placeholder: 本次要解决的问题（用于关联摘要）
        - button "复制关联摘要" [ref=e38] [cursor=pointer]
        - button "导出 JSON" [ref=e39] [cursor=pointer]
        - button "保存视图" [ref=e40] [cursor=pointer]
      - generic [ref=e41]:
        - generic [ref=e42]:
          - button "问题辐射" [ref=e43] [cursor=pointer]
          - button "主题聚合" [ref=e44] [cursor=pointer]
          - button "证据链" [ref=e45] [cursor=pointer]
        - combobox "展开深度" [ref=e46]:
          - option "一跳关联" [selected]
          - option "两跳关联"
        - combobox "关系类型" [ref=e47]:
          - option "全部关系类型" [selected]
          - option "引用支持依据"
          - option "使用输入"
          - option "引用反证"
          - option "引用背景"
          - option "归属"
          - option "包含"
          - option "产出"
          - option "使用上游结果"
          - option "引用"
          - option "关联"
          - option "语义相似候选"
          - option "共享关键词"
        - generic [ref=e48]:
          - checkbox "显示候选" [ref=e49]
          - text: 显示候选
        - button "返回上个中心" [disabled] [ref=e50]
        - button "全部材料" [ref=e51] [cursor=pointer]
      - generic [ref=e52]:
        - complementary [ref=e53]:
          - heading "材料与主题" [level=2] [ref=e54]
          - group "记录层级" [ref=e55]:
            - generic [ref=e57]:
              - checkbox "L1 详细研究" [checked] [ref=e58]
              - text: L1 详细研究
            - generic [ref=e59]:
              - checkbox "L2 过程" [ref=e60]
              - text: L2 过程
            - generic [ref=e61]:
              - checkbox "L3 经验" [ref=e62]
              - text: L3 经验
            - generic [ref=e63]:
              - checkbox "L4 地图" [ref=e64]
              - text: L4 地图
            - generic [ref=e65]:
              - checkbox "原生导航（未分层）" [checked] [ref=e66]
              - text: 原生导航（未分层）
            - generic [ref=e67]: L0 原始证据通过固定来源按需追溯。
          - textbox "查找中心材料" [active] [ref=e68]:
            - /placeholder: 搜索标题或 ID
            - text: 合成材料 0
          - group "材料分类（可多选）" [ref=e69]:
            - generic [ref=e71] [cursor=pointer]:
              - checkbox "分类：详细研究" [ref=e72]
              - generic [ref=e73]: 详细研究
            - generic [ref=e74] [cursor=pointer]:
              - checkbox "分类：过程记录" [ref=e75]
              - generic [ref=e76]: 过程记录
            - generic [ref=e77] [cursor=pointer]:
              - checkbox "分类：复用经验" [ref=e78]
              - generic [ref=e79]: 复用经验
            - generic [ref=e80] [cursor=pointer]:
              - checkbox "分类：研究地图" [ref=e81]
              - generic [ref=e82]: 研究地图
            - generic [ref=e83] [cursor=pointer]:
              - checkbox "分类：核心算法" [ref=e84]
              - generic [ref=e85]: 核心算法
            - generic [ref=e86] [cursor=pointer]:
              - checkbox "分类：实验" [ref=e87]
              - generic [ref=e88]: 实验
            - generic [ref=e89] [cursor=pointer]:
              - checkbox "分类：结论" [ref=e90]
              - generic [ref=e91]: 结论
            - generic [ref=e92] [cursor=pointer]:
              - checkbox "分类：研究" [ref=e93]
              - generic [ref=e94]: 研究
            - generic [ref=e95] [cursor=pointer]:
              - checkbox "分类：知识" [ref=e96]
              - generic [ref=e97]: 知识
            - generic [ref=e98] [cursor=pointer]:
              - checkbox "分类：报告" [ref=e99]
              - generic [ref=e100]: 报告
            - generic [ref=e101] [cursor=pointer]:
              - checkbox "分类：数据" [ref=e102]
              - generic [ref=e103]: 数据
            - generic [ref=e104] [cursor=pointer]:
              - checkbox "分类：工具" [ref=e105]
              - generic [ref=e106]: 工具
            - generic [ref=e107] [cursor=pointer]:
              - checkbox "分类：项目" [ref=e108]
              - generic [ref=e109]: 项目
            - generic [ref=e110] [cursor=pointer]:
              - checkbox "分类：材料" [ref=e111]
              - generic [ref=e112]: 材料
            - generic [ref=e113]: 未勾选时显示全部分类
          - paragraph [ref=e114]: 已选 0/50 · 最多列出 60 个搜索结果
          - group [ref=e115]:
            - generic "自定义视觉分组" [ref=e116] [cursor=pointer]
        - main [ref=e117]:
          - generic [ref=e118]:
            - generic [ref=e119]:
              - button "适应画面" [ref=e120] [cursor=pointer]
              - button "＋" [ref=e121] [cursor=pointer]
              - button "－" [ref=e122] [cursor=pointer]
            - img "材料关系图" [ref=e123]
            - paragraph [ref=e128]: ● 材料 ◆ 结论 ■ 报告 红框：风险 虚线：候选 箭头：起点引用或关联终点
          - generic [ref=e129]:
            - paragraph [ref=e130]: 显示 0 个节点 / 0 条边 · 当前范围另有 0 个节点、0 条边未显示
            - generic [ref=e131]:
              - button "上一页" [disabled] [ref=e132]
              - button "下一页" [disabled] [ref=e133]
              - button "重置布局" [ref=e134] [cursor=pointer]
          - group [ref=e135]:
            - generic "读取范围与缺口" [ref=e136] [cursor=pointer]
        - complementary [ref=e137]:
          - heading "材料详情" [level=2] [ref=e138]
          - paragraph [ref=e139]: 点击节点查看材料，点击连线查看依据。列表支持键盘操作。
      - generic [ref=e140]:
        - generic [ref=e141]:
          - heading "发现潜在联系" [level=2] [ref=e142]
          - generic [ref=e143]:
            - button "共享关键词" [disabled] [ref=e144]
            - button "本地语义相似" [disabled] [ref=e145]
            - button "结构聚类" [ref=e146] [cursor=pointer]
            - button "全范围结构聚类" [ref=e147] [cursor=pointer]
            - button "候选聚类" [disabled] [ref=e148]
        - paragraph [ref=e149]: 相似分析在允许范围内寻找近邻；默认聚类针对当前可见选择，全范围聚类覆盖未排除材料。候选结果不会提高证据可信等级。
      - generic [ref=e150]:
        - heading "关联建议" [level=2] [ref=e151]
        - generic [ref=e152]:
          - textbox "候选标题" [ref=e153]:
            - /placeholder: 针对所选材料提出一个关联建议
          - textbox "候选解释" [ref=e154]:
            - /placeholder: 依据与待核对内容
          - button "保存候选" [disabled] [ref=e155]
          - button "导入 AI 候选" [ref=e156] [cursor=pointer]
```

# Test source

```ts
  163 |           (n: { level?: string }) =>
  164 |             !n.level || n.level === "L1" || n.level === "L2",
  165 |         )
  166 |         .map((n: { id: string }) => n.id),
  167 |     );
  168 |     const catalog = {
  169 |       ...rawCatalog,
  170 |       nodes: rawCatalog.nodes.filter((n: { id: string }) => allowed.has(n.id)),
  171 |       edges: rawCatalog.edges.filter(
  172 |         (e: { source: string; target: string }) =>
  173 |           allowed.has(e.source) && allowed.has(e.target),
  174 |       ),
  175 |     };
  176 |     const expected = (ids: string[]) => {
  177 |       const selected = new Set(ids);
  178 |       for (const edge of catalog.edges) {
  179 |         if (ids.includes(edge.source)) selected.add(edge.target);
  180 |         if (ids.includes(edge.target)) selected.add(edge.source);
  181 |       }
  182 |       return [...selected].sort();
  183 |     };
  184 |     async function assertExport(ids: string[]) {
  185 |       const visible = expected(ids);
  186 |       await expect(page.locator(".graph-main")).toContainText(
  187 |         `显示 ${visible.length} 个节点`,
  188 |       );
  189 |       const pending = page.waitForEvent("download");
  190 |       await page
  191 |         .getByRole("button", { name: "导出 JSON", exact: true })
  192 |         .click();
  193 |       const file = await (await pending).path();
  194 |       const value = JSON.parse(await readFile(file!, "utf8"));
  195 |       expect(value.graph.nodes.map((n: { id: string }) => n.id).sort()).toEqual(
  196 |         visible,
  197 |       );
  198 |       expect(value.graph.selection.checked.sort()).toEqual([...ids].sort());
  199 |     }
  200 |     await page
  201 |       .getByRole("checkbox", { name: "分类：结论", exact: true })
  202 |       .check();
  203 |     await page.getByLabel("查找中心材料").fill("合成");
  204 |     expect(
  205 |       await page.locator(".material-row .eyebrow").allTextContents(),
  206 |     ).toEqual(["结论"]);
  207 |     await page
  208 |       .getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true })
  209 |       .check();
  210 |     await assertExport(["CLM-SYNTHETIC"]);
  211 |     await page
  212 |       .getByRole("checkbox", { name: "分类：研究", exact: true })
  213 |       .check();
  214 |     const shownKinds = new Set(
  215 |       await page.locator(".material-row .eyebrow").allTextContents(),
  216 |     );
  217 |     expect(shownKinds).toEqual(new Set(["结论", "研究"]));
  218 |     await page
  219 |       .getByRole("checkbox", { name: "分类：结论", exact: true })
  220 |       .uncheck();
  221 |     await expect(
  222 |       page.getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true }),
  223 |     ).toHaveCount(0);
  224 |     await page
  225 |       .locator('[data-material-id="RES-SYNTHETIC"] input[type="checkbox"]')
  226 |       .check();
  227 |     await assertExport(["CLM-SYNTHETIC", "RES-SYNTHETIC"]);
  228 |     await page
  229 |       .getByRole("checkbox", { name: "分类：研究", exact: true })
  230 |       .uncheck();
  231 |     expect(
  232 |       new Set(await page.locator(".material-row .eyebrow").allTextContents())
  233 |         .size,
  234 |     ).toBeGreaterThan(2);
  235 |     await page
  236 |       .getByRole("checkbox", { name: "分类：结论", exact: true })
  237 |       .check();
  238 |     await expect(
  239 |       page.getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true }),
  240 |     ).toBeChecked();
  241 |     await page
  242 |       .getByLabel("选择 合成计算偏移为 1.4 ms", { exact: true })
  243 |       .uncheck();
  244 |     await assertExport(["RES-SYNTHETIC"]);
  245 |     await page.getByRole("button", { name: "清空勾选", exact: true }).click();
  246 |     await expect(page.locator(".graph-main")).toContainText(
  247 |       `显示 ${catalog.nodes.length} 个节点`,
  248 |     );
  249 |   } finally {
  250 |     app.process.kill();
  251 |   }
  252 | });
  253 | 
  254 | test("一万节点十万关系下局部图和轻量状态响应", async ({ page, request }) => {
  255 |   const app = await server(true);
  256 |   try {
  257 |     await page.goto(app.url + "#/relations");
  258 |     await expect(page.getByRole("img", { name: "材料关系图" })).toBeVisible();
  259 |     await page
  260 |       .getByRole("checkbox", { name: "原生导航（未分层）", exact: true })
  261 |       .check();
  262 |     await page.getByLabel("查找中心材料").fill("合成材料 0");
> 263 |     await page.locator('[data-material-id="N0"] button').click();
      |                                                          ^ Error: locator.click: Test timeout of 60000ms exceeded.
  264 |     const start = Date.now();
  265 |     await page.getByRole("button", { name: "以此为中心", exact: true }).click();
  266 |     await expect(page.locator(".graph-main")).toContainText("显示 21 个节点");
  267 |     await page.getByRole("button", { name: "适应画面", exact: true }).click();
  268 |     const elapsed = Date.now() - start;
  269 |     expect(elapsed).toBeLessThan(3000);
  270 |     await page
  271 |       .getByRole("button", { name: "全范围结构聚类", exact: true })
  272 |       .click();
  273 |     const t = Date.now();
  274 |     const response = await request.get(app.url + "api/v1/capabilities");
  275 |     expect(response.ok()).toBeTruthy();
  276 |     const apiMs = Date.now() - t;
  277 |     expect(apiMs).toBeLessThan(500);
  278 |     console.log(
  279 |       JSON.stringify({
  280 |         scaleNodes: 10000,
  281 |         scaleEdges: 100000,
  282 |         localInteractionMs: elapsed,
  283 |         statusMs: apiMs,
  284 |       }),
  285 |     );
  286 |     await page.screenshot({
  287 |       path: resolve(root, "tmp/workbench-scale.png"),
  288 |       fullPage: true,
  289 |     });
  290 |   } finally {
  291 |     app.process.kill();
  292 |   }
  293 | });
  294 | 
  295 | test("对象阅读清单、完整原文和版本导出真实接口", async ({ page }) => {
  296 |   const app = await server(false, true);
  297 |   const errors: string[] = [];
  298 |   page.on("pageerror", (e) => errors.push(e.message));
  299 |   try {
  300 |     await page.goto(app.url + "#/memory");
  301 |     await page.getByLabel("记忆归属对象").selectOption("RES-SYNTHETIC");
  302 |     await page.getByRole("button", { name: "阅读记录", exact: true }).click();
  303 |     await page
  304 |       .getByRole("button", { name: "合成阅读会话", exact: true })
  305 |       .click();
  306 |     await expect(
  307 |       page.getByText("合成阅读理解：保留前提", { exact: true }),
  308 |     ).toBeVisible();
  309 |     await expect(
  310 |       page.getByText("必要细节：绝对温度偏置273.15", { exact: true }),
  311 |     ).toBeVisible();
  312 |     const event = page.waitForEvent("download");
  313 |     await page.getByRole("button", { name: "导出此版本笔记" }).click();
  314 |     expect((await event).suggestedFilename()).toMatch(/RS-.*-r4.md/);
  315 |     await page.getByRole("button", { name: "面板固定方法 · 读取原文" }).click();
  316 |     await expect(page.getByText(/panelreading 前提：绝对温度/)).toBeVisible();
  317 |     await page.screenshot({
  318 |       path: resolve(root, ".local/unified-reading-panel.png"),
  319 |       fullPage: true,
  320 |     });
  321 |     expect(errors).toEqual([]);
  322 |   } finally {
  323 |     app.process.kill();
  324 |   }
  325 | });
  326 | 
```