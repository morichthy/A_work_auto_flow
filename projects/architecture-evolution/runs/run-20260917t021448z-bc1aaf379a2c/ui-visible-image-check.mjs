// Isolated acceptance probe: no frontend source or build artifact is changed.
import {spawn} from 'node:child_process';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {writeFile} from 'node:fs/promises';
const root=process.cwd();
const output=resolve(root,'projects/architecture-evolution/runs/run-20260917t021448z-bc1aaf379a2c');
const {chromium,expect}=await import(pathToFileURL(resolve(root,'automation/frontend/node_modules/@playwright/test/index.mjs')));
const child=spawn(resolve(root,'services/qdrant/runtime/python.exe'),[resolve(root,'automation/tests/serve_workbench_test.py'),'--reading'],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
let browser;
try {
  const url=await new Promise((ok,fail)=>{
    let output='';
    const timeout=setTimeout(()=>fail(Error('Fixture startup timeout')),30000);
    child.stdout.on('data',chunk=>{output+=chunk;for(const line of output.split('\n')){try{const row=JSON.parse(line);if(row.url){clearTimeout(timeout);ok(row.url);return;}}catch{}}});
    child.stderr.on('data',chunk=>{output+=chunk;});
    child.on('exit',code=>{clearTimeout(timeout);fail(Error(`Fixture exit ${code}: ${output}`));});
  });
  browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto(url+'#/evidence');
  await page.getByLabel('搜索证据').fill('证据面板完整文稿');
  await page.getByRole('button',{name:'搜索',exact:true}).click();
  await page.getByRole('link',{name:/证据面板完整文稿/}).click();
  const detail=page.getByLabel('选中证据详情');
  const image=detail.locator('img').first();
  await expect(image).toBeVisible();
  await expect.poll(()=>image.evaluate(img=>img.naturalWidth)).toBeGreaterThan(1);
  const documentImage=await image.evaluate(img=>({width:img.naturalWidth,height:img.naturalHeight,alt:img.alt}));
  await expect(detail.getByRole('heading',{name:'参考文献',exact:true})).toHaveCount(1);
  await page.screenshot({path:resolve(output,'ui-visible-document.png'),fullPage:true});
  await page.goto(url+'#/evidence?id=SRC-PANEL-FIGURE');
  const source=page.getByLabel('选中证据详情').locator('img');
  await expect(source).toBeVisible();
  await expect.poll(()=>source.evaluate(img=>img.naturalWidth)).toBeGreaterThan(1);
  const sourceImage=await source.evaluate(img=>({width:img.naturalWidth,height:img.naturalHeight,alt:img.alt}));
  await page.screenshot({path:resolve(output,'ui-visible-source.png'),fullPage:true});
  const result={status:'passed',documentImage,sourceImage};
  await writeFile(resolve(output,'ui-visible-image-result.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
} finally { await browser?.close();child.kill(); }
