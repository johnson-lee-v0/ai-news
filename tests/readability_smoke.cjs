/* Optional isolated browser regression for complete implications and takeaways.
 * Build _site first. Uses an existing Playwright/Chromium runtime, no installation.
 * Set PLAYWRIGHT_MODULE, PAGES_SCREENSHOT_DIR (outside this repository), and
 * optionally VERIFY_BASE to compare a live deployment with the exact local build.
 * Synthetic responses are in memory only. No source browsing or publishing.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const crypto = require('node:crypto');
const compact = value => String(value).replace(/\s+/g, ' ').trim();
const hash = value => crypto.createHash('sha256').update(value).digest('hex');

async function readable(locator, expected, label) {
  assert.equal(compact(await locator.innerText()), compact('Why it matters: ' + expected), label + ' retains every sentence');
  const state = await locator.evaluate(element => {
    const style = getComputedStyle(element);
    const range = document.createRange(); range.selectNodeContents(element);
    const box = element.getBoundingClientRect();
    const rects = [...range.getClientRects()];
    return {
      whitespace: style.whiteSpace, overflow: style.overflow, ellipsis: style.textOverflow,
      clamp: style.webkitLineClamp, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
      scrollHeight: element.scrollHeight, clientHeight: element.clientHeight,
      textOutside: rects.some(rect => rect.right > box.right + 2 || rect.left < box.left - 2 || rect.bottom > box.bottom + 2),
    };
  });
  assert.notEqual(state.whitespace, 'nowrap', label + ' wraps');
  assert.notEqual(state.ellipsis, 'ellipsis', label + ' has no ellipsis');
  assert.ok(!state.clamp || ['none', '0'].includes(state.clamp), label + ' has no line clamp');
  assert.ok(state.scrollWidth <= state.clientWidth + 1, label + ' has no horizontal clipping');
  assert.ok(state.scrollHeight <= state.clientHeight + 1, label + ' has no vertical clipping');
  assert.equal(state.textOutside, false, label + ' text stays within its paragraph');
}

async function main() {
  const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const root = path.resolve(__dirname, '..');
  const site = path.resolve(process.env.PAGES_SITE_DIR || path.join(root, '_site'));
  const output = process.env.PAGES_SCREENSHOT_DIR ? path.resolve(process.env.PAGES_SCREENSHOT_DIR) : fs.mkdtempSync(path.join(os.tmpdir(), 'pulse-readability-'));
  const outside = file => {const rel = path.relative(root, file); return rel.startsWith('..' + path.sep) || path.isAbsolute(rel);};
  assert.ok(outside(output), 'Evidence must remain outside the repository');
  fs.mkdirSync(output, {recursive: true});
  assert.ok(outside(fs.realpathSync(output)), 'Evidence cannot resolve into the repository');
  const manifest = JSON.parse(fs.readFileSync(path.join(site, 'build.json')));
  const dataset = JSON.parse(fs.readFileSync(path.join(site, 'data/dashboard.json')));
  assert.equal(dataset.publication.mode, 'static');
  const rows = dataset.stories || dataset.articles;
  assert.ok(rows.length > 0 && rows.length <= 24, 'Small populated public snapshot');
  const assets = new Set(['build.json', ...Object.keys(manifest.files)]);
  for (const file of assets) assert.ok(!path.isAbsolute(file) && !file.split('/').includes('..'), 'Safe artifact paths');
  const mime = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml'};
  let server, browser, base;
  const errors = [], requests = [], forbidden = [], responseErrors = [], screenshots = [];
  try {
    if (process.env.VERIFY_BASE) {
      base = new URL(process.env.VERIFY_BASE);
      assert.equal(base.protocol, 'https:', 'Remote verification requires HTTPS');
      assert.match(manifest.commit, /^[0-9a-f]{40}$/, 'Live verification requires an exact committed artifact');
    } else {
      server = http.createServer((req, res) => {
        const url = new URL(req.url, 'http://localhost');
        const file = url.pathname.startsWith('/ai-news/') ? url.pathname.slice('/ai-news/'.length) || 'index.html' : '';
        if (req.method !== 'GET' || !assets.has(file)) {res.writeHead(404);res.end();return;}
        res.writeHead(200, {'Content-Type':mime[path.extname(file)] || 'text/plain', 'Cache-Control':'no-store'});
        res.end(fs.readFileSync(path.join(site, file)));
      });
      await new Promise((resolve, reject) => {server.once('error', reject);server.listen(0, '127.0.0.1', resolve);});
      base = new URL(`http://127.0.0.1:${server.address().port}/ai-news/`);
    }
    browser = await chromium.launch({headless:true});
    const contextFor = async width => {
      const context = await browser.newContext({viewport:{width, height:width >= 1000 ? 1000 : 844}});
      await context.route('**/*', route => {
        const req = route.request(), target = new URL(req.url());
        if (req.method() !== 'GET' || target.origin !== base.origin || !target.pathname.startsWith(base.pathname) || target.pathname.includes('/api/')) {
          forbidden.push({method:req.method(), url:req.url()});return route.abort();
        }
        return route.continue();
      });
      context.on('page', page => {
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', req => requests.push({method:req.method(), url:req.url()}));
        page.on('response', response => {if(response.status() >= 400)responseErrors.push(response.status() + ':' + response.url());});
      });
      return context;
    };
    const ready = page => page.locator('#dashboard').waitFor({state:'visible'});
    const noOverflow = async (page, label) => assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), label + ' has no page overflow');
    const capture = async (page, name) => {await page.screenshot({path:path.join(output, name)});screenshots.push(name);};
    const go = async (page, section) => {
      if (['brief','explore'].includes(section)) await page.locator(`.nav [data-nav="${section}"]`).click();
      else {await page.locator('.nav [data-nav="explore"]').click();await page.locator(`#panel-explore [data-nav="${section}"]`).click();}
      await page.locator(`#panel-${section}`).waitFor({state:'visible'});
    };
    const checkedAssets = {};
    const fetchContext = await contextFor(1440);
    for (const file of assets) {
      if (file === '.nojekyll') continue;
      const response = await fetchContext.request.get(new URL(file, base).href);
      assert.equal(response.status(), 200, file + ' resolves at repository base path');
      const actualHash = hash(await response.body());
      assert.equal(actualHash, hash(fs.readFileSync(path.join(site, file))), file + ' matches exact build');
      checkedAssets[file] = actualHash;
    }
    await fetchContext.close();

    for (const width of [320, 390, 1440]) {
      const context = await contextFor(width);
      const page = await context.newPage();
      await page.goto(base.href);await ready(page);
      assert.equal(await page.locator('#brief-feed details[open]').count(), 0, 'Details start collapsed');
      const cards = page.locator('#brief-feed .news-card');
      assert.equal(await cards.count(), rows.length);
      for (let index = 0; index < rows.length; index++) {
        const card = cards.nth(index);
        const url = await card.locator('.news-card-title a').getAttribute('href');
        const row = rows.find(item => item.url === url);
        assert.ok(row, 'Each card retains a reviewed source');
        await readable(card.locator('.news-card-implication'), row.implication, width + 'px/' + row.id);
        assert.equal(await card.locator('.news-card-implication').evaluate(el => Boolean(el.closest('details'))), false, 'Implication is outside disclosure');
        const details = card.locator('.article-details');
        assert.ok(!(await details.textContent()).includes(row.implication), 'Complete implication is not duplicated inside details: ' + row.id);
      }
      await noOverflow(page, width + 'px news');
      await capture(page, `news-${width}.png`);
      const first = rows[0];
      await page.locator('#news-search').fill(first.title);
      assert.equal(await page.locator('#brief-feed .news-card').count(), 1, 'Search still resolves a known story');
      await page.locator('#brief-feed .article-details > summary').click();
      const detail = page.locator('#brief-feed .article-details');
      assert.ok((await detail.innerText()).includes(first.counterevidence), 'Counterevidence retained');
      assert.ok((await detail.innerText()).includes(first.uncertainty), 'Uncertainty retained');
      if (first.highlights?.length) assert.match(await detail.innerText(), /Key takeaways/i);
      assert.ok((await detail.innerText()).includes(first.observation), 'Observation retained');
      await noOverflow(page, width + 'px expanded evidence');
      await page.locator('#news-search').fill('');
      await page.locator('#news-filters > summary').click();
      const layer = dataset.layer_tracking.layers.find(item => item.article_count > 0);
      await page.locator('#news-layer').selectOption(layer.id);
      assert.equal(await page.locator('#brief-feed .news-card').count(), rows.filter(item => item.ai_layers.includes(layer.id)).length, 'Layer filter retains expected stories');
      await page.locator('#news-layer').selectOption('all');
      await page.locator('#news-filters > summary').click();
      await go(page, 'layers');
      for (const item of dataset.layer_tracking.layers) {
        assert.ok(item.takeaway && !item.takeaway.includes('?'), 'Layer has a substantive declarative takeaway');
        const actual = page.locator(`[data-layer-card="${item.id}"] .layer-takeaway`);
        assert.ok((await actual.innerText()).includes(item.takeaway), 'Layer takeaway displayed in full');
      }
      assert.equal(await page.getByText('What would change the view?', {exact:true}).count(), 0);
      await noOverflow(page, width + 'px layers');
      await page.evaluate(() => scrollTo(0,0));await capture(page, `layers-${width}.png`);
      await page.goBack();await page.locator('#panel-explore').waitFor({state:'visible'});
      await page.goForward();await page.locator('#panel-layers').waitFor({state:'visible'});
      await page.reload();await ready(page);await page.locator('#panel-layers').waitFor({state:'visible'});
      await go(page, 'earnings');
      const sourceLinks = page.locator('#earnings-content tbody tr td:last-child a');
      assert.equal(await sourceLinks.count(), dataset.earnings.length, 'Every earnings comparison retains its evidence link');
      assert.deepEqual(await sourceLinks.allTextContents(), dataset.earnings.map(() => 'Source ↗'), 'Neutral evidence labels do not misidentify third-party transcripts as company sources');
      assert.deepEqual(await sourceLinks.evaluateAll(links => links.map(link => link.href)), dataset.earnings.map(row => row.source_url), 'Earnings links preserve exact source attribution');
      await go(page, 'brief');
      await page.reload();await ready(page);
      assert.match(await page.locator('#visit-summary').innerText(), /0 new stor.*0 material revision/);
      assert.equal(await page.locator('#brief-feed details[open]').count(), 0);
      await context.close();
    }

    // Synthetic test-only response catches first-sentence truncation and long-token overflow.
    const synthetic = JSON.parse(JSON.stringify(dataset));
    const example = {...rows[0], id:'synthetic-readability-only', title:'Synthetic complete implication test', url:'https://example.org/readability-test',
      implication:'A disclosed factory expansion can support equipment demand when customers accept deliveries and pay the supplier on time.\nThe second sentence is essential: financing commitments do not establish realized revenue, energized capacity, sustained utilization or durable returns, and this caveat must remain visible without expanding anything. ' + 'LongUnbrokenSyntheticToken'.repeat(12),
      observation:'Synthetic observation for the isolated browser test only.', article_ids:['synthetic-readability-only'],
      highlights:[{title:'Synthetic source classification',observation:'Synthetic claim for layout verification.',implication:'Synthetic interpretation, not public research.',claim_type:'Management statement reproduced in a third-party transcript; interpretation is conditional analysis with explicit uncertainty',source_url:'https://example.org/readability-test',source_date:'2026-10-25'}]};
    synthetic.articles=[example];synthetic.stories=[example];synthetic.notes=[];synthetic.brief.priority_items=[example];
    assert.ok(example.implication.length > 230);
    for (const width of [320,390,1440]) {
      const context = await contextFor(width), page = await context.newPage();
      await page.route('**/data/dashboard.json', route => route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(synthetic)}));
      await page.goto(base.href);await ready(page);
      assert.equal(await page.locator('#brief-feed details[open]').count(), 0);
      await readable(page.locator('#brief-feed .news-card-implication'), example.implication, 'Synthetic ' + width + 'px');
      await noOverflow(page, 'Synthetic ' + width + 'px');
      if (width === 390) await capture(page, 'synthetic-complete-390.png');
      await page.locator('#brief-feed .article-details > summary').click();
      const classification = page.locator('#brief-feed .highlight-heading .badge');
      assert.equal(await classification.textContent(), example.highlights[0].claim_type, 'Complete source classification retained');
      assert.ok(await classification.evaluate(element => {
        const box = element.getBoundingClientRect(), parent = element.parentElement.getBoundingClientRect();
        return box.right <= parent.right + 1 && box.left >= parent.left - 1 && element.scrollWidth <= element.clientWidth + 1;
      }), 'Long source classification stays readable within the card at ' + width + 'px');
      await noOverflow(page, 'Expanded synthetic ' + width + 'px');
      await context.close();
    }
    assert.deepEqual(errors, [], 'No runtime errors');
    assert.deepEqual(forbidden, [], 'No external requests, writes or local API calls');
    assert.deepEqual(responseErrors, [], 'No failed assets');
    const receipt = {passed:true,checked_at:new Date().toISOString(),commit:manifest.commit,scope:process.env.VERIFY_BASE ? 'Exact live public artifact plus isolated synthetic response tests' : 'Local static artifact plus isolated synthetic response tests',articles:rows.length,viewports:[320,390,1440],complete_implications:true,no_duplicate_detail_implication:true,declarative_takeaways:true,search_filter_back_reload:true,source_counterevidence_uncertainty_preserved:true,browser_errors:errors.length,forbidden_requests:forbidden.length,asset_hashes:checkedAssets,screenshots};
    fs.writeFileSync(path.join(output, 'readability-smoke.json'), JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify(receipt,null,2));
  } finally {
    if (browser) await browser.close();
    if (server) await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => {console.error(error);process.exitCode=1;});
