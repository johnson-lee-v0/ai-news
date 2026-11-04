"""Synthetic review records only; no production wall or model calls."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from pulse import wall, wall_review
from scripts.review_wall import main


STAMP = "2026-11-01T12:00:00Z"


def fixture():
    value = wall.empty_payload()
    value["updated_at"] = STAMP
    value["items"] = [{"id": "fixture-review", "source_id": wall.SOURCES[0]["id"],
                       "section": "sports", "title": "Synthetic fixture event",
                       "url": "https://example.com/synthetic", "published_at": "2026-11-01",
                       "first_seen_at": STAMP, "updated_at": STAMP, "format": "article",
                       "topics": ["F1"], "summary": "", "analysis": None}]
    item = value["items"][0]
    digest = wall.item_content_hash(item)
    packet = {"version": 1, "reviews": [{"item_id": item["id"], "content_hash": digest,
              "analysis": {"text": "Synthetic reasoning for a test fixture.", "basis": "Synthetic public excerpt",
                           "reviewed_at": STAMP, "source_urls": [item["url"]],
                           "key_takeaway": "Fixture result needs no real-world action.",
                           "worth_reading": "skim", "rationale": "The fixture is brief.",
                           "scope": "excerpt", "confidence": "medium", "content_hash": digest},
              "evidence": [{"url": item["url"], "published_at": item["published_at"],
                            "retrieved_at": STAMP, "content_hash": hashlib.sha256(b"Synthetic fixture text").hexdigest(),
                            "scope": "excerpt"}]}]}
    return value, packet


class WallReviewTests(unittest.TestCase):
    def test_queue_has_current_hash_and_no_raw_body(self):
        value, _ = fixture()
        queue = wall_review.review_queue(value)
        self.assertEqual(len(queue["items"]), 1)
        self.assertEqual(queue["items"][0]["content_hash"], wall.item_content_hash(value["items"][0]))
        self.assertEqual(queue["coverage"]["missing_reviews"], 1)
        self.assertNotIn("analysis", queue["items"][0])
        self.assertIn("untrusted source data", queue["instruction"])

    def test_review_import_is_idempotent_and_does_not_mutate_input(self):
        value, packet = fixture()
        imported, first = wall_review.apply_packet(value, packet)
        second, again = wall_review.apply_packet(imported, packet)
        self.assertIsNone(value["items"][0]["analysis"])
        self.assertEqual((first["changed"], again["unchanged"]), (1, 1))
        self.assertEqual(imported, second)
        self.assertEqual(wall_review.review_queue(imported)["items"], [])
        self.assertEqual(len(wall_review.review_queue(imported, include_reviewed=True)["items"]), 1)
        self.assertTrue(wall_review.coverage(imported)["complete"])
        self.assertEqual(imported["items"][0]["analysis"]["evidence"], packet["reviews"][0]["evidence"])

    def test_updated_metadata_rejects_old_packet(self):
        value, packet = fixture()
        for key, changed in (("title", "Changed synthetic title"), ("summary", "Changed summary"),
                             ("url", "https://example.com/revision"), ("published_at", None)):
            with self.subTest(key=key):
                newer = deepcopy(value)
                newer["items"][0][key] = changed
                with self.assertRaisesRegex(ValueError, "changed after"):
                    wall_review.apply_packet(newer, packet)

    def test_retrieval_time_does_not_invalidate_same_metadata(self):
        value, packet = fixture()
        value["items"][0]["updated_at"] = "2026-11-02T12:00:00Z"
        value["items"][0]["provenance_hash"] = "f" * 64
        imported, _ = wall_review.apply_packet(value, packet)
        self.assertTrue(wall_review.reviewed(imported["items"][0]))

    def test_scope_cannot_exceed_evidence_access(self):
        value, packet = fixture()
        packet["reviews"][0]["analysis"]["scope"] = "full_text"
        with self.assertRaisesRegex(ValueError, "exceeds"):
            wall_review.apply_packet(value, packet)

    def test_uncited_full_text_cannot_upgrade_unavailable_cited_source(self):
        value, packet = fixture()
        entry = packet["reviews"][0]
        entry["analysis"]["scope"] = "full_text"
        entry["evidence"][0].update(scope="unavailable", content_hash=None)
        entry["evidence"].append({"url": "https://example.com/uncited",
                                  "published_at": None, "retrieved_at": STAMP,
                                  "content_hash": "f" * 64, "scope": "full_text"})
        with self.assertRaisesRegex(ValueError, "exceeds"):
            wall_review.apply_packet(value, packet)

    def test_metadata_does_not_allow_high_confidence(self):
        value, packet = fixture()
        packet["reviews"][0]["analysis"].update(scope="metadata", confidence="high")
        with self.assertRaisesRegex(ValueError, "high-confidence"):
            wall_review.apply_packet(value, packet)

    def test_unavailable_is_explicit_and_returns_to_queue(self):
        value, packet = fixture()
        entry = packet["reviews"][0]
        entry["analysis"].update(scope="unavailable", confidence="low", worth_reading="unavailable",
                                 key_takeaway="Content unavailable; no takeaway can be supported.")
        entry["evidence"][0].update(scope="unavailable", content_hash=None)
        imported, _ = wall_review.apply_packet(value, packet)
        self.assertEqual(len(wall_review.review_queue(imported)["items"]), 1)
        self.assertEqual(wall_review.coverage(imported)["by_scope"], {"unavailable": 1})
        entry["analysis"]["worth_reading"] = "dig_deeper"
        with self.assertRaisesRegex(ValueError, "Unavailable content"):
            wall_review.apply_packet(value, packet)

    def test_partial_access_without_reading_judgment_returns_to_queue(self):
        value, packet = fixture()
        packet["reviews"][0]["analysis"]["worth_reading"] = "unavailable"
        imported, _ = wall_review.apply_packet(value, packet)
        self.assertEqual(len(wall_review.review_queue(imported)["items"]), 1)

    def test_every_source_has_receipt_and_accessed_evidence_has_hash(self):
        value, packet = fixture()
        packet["reviews"][0]["analysis"]["source_urls"].append("https://example.com/no-receipt")
        with self.assertRaisesRegex(ValueError, "evidence receipt"):
            wall_review.apply_packet(value, packet)
        value, packet = fixture()
        packet["reviews"][0]["evidence"][0]["content_hash"] = None
        with self.assertRaisesRegex(ValueError, "SHA256"):
            wall_review.apply_packet(value, packet)

    def test_temporally_inconsistent_review_is_rejected(self):
        value, packet = fixture()
        packet["reviews"][0]["evidence"][0]["retrieved_at"] = "2026-11-02T12:00:00Z"
        with self.assertRaisesRegex(ValueError, "later than its review"):
            wall_review.apply_packet(value, packet)
        value, packet = fixture()
        packet["reviews"][0]["evidence"][0]["published_at"] = "2026-11-02"
        with self.assertRaisesRegex(ValueError, "publication cannot be later"):
            wall_review.apply_packet(value, packet)

    def test_legacy_analysis_stays_valid_but_needs_reading_judgment(self):
        value, packet = fixture()
        value["items"][0]["analysis"] = {key: packet["reviews"][0]["analysis"][key] for key in wall.ANALYSIS_FIELDS}
        wall.validate_public(value)
        self.assertEqual(wall_review.coverage(value)["missing_reviews"], 1)

    def test_whole_batch_fails_without_writing_or_erasing_reviews(self):
        value, packet = fixture()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "wall.json"
            target.write_text(json.dumps(value))
            before = target.read_bytes()
            packet["reviews"].append(deepcopy(packet["reviews"][0]))
            with self.assertRaisesRegex(ValueError, "once per packet"):
                wall_review.import_file(target, packet)
            self.assertEqual(target.read_bytes(), before)

    def test_private_and_extra_content_is_rejected(self):
        value, packet = fixture()
        packet["reviews"][0]["analysis"]["basis"] = "/Users/private-person/notes"
        with self.assertRaisesRegex(ValueError, "Private content"):
            wall_review.apply_packet(value, packet)
        value, packet = fixture()
        packet["reviews"][0]["raw_article_body"] = "Do not export this"
        with self.assertRaisesRegex(ValueError, "packet fields"):
            wall_review.apply_packet(value, packet)

    def test_import_keeps_public_coverage_and_date_fields(self):
        value, packet = fixture()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "wall.json"
            target.write_text(json.dumps(value))
            receipt = wall_review.import_file(target, packet)
            self.assertTrue(receipt["complete"])
            updated = wall.load_file(target, strict=True)
            self.assertEqual(updated["updated_at"], value["updated_at"])
            for key in ("published_at", "first_seen_at", "updated_at"):
                self.assertEqual(updated["items"][0][key], value["items"][0][key])

    def test_cli_coverage_gate_reports_missing_then_complete(self):
        value, packet = fixture()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            target = Path(directory) / "wall.json"
            target.write_text(json.dumps(value))
            self.assertEqual(main(["check", "--data-file", str(target), "--require-complete"]), 2)
            wall_review.import_file(target, packet)
            self.assertEqual(main(["check", "--data-file", str(target), "--require-complete"]), 0)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["queue", "--data-file", str(target), "--output", str(target)]), 1)


if __name__ == "__main__":
    unittest.main()
