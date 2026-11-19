"""Public-view rotation preserves evidence and never deletes the local archive."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulse import wall_review
from scripts import build_site
from scripts.public_rotation import rotate_snapshot
from test_wall_review import fixture as wall_fixture


STAMP = "2020-12-31T00:00:00+00:00"


def source(identifier):
    return {
        "id": identifier, "name": "Synthetic " + identifier,
        "url": "https://example.com/evidence/" + identifier,
        "role": "primary", "kind": "company_release", "reviewed_at": STAMP,
        "quality_note": "Synthetic source for a temporary test only.",
        "topics": ["funding"], "source_date": "2020-01-01",
    }


def reviewed_fixture(count=3):
    sources = [source("source-%03d" % index) for index in range(count)]
    articles = []
    for index, evidence in enumerate(sources):
        published = (datetime(2020, 1, 1, tzinfo=timezone.utc)
                     + timedelta(days=index)).isoformat()
        article = {
            "id": "article-%03d" % index, "title": "Synthetic research %d" % index,
            "url": evidence["url"], "published_at": published,
            "date_kind": "publication_date", "source_id": evidence["id"],
            "source_role": "primary", "lens": "funding", "rank": index + 1,
            "observation": "Synthetic reported evidence.",
            "summary": "Synthetic summary.", "implication": "A conditional implication.",
            "counterevidence": "This remains a synthetic example.",
            "confirms": "Subsequent reported delivery.", "refutes": "Failed delivery.",
            "uncertainty": "Not real research or live data.", "entities": ["Example"],
            "reviewed_at": STAMP,
        }
        article["reading_review"] = {
            "key_takeaway": "Synthetic concise takeaway.", "worth_reading": "skim",
            "rationale": "Synthetic reading judgment.",
            "basis": build_site.READING_REVIEW_BASIS, "reviewed_at": STAMP,
            "content_hash": build_site.reading_content_hash(article),
        }
        articles.append(article)
    return {
        "reviewed_at": STAMP, "headline": "Synthetic reviewed research",
        "bullets": ["Temporary test data only."], "notice": "Synthetic snapshot.",
        "articles": articles, "sources": sources, "ledger": [], "earnings": [],
    }


def ids(rows):
    return {row["id"] for row in rows}


class RotationSelectionTests(unittest.TestCase):
    def test_below_caps_preserves_content_order_and_input(self):
        raw = reviewed_fixture(3)
        raw["sources"].append(source("intentional-roster"))
        before = deepcopy(raw)
        selected, _ = rotate_snapshot(raw)
        self.assertEqual(selected, before)
        self.assertEqual(raw, before)
        selected["articles"][0]["observation"] = "Changed returned copy"
        self.assertEqual(raw, before)

    def test_oldest_first_satisfies_both_caps_with_minimum_prefix(self):
        raw = reviewed_fixture(5)
        raw["sources"].extend([source("roster-a"), source("roster-b")])
        before = deepcopy(raw)
        selected, _ = rotate_snapshot(raw, max_articles=4, max_sources=5)
        # One retirement fits the article limit but not the source limit.
        self.assertEqual(ids(selected["articles"]),
                         {"article-002", "article-003", "article-004"})
        self.assertEqual(len(selected["sources"]), 5)
        self.assertTrue({"roster-a", "roster-b"} <= ids(selected["sources"]))
        self.assertEqual(raw, before)

    def test_source_pressure_can_retire_more_than_article_pressure(self):
        raw = reviewed_fixture(4)
        extra = source("old-only-highlight")
        raw["sources"].append(extra)
        raw["articles"][0]["highlights"] = [{"source_url": extra["url"]}]
        selected, _ = rotate_snapshot(raw, max_articles=4, max_sources=3)
        self.assertEqual(ids(selected["articles"]),
                         {"article-001", "article-002", "article-003"})
        self.assertEqual(ids(selected["sources"]),
                         {"source-001", "source-002", "source-003"})

    def test_review_date_and_editorial_rank_do_not_make_old_news_new(self):
        raw = reviewed_fixture(3)
        raw["articles"][0].update(reviewed_at="2026-11-19T12:00:00Z", rank=1)
        raw["articles"][0]["reading_review"]["reviewed_at"] = "2026-11-19T12:00:00Z"
        raw["articles"][2]["rank"] = 999
        selected, _ = rotate_snapshot(raw, max_articles=2, max_sources=3)
        self.assertNotIn("article-000", ids(selected["articles"]))
        self.assertIn("article-002", ids(selected["articles"]))
        self.assertEqual(selected["articles"][-1]["rank"], 999)

    def test_publication_date_precedes_event_date_for_recency(self):
        raw = reviewed_fixture(3)
        raw["articles"][0]["event_date"] = "2020-12-30"
        selected, _ = rotate_snapshot(raw, max_articles=2, max_sources=3)
        self.assertNotIn("article-000", ids(selected["articles"]))

    def test_event_and_unknown_date_fallback_are_deterministic(self):
        raw = reviewed_fixture(3)
        raw["articles"][0]["published_at"] = None
        raw["articles"][0]["event_date"] = "2020-01-04"
        raw["articles"][1]["published_at"] = None
        # Missing both source and event dates is oldest; never use review time.
        selected, _ = rotate_snapshot(raw, max_articles=2, max_sources=3)
        self.assertEqual(ids(selected["articles"]), {"article-000", "article-002"})

    def test_equal_dates_use_stable_id_tiebreak_not_input_order(self):
        raw = reviewed_fixture(3)
        for item in raw["articles"]:
            item["published_at"] = "2020-01-01T00:00:00Z"
        forward, _ = rotate_snapshot(raw, max_articles=2, max_sources=3)
        reverse = deepcopy(raw)
        reverse["articles"].reverse()
        reverse["sources"].reverse()
        backward, _ = rotate_snapshot(reverse, max_articles=2, max_sources=3)
        self.assertEqual(ids(forward["articles"]), ids(backward["articles"]))
        self.assertEqual(ids(forward["articles"]), {"article-001", "article-002"})

    def test_shared_financial_global_and_roster_evidence_survives(self):
        raw = reviewed_fixture(3)
        shared, financial, global_source, roster = [source(name) for name in
                                                  ("shared", "financial", "global", "roster")]
        raw["sources"].extend([shared, financial, global_source, roster])
        raw["articles"][0]["highlights"] = [
            {"source_url": item["url"]} for item in (shared, financial, global_source)
        ]
        raw["articles"][2]["highlights"] = [{"source_url": shared["url"]}]
        raw["ledger"] = [{"source_url": financial["url"]}]
        raw["notice"] = "Context: " + global_source["url"]
        selected, _ = rotate_snapshot(raw, max_articles=2, max_sources=6)
        self.assertEqual(ids(selected["sources"]),
                         {"source-001", "source-002", "shared", "financial", "global", "roster"})
        self.assertEqual(selected["ledger"], raw["ledger"])
        self.assertEqual(selected["notice"], raw["notice"])

    def test_inline_article_urls_and_supplemental_financial_links_are_kept(self):
        raw = reviewed_fixture(3)
        inline, supplementary, consensus = [source(name) for name in
                                            ("inline", "supplementary", "consensus")]
        raw["sources"].extend([inline, supplementary, consensus])
        raw["articles"][0]["highlights"] = [
            {"source_url": item["url"]} for item in (inline, supplementary, consensus)
        ]
        raw["articles"][2]["access_note"] = "Original evidence (" + inline["url"] + ")."
        raw["ledger"] = [{"sources": [{"url": supplementary["url"]}]}]
        raw["earnings"] = [{"consensus_source_url": consensus["url"]}]
        selected, _ = rotate_snapshot(raw, max_articles=2, max_sources=5)
        self.assertTrue({"inline", "supplementary", "consensus"} <= ids(selected["sources"]))
        self.assertNotIn("source-000", ids(selected["sources"]))

    def test_unremovable_keeper_pressure_fails_without_mutating_input(self):
        raw = reviewed_fixture(2)
        raw["sources"].extend([source("roster-a"), source("roster-b")])
        before = deepcopy(raw)
        with self.assertRaises(ValueError):
            rotate_snapshot(raw, max_articles=2, max_sources=1)
        self.assertEqual(raw, before)


class RotationPublicationGateTests(unittest.TestCase):
    def test_prepare_uses_existing_finite_article_cap_and_keeps_source_history(self):
        raw = reviewed_fixture(50)
        before = deepcopy(raw)
        selected, _ = build_site.prepare_snapshot(raw)
        self.assertEqual(len(selected["articles"]), 49)
        self.assertNotIn("article-000", ids(selected["articles"]))
        self.assertEqual(len(selected["sources"]), 49)
        build_site.validate_public(selected)
        self.assertEqual(raw, before)

    def test_prepare_preserves_real_source_cap_without_purging_roster_entries(self):
        raw = reviewed_fixture(2)
        raw["sources"].extend(source("keeper-%03d" % index) for index in range(167))
        before = deepcopy(raw)
        selected, _ = build_site.prepare_snapshot(raw)
        self.assertEqual(len(selected["sources"]), 168)
        self.assertEqual(ids(selected["articles"]), {"article-001"})
        self.assertTrue({"keeper-%03d" % index for index in range(167)}
                        <= ids(selected["sources"]))
        build_site.validate_public(selected)
        self.assertEqual(raw, before)

    def test_oldest_missing_review_cannot_be_removed_to_pass_gate(self):
        raw = reviewed_fixture(50)
        raw["articles"][0].pop("reading_review")
        with self.assertRaisesRegex(ValueError, "reading review"):
            build_site.prepare_snapshot(raw)

    def test_oldest_stale_review_cannot_be_removed_to_pass_gate(self):
        raw = reviewed_fixture(50)
        raw["articles"][0]["observation"] = "Changed after review"
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_site.prepare_snapshot(raw)

    def test_oldest_private_content_cannot_disappear_before_safety_validation(self):
        raw = reviewed_fixture(50)
        raw["articles"][0]["observation"] = "/Users/synthetic/private"
        with self.assertRaisesRegex(ValueError, "Private path"):
            build_site.prepare_snapshot(raw)

    def test_default_build_path_rotates_without_rewriting_original_candidate(self):
        raw = reviewed_fixture(50)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "candidate.json"
            content = json.dumps(raw, indent=2).encode()
            original.write_bytes(content)
            build_site.build(root / "site", source=original)
            payload = json.loads((root / "site/data/dashboard.json").read_text())
            self.assertEqual(len(payload["articles"]), 49)
            self.assertNotIn("article-000", ids(payload["articles"]))
            self.assertEqual(original.read_bytes(), content)


class RotationArchiveTests(unittest.TestCase):
    def setUp(self):
        from scripts.prepare_public import prepare
        self.prepare = prepare

    def files(self, directory, complete=True):
        root = Path(directory)
        input_path = root / "reviewed-input.json"
        input_path.write_text(json.dumps(reviewed_fixture(50), indent=2) + "\n")
        wall_path = root / "local-wall.json"
        payload, packet = wall_fixture()
        if complete:
            payload, _ = wall_review.apply_packet(payload, packet)
        wall_path.write_text(json.dumps(payload, indent=2) + "\n")
        output = root / "public"
        output.mkdir()
        (output / "brief.json").write_text(json.dumps(reviewed_fixture(2)) + "\n")
        (output / "wall.json").write_text(json.dumps(payload) + "\n")
        archive = root / "private-archive"
        return input_path, wall_path, archive, output

    def test_prepare_archives_complete_input_and_previous_public_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, archive, output = self.files(directory)
            original = source_path.read_bytes()
            wall_before = wall_path.read_bytes()
            previous = [(output / name).read_bytes() for name in ("brief.json", "wall.json")]
            self.prepare(source_path, wall_path, archive, output)
            self.assertEqual(source_path.read_bytes(), original)
            self.assertEqual(wall_path.read_bytes(), wall_before)
            archived = [p.read_bytes() for p in archive.rglob("*") if p.is_file()]
            self.assertIn(original, archived)
            self.assertIn(wall_before, archived)
            for content in previous:
                self.assertIn(content, archived)
            self.assertEqual(len(json.loads((output / "brief.json").read_text())["articles"]), 49)
            self.assertTrue(wall_review.coverage(json.loads((output / "wall.json").read_text()))["complete"])

    def test_dry_run_does_not_write_archive_or_public_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, archive, output = self.files(directory)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            self.prepare(source_path, wall_path, archive, output, dry_run=True)
            self.assertFalse(archive.exists())
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_incomplete_wall_blocks_both_public_writes_and_archiving(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, archive, output = self.files(directory, complete=False)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaisesRegex(ValueError, "review|judgment"):
                self.prepare(source_path, wall_path, archive, output)
            self.assertFalse(archive.exists())
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_archive_inside_public_output_is_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, _, output = self.files(directory)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaises(ValueError):
                self.prepare(source_path, wall_path, output / "archive", output)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_corrupted_existing_archive_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, archive, output = self.files(directory)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            archive.mkdir()
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            existing = archive / ("reviewed-candidate-" + digest + ".json")
            existing.write_bytes(b"Synthetic archive corruption sentinel")
            with self.assertRaisesRegex(ValueError, "archive"):
                self.prepare(source_path, wall_path, archive, output)
            self.assertEqual(existing.read_bytes(), b"Synthetic archive corruption sentinel")
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_symlink_public_destination_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, archive, output = self.files(directory)
            target = Path(directory) / "unrelated.json"
            target.write_bytes(b"Synthetic unrelated file")
            destination = output / "brief.json"
            destination.unlink()
            destination.symlink_to(target)
            old_wall = (output / "wall.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "symlink"):
                self.prepare(source_path, wall_path, archive, output)
            self.assertEqual(target.read_bytes(), b"Synthetic unrelated file")
            self.assertEqual((output / "wall.json").read_bytes(), old_wall)
            self.assertFalse(archive.exists())

    def test_private_wall_commentary_blocks_both_public_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, archive, output = self.files(directory)
            payload = json.loads(wall_path.read_text())
            payload["items"][0]["analysis"]["key_takeaway"] = "/Users/synthetic/private"
            wall_path.write_text(json.dumps(payload))
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaisesRegex(ValueError, "Private"):
                self.prepare(source_path, wall_path, archive, output)
            self.assertFalse(archive.exists())
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_second_public_replace_failure_restores_both_previous_feeds(self):
        from scripts import prepare_public
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, archive, output = self.files(directory)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            original = source_path.read_bytes()
            original_wall = wall_path.read_bytes()
            real_replace = prepare_public.os.replace
            replacements = []

            def fail_second(source, destination):
                replacements.append(Path(destination).name)
                if len(replacements) == 2:
                    raise OSError("Synthetic second replacement failure")
                return real_replace(source, destination)

            with patch.object(prepare_public.os, "replace", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "second replacement"):
                    self.prepare(source_path, wall_path, archive, output)
            self.assertEqual(replacements, ["brief.json", "wall.json", "brief.json"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
            archived = [p.read_bytes() for p in archive.rglob("*") if p.is_file()]
            self.assertIn(original, archived)
            self.assertIn(original_wall, archived)
            for content in before.values():
                self.assertIn(content, archived)

    def test_concurrent_input_change_is_not_published_or_overwritten(self):
        from scripts import prepare_public
        with tempfile.TemporaryDirectory() as directory:
            source_path, wall_path, archive, output = self.files(directory)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            original = source_path.read_bytes()
            real_archive = prepare_public._archive
            changed = b"Synthetic external edit during preparation"

            def archive_then_change(directory, name, content):
                result = real_archive(directory, name, content)
                if name == "reviewed-candidate":
                    source_path.write_bytes(changed)
                return result

            with patch.object(prepare_public, "_archive", side_effect=archive_then_change):
                with self.assertRaisesRegex(ValueError, "input changed"):
                    self.prepare(source_path, wall_path, archive, output)
            self.assertEqual(source_path.read_bytes(), changed)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
            self.assertIn(original, [p.read_bytes() for p in archive.rglob("*") if p.is_file()])


if __name__ == "__main__":
    unittest.main()
