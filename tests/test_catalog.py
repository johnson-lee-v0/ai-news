"""Coverage and migration checks use synthetic records only."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from pulse.catalog import SOURCES, COVERAGE_GAPS
from pulse import ingest, storage


class CatalogTests(unittest.TestCase):
    def test_sources_are_unique_https_and_have_explicit_roles(self):
        self.assertEqual(len(SOURCES), len({s['id'] for s in SOURCES}))
        self.assertGreater(len(SOURCES), 8)
        for source in SOURCES:
            with self.subTest(source=source['id']):
                self.assertTrue(source['url'].startswith('https://'))
                self.assertIn(source['role'], ('primary','secondary','discovery'))
                self.assertTrue(source['topics'])
                self.assertTrue(source['quality_note'])
                self.assertTrue(source['coverage_note'])
                self.assertLessEqual(source['max_items'],100)

    def test_labs_funding_has_dedicated_30_day_discovery(self):
        source = next(s for s in SOURCES if s['id']=='discovery-lab-funding')
        query = parse_qs(urlsplit(source['url']).query)['q'][0]
        for term in ('OpenAI','Anthropic','valuation','funding','IPO','when:30d'):
            self.assertIn(term,query)
        self.assertEqual(source['role'],'discovery')
        self.assertEqual(source['kind'],'discovery_lead')
        self.assertTrue(any(g['id']=='anthropic-official' and g['status']=='manual_review' for g in COVERAGE_GAPS))

    def test_original_publishers_retained_without_claiming_full_text(self):
        source=next(s for s in SOURCES if s['id']=='discovery-lab-funding')
        payload=b'''<rss><channel><item><title>Synthetic lab valuation report - Example Wire</title><link>https://news.google.com/rss/articles/fixture</link><pubDate>Thu, 15 Oct 2026 21:00:26 GMT</pubDate><description>Fixture discovery title, not article body.</description><source url="https://example.org">Example Wire</source></item></channel></rss>'''
        article=ingest.parse_feed(payload,source,'2026-10-25T02:00:00Z')[0]
        self.assertEqual(article['publisher_name'],'Example Wire')
        self.assertEqual(article['publisher_url'],'https://example.org/')
        self.assertEqual(article['verification_status'],'discovery_lead')
        self.assertEqual(article['date_kind'],'search_feed_date')
        self.assertEqual(article['published_at'],'2026-10-15T21:00:26Z')
        self.assertEqual(article['first_seen_at'],'2026-10-25T02:00:00Z')
        self.assertTrue(article['url'].startswith('https://news.google.com/'))

    def test_partial_parse_and_feed_window_counts_are_visible(self):
        source={'id':'fixture','name':'Fixture','kind':'company_ir','url':'https://example.org/feed','format':'rss','max_items':2}
        payload=b'<rss><channel><item><title>Good fixture</title><link>https://example.org/a</link></item><item><title>Missing link</title></item><item><title>Beyond window</title><link>https://example.org/b</link></item></channel></rss>'
        records,stats=ingest.parse_feed(payload,source,'2026-10-25T02:00:00Z',with_stats=True)
        self.assertEqual(len(records),1)
        self.assertEqual(stats,{'rejected_count':1,'window_truncated_count':1})
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'test.db'
            run=ingest.refresh(db,[source],lambda _:payload,sleep=lambda _:None)
            self.assertEqual(run['rejected_count'],1)
            row=storage.dashboard_data(db)['sources'][0]
            self.assertEqual(row['rejected_count'],1)
            self.assertEqual(row['window_truncated_count'],1)

    def test_old_refresh_receipts_gain_zero_defaults_without_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.sqlite3'
            with sqlite3.connect(str(path)) as db:
                db.execute('CREATE TABLE refreshes (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT, new_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0, skipped_count INTEGER NOT NULL DEFAULT 0)')
                db.execute("INSERT INTO refreshes(started_at,new_count) VALUES('2026-10-24T01:00:00Z',7)")
            storage.initialize(path)
            storage.initialize(path)
            with storage.connect(path) as db:
                row=db.execute('SELECT * FROM refreshes').fetchone()
                self.assertEqual(row['new_count'],7)
                self.assertEqual(row['changed_count'],0)
                self.assertEqual(row['rejected_count'],0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM refreshes').fetchone()[0],1)


if __name__=='__main__':
    unittest.main()
