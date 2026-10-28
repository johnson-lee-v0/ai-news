import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pulse import storage, ingest, research
from pulse.analysis import compose, enrich, coverage, group_stories

NOW = datetime(2026, 10, 25, 3, tzinfo=timezone.utc)

def article(id='one', title='OpenAI raises funding at lower valuation', **kwargs):
    return {'id':id,'title':title,'summary':'','published_at':'2026-10-24T02:00:00Z','source_role':'secondary','content_hash':'hash-one',**kwargs}


class V2AnalysisTests(unittest.TestCase):
    def test_valuation_is_funding_not_direct_demand_collapse(self):
        a = enrich(article(), NOW)
        self.assertEqual(a['lens'],'funding')
        self.assertEqual(a['relevance'],'material')
        self.assertIn('bargaining alone',a['implication'])

    def test_promotional_conference_is_background(self):
        a = enrich(article(title='Who founders will hear from at TechCrunch Founder Summit 2026',summary='OpenAI funding, valuation, debt and artificial intelligence'),NOW)
        self.assertEqual(a['relevance'],'background')

    def test_non_ai_funding_is_not_material_ai_story(self):
        a = enrich(article(title='Coffee shop announces new funding and valuation'),NOW)
        self.assertEqual(a['relevance'],'background')

    def test_scheduled_call_is_not_reported_earnings(self):
        a = enrich(article(title='AMD to Report Fiscal Third Quarter Financial Results'),NOW)
        self.assertIn('scheduled reporting event',a['implication'])
        self.assertEqual(a['relevance'],'background')

    def test_discovery_does_not_become_verified(self):
        a = enrich(article(source_role='discovery',verification_status='discovery_lead'),NOW)
        self.assertEqual(a['verification_status'],'discovery_lead')
        self.assertIn('Search-feed discovery lead',a['uncertainty'])

    def test_distinct_amounts_not_merged(self):
        items=[enrich(article(id='a',title='OpenAI funding valuation $1.4 trillion'),NOW),enrich(article(id='b',title='OpenAI funding valuation $1.25 trillion'),NOW)]
        self.assertEqual(len(group_stories(items)),2)

    def test_exact_repeated_headlines_prefer_original_publisher(self):
        items=[enrich(article(id='a',source_role='discovery',title='OpenAI valuation declines - CNBC',publisher_name='CNBC'),NOW),enrich(article(id='b',title='OpenAI valuation declines',source_name='CNBC'),NOW)]
        group=group_stories(items)[0]
        self.assertEqual(group['id'],'b')
        self.assertEqual(group['related_count'],1)
        self.assertIn('not independent',group['grouping_note'])

    def test_brief_diversity_and_loaded_total_distinction(self):
        items=[article(id=str(i),title='OpenAI funding valuation '+str(i)) for i in range(6)]+[article(id='meta',title='Meta cuts capex guidance'),article(id='anthropic',title='Anthropic IPO valuation expectations')]
        result=compose({'articles':items,'sources':[],'refreshes':[{'new_count':8,'changed_count':1}],'total_count':600},NOW)
        selected=result['brief']['priority_items']
        self.assertEqual(sum('OpenAI' in a['title'] for a in selected),1)
        self.assertEqual(result['stats']['total_articles'],600)
        self.assertEqual(result['stats']['articles'],8)
        self.assertEqual(result['stats']['changed_items'],1)

    def test_takeaways_are_relevant_context_not_verified_headlines(self):
        result=compose({'articles':[article(source_role='discovery',verification_status='discovery_lead')],'sources':[]},NOW)
        takeaways=result['brief']['priority_takeaways']
        self.assertEqual([item['topic'] for item in takeaways],['funding'])
        self.assertEqual(takeaways[0]['basis'],'general_context')
        self.assertIn('conditional commitments',takeaways[0]['takeaway'])
        self.assertNotIn('?',takeaways[0]['takeaway'])
        self.assertEqual(result['articles'][0]['verification_status'],'discovery_lead')
        self.assertNotIn('priority_questions',result['brief'])
        self.assertEqual(compose({'articles':[],'sources':[]},NOW)['brief']['priority_takeaways'],[])
        dismissed=article(review_status='dismissed',reviewed_hash='hash-one')
        self.assertEqual(compose({'articles':[dismissed],'sources':[]},NOW)['brief']['priority_takeaways'],[])

    def test_coverage_takeaways_do_not_imply_missing_evidence_was_found(self):
        result=coverage([],NOW)
        self.assertTrue(all(domain['status']=='gap' for domain in result['domains']))
        self.assertTrue(all(domain['takeaway'] and '?' not in domain['takeaway'] for domain in result['domains']))
        self.assertTrue(all('question' not in domain for domain in result['domains']))
        self.assertIn('Source health',result['note'])

    def test_product_maps_to_models_and_stale_sources_not_covered(self):
        source={'id':'official-model','topics':['product'],'role':'primary','status':'ok','last_success_at':NOW.isoformat()}
        result=coverage([source],NOW)
        self.assertEqual(next(d for d in result['domains'] if d['id']=='models')['status'],'covered')
        source['last_success_at']='2026-01-01T00:00:00Z'
        self.assertEqual(next(d for d in coverage([source],NOW)['domains'] if d['id']=='models')['status'],'gap')

    def test_dismissed_article_reappears_after_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'test.sqlite3'
            source={'id':'test','name':'Fixture','url':'https://example.com/feed','kind':'company_ir','entity':'OpenAI'}
            storage.register_sources(db,[source])
            first=ingest.make_article(source,'OpenAI valuation1.4','https://example.com/a','','2026-10-24',NOW.isoformat())
            with storage.connect(db) as conn: storage.save_article(conn,first,'raw1')
            research.review_article(db,first['id'],'dismissed')
            before=compose({**storage.dashboard_data(db),**research.read(db)},NOW)
            self.assertEqual(before['articles'][0]['review_status'],'dismissed')
            second=ingest.make_article(source,'OpenAI valuation1.25','https://example.com/a','','2026-10-24',NOW.isoformat())
            with storage.connect(db) as conn: storage.save_article(conn,second,'raw2')
            after=compose({**storage.dashboard_data(db),**research.read(db)},NOW)
            self.assertEqual(after['articles'][0]['review_status'],'unreviewed')
            self.assertEqual(after['articles'][0]['verification_status'],'publisher_metadata')
            with self.assertRaises(ValueError): research.review_article(db,first['id'],'verified')
            with self.assertRaises(ValueError): research.review_article(db,'does-not-exist','reviewed')

    def test_group_review_is_atomic_and_dismisses_all_current_appearances(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'test.sqlite3'
            source={'id':'test','name':'Fixture','url':'https://example.com/feed','kind':'company_ir','entity':'OpenAI'}
            storage.register_sources(db,[source])
            rows=[ingest.make_article(source,'OpenAI funding valuation','https://example.com/'+str(i),'Different appearance '+str(i),'2026-10-24',NOW.isoformat()) for i in range(2)]
            with storage.connect(db) as conn:
                for row in rows: storage.save_article(conn,row,'raw')
            ids=[row['id'] for row in rows]
            with self.assertRaises(ValueError): research.review_articles(db,ids+['missing'],'dismissed')
            self.assertEqual(research.read(db)['reviews'],{})
            result=research.review_articles(db,ids,'dismissed')
            self.assertEqual(result['count'],2)
            after=compose({**storage.dashboard_data(db),**research.read(db)},NOW)
            self.assertEqual(len(after['stories']),1)
            self.assertEqual(after['stories'][0]['review_status'],'dismissed')
            self.assertEqual(set(after['stories'][0]['article_ids']),set(ids))
            self.assertEqual(after['brief']['priority_items'],[])

if __name__ == '__main__': unittest.main()
