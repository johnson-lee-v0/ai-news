/* A sourced relationship explorer. No requests, persistence, inferred transfers or totals. */
'use strict';
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const DAY = 86400000;
  const instrumentNames = {equity:'Equity investment',investment:'Investment',debt:'Debt financing',customer_contract:'Customer contract / reservation',compute_purchase:'Compute purchase',guarantee:'Guarantee',reservation:'Reservation advance',credits:'Service credits',cloud_credits:'Cloud credits',capacity:'Capacity commitment',revenue:'Reported revenue',service:'Service delivery',other:'Other sourced arrangement'};
  const flowNames = {money:'Money / obligation',service:'Services',capacity:'Capacity',guarantee:'Guarantee support',credit:'Credits',ownership:'Ownership rights',unspecified:'Recorded relationship'};
  const state = {container:null,rows:[],sources:[],snapshotDate:null,company:'',recent:false,relationship:'',dialog:null,returnFocus:null,ownedDetail:false,onNavigate:null,focusAfterRender:''};
  const string = (value, fallback='') => value === null || value === undefined || value === '' ? fallback : typeof value === 'object' ? fallback : String(value);
  const dateNumber = value => { const number = Date.parse(string(value)); return Number.isFinite(number) ? number : null; };
  const dateLabel = value => { const number=dateNumber(value); return number === null ? 'Date unavailable' : new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(number); };
  const safeUrl = value => { try { const url=new URL(string(value)); return url.protocol==='https:' && !url.username && !url.password ? url.href : null; } catch (_) { return null; } };
  const element = (tag, className, text) => { const node=document.createElement(tag); if(className) node.className=className; if(text!==undefined) node.textContent=String(text); return node; };
  const append = (parent,...children) => { children.forEach(child=>{if(child) parent.append(child);}); return parent; };
  const button = (label,className,action) => { const node=element('button',className,label);node.type='button';if(action)node.addEventListener('click',action);return node; };
  function sourceLink(row,label='Read the source ↗') {
    const url=safeUrl(row.source_url);
    if(!url) return element('span','pf-source-missing','Dated source unavailable');
    const link=element('a','pf-source-link',label);link.href=url;link.target='_blank';link.rel='noopener noreferrer';return link;
  }
  function amountLabel(row) {
    if(row.amount===null || row.amount===undefined || row.amount==='') return 'Amount not stated';
    const unit=string(row.unit || row.currency,'Units not stated');
    if(typeof row.amount==='number' && Number.isFinite(row.amount)) {
      const amount=new Intl.NumberFormat('en-US',{maximumFractionDigits:6}).format(row.amount);
      if(unit==='USD bn' || unit==='USD billion') return 'US$'+amount+'bn';
      if(unit==='USD million') return 'US$'+amount+'m';
      if(unit==='USD') return 'US$'+amount;
      return amount+' '+unit;
    }
    return string(row.amount)+' · '+unit;
  }
  function normalizeRows(rows,sources=[]) {
    const knownSources=new Map((Array.isArray(sources)?sources:[]).filter(source=>source && safeUrl(source.url)).map(source=>[safeUrl(source.url),source]));
    const used=new Set();
    return (Array.isArray(rows)?rows:[]).map((raw,index)=>{
      const row=raw && typeof raw==='object'?raw:{};
      let id=string(row.id,'relationship-'+(index+1));
      if(used.has(id))id+='-'+(index+1);used.add(id);
      const instrument=string(row.instrument,'other');
      const fallbackFlow=({equity:'money',investment:'money',debt:'money',reservation:'money',guarantee:'guarantee',capacity:'capacity',credits:'credit',cloud_credits:'credit',service:'service'})[instrument] || 'unspecified';
      const flow=Object.prototype.hasOwnProperty.call(flowNames,row.flow_type)?row.flow_type:fallbackFlow;
      const source=knownSources.get(safeUrl(row.source_url));
      return {...row,id,from_entity:string(row.from_entity,'Source entity unknown'),to_entity:string(row.to_entity,'Recipient unknown'),instrument,
        instrument_name:instrumentNames[instrument] || instrument.replace(/_/g,' '),flow_type:flow,flow_label:string(row.flow_label,flowNames[flow]),
        status:string(row.status,'Stage unknown'),payment_status:string(row.payment_status,'Unknown — cash movement not established'),
        revenue_status:string(row.revenue_status,'Unknown — revenue recognition not established'),
        uncertainty:string(row.uncertainty || row.risk,'Terms, payment and performance are not fully established by this record.'),
        source_name:string(row.source_name || (source && source.name),'Linked source'),amount_label:amountLabel(row),ordinal:index+1};
    });
  }
  function inRecentWindow(row) {
    const day=dateNumber(string(row.source_date).slice(0,10));
    const snapshot=dateNumber(string(state.snapshotDate).slice(0,10));
    return day!==null && snapshot!==null && snapshot-day>=0 && snapshot-day<7*DAY;
  }
  function visibleRows() { return state.rows.filter(row=>(!state.company || row.from_entity===state.company || row.to_entity===state.company) && (!state.recent || inRecentWindow(row))); }
  function companyCounts(rows) {
    const counts=new Map();
    rows.forEach(row=>new Set([row.from_entity,row.to_entity]).forEach(company=>counts.set(company,(counts.get(company)||0)+1)));
    return [...counts].sort((a,b)=>b[1]-a[1] || a[0].localeCompare(b[0]));
  }
  function viewRoute(company=state.company,recent=state.recent,relationship='') {
    let route='#financing';const params=new URLSearchParams();
    if(relationship) {route+='/relationship/'+encodeURIComponent(relationship);if(company)params.set('company',company);}
    else if(company)route+='/company/'+encodeURIComponent(company);
    if(recent)params.set('recent','1');
    return route+(params.size?'?'+params.toString():'');
  }
  function navigate(route,replace=false) {
    if(state.onNavigate)state.onNavigate(route,{replace});
    else if(replace) {history.replaceState(history.state,'',route);window.dispatchEvent(new Event('hashchange'));}
    else if(location.hash!==route)location.hash=route;
    updateRoute(route);
  }
  function chooseCompany(company) {state.ownedDetail=false;state.focusAfterRender='company';navigate(viewRoute(company,state.recent));}
  function openRelationship(row,trigger) {
    state.returnFocus=trigger || document.activeElement;state.ownedDetail=true;
    navigate(viewRoute(state.company,state.recent,row.id));
  }
  function closeFromUI() {
    if(state.ownedDetail && location.hash.startsWith('#financing/relationship/') && history.length>1) {state.ownedDetail=false;history.back();}
    else {state.ownedDetail=false;navigate(viewRoute(state.company,state.recent),true);}
  }
  function closeDetails(restoreFocus=true) {
    if(state.dialog && state.dialog.open)state.dialog.close();
    state.relationship='';
    if(restoreFocus && state.returnFocus && state.returnFocus.isConnected)state.returnFocus.focus({preventScroll:true});
  }
  function detailField(label,value) {return append(element('div','pf-detail-field'),element('dt','',label),element('dd','',value));}
  function showDetails(row) {
    if(!state.dialog)return;
    const dialog=state.dialog;
    if(state.relationship===row.id && dialog.open)return;
    state.relationship=row.id;dialog.replaceChildren();
    const header=append(element('div','pf-dialog-top'),element('p','pf-kicker','Relationship '+row.ordinal),button('Close ×','pf-close',closeFromUI));
    const title=element('h2','pf-dialog-title',row.from_entity+' → '+row.to_entity);title.id='pf-dialog-title';
    const subtitle=element('p','pf-dialog-subtitle',row.instrument_name+' · '+row.amount_label);
    const stage=element('p','pf-stage',row.status);
    const flow=append(element('div','pf-detail-flow'),element('span','pf-kicker','What moves'),element('strong','',row.flow_label),element('p','',row.from_entity+' → '+row.to_entity));
    const facts=append(element('dl','pf-detail-grid'),detailField('Cash moved?',row.payment_status),detailField('Revenue earned?',row.revenue_status),detailField('Arrangement as of',dateLabel(row.as_of)),detailField('Source date',dateLabel(row.source_date)),detailField('Amount / units',row.amount_label),detailField('Units',string(row.unit || row.currency,'Units not stated')),detailField('Overlap group',string(row.overlap_group,'Overlap not assessed')));
    if(row.reviewed_at)facts.append(detailField('Record reviewed',dateLabel(row.reviewed_at)));
    const note=append(element('section','pf-detail-section'),element('h3','','Evidence and scope'),element('p','',string(row.note,'No explanatory note supplied.')));
    const uncertainty=append(element('section','pf-detail-section pf-caution'),element('h3','','Uncertainty / risk'),element('p','',row.uncertainty));
    const source=append(element('div','pf-detail-source'),sourceLink(row),element('span','',row.source_name+' · '+dateLabel(row.source_date)));
    const supplemental=element('div','pf-supplemental-sources');
    const otherSources=Array.isArray(row.sources)?row.sources:[];
    if(otherSources.length){supplemental.append(element('h3','','Supporting sources / updates'));otherSources.forEach(item=>{if(!item || typeof item!=='object')return;const entry=element('p','');append(entry,sourceLink({source_url:item.url},string(item.title,'Supporting source')+' ↗'),element('span','',dateLabel(item.date)+(item.role?' · '+string(item.role):'')));supplemental.append(entry);});}
    append(dialog,header,title,subtitle,stage,flow,facts,note,uncertainty,element('p','pf-footnote',row.instrument==='revenue'?'Revenue is not automatically cash collected.':'This is not a revenue record. Announced amounts, service capacity and cash received are different measures.'),source,supplemental);
    if(!dialog.open)dialog.showModal();
    header.querySelector('button').focus({preventScroll:true});
  }
  function makeDialog() {
    const dialog=element('dialog','pf-dialog');dialog.setAttribute('aria-labelledby','pf-dialog-title');
    dialog.addEventListener('cancel',event=>{event.preventDefault();closeFromUI();});
    dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left || event.clientX>rect.right || event.clientY<rect.top || event.clientY>rect.bottom)closeFromUI();});
    return dialog;
  }
  function makeCard(row) {
    const card=element('article','pf-relationship relationship-card');card.dataset.relationshipId=row.id;
    const top=append(element('div','pf-card-top'),element('span','pf-edge-number',row.ordinal),element('span','pf-kind',row.instrument_name),element('span','pf-card-date',dateLabel(row.source_date)));
    const from=button(row.from_entity,'pf-company-link',()=>chooseCompany(row.from_entity));
    const to=button(row.to_entity,'pf-company-link',()=>chooseCompany(row.to_entity));
    const route=append(element('h3','pf-card-route'),from,element('span','pf-arrow','→'),to);
    const transfer=append(element('div','pf-transfer'),element('span','pf-kicker','What moves'),element('strong','',row.flow_label),element('span','pf-card-amount',row.amount_label));
    if(!row.unit && !row.currency)transfer.append(element('small','pf-unit-note','Units not stated'));
    const stage=element('p','pf-stage',row.status);
    const checks=append(element('dl','pf-card-checks'),detailField('Cash moved?',row.payment_status),detailField('Revenue earned?',row.revenue_status));
    const metadata=element('p','pf-card-meta','Arrangement as of '+dateLabel(row.as_of)+' · '+string(row.overlap_group,'Overlap not assessed'));
    const caveat=element('p','pf-card-caveat',row.instrument==='revenue'?'Reported revenue is not automatically collected cash.':'This is not a revenue record.');
    const details=button('Inspect relationship','pf-inspect',event=>openRelationship(row,event.currentTarget));
    details.setAttribute('aria-label','Inspect '+row.instrument_name+' from '+row.from_entity+' to '+row.to_entity);
    const footer=append(element('div','pf-card-footer'),sourceLink(row),details);
    append(card,top,route,transfer,stage,checks,metadata,caveat,footer);return card;
  }
  function graphPositions(companies,rows,width,height) {
    const nodes=companies.map(([name,count],index)=>({name,count,x:width/2+Math.cos(-Math.PI/2+index*2*Math.PI/companies.length)*width*.36,y:height/2+Math.sin(-Math.PI/2+index*2*Math.PI/companies.length)*height*.36}));
    if(nodes.length===1){nodes[0].x=width/2;nodes[0].y=height/2;return nodes;}
    if(state.company) {
      const center=nodes.find(n=>n.name===state.company);const neighbors=nodes.filter(n=>n!==center);
      if(center){center.x=width/2;center.y=height/2;}
      neighbors.forEach((n,i)=>{const angle=-Math.PI/2+i*2*Math.PI/neighbors.length;n.x=width/2+Math.cos(angle)*width*.36;n.y=height/2+Math.sin(angle)*height*.36;});
      return nodes;
    }
    // A fixed grid makes every company readable in a dense overview. Position
    // encodes no industry cohort, payment size or economic importance.
    const columns=Math.min(4,nodes.length);
    const rowCount=Math.ceil(nodes.length/columns);
    nodes.forEach((node,index)=>{
      const row=Math.floor(index/columns),column=index%columns;
      const inRow=Math.min(columns,nodes.length-row*columns);
      node.x=(column+(columns-inRow)/2+.5)*width/columns;
      node.y=(height-(rowCount-1)*140)/2+row*140;
    });
    return nodes;
  }
  function makeGraph(rows) {
    const companies=companyCounts(rows);const width=1000,height=state.company?(companies.length>12?680:520):Math.max(430,Math.ceil(companies.length/4)*140+10);
    const section=element('section','pf-graph-section');section.setAttribute('aria-label','Interactive relationship overview');
    append(section,element('p','pf-graph-hint','Select a company to follow its relationships. The full overview shows every company in the selected network. Choose a company for labeled relationships, or select a line to inspect its source. Every relationship is also listed below.'),button('Skip map to relationship list','pf-skip-map',()=>{const heading=state.container.querySelector('.pf-list-heading h3');if(heading){heading.focus({preventScroll:true});heading.scrollIntoView({block:'start',behavior:'auto'});}}));
    if(companies.length>30){append(section,element('p','pf-empty','This network has '+companies.length+' companies. Choose a company for a readable map; the full relationship list remains below.'));return section;}
    const graph=element('div','pf-graph');graph.style.aspectRatio=width+' / '+height;
    const svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 '+width+' '+height);svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');svg.setAttribute('preserveAspectRatio','none');
    const defs=document.createElementNS(NS,'defs');
    Object.keys(flowNames).forEach(type=>{const marker=document.createElementNS(NS,'marker');marker.setAttribute('id','pf-arrow-'+type);marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','8');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','6');marker.setAttribute('markerHeight','6');marker.setAttribute('orient','auto-start-reverse');const arrow=document.createElementNS(NS,'path');arrow.setAttribute('d','M 0 0 L 10 5 L 0 10 z');arrow.setAttribute('class','pf-marker pf-flow-'+type);marker.append(arrow);defs.append(marker);});svg.append(defs);
    const nodes=graphPositions(companies,rows,width,height),byName=new Map(nodes.map(n=>[n.name,n]));const pairs=new Map(),labels=[];
    rows.forEach(row=>{const key=[row.from_entity,row.to_entity].sort().join('\u0000');if(!pairs.has(key))pairs.set(key,[]);pairs.get(key).push(row);});
    rows.forEach(row=>{
      const from=byName.get(row.from_entity),to=byName.get(row.to_entity);if(!from||!to)return;
      const pair=pairs.get([row.from_entity,row.to_entity].sort().join('\u0000')),pairIndex=pair.indexOf(row);
      let dx=to.x-from.x,dy=to.y-from.y,distance=Math.max(1,Math.hypot(dx,dy));
      const self=from===to;const bend=((pairIndex-(pair.length-1)/2)*58+(self?90:18))*(row.from_entity.localeCompare(row.to_entity)<=0?1:-1);
      const start={x:from.x+dx/distance*65,y:from.y+dy/distance*33};const end={x:to.x-dx/distance*72,y:to.y-dy/distance*39};
      const control={x:(from.x+to.x)/2-dy/distance*bend,y:(from.y+to.y)/2+dx/distance*bend};
      if(self){start.x=from.x-36;end.x=from.x+36;start.y=end.y=from.y-25;control.x=from.x;control.y=from.y-120;}
      const path=document.createElementNS(NS,'path');path.setAttribute('d','M '+start.x+' '+start.y+' Q '+control.x+' '+control.y+' '+end.x+' '+end.y);path.setAttribute('class','pf-edge pf-flow-'+row.flow_type);path.setAttribute('marker-end','url(#pf-arrow-'+row.flow_type+')');svg.append(path);
      const hit=document.createElementNS(NS,'path');hit.setAttribute('d',path.getAttribute('d'));hit.setAttribute('class','pf-edge-hit');const hitTitle=document.createElementNS(NS,'title');hitTitle.textContent=row.from_entity+' → '+row.to_entity+' · '+row.flow_label+' · '+row.amount_label;hit.append(hitTitle);hit.addEventListener('click',()=>openRelationship(row,state.container.querySelector('.pf-company-selector select')));svg.append(hit);
      if(!state.company)return; // Dense overview uses lines plus the complete list; focus reveals labels.
      const position=t=>({x:(1-t)*(1-t)*start.x+2*(1-t)*t*control.x+t*t*end.x,y:(1-t)*(1-t)*start.y+2*(1-t)*t*control.y+t*t*end.y});
      const candidates=[.5,.34,.66,.23,.77].map(position);const collision=p=>nodes.reduce((n,x)=>n+(Math.abs(x.x-p.x)<115&&Math.abs(x.y-p.y)<55?3:0),0)+labels.reduce((n,x)=>n+(Math.abs(x.x-p.x)<100&&Math.abs(x.y-p.y)<28?2:0),0);
      candidates.sort((a,b)=>collision(a)-collision(b));const point=candidates[0];labels.push(point);
      const label=button(state.company?row.ordinal+' · '+(row.instrument==='other'?row.flow_label:row.instrument_name):String(row.ordinal),'pf-edge-label'+(state.company?'':' pf-edge-label-compact')+' pf-flow-'+row.flow_type,event=>openRelationship(row,event.currentTarget));label.style.left=point.x/width*100+'%';label.style.top=point.y/height*100+'%';label.title=row.from_entity+' → '+row.to_entity+' · '+row.amount_label;label.setAttribute('aria-label','Relationship '+row.ordinal+': '+row.from_entity+' to '+row.to_entity+', '+row.instrument_name+', '+row.amount_label);graph.append(label);
    });
    graph.prepend(svg);
    nodes.forEach(node=>{const control=button('','pf-node'+(node.name===state.company?' pf-node-selected':''),()=>chooseCompany(node.name===state.company?'':node.name));control.style.left=node.x/width*100+'%';control.style.top=node.y/height*100+'%';control.setAttribute('aria-pressed',String(node.name===state.company));control.title=node.name;append(control,element('strong','',node.name),element('span','',node.count+' relationship'+(node.count===1?'':'s')));graph.append(control);});
    append(section,graph);return section;
  }
  function redraw() {
    if(!state.container)return;
    const existingDialog=state.dialog;if(existingDialog && existingDialog.open)existingDialog.close();
    state.container.replaceChildren();state.relationship='';
    const root=element('div','pf-explorer');
    const intro=append(element('div','pf-intro'),element('p','pf-kicker','Capital, commitments and capacity'),element('h2','','Follow each relationship.'),element('p','','Explore the sourced network, then choose a company. Arrows follow the recorded direction; money, services and guarantees stay distinct.'));
    const toolbar=element('div','pf-toolbar');const companyLabel=element('label','pf-company-selector');companyLabel.append(element('span','','Company focus'));
    const select=element('select','');select.setAttribute('aria-label','Company focus');append(select,new Option('Full network',''));companyCounts(state.rows).forEach(([name,count])=>select.append(new Option(name+' ('+count+')',name)));select.value=state.company;select.addEventListener('change',()=>chooseCompany(select.value));companyLabel.append(select);
    const recent=element('label','pf-recent-toggle');const checkbox=element('input','');checkbox.type='checkbox';checkbox.checked=state.recent;checkbox.disabled=dateNumber(state.snapshotDate)===null;checkbox.addEventListener('change',()=>{state.focusAfterRender='recent';navigate(viewRoute(state.company,checkbox.checked));});append(recent,checkbox,element('span','','Recent changes · 7 source days'));
    const reset=button('Full network','pf-reset',()=>{state.focusAfterRender='company';navigate(viewRoute('',false));});reset.disabled=!state.company&&!state.recent;append(toolbar,companyLabel,recent,reset);
    const scope=element('p','pf-scope','Recent changes means source dates in the seven calendar days ending '+dateLabel(state.snapshotDate)+'. A recent source date is not proof of a new transaction. No amounts are added together.');
    const rows=visibleRows();const companies=companyCounts(state.rows);const legend=element('div','pf-legend');['money','service','capacity','guarantee','credit','ownership','unspecified'].forEach(type=>append(legend,append(element('span','pf-legend-item'),element('i','pf-flow-'+type),document.createTextNode(flowNames[type]))));
    const summary=element('p','pf-summary');summary.setAttribute('role','status');summary.setAttribute('aria-live','polite');summary.textContent=rows.length+' of '+state.rows.length+' sourced relationships'+(state.company?' involving '+state.company:' across '+companies.length+' companies')+(state.recent?' · recent source dates':' · full retained history');
    const mobile=element('div','pf-mobile-companies');mobile.setAttribute('aria-label','Choose a company');companyCounts(state.recent?state.rows.filter(inRecentWindow):state.rows).forEach(([name,count])=>{const tile=button('','pf-company-tile',()=>chooseCompany(state.company===name?'':name));tile.setAttribute('aria-pressed',String(state.company===name));append(tile,element('strong','',name),element('span','',count+' relationships'));mobile.append(tile);});
    append(root,intro,toolbar,scope,legend,summary,mobile);
    if(rows.length)root.append(makeGraph(rows));
    const pathways=element('details','pf-risk-pathways');
    append(pathways,element('summary','','How trouble can travel through the network'),element('p','','Conditional scenarios to investigate. Their relevance depends on the actual contracts, operating conditions and funding terms.'));
    const paths=[['Power delay → financing pressure','If power or commissioning slips, GPUs may sit idle while revenue arrives later. Interest and refinancing needs can continue.'],['Service failure → weaker cash support','If availability or delivery terms are breached, contracts may allow credits, penalties or termination. That can reduce cash supporting the financing.']];
    paths.forEach(([title,description])=>append(pathways,append(element('section',''),element('h4','',title),element('p','',description))));
    pathways.append(element('p','pf-footnote','Connected counterparties do not by themselves establish circular cash movement or artificial transactions.'));root.append(pathways);
    const listHeading=append(element('div','pf-list-heading'),element('h3','',state.company?'Relationships involving '+state.company:'Every sourced relationship'),element('p','','Open a relationship for its stage, dates, source and uncertainty. Lines show connections, not verified circular cash flows.'));
    listHeading.querySelector('h3').tabIndex=-1;
    const list=element('div','pf-relationships');list.setAttribute('aria-label','Accessible relationship list');rows.forEach(row=>list.append(makeCard(row)));
    if(!rows.length)list.append(element('p','pf-empty',state.rows.length?'No relationships match this selection. Clear the company or recent-source filter to return to the full network.':'No sourced relationships are available in this snapshot. Missing data does not establish that no relationships exist.'));
    append(root,listHeading,list,element('p','pf-footnote','This map contains selected sourced relationships, not every relationship in the market. Overlapping commitments are never totaled. An overlap group flags a possible shared transaction; an absent group does not establish independence.'));
    state.dialog=makeDialog();append(state.container,root,state.dialog);
  }
  function parseRoute(hash) {
    const value=string(hash,location.hash).replace(/^#/,'');const [path,query='']=value.split('?');const parts=path.split('/');const params=new URLSearchParams(query);
    if(parts[0]!=='financing')return null;
    const decode=value=>{try{return decodeURIComponent(value||'');}catch(_){return '';}};
    return {company:parts[1]==='company'?decode(parts.slice(2).join('/')):params.get('company')||'',relationship:parts[1]==='relationship'?decode(parts.slice(2).join('/')):'',recent:params.get('recent')==='1'};
  }
  function updateRoute(hash=location.hash) {
    if(!state.container)return;
    const route=parseRoute(hash);
    if(!route){closeDetails(false);state.ownedDetail=false;return;}
    if(!companyCounts(state.rows).some(([name])=>name===route.company))route.company='';
    const changed=route.company!==state.company || route.recent!==state.recent;
    state.company=route.company;state.recent=route.recent;
    if(changed){redraw();if(state.focusAfterRender){const focus=state.container.querySelector(state.focusAfterRender==='recent'?'.pf-recent-toggle input':'.pf-company-selector select');if(focus)focus.focus({preventScroll:true});}}
    state.focusAfterRender='';
    const row=state.rows.find(row=>row.id===route.relationship);
    if(row)showDetails(row);else closeDetails(true);
  }
  function render({rows=[],container,sources=[],snapshotDate=null,onNavigate=null}={}) {
    if(!container || typeof container.replaceChildren!=='function')return;
    closeDetails(false);state.container=container;state.rows=normalizeRows(rows,sources);state.sources=sources;state.snapshotDate=snapshotDate;state.onNavigate=typeof onNavigate==='function'?onNavigate:null;
    const route=parseRoute(location.hash);state.company=route?route.company:'';state.recent=route?route.recent:false;
    if(!companyCounts(state.rows).some(([name])=>name===state.company))state.company='';
    redraw();updateRoute(location.hash);
    return {updateRoute,closeDetails,destroy};
  }
  function destroy(){closeDetails(false);if(state.dialog)state.dialog.remove();state.container=null;state.rows=[];state.dialog=null;state.returnFocus=null;state.ownedDetail=false;}
  window.addEventListener('hashchange',()=>updateRoute(location.hash));
  window.PulseFinance=Object.freeze({render,updateRoute,closeDetails,destroy,normalizeRows});
})();
