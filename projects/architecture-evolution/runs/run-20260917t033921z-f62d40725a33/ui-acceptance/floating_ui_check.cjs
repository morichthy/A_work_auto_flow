// Actual saved research, isolated copy, production frontend. This temporary
// acceptance harness does not create records or use the production server.
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(process.env.RDWORK_UI_ROOT || process.cwd());
const { chromium } = require(path.join(root,'automation/frontend/node_modules/playwright'));
const output = path.resolve(process.argv[2]);
let server, browser;
(async () => {
  server = spawn(path.join(root, 'services/qdrant/runtime/python.exe'),
    [path.join(__dirname, 'floating_ui_snapshot.py'), output],
    {cwd: root, windowsHide: true, env: {...process.env, PYTHONIOENCODING:'utf-8'}, stdio:['ignore','pipe','pipe']});
  let log = '';
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('snapshot server timeout: ' + log)), 120000);
    server.stdout.on('data', data => {
      log += data.toString();
      for (const line of log.split('\n')) {
        try { const entry=JSON.parse(line); if(entry.url) {clearTimeout(timer); resolve(entry.url);} } catch {}
      }
    });
    server.stderr.on('data', data => {log += data.toString();});
    server.on('exit', code => {clearTimeout(timer); reject(Error('server exit '+code+': '+log));});
  });
  const snapshot=JSON.parse(await fs.readFile(path.join(output, 'FLOATING_UI_SNAPSHOT.json'),'utf8'));
  browser=await chromium.launch({channel:'msedge', headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];
  page.on('pageerror', error => errors.push(error.message));
  const results=[];
  const requestedKinds=process.argv[3] ? process.argv[3].split(',') : ['source','narrative','experience','overview','document'];
  const selected=snapshot.records.filter(record => requestedKinds.includes(record.kind));
  for(const [position, record] of selected.entries()) {
    const target=url+'#/evidence?id='+encodeURIComponent(record.record_id)+'&revision='+record.revision;
    await page.goto(target);
    const panel=page.getByLabel('选中证据详情');
    await panel.getByRole('heading',{name:record.title, exact:true}).waitFor({timeout:60000});
    const content=await panel.innerText();
    const alerts=await panel.getByRole('alert').allTextContents();
    const global_alerts=await page.locator('.alert').allTextContents();
    const imageCount=await panel.locator('img').count();
    // Figures load lazily; scroll every actual figure into view and await
    // decoding before classifying an unloaded image as a display failure.
    for (let index=0; index<imageCount; index++) {
      const figure=panel.locator('img').nth(index);
      await figure.scrollIntoViewIfNeeded();
      await figure.evaluate(img=>img.decode());
    }
    const images=await panel.locator('img').evaluateAll(nodes=>nodes.map(img=>({width:img.naturalWidth,complete:img.complete})));
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
    const filename='floating-'+String(position+1).padStart(2,'0')+'-'+record.kind+'.png';
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.screenshot({path:path.join(output,filename), fullPage:true});
    await page.screenshot({path:path.join(output,filename.replace('.png','-top.png'))});
    await fs.writeFile(path.join(output,filename.replace('.png','.txt')),content);
    for (const [suffix, locator] of [['formula',panel.locator('.katex-display')], ['table',panel.locator('table')]]) {
      if (await locator.count()) {
        await locator.first().scrollIntoViewIfNeeded();
        await page.screenshot({path:path.join(output,filename.replace('.png','-'+suffix+'.png'))});
      }
    }
    const fields=panel.getByText('结构化记录字段',{exact:true});
    if (await fields.count()) {
      await fields.scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(output,filename.replace('.png','-collapsed.png'))});
    }
    results.push({...record, url:target, screenshot:filename, content_chars:content.length, alerts, global_alerts, imageCount, images, horizontal_overflow:overflow,
      confirmation_visible:await panel.getByLabel('结论确认状态').isVisible(), rendered_math:await panel.locator('.katex').count()});
  }
  const originalHead=JSON.parse(await fs.readFile(path.join(root,'research/floating-point-summation/memory/HEAD.json'),'utf8'));
  await fs.writeFile(path.join(output,'FLOATING_UI_BROWSER.json'), JSON.stringify({results,errors,server_log:log,
    original_head_unchanged:JSON.stringify(originalHead)===JSON.stringify(snapshot.research_head)},null,2));
  console.log(JSON.stringify({checked:results.length,errors,results:results.map(r=>({kind:r.kind,revision:r.revision,title:r.title,chars:r.content_chars,overflow:r.horizontal_overflow,images:r.images}))},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
