"""Queue fairness regressions with synthetic content, never production data."""
from collections import Counter
from copy import deepcopy
import unittest

from pulse import wall, wall_review


STAMP = "2026-11-27T12:00:00Z"
UW_SOURCE = "unusual-whales-blog"
# The four identifiers reproduce the November 25/26 selection failure, but all
# dates and content below are explicit test fixtures rather than source evidence.
NOV25_WAITING = (
    "wall-c3501c87dfb3159a7eef13fb", "wall-f2661a182dfb5e8beca212b1",
    "wall-3c8827bfa4b62bddc08b0c28", "wall-15eac196346ac25a4c2f943a",
)


def add_item(payload, item_id, source_id=UW_SOURCE, seen="2026-11-25T12:00:00Z",
             published="2026-11-25", updated=STAMP):
    source = next(source for source in payload["source_status"] if source["id"] == source_id)
    item = {"id": item_id, "source_id": source_id, "section": source["section"],
            "title": "Synthetic queue fixture " + item_id, "url": "https://example.com/" + item_id,
            "published_at": published, "first_seen_at": seen, "updated_at": updated,
            "format": "article", "topics": ["Synthetic"], "summary": "", "analysis": None}
    payload["items"].append(item)
    return item


def mark_reviewed(item, attempted=STAMP, unavailable=False):
    scope = "unavailable" if unavailable else "excerpt"
    item["analysis"] = {
        "text": "Synthetic test disposition.", "basis": "Synthetic test fixture only.",
        "reviewed_at": attempted, "source_urls": [item["url"]],
        "key_takeaway": "Fixture needs no real-world action.",
        "worth_reading": "unavailable" if unavailable else "skim",
        "rationale": "Synthetic queue fairness test.", "scope": scope,
        "confidence": "low" if unavailable else "medium",
        "content_hash": wall.item_content_hash(item),
        "evidence": [{"url": item["url"], "published_at": None, "retrieved_at": attempted,
                      "content_hash": None if unavailable else "a" * 64, "scope": scope}],
    }


class WallQueueFairnessTests(unittest.TestCase):
    def test_nov25_waiting_four_precede_eight_newer_never_reviewed(self):
        payload = wall.empty_payload()
        for item_id in NOV25_WAITING:
            add_item(payload, item_id)
        for day in (26, 27):
            for index in range(4):
                add_item(payload, "new-%s-%s" % (day, index),
                         seen="2026-11-%sT12:00:00Z" % day,
                         published="2026-11-%s" % day)
        queue = wall_review.review_queue(payload)
        self.assertEqual([row["id"] for row in queue["items"]], sorted(NOV25_WAITING))
        self.assertEqual(queue["selection"]["deferred_items"], 8)
        self.assertEqual(queue["coverage"]["missing_reviews"], 12)

    def test_required_judgments_across_sources_precede_optional_retries(self):
        payload = wall.empty_payload()
        for index in range(4):
            item = add_item(payload, "required-%s" % index)
            if index == 0:
                # Legacy commentary has no current item-bound reading judgment.
                item["analysis"] = {"text": "Old synthetic commentary.", "basis": "Test fixture.",
                                    "reviewed_at": "2026-11-25T12:00:00Z", "source_urls": [item["url"]]}
        for index in range(4):
            retry = add_item(payload, "retry-%s" % index, "f1-official")
            mark_reviewed(retry, "2026-11-25T12:00:00Z", unavailable=True)
        same_source_retry = add_item(payload, "same-source-retry")
        mark_reviewed(same_source_retry, unavailable=True)
        queue = wall_review.review_queue(payload, limit=6)
        self.assertEqual([row["id"] for row in queue["items"][:4]],
                         ["required-%s" % index for index in range(4)])
        self.assertEqual([row["id"] for row in queue["items"][4:]], ["retry-0", "retry-1"])
        self.assertNotIn("same-source-retry", [row["id"] for row in queue["items"]])
        self.assertEqual(queue["selection"]["deferred_items"], 3)

    def test_changed_item_cleared_review_is_required_and_stale_hash_still_rejected(self):
        payload = wall.empty_payload()
        changed = add_item(payload, "changed")
        mark_reviewed(changed)
        changed["summary"] = "Synthetic material revision."
        with self.assertRaisesRegex(ValueError, "current item content"):
            wall_review.review_queue(payload)
        # Normal ingestion clears invalidated analysis rather than importing a
        # stale judgment. Queue priority must not depend on an absent attempt.
        changed["analysis"] = None
        retry = add_item(payload, "retry", "f1-official")
        mark_reviewed(retry, unavailable=True)
        self.assertEqual(wall_review.review_queue(payload, limit=1)["items"][0]["id"], "changed")

    def test_continuing_new_arrivals_do_not_starve_displayed_waiting_items(self):
        payload = wall.empty_payload()
        sources = (UW_SOURCE, "f1-official", "nba-communications")
        waiting = set()
        for source in sources:
            for index in range(3):
                item_id = "%s-old-%s" % (source, index)
                add_item(payload, item_id, source, seen="2026-11-23T12:00:00Z", published="2026-11-23")
                waiting.add(item_id)
        for day in (24, 25, 26):
            for source in sources:
                add_item(payload, "%s-new-%s" % (source, day), source,
                         seen="2026-11-%sT12:00:00Z" % day, published="2026-11-%s" % day)
            selected = wall_review.review_queue(payload, limit=3, per_source=2)["items"]
            self.assertEqual(Counter(row["source_id"] for row in selected), Counter(sources))
            self.assertTrue({row["id"] for row in selected} <= waiting)
            for row in selected:
                mark_reviewed(next(item for item in payload["items"] if item["id"] == row["id"]),
                              "2026-11-%sT12:00:00Z" % day)
                waiting.remove(row["id"])
        self.assertFalse(waiting)

    def test_defaults_are_bounded_and_source_round_robin_is_preserved(self):
        payload = wall.empty_payload()
        sources = [source["id"] for source in payload["source_status"][:7]]
        for source in sources:
            for index in range(5):
                add_item(payload, "%s-%s" % (source, index), source)
        queue = wall_review.review_queue(payload)
        counts = Counter(row["source_id"] for row in queue["items"])
        self.assertEqual(len(queue["items"]), 24)
        self.assertEqual(set(counts), set(sources))
        self.assertTrue(all(3 <= count <= 4 for count in counts.values()))
        self.assertEqual(len({row["source_id"] for row in queue["items"][:7]}), 7)
        self.assertEqual(queue["selection"], {"limit": 24, "per_source": 4, "eligible_items": 35,
                                               "deferred_items": 11, "source_count": 7})

    def test_first_seen_is_stable_and_date_fallbacks_and_ties_are_deterministic(self):
        payload = wall.empty_payload()
        add_item(payload, "seen-old", seen="2026-11-01T10:00:00Z", published="2026-11-27")
        add_item(payload, "seen-new", seen="2026-11-02T10:00:00Z", published="2020-01-01")
        add_item(payload, "fallback-day", seen=None, published="2026-11-03")
        add_item(payload, "fallback-update", seen=None, published=None, updated="2026-11-04T10:00:00Z")
        add_item(payload, "tie-b", seen="2026-11-05T10:00:00Z")
        add_item(payload, "tie-a", seen="2026-11-05T12:00:00+02:00")
        add_item(payload, "undated", seen=None, published=None, updated=None)
        original = deepcopy(payload)
        expected = ["undated", "seen-old", "seen-new", "fallback-day", "fallback-update", "tie-a", "tie-b"]
        selected = wall_review.review_queue(payload, per_source=8)["items"]
        self.assertEqual([row["id"] for row in selected], expected)
        payload["items"].reverse()
        repeated = wall_review.review_queue(payload, per_source=8)["items"]
        self.assertEqual(repeated, selected)
        payload["items"].reverse()
        self.assertEqual(payload, original)
        self.assertIsNone(next(row for row in selected if row["id"] == "fallback-update")["published_at"])

    def test_optional_retries_use_oldest_attempt_then_stable_age(self):
        payload = wall.empty_payload()
        for item_id, attempted in (("recent-attempt", "2026-11-27T12:00:00Z"),
                                   ("old-attempt-b", "2026-11-25T12:00:00Z"),
                                   ("old-attempt-a", "2026-11-25T12:00:00Z")):
            item = add_item(payload, item_id)
            mark_reviewed(item, attempted, unavailable=True)
        selected = wall_review.review_queue(payload, limit=2)["items"]
        self.assertEqual([row["id"] for row in selected], ["old-attempt-a", "old-attempt-b"])

    def test_older_waiting_sources_progress_across_runs_with_small_global_limit(self):
        payload = wall.empty_payload()
        for index, source in enumerate(payload["source_status"][:3]):
            add_item(payload, "old-%s" % index, source["id"], seen="2026-11-2%sT12:00:00Z" % index)
        for index in range(3):
            selected = wall_review.review_queue(payload, limit=1)["items"][0]
            self.assertEqual(selected["id"], "old-%s" % index)
            mark_reviewed(next(item for item in payload["items"] if item["id"] == selected["id"]))
            add_item(payload, "arrival-%s" % index, payload["source_status"][0]["id"], seen=STAMP)


if __name__ == "__main__":
    unittest.main()
