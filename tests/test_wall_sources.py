"""Synthetic source parsing fixtures; these records never enter data/."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulse import wall

STAMP = "2026-11-01T12:00:00Z"
LATER = "2026-11-02T12:00:00Z"


def source(identity):
    return next(s for s in wall.SOURCES if s["id"] == identity)


def rss(subtitle="A fictional election interview", extra=""):
    return ('<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><title>GAME TIME</title>'
            '<link>https://example.com/fixture-game</link><pubDate>Sun, 01 Nov 2026 10:00:00 GMT</pubDate>'
            '<description>' + subtitle + '</description><content:encoded>Never export this full body</content:encoded>'
            '</item>' + extra + '</channel></rss>').encode()


def channel(identity, titles, selected="Videos", durations=None, members=None):
    cards = [{"richItemRenderer": {"content": {"lockupViewModel": {"contentId": video,
              "metadata": {"lockupMetadataViewModel": {"title": {"content": title}}}}}}}
             for video, title in titles]
    for card in cards:
        node = card["richItemRenderer"]["content"]["lockupViewModel"]
        if durations and node["contentId"] in durations:
            node["contentImage"] = {"thumbnailViewModel": {"overlays": [{"thumbnailBottomOverlayViewModel": {
                "badges": [{"thumbnailBadgeViewModel": {"text": durations[node["contentId"]]}}]}}]}}
        if node["contentId"] in (members or []):
            node["metadata"]["lockupMetadataViewModel"]["badges"] = [{"badgeViewModel": {
                "badgeText": "Members only", "badgeStyle": "BADGE_MEMBERS_ONLY"}}]
    data = {"metadata": {"channelMetadataRenderer": {"externalId": identity}},
            "contents": {"twoColumnBrowseResultsRenderer": {"tabs": [{"tabRenderer": {
                "title": selected, "selected": True, "content": {"richGridRenderer": {"contents": cards}}}}]}}}
    return ('<!doctype html><html><script>var ytInitialData = ' + json.dumps(data) + ';</script></html>').encode()


class WallSourceTests(unittest.TestCase):
    def test_polymarket_subtitle_adds_context_without_copying_article_body(self):
        rows, _ = wall.parse_feed(rss(), source("polymarket-news"), STAMP)
        item = rows[0]
        self.assertEqual(item["title"], "A fictional election interview")
        self.assertIn("GAME TIME", item["summary"])
        self.assertIn("Publisher commentary", item["summary"])
        self.assertNotIn("Never export", json.dumps(item))
        self.assertEqual(item["provenance_hash"], hashlib.sha256(rss()).hexdigest())
        self.assertEqual(item["content_hash"], wall.item_content_hash(item))
        self.assertIsNone(item["analysis"])

    def test_polymarket_missing_subtitle_explains_gap(self):
        rows, _ = wall.parse_feed(rss(""), source("polymarket-news"), STAMP)
        self.assertIn("no descriptive subtitle", rows[0]["summary"])
        self.assertEqual(rows[0]["title"], "GAME TIME")

    def test_changed_subtitle_invalidates_review_but_unrelated_feed_change_does_not(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(wall, "SOURCES", [source("polymarket-news")]):
            path = Path(directory) / "wall.json"
            wall.refresh_file(path, fetcher=lambda _: rss(), now=STAMP)
            payload = wall.load_file(path)
            payload["items"][0]["analysis"] = {"text": "Synthetic interpretation", "basis": "Fixture metadata", "reviewed_at": STAMP, "source_urls": ["https://example.com/fixture-game"]}
            path.write_text(json.dumps(payload))
            changed_response = rss(extra="<!-- Unrelated feed change -->")
            wall.refresh_file(path, fetcher=lambda _: changed_response, now=LATER)
            self.assertEqual(wall.load_file(path)["items"][0], payload["items"][0])
            wall.refresh_file(path, fetcher=lambda _: rss("A different fictional election interview"), now=LATER)
            current = wall.load_file(path)["items"][0]
            self.assertIsNone(current["analysis"])
            self.assertNotEqual(current["content_hash"], payload["items"][0]["content_hash"])

    def test_channel_uses_verified_identity_and_video_tab_and_preserves_unknown_dates(self):
        s = source("tevis-investing")
        body = channel(wall.YOUTUBE_CHANNEL_IDS[s["id"]], [("abcdefghijk", "Synthetic company analysis")])
        rows, _ = wall.parse_feed(body, s, STAMP)
        self.assertEqual(rows[0]["url"], "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(rows[0]["format"], "video")
        self.assertIsNone(rows[0]["published_at"])
        for wrong in [channel("UCWRONG", [("abcdefghijk", "Wrong source")]), channel(wall.YOUTUBE_CHANNEL_IDS[s["id"]], [("abcdefghijk", "Wrong tab")], "Home")]:
            with self.assertRaises(ValueError):
                wall.parse_feed(wrong, s, STAMP)

    def test_sports_filters_keep_wins_and_losses_and_are_bounded(self):
        s = source("knicks-highlights")
        entries = [("abcdefghij" + str(i), title) for i, title in enumerate([
            "Synthetic Knicks Defeat Opponent", "Synthetic Knicks Take On Opponent", "Game Highlights: Fixture",
            "Player interview only", "Community visit", "Game Recap: Fixture"])]
        rows, stats = wall.parse_feed(channel(wall.YOUTUBE_CHANNEL_IDS[s["id"]], entries), s, STAMP)
        self.assertEqual(len(rows), 4)
        self.assertEqual(stats["filtered_count"], 2)
        self.assertTrue(all(r["topics"] == ["NBA", "Knicks", "Highlights"] for r in rows))
        many = [("abcdefgh" + f"{i:03}", "Game Highlights Fixture") for i in range(30)]
        rows, stats = wall.parse_feed(channel(wall.YOUTUBE_CHANNEL_IDS[s["id"]], many), s, STAMP)
        self.assertEqual(len(rows), 8)
        self.assertEqual(stats["window_truncated_count"], 22)

    def test_malformed_channel_schema_is_source_failure_not_whole_refresh_failure(self):
        s = source("tevis-investing")
        for data in ([], {"metadata": None}, {"metadata": {"channelMetadataRenderer": None}}):
            body = ("<script>var ytInitialData = " + json.dumps(data) + ";</script>").encode()
            with self.subTest(data=data), self.assertRaises(ValueError):
                wall.parse_feed(body, s, STAMP)
        with tempfile.TemporaryDirectory() as directory, patch.object(wall, "SOURCES", [s]):
            path = Path(directory) / "wall.json"
            receipt = wall.refresh_file(path, fetcher=lambda _: b"<script>var ytInitialData = [];</script>", now=STAMP)
            self.assertEqual(receipt["error_count"], 1)
            self.assertEqual(wall.load_file(path)["source_status"][0]["status"], "error")

    def test_youtube_atom_entries_remain_video_metadata(self):
        s = {**source("tevis-investing"), "kind": "youtube_rss"}
        body = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Fixture video</title><link rel="alternate" href="https://www.youtube.com/watch?v=abcdefghijk"/><published>2026-11-01T10:00:00Z</published></entry></feed>'
        rows, _ = wall.parse_feed(body, s, STAMP)
        self.assertEqual(rows[0]["format"], "video")
        self.assertEqual(rows[0]["published_at"], "2026-11-01T10:00:00Z")

    def test_new_channel_selection_skips_short_promotional_and_members_only_cards(self):
        s = source("thinking-basketball")
        entries = [("abcdefghij" + str(i), title) for i, title in enumerate([
            "Synthetic brief clip", "Synthetic private analysis", "Synthetic #Shorts clip",
            "Channel trailer", "Synthetic public analysis one", "Synthetic public analysis two",
            "Synthetic public analysis three", "Synthetic public analysis four"])]
        durations = {video: "12:34" for video, _ in entries}
        durations[entries[0][0]] = "2:59"
        rows, stats = wall.parse_feed(channel(wall.YOUTUBE_CHANNEL_IDS[s["id"]], entries,
                                            durations=durations, members=[entries[1][0]]), s, STAMP)
        self.assertEqual([row["title"] for row in rows], [title for _, title in entries[4:7]])
        self.assertEqual(stats["filtered_count"], 4)
        self.assertEqual(stats["window_truncated_count"], 1)
        self.assertTrue(all(row["duration"] == "12:34" for row in rows))
        self.assertTrue(all(row["published_at"] is None for row in rows))

    def test_formula1_video_selection_focuses_on_analysis_and_race_coverage(self):
        s = source("formula1-video")
        entries = [("abcdefghij" + str(i), title) for i, title in enumerate([
            "Synthetic Palmer's Analysis", "Synthetic Top 10 Onboards", "Radio Rewind Synthetic Race",
            "Synthetic Driver Interview", "Race Highlights Synthetic Grand Prix", "Qualifying Highlights Fixture"])]
        rows, stats = wall.parse_feed(channel(wall.YOUTUBE_CHANNEL_IDS[s["id"]], entries), s, STAMP)
        self.assertEqual([row["title"] for row in rows], [entries[i][1] for i in (0, 1, 4)])
        self.assertEqual(stats["filtered_count"], 2)
        self.assertEqual(stats["window_truncated_count"], 1)

    def test_new_channel_identities_have_deliberate_small_limits_and_correct_sections(self):
        for identity, section in (("ben-felix", "markets"), ("andrej-karpathy", "markets"),
                                  ("thinking-basketball", "sports"), ("formula1-video", "sports")):
            with self.subTest(identity=identity):
                s = source(identity)
                self.assertEqual(s["section"], section)
                self.assertEqual(wall.YOUTUBE_CHANNEL_LIMITS[identity], 2 if identity == "andrej-karpathy" else 3)
                self.assertTrue(wall.YOUTUBE_CHANNEL_IDS[identity].startswith("UC"))
                self.assertEqual(s["kind"], "public_youtube_channel")

    def test_kobeissi_identity_is_a_gap_not_a_fabricated_feed(self):
        payload = wall.empty_payload()
        item = next(s for s in payload["source_status"] if s["id"] == "kobeissi-letter")
        self.assertEqual(item["status"], "not_connected")
        self.assertIsNone(item["feed_url"])
        self.assertIn("@KobeissiLetter", item["note"])

    def test_selected_browser_posts_status_survives_feed_refresh(self):
        payload = wall.empty_payload()
        selected = next(s for s in payload["source_status"] if s["id"] == "kobeissi-letter")
        selected.update(status="selected_posts", item_count=1, last_attempt_at=STAMP, last_success_at=STAMP)
        item = {"id": "fixture-selected-public-post", "section": "markets", "source_id": selected["id"],
                "title": "Synthetic public calendar post", "url": "https://example.com/public-post",
                "published_at": "2026-11-01", "first_seen_at": STAMP, "updated_at": STAMP,
                "format": "article", "topics": ["Markets"], "summary": "Fixture source selection", "analysis": None}
        item["content_hash"] = wall.item_content_hash(item)
        payload["items"] = [item]
        wall.validate_public(payload)
        with tempfile.TemporaryDirectory() as directory, patch.object(wall, "SOURCES", []):
            path = Path(directory) / "wall.json"
            path.write_text(json.dumps(payload))
            wall.refresh_file(path, now=LATER)
            updated = wall.load_file(path)
        self.assertEqual(next(s for s in updated["source_status"] if s["id"] == selected["id"]), selected)
        self.assertEqual(updated["items"], [item])


if __name__ == "__main__":
    unittest.main()
