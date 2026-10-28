/* Local-only regression for the news-first desk and sourced financing network.
 * Build _site first. Uses existing Playwright/Chromium, an ephemeral loopback
 * server and isolated browser contexts. Synthetic responses stay in memory.
 * PAGES_SCREENSHOT_DIR must be outside this repository. No live source fetches,
 * production data changes, user browser profile, credentials or deployment.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');

async function main() {
  const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const root = path.resolve(__dirname, '..');
  const site = path.resolve(process.env.PAGES_SITE_DIR || path.join(root, '_site'));
  const dataset = JSON.parse(fs.readFileSync(path.join(site, 'data/dashboard.json'), 'utf8'));
  const clone = value => JSON.parse(JSON.stringify(value));
  assert.equal(dataset.publication.mode, 'static');
  assert.ok(dataset.articles.length > 0, 'The tested build must contain reviewed evidence');
  const output = process.env.PAGES_SCREENSHOT_DIR ? path.resolve(process.env.PAGES_SCREENSHOT_DIR) : fs.mkdtempSync(path.join(os.tmpdir(), 'pulse-news-map-qa-'));
  const outside = value => { const relative=path.relative(root,value); return relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative); };
  assert.ok(outside(output), 'QA artifacts must stay outside the repository');
  fs.mkdirSync(output, {recursive:true});
  assert.ok(outside(fs.realpathSync(output)), 'QA output cannot resolve into the repository');
  const assets = new Map([['index.html','text/html'],['app.js','text/javascript'],['finance.js','text/javascript'],['visit-state.js','text/javascript'],['styles.css','text/css'],['finance.css','text/css'],['favicon.svg','image/svg+xml'],['data/dashboard.json','application/json']]);
  const served=[], requests=[], errors=[], external=[], httpErrors=[];
  const server=http.createServer((req,res)=>{
    const url=new URL(req.url,'http://localhost');
    served.push({path:url.pathname,method:req.method});
    if(req.method!=='GET' || !url.pathname.startsWith('/ai-news/')) {res.writeHead(404);res.end();return;}
    const name=url.pathname.slice('/ai-news/'.length) || 'index.html';
    if(!assets.has(name)) {res.writeHead(404);res.end();return;}
    try {res.writeHead(200,{'Content-Type':assets.get(name),'Cache-Control':'no-store'});res.end(fs.readFileSync(path.join(site,name)));}
    catch (_) {res.writeHead(404);res.end();}
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const origin=`http://127.0.0.1:${server.address().port}`;
  const url=origin+'/ai-news/';
  let browser;
  const screenshots=[];
  try {
    browser=await chromium.launch({headless:true});
    const makeContext=async options=>{
      const context=await browser.newContext(options);
      await context.route('**/*',route=>{
        const req=route.request();
        if(new URL(req.url()).origin!==origin) {external.push(req.url());return route.abort();}
        return route.continue();
      });
      context.on('page',page=>{
        page.on('pageerror',error=>errors.push(error.message));
        page.on('request',req=>requests.push({path:new URL(req.url()).pathname,method:req.method()}));
        page.on('response',response=>{if(response.status()>=400)httpErrors.push(response.status()+':'+response.url());});
      });
      return context;
    };
    const ready=async page=>{await page.locator('#dashboard').waitFor({state:'visible'});};
    const go=async (page,section)=>{
      if(section==='brief' || section==='explore') await page.locator(`.nav [data-nav="${section}"]`).click();
      else {await page.locator('.nav [data-nav="explore"]').click();await page.locator(`#panel-explore [data-nav="${section}"]`).click();}
      await page.locator(`#panel-${section}`).waitFor({state:'visible'});
    };
    const capture=async(page,name,options={})=>{
      if(options.element)await options.element.screenshot({path:path.join(output,name)});
      else {if(options.at)await options.at.scrollIntoViewIfNeeded();else await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:path.join(output,name)});}
      screenshots.push(name);
    };
    const noOverflow=async(page,label)=>assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),label+' horizontal overflow');
    const firstTitle=page=>page.locator('#brief-feed .news-card-title').first();
    const titleText=page=>firstTitle(page).innerText().then(text=>text.replace(/\s*↗\s*$/,'').trim());
    const stamp=item=>item.date_precision==='future_unverified' || Date.parse(item.published_at)>Date.now() ? 0 : Date.parse(item.published_at)||0;
    const important=(a,b)=>(Number(a.editorial_rank)||999)-(Number(b.editorial_rank)||999);
    const stories=dataset.stories || dataset.articles;
    const latest=stories.slice().sort((a,b)=>stamp(b)-stamp(a)||important(a,b));
    const ranked=stories.slice().sort((a,b)=>important(a,b)||stamp(b)-stamp(a));
    const context=await makeContext({viewport:{width:1440,height:1000}});
    const page=await context.newPage();
    await page.goto(url);await ready(page);
    assert.equal(await page.locator('#news-filters').getAttribute('open'),null,'Home filters begin collapsed');
    assert.equal(await page.locator('[data-news-order="latest"]').getAttribute('aria-pressed'),'true');
    assert.equal(await titleText(page),latest[0].title);
    assert.match(await page.locator('#edition-date').innerText(),/Latest source/);
    assert.match(await page.locator('#edition-asof').innerText(),/Reviewed.*not live/);
    assert.match(await page.locator('#publication-banner').innerText(),/snapshot.*not live/i);
    if(dataset.publication.draft)assert.match(await page.locator('#publication-banner').innerText(),/approval pending/i);
    assert.match(await page.locator('#visit-summary').innerText(),/First visit/);
    assert.equal(await page.locator('#brief-feed details[open]').count(),0,'News details are collapsed');
    assert.equal(await page.locator('#brief-feed .article-body:visible').count(),0,'Long observations remain inside collapsed evidence');
    let box=await firstTitle(page).boundingBox();assert.ok(box && box.y>=0 && box.y+box.height<1000,'Desktop first news headline is on the first screen');
    await capture(page,'news-desktop.png');
    await page.locator('[data-news-order="important"]').click();
    assert.equal(await page.locator('[data-news-order="important"]').getAttribute('aria-pressed'),'true');
    assert.equal(await titleText(page),ranked[0].title);
    await page.locator('[data-news-order="latest"]').click();
    await page.locator('#news-search').fill(latest[0].url);
    assert.ok(await page.locator('#brief-feed .news-card').count()>0,'URL search finds a source');
    await page.locator('#news-search').fill('synthetic-no-matching-headline-qa');
    assert.match(await page.locator('#brief-feed').innerText(),/No news matches/);
    await page.locator('#news-search').fill('');
    await page.locator('#news-filters > summary').click();
    await page.locator('#news-lens').selectOption(latest[0].lens || 'other');
    assert.ok(await page.locator('#brief-feed .news-card').count()>0);
    await page.locator('#news-lens').selectOption('all');
    await page.locator('#news-filters > summary').click();
    await page.locator('#brief-feed .article-details > summary').first().click();
    assert.match(await page.locator('#brief-feed .article-details').first().innerText(),/Counterevidence/i);
    await page.locator('#brief-feed .article-details > summary').first().click();
    for(const id of ['refresh','lead-url','lead-note','review-filter'])assert.equal(await page.locator('#'+id).isDisabled(),true);
    assert.equal(await page.locator('#refresh').isVisible(),false);
    assert.equal(await page.locator('button[data-review]:visible').count(),0);
    await page.evaluate(()=>{
      document.querySelector('#refresh').dispatchEvent(new Event('click',{bubbles:true}));
      document.querySelector('#lead-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      document.querySelector('button[data-review]')?.dispatchEvent(new Event('click',{bubbles:true}));
    });
    await go(page,'explore');
    for(const section of ['financing','layers','earnings','sources','evidence'])assert.equal(await page.locator(`#panel-explore [data-nav="${section}"]`).isVisible(),true);
    await capture(page,'explore-desktop.png');
    await go(page,'evidence');
    assert.equal(await page.locator('#evidence-filters').getAttribute('open'),null);
    await page.locator('#search').fill(latest[0].title);
    assert.ok(await page.locator('#evidence-feed .article').count()>0);
    await page.locator('#search').fill('');
    await page.locator('#evidence-filters > summary').click();
    await page.locator('#role-filter').selectOption('primary');
    assert.equal(await page.locator('#evidence-feed .article').count(),Math.min(40,stories.filter(item=>item.source_role==='primary').length));
    await page.locator('#role-filter').selectOption('all');
    await page.locator('#evidence-filters > summary').click();
    for(const item of stories.filter(item=>item.quote_as_of || item.republished_at || item.report_period || item.event_date || item.event_start || item.highlights?.length)) {
      await page.locator('#search').fill(item.title);
      const details=page.locator('#evidence-feed .article-details').first();
      await details.locator(':scope > summary').click();
      const value=await details.innerText();
      if(item.quote_as_of)assert.match(value,/Market quote as of/i);
      if(item.republished_at)assert.match(value,/Republished/i);
      if(item.report_period)assert.ok(value.includes(item.report_period));
      if(item.event_date)assert.match(value,/Event date/i);
      if(item.event_start)assert.match(value,/Event starts/i);
      if(item.event_end)assert.match(value,/Event ends/i);
      if(item.reviewed_at)assert.match(value,/Item reviewed/i);
      if(item.highlights?.length) {
        assert.equal(await details.locator('.article-highlights li').count(),item.highlights.length);
        for(const highlight of item.highlights)assert.ok(value.includes(highlight.observation));
      }
      if(item.methodology_url)assert.equal(await details.getByRole('link',{name:/Probability methodology/}).getAttribute('href'),item.methodology_url);
    }
    await page.locator('#search').fill('');
    await go(page,'layers');assert.equal(await page.locator('.layer-card').count(),5);
    await page.locator('button[data-layer="energy"]').click();
    await page.locator('#panel-evidence').waitFor({state:'visible'});
    assert.equal(await page.locator('#layer-filter').inputValue(),'energy');
    await go(page,'earnings');assert.ok(await page.locator('#earnings-content').innerText());
    await go(page,'sources');assert.equal(await page.locator('#source-list .source-row').count(),dataset.sources.length);
    assert.match(await page.locator('#x-access').innerText(),/No X collection/);
    assert.match(await page.locator('#coverage-gaps').innerText(),/not.*live|not connected|not.*exhaustive/i);
    assert.equal(await page.locator('.nav [data-nav="explore"]').getAttribute('aria-current'),'page');
    await page.goBack();await page.locator('#panel-explore').waitFor({state:'visible'});
    await page.goForward();await page.locator('#panel-sources').waitFor({state:'visible'});
    await page.reload();await ready(page);await page.locator('#panel-sources').waitFor({state:'visible'});
    assert.match(await page.locator('#visit-summary').innerText(),/0 new stor.*0 material revision/i,'Same-snapshot reload is not new news');

    // Financing-specific selectors/route checks are defined below, using reviewed rows.
    await financingChecks({page,dataset,go,capture,noOverflow,url});
    for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
      await page.setViewportSize(viewport);
      for(const section of ['brief','explore','financing','layers','earnings','sources','evidence']) {
        await go(page,section);await noOverflow(page,`${section} ${viewport.width}`);
        if(section==='brief') {
          assert.equal(await page.locator('#edition-date').isVisible(),true,`${name} shows source freshness`);
          assert.match(await page.locator('#edition-date').innerText(),/Latest source/);
          assert.equal(await page.locator('#edition-asof').isVisible(),true,`${name} shows review freshness separately`);
          await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
          const titleBox=await firstTitle(page).boundingBox();
          assert.ok(titleBox && titleBox.y>=0 && titleBox.y+titleBox.height<viewport.height,`${name} first headline must be visible without scrolling`);
        }
        await capture(page,`${name}-${section}.png`);
      }
      if(name==='mobile')await financingChecks({page,dataset,go,capture,noOverflow,url,mobile:true});
    }
    const links=await page.locator('a[target="_blank"]').evaluateAll(nodes=>nodes.map(node=>({url:node.href,rel:node.rel})));
    assert.ok(links.every(link=>link.url.startsWith('https://')&&link.rel.includes('noopener')&&link.rel.includes('noreferrer')));
    const stored=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage)));
    const visitKey='pulse-news-visit-v1:/ai-news/';
    assert.deepEqual(Object.keys(stored),[visitKey]);
    assert.ok(!stored[visitKey].includes(dataset.articles[0].title),'Stored visit state excludes article text');
    assert.ok(!stored[visitKey].includes('https://'),'Stored visit state excludes source URLs');
    assert.equal(await page.evaluate(()=>sessionStorage.length),0);
    assert.deepEqual(await context.cookies(),[]);
    await go(page,'financing');
    assert.equal(await page.locator('#cds-guide').getAttribute('open'),null);
    await page.locator('#cds-guide > summary').click();
    await page.locator('#cds-spread').fill('1194.5');await page.locator('#cds-years').fill('5');await page.locator('#cds-recovery').fill('40');
    await page.getByRole('button',{name:'Calculate illustration'}).click();
    assert.match(await page.locator('#cds-output').innerText(),/63.0% over 5 years/);
    assert.match(await page.locator('#cds-output').innerText(),/18.1% over one year/);
    assert.match(await page.locator('#cds-output').innerText(),/risk-neutral illustration/i);
    await context.close();

    const edgeContext=await makeContext({viewport:{width:390,height:844}});
    const stale=clone(dataset);stale.publication.reviewed_at=new Date(Date.now()-10*86400000).toISOString();
    const stalePage=await edgeContext.newPage();
    await stalePage.route('**/data/dashboard.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(stale)}));
    await stalePage.goto(url);await ready(stalePage);assert.match(await stalePage.locator('#freshness').innerText(),/over 48 hours ago.*stale/);
    await stalePage.close();
    const empty=clone(dataset);empty.ledger=[];empty.layer_tracking={method:'Synthetic empty response for verification.',layers:[],scope:'Response-only fixture'};
    empty.articles=empty.articles.map(item=>({...item,ai_layers:[]}));empty.stories=clone(empty.articles);
    const emptyPage=await edgeContext.newPage();
    await emptyPage.route('**/data/dashboard.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(empty)}));
    await emptyPage.goto(url+'#financing');await ready(emptyPage);
    assert.match(await emptyPage.locator('#ledger-content').innerText(),/No sourced relationships/i);
    await go(emptyPage,'layers');assert.equal(await emptyPage.locator('.layer-card').count(),5);
    assert.ok((await emptyPage.locator('.layer-evidence strong').allTextContents()).every(value=>value==='—'));
    await emptyPage.locator('button[data-layer="energy"]').click();assert.match(await emptyPage.locator('#evidence-feed').innerText(),/No evidence matches/);
    await emptyPage.close();
    const unknown=clone(empty);unknown.ledger=[{id:'synthetic-unknown',instrument:'other',amount:null,currency:null,status:null,source_url:'javascript:window.unsafeQA=1',source_date:null,as_of:null}];
    const unknownPage=await edgeContext.newPage();
    await unknownPage.route('**/data/dashboard.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(unknown)}));
    await unknownPage.goto(url+'#financing');await ready(unknownPage);
    const unknownText=await unknownPage.locator('#ledger-content').innerText();
    for(const expected of ['Amount not stated','Stage unknown','Source entity unknown','Recipient unknown','Dated source unavailable','Overlap not assessed'])assert.ok(unknownText.includes(expected),expected);
    assert.equal(await unknownPage.locator('a[href^="javascript:"]').count(),0);
    await unknownPage.locator('.pf-inspect').click();await unknownPage.locator('.pf-dialog').waitFor({state:'visible'});
    assert.match(await unknownPage.locator('.pf-dialog').innerText(),/Unknown.*cash movement not established/i);
    assert.equal(await unknownPage.evaluate(()=>window.unsafeQA),undefined);
    await edgeContext.close();

    // Mutations are isolated response fixtures, never public data or database edits.
    const fixture=clone(dataset);fixture.articles=fixture.articles.slice(0,2);fixture.stories=clone(fixture.articles);fixture.brief.priority_items=clone(fixture.articles);
    let responseFixture=fixture;
    const visitContext=await makeContext({viewport:{width:390,height:844}});
    const visitPage=await visitContext.newPage();
    await visitPage.route('**/data/dashboard.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(responseFixture)}));
    const reload=async()=>{await visitPage.goto(url);await ready(visitPage);};
    const sync=()=>{responseFixture.stories=clone(responseFixture.articles);responseFixture.brief.priority_items=clone(responseFixture.articles);};
    await reload();assert.match(await visitPage.locator('#visit-summary').innerText(),/First visit/);
    await reload();assert.match(await visitPage.locator('#visit-summary').innerText(),/0 new stor.*0 material revision/);
    responseFixture=clone(responseFixture);
    responseFixture.publication.reviewed_at='2026-10-25T20:00:00Z';
    responseFixture.articles.forEach(item=>{item.published_at='2026-10-24T12:00:00Z';item.reviewed_at='2026-10-25T20:00:00Z';item.observed_at='2026-10-25T20:00:00Z';item.editorial_rank=99;});sync();
    await reload();assert.match(await visitPage.locator('#visit-summary').innerText(),/0 new stor.*0 material revision/,'Review/feed/date/rank changes alone do not count as material news');
    responseFixture.articles[0].observation+=' Synthetic QA material claim revision: contracted demand was cancelled.';sync();
    await reload();assert.match(await visitPage.locator('#visit-summary').innerText(),/0 new stor.*1 material revision/);
    await go(visitPage,'sources');await go(visitPage,'brief');assert.match(await visitPage.locator('#visit-summary').innerText(),/1 material revision/,'Navigation preserves this visit comparison');
    await reload();assert.match(await visitPage.locator('#visit-summary').innerText(),/0 new stor.*0 material revision/);
    const synthetic={...clone(responseFixture.articles[0]),id:'synthetic-qa-new-item',title:'Synthetic QA new item',url:'https://example.org/synthetic-qa-item',article_ids:['synthetic-qa-new-item'],published_at:'2026-10-25T20:00:00Z'};
    responseFixture.articles.push(synthetic);sync();
    await reload();assert.match(await visitPage.locator('#visit-summary').innerText(),/1 new story.*0 material revision/);
    await reload();assert.match(await visitPage.locator('#visit-summary').innerText(),/0 new stor.*0 material revision/);
    await visitContext.close();

    const hostile=clone(dataset);
    hostile.articles=[{...hostile.articles[0],id:'synthetic-hostile',title:'<img src=x onerror="window.unsafeQA=1">',summary:'<script>window.unsafeQA=1</script>',observation:'Synthetic untrusted text',url:'javascript:window.unsafeQA=1'}];
    hostile.stories=clone(hostile.articles);hostile.brief.priority_items=clone(hostile.articles);
    const hostileContext=await makeContext({viewport:{width:390,height:844}});
    const hostilePage=await hostileContext.newPage();
    await hostilePage.route('**/data/dashboard.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(hostile)}));
    await hostilePage.goto(url);await ready(hostilePage);
    assert.equal(await hostilePage.locator('#brief-feed img,#brief-feed script').count(),0);
    assert.equal(await hostilePage.locator('#brief-feed a[href^="javascript:"]').count(),0);
    assert.equal(await hostilePage.evaluate(()=>window.unsafeQA),undefined);
    await hostilePage.locator('#brief-feed .article-details > summary').first().click();
    assert.match(await hostilePage.locator('#brief-feed').innerText(),/<script>/);
    await noOverflow(hostilePage,'Hostile text mobile');
    await hostileContext.close();

    const blockedContext=await makeContext({viewport:{width:390,height:844}});
    await blockedContext.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Denied','SecurityError');}}));
    const blockedPage=await blockedContext.newPage();await blockedPage.goto(url);await ready(blockedPage);
    assert.match(await blockedPage.locator('#visit-summary').innerText(),/unavailable/i);
    assert.ok(await blockedPage.locator('#brief-feed .news-card').count()>0);
    await blockedContext.close();

    assert.deepEqual(errors,[],'No browser runtime errors');
    assert.deepEqual(external,[],'No external resource requests');
    assert.deepEqual(httpErrors,[],'Every asset resolves under the repository base path');
    assert.ok(requests.every(req=>req.method==='GET'&&req.path.startsWith('/ai-news/')&&!req.path.includes('/api/')),'Read-only static mode performs no writes/local API requests');
    const receipt={passed:true,checked_at:new Date().toISOString(),scope:'Local static artifact; isolated browser contexts; synthetic data response-only',articles:dataset.articles.length,sources:dataset.sources.length,relationships:dataset.ledger.length,desktop_mobile:true,first_screen_news:true,api_requests:0,external_requests:0,browser_errors:0,cookies:0,visit_history:'Stable IDs and fingerprints only; timestamp-only changes ignored; first/new/revised/reload/blocked storage checked',screenshots};
    fs.writeFileSync(path.join(output,'news-map-smoke.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify(receipt,null,2));
  } finally {
    if(browser)await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
}

async function graphReadability(page,label) {
  const issues=await page.locator('.pf-graph').evaluate(graph=>{
    const nodes=[...graph.querySelectorAll('.pf-node')].map(node=>({name:node.innerText,box:node.getBoundingClientRect()}));
    const labels=[...graph.querySelectorAll('.pf-edge-label')].map(node=>({name:node.getAttribute('aria-label'),box:node.getBoundingClientRect()}));
    const problems=[];
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++) {
      const a=nodes[i].box,b=nodes[j].box;
      const width=Math.min(a.right,b.right)-Math.max(a.left,b.left),height=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
      if(width>2 && height>2)problems.push('Company boxes overlap: '+nodes[i].name+' / '+nodes[j].name);
    }
    for(const edge of labels) {
      const x=(edge.box.left+edge.box.right)/2,y=(edge.box.top+edge.box.bottom)/2;
      for(const node of nodes)if(x>node.box.left+1 && x<node.box.right-1 && y>node.box.top+1 && y<node.box.bottom-1)problems.push('Relationship label hidden by '+node.name+': '+edge.name);
    }
    return problems;
  });
  assert.deepEqual(issues,[],label+' has readable company nodes and relationship targets');
}

async function financingChecks({page,dataset,go,capture,noOverflow,url,mobile=false}) {
  await go(page,'financing');
  const rows=dataset.ledger;
  assert.ok(rows.length>0);
  assert.equal(await page.locator('.pf-company-selector select').inputValue(),'','Default is the full network');
  assert.equal(await page.locator('.pf-recent-toggle input').isChecked(),false);
  assert.equal(await page.locator('.pf-relationship').count(),rows.length);
  assert.match(await page.locator('.pf-scope').innerText(),/seven calendar days.*not proof of a new transaction/i);
  assert.match(await page.locator('.pf-footnote').last().innerText(),/never totaled/);
  await noOverflow(page,'Financing overview');
  await capture(page,`finance-${mobile?'mobile':'desktop'}-overview.png`);
  const counts=new Map();for(const row of rows)for(const name of new Set([row.from_entity,row.to_entity]))counts.set(name,(counts.get(name)||0)+1);
  const company=[...counts].sort((a,b)=>b[1]-a[1])[0][0];
  if(!mobile) {
    await capture(page,'finance-desktop-full-graph.png',{element:page.locator('.pf-graph')});
    await graphReadability(page,'Full network');
    const hits=page.locator('.pf-edge-hit');
    assert.equal(await hits.count(),rows.length,'Each overview relationship has a tappable arrow and accessible list equivalent');
    let hitPoint=null;
    for(let index=0;index<Math.min(10,await hits.count()) && !hitPoint;index++) {
      const hit=hits.nth(index);await hit.scrollIntoViewIfNeeded();
      hitPoint=await hit.evaluate(node=>{
        const length=node.getTotalLength(),matrix=node.getScreenCTM();
        for(const part of [.5,.35,.65,.2,.8]) {
          const point=node.getPointAtLength(length*part).matrixTransform(matrix);
          if(point.x<0 || point.x>=innerWidth || point.y<0 || point.y>=innerHeight)continue;
          if(document.elementFromPoint(point.x,point.y)===node)return {x:point.x,y:point.y};
        }
        return null;
      });
    }
    assert.ok(hitPoint,'An overview arrow is reachable by pointer');
    await page.mouse.click(hitPoint.x,hitPoint.y);await page.locator('dialog.pf-dialog').waitFor({state:'visible'});
    assert.ok(page.url().includes('#financing/relationship/'));
    await page.keyboard.press('Escape');await page.locator('dialog.pf-dialog').waitFor({state:'hidden'});
  }
  const expected=rows.filter(item=>item.from_entity===company || item.to_entity===company);
  if(mobile) {
    assert.equal(await page.locator('.pf-graph').isVisible(),false,'Mobile does not require pinching a tiny map');
    const tile=page.locator('.pf-company-tile').filter({has:page.locator('strong',{hasText:company})}).first();
    assert.equal(await tile.isVisible(),true);await tile.click();
  } else {
    assert.equal(await page.locator('.pf-graph').isVisible(),true);
    const node=page.locator('.pf-node').filter({has:page.locator('strong',{hasText:company})}).first();
    await node.focus();await page.keyboard.press('Enter');
  }
  await page.waitForFunction(value=>document.querySelector('.pf-company-selector select')?.value===value,company);
  assert.equal(await page.locator('.pf-relationship').count(),expected.length);
  assert.ok(page.url().includes('#financing/company/'));
  await page.reload();await page.locator('#dashboard').waitFor({state:'visible'});
  assert.equal(await page.locator('.pf-company-selector select').inputValue(),company,'Company route survives reload');
  assert.equal(await page.locator('.pf-relationship').count(),expected.length);
  if(mobile)await capture(page,'finance-mobile-focused-list.png',{at:page.locator('.pf-list-heading')});
  else {await capture(page,'finance-desktop-focused-graph.png',{element:page.locator('.pf-graph')});await graphReadability(page,'Focused network');}
  const card=page.locator('.pf-relationship').first();
  const rowId=await card.getAttribute('data-relationship-id');
  const relation=rows.find(item=>item.id===rowId);
  assert.ok(relation);
  const sourceLink=card.getByRole('link',{name:'Read the source ↗'});
  assert.equal(await sourceLink.getAttribute('href'),relation.source_url);
  await card.locator('.pf-inspect').focus();await page.keyboard.press('Enter');
  await page.locator('dialog.pf-dialog').waitFor({state:'visible'});
  assert.ok(page.url().includes('#financing/relationship/'));
  const dialog=page.locator('dialog.pf-dialog');
  assert.match(await dialog.innerText(),/Cash status/);
  assert.match(await dialog.innerText(),/Revenue status/);
  assert.match(await dialog.innerText(),/Source date/);
  assert.match(await dialog.innerText(),/Uncertainty \/ risk/);
  assert.ok((await dialog.innerText()).includes(relation.from_entity));
  assert.ok((await dialog.innerText()).includes(relation.to_entity));
  assert.equal(await dialog.getByRole('link',{name:'Read the source ↗'}).getAttribute('href'),relation.source_url);
  assert.equal(await page.evaluate(()=>document.activeElement.classList.contains('pf-close')),true,'Dialog opens with a keyboard focus target');
  const detailFile=`finance-${mobile?'mobile':'desktop'}-detail.png`;
  await capture(page,detailFile);
  await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
  assert.equal(await page.locator('.pf-company-selector select').inputValue(),company);
  assert.equal(await page.evaluate(()=>document.activeElement.classList.contains('pf-inspect')),true,'Escape returns focus to the invoking relationship');
  await page.locator('.pf-relationship .pf-inspect').first().click();
  await page.locator('dialog.pf-dialog').waitFor({state:'visible'});
  await page.goBack();await page.locator('dialog.pf-dialog').waitFor({state:'hidden'});
  await page.goForward();await page.locator('dialog.pf-dialog').waitFor({state:'visible'});
  await page.reload();await page.locator('#dashboard').waitFor({state:'visible'});await page.locator('dialog.pf-dialog').waitFor({state:'visible'});
  await page.locator('.pf-close').click();await page.locator('dialog.pf-dialog').waitFor({state:'hidden'});
  assert.equal(await page.locator('.pf-company-selector select').inputValue(),company,'Closing a deep-linked dialog preserves the company view');
  await page.locator('.pf-reset').click();
  await page.waitForFunction(()=>document.querySelector('.pf-company-selector select')?.value==='');
  assert.equal(await page.locator('.pf-relationship').count(),rows.length);
  await page.locator('.pf-recent-toggle input').check();
  const end=Date.parse(String(dataset.publication.reviewed_at).slice(0,10));
  const recent=rows.filter(item=>{const source=Date.parse(String(item.source_date).slice(0,10));return Number.isFinite(source)&&end-source>=0&&end-source<7*86400000;});
  await page.waitForFunction(count=>document.querySelectorAll('.pf-relationship').length===count,recent.length);
  assert.ok(page.url().includes('recent=1'));
  await page.reload();await page.locator('#dashboard').waitFor({state:'visible'});
  assert.equal(await page.locator('.pf-recent-toggle input').isChecked(),true,'Recent filter survives reload');
  assert.equal(await page.locator('.pf-relationship').count(),recent.length);
  await page.locator('.pf-reset').click();
  assert.equal(await page.locator('.pf-recent-toggle input').isChecked(),false);
  await noOverflow(page,'Financing selected/reset');
}

main().catch(error=>{console.error(error);process.exitCode=1;});
