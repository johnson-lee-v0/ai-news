/* Optional populated-post regression. Uses a fresh browser, never a personal profile. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),site=path.join(root,'_site'),out=path.resolve(process.env.EMBED_OUT||path.join(root,'../embed-fix-20261104/qa'));
assert.ok(path.relative(root,out).startsWith('..'+path.sep),'Evidence stays outside publication');
const real=process.env.EMBED_REAL==='1',manifest=JSON.parse(fs.readFileSync(path.join(site,'build.json')));
(async()=>{let server,browser,base=process.env.VERIFY_BASE;const checks=[],errors=[];try{
fs.mkdirSync(out,{recursive:true});
if(!base){const allowed=new Set(['build.json',...Object.keys(manifest.files)]);server=http.createServer((req,res)=>{const name=new URL(req.url,'http://localhost').pathname.replace(/^\/ai-news\//,'')||'index.html';if(!allowed.has(name)){res.writeHead(404);res.end();return;}res.writeHead(200,{'Content-Type':{'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml'}[path.extname(name)]||'text/plain'});res.end(fs.readFileSync(path.join(site,name)));});await new Promise(r=>server.listen(0,'127.0.0.1',r));base=`http://127.0.0.1:${server.address().port}/ai-news/`;}
browser=await chromium.launch({headless:true});
for(const width of [320,390,1440])for(const section of ['sports','markets']){
 const context=await browser.newContext({viewport:{width,height:width<500?844:1000}}),external=[];
 let consent=false;context.on('request',r=>{if(!r.url().startsWith(base)&&/^https?:/.test(r.url()))external.push({host:new URL(r.url()).hostname,beforeConsent:!consent});});
 if(!real)await context.route('**/*',r=>r.request().url().startsWith(base)?r.continue():r.abort());
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(base+(section==='sports'?'#sports':'#brief'));await page.locator('#dashboard').waitFor();
 const data=await (await context.request.get(base+'data/dashboard.json')).json();assert.equal(data.publication.commit,manifest.commit);
 const expected=data.personal_wall.items.filter(i=>i.section===section&&i.format==='instagram');assert.ok(expected.length,'Populated real post is required in both sections');
 const prefix=section==='sports'?'sports':'news',feed=page.locator(section==='sports'?'#sports-feed':'#brief-feed');
 const shortcut=page.locator(`#wall-formats-${section} [data-wall-format="instagram"]`);assert.equal(await shortcut.isEnabled(),true);assert.match(await shortcut.innerText(),new RegExp(String(expected.length)));
 const box=await shortcut.boundingBox();assert.ok(box.y<844,'Shortcut is on the first mobile screen');assert.equal(await page.locator('iframe').count(),0);assert.equal(external.length,0);
 await page.screenshot({path:path.join(out,`${section}-${width}-before.png`)});
 // Conflicting filters must not hide posts after using the explicit shortcut.
 await page.locator(`#${prefix}-search`).fill('no-match-filter-regression');assert.equal(await feed.locator('article').count(),0);
 consent=true;await shortcut.click();assert.equal(await page.locator(`#${prefix}-search`).inputValue(),'');assert.equal(await page.locator(`#${prefix}-format`).inputValue(),'instagram');assert.equal(await feed.locator('.wall-card').count(),expected.length);
 assert.equal(await feed.locator('iframe').count(),Math.min(3,expected.length));assert.equal(external.filter(r=>r.beforeConsent).length,0);
 const card=feed.locator(`[data-wall-id="${expected[0].id}"]`),iframe=card.locator('iframe');assert.equal(await iframe.getAttribute('src'),expected[0].url+'embed/');
 let actualPost=null;
 if(real){await iframe.scrollIntoViewIfNeeded();const frame=await (await iframe.elementHandle()).contentFrame();await frame.waitForLoadState('domcontentloaded');await frame.waitForFunction(()=>[...document.images].some(i=>i.complete&&i.naturalWidth>200&&i.getBoundingClientRect().width>200),{timeout:15000});actualPost=await frame.evaluate(()=>({authorVisible:document.body.innerText.includes(location.pathname.includes('DfSv5lriAen')?'f1':'thewallstreetskinny'),largeImages:[...document.images].filter(i=>i.complete&&i.naturalWidth>200&&i.getBoundingClientRect().width>200).length}));assert.ok(actualPost.authorVisible&&actualPost.largeImages>0,'A genuine public post must render, not just an HTTP200 player');await page.waitForTimeout(1500);}
 assert.ok(await card.locator('a[target="_blank"]').count());assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await card.screenshot({path:path.join(out,`${section}-${width}-post.png`)});
 await card.locator('[data-wall-hide]').click();assert.equal(await shortcut.isDisabled(),true,'Hidden post is not re-exposed by shortcut');
 await page.locator(`#wall-controls-${section} .wall-hidden>summary`).click();await page.locator(`#wall-controls-${section} [data-wall-restore]`).click();await page.locator(`#wall-controls-${section} .wall-settings>summary`).click();assert.equal(await shortcut.isEnabled(),true);assert.equal(await feed.locator('iframe').count(),0,'Restoring does not load a third-party frame');
 const source=expected[0].source_id;await page.locator(`#wall-controls-${section} [data-wall-source="${source}"]`).selectOption('mute');assert.equal(await shortcut.isDisabled(),true);await page.locator(`#wall-controls-${section} [data-wall-reset]`).click();
 await page.locator(`#wall-formats-${section} [data-wall-format="all"]`).click();assert.equal(await page.locator(`#${prefix}-format`).inputValue(),'all');assert.equal(await page.locator('iframe').count(),0);
 checks.push({section,width,commit:data.publication.commit,populatedPosts:expected.length,firstScreenShortcut:true,oneTapInlinePost:true,conflictingFiltersCleared:true,hideMuteRespected:true,noUnsolicitedRequests:true,originalFallback:true,actualPost});await context.close();
}
assert.deepEqual(errors,[]);const receipt={passed:true,checked_at:new Date().toISOString(),commit:manifest.commit,real_public_media:real,checks,browser_errors:errors};fs.writeFileSync(path.join(out,'embed-discovery.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
}finally{await browser?.close();if(server)await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
