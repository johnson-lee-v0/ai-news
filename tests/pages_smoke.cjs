/* Optional GitHub Pages QA: build _site first, then node tests/pages_smoke.cjs.
 * Existing Playwright/Chromium only; no downloads or user browser profiles.
 * PAGES_SITE_DIR selects the build. PAGES_SCREENSHOT_DIR must be outside the repo.
 * No database, live feeds, accounts, publication or repository artifacts are used.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');

async function main() {
  let chromium;
  try { ({chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright')); }
  catch (_) { throw new Error('Install Playwright separately or set PLAYWRIGHT_MODULE to an existing installation. This test downloads nothing.'); }
  const root = path.resolve(__dirname, '..');
  const site = path.resolve(process.env.PAGES_SITE_DIR || path.join(root, '_site'));
  const dataset = JSON.parse(fs.readFileSync(path.join(site, 'data/dashboard.json'), 'utf8'));
  assert.equal(dataset.publication.mode, 'static');
  assert.ok(dataset.articles.length > 0, 'Build must contain reviewed public evidence');
  const output = process.env.PAGES_SCREENSHOT_DIR ? path.resolve(process.env.PAGES_SCREENSHOT_DIR) : fs.mkdtempSync(path.join(os.tmpdir(), 'ai-news-pages-qa-'));
  const proposedOutput = path.relative(root,output);
  assert.ok(proposedOutput.startsWith(`..${path.sep}`) || path.isAbsolute(proposedOutput), 'Screenshots and receipts must be outside the repository');
  fs.mkdirSync(output, {recursive:true});
  const relativeOutput = path.relative(fs.realpathSync(root), fs.realpathSync(output));
  assert.ok(relativeOutput.startsWith(`..${path.sep}`) || path.isAbsolute(relativeOutput), 'Screenshots and receipts must be outside the repository');
  const allowed = new Map([['index.html','text/html'],['app.js','text/javascript'],['styles.css','text/css'],['favicon.svg','image/svg+xml'],['data/dashboard.json','application/json']]);
  const served = [], errors = [], requests = [], external = [];
  const server = http.createServer((request,response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    served.push({path:pathname,method:request.method});
    if(request.method !== 'GET' && request.method !== 'HEAD') {response.writeHead(405);response.end();return;}
    if(!pathname.startsWith('/ai-news/')) {response.writeHead(404);response.end();return;}
    const file = pathname.slice('/ai-news/'.length) || 'index.html';
    if(!allowed.has(file)) {response.writeHead(404);response.end();return;}
    try {
      const body=fs.readFileSync(path.join(site,file));
      response.writeHead(200,{'Content-Type':allowed.get(file),'Cache-Control':'no-store'});
      response.end(request.method==='HEAD' ? undefined : body);
    } catch (_) {response.writeHead(404);response.end();}
  });
  await new Promise((resolve,reject) => {server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const origin=`http://127.0.0.1:${server.address().port}`;
  const url=`${origin}/ai-news/`;
  let browser;
  try {
    browser=await chromium.launch({headless:true});
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    await context.route('**/*',route=>{
      if(new URL(route.request().url()).origin!==origin) {external.push(route.request().url());return route.abort();}
      return route.continue();
    });
    const page=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>requests.push({path:new URL(request.url()).pathname,method:request.method()}));
    await page.goto(url);
    await page.locator('#dashboard').waitFor({state:'visible'});
    assert.equal(await page.locator('html').getAttribute('data-mode'),'static');
    assert.match(await page.locator('#publication-banner').innerText(),/Public reviewed snapshot/);
    assert.match(await page.locator('#edition-asof').innerText(),/Reviewed/);
    assert.equal(await page.locator('#stat-total').innerText(),String(dataset.articles.length));
    assert.equal(await page.locator('#stat-sources').innerText(),String(dataset.sources.length));
    assert.ok(await page.locator('#brief-feed .article').count()>0);
    assert.equal(await page.locator('#refresh').isVisible(),false);
    assert.equal(await page.locator('#refresh').isDisabled(),true);
    assert.equal(await page.locator('#lead-url').isDisabled(),true);
    assert.equal(await page.locator('#lead-note').isDisabled(),true);
    assert.equal(await page.locator('button[data-review]:visible').count(),0);
    assert.ok(await page.locator('button[data-review]').evaluateAll(buttons=>buttons.every(button=>button.disabled)));
    assert.equal(await page.locator('#review-filter').isDisabled(),true);

    const go = async section => {await page.locator(`[data-nav="${section}"]`).click();await page.locator(`#panel-${section}`).waitFor({state:'visible'});};
    await go('evidence');
    const stories=dataset.stories || dataset.articles;
    assert.equal(await page.locator('#evidence-feed .article').count(),Math.min(stories.length,40));
    const first=stories[0];
    await page.locator('#search').fill(first.title);
    assert.ok(await page.locator('#evidence-feed .article').count()>0);
    await page.locator('#search').fill('no-public-snapshot-match-qa');
    assert.match(await page.locator('#evidence-feed').innerText(),/No evidence matches/);
    await page.locator('#search').fill('');
    for(const role of ['primary','secondary','discovery']) {
      await page.locator('#role-filter').selectOption(role);
      assert.equal(await page.locator('#evidence-feed .article').count(),Math.min(stories.filter(item=>item.source_role===role).length,40));
    }
    await page.locator('#role-filter').selectOption('all');
    const entity=first.entities?.[0];
    if(entity) {
      await page.locator('#entity-filter').selectOption(entity);
      assert.equal(await page.locator('#evidence-feed .article').count(),Math.min(stories.filter(item=>(item.entities||[]).includes(entity)||(item.source_entities||[]).includes(entity)).length,40));
      await page.locator('#entity-filter').selectOption('all');
    }
    await page.locator('#lens-filter').selectOption(first.lens || 'other');
    assert.ok(await page.locator('#evidence-feed .article').count()>0);
    await page.locator('#lens-filter').selectOption('all');
    await page.locator('#sort').selectOption('date');
    await page.locator('#sort').selectOption('rank');
    const firstDetails=page.locator('#evidence-feed .article-details').first();
    await firstDetails.locator('summary').click();
    assert.equal(await firstDetails.getAttribute('open'),'');
    assert.match(await firstDetails.innerText(),/Snapshot reviewed/);
    assert.match(await firstDetails.innerText(),/Counterevidence/i);
    await firstDetails.locator('summary').click();
    for(const item of stories.filter(item=>item.quote_as_of || item.republished_at || item.report_period || item.event_date)) {
      await page.locator('#search').fill(item.title);
      const detail=page.locator('#evidence-feed .article-details').first();
      await detail.locator('summary').click();
      const contextText=await detail.innerText();
      if(item.quote_as_of) assert.match(contextText,/Market quote as of/);
      if(item.republished_at) assert.match(contextText,/Republished/);
      if(item.report_period) assert.ok(contextText.includes(item.report_period));
      if(item.event_date) assert.match(contextText,/Event date/);
      if(item.methodology_url) assert.equal(await detail.getByRole('link',{name:/Probability methodology/}).getAttribute('href'),item.methodology_url);
    }
    await page.locator('#search').fill('');

    await go('financing');
    await page.locator('#cds-spread').fill('1194.5');
    await page.locator('#cds-years').fill('5');
    await page.locator('#cds-recovery').fill('40');
    await page.getByRole('button',{name:'Calculate illustration'}).click();
    assert.match(await page.locator('#cds-output').innerText(),/63.0% over 5 years/);
    assert.match(await page.locator('#cds-output').innerText(),/18.1% over one year/);
    await go('sources');
    assert.equal(await page.locator('.source-row').count(),dataset.sources.length);
    assert.match(await page.locator('#source-list').innerText(),/Curated reference/);
    assert.doesNotMatch(await page.locator('#source-list').innerText(),/Last success|Last attempt|Not fetched|Fetch failed/);
    assert.match(await page.locator('#source-status-summary').innerText(),/linked reference/);
    assert.equal(await page.locator('#lead-form').isVisible(),false);
    assert.match(await page.locator('#x-access').innerText(),/No X collection/);

    // Even synthetic events on hidden controls must never trigger an API request.
    await page.evaluate(()=>{
      document.querySelector('#refresh').dispatchEvent(new Event('click',{bubbles:true}));
      document.querySelector('#lead-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      document.querySelector('button[data-review]')?.dispatchEvent(new Event('click',{bubbles:true}));
    });
    const screenshots=[];
    for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
      await page.setViewportSize(viewport);
      for(const section of ['brief','evidence','financing','earnings','sources']) {
        await go(section);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${section} overflows at ${viewport.width}px`);
        await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
        const filename=`pages-${name}-${section}.png`;
        await page.screenshot({path:path.join(output,filename)});screenshots.push(filename);
      }
    }
    const links=await page.locator('a[target="_blank"]').evaluateAll(nodes=>nodes.map(node=>({url:node.href,rel:node.rel})));
    assert.ok(links.every(link=>link.url.startsWith('https://')&&link.rel.includes('noopener')&&link.rel.includes('noreferrer')));
    assert.equal(requests.filter(request=>request.path==='/ai-news/data/dashboard.json').length,1,'Snapshot fetched exactly once per page document');
    assert.ok(requests.some(request=>request.path==='/ai-news/app.js'));
    assert.ok(requests.some(request=>request.path==='/ai-news/styles.css'));
    assert.ok(requests.every(request=>request.method==='GET'&&request.path.startsWith('/ai-news/')&&!request.path.includes('/api/')));
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    assert.deepEqual(await context.cookies(),[]);

    // An intercepted stale snapshot is display-only and never saved into the build.
    const stale=JSON.parse(JSON.stringify(dataset));
    stale.publication.reviewed_at=new Date(Date.now()-10*86400000).toISOString();
    const stalePage=await context.newPage();
    stalePage.on('pageerror',error=>errors.push(error.message));
    await stalePage.route('**/data/dashboard.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(stale)}));
    await stalePage.goto(url);
    await stalePage.locator('#dashboard').waitFor({state:'visible'});
    assert.match(await stalePage.locator('#freshness').innerText(),/over 48 hours ago.*stale/);
    await stalePage.close();
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    assert.ok(served.every(request=>request.method==='GET'&&!request.path.includes('/api/')));
    const receipt={passed:true,checked_at:new Date().toISOString(),prefix:'/ai-news/',mode:'static',articles:dataset.articles.length,sources:dataset.sources.length,snapshot_requests_per_document:1,api_requests:0,external_requests:0,browser_errors:0,checks:['populated reviewed snapshot and source dates','relative assets under repository prefix','single JSON fetch; no API, POST, cookies or browser storage','tabs, search, filters, details, dated provenance and calculator','hidden and disabled mutation controls with guarded handlers','linked source references without backend health claims','desktop/mobile all five sections without page overflow','stale review warning'],screenshots};
    fs.writeFileSync(path.join(output,'pages-smoke.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(`PASS: static Pages smoke. Screenshots and receipt: ${output}`);
  } finally {
    if(browser) await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
