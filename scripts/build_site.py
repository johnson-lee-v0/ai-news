"""Build only reviewed public content; never open a local database or raw archive."""
from argparse import ArgumentParser
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from pulse.layers import LAYER_IDS, annotate as annotate_layers, tracking as layer_tracking
FORMAT = 'ai-stock-pulse-static-v1'
OUTPUTS = {'index.html', 'app.js', 'styles.css', 'favicon.svg', 'data/dashboard.json', 'build.json', '.nojekyll'}
TOP_FIELDS = {'reviewed_at', 'headline', 'bullets', 'notice', 'articles', 'sources', 'ledger', 'earnings'}
ARTICLE_FIELDS = {'id','title','url','published_at','date_kind','date_precision','source_id','source_name','source_role','lens','relevance','observation','summary','implication','beneficiaries','risks','counterevidence','confirms','refutes','uncertainty','entities','rank','event_date','event_start','event_end','reviewed_at','report_period','publication_note','claim_type','access_note','source_date_note','methodology_url','republished_at','quote_as_of','highlights','ai_layers'}
HIGHLIGHT_FIELDS = {'title','observation','claim_type','implication','source_url','source_date'}
RECORD_FIELDS = {'ledger':{'id','as_of','source_url','source_date','from_entity','to_entity','instrument','status','amount','currency','note','overlap_group','risk','payment_status','revenue_status','reviewed_at'},'earnings':{'id','as_of','source_url','source_date','company','period','metric','unit','reported','reported_period','guidance','guidance_period','consensus','consensus_source_url','consensus_as_of','consensus_period','note'}}
SOURCE_FIELDS = {'id','name','url','role','kind','reviewed_at','quality_note','topics','access_note','source_date','publication_note'}
DOMAINS = [('funding','Funding & valuation','Can operators fund their commitments?'),('demand','Paid demand','Does usage convert to collected cash?'),('capacity','Capacity delivery','Which projects reach service?'),('earnings','Earnings','What is reported versus forecast?'),('models','Model economics','Does capability become paid use?'),('policy','Policy & constraints','What rules affect access or delivery?')]


def iso(value):
    if not isinstance(value, str): raise ValueError('A reviewed/publication date must be an ISO string')
    try: parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: raise ValueError('Invalid ISO date')
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def safe_text(value):
    if isinstance(value, dict):
        for item in value.values(): safe_text(item)
    elif isinstance(value, list):
        for item in value: safe_text(item)
    elif isinstance(value, str):
        if re.search(r'/Users/|/home/|[A-Z]:\\Users\\|-----BEGIN .*PRIVATE KEY-----|\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,}|AKIA[A-Z0-9]{16})\b', value):
            raise ValueError('Private path or credential-like content is forbidden in a public artifact')
        if len(value) > 2500: raise ValueError('Public fields must be short summaries, not article bodies')


def public_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.hostname in ('localhost','127.0.0.1','::1') or parsed.hostname.endswith('.local'):
        raise ValueError('Public evidence requires a plain HTTPS URL')


def validate_public(raw):
    if not isinstance(raw, dict) or set(raw) != TOP_FIELDS: raise ValueError('Public brief must use the explicit reviewed schema')
    safe_text(raw)
    reviewed = iso(raw['reviewed_at'])
    if reviewed > datetime.now(timezone.utc): raise ValueError('Review date cannot be in the future')
    if not 1 <= len(raw['articles']) <= 20 or not 1 <= len(raw['sources']) <= 30: raise ValueError('Public snapshot must be small and populated')
    ids = set()
    for source in raw['sources']:
        if set(source) - SOURCE_FIELDS: raise ValueError('Unexpected public source field')
        for key in ('id','name','url','role','reviewed_at','quality_note','topics'):
            if key not in source: raise ValueError('Missing public source field: '+key)
        if source['id'] in ids or source['role'] not in ('primary','secondary'): raise ValueError('Sources must have unique IDs and reviewed evidence roles')
        if iso(source['reviewed_at']) > reviewed: raise ValueError('Source review is later than the snapshot')
        public_url(source['url']);ids.add(source['id'])
    article_ids = set()
    for item in raw['articles']:
        if set(item) - ARTICLE_FIELDS: raise ValueError('Unexpected public article field')
        for key in ('id','title','url','published_at','date_kind','source_id','source_role','lens','observation','summary','implication','counterevidence','confirms','refutes','uncertainty','entities','rank'):
            if key not in item: raise ValueError('Missing reviewed article field: '+key)
        if item['id'] in article_ids or item['source_id'] not in ids: raise ValueError('Duplicate article or unknown public source')
        if item['source_role'] not in ('primary','secondary') or iso(item['published_at']) > reviewed: raise ValueError('Unreviewed/future evidence cannot be published')
        public_url(item['url'])
        for date_key in ('reviewed_at','event_start','event_end'):
            if item.get(date_key) and iso(item[date_key]) > reviewed:
                raise ValueError('Article context dates cannot be later than review')
        if item.get('event_start') and item.get('event_end') and iso(item['event_start']) > iso(item['event_end']):
            raise ValueError('Event date range is reversed')
        if item.get('methodology_url'): public_url(item['methodology_url'])
        if 'ai_layers' in item:
            if not isinstance(item['ai_layers'], list) or any(key not in LAYER_IDS for key in item['ai_layers']) or len(set(item['ai_layers'])) != len(item['ai_layers']):
                raise ValueError('Public layer mappings must use unique framework IDs')
        if 'highlights' in item:
            if not isinstance(item['highlights'], list) or not 1 <= len(item['highlights']) <= 8:
                raise ValueError('Use one to eight short reviewed highlights')
            for highlight in item['highlights']:
                if not isinstance(highlight, dict) or set(highlight) != HIGHLIGHT_FIELDS or any(not isinstance(value, str) or not value.strip() for value in highlight.values()):
                    raise ValueError('Highlights require explicit claims, implications and dated sources')
                public_url(highlight['source_url'])
                if highlight['source_url'] not in {source['url'] for source in raw['sources']} or iso(highlight['source_date']) > reviewed:
                    raise ValueError('Highlight source must be reviewed and not future dated')
        article_ids.add(item['id'])
    # Validation functions inspect input only and do not create a database.
    import sys
    if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
    from pulse.research import validate
    for section in ('ledger','earnings'):
        for record in raw[section]:
            if set(record)-RECORD_FIELDS[section]: raise ValueError('Unexpected public financial-record field')
            if record.get('reviewed_at') and iso(record['reviewed_at']) > reviewed: raise ValueError('Record review cannot be later than snapshot')
            validate(section, deepcopy(record))
    return raw


def dashboard(raw, accounts, commit):
    stamp=raw['reviewed_at']
    articles=[]
    for value in sorted(raw['articles'], key=lambda x: x['rank']):
        item=deepcopy(value)
        item.update(editorial_rank=item.pop('rank'), first_seen_at=stamp, observed_at=stamp,
                    review_status='unreviewed', verification_status='source_reviewed_not_independently_audited',
                    inference_type='conditional_editorial_inference', article_ids=[item['id']], related_count=0,
                    score_reason='Editorial order in this selected, manually reviewed public snapshot. It is not a price forecast or a confidence score.')
        articles.append(annotate_layers(item))
    sources=[{**source,'status':'reviewed','item_count':sum(a['source_id']==source['id'] for a in articles)} for source in raw['sources']]
    domains=[]
    for key,name,question in DOMAINS:
        mapped=[s['id'] for s in sources if key in s.get('topics',[])]
        domains.append({'id':key,'name':name,'question':question,'status':'snapshot' if mapped else 'gap','connected_sources':mapped,
                        'note':'Reviewed sources are included for this topic; no live ingestion or complete coverage is implied.' if mapped else 'No reviewed item for this topic in the current public snapshot.'})
    safe_text(accounts)
    return {'as_of':stamp,'publication':{'mode':'static','reviewed_at':stamp,'notice':raw['notice'],'repository_url':'https://github.com/johnson-lee-v0/ai-news','commit':commit,'draft':commit=='uncommitted'},
            'articles':articles,'stories':deepcopy(articles),'sources':sources,'refreshes':[], 'leads':[], 'notes':[], 'reviews':{},
            'ledger':raw['ledger'],'earnings':raw['earnings'],'accounts':accounts,'layer_tracking':layer_tracking(articles,sources,static=True),
            'x_access':{'status':'not_connected','automatic':False,'can_capture':False,'detail':'This public snapshot does not collect X posts, trends or engagement. Profile links are a reading list; saved leads remain a local-app feature.'},
            'coverage':{'domains':domains,'gaps':['This is a selected manually reviewed snapshot, not a live or exhaustive feed.','X trends, live market/CDS quotes and consensus are not connected.','Local feed refreshes do not automatically publish to this site.'],'note':'Included sources were reviewed for this publication. These are not live endpoint-health checks.'},
            'watchlist':{'entities':sorted({e for a in articles for e in a['entities']}),'topics':[x[0] for x in DOMAINS]},
            'brief':{'headline':raw['headline'],'bullets':raw['bullets'],'coverage_note':raw['notice'],'priority_items':deepcopy(articles),'priority_questions':[]},
            'stats':{'articles':len(articles),'total_articles':len(articles),'story_count':len(articles),'new_items':0,'changed_items':0,'source_ok':0,'source_total':len(sources),'needs_review':0,'recent_items':0,'discovery_items':0,'last_refresh':None}}


def revision():
    value=os.environ.get('GITHUB_SHA')
    if not value:
        try:
            dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
            value='uncommitted' if dirty else subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.CalledProcessError): value='uncommitted'
    if value!='uncommitted' and not re.fullmatch(r'[0-9a-f]{40}',value): raise ValueError('Invalid public commit identifier')
    return value


def build(output, source=None):
    output=Path(output)
    source=Path(source) if source else ROOT/'public/brief.json'
    raw=validate_public(json.loads(source.read_text(encoding='utf-8')))
    if output.exists():
        existing={str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()}
        if existing-OUTPUTS or any(p.is_symlink() for p in output.rglob('*')): raise ValueError('Build output contains unexpected files; refusing to publish or remove them')
        if existing and (not (output/'build.json').exists() or json.loads((output/'build.json').read_text()).get('format')!=FORMAT): raise ValueError('Build output is not an owned static artifact')
    output.mkdir(parents=True,exist_ok=True)
    (output/'data').mkdir(exist_ok=True)
    account_data=json.loads((ROOT/'config/accounts.json').read_text())
    accounts=account_data['accounts'] if isinstance(account_data,dict) else account_data
    commit=revision()
    payload=dashboard(raw,accounts,commit)
    (output/'data/dashboard.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
    html=(ROOT/'static/index.html').read_text().replace('<html lang="en">','<html lang="en" data-mode="static">')
    html=html.replace('href="/styles.css"','href="./styles.css"').replace('src="/app.js"','src="./app.js"')
    html=html.replace('</head>', '<link rel="icon" type="image/svg+xml" href="./favicon.svg">\n<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\'; style-src \'self\'; img-src \'self\' data:; connect-src \'self\'; base-uri \'none\'; form-action \'none\'">\n</head>')
    if 'data-mode="static"' not in html: raise ValueError('Static HTML marker missing')
    (output/'index.html').write_text(html)
    for name in ('app.js','styles.css'): (output/name).write_bytes((ROOT/'static'/name).read_bytes())
    (output/'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#f5f4ee"/><path stroke="#226d60" stroke-width="4" stroke-linecap="round" d="M8 20V13M16 24V8M24 27V5"/></svg>\n')
    (output/'.nojekyll').write_text('')
    files={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file() and p.name!='build.json'}
    manifest={'format':FORMAT,'commit':commit,'reviewed_at':raw['reviewed_at'],'files':files}
    (output/'build.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return manifest


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'_site')
    args=parser.parse_args(); result=build(args.output)
    print(json.dumps({'artifact_files':len(result['files'])+1,'reviewed_at':result['reviewed_at'],'commit':result['commit']}))
