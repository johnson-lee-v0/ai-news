"""Synthetic fixtures stay in tests; no fake articles enter the real database."""
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from pulse import ingest, storage


SOURCE = {"id": "test-rss", "name": "Synthetic test feed", "url": "https://example.com/feed",
          "kind": "company_ir", "format": "rss", "entity": "Fixture Corp"}
OBSERVED = "2026-10-24T12:00:00Z"


def rss(title="Synthetic GPU capacity announcement", url="https://example.com/story?utm_source=feed", date="Fri, 23 Oct 2026 09:30:00 -0400"):
    return ("<rss><channel><item><title>" + title + "</title><link>" + url + "</link><pubDate>" + date +
            "</pubDate><description>&lt;p&gt;Synthetic text only.&lt;/p&gt;</description></item></channel></rss>").encode()


class ParseTests(unittest.TestCase):
    def test_rss_canonical_url_timezone_and_markup(self):
        article = ingest.parse_feed(rss(), SOURCE, OBSERVED)[0]
        self.assertEqual(article["url"], "https://example.com/story")
        self.assertEqual(article["published_at"], "2026-10-23T13:30:00Z")
        self.assertEqual(article["date_precision"], "second")
        self.assertEqual(article["date_kind"], "feed_date")
        self.assertEqual(article["observed_at"], OBSERVED)
        self.assertEqual(article["summary"], "Synthetic text only.")
        self.assertIn("capacity", article["tags"])

    def test_atom_and_missing_publication_date(self):
        payload = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Fixture</title><link href="https://example.com/a"/><updated>2026-10-23T01:00:00Z</updated><summary>Fixture summary</summary></entry></feed>'
        article = ingest.parse_feed(payload, SOURCE, OBSERVED)[0]
        self.assertIsNone(article["published_at"])
        self.assertEqual(article["date_precision"], "unknown")
        # An update timestamp is deliberately not relabeled as original publication.

    def test_invalid_date_does_not_become_fetch_date(self):
        self.assertEqual(ingest.parse_date("not a date"), (None, "unknown"))
        self.assertEqual(ingest.parse_date("2026-10-23T03:04:05"), (None, "unknown_timezone"))
        self.assertEqual(ingest.parse_date("2026-02-30"), (None, "unknown"))

    def test_day_precision_and_future_date(self):
        now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        self.assertEqual(ingest.parse_date("2026-10-23", now), ("2026-10-23T00:00:00Z", "day"))
        self.assertEqual(ingest.parse_date("2027-01-01", now)[1], "future_unverified")

    def test_invalid_link_and_empty_feed(self):
        with self.assertRaises(ValueError):
            ingest.canonical_url("javascript:alert(1)")
        with self.assertRaises(ValueError):
            ingest.canonical_url("http://127.0.0.1/private")
        self.assertEqual(ingest.parse_feed(b"<rss><channel/></rss>", SOURCE, OBSERVED), [])
        with self.assertRaises(ValueError):
            ingest.parse_feed(b"<html>Access denied</html>", SOURCE, OBSERVED)
        with self.assertRaises(ValueError):
            ingest.parse_feed(rss(url="javascript:bad"), SOURCE, OBSERVED)

    def test_feed_partial_item_failure(self):
        payload = rss().replace(b"</channel>", b"<item><title>Missing link fixture</title></item></channel>")
        self.assertEqual(len(ingest.parse_feed(payload, SOURCE, OBSERVED)), 1)

    def test_sec_keeps_filing_and_report_dates_distinct(self):
        source = {**SOURCE, "format": "sec", "kind": "sec_filing", "cik": "0000000123"}
        payload = json.dumps({"cik": "123", "filings": {"recent": {
            "form": ["4", "10-Q", "8-K"],
            "accessionNumber": ["0000000123-26-000001", "0000000123-26-000002", "0000000123-26-000003"],
            "primaryDocument": ["form4.xml", "quarter.htm", "event.htm"],
            "filingDate": ["2026-10-22", "2026-10-23", "2026-10-24"],
            "reportDate": ["2026-10-20", "2026-09-30", "2026-10-21"],
            "primaryDocDescription": ["", "Quarterly report", ""], "items": ["", "", "2.02,9.01"]}}}).encode()
        articles = ingest.parse_sec(payload, source, OBSERVED)
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["published_at"], "2026-10-23T00:00:00Z")
        self.assertEqual(articles[0]["date_precision"], "day")
        self.assertEqual(articles[0]["date_kind"], "filing_date")
        self.assertEqual(articles[0]["report_date"], "2026-09-30")
        self.assertIn("metadata only", articles[0]["summary"])
        self.assertEqual(articles[0]["url"], "https://www.sec.gov/Archives/edgar/data/123/000000012326000002/quarter.htm")
        with self.assertRaises(ValueError):
            ingest.parse_sec(payload, {**source, "cik": "999"}, OBSERVED)


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def refresh(self, payload=None, sources=None, fetcher=None):
        return ingest.refresh(self.db, sources=[SOURCE] if sources is None else sources,
                              fetcher=fetcher or (lambda source: payload if payload is not None else rss()),
                              sleep=lambda duration: None)

    def test_repeated_refresh_is_idempotent_and_preserves_first_seen(self):
        first = self.refresh()
        original = storage.dashboard_data(self.db)["articles"][0]
        second = self.refresh()
        article = storage.dashboard_data(self.db)["articles"][0]
        self.assertEqual(first["new_count"], 1)
        self.assertEqual(second["new_count"], 0)
        self.assertEqual(second["duplicate_count"], 1)
        self.assertEqual(second["changed_count"], 0)
        self.assertEqual(article["first_seen_at"], original["first_seen_at"])
        self.assertEqual(len(article["provenance"]), 1)
        self.assertTrue((Path(self.temp.name) / "raw" / SOURCE["id"]).is_dir())

    def test_cross_source_exact_content_keeps_both_provenance_records(self):
        second_source = {**SOURCE, "id": "test-second", "name": "Second synthetic source"}
        self.refresh(sources=[SOURCE, second_source], fetcher=lambda source: rss(url="https://example.com/" + source["id"]))
        articles = storage.dashboard_data(self.db)["articles"]
        self.assertEqual(len(articles), 1)
        self.assertEqual(len(articles[0]["provenance"]), 2)

    def test_revision_is_not_new_story_and_old_version_survives(self):
        self.refresh()
        result = self.refresh(payload=rss(title="Synthetic revised headline"))
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(result["duplicate_count"], 0)
        self.assertIsNotNone(storage.dashboard_data(self.db)["articles"][0]["revised_at"])
        with storage.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM article_versions").fetchone()[0], 2)

    def test_same_title_later_date_is_not_a_duplicate(self):
        self.refresh()
        self.refresh(payload=rss(url="https://example.com/later", date="Sat, 24 Oct 2026 01:00:00 +0000"))
        self.assertEqual(len(storage.dashboard_data(self.db)["articles"]), 2)

    def test_publication_correction_updates_raw_and_normalized_dates(self):
        self.refresh()
        changed = "Sat, 24 Oct 2026 01:00:00 +0000"
        self.refresh(payload=rss(date=changed))
        article = storage.dashboard_data(self.db)["articles"][0]
        self.assertEqual(article["source_date_raw"], changed)
        self.assertEqual(article["published_at"], "2026-10-24T01:00:00Z")
        self.assertEqual(len(storage.dashboard_data(self.db)["articles"]), 1)

    def test_distinct_sec_accessions_do_not_collapse_generic_metadata(self):
        storage.register_sources(self.db, [SOURCE])
        one = ingest.make_article(SOURCE, "Fixture files 424B5", "https://example.com/one", "SEC metadata only", "2026-10-23", OBSERVED, accession_number="0000000123-26-000001")
        two = ingest.make_article(SOURCE, "Fixture files 424B5", "https://example.com/two", "SEC metadata only", "2026-10-23", OBSERVED, accession_number="0000000123-26-000002")
        with storage.connect(self.db) as db:
            self.assertTrue(storage.save_article(db, one, "test-hash"))
            self.assertTrue(storage.save_article(db, two, "test-hash"))
        self.assertEqual(len(storage.dashboard_data(self.db)["articles"]), 2)

    def test_fetch_failure_preserves_previous_articles_and_success_date(self):
        self.refresh()
        before = storage.dashboard_data(self.db)["sources"][0]
        def failing(source):
            raise urllib.error.URLError("Synthetic offline test")
        result = self.refresh(fetcher=failing)
        data = storage.dashboard_data(self.db)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(len(data["articles"]), 1)
        self.assertEqual(data["sources"][0]["status"], "error")
        self.assertEqual(data["sources"][0]["last_success_at"], before["last_success_at"])
        self.assertIn("Synthetic offline", data["sources"][0]["last_error"])

    def test_http_denial_cooldown_does_not_retry(self):
        calls = []
        def failing(source):
            calls.append(source)
            raise urllib.error.HTTPError(source["url"], 403, "Synthetic denial", {}, None)
        first = self.refresh(fetcher=failing)
        second = self.refresh(fetcher=failing)
        self.assertEqual(first["error_count"], 1)
        self.assertEqual(second["skipped_count"], 1)
        self.assertEqual(len(calls), 1)

    def test_empty_feed_is_successful_and_does_not_erase_history(self):
        self.refresh()
        result = self.refresh(payload=b"<rss><channel/></rss>")
        data = storage.dashboard_data(self.db)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(data["sources"][0]["status"], "ok")
        self.assertEqual(data["sources"][0]["item_count"], 0)
        self.assertEqual(len(data["articles"]), 1)

    def test_raw_retention_is_bounded(self):
        for i in range(8):
            self.refresh(payload=rss(title="Synthetic revision " + str(i)))
        self.assertEqual(len(list((Path(self.temp.name) / "raw" / SOURCE["id"]).iterdir())), 5)


class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "provenance.sqlite3"
        self.primary = {**SOURCE, "role": "primary"}
        self.discovery = {**SOURCE, "id": "search", "name": "Synthetic discovery",
                          "kind": "discovery_lead", "role": "discovery"}
        self.secondary = {**SOURCE, "id": "news", "name": "Synthetic news",
                          "kind": "news_report", "role": "secondary"}
        storage.register_sources(self.db, [self.primary, self.discovery, self.secondary])

    def tearDown(self):
        self.temp.cleanup()

    def article(self, source, title="Synthetic original", url="https://example.com/shared", observed=OBSERVED):
        return ingest.make_article(source, title, url, "Synthetic source text", "2026-10-23", observed,
            publisher_name=source["name"], publisher_url=source["url"], discovered_via=source["id"],
            verification_status="discovery_lead" if source["role"] == "discovery" else "publisher_metadata")

    def save(self, article):
        with storage.connect(self.db) as db:
            return storage.save_article(db, article, "fixture-response", return_status=True)

    def current(self):
        articles = storage.dashboard_data(self.db)["articles"]
        self.assertEqual(len(articles), 1)
        return articles[0]

    def test_lower_role_cross_source_text_cannot_inherit_primary_identity(self):
        primary = self.article(self.primary)
        self.assertEqual(self.save(primary), "new")
        for source in (self.secondary, self.discovery):
            candidate = self.article(source, "Different " + source["id"], observed="2026-10-25T12:00:00Z")
            self.assertEqual(self.save(candidate), "duplicate")
        selected = self.current()
        for field in ("title", "summary", "source_id", "kind", "publisher_name", "publisher_url",
                      "verification_status", "discovered_via", "date_kind", "observed_at", "content_hash"):
            self.assertEqual(selected[field], primary[field], field)
        self.assertIsNone(selected["revised_at"])
        self.assertEqual(len(selected["provenance"]), 3)
        with storage.connect(self.db) as db:
            versions = [json.loads(row[0]) for row in db.execute("SELECT record_json FROM article_versions")]
        self.assertEqual({item["source_id"] for item in versions}, {"test-rss", "search", "news"})
        self.assertEqual(next(item for item in versions if item["source_id"] == "search")["verification_status"], "discovery_lead")

    def test_primary_arriving_after_discovery_promotes_all_origin_fields(self):
        discovery = self.article(self.discovery)
        self.save(discovery)
        primary = self.article(self.primary, "Synthetic primary revision", observed="2026-10-25T12:00:00Z")
        self.assertEqual(self.save(primary), "changed")
        selected = self.current()
        for field in ("title", "summary", "source_id", "kind", "publisher_name", "publisher_url",
                      "verification_status", "discovered_via", "date_kind", "observed_at", "content_hash"):
            self.assertEqual(selected[field], primary[field], field)
        self.assertEqual(selected["source_role"], "primary")
        self.assertEqual(selected["first_seen_at"], discovery["first_seen_at"])
        self.assertEqual(selected["revised_at"], primary["observed_at"])
        self.assertEqual(len(selected["provenance"]), 2)

    def test_same_content_promotion_preserves_identity_and_prior_url_recognition(self):
        discovery = self.article(self.discovery, url="https://example.com/lead")
        primary = self.article(self.primary, url="https://example.com/origin", observed="2026-10-25T12:00:00Z")
        self.assertEqual(discovery["content_hash"], primary["content_hash"])
        self.save(discovery)
        self.assertEqual(self.save(primary), "changed")
        selected = self.current()
        self.assertEqual(selected["id"], discovery["id"])
        self.assertEqual(selected["url"], primary["url"])
        self.assertEqual(selected["source_id"], primary["source_id"])
        self.assertEqual(selected["verification_status"], "publisher_metadata")
        self.assertEqual(selected["date_kind"], "feed_date")
        revised_discovery = self.article(self.discovery, "New search wording", url=discovery["url"], observed="2026-10-26T12:00:00Z")
        self.assertEqual(self.save(revised_discovery), "duplicate")
        self.assertEqual(self.current()["title"], primary["title"])
        self.assertEqual(len(self.current()["provenance"]), 2)

    def test_equal_role_source_is_stable_but_own_revision_updates_metadata(self):
        peer = {**self.primary, "id": "peer", "name": "Synthetic peer"}
        storage.register_sources(self.db, [peer])
        original = self.article(self.primary)
        self.save(original)
        self.assertEqual(self.save(self.article(peer, "Peer wording")), "duplicate")
        self.assertEqual(self.current()["title"], original["title"])
        revision = self.article(self.primary, "Corrected origin wording", observed="2026-10-25T12:00:00Z")
        revision.update(publisher_name="Corrected publisher label", publisher_url="https://example.com/publisher",
                        filing_form="8-K", report_date="2026-09-30", accession_number="0000000123-26-000123")
        self.assertEqual(self.save(revision), "changed")
        selected = self.current()
        for field in ("publisher_name", "publisher_url", "filing_form", "report_date", "accession_number"):
            self.assertEqual(selected[field], revision[field], field)
        self.assertEqual(selected["first_seen_at"], original["first_seen_at"])


if __name__ == "__main__":
    unittest.main()
