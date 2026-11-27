"""Public product-access checks: synthetic markup, never member issue content."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from pulse import wall
from pulse.__main__ import main as pulse_main
from scripts.refresh_wall import main as wall_main


STAMP = "2026-11-26T12:00:00Z"
LATER = "2026-11-27T12:00:00Z"
IDS = ["kobeissi-newsletter", "kobeissi-chart-week"]
PRODUCTS = [next(source for source in wall.SOURCES if source["id"] == identity) for identity in IDS]
FEED = next(source for source in wall.SOURCES if source["id"] == "f1-official")


def product(source, extra=""):
    if source["id"] == IDS[0]:
        title, body = "Newsletters", "The Kobeissi Letter: Our subscription-based weekly newsletter."
    else:
        title, body = "Chart of the Week", "Our FREE weekly chart. Simply create an account and get instant access."
    return ("<!doctype html><html><head><title>" + title + "</title></head><body><h1>" + title +
            "</h1><p>" + body + "</p>" + extra + "</body></html>").encode()


def seed(path):
    with patch.object(wall, "SOURCES", [FEED]):
        wall.refresh_file(path, fetcher=lambda _: b'<rss><channel><item><title>Synthetic article</title><link>https://example.com/fixture</link></item></channel></rss>', now=STAMP)
    return wall.load_file(path)


class KobeissiSourceTests(unittest.TestCase):
    def test_separate_free_chart_paid_newsletter_and_existing_selected_x(self):
        state = wall.empty_payload()
        sources = {source["id"]: source for source in state["source_status"]}
        self.assertEqual(sources["kobeissi-letter"]["kind"], "requested")
        self.assertIn("@KobeissiLetter", sources["kobeissi-letter"]["note"])
        self.assertIn("paid newsletter", sources[IDS[0]]["name"])
        self.assertIn("free Chart of the Week", sources[IDS[1]]["name"])
        self.assertIn("account is required", sources[IDS[1]]["note"])
        self.assertTrue(all(source["feed_url"].startswith("https://www.thekobeissiletter.com/analysis/") for source in PRODUCTS))

    def test_public_marketing_access_is_not_an_issue_or_analysis(self):
        for source in PRODUCTS:
            with self.subTest(source=source["id"]):
                rows, stats = wall.parse_feed(product(source), source, STAMP)
                self.assertEqual(rows, [])
                self.assertEqual(stats["access_status"], "not_connected")
                self.assertEqual(stats["verification_scope"], "public_product_access_notice")

    def test_member_index_and_issue_html_are_not_accepted_as_public_source(self):
        for path in ["/members/products/newsletters", "/members/products/chart-of-the-week", "/cow/week-of-january-1st-2026", "/about/samples"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                wall.parse_feed(product(PRODUCTS[0]), {**PRODUCTS[0], "feed_url": "https://www.thekobeissiletter.com" + path}, STAMP)

    def test_no_issue_date_or_card_is_inferred_from_links_samples_or_fetch_time(self):
        extra = '<a href="/members-newsletters/fixture">Week of January 1st, 2026</a><time>2026-01-01</time><p>Historical sample</p>'
        for source in PRODUCTS:
            self.assertEqual(wall.parse_feed(product(source, extra), source, STAMP)[0], [])

    def test_hidden_script_or_member_content_cannot_establish_public_access(self):
        for wrapper in ['<script>{}</script>', '<div hidden>{}</div>', '<div data-ms-content="members">{}</div>', '<div class="w-condition-invisible">{}</div>']:
            body = '<html><title>Newsletters</title>' + wrapper.format('The Kobeissi Letter: subscription-based weekly newsletter') + '</html>'
            with self.subTest(wrapper=wrapper), self.assertRaises(ValueError):
                wall.parse_feed(body.encode(), PRODUCTS[0], STAMP)

    def test_signin_and_changed_identity_fail_closed(self):
        for payload in [b'<title>Sign In</title><p>Log in</p>', product(PRODUCTS[0]).replace(b'subscription-based', b'status-unknown'), b'<title>Samples</title><p>sample content</p>']:
            with self.assertRaises(ValueError):
                wall.parse_feed(payload, PRODUCTS[0], STAMP)

    def test_selective_checks_preserve_all_items_dates_reviews_and_peer_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wall.json"
            old = seed(path)
            old_sources = {source["id"]: source for source in old["source_status"]}
            calls = []
            def fetch(source):
                calls.append(source["id"])
                return product(source)
            result = wall.refresh_file(path, fetcher=fetch, now=LATER, source_ids=IDS)
            new = wall.load_file(path)
            sources = {source["id"]: source for source in new["source_status"]}
            self.assertEqual(calls, IDS)
            self.assertEqual(new["items"], old["items"])
            self.assertTrue(all(sources[identity] == value for identity, value in old_sources.items() if identity not in IDS))
            self.assertEqual((result["new_count"], result["changed_count"], result["error_count"]), (0, 0, 0))
            for source in PRODUCTS:
                state = sources[source["id"]]
                self.assertEqual((state["status"], state["item_count"], state["last_success_at"]), ("not_connected", 0, LATER))
                self.assertIn("successful check dates do not mean", state["note"])
            self.assertFalse(result["public_written"])
            self.assertEqual(result["sources"][0]["response_sha256"], hashlib.sha256(product(PRODUCTS[0])).hexdigest())

    def test_failure_retains_valid_rows_and_last_product_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wall.json"
            seed(path)
            wall.refresh_file(path, fetcher=product, now=STAMP, source_ids=IDS)
            old = wall.load_file(path)
            def fail(source):
                raise HTTPError(source["feed_url"], 403, "Forbidden", {}, None)
            result = wall.refresh_file(path, fetcher=fail, now=LATER, source_ids=IDS)
            current = wall.load_file(path)
            self.assertEqual(result["error_count"], 2)
            self.assertEqual(current["items"], old["items"])
            for source in current["source_status"]:
                if source["id"] in IDS:
                    self.assertEqual(source["status"], "error")
                    self.assertEqual(source["last_success_at"], STAMP)
                    self.assertIn("cooldown_until", source)

    def test_invalid_selection_does_not_fetch_or_change_store(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wall.json"
            seed(path)
            before = path.read_bytes()
            for selection in [[], [IDS[0], IDS[0]], ["unknown-source"], "kobeissi-newsletter", [None]]:
                with self.subTest(selection=selection), patch.object(wall, "fetch_feed") as fetch, self.assertRaises(ValueError):
                    wall.refresh_file(path, source_ids=selection)
                fetch.assert_not_called()
                self.assertEqual(path.read_bytes(), before)

    def test_cli_source_selection_checks_only_requested_public_products(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wall.json"
            seed(path)
            argv = ["refresh_wall.py", "--data-file", str(path), "--source", IDS[0], "--source", IDS[1]]
            with patch("sys.argv", argv), patch.object(wall, "fetch_feed", side_effect=product) as fetch, redirect_stdout(io.StringIO()):
                self.assertEqual(wall_main(), 0)
            self.assertEqual([call.args[0]["id"] for call in fetch.call_args_list], IDS)

    def test_cli_export_cannot_silently_ignore_source_option(self):
        argv = ["refresh_wall.py", "--export-only", "--public-output", "public/wall.json", "--source", IDS[0]]
        with patch("sys.argv", argv), patch.object(wall, "refresh_file") as fetch, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            wall_main()
        self.assertEqual(error.exception.code, 2)
        fetch.assert_not_called()

    def test_normal_pulse_refresh_includes_product_checks_without_new_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            def fetch(source):
                return product(source) if source["id"] in IDS else b'<rss><channel/></rss>'
            with patch("sys.argv", ["pulse", "--data-dir", directory, "refresh"]), patch.object(wall, "SOURCES", [FEED] + PRODUCTS), patch.object(wall, "fetch_feed", side_effect=fetch) as calls, patch("pulse.server.ingest.refresh", return_value={"new_count": 0, "error_count": 0}), redirect_stdout(io.StringIO()):
                self.assertEqual(pulse_main(), 0)
            self.assertEqual([call.args[0]["id"] for call in calls.call_args_list], [FEED["id"]] + IDS)
            stored = wall.load_file(Path(directory) / "wall.json")
            self.assertEqual(stored["items"], [])
            self.assertEqual(len(list(Path(directory).glob("daily/*/*.json"))), 1)
            self.assertEqual({source["id"] for source in stored["source_status"] if source["status"] == "not_connected"} & set(IDS), set(IDS))


if __name__ == "__main__":
    unittest.main()
