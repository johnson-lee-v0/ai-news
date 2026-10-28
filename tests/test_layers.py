"""Layer tags must not manufacture operating metrics or source health."""
from datetime import datetime, timezone
import unittest
from pulse.layers import annotate, tracking, LAYER_IDS

NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


class LayerTests(unittest.TestCase):
    def test_one_story_can_span_layers_without_fabricated_metrics(self):
        item=annotate({'title':'GPU data center delayed by grid connection','source_id':'dcd-news','published_at':'2026-10-24'})
        self.assertEqual(item['ai_layers'],['energy','chips','infrastructure'])
        result=tracking([item],[{'id':'dcd-news','role':'secondary','status':'ok','last_success_at':'2026-10-25T11:00:00Z'}],NOW)
        self.assertEqual(len(result['layers']),5)
        self.assertEqual(result['layers'][0]['status'],'connected')
        self.assertIn('Unavailable',result['layers'][0]['metric_status'])
        self.assertNotIn('operating_mw',result['layers'][0])

    def test_layer_takeaways_keep_implications_and_missing_metrics_separate(self):
        cards=tracking([],[],NOW,static=True)['layers']
        self.assertTrue(all(card['takeaway'] and '?' not in card['takeaway'] for card in cards))
        self.assertTrue(all('question' not in card for card in cards))
        self.assertTrue(all(card['status']=='gap' and card['article_count']==0 for card in cards))
        self.assertTrue(all('Unavailable' in card['metric_status'] for card in cards))
        self.assertIn('debt service',next(card for card in cards if card['id']=='infrastructure')['takeaway'])

    def test_administrative_words_do_not_become_model_or_app_tags(self):
        item=annotate({'title':'Campus permit application and default model update','summary':'PowerPoint presentation'})
        self.assertEqual(item['ai_layers'],[])

    def test_editorial_mapping_is_explicit_and_nonexclusive(self):
        item=annotate({'title':'Berlin review','ai_layers':['applications','chips']})
        self.assertEqual(item['ai_layers'],['chips','applications'])
        self.assertIn('Curator',item['layer_match_basis'])

    def test_stale_and_failed_sources_are_not_connected(self):
        for source in [{'id':'openai-news','role':'primary','status':'error','last_success_at':'2026-10-25T11:00:00Z'},
                       {'id':'openai-news','role':'primary','status':'ok','last_success_at':'2026-10-20T11:00:00Z'}]:
            card=tracking([], [source], NOW)['layers'][3]
            self.assertEqual(card['status'],'gap')
            self.assertEqual(card['article_count'],0)

    def test_discovery_and_static_reference_are_not_live_verification(self):
        item=annotate({'title':'OpenAI valuation talks','source_id':'discovery-lab-funding','published_at':'2026-10-22'})
        source={'id':'discovery-lab-funding','role':'discovery','status':'ok','last_success_at':'2026-10-25T11:00:00Z'}
        self.assertEqual(tracking([item],[source],NOW)['layers'][3]['status'],'discovery_only')
        self.assertEqual(tracking([item],[source],NOW,static=True)['layers'][3]['status'],'reviewed_snapshot')
        self.assertEqual(tracking([],[],NOW,static=True)['layers'][3]['status'],'gap')

    def test_unknown_and_future_dates_remain_unavailable(self):
        items=[annotate({'title':'GPU launch','published_at':date}) for date in [None,'bad date','2027-01-01']]
        self.assertIsNone(tracking(items,[],NOW)['layers'][1]['last_source_date'])
        self.assertEqual(tuple(x['id'] for x in tracking([],[],NOW)['layers']),LAYER_IDS)

    def test_group_keeps_tags_and_attribution_from_other_appearances(self):
        from pulse.analysis import compose
        sources=[{'id':'issuer','role':'primary','status':'ok','last_success_at':'2026-10-25T11:00:00Z'},
                 {'id':'reporter','role':'secondary','status':'ok','last_success_at':'2026-10-25T11:00:00Z'}]
        articles=[{'id':'a','title':'Campus update','summary':'Construction continues at the data center','source_id':'issuer','source_role':'primary','published_at':'2026-10-24','url':'https://example.com/a'},
                  {'id':'b','title':'Campus update','summary':'Fuel cell power ready','source_id':'reporter','source_role':'secondary','published_at':'2026-10-24','url':'https://example.com/b'}]
        result=compose({'articles':articles,'sources':sources},NOW)
        self.assertEqual(len(result['stories']),1)
        group=result['stories'][0]
        self.assertEqual(group['id'],'a')
        self.assertIn('energy',group['ai_layers'])
        card=result['layer_tracking']['layers'][0]
        self.assertEqual(card['article_count'],1)
        self.assertEqual(card['source_ids'],['reporter'])
        self.assertEqual(group['layer_matches'][1]['article_id'],'b')

if __name__=='__main__': unittest.main()
