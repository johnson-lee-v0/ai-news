/* Optional offline UI smoke test: node tests/ui_smoke.cjs
 * Requires an existing Playwright + Chromium installation; never downloads them.
 * Set PLAYWRIGHT_MODULE or PYTHON when those runtimes are not on the usual paths.
 * All data is synthetic and temporary. No screenshots or logs are saved in the repo.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');

async function main() {
  let chromium;
  try { ({chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright')); }
  catch (_) { throw new Error('Optional UI test requires an installed Playwright module. Set PLAYWRIGHT_MODULE to its module path. Nothing was downloaded.'); }
  const root = path.resolve(__dirname, '..');
  const helper = path.join(__dirname, 'fixtures', 'ui_fixture.py');
  const python = process.env.PYTHON || 'python3';
  const env = {...process.env, PYTHONDONTWRITEBYTECODE:'1'};
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-news-ui-'));
  fs.writeFileSync(path.join(tmp, '.ui-smoke-only'), 'synthetic-ui-test');
  const server = spawn(python, [helper, 'serve', tmp], {cwd:root, env, stdio:['ignore','pipe','pipe']});
  let browser;
  let stderr = '';
  server.stderr.on('data', value => {stderr += value;});
  try {
    const url = await new Promise((resolve, reject) => {
      let stdout = '';
      const timeout = setTimeout(() => reject(new Error(`Test server startup timed out: ${stderr}`)), 10000);
      server.stdout.on('data', value => {
        stdout += value;
        const match = stdout.match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) { clearTimeout(timeout); resolve(match[0]); }
      });
      server.once('error', error => {clearTimeout(timeout); reject(error);});
      server.once('exit', code => {clearTimeout(timeout); reject(new Error(`Test server exited ${code}: ${stderr}`));});
    });
    browser = await chromium.launch({headless:true});
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    const external = [], errors = [], reviewRequests = [];
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin !== url) {external.push(route.request().url()); return route.abort();}
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if(request.url() === `${url}/api/review`) reviewRequests.push(request.postDataJSON());});
    let navigation = 0;
    const load = async (section='brief') => {
      await page.goto(`${url}/?test=${++navigation}#${section}`);
      await page.locator('#dashboard').waitFor({state:'visible'});
      if(section==='evidence')await page.locator('#evidence-filters > summary').click();
    };
    const data = async () => (await context.request.get(`${url}/api/dashboard`)).json();
    await load();
    assert.match(await page.locator('#brief-feed').innerText(), /No news matches|No evidence has been collected/);
    assert.equal(await page.locator('#stat-total').textContent(), '0');
    await load('sources');
    assert.equal(await page.locator('.source-row').count(), 3);
    assert.match(await page.locator('#source-list').innerText(), /Not fetched/);
    assert.match(await page.locator('#x-access').innerText(), /not verified|not connected/i);

    const seeded = spawnSync(python, [helper, 'seed', tmp], {cwd:root, env, encoding:'utf8'});
    assert.equal(seeded.status, 0, seeded.stderr || String(seeded.error || 'Fixture seeding failed'));
    await load('evidence');
    const baseline = await data();
    assert.equal(baseline.articles.length, 4);
    assert.equal(baseline.stories.length, 3);
    assert.equal(await page.locator('#evidence-feed .article').count(), 3);
    assert.match(await page.locator('#filter-count').innerText(), /4 loaded source items of 4 retained/);
    for (const role of ['primary','secondary','discovery']) {
      await page.locator('#role-filter').selectOption(role);
      assert.equal(await page.locator('#evidence-feed .article').count(), 1);
      assert.equal(await page.locator(`#evidence-feed .source-${role}`).count(), 1);
    }
    assert.match(await page.locator('#evidence-feed').innerText(), /Search feed date/);
    await page.locator('#evidence-feed .article-details > summary').first().click();
    assert.match(await page.locator('#evidence-feed').innerText(), /original publication date/);
    await page.locator('#role-filter').selectOption('all');
    await page.locator('#entity-filter').selectOption('Synthetic Finance');
    assert.equal(await page.locator('#evidence-feed .article').count(), 1);
    await page.locator('#entity-filter').selectOption('all');
    await page.locator('#lens-filter').selectOption('capacity');
    assert.equal(await page.locator('#evidence-feed .article').count(), 1);
    await page.locator('#lens-filter').selectOption('all');
    await page.locator('#relevance-filter').selectOption('material');
    assert.equal(await page.locator('#evidence-feed .article').count(), 3);
    await page.locator('#relevance-filter').selectOption('all');
    await page.locator('#search').fill('no-matching-synthetic-item');
    assert.match(await page.locator('#evidence-feed').innerText(), /No evidence matches/);
    await page.locator('#search').fill('');

    const group = baseline.stories.find(item => item.article_ids.length === 2);
    assert.ok(group, 'Synthetic repeated headline should form one reading group');
    const button = status => page.locator(`#evidence-feed button[data-article-id="${group.id}"][data-review="${status}"]`);
    async function review(status, message) {
      const details=button(status).locator('xpath=ancestor::details[1]');
      if(await details.getAttribute('open')===null)await details.locator(':scope > summary').click();
      const responsePromise = page.waitForResponse(response => response.url() === `${url}/api/review`);
      await button(status).click();
      const response = await responsePromise;
      assert.equal(response.status(), 200);
      assert.equal((await response.json()).count, 2);
      assert.deepEqual(reviewRequests[reviewRequests.length-1].article_ids.slice().sort(), group.article_ids.slice().sort());
      await page.waitForFunction(value => document.querySelector('#notification').textContent.includes(value), message);
      const saved = await data();
      assert.ok(saved.articles.filter(item => group.article_ids.includes(item.id)).every(item => item.review_status === status));
    }
    await review('reviewed', 'Marked read');
    await page.locator('#review-filter').selectOption('reviewed');
    assert.equal(await page.locator('#evidence-feed .article').count(), 1);
    await review('dismissed', 'Dismissed from');
    await page.locator('#review-filter').selectOption('active');
    assert.equal(await page.locator('#evidence-feed .article').count(), 2);
    await page.locator('#review-filter').selectOption('dismissed');
    assert.equal(await page.locator('#evidence-feed .article').count(), 1);
    await review('unreviewed', 'Returned to the unread');
    await page.locator('#review-filter').selectOption('active');
    assert.equal(await page.locator('#evidence-feed .article').count(), 3);

    await load('sources');
    assert.match(await page.locator('#source-list').innerText(), /Fetch failed/);
    assert.match(await page.locator('#source-list').innerText(), /<script>/);
    assert.equal(await page.evaluate(() => window.testInjection), undefined);
    await page.locator('#lead-url').fill('https://x.com/synthetic_test/status/123456789');
    await page.locator('#lead-note').fill('<script>window.testInjection=true</script> Synthetic local test only.');
    await page.getByRole('button', {name:/Save unverified lead/}).click();
    await page.waitForFunction(() => document.querySelector('#lead-message').textContent.startsWith('Saved locally'));
    assert.equal(await page.locator('.lead-item').count(), 1);
    assert.match(await page.locator('.lead-item').innerText(), /<script>/);
    assert.equal(await page.evaluate(() => window.testInjection), undefined);
    await page.locator('#lead-url').fill('https://twitter.com/synthetic_test/status/123456789?test=1');
    await page.getByRole('button', {name:/Save unverified lead/}).click();
    await page.waitForFunction(() => document.querySelector('#lead-message').textContent.includes('already saved'));
    assert.equal(await page.locator('.lead-item').count(), 1);
    await page.getByRole('button', {name:'Refresh sources'}).click();
    await page.waitForFunction(() => document.querySelector('#notification').textContent.includes('Synthetic offline failure'));
    assert.equal(await page.locator('#refresh').isEnabled(), true);
    assert.equal(await page.locator('#stat-total').textContent(), '4');

    for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
      await page.setViewportSize(viewport);
      for (const section of ['brief','explore','evidence','layers','financing','earnings','sources']) {
        await load(section);
        const width = await page.evaluate(() => document.documentElement.scrollWidth);
        assert.ok(width <= viewport.width, `${section} overflows at ${viewport.width}px`);
      }
    }
    await load('layers');
    assert.equal(await page.locator('.layer-card').count(),5);
    assert.match(await page.locator('#panel-layers').innerText(),/Unavailable/);
    const tracked=(await data()).layer_tracking.layers.find(layer=>layer.article_count>0);
    assert.ok(tracked,'Synthetic evidence should map to a layer');
    await page.locator(`button[data-layer="${tracked.id}"]`).click();
    await page.locator('#panel-evidence').waitFor({state:'visible'});
    assert.equal(await page.locator('#layer-filter').inputValue(),tracked.id);
    const anchors = await page.locator('a[target="_blank"]').evaluateAll(nodes => nodes.map(node => ({href:node.href,rel:node.rel})));
    assert.ok(anchors.every(a => a.href.startsWith('https://') && a.rel.includes('noopener')));
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log('PASS: offline synthetic UI smoke — empty states, filters, grouped read/dismiss/reset, escaped/deduplicated leads, failed refresh, desktop/mobile, no JS errors or external requests.');
  } finally {
    if (browser) await browser.close();
    if (server.exitCode === null && server.pid) {
      const exited = new Promise(resolve => server.once('exit', resolve));
      server.kill('SIGTERM');
      await exited;
    }
    fs.rmSync(tmp, {recursive:true,force:true});
  }
}
main().catch(error => {console.error(error.stack || error.message); process.exitCode = 1;});
