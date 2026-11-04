"""The personal wall must survive market updates without weakening publication boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from scripts.build_site import ROOT, build
from pulse import wall

class WallPublicationTests(unittest.TestCase):
    def test_independent_wall_retained_when_market_editorial_text_changes(self):
        raw=json.loads((ROOT/'public/brief.json').read_text())
        personal=json.loads((ROOT/'public/wall.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp); source=p/'brief.json'; raw['headline']='Updated synthetic editorial headline'; source.write_text(json.dumps(raw))
            build(p/'site',source=source)
            data=json.loads((p/'site/data/dashboard.json').read_text())
            self.assertEqual(data['personal_wall'],wall.public_projection(personal))
            self.assertEqual(len(data['articles']),len(raw['articles']))
            self.assertEqual(data['ledger'],raw['ledger'])
            self.assertEqual(data['earnings'],raw['earnings'])

    def test_both_assets_and_narrow_csp_published(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'site';manifest=build(p)
            self.assertIn('wall.js',manifest['files']);self.assertIn('wall.css',manifest['files'])
            html=(p/'index.html').read_text()
            self.assertIn("script-src 'self'",html);self.assertIn("connect-src 'self'",html)
            self.assertIn('frame-src https://www.instagram.com https://www.youtube-nocookie.com',html)
            self.assertIn("object-src 'none'",html)
            self.assertNotIn('unsafe-inline',html);self.assertNotIn('unsafe-eval',html)
            self.assertNotIn('https://*',html)
            self.assertIn('data-panel="sports"',html)

    def test_no_private_fields_or_fake_embedded_model_status(self):
        raw=wall.empty_payload();raw['model_status']['mode']='automatic_gpt'
        with self.assertRaises(ValueError):wall.validate_public(raw)
        raw=wall.empty_payload();raw['private_records']=['synthetic']
        with self.assertRaises(ValueError):wall.validate_public(raw)
        raw=wall.empty_payload();raw['coverage'].append('/Users/example/private')
        with self.assertRaises(ValueError):wall.validate_public(raw)

if __name__=='__main__':unittest.main()
