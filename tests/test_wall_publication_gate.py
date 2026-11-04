"""Public builds require review dispositions; all synthetic walls stay temporary."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pulse import wall, wall_review
from scripts import build_site
from test_wall_review import fixture


class WallPublicationGateTests(unittest.TestCase):
    def build_fixture(self, directory, value):
        root = Path(directory) / "source"
        (root / "public").mkdir(parents=True)
        (root / "public/wall.json").write_text(json.dumps(value))
        for name in ("static", "config"):
            shutil.copytree(build_site.ROOT / name, root / name)
        output = Path(directory) / "site"
        source = build_site.ROOT / "public/brief.json"
        with patch.object(build_site, "ROOT", root):
            result = build_site.build(output, source=source)
        return output, result

    def test_missing_structured_review_stops_before_artifact_creation(self):
        value, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "1 displayed item.*lack a current structured"):
                self.build_fixture(directory, value)
            self.assertFalse((Path(directory) / "site").exists())

    def test_explicit_unavailable_disposition_can_be_published_honestly(self):
        value, packet = fixture()
        entry = packet["reviews"][0]
        entry["analysis"].update(scope="unavailable", confidence="low", worth_reading="unavailable")
        entry["evidence"][0].update(scope="unavailable", content_hash=None)
        value, _ = wall_review.apply_packet(value, packet)
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.build_fixture(directory, value)
            published = json.loads((output / "data/dashboard.json").read_text())["personal_wall"]
            self.assertEqual(published["items"][0]["analysis"]["worth_reading"], "unavailable")
            self.assertEqual(published["items"][0]["analysis"]["scope"], "unavailable")

    def test_only_projected_items_require_review_and_enter_artifact(self):
        value, packet = fixture()
        value, _ = wall_review.apply_packet(value, packet)
        original = value["items"][0]
        value["items"] = [{**deepcopy(original), "id": "fixture-" + str(i)}
                          for i in range(wall.MAX_PUBLIC_ITEMS_PER_SOURCE)]
        old = {**deepcopy(original), "id": "old-unreviewed", "published_at": "2026-10-01", "analysis": None}
        old["content_hash"] = wall.item_content_hash(old)
        value["items"].append(old)
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.build_fixture(directory, value)
            published = json.loads((output / "data/dashboard.json").read_text())["personal_wall"]
            self.assertEqual(len(published["items"]), wall.MAX_PUBLIC_ITEMS_PER_SOURCE)
            self.assertNotIn("old-unreviewed", {item["id"] for item in published["items"]})


if __name__ == "__main__":
    unittest.main()
