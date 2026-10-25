import copy
import json
from pathlib import Path
import tempfile
import unittest

from pulse import research, storage
from pulse.analysis import compose, enrich
from datetime import datetime, timezone


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'test.sqlite3'

    def test_x_lead_canonical_duplicate_not_verified(self):
        a = research.add_lead(self.db, 'https://twitter.com/fixture/status/12345?s=20', 'Needs evidence')
        b = research.add_lead(self.db, 'https://x.com/fixture/status/12345', 'Different note')
        self.assertEqual(a['id'], b['id'])
        self.assertTrue(b['duplicate'])
        self.assertEqual(b['note'], 'Needs evidence')
        self.assertEqual(b['status'], 'unverified')
        self.assertEqual(len(research.read(self.db)['leads']), 1)

    def test_lead_rejects_unsafe_or_nonpost_links(self):
        for value in ['javascript:alert(1)', 'https://x.com', 'https://x.com.evil.test/a/status/1', 'https://user:pass@x.com/a/status/1', 'http://x.com/a/status/1']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                research.add_lead(self.db, value)

    def test_consensus_requires_independent_dated_provenance_and_period(self):
        row = {'id':'test', 'company':'Fixture Co', 'period':'FY2024 Q1', 'metric':'revenue', 'unit':'USD million', 'reported':2, 'consensus':3, 'source_url':'https://example.com/release', 'source_date':'2024-05-01', 'as_of':'2024-05-02'}
        with self.assertRaisesRegex(ValueError, 'consensus_source_url'):
            research.import_records(self.db, {'earnings':[row]})
        row.update(consensus_source_url='https://example.org/estimate', consensus_as_of='2024-04-30', consensus_period='FY2024 Q1')
        self.assertEqual(research.import_records(self.db, {'earnings':[row]})['changed'], 1)

    def test_curation_is_atomic_and_versions_preserved(self):
        row = {'id':'fixture-note', 'title':'Synthetic test', 'observation':'Fixture observation', 'implication':'Conditional only', 'as_of':'2024-01-02', 'sources':[{'url':'https://example.com/source', 'title':'Fixture', 'date':'2024-01-01'}], 'uncertainty':'Not real'}
        result = research.import_records(self.db, {'notes':[row]})
        self.assertEqual(result['changed'], 1)
        self.assertEqual(research.import_records(self.db, {'notes':[row]})['changed'], 0)
        row['observation'] = 'Corrected fixture'
        research.import_records(self.db, {'notes':[row]})
        with storage.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM research_versions').fetchone()[0], 2)
        broken = copy.deepcopy(row)
        broken['id'] = 'new-note'
        broken['sources'] = []
        with self.assertRaises(ValueError):
            research.import_records(self.db, {'notes':[dict(row, id='would-be-new'), broken]})
        self.assertEqual(len(research.read(self.db)['notes']), 1)

    def test_future_asof_not_allowed(self):
        with self.assertRaises(ValueError):
            research.date('2999-01-01', 'as_of')


class AnalysisTests(unittest.TestCase):
    def test_empty_never_claims_current_news(self):
        result = compose({'articles':[], 'sources':[], 'refreshes':[]})
        self.assertEqual(result['stats']['articles'], 0)
        self.assertIn('starts with a refresh', result['brief']['headline'])

    def test_undated_recently_discovered_is_not_fresh(self):
        now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        result = enrich({'title':'AI capacity announced', 'summary':'', 'first_seen_at':now.isoformat(), 'published_at':None}, now)
        self.assertTrue(result['stale'])
        self.assertIn('0 recency', result['score_reason'])
        self.assertEqual(result['inference_type'], 'conditional_rule')

    def test_future_dates_are_not_recent(self):
        now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        result = compose({'articles':[{'title':'Future AI news', 'published_at':'2099-01-01T00:00:00Z'}], 'sources':[], 'refreshes':[{'new_count':1, 'finished_at':now.isoformat()}]}, now)
        self.assertEqual(result['stats']['recent_items'], 0)
        self.assertIn('No feed or filing date', result['brief']['headline'])

    def test_near_future_publication_does_not_round_into_current_news(self):
        now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        result = compose({'articles':[{'title':'Future AI news', 'published_at':'2026-10-24T01:00:00Z'}], 'sources':[], 'refreshes':[]}, now)
        self.assertEqual(result['stats']['recent_items'], 0)

    def test_financing_is_not_revenue(self):
        result = enrich({'title':'Company announces debt financing', 'summary':'New capacity investment'})
        self.assertEqual(result['lens'], 'funding')
        self.assertIn('does not establish', result['implication'])
        self.assertIn('not a market-impact', result['score_reason'].lower())

    def test_ai_keyword_does_not_match_said(self):
        self.assertEqual(enrich({'title':'Company said hello'})['lens'], 'other')


if __name__ == '__main__':
    unittest.main()
