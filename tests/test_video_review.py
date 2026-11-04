"""Synthetic video review contracts; no real captions or user state are loaded."""
from copy import deepcopy
import unittest

from pulse import wall, wall_review
from test_wall_review import fixture, STAMP


def video_fixture(scope="transcript", verdict="dig_deeper"):
    value, packet = fixture()
    item = value["items"][0]
    item.update(format="video", url="https://www.youtube.com/watch?v=AbCdEfGhI12")
    digest = wall.item_content_hash(item)
    entry = packet["reviews"][0]
    entry["content_hash"] = digest
    entry["analysis"].update(content_hash=digest, scope=scope, worth_reading=verdict,
                             source_urls=[item["url"]], basis="Synthetic transcript fixture; original authored notes.")
    entry["evidence"][0].update(url=item["url"], scope=scope)
    if scope in wall.VIDEO_CONTENT_SCOPES:
        entry["analysis"]["video_citations"] = [{"start_seconds": 12, "end_seconds": 35,
                                                 "note": "Synthetic explanation of the fixture's central claim."}]
    return value, packet


def external_transcript_fixture(scope="transcript"):
    value, packet = video_fixture(scope)
    entry = packet["reviews"][0]
    original = deepcopy(entry["evidence"][0])
    original["scope"] = "metadata"
    external = entry["evidence"][0]
    external["video_url"] = value["items"][0]["url"]
    external["url"] = "https://transcripts.example/yt/AbCdEfGhI12/synthetic"
    entry["evidence"].append(original)
    entry["analysis"]["source_urls"] = [external["url"], original["url"]]
    entry["analysis"]["basis"] = wall.THIRD_PARTY_TRANSCRIPT_BASIS + " Synthetic external transcript fixture."
    return value, packet


class VideoReviewTests(unittest.TestCase):
    def test_external_transcript_preserves_actual_source_and_original_video_binding(self):
        for scope in ("transcript", "partial_transcript"):
            with self.subTest(scope=scope):
                value, packet = external_transcript_fixture(scope)
                imported, _ = wall_review.apply_packet(value, packet)
                analysis = imported["items"][0]["analysis"]
                self.assertEqual(analysis["scope"], scope)
                self.assertEqual(analysis["evidence"][0]["url"], "https://transcripts.example/yt/AbCdEfGhI12/synthetic")
                self.assertEqual(analysis["evidence"][0]["video_url"], value["items"][0]["url"])
                self.assertIn(wall.THIRD_PARTY_TRANSCRIPT_BASIS, analysis["basis"])
                self.assertTrue(wall_review.coverage(imported)["complete"])

    def test_external_transcript_requires_exact_link_original_receipt_and_disclosure(self):
        for change, expected in (("no_video_url", "explicitly linked"), ("wrong_video", "exact canonical"),
                                 ("no_metadata", "original-video metadata"), ("metadata_not_cited", "original-video metadata"),
                                 ("no_disclosure", "must disclose"), ("high_confidence", "cannot have high confidence"),
                                 ("external_not_cited", "actual source URL")):
            with self.subTest(change=change):
                value, packet = external_transcript_fixture()
                entry = packet["reviews"][0]
                if change == "no_video_url":
                    entry["evidence"][0].pop("video_url")
                elif change == "wrong_video":
                    entry["evidence"][0]["video_url"] = "https://www.youtube.com/watch?v=OtherVid123"
                elif change == "no_metadata":
                    entry["evidence"].pop()
                    entry["analysis"]["source_urls"].pop()
                elif change == "metadata_not_cited":
                    entry["analysis"]["source_urls"].pop()
                elif change == "no_disclosure":
                    entry["analysis"]["basis"] = "Transcript accessed."
                elif change == "high_confidence":
                    entry["analysis"]["confidence"] = "high"
                elif change == "external_not_cited":
                    entry["analysis"]["source_urls"].pop(0)
                with self.assertRaisesRegex(ValueError, expected):
                    wall_review.apply_packet(value, packet)

    def test_video_url_annotation_cannot_upgrade_description_or_wrong_youtube_video(self):
        value, packet = external_transcript_fixture()
        packet["reviews"][0]["evidence"][0]["scope"] = "metadata"
        with self.assertRaisesRegex(ValueError, "Only video transcript evidence"):
            wall_review.apply_packet(value, packet)
        value, packet = external_transcript_fixture()
        wrong = "https://www.youtube.com/watch?v=OtherVid123"
        packet["reviews"][0]["evidence"][0]["url"] = wrong
        packet["reviews"][0]["analysis"]["source_urls"][0] = wrong
        with self.assertRaisesRegex(ValueError, "this exact video"):
            wall_review.apply_packet(value, packet)

    def test_transcript_review_retains_timestamps_and_exact_video_provenance(self):
        value, packet = video_fixture()
        imported, _ = wall_review.apply_packet(value, packet)
        review = imported["items"][0]["analysis"]
        self.assertEqual(review["scope"], "transcript")
        self.assertEqual(review["video_citations"][0]["start_seconds"], 12)
        self.assertEqual(wall_review.coverage(imported)["video_content_pending"], 0)
        self.assertEqual(wall_review.review_queue(imported)["items"], [])

    def test_metadata_does_not_support_positive_or_negative_video_verdict(self):
        for scope in ("metadata", "excerpt", "full_text"):
            for verdict in ("dig_deeper", "skim", "skip"):
                with self.subTest(scope=scope, verdict=verdict):
                    value, packet = video_fixture(scope, verdict)
                    with self.assertRaisesRegex(ValueError, "require reviewed transcript or visual content"):
                        wall_review.apply_packet(value, packet)

    def test_metadata_unavailable_remains_publishable_but_queued_for_upgrade(self):
        value, packet = video_fixture("metadata", "unavailable")
        imported, _ = wall_review.apply_packet(value, packet)
        self.assertTrue(wall_review.coverage(imported)["complete"])
        self.assertEqual(wall_review.coverage(imported)["video_content_pending"], 1)
        queue = wall_review.review_queue(imported)
        self.assertEqual(len(queue["items"]), 1)
        self.assertEqual(queue["items"][0]["review_reason"], "video_content_needed")

    def test_legacy_metadata_positive_is_readable_but_blocks_publication_coverage(self):
        value, packet = video_fixture("metadata", "skim")
        entry = packet["reviews"][0]
        value["items"][0]["analysis"] = {**entry["analysis"], "evidence": entry["evidence"]}
        wall.validate_public(value)
        self.assertFalse(wall_review.coverage(value)["complete"])
        self.assertEqual(wall_review.coverage(value)["missing_reviews"], 1)
        self.assertEqual(len(wall_review.review_queue(value)["items"]), 1)

    def test_partial_transcript_needs_ranges_and_does_not_claim_high_confidence(self):
        value, packet = video_fixture("partial_transcript")
        imported, _ = wall_review.apply_packet(value, packet)
        self.assertEqual(imported["items"][0]["analysis"]["scope"], "partial_transcript")
        packet["reviews"][0]["analysis"]["video_citations"][0]["end_seconds"] = None
        with self.assertRaisesRegex(ValueError, "explicit covered ranges"):
            wall_review.apply_packet(value, packet)
        value, packet = video_fixture("partial_transcript")
        packet["reviews"][0]["analysis"]["confidence"] = "high"
        with self.assertRaisesRegex(ValueError, "high-confidence"):
            wall_review.apply_packet(value, packet)

    def test_unrelated_video_transcript_cannot_support_a_recommendation(self):
        value, packet = video_fixture()
        entry = packet["reviews"][0]
        other = "https://www.youtube.com/watch?v=OtherVid123"
        entry["analysis"]["source_urls"] = [other]
        entry["evidence"][0]["url"] = other
        with self.assertRaisesRegex(ValueError, "this exact video"):
            wall_review.apply_packet(value, packet)

    def test_time_links_and_short_urls_match_exact_youtube_video(self):
        value, packet = video_fixture()
        entry = packet["reviews"][0]
        timed = "https://youtu.be/AbCdEfGhI12?t=12"
        entry["analysis"]["source_urls"] = [timed]
        entry["evidence"][0]["url"] = timed
        imported, _ = wall_review.apply_packet(value, packet)
        self.assertTrue(wall_review.coverage(imported)["complete"])

    def test_invalid_timestamps_and_unreviewed_timestamp_claims_rejected(self):
        for field, bad in (("start_seconds", -1), ("start_seconds", True),
                           ("end_seconds", 10), ("end_seconds", 200000), ("note", "x" * 221)):
            with self.subTest(field=field):
                value, packet = video_fixture()
                packet["reviews"][0]["analysis"]["video_citations"][0][field] = bad
                with self.assertRaises(ValueError):
                    wall_review.apply_packet(value, packet)
        value, packet = video_fixture("metadata", "unavailable")
        packet["reviews"][0]["analysis"]["video_citations"] = [{"start_seconds": 0, "end_seconds": 1, "note": "Unsupported timestamp"}]
        with self.assertRaisesRegex(ValueError, "cannot claim video timestamp"):
            wall_review.apply_packet(value, packet)

    def test_citations_respect_known_duration_with_two_second_rounding_tolerance(self):
        for duration in (60, "60", "1:00", "0:01:00"):
            with self.subTest(duration=duration):
                value, packet = video_fixture()
                item = value["items"][0]
                item["duration"] = duration
                entry = packet["reviews"][0]
                entry["content_hash"] = entry["analysis"]["content_hash"] = wall.item_content_hash(item)
                citation = entry["analysis"]["video_citations"][0]
                citation.update(start_seconds=600, end_seconds=610)
                with self.assertRaisesRegex(ValueError, "exceeds the known duration"):
                    wall_review.apply_packet(value, packet)
                citation.update(start_seconds=59, end_seconds=62)
                wall_review.apply_packet(value, packet)
                citation["end_seconds"] = 63
                with self.assertRaisesRegex(ValueError, "exceeds the known duration"):
                    wall_review.apply_packet(value, packet)
        value, packet = video_fixture()
        packet["reviews"][0]["analysis"]["video_citations"][0].update(start_seconds=600, end_seconds=610)
        wall_review.apply_packet(value, packet)

    def test_visual_review_is_explicit_and_never_inferred_from_title(self):
        value, packet = video_fixture("video_viewed")
        imported, _ = wall_review.apply_packet(value, packet)
        self.assertEqual(imported["items"][0]["analysis"]["scope"], "video_viewed")
        packet["reviews"][0]["evidence"][0]["scope"] = "metadata"
        with self.assertRaisesRegex(ValueError, "exceeds"):
            wall_review.apply_packet(value, packet)

    def test_queue_bounds_round_robin_sources_without_personal_seen_state(self):
        value, _ = video_fixture()
        template = value["items"][0]
        value["items"] = []
        sources = value["source_status"][:7]
        for index, source in enumerate(sources):
            for number in range(6):
                value["items"].append({**deepcopy(template), "id": "queue-" + str(index) + "-" + str(number),
                                       "source_id": source["id"], "section": source["section"]})
        queue = wall_review.review_queue(value)
        self.assertEqual(len(queue["items"]), 24)
        counts = {source["id"]: sum(row["source_id"] == source["id"] for row in queue["items"]) for source in sources}
        self.assertTrue(all(3 <= count <= 4 for count in counts.values()))
        self.assertEqual(queue["selection"]["eligible_items"], 42)
        self.assertEqual(queue["selection"]["deferred_items"], 18)
        self.assertTrue(all(row["first_seen_at"] == STAMP for row in queue["items"]))
        smaller = wall_review.review_queue(value, limit=5, per_source=1)
        self.assertEqual(len(smaller["items"]), 5)
        self.assertEqual(len({row["source_id"] for row in smaller["items"]}), 5)
        for limit, per_source in ((0, 4), (201, 4), (24, 0), (24, 25)):
            with self.assertRaises(ValueError):
                wall_review.review_queue(value, limit=limit, per_source=per_source)

    def test_queue_prioritizes_source_without_prior_content_review(self):
        value, packet = video_fixture()
        value, _ = wall_review.apply_packet(value, packet)
        old = value["items"][0]
        first, second = value["source_status"][:2]
        value["items"] += [{**deepcopy(old), "id": "old-source-new-video", "analysis": None},
                           {**deepcopy(old), "id": "new-source-video", "analysis": None,
                            "source_id": second["id"], "section": second["section"]}]
        for item in value["items"]:
            item["content_hash"] = wall.item_content_hash(item)
        queue = wall_review.review_queue(value, limit=1)
        self.assertEqual(queue["items"][0]["source_id"], second["id"])


if __name__ == "__main__":
    unittest.main()
