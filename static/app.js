'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const isStatic = document.documentElement.dataset.mode === 'static';
  let snapshotRequest;
  const state = { data: null, page: 'brief', limit: 40, refreshing: false, newsOrder:'latest', visit:null, visitReady:false };
  let visitTracker;
  try { visitTracker = window.PulseVisit?.create(window.localStorage, 'pulse-news-visit-v1:'+location.pathname.replace(/index\.html$/,'')); } catch (_) { visitTracker = window.PulseVisit?.create(null); }
  const sections = new Set(['brief', 'explore', 'evidence', 'financing', 'layers', 'earnings', 'sources']);
  const layerNames = {energy:'Energy',chips:'Chips',infrastructure:'Infrastructure',models:'Models',applications:'Applications'};
  const labels = { demand: 'Demand', capacity: 'Capacity', funding: 'Funding', earnings: 'Earnings', models: 'Model economics', policy: 'Policy & constraints', other: 'Source update' };
  const roleLabels = { primary: 'Primary source', secondary: 'Reported news', discovery: 'Discovery lead', curated:'Curated research' };
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const list = (value) => Array.isArray(value) ? value : [];
  const text = (value, fallback = 'Not assessed') => {
    if (value === null || value === undefined || value === '') return fallback;
    if (Array.isArray(value)) return value.map((v) => text(v, '')).filter(Boolean).join(' · ') || fallback;
    if (typeof value === 'object') return Object.entries(value).map(([k, v]) => `${k}: ${text(v, '')}`).join('; ');
    return String(value);
  };
  const safeUrl = (value) => {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch (_) { return null; }
  };
  const link = (url, label, cls = '') => {
    const target = safeUrl(url);
    return target ? `<a href="${esc(target)}" target="_blank" rel="noopener noreferrer"${cls ? ` class="${esc(cls)}"` : ''}>${label}</a>` : `<span>${label}</span>`;
  };
  const dateValue = (value) => { if (!value) return null; const date = new Date(value); return Number.isNaN(date.getTime()) ? null : date; };
  const dateLabel = (value, withTime = false) => {
    const date = dateValue(value);
    if (!date) return 'Date unavailable';
    return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', ...(withTime ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}), timeZone: 'UTC' }).format(date) + (withTime ? ' UTC' : '');
  };
  const timestamp = (value) => dateValue(value)?.getTime() || 0;
  const plural = (n, singular, multiple = `${singular}s`) => `${n} ${Number(n) === 1 ? singular : multiple}`;
  const empty = (title, explanation, extra = '') => `<div class="empty"><p class="eyebrow">Nothing inferred from missing data</p><h2>${esc(title)}</h2><p>${esc(explanation)}</p>${extra}</div>`;
  const notify = (message, type = '') => { const el = $('notification'); el.textContent = message; el.className = `notification ${type}`; el.hidden = false; };
  async function api(path, options = {}) {
    if (isStatic) throw new Error('The public snapshot does not connect to the local API.');
    const response = await fetch(path, { cache: 'no-store', ...options });
    let body;
    try { body = await response.json(); } catch (_) { throw new Error(`The local server returned an unreadable response (${response.status}).`); }
    if (!response.ok) throw new Error(body.error || body.message || `Request failed (${response.status}).`);
    return body;
  }
  function loadSnapshot() {
    if (!snapshotRequest) snapshotRequest = fetch('./data/dashboard.json', {cache:'no-store'}).then(async response => {
      if (!response.ok) throw new Error(`The published snapshot is unavailable (${response.status}).`);
      const data = await response.json();
      if (data?.publication?.mode !== 'static') throw new Error('This file is not a published research snapshot.');
      return data;
    });
    return snapshotRequest;
  }
  function hideLocalControls() {
    document.querySelectorAll('.local-only').forEach(element => {
      element.hidden = true;
      if ('disabled' in element) element.disabled = true;
      element.querySelectorAll('input,textarea,select,button').forEach(control => {control.disabled = true;});
    });
  }
  function configureStaticMode() {
    if (!isStatic) return;
    hideLocalControls();
    $('review-filter').value = 'all';
    const discoveryOrder = $('sort').querySelector('[value="discovery"]');
    discoveryOrder.hidden = true; discoveryOrder.disabled = true;
    const replacements = {
      'mode-label':'PUBLIC / REVIEWED SNAPSHOT', 'desk-kicker':'The public research desk',
      'stat-new-label':'Days since review', 'stat-total-label':'Published evidence items',
      'stat-sources-label':'Linked sources', 'stat-review-label':'Topics represented',
      'brief-method':'Reviewed public snapshot', 'priority-description':'Selected research and dated evidence from this published snapshot. Source links, counterevidence and uncertainty remain available for inspection.',
      'evidence-scope':'Selected for this public snapshot', 'sources-title':'Sources behind the snapshot.',
      'sources-description':'These are the dated references selected for this public edition. Source access and market conditions may have changed since review.',
      'sources-heading':'Linked source references', 'footer-desk':'A public research snapshot',
      'account-description':'Public profile links offer additional viewpoints. Identity references do not certify every claim. This site does not follow accounts or capture posts.',
    };
    Object.entries(replacements).forEach(([id,value]) => {$(id).textContent = value;});
    document.querySelector('[data-nav="brief"]').textContent = 'News';
    const sourceCard = document.querySelector('[data-nav="sources"] h2'); if (sourceCard) sourceCard.textContent = 'Sources & scope';
    $('loading').textContent = 'Opening the published research snapshot…';
    $('load-error').querySelector('h1').textContent = 'The published snapshot could not be loaded.';
    $('retry').textContent = 'Reload page';
    $('refresh-explainer').innerHTML = '<div><p class="eyebrow">How this public edition works</p><h2>A dated view. A visible boundary.</h2><p>This site loads one reviewed snapshot. It does not refresh the news, check source availability, or collect posts. Search and filters explore the published evidence; they cannot find events outside it.</p></div><ol><li><strong>Read the date</strong><span>Snapshot review and source publication describe different events.</span></li><li><strong>Inspect the evidence</strong><span>Open the linked source and compare the claim with its context.</span></li><li><strong>Test the implication</strong><span>Use counterevidence and the next checks to challenge the interpretation.</span></li></ol>';
    $('methodology').innerHTML = '<summary>How this public snapshot works <span aria-hidden="true">+</span></summary><div><p>This is a reviewed, read-only publication. It contains selected evidence and interpretation as of the displayed review date, not a complete or continuously updated market feed.</p><p>Source dates describe publication or filing. A review date records when this edition was examined; it does not establish that linked pages remain available or that claims remain current.</p><p>Search, filters and the probability illustration run in this page. This browser stores only stable item identifiers and content fingerprints to compare visits; no article text, personal notes or browsing history is sent to an application server. Clearing browser storage resets this comparison. The hosting provider may process ordinary page-request logs.</p><p>Financing and earnings comparisons keep commitments, revenue, guidance and sourced consensus separate. Missing fields mean unavailable, not zero. Conditional implications are not forecasts.</p></div>';
  }
  function renderPublication() {
    if (!isStatic) return;
    const publication = state.data.publication || {};
    const reviewedAt = publication.reviewed_at || publication.as_of;
    $('publication-banner').hidden = false;
    $('publication-banner').innerHTML = `${publication.draft ? '<strong class="publication-draft">Local draft · publication approval pending.</strong>' : ''}<span>Reviewed snapshot · not live</span><a href="#sources">Coverage & missing sources ↗</a>`;
  }
  function selectPage() {
    const hash = location.hash.slice(1).split('?')[0].split('/')[0];
    state.page = sections.has(hash) ? hash : 'brief';
    document.querySelectorAll('[data-panel]').forEach((panel) => { panel.hidden = panel.dataset.panel !== state.page; });
    document.querySelectorAll('[data-nav]').forEach((item) => {
      const active = item.dataset.nav === state.page || (item.closest('.nav') && item.dataset.nav==='explore' && !['brief','explore'].includes(state.page));
      item.classList.toggle('active', active);
      if (active) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
    });
    if (state.page==='financing') window.PulseFinance?.updateRoute(location.hash); else window.PulseFinance?.closeDetails();
    document.title = `${{ brief:'News', explore:'Explore', evidence: 'Evidence feed', financing: 'Financing map', layers:'Five AI layers', earnings: 'Earnings', sources: isStatic ? 'Sources & scope' : 'Sources & leads' }[state.page]} — AI Stock Pulse`;
  }
  function lastRefresh() {
    const refresh = list(state.data?.refreshes)[0];
    return refresh || {};
  }
  function isNew(article) {
    if (isStatic) return false;
    const latest = lastRefresh();
    return Boolean(latest.started_at && timestamp(article.first_seen_at) >= timestamp(latest.started_at));
  }
  function roleOf(item) {
    if (roleLabels[item.source_role || item.role]) return item.source_role || item.role;
    if (item.verification_status === 'discovery_lead') return 'discovery';
    if (['company_ir','sec_filing'].includes(item.kind)) return 'primary';
    return 'secondary';
  }
  function stories() { return Array.isArray(state.data?.stories) ? state.data.stories : list(state.data?.articles); }
  function readingState(article) { return !isStatic && ['reviewed','dismissed'].includes(article.review_status) ? article.review_status : 'unreviewed'; }
  function groupedArticleIds(article) {
    const ids = [...new Set([article.id, ...list(article.article_ids), ...list(article.related_sources).map(source => source.article_id)].filter(id => id !== null && id !== undefined))];
    if (!ids.length || ids.some(id => typeof id !== 'string' || !id.trim())) throw new Error('This reading group has incomplete source identifiers. Reload before changing its state.');
    if (ids.length > 100) throw new Error('This group exceeds the 100-source action limit. Its reading state has not changed.');
    return ids;
  }
  function renderHighlights(raw) {
    const highlights = list(raw).filter(item => item && typeof item === 'object');
    return highlights.length ? `<section class="article-highlights"><p class="eyebrow">Key takeaways</p><ol>${highlights.map(highlight => `<li><div class="highlight-heading"><h4>${esc(highlight.title || 'Source highlight')}</h4><span class="badge amber">${esc(text(highlight.claim_type,'Claim type not specified').replace(/_/g,' '))}</span></div><p>${esc(text(highlight.observation,'Observation unavailable.'))}</p><p class="highlight-implication"><strong>Conditional implication:</strong> ${esc(text(highlight.implication,'Not assessed.'))}</p><p class="fine-print">${link(highlight.source_url,'Source ↗')} · ${esc(dateLabel(highlight.source_date))}</p></li>`).join('')}</ol></section>` : '';
  }
  function renderArticle(article, rank) {
    const lens = labels[article.lens] ? article.lens : 'other';
    const role = roleOf(article);
    const reviewed = readingState(article);
    const claimBadge=/opinion|executive|commentary/i.test(article.claim_type||'') ? 'Attributed claim / opinion' : /management/i.test(article.claim_type||'') ? 'Management claim' : '';
    const published = dateValue(article.published_at);
    const future = article.date_precision === 'future_unverified' || (published && published.getTime() > Date.now());
    const dateKind = article.date_kind || (isStatic ? 'publication_date' : article.kind === 'sec_filing' ? 'filing_date' : role === 'discovery' ? 'search_feed_date' : 'feed_date');
    const dateName = {filing_date:'Filed',search_feed_date:'Search feed date',feed_date:'Feed date',publication_date:'Published'}[dateKind] || 'Source date';
    const publication = future ? `Unverified source date ${dateLabel(article.published_at)}` : published ? `${dateName} ${dateLabel(article.published_at)}` : 'Source date unknown';
    const revised = list(state.visit?.changedIds).includes(article.id);
    const newly = list(state.visit?.newIds).includes(article.id);
    const details = [
      ['Potential beneficiaries', article.beneficiaries], ['Exposures / possible losers', article.risks], ['Counterevidence', article.counterevidence],
      ['Would strengthen the implication', article.confirms], ['Would weaken the implication', article.refutes], ['Uncertainty', article.uncertainty],
    ];
    const related = list(article.related_sources);
    const relationCount = Number.isFinite(Number(article.related_count)) ? Number(article.related_count) : related.length;
    const dated = value => value ? dateLabel(value, String(value).includes('T')) : null;
    const sourceContext = [['Claim type', article.claim_type], ['Item reviewed', dated(article.reviewed_at)], ['Event date', dated(article.event_date)], ['Event starts', dated(article.event_start)], ['Event ends', dated(article.event_end)], ['Report period', article.report_period], ['Republished', dated(article.republished_at)], ['Market quote as of', dated(article.quote_as_of)], ['Source date context', article.source_date_note || article.publication_note], ['Source access', article.access_note]].filter(([,value]) => value);
    return `<article class="article news-card ${reviewed === 'dismissed' ? 'article-dismissed' : ''}"><div class="article-rank" aria-hidden="true">${String(rank).padStart(2, '0')}</div><div class="article-main">
      <div class="article-meta news-card-meta"><span class="badge ${lens}">${labels[lens]}</span><span class="badge source-${role}">${roleLabels[role]}</span>${claimBadge ? `<span class="badge amber">${esc(claimBadge)}</span>` : ''}${newly ? '<span class="badge new">New since visit</span>' : ''}${revised ? '<span class="badge amber">Materially revised</span>' : ''}${reviewed !== 'unreviewed' ? `<span class="badge subtle">${reviewed === 'reviewed' ? 'Read' : 'Dismissed'}</span>` : ''}<span class="source-name">${esc(article.publisher_name || article.source_name || article.source_id || 'Source')}</span><span class="meta-separator" aria-hidden="true">/</span><span>${esc(publication)}</span></div>
      <h3 class="news-card-title">${link(article.url, `${esc(article.title || 'Untitled source item')} <span class="article-link-icon" aria-hidden="true">↗</span>`)}</h3>
      <p class="news-card-implication"><strong>Why it matters:</strong> ${esc(text(article.implication, 'Interpretation not assessed. Open the source before drawing a conclusion.'))}</p>
      <details class="article-details news-card-details"><summary>Evidence & caveats</summary>
      ${role === 'discovery' ? '<p class="discovery-caveat">Discovery lead: this search result is a pointer to reporting. Open the publisher and verify the claim and original publication date; the search-feed date can be later. It is not independent corroboration.</p>' : ''}
      <div class="article-body article-observation"><div class="article-block"><p class="eyebrow">${isStatic ? 'Sourced observation' : role === 'discovery' ? 'Claim to investigate · search metadata' : 'Observation · source metadata'}</p><p>${esc(text(article.observation || article.summary || article.title, 'No excerpt available. Open the original source.'))}</p></div></div>
      <div class="reading-actions local-only ${article.curated ? 'curated-reading-disabled' : ''}" aria-label="Reading state for ${esc(article.title || 'source item')}">${reviewed !== 'reviewed' ? `<button class="queue-button" type="button" data-review="reviewed" data-article-id="${esc(article.id)}">Mark read</button>` : ''}${reviewed !== 'dismissed' ? `<button class="queue-button quiet" type="button" data-review="dismissed" data-article-id="${esc(article.id)}">Dismiss</button>` : ''}${reviewed !== 'unreviewed' ? `<button class="queue-button quiet" type="button" data-review="unreviewed" data-article-id="${esc(article.id)}">Reset to unread</button>` : ''}${relationCount ? `<span class="related-count">${plural(relationCount, 'related source appearance')}</span>` : ''}</div>
      ${relationCount ? '<p class="fine-print reading-scope local-only">Reading actions apply to every source appearance currently grouped here.</p>' : ''}<div class="source-excerpt"><p class="eyebrow">${isStatic ? 'Source summary & date context' : 'Source excerpt / filing metadata'}</p>${text(article.summary, '').trim() !== text(article.implication, '').trim() ? `<p>${esc(text(article.summary, 'No source excerpt supplied. Open the original.'))}</p>` : ''}${sourceContext.length ? `<dl class="source-context">${sourceContext.map(([label,value]) => `<div><dt>${esc(label)}</dt><dd>${esc(text(value))}</dd></div>`).join('')}</dl>` : ''}${article.methodology_url ? `<p class="methodology-link">${link(article.methodology_url,'Probability methodology / assumptions ↗')}</p>` : ''}</div><div class="analysis-grid">${details.map(([heading, value]) => `<div class="analysis-item"><p class="eyebrow">${esc(heading)}</p><p>${esc(text(value, 'Not assessed for this item.'))}</p></div>`).join('')}<div class="analysis-item wide"><p class="eyebrow">${isStatic ? 'Why this is included' : 'Why this is ranked here'}</p><p>${esc(text(article.score_reason, isStatic ? 'Selected for this dated public brief. Editorial order is not a market-impact forecast.' : 'Priority rules consider signal relevance and source dates.'))}${Number.isFinite(article.score) ? ` · Priority score: ${article.score}` : ''}</p>${article.priority_factors ? `<p class="factor-line">${esc(text(article.priority_factors, ''))}</p>` : ''}</div></div>
      ${related.length ? `<div class="related-sources"><p class="eyebrow">Related coverage</p>${related.map(source => `<p>${link(source.url || source.original_url, esc(source.title || source.name || source.source_name || source.publisher_name || 'Related source'))}${source.source_role || source.role ? ` <span class="badge subtle">${esc(roleLabels[source.source_role || source.role] || source.source_role || source.role)}</span>` : ''}</p>`).join('')}<p class="fine-print">A similar headline or multiple links may trace to the same announcement. Grouping is a reading aid, not proof of independent corroboration.</p></div>` : ''}
      ${renderHighlights(article.highlights)}
      ${relationCount && list(article.layer_matches).length ? `<div class="layer-attributions"><p class="eyebrow">Where the layer tags came from</p>${list(article.layer_matches).filter(match => match && typeof match==='object' && list(match.ai_layers).some(id => layerNames[id])).map(match => `<p>${list(match.ai_layers).filter(id => layerNames[id]).map(id => esc(layerNames[id])).join(' · ')} <span aria-hidden="true">→</span> ${link(match.url,esc(match.source_name || match.source_id || 'Related source'))} <span class="badge subtle">${esc(roleLabels[match.source_role] || 'Source role unknown')}</span> · ${esc({filing_date:'Filed',search_feed_date:'Search feed date',feed_date:'Feed date',publication_date:'Published'}[match.date_kind] || 'Source date')} ${esc(dateLabel(match.published_at))}</p>`).join('')}<p class="fine-print">Layer tags may come from related coverage. Grouping does not turn related text into a primary disclosure or independent corroboration.</p></div>` : ''}
      ${list(article.ai_layers).filter(id => layerNames[id]).length ? `<p class="fine-print">Metadata layer matches: ${list(article.ai_layers).filter(id => layerNames[id]).map(id => esc(layerNames[id])).join(' · ')}. Classification is not verification.</p>` : ''}
      <div class="provenance-line">${isStatic ? `<span>Snapshot reviewed ${esc(dateLabel(state.data.publication?.reviewed_at || state.data.publication?.as_of,true))}</span>${article.as_of ? `<span>Analysis as of ${esc(dateLabel(article.as_of))}</span>` : ''}` : `<span>First discovered ${esc(dateLabel(article.first_seen_at, true))}</span><span>Last observed ${esc(dateLabel(article.observed_at, true))}</span>`}${article.revised_at ? `<span>Last revised ${esc(dateLabel(article.revised_at, true))}</span>` : ''}<span>Date kind: ${esc(dateKind)} · precision: ${esc(article.date_precision || 'unknown')}</span><span>${link(article.url, role === 'discovery' ? 'Open discovery result ↗' : 'Open dated source ↗')}</span></div>
      ${article.source_quality ? `<p class="fine-print">Source scope: ${esc(text(article.source_quality))}</p>` : ''}${article.content_hash ? `<div class="provenance-line"><span>Content fingerprint ${esc(String(article.content_hash).slice(0, 16))}…</span></div>` : ''}${list(article.provenance).length ? `<div class="provenance-line"><span>Recorded appearances (${list(article.provenance).length}): ${list(article.provenance).map(p => link(p.original_url, esc(p.source_name || p.source_id || 'Source'))).join(' · ')}.</span></div>` : ''}<p class="fine-print local-only">Read / dismissed is your local reading queue, not a verification judgment.</p></details>
    </div></article>`;
  }
  function noteArticle(note) {
    const sources=list(note.sources).filter(source => safeUrl(source.url));
    const primary=sources[0] || {};
    // Review/as-of time never substitutes for a missing publication date.
    const sourceDate=note.published_at || primary.date || null;
    return {...note,id:'note:'+note.id,curated:true,visitKind:'curated',source_role:note.source_role || primary.role || primary.source_role || 'curated',source_name:note.source_name || 'Curated research',url:primary.url,published_at:sourceDate,date_kind:note.date_kind || 'publication_date',date_precision:note.date_precision || 'day',summary:note.observation,related_sources:sources.slice(1).map(source => ({...source,name:source.title})),score:note.priority || 85,relevance:'material',article_ids:[],verification_status:'curated_research',inference_type:'conditional_editorial_inference'};
  }
  function newsItems() {
    const notes=list(state.data?.notes).map(noteArticle).map(note=>({...note,article_ids:stories().filter(item=>safeUrl(item.url)===safeUrl(note.url)).flatMap(item=>[item.id,...list(item.article_ids)])}));
    const covered=new Set(notes.map(note => safeUrl(note.url)).filter(Boolean));
    const items=[...notes,...stories().filter(item => !covered.has(safeUrl(item.url)))];
    return items.filter(item => readingState(item)!=='dismissed' && (isStatic || item.curated || ['material','watch'].includes(item.relevance)));
  }
  function updateVisit() {
    if (!visitTracker) return;
    const items=newsItems();
    // Keep the comparison baseline fixed through filters, triage and refresh in one visit.
    state.visit=visitTracker.compare(items);
    const saved=visitTracker.commit([...list(state.data.articles),...stories(),...items]);if(!saved.storageAvailable)state.visit.storageAvailable=false;state.visitReady=true;
  }
  function renderNews() {
    let items=newsItems();
    const q=($('news-search')?.value || '').trim().toLowerCase();
    const lens=$('news-lens')?.value || 'all', entity=$('news-entity')?.value || 'all', layer=$('news-layer')?.value || 'all';
    items=items.filter(a => (!q || [a.title,a.summary,a.observation,a.implication,a.url,...list(a.entities)].join(' ').toLowerCase().includes(q)) && (lens==='all' || a.lens===lens) && (entity==='all' || list(a.entities).includes(entity)) && (layer==='all' || list(a.ai_layers).includes(layer)));
    const sourceTime=a => a.date_precision==='future_unverified' || timestamp(a.published_at)>Date.now() ? 0 : timestamp(a.published_at);
    const important=(a,b) => isStatic ? (Number(a.editorial_rank)||999)-(Number(b.editorial_rank)||999) : (Number(b.score)||0)-(Number(a.score)||0);
    items.sort(state.newsOrder==='important' ? (a,b)=>important(a,b)||sourceTime(b)-sourceTime(a) : (a,b)=>sourceTime(b)-sourceTime(a)||important(a,b));
    $('brief-feed').innerHTML=items.length ? items.slice(0,20).map((item,index)=>renderArticle(item,index+1)).join('') : empty('No news matches this view.', 'Try another filter or open Explore → All evidence. This is selected coverage, not proof that nothing happened.');
    if ($('news-count')) $('news-count').textContent=`${plural(items.length,'selected story')} · ${state.newsOrder==='latest' ? 'Latest source date first; unknown dates last' : 'Important first; priority is editorial or rule-based'} · ${isStatic ? 'Review date is not publication date.' : 'Background items remain in All evidence.'}`;
    document.querySelectorAll('[data-news-order]').forEach(button=>{const selected=button.dataset.newsOrder===state.newsOrder;button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected));});
    const visit=state.visit;
    if ($('visit-summary')) $('visit-summary').textContent=!visit?.storageAvailable ? 'Visit comparison unavailable in this browser. Source dates still apply.' : visit.firstVisit ? 'First visit in this browser · baseline saved. Nothing is labeled new yet.' : `${plural(list(visit.newIds).length,'new story')} · ${plural(list(visit.changedIds).length,'material revision')} since your previous visit. Newly found does not mean newly published.`;
    if (isStatic) hideLocalControls();
  }
  function renderBrief() {
    const data = state.data;
    const stats = data.stats || {};
    const sources = list(data.sources);
    const articles = list(data.articles);
    const latest = lastRefresh();
    const reviewedAt = data.publication?.reviewed_at || data.publication?.as_of;
    const latestTime = isStatic ? reviewedAt : latest.finished_at || (typeof stats.last_refresh === 'string' ? stats.last_refresh : stats.last_refresh?.finished_at);
    const datedItems = newsItems().filter(a => timestamp(a.published_at)>0 && timestamp(a.published_at)<=Date.now());
    const sourceDate = Math.max(0,...datedItems.map(a => timestamp(a.published_at)));
    $('edition-date').textContent = sourceDate ? `Latest source ${dateLabel(sourceDate)}` : 'Source dates unavailable';
    $('edition-asof').textContent = isStatic ? `Reviewed ${dateLabel(reviewedAt,true)} · not live` : latestTime ? `Fetched ${dateLabel(latestTime,true)} · notes reviewed separately` : 'No refresh completed';
    const reviewAge = dateValue(reviewedAt) ? (Date.now()-timestamp(reviewedAt))/86400000 : null;
    $('stat-new').textContent = isStatic ? reviewAge !== null && reviewAge >= 0 ? Math.floor(reviewAge) : '—' : stats.new_items ?? latest.new_count ?? 0;
    $('stat-changed').textContent = isStatic ? 'See the exact date above' : `${stats.changed_items ?? latest.changed_count ?? 0} revised`;
    $('stat-stories').textContent = `${stats.story_count ?? stories().length} reading groups`;
    $('stat-review').textContent = isStatic ? new Set(articles.map(article => article.lens || 'other')).size : stats.needs_review ?? stories().filter(a => readingState(a) === 'unreviewed' && a.relevance === 'material').length;
    $('stat-total').textContent = stats.total_articles ?? stats.articles ?? articles.length;
    $('stat-sources').textContent = isStatic ? sources.length : `${stats.source_ok ?? sources.filter((s) => s.status === 'ok').length} / ${stats.source_total ?? sources.length}`;
    $('nav-count').textContent = stories().filter(a => readingState(a) !== 'dismissed').length;
    const roleCounts = {primary:0,secondary:0,discovery:0}; sources.forEach(source => { roleCounts[roleOf(source)] += 1; });
    $('scope-strip').innerHTML = isStatic ? `<div><strong>Selected public evidence, reviewed as a dated snapshot.</strong><span>${roleCounts.primary} primary sources · ${roleCounts.secondary} reported sources · ${roleCounts.discovery} discovery leads. Linked sources are references, not live feed connections.</span></div><a class="text-link" href="#sources">See sources & scope ↗</a>` : `<div><strong>Selected coverage, not the whole market.</strong><span>${roleCounts.primary} primary sources · ${roleCounts.secondary} reporting feeds · ${roleCounts.discovery} discovery searches. A clear source check is not a complete news check.</span></div><a class="text-link" href="#sources">See coverage & gaps ↗</a>`;
    const issues = [];
    if (!dateValue(latestTime)) issues.push(isStatic ? 'The snapshot review date is unavailable. Check original sources before relying on these claims.' : 'No refresh has completed. Refresh sources to begin; no example articles are mixed into this feed.');
    else if (timestamp(latestTime) > Date.now()) issues.push(isStatic ? 'The supplied review date is in the future and has not been validated.' : 'The recorded refresh time is in the future. Check the local clock.');
    else if (Date.now() - timestamp(latestTime) > 48 * 3600000) issues.push(isStatic ? 'This snapshot was reviewed over 48 hours ago. It may be stale; inspect source updates before treating it as current.' : 'The last refresh is over 48 hours old. Refresh before treating this as a current brief.');
    const failed = sources.filter((s) => s.status === 'error').length;
    if (failed && !isStatic) issues.push(`${plural(failed, 'source')} failed on the latest attempt. Stored evidence may be older; inspect Sources & leads.`);
    const freshestPublication = Math.max(0, ...articles.filter((a) => a.date_precision !== 'future_unverified' && timestamp(a.published_at) <= Date.now()).map((a) => timestamp(a.published_at)));
    if (articles.length && freshestPublication && Date.now() - freshestPublication > 7 * 86400000) issues.push(isStatic ? 'The newest published source date is over seven days old. This is a historical snapshot.' : 'The newest loaded source date is over seven days old. A successful fetch does not mean the articles are new.');
    $('freshness').textContent = issues.join(' ');
    $('freshness').hidden = !issues.length;
    $('brief-headline').textContent = data.brief?.headline || (isStatic ? 'A dated view of the evidence.' : articles.length ? 'The evidence is ready for review.' : 'Your brief starts with primary sources.');
    const bullets = list(data.brief?.bullets);
    $('brief-bullets').innerHTML = bullets.length ? bullets.map((item) => `<li>${esc(text(item, ''))}</li>`).join('') : isStatic ? '<li>Read the review date and each source date together.</li><li>Use the evidence and counterevidence to test conditional implications.</li>' : '<li>Refresh official sources to start a dated evidence history.</li><li>Use X links as leads; confirm the underlying claim before assigning an implication.</li>';
    $('coverage-note').textContent = data.brief?.coverage_note || 'Coverage is limited to configured public sources. No comprehensive X trend stream, market-wide consensus feed or real-time price feed is connected.';
    renderNews();
    const takeaways = list(data.brief?.priority_takeaways);
    $('priority-takeaways').hidden = !takeaways.length;
    $('priority-takeaways').innerHTML = takeaways.length ? `<p class="eyebrow">Key takeaways · general context</p><div>${takeaways.slice(0,4).map((item,i) => `<p><span>${String(i+1).padStart(2,'0')}</span>${esc(typeof item === 'string' ? item : item.takeaway || item.title || text(item))}</p>`).join('')}</div><p class="fine-print">These explain why a signal can matter; they do not verify the underlying headlines.</p>` : '';
    $('curated-research').innerHTML='';
  }
  function renderNotes() {
    const notes = list(state.data.notes);
    const cards = notes.map((note) => {
      const sources = list(note.sources);
      const accessGap = sources.some(source => source.access_status === 'failed');
      const implication = text(note.implication);
      const old = timestamp(note.as_of) && Date.now() - timestamp(note.as_of) > 7 * 86400000;
      return `<article class="article curated-note"><div class="article-rank" aria-hidden="true">↳</div><div>
        <div class="article-meta"><span class="badge teal">Curated research</span><span>As of ${esc(dateLabel(note.as_of))}</span>${note.reviewed_at ? `<span>Item reviewed ${esc(dateLabel(note.reviewed_at,true))}</span>` : ''}<span class="badge ${labels[note.lens] ? note.lens : 'subtle'}">${esc(labels[note.lens] || 'Research')}</span>${accessGap ? '<span class="badge amber">Some direct sources unavailable</span>' : ''}${old ? '<span class="badge amber">Review age · over 7 days</span>' : ''}</div>
        <h3>${esc(note.title)}</h3><p class="curated-takeaway"><strong>Why it matters:</strong> ${esc(implication)}</p>
        <details class="article-details"><summary>Read the evidence, implications & uncertainty</summary>
          <div class="article-body curated-expanded"><div class="article-block"><p class="eyebrow">Sourced observation</p><p>${esc(text(note.observation))}</p></div><div class="article-block inference"><p class="eyebrow">Interpretation · not a prediction</p><p>${esc(implication)}</p></div></div>
          <div class="analysis-grid">${[['Counterevidence',note.counterevidence],['Would strengthen',note.confirms],['Would weaken',note.refutes],['Potential beneficiaries',note.beneficiaries],['Exposures / possible losers',note.risks],['Uncertainty',note.uncertainty]].map(([label, value]) => `<div class="analysis-item"><p class="eyebrow">${esc(label)}</p><p>${esc(text(value))}</p></div>`).join('')}</div>
          ${renderHighlights(note.highlights)}
          <div class="note-sources">${sources.map(source => `<p class="fine-print">${link(source.url, `${esc(source.title || 'Source')} ↗`)} · ${esc(dateLabel(source.date))}${source.access_status || source.status ? ` · Access: ${esc(source.access_status || source.status)}` : ''}</p>`).join('')}</div>
          ${note.source_access ? `<p class="fine-print">Source access: ${esc(text(note.source_access))}</p>` : ''}
        </details></div></article>`;
    }).join('');
    $('curated-research').innerHTML = notes.length ? `<div class="section-heading"><div><p class="eyebrow">Source-grounded research</p><h2>Claims in context</h2></div><span class="badge teal">Curated · dated sources</span></div><p class="section-description">A quick read, with the full evidence and limitations one click away. ${isStatic ? 'These notes reflect their displayed review dates; this site does not update them automatically.' : 'These dated research notes are reviewed separately from automatic feed refreshes.'}</p><div class="article-list">${cards}</div>` : '';
  }
  function renderEvidence() {
    const query = $('search').value.trim().toLowerCase();
    const lens = $('lens-filter').value;
    const role = $('role-filter').value;
    const entity = $('entity-filter').value;
    const relevance = $('relevance-filter').value;
    const layer = $('layer-filter').value;
    const review = $('review-filter').value;
    let items = stories().filter(a => {
      const entities = [...list(a.entities), ...list(a.source_entities)];
      const status = readingState(a);
      return (lens === 'all' || (a.lens || 'other') === lens)
        && (role === 'all' || roleOf(a) === role)
        && (entity === 'all' || entities.includes(entity))
        && (relevance === 'all' || a.relevance === relevance)
        && (layer === 'all' || list(a.ai_layers).includes(layer))
        && (review === 'all' || (review === 'active' ? status !== 'dismissed' : status === review))
        && (!query || [a.title,a.summary,a.url,a.original_url,a.observation,a.source_name,a.publisher_name,...entities,...list(a.tags),...list(a.event_flags)].join(' ').toLowerCase().includes(query));
    });
    if ($('sort').value === 'date') items.sort((a,b) => timestamp(b.published_at)-timestamp(a.published_at));
    else if ($('sort').value === 'discovery') items.sort((a,b) => timestamp(b.first_seen_at)-timestamp(a.first_seen_at));
    else items.sort((a,b) => isStatic ? (Number(a.editorial_rank)||Number.MAX_SAFE_INTEGER)-(Number(b.editorial_rank)||Number.MAX_SAFE_INTEGER) : (Number(b.score)||0)-(Number(a.score)||0));
    $('evidence-count').textContent = plural(stories().length,'reading group');
    $('filter-count').textContent = isStatic ? `${plural(items.length,'matching group')} from ${plural(list(state.data.articles).length,'published evidence item')}. Source dates and snapshot review dates are distinct; timestamps use UTC.` : `${plural(items.length,'matching group')} from ${plural(list(state.data.articles).length,'loaded source item')} of ${state.data.stats?.total_articles ?? list(state.data.articles).length} retained. Filed, feed and search-feed dates are labeled separately; timestamps use UTC.`;
    $('evidence-feed').innerHTML = items.length ? items.slice(0,state.limit).map((a,i) => renderArticle(a,i+1)).join('') : empty('No evidence matches these filters.', 'Try another company, source type or reading state. No result is not evidence that the topic has no developments.');
    $('show-more').hidden = items.length <= state.limit;
    if (isStatic) hideLocalControls();
  }
  function populateEntities() {
    const select = $('entity-filter'); const previous = select.value;
    const entities = [...new Set([...list(state.data.watchlist?.entities).map(e => typeof e === 'string' ? e : e.name || e.id).filter(Boolean),...list(state.data.articles).flatMap(a => [...list(a.entities),...list(a.source_entities)])])].sort();
    select.innerHTML = '<option value="all">All companies</option>' + entities.map(entity => `<option value="${esc(entity)}">${esc(entity)}</option>`).join('');
    select.value = entities.includes(previous) ? previous : 'all';
    if ($('news-entity')) {const prior=$('news-entity').value;$('news-entity').innerHTML=select.innerHTML;$('news-entity').value=entities.includes(prior)?prior:'all';}
  }
  function amount(value, currency) {
    if (value === null || value === undefined || value === '') return 'Amount not stated';
    const formatted = typeof value === 'number' ? new Intl.NumberFormat('en-US', {maximumFractionDigits:2}).format(value) : text(value);
    const unit = typeof currency === 'string' ? currency.trim().replace(/_/g,' ') : '';
    const scaled = unit.match(/^([A-Z]{3})\s+(bn|billion|mn|million)$/i);
    return scaled ? `${scaled[1].toUpperCase()} ${formatted} ${scaled[2]}` : `${unit ? unit+' ' : ''}${formatted}`;
  }
  const instruments = {
    equity:{label:'Equity investment',moves:'Capital for ownership',note:'An investment buys ownership; it is not customer revenue.'},
    debt:{label:'Debt / loan',moves:'Borrowed capital',note:'Debt must be repaid. An announced facility may be undrawn.'},
    customer_contract:{label:'Customer commitment',moves:'A purchase commitment',note:'Orders or contract value do not establish delivery, cash received or earned revenue.'},
    cloud_credits:{label:'Cloud credits',moves:'A cloud-use allowance',note:'Credits can support usage without being a cash payment or lasting demand.'},
    guarantee:{label:'Guarantee',moves:'Conditional credit support',note:'A guarantee can create a future obligation. It is not a current cash transfer.'},
    capacity:{label:'Compute capacity',moves:'Planned or available compute',note:'Capacity is a physical or service commitment. Delivery and utilization need separate evidence.'},
    revenue:{label:'Revenue',moves:'Earned revenue, if sourced',note:'Recognition needs a dated reporting source and accounting period; cash collection may differ.'},
    investment:{label:'Investment',moves:'Capital on stated terms',note:'Check the instrument and closing terms before treating an announcement as funded capital.'},
    other:{label:'Other arrangement',moves:'See the sourced terms',note:'The economic substance and transfer need to be established from the source.'},
  };
  function renderLedger() {
    const records = list(state.data.ledger).filter(record => record && typeof record==='object');
    $('ledger-count').textContent = plural(records.length,'sourced relationship');
    if (window.PulseFinance) window.PulseFinance.render({rows:records,container:$('ledger-content'),sources:list(state.data.sources),snapshotDate:state.data.publication?.reviewed_at || state.data.as_of || lastRefresh().finished_at});
    else $('ledger-content').innerHTML = empty('The financing view could not load.', 'Reload the page. No relationships are inferred from this unavailable view.');
  }
  function renderLayers() {
    const tracking = state.data.layer_tracking || {};
    const supplied = new Map(list(tracking.layers).filter(layer => layer && layerNames[layer.id]).map(layer => [layer.id,layer]));
    const sources = new Map(list(state.data.sources).map(source => [source.id,source]));
    const framework = tracking.source || {};
    $('layer-method').innerHTML = `<p class="eyebrow">Key takeaways by AI layer</p><p>${esc(text(tracking.method,'Layer assignments have not been supplied for this snapshot. The five views below do not imply monitoring is connected.'))}</p><p class="fine-print">Assignments are transparent metadata matches, not verified claims or comprehensive monitoring. One item can match more than one layer; counts are not additive.</p>${framework.url ? `<p class="fine-print">Framework: ${link(framework.url,esc(framework.title || 'Original source'))} · ${esc(dateLabel(framework.date))}</p>` : '<p class="fine-print">Framework source not supplied.</p>'}`;
    $('layer-grid').innerHTML = Object.entries(layerNames).map(([id,name],index) => {
      const layer=supplied.get(id) || {};
      const count=Number.isInteger(layer.article_count) && layer.article_count>=0 ? layer.article_count : null;
      const matched=list(layer.source_ids).map(sourceId => sources.get(sourceId)).filter(Boolean);
      const status=count===null ? 'Not assessed' : count ? 'Metadata matches' : 'No matched evidence';
      return `<article class="layer-card" data-layer-card="${id}"><div class="layer-heading"><span class="layer-number">${String(index+1).padStart(2,'0')}</span><div><h2>${esc(layer.name || name)}</h2><span class="badge ${count ? 'teal' : 'amber'}">${status}</span></div></div><p class="layer-summary">${esc(text(layer.summary,'What matters at this layer has not been summarized in the supplied data.'))}</p><div class="layer-takeaway"><p class="eyebrow">Key takeaway · general context</p><p>${esc(text(layer.takeaway,'No takeaway has been assessed for this layer yet.'))}</p></div><div class="layer-metrics"><p class="eyebrow">What to measure</p>${list(layer.metrics).length ? `<ul>${list(layer.metrics).map(metric => `<li>${esc(text(metric))}</li>`).join('')}</ul>` : '<p>Metrics have not been specified.</p>'}<p class="fine-print">${esc(text(layer.metric_status,'Measured metrics are unavailable in this view.'))}</p></div><div class="layer-evidence"><strong>${count===null ? '—' : count}</strong><span>${count===null ? 'Match count unavailable' : 'matched evidence '+(count===1?'item':'items')}</span></div><p class="fine-print">Latest matched source date: ${esc(dateLabel(layer.last_source_date))}</p>${layer.status ? `<p class="fine-print">Supplied coverage status: ${esc(String(layer.status).replace(/_/g,' '))}</p>` : ''}<div class="layer-source-links">${matched.length ? matched.map(source => link(source.url,esc(source.name || source.title || source.id))).join(' · ') : 'No linked source matched in this view.'}</div><p class="layer-gap"><strong>Gap:</strong> ${esc(text(layer.gap,'Completeness has not been assessed. A match does not establish ongoing coverage.'))}</p><button type="button" class="button layer-button" data-layer="${id}">View ${esc(name.toLowerCase())} evidence <span aria-hidden="true">↗</span></button></article>`;
    }).join('');
    $('layer-scope').textContent = tracking.scope || 'Selected evidence only. Missing matches do not establish that nothing happened at a layer.';
  }
  const metricValue = (value, unit) => value === null || value === undefined || value === '' ? '<span class="unavailable">Not sourced</span>' : `${esc(text(value))}${unit ? `<small>${esc(unit)}</small>` : ''}`;
  function renderEarnings() {
    const records = list(state.data.earnings);
    $('earnings-content').innerHTML = records.length ? `<div class="table-wrap" tabindex="0" role="region" aria-label="Earnings comparisons; scroll horizontally if needed"><table><thead><tr><th>Company / period</th><th>Metric</th><th>Reported</th><th>Guidance</th><th>Consensus</th><th>Evidence</th></tr></thead><tbody>${records.map((r) => `<tr><td><strong>${esc(r.company)}</strong><small>${esc(r.period)}</small></td><td>${esc(r.metric)}<small>${esc(r.note || '')}</small></td><td>${metricValue(r.reported,r.unit)}<small>Period: ${esc(r.reported_period || r.period || 'Not specified')}</small></td><td>${metricValue(r.guidance,r.unit)}<small>Guidance period: ${esc(r.guidance_period || 'Not specified')}</small></td><td>${metricValue(r.consensus,r.unit)}<small>Consensus period: ${esc(r.consensus_period || 'Not specified')}</small><small>Consensus as of: ${esc(r.consensus_as_of ? dateLabel(r.consensus_as_of, true) : 'Not sourced')}</small>${r.consensus_source_url ? `<small>${link(r.consensus_source_url, 'Consensus source ↗')}</small>` : ''}</td><td>${link(r.source_url, 'Company source ↗')}<small>${esc(dateLabel(r.source_date))}</small></td></tr>`).join('')}</tbody></table></div><p class="table-note">No beat / miss is calculated automatically. Verify fiscal period, units, GAAP versus adjusted basis, and consensus timestamp before comparing.</p>` : empty('No earnings comparisons verified yet.', 'Earnings announcements can appear in the feed. Numeric comparisons are added only after the reported period, metric, accounting basis and source are checked. Unavailable consensus remains blank.', isStatic ? '' : '<p>Add reviewed comparisons using <code>python3 -m pulse import-curation research.json</code>. Separate actuals and management guidance; attach an independent source to consensus.</p>');
  }
  function renderCoverage() {
    const coverage = state.data.coverage || {};
    const sourceMap = new Map(list(state.data.sources).map(s => [s.id,s]));
    $('coverage-explanation').textContent = coverage.note || 'These are the topics mapped to selected sources. Coverage is not exhaustive; source health and the quality of the underlying evidence still matter.';
    $('coverage-matrix').innerHTML = list(coverage.domains).length ? list(coverage.domains).map(domain => {
      const mapped = list(domain.connected_sources).map(s => typeof s === 'string' ? sourceMap.get(s) || {id:s,name:s} : s);
      const status = isStatic ? mapped.length ? 'Included' : 'Outside snapshot' : domain.status === 'covered' ? 'Sources mapped' : domain.status === 'discovery_only' ? 'Discovery only' : 'Coverage gap';
      return `<article class="coverage-cell"><div class="coverage-cell-heading"><h3>${esc(domain.name || domain.id)}</h3><span class="badge ${(isStatic ? mapped.length : domain.status === 'covered') ? 'teal' : 'amber'}">${status}</span></div><p>${esc(domain.takeaway || '')}</p><p class="fine-print">${esc(domain.note || '')}</p><div class="coverage-source-links">${mapped.length ? mapped.map(source => source.url ? link(source.url, esc(source.name || source.id)) : `<span>${esc(source.name || source.id)}</span>`).join(' · ') : isStatic ? 'No reference included for this topic' : 'No configured source mapped'}</div></article>`;
    }).join('') : empty('Coverage mapping is not available.', 'The source list below shows what is configured, not proof of complete topic coverage.');
    const gaps = list(coverage.gaps);
    $('coverage-gaps').innerHTML = gaps.length ? `<p class="eyebrow">Known gaps</p><ul>${gaps.map(gap => `<li>${esc(typeof gap === 'string' ? gap : gap.note || gap.message || gap.name || text(gap))}</li>`).join('')}</ul>` : '';
    $('coverage-gaps').hidden = !gaps.length;
  }
  function renderAccounts() {
    if (isStatic) {
      $('x-access').innerHTML = '<span class="badge amber">No X collection</span><div><strong>A public snapshot has no account connection.</strong><p>This page does not read timelines, find trending posts or accept personal research notes. Any included social reference remains a lead to check against its underlying evidence.</p></div>';
      const hasAccounts = list(state.data.accounts).length > 0;
      ['account-heading','account-description','account-list'].forEach(id => {$(id).hidden = !hasAccounts;});
      if (!hasAccounts) return;
    }
    const access = state.data.x_access || {};
    const blocked = access.status !== 'connected';
    if (!isStatic) $('x-access').innerHTML = `<span class="badge ${blocked ? 'amber' : 'teal'}">${blocked ? 'X session not verified' : 'X session available'}</span><div><strong>${access.automatic ? 'X collection status' : 'X reading is separate from automatic refresh'}</strong><p>${esc(access.detail || 'Manual post capture is available; no automated timeline or trend coverage is configured.')}</p><small>${access.checked_at ? `Access check ${esc(dateLabel(access.checked_at,true))}` : 'Existing browser session has not been checked.'}</small></div>`;
    const accounts = list(state.data.accounts);
    $('account-count').textContent = plural(accounts.length,'profile');
    $('account-list').innerHTML = accounts.length ? accounts.map(account => `<article class="account-card"><div class="account-heading"><h3>${link(account.url,esc(account.name || account.handle || 'Account'))}</h3><span class="account-handle">${esc(account.handle ? '@'+String(account.handle).replace(/^@/,'') : '')}</span></div><p class="account-role">${esc(text(account.role,''))}</p><div class="account-topics">${list(account.topics).map(topic => `<span class="badge subtle">${esc(topic)}</span>`).join('')}</div><p>${esc(text(account.why,''))}</p><p class="account-caveat"><strong>Read with context:</strong> ${esc(text(account.bias,'No source is a substitute for primary evidence.'))}</p>${account.example_url ? `<p class="account-example">${link(account.example_url,'Example post ↗')}${account.example_note ? ` · ${esc(account.example_note)}` : ''}</p>` : ''}<div class="account-footer">${account.verification_url ? link(account.verification_url,'Identity / expertise evidence ↗') : '<span>Identity source unavailable</span>'}<span>Checked ${esc(dateLabel(account.verified_at))}</span></div><p class="fine-print">Public identity checked; session access and every post are not verified.</p></article>`).join('') : empty('No reading-list profiles verified yet.', 'Profiles will appear here once their identity and area of expertise have source references. No accounts are followed automatically.');
  }
  function renderSources() {
    renderCoverage(); renderAccounts();
    const sources = list(state.data.sources);
    if (isStatic) {
      $('source-status-summary').textContent = plural(sources.length,'linked reference');
      $('source-list').innerHTML = sources.length ? sources.map(source => {
        const role = roleOf(source);
        return `<article class="source-row"><div class="source-heading-wrap"><div class="source-heading">${link(source.url,esc(source.name || source.title || source.id))}<span class="badge subtle">Curated reference</span><span class="badge source-${role}">${roleLabels[role]}</span></div><p class="source-quality">${esc(text(source.quality_note || source.coverage_note,'Selected evidence for this edition. Inclusion does not verify every claim or establish current availability.'))}</p>${source.access_note ? `<p class="source-detail">${esc(source.access_note)}</p>` : ''}</div><div class="source-time">Source date<strong>${esc(dateLabel(source.published_at || source.source_date || source.date))}</strong></div><div class="source-time">${source.reviewed_at ? 'Reviewed for this edition' : 'Snapshot reviewed'}<strong>${esc(dateLabel(source.reviewed_at || state.data.publication?.reviewed_at,true))}</strong></div></article>`;
      }).join('') : empty('No source references in this edition.', 'This public snapshot does not check live feed availability.');
      $('lead-list').innerHTML = '';
      return;
    }
    const ok = sources.filter(s => s.status === 'ok').length;
    $('source-status-summary').textContent = `${ok} / ${sources.length} last fetches successful`;
    $('source-list').innerHTML = sources.length ? sources.map(source => {
      const successful = source.status === 'ok';
      const never = !source.last_attempt_at;
      const stale = source.last_success_at && Date.now()-timestamp(source.last_success_at)>48*3600000;
      const role = roleOf(source);
      return `<article class="source-row"><div class="source-heading-wrap"><div class="source-heading">${link(source.url,esc(source.name || source.id))}<span class="badge ${successful ? stale ? 'amber' : 'teal' : never ? 'subtle' : 'error'}">${successful ? stale ? 'Fetch old' : 'Fetched' : never ? 'Not fetched' : 'Fetch failed'}</span><span class="badge source-${role}">${roleLabels[role]}</span></div><p class="source-detail">${esc(source.kind === 'sec_filing' ? 'SEC filing metadata' : text(source.format || source.kind,'Public source'))} · ${plural(source.item_count ?? 0,'item in last successful fetch')}</p>${source.quality_note || source.coverage_note ? `<p class="source-quality">${esc(text(source.quality_note || source.coverage_note,''))}</p>` : ''}${source.cadence_hint ? `<p class="source-detail">${esc(text(source.cadence_hint,''))}</p>` : ''}${list(source.topics).length ? `<p class="source-detail">Topics: ${esc(list(source.topics).join(' · '))}</p>` : ''}</div><div class="source-time">Last attempt<strong>${esc(dateLabel(source.last_attempt_at,true))}</strong></div><div class="source-time">Last success<strong>${esc(dateLabel(source.last_success_at,true))}</strong></div>${source.last_error && !successful ? `<div class="source-error">${esc(source.last_error)}. Previously stored evidence is retained.</div>` : ''}${source.rejected_count ? `<div class="source-error">${esc(source.rejected_count)} unusable items were rejected on the last check; this is partial coverage.</div>` : ''}</article>`;
    }).join('') : empty('No sources configured.', 'Configured sources and their actual status will appear here.');
    const leads = list(state.data.leads);
    $('lead-count').textContent = plural(leads.length,'lead');
    $('lead-list').innerHTML = leads.length ? leads.map(lead => `<article class="lead-item"><span class="badge amber">Unverified lead</span><div>${link(lead.url,`${esc(lead.url)} ↗`)}${lead.note ? `<p>${esc(lead.note)}</p>` : ''}<p class="fine-print">Saved ${esc(dateLabel(lead.created_at,true))} · Contents not fetched or verified</p></div></article>`).join('') : empty('No X leads saved.', 'Paste a public post link above to investigate. A saved link never counts as confirmed evidence.');
  }
  function render() { renderPublication(); populateEntities(); renderBrief(); renderEvidence(); renderLedger(); renderLayers(); renderEarnings(); renderSources(); selectPage(); if (isStatic) hideLocalControls(); }
  async function load(initial = false) {
    if (initial) { $('loading').hidden = false; $('load-error').hidden = true; }
    try {
      state.data = isStatic ? await loadSnapshot() : await api('/api/dashboard');
      updateVisit();
      render();
      $('dashboard').hidden = false; $('loading').hidden = true; $('load-error').hidden = true;
    } catch (error) {
      $('loading').hidden = true;
      if (state.data) notify(`${error.message} The visible data is the last loaded snapshot.`, 'error');
      else { $('load-error-text').textContent = `${error.message} ${isStatic ? 'Reload this page or check the published site later.' : 'Check that the local launcher is running.'}`; $('load-error').hidden = false; }
      throw error;
    }
  }
  $('refresh').addEventListener('click', async () => {
    if (isStatic) return;
    if (state.refreshing) return;
    state.refreshing = true;
    const button = $('refresh'); button.disabled = true; button.textContent = 'Refreshing…';
    notify('Checking public sources. This can take a minute; individual failures will be recorded.');
    try {
      const result = await api('/api/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      await load();
      const summary = result.summary || result;
      const errors = Number(summary.error_count ?? 0);
      const added = Number(summary.new_count ?? 0);
      const duplicates = Number(summary.duplicate_count ?? 0);
      const changed = Number(summary.changed_count ?? 0);
      const rejected = Number(summary.rejected_count ?? 0);
      const skipped = Number(summary.skip_count ?? summary.skipped_count ?? 0);
      notify(`Refresh ${errors || skipped || rejected ? 'completed with gaps' : 'completed'}: ${plural(added,'new item')}; ${plural(changed,'revised item')}; ${plural(duplicates,'unchanged item')}.${errors ? ` ${plural(errors,'source')} failed.` : ''}${skipped ? ` ${plural(skipped,'source')} skipped.` : ''}${rejected ? ` ${plural(rejected,'unusable item')} rejected.` : ''}${errors || skipped || rejected ? ' Check Sources & leads for details.' : ' This describes configured coverage, not all market news.'}`, errors || skipped || rejected ? '' : 'success');
    } catch (error) { notify(`Refresh did not complete: ${error.message} Previously stored evidence is preserved.`, 'error'); }
    finally { state.refreshing = false; button.disabled = false; button.innerHTML = '<span aria-hidden="true">↻</span> Refresh sources'; }
  });
  $('lead-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (isStatic) return;
    const form = event.currentTarget; const button = form.querySelector('button'); const url = $('lead-url').value.trim();
    if (!/^https:\/\/(?:www\.)?(?:x\.com|twitter\.com)\/[A-Za-z0-9_]+\/status\/\d+(?:[/?#].*)?$/.test(url)) { $('lead-message').textContent = 'Use a public https://x.com/account/status/123 or twitter.com post URL.'; $('lead-url').focus(); return; }
    button.disabled = true; $('lead-message').textContent = 'Saving the unverified lead locally…';
    try {
      const result = await api('/api/leads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, note: $('lead-note').value.trim() }) });
      await load(); form.reset(); $('lead-message').textContent = result.duplicate || result.created === false ? 'This post is already saved. It remains an unverified lead.' : 'Saved locally as an unverified lead. The post contents were not fetched.';
    } catch (error) { $('lead-message').textContent = `Could not save this lead: ${error.message}`; }
    finally { button.disabled = false; }
  });
  $('cds-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const spread = Number($('cds-spread').value); const years = Number($('cds-years').value); const recovery = Number($('cds-recovery').value);
    if (![spread, years, recovery].every(Number.isFinite) || spread < 0 || years <= 0 || recovery < 0 || recovery >= 100) { $('cds-output').textContent = 'Use a nonnegative spread, a positive horizon and recovery below 100%.'; return; }
    const probability = -Math.expm1(-(spread / 10000) * years / (1 - recovery / 100));
    const oneYear = -Math.expm1(-(spread / 10000) / (1 - recovery / 100));
    $('cds-output').innerHTML = `<strong>${(probability * 100).toFixed(1)}% over ${esc(years)} ${years === 1 ? 'year' : 'years'}</strong>Simplified cumulative risk-neutral illustration. ${(oneYear * 100).toFixed(1)}% over one year with the same assumptions. Inputs: ${esc(spread)} bps; ${esc(recovery)}% recovery. No issuer or live market quote is implied.`;
  });
  ['search', 'lens-filter', 'sort', 'role-filter', 'entity-filter', 'layer-filter', 'relevance-filter', 'review-filter'].forEach((id) => $(id).addEventListener(id === 'search' ? 'input' : 'change', () => { state.limit = 40; if (state.data) renderEvidence(); }));
  $('layer-grid').addEventListener('click', event => {
    const button=event.target.closest('button[data-layer]');
    if (!button || !layerNames[button.dataset.layer]) return;
    $('layer-filter').value=button.dataset.layer;
    $('search').value='';
    ['lens-filter','role-filter','entity-filter','relevance-filter'].forEach(id => {$(id).value='all';});
    // The layer count includes every loaded group, including locally dismissed ones.
    $('review-filter').value='all';
    state.limit=40; renderEvidence();
    location.hash='evidence'; selectPage();
  });
  $('dashboard').addEventListener('click', async event => {
    if (isStatic) return;
    const button = event.target.closest('button[data-review]');
    if (!button || button.disabled) return;
    const status = button.dataset.review;
    const articleId = button.dataset.articleId;
    if (!articleId || !['unreviewed','reviewed','dismissed'].includes(status)) return;
    button.disabled = true;
    try {
      const article = [...stories(), ...list(state.data?.brief?.priority_items)].find(item => item.id === articleId);
      if (!article) throw new Error('This item is no longer in the loaded snapshot. Reload before changing its state.');
      const articleIds = groupedArticleIds(article);
      const result = await api('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({article_ids:articleIds,status})});
      await load();
      const scope = `${plural(result.count ?? articleIds.length, 'source appearance')} in this group. `;
      notify(scope + (status === 'dismissed' ? 'Dismissed from the active reading queue. Use the Dismissed filter to restore it.' : status === 'reviewed' ? 'Marked read. This changes your queue, not the verification status of the claim.' : 'Returned to the unread queue.'),'success');
    } catch(error) { button.disabled = false; notify(`Reading state was not saved: ${error.message}`,'error'); }
  });
  $('show-more').addEventListener('click', () => { state.limit += 40; renderEvidence(); });
  $('retry').addEventListener('click', () => { if (isStatic) location.reload(); else load(true).catch(() => {}); });
  window.addEventListener('hashchange', selectPage);
  document.querySelectorAll('[data-news-order]').forEach(button=>button.addEventListener('click',()=>{state.newsOrder=button.dataset.newsOrder==='important'?'important':'latest';renderNews();}));
  ['news-search','news-lens','news-entity','news-layer'].forEach(id=>$(id)?.addEventListener(id==='news-search'?'input':'change',()=>{if(state.data)renderNews();}));
  configureStaticMode(); selectPage(); load(true).catch(() => {});
})();
