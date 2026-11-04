from copy import deepcopy
from datetime import datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from pulse import wall


STAMP = "2026-11-01T12:00:00Z"
LATER = "2026-11-02T12:00:00Z"
SOURCE = wall.SOURCES[0]


def feed(title="Fixture race result", date="Sun, 01 Nov 2026 10:00:00 GMT", link="https://example.com/story", guid="", extra=""):
    return ("<rss><channel><item><title>" + title + "</title><link>" + link + "</link><pubDate>" + date + "</pubDate><guid>" + guid + "</guid>" + extra + "</item></channel></rss>").encode()


class WallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "data" / "wall.json"

    def tearDown(self):
        self.temp.cleanup()

    def refresh(self, payload, stamp=STAMP):
        with patch.object(wall, "SOURCES", [SOURCE]):
            return wall.refresh_file(self.path, fetcher=lambda _: payload, now=stamp)

    def test_missing_store_is_empty_without_creating_file(self):
        result = wall.read_file(self.path)
        self.assertEqual(result["items"], [])
        self.assertFalse(self.path.exists())
        self.assertTrue(all(s["status"] in ("pending", "not_connected", "unresolved") for s in result["source_status"]))
        self.assertEqual(result["model_status"]["mode"], "external_agent")

    def test_refresh_and_reimport_keep_stable_id_and_dates(self):
        first = self.refresh(feed())
        original = wall.read_file(self.path)["items"][0]
        second = self.refresh(feed(), LATER)
        current = wall.read_file(self.path)["items"][0]
        self.assertEqual((first["new_count"], second["duplicate_count"]), (1, 1))
        self.assertEqual(current, original)
        self.assertFalse(first["public_written"])
        self.assertEqual(len(list((self.path.parent / "wall-receipts").glob("*.json"))), 2)

    def test_changed_title_archives_review_and_requires_new_analysis(self):
        self.refresh(feed())
        state = wall.read_file(self.path)
        analysis = {"text": "Fixture-only analysis", "basis": "Synthetic evidence", "reviewed_at": STAMP, "source_urls": ["https://example.com/story"]}
        state["items"][0]["analysis"] = analysis
        self.path.write_text(json.dumps(state))
        result = self.refresh(feed(title="Changed result with a different winner"), LATER)
        current = wall.read_file(self.path)["items"][0]
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(current["id"], state["items"][0]["id"])
        self.assertEqual(current["first_seen_at"], STAMP)
        self.assertEqual(current["updated_at"], LATER)
        self.assertIsNone(current["analysis"])
        history = list((self.path.parent / "wall-history").glob("*/*.json"))
        self.assertEqual(json.loads(history[0].read_text())["analysis"], analysis)

    def test_missing_feed_date_does_not_erase_verified_date_or_review(self):
        self.refresh(feed())
        state = wall.read_file(self.path)
        state["items"][0]["analysis"] = {"text": "Fixture analysis", "basis": "Original article", "reviewed_at": STAMP, "source_urls": ["https://example.com/story"]}
        self.path.write_text(json.dumps(state))
        self.refresh(feed(date=""), LATER)
        current = wall.read_file(self.path)["items"][0]
        self.assertEqual(current["published_at"], state["items"][0]["published_at"])
        self.assertEqual(current["analysis"], state["items"][0]["analysis"])

    def test_unknown_date_not_replaced_by_retrieval_and_future_rejected(self):
        rows, _ = wall.parse_feed(feed(date=""), SOURCE, STAMP)
        self.assertIsNone(rows[0]["published_at"])
        self.assertEqual(rows[0]["first_seen_at"], STAMP)
        with self.assertRaises(ValueError):
            wall.parse_feed(feed(date="Sun, 01 Nov 2030 10:00:00 GMT"), SOURCE, STAMP)

    def test_rfc_unknown_local_zone_preserves_day_without_inventing_time(self):
        rows, _ = wall.parse_feed(feed(date="Wed, 28 Oct 2026 00:13:00 -0000"), SOURCE, STAMP)
        self.assertEqual(rows[0]["published_at"], "2026-10-28")
        value = wall.empty_payload()
        value["items"] = rows
        self.assertEqual(wall.validate_public(value)["items"][0]["published_at"], "2026-10-28")

    def test_failure_retains_items_last_success_and_sets_cooldown(self):
        self.refresh(feed())
        previous = wall.read_file(self.path)
        def blocked(_):
            raise HTTPError(SOURCE["feed_url"], 403, "Forbidden", {}, None)
        with patch.object(wall, "SOURCES", [SOURCE]):
            result = wall.refresh_file(self.path, fetcher=blocked, now=LATER)
            state = wall.read_file(self.path)
            self.assertEqual(result["error_count"], 1)
            self.assertEqual(state["items"], previous["items"])
            self.assertEqual(state["source_status"][0]["last_success_at"], STAMP)
            self.assertEqual(state["source_status"][0]["status"], "error")
            calls = []
            again = wall.refresh_file(self.path, fetcher=lambda s: calls.append(s), now=LATER)
            self.assertEqual(again["skipped_count"], 1)
            self.assertEqual(calls, [])

    def test_empty_feed_has_honest_status_and_preserves_old_rows(self):
        self.refresh(feed())
        result = self.refresh(b"<rss><channel/></rss>", LATER)
        state = wall.read_file(self.path)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(state["source_status"][0]["status"], "empty")
        self.assertEqual(state["source_status"][0]["item_count"], 0)
        self.assertEqual(len(state["items"]), 1)

    def test_corrupt_existing_store_is_not_overwritten(self):
        self.path.parent.mkdir()
        self.path.write_text("not valid JSON")
        with self.assertRaises(ValueError):
            self.refresh(feed())
        self.assertEqual(self.path.read_text(), "not valid JSON")
        self.assertIn("could not be read", wall.read_file(self.path)["coverage"][0])

    def test_feed_never_copies_description_html_or_article_body(self):
        rows, _ = wall.parse_feed(feed(extra="<description><![CDATA[<script>bad()</script>Article full text that must not be copied]]></description>"), SOURCE, STAMP)
        self.assertEqual(rows[0]["summary"], "")
        self.assertIsNone(rows[0]["analysis"])
        self.assertNotIn("Article full text", json.dumps(rows))

    def test_rejects_unsafe_xml_and_urls(self):
        with self.assertRaises(ValueError):
            wall.parse_feed(b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss/>', SOURCE, STAMP)
        for url in ("http://example.com/a", "https://localhost/a", "https://127.0.0.1/a", "https://example.com/?api_key=secret", "https://user:password@example.com/a", "https://example.com:9000/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                wall.public_url(url)

    def test_public_projection_rejects_private_and_unknown_fields(self):
        self.refresh(feed())
        value = wall.read_file(self.path)
        for extra in ({"private_notes": "not public"}, {"summary": "/Users/private-person/private"}):
            bad = deepcopy(value)
            bad["items"][0].update(extra)
            with self.assertRaises(ValueError):
                wall.public_projection(bad)
        bad = deepcopy(value)
        bad["items"][0]["id"] = "../../private"
        with self.assertRaises(ValueError):
            wall.validate_public(bad)

    def test_manual_formats_and_reviews_survive_bounded_projection(self):
        self.refresh(feed())
        value = wall.read_file(self.path)
        original = value["items"][0]
        value["items"] = [{**original, "id": "fixture-" + str(i)} for i in range(20)]
        manual = {**original, "id": "manual-instagram", "format": "instagram", "published_at": None, "url": "https://www.instagram.com/p/FixtureCode/"}
        manual["content_hash"] = wall.item_content_hash(manual)
        value["items"].append(manual)
        result = wall.public_projection(value)
        self.assertIn(manual, result["items"])
        self.assertEqual(len(result["items"]), wall.MAX_PUBLIC_ITEMS_PER_SOURCE + 1)

    def test_public_export_is_explicit_and_allowlisted(self):
        self.refresh(feed())
        value = wall.read_file(self.path)
        with self.assertRaises(ValueError):
            wall.write_public(Path(self.temp.name) / "raw.json", value)
        target = Path(self.temp.name) / "public" / "wall.json"
        receipt = wall.write_public(target, value)
        self.assertEqual(receipt["items"], 1)
        self.assertEqual(json.loads(target.read_text()), wall.public_projection(value))

    def test_media_allowlist_and_csp_do_not_allow_general_external_requests(self):
        self.refresh(feed())
        value = wall.read_file(self.path)
        value["items"][0]["media_url"] = "https://evil.example/audio.mp3"
        with self.assertRaises(ValueError):
            wall.validate_public(value)
        csp = wall.content_security_policy(static=True)
        for required in ("script-src 'self'", "connect-src 'self'", "object-src 'none'", "https://traffic.megaphone.fm", "https://www.instagram.com", "form-action 'none'"):
            self.assertIn(required, csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("*", csp)

    def test_future_manual_analysis_is_rejected(self):
        self.refresh(feed())
        value = wall.read_file(self.path)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        value["items"][0]["analysis"] = {"text": "Fixture analysis", "basis": "Source review", "reviewed_at": future, "source_urls": ["https://example.com/story"]}
        with self.assertRaises(ValueError):
            wall.validate_public(value)

    def test_podcast_without_webpage_uses_guid_and_homepage(self):
        source = next(s for s in wall.SOURCES if s["id"] == "wall-street-skinny")
        payload = feed(link="", guid="episode-1", extra='<enclosure type="audio/mpeg" url="https://www.podtrac.com/pts/redirect.mp3/traffic.megaphone.fm/TTNSE12345.mp3"/>')
        rows, _ = wall.parse_feed(payload, source, STAMP)
        self.assertEqual(rows[0]["url"], source["home_url"])
        self.assertEqual(rows[0]["format"], "podcast")
        self.assertEqual(rows[0]["media_url"], "https://traffic.megaphone.fm/TTNSE12345.mp3")
        other, _ = wall.parse_feed(payload.replace(b"episode-1", b"episode-2"), source, STAMP)
        self.assertNotEqual(rows[0]["id"], other[0]["id"])

    def test_nba_feed_labels_wnba_and_uw_filter_is_transparent(self):
        source = next(s for s in wall.SOURCES if s["id"] == "nba-communications")
        rows, _ = wall.parse_feed(feed(title="WNBA business announcement"), source, STAMP)
        self.assertEqual(rows[0]["topics"], ["WNBA"])
        uw = next(s for s in wall.SOURCES if s["id"] == "unusual-whales-blog")
        rows, stats = wall.parse_feed(feed(title="An unrelated crime story"), uw, STAMP)
        self.assertEqual(rows, [])
        self.assertEqual(stats["filtered_count"], 1)

    def test_second_refresh_cannot_overlap(self):
        self.path.parent.mkdir()
        with (self.path.parent / ".wall.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(RuntimeError):
                self.refresh(feed())
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
