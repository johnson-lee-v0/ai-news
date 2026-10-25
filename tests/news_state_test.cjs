'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const PulseVisit = require('../static/visit-state.js');
const AT = '2026-10-25T17:00:00Z';
const KEY = 'test-visit';
function storage(initial) {
  const values = new Map(initial === undefined ? [] : [[KEY, initial]]);
  return {getItem:key=>values.has(key)?values.get(key):null, setItem:(key,value)=>values.set(key,value), removeItem:key=>values.delete(key), values};
}
const item = (extra={}) => ({id:'article-a',title:'OpenAI funding target $1.25tn',summary:'Funding is proposed, not closed.',...extra});
const tracker = store => PulseVisit.create(store,KEY,AT);
function baseline(store, items=[item()]) {tracker(store).commit(items);return tracker(store);}
let passed=0;
function test(name, run) {run();passed+=1;process.stdout.write('PASS '+name+'\n');}

test('first visit never counts all existing items as new',()=>{
  const store=storage(), visit=tracker(store);
  assert.deepEqual(visit.compare([item()]),{firstVisit:true,storageAvailable:true,newIds:[],changedIds:[],baselineAt:null});
  assert.equal(visit.commit([item()]).persisted,true);
  assert.equal(visit.compare([item()]).firstVisit,true);
  assert.equal(tracker(store).compare([item()]).firstVisit,false);
});
test('same data on reload and same-page back/render are stable',()=>{
  const store=storage(), visit=baseline(store);
  const updated=[item(),item({id:'article-b'})];
  assert.deepEqual(visit.compare(updated).newIds,['article-b']);
  visit.commit(updated);
  assert.deepEqual(visit.compare(updated).newIds,['article-b']);
  assert.deepEqual(tracker(store).compare(updated).newIds,[]);
});
test('new and changed IDs are separate, with meaningful numbers and negation retained',()=>{
  const visit=baseline(storage());
  const result=visit.compare([item({summary:'Funding closed at $1.4tn.'}),item({id:'article-b'})]);
  assert.deepEqual(result.changedIds,['article-a']);
  assert.deepEqual(result.newIds,['article-b']);
});
test('fetch, publication, build, review, scoring and grouping metadata are ignored',()=>{
  const visit=baseline(storage());
  const result=visit.compare([item({published_at:'2030-01-01',first_seen_at:'2030-01-01',observed_at:'2030-01-01',
    reviewed_at:'2030-01-01',imported_at:'2030-01-01',revised_at:'2030-01-01',as_of:'2030-01-01',
    content_hash:'different',story_id:'different',source_id:'primary',url:'https://example.com/new',
    source_role:'primary',score:999,rank:1,review_status:'reviewed',article_ids:['article-a','alias-new'],
    ai_layers:['models'],related_count:22,implication:'New generated rule text'})]);
  assert.deepEqual(result.newIds,[]);assert.deepEqual(result.changedIds,[]);
});
test('cosmetic case, whitespace and publisher suffix do not create a revision',()=>{
  const visit=baseline(storage());
  assert.deepEqual(visit.compare([item({title:'  OPENAI  funding target $1.25tn - Reuters',publisher_name:'Reuters',summary:'Funding is proposed,\nnot closed.'})]).changedIds,[]);
});
test('curated notes and public items include analysis but not review timestamps',()=>{
  const original=item({id:'note:review',visitKind:'curated',observation:'Proposed target.',implication:'Funding timing could constrain orders.'});
  const visit=baseline(storage(),[original]);
  assert.deepEqual(visit.compare([{...original,reviewed_at:'2030-01-01',as_of:'2030-01-01'}]).changedIds,[]);
  assert.deepEqual(visit.compare([{...original,implication:'Funding is now completed.'}]).changedIds,['note:review']);
  assert.deepEqual(visit.compare([{...original,quote_as_of:'2026-10-22'}]).changedIds,['note:review']);
});
test('curated highlight order/source links are ignored while claims are preserved',()=>{
  const first={title:'Power',observation:'First block ready',implication:'Commissioning remains',claim_type:'management_claim',source_url:'https://example.com/a'};
  const second={title:'Chips',observation:'Shipment planned',implication:'Await acceptance',claim_type:'plan'};
  const original=item({visitKind:'curated',highlights:[first,second]});
  const visit=baseline(storage(),[original]);
  assert.deepEqual(visit.compare([{...original,highlights:[second,{...first,source_url:'https://example.com/b',source_date:'2030-01-01'}]}]).changedIds,[]);
  assert.deepEqual(visit.compare([{...original,highlights:[{...first,observation:'300MW operational'},second]}]).changedIds,['article-a']);
});
test('representative flips and added duplicate appearances do not make new news',()=>{
  const store=storage(), original=item({article_ids:['article-a','article-b']});
  const visit=baseline(store,[original]);
  const flip=item({id:'article-b',article_ids:['article-b','article-a','article-c'],summary:'Alternate publisher wording.'});
  assert.deepEqual(visit.compare([flip]).newIds,[]);assert.deepEqual(visit.compare([flip]).changedIds,[]);
  visit.commit([flip]);
  const next=tracker(store);
  assert.deepEqual(next.compare([original]).changedIds,[]);
  assert.deepEqual(next.compare([flip]).changedIds,[]);
  assert.deepEqual(next.compare([{...flip,summary:'Funding was canceled.'}]).changedIds,['article-b']);
  assert.deepEqual(next.compare([item({id:'article-c'})]).newIds,[]);
});
test('date corrections can change story IDs without changing visit identity',()=>{
  const original=item({story_id:'day1',published_at:'2026-10-24'}), visit=baseline(storage(),[original]);
  const result=visit.compare([{...original,story_id:'day2',published_at:'2026-10-25'}]);
  assert.deepEqual(result.newIds,[]);assert.deepEqual(result.changedIds,[]);
});
test('remembering all loaded IDs prevents date-only promotion from inventing a new story',()=>{
  const store=storage(),background=item({relevance:'background',published_at:'2025-01-01'});
  const first=tracker(store);assert.deepEqual(first.compare([]).newIds,[]);first.commit([background]);
  const result=tracker(store).compare([{...background,relevance:'material',published_at:'2026-10-25'}]);
  assert.deepEqual(result.newIds,[]);assert.deepEqual(result.changedIds,[]);
});
test('corrupt, malformed, oversized and prototype-like storage resets gracefully',()=>{
  const cases=['not json','null','[]','x'.repeat(750001),JSON.stringify({version:99,at:AT,entries:[]}),
    JSON.stringify({version:1,at:'invalid',entries:[]}),JSON.stringify({version:1,at:AT,entries:[['__proto__','a'.repeat(16)]]}),
    JSON.stringify({version:1,at:AT,entries:[['a','not-a-hash']]}),JSON.stringify({version:1,at:AT,entries:Array.from({length:2001},(_,i)=>['id'+i,null])})];
  for(const raw of cases){const store=storage(raw),visit=tracker(store);assert.equal(visit.compare([item()]).firstVisit,true);assert.deepEqual(visit.compare([item()]).newIds,[]);assert.equal(visit.commit([item()]).persisted,true);}
  assert.equal({}.polluted,undefined);
});
test('denied storage and quota failures keep comparison usable without throwing',()=>{
  const denied=PulseVisit.create({getItem(){throw Error('denied');},setItem(){throw Error('denied');}},KEY,AT);
  assert.equal(denied.compare([item()]).storageAvailable,false);assert.equal(denied.commit([item()]).persisted,false);
  const store=storage(),visit=baseline(store);store.setItem=()=>{throw Error('quota');};
  assert.equal(visit.commit([item()]).storageAvailable,false);
  assert.deepEqual(visit.compare([item({summary:'Canceled.'})]).changedIds,['article-a']);
});
test('only bounded IDs and hashes are persisted, never content or URLs',()=>{
  const store=storage(),visit=tracker(store);
  const items=Array.from({length:2100},(_,i)=>item({id:'item-'+i,article_ids:['alias-'+i],summary:'PRIVATE_SENTINEL_SOURCE_TEXT'}));
  visit.commit(items);
  const raw=store.values.get(KEY),saved=JSON.parse(raw);
  assert.ok(saved.entries.length<=2000);assert.ok(!raw.includes('PRIVATE_SENTINEL'));assert.ok(!raw.includes('OpenAI'));assert.ok(!raw.includes('https:'));
  assert.deepEqual(Object.keys(saved).sort(),['at','entries','version']);
  assert.ok(saved.entries.every(([id,value])=>typeof id==='string'&&(value===null||/^[a-f0-9]{16}$/.test(value))));
});
test('URL-shaped IDs and aliases are excluded while opaque note namespaces survive',()=>{
  const urls=['https://example.com/private-id-marker','HTTPS://example.com/private-id-marker',
    'https:example.com/private-id-marker','file:///private-id-marker','custom://private-id-marker',
    'note:https://example.com/private-id-marker'];
  const store=storage(),visit=tracker(store);
  visit.commit([...urls.map(id=>item({id})),item({id:'note:opaque',article_ids:urls,aliases:[...urls,'article-opaque']})]);
  const raw=store.values.get(KEY),saved=JSON.parse(raw);
  assert.ok(!raw.includes('private-id-marker'));
  assert.deepEqual(saved.entries.map(([id])=>id).sort(),['article-opaque','note:opaque']);
  assert.deepEqual(tracker(store).compare([item({id:'note:opaque'}),...urls.map(id=>item({id}))]).newIds,[]);
  const legacy=storage(JSON.stringify({version:1,at:AT,entries:[[urls[0],null]]}));
  const restored=tracker(legacy);assert.equal(restored.compare([item()]).firstVisit,true);
  restored.commit([item()]);assert.ok(!legacy.values.get(KEY).includes('private-id-marker'));
});
test('hostile IDs/content/links remain inert and are not stored as text',()=>{
  const store=storage(),visit=tracker(store);
  const injected=item({summary:'<img src=x onerror="globalThis.hacked=1">',url:'javascript:globalThis.hacked=1'});
  visit.commit([injected,item({id:'__proto__'}),item({id:'<script>alert(1)</script>'})]);
  assert.equal(globalThis.hacked,undefined);assert.equal(JSON.parse(store.values.get(KEY)).entries.length,1);
  assert.ok(!store.values.get(KEY).includes('onerror'));assert.ok(!store.values.get(KEY).includes('javascript:'));
});
test('clear removes only the owned key and establishes first-visit behavior',()=>{
  const store=storage();store.values.set('other-app','preserve');const visit=baseline(store);
  visit.clear();assert.equal(store.values.has(KEY),false);assert.equal(store.values.get('other-app'),'preserve');assert.equal(visit.compare([item()]).firstVisit,true);
});
test('browser global loads with no DOM, network, cookies or storage side effects',()=>{
  const sandbox={};vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/visit-state.js'),'utf8'),sandbox);
  assert.equal(typeof sandbox.PulseVisit.create,'function');
  assert.equal(sandbox.PulseVisit.create(null,KEY,AT).compare([]).storageAvailable,false);
});
process.stdout.write(JSON.stringify({passed,scope:'offline synthetic visit-state tests'})+'\n');
