"""Publication boundaries use reviewed public JSON and temporary build directories."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from scripts.build_site import ROOT, OUTPUTS, build, dashboard, validate_public


class PublicBuildTests(unittest.TestCase):
    def setUp(self):
        self.raw=json.loads((ROOT/'public/brief.json').read_text())

    def test_only_allowlisted_static_files_and_relative_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'site'
            manifest=build(target)
            self.assertEqual({str(p.relative_to(target)) for p in target.rglob('*') if p.is_file()},OUTPUTS)
            html=(target/'index.html').read_text()
            self.assertIn('data-mode="static"',html)
            self.assertIn('href="./styles.css"',html)
            self.assertIn('src="./app.js"',html)
            self.assertNotIn('href="/styles.css"',html)
            data=json.loads((target/'data/dashboard.json').read_text())
            self.assertEqual(data['publication']['reviewed_at'],self.raw['reviewed_at'])
            self.assertEqual(data['refreshes'],[])
            self.assertEqual(data['leads'],[])
            self.assertEqual(data['stats']['source_ok'],0)
            self.assertFalse(data['x_access']['can_capture'])
            self.assertEqual(manifest['reviewed_at'],self.raw['reviewed_at'])
            self.assertEqual(build(target),manifest)

    def test_private_path_is_rejected(self):
        raw=deepcopy(self.raw);raw['articles'][0]['observation']='/Users/example/private/file'
        with self.assertRaises(ValueError): validate_public(raw)

    def test_unknown_export_fields_are_rejected(self):
        raw=deepcopy(self.raw);raw['database_export']={'private':'text'}
        with self.assertRaises(ValueError): validate_public(raw)
        raw=deepcopy(self.raw);raw['articles'][0]['private_note']='not for publication'
        with self.assertRaises(ValueError): validate_public(raw)
        raw=deepcopy(self.raw);raw['ledger'][0]['private_note']='not for publication'
        with self.assertRaises(ValueError): validate_public(raw)

    def test_future_review_and_unreviewed_sources_are_rejected(self):
        raw=deepcopy(self.raw);raw['reviewed_at']='2099-01-01T00:00:00Z'
        with self.assertRaises(ValueError): validate_public(raw)
        raw=deepcopy(self.raw);raw['sources'][0]['role']='discovery'
        with self.assertRaises(ValueError): validate_public(raw)

    def test_missing_or_duplicate_evidence_is_rejected(self):
        raw=deepcopy(self.raw);raw['articles'][0]['source_id']='not-in-reviewed-sources'
        with self.assertRaises(ValueError): validate_public(raw)
        raw=deepcopy(self.raw);raw['articles'][1]['id']=raw['articles'][0]['id']
        with self.assertRaises(ValueError): validate_public(raw)

    def test_existing_unexpected_file_is_not_deleted_or_published(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'site';target.mkdir();private=target/'private.db';private.write_text('synthetic sentinel')
            with self.assertRaises(ValueError): build(target)
            self.assertEqual(private.read_text(),'synthetic sentinel')

    def test_conditional_editorial_text_is_preserved(self):
        output=dashboard(self.raw,[],'a'*40)
        self.assertEqual(output['articles'][0]['implication'],self.raw['articles'][0]['implication'])
        self.assertEqual(output['publication']['commit'],'a'*40)
        self.assertEqual(output['sources'][0]['status'],'reviewed')
        self.assertNotIn('last_success_at',output['sources'][0])
        self.assertEqual(output['earnings'][0]['guidance'],self.raw['earnings'][0]['guidance'])

    def test_highlights_reject_unreviewed_sources_and_private_fields(self):
        raw=deepcopy(self.raw)
        raw['articles'][0]['highlights']=[{'title':'Example','observation':'Synthetic test','claim_type':'management claim','implication':'Conditional','source_url':'https://example.com/unreviewed','source_date':'2026-01-01'}]
        with self.assertRaises(ValueError): validate_public(raw)
        raw['articles'][0]['highlights'][0]['source_url']=raw['sources'][0]['url']
        raw['articles'][0]['highlights'][0]['private_note']='synthetic'
        with self.assertRaises(ValueError): validate_public(raw)

    def test_layer_ids_and_old_review_dates_remain_explicit(self):
        raw=deepcopy(self.raw);raw['articles'][0]['ai_layers']=['unknown']
        with self.assertRaises(ValueError): validate_public(raw)
        raw=deepcopy(self.raw);raw['articles'][0]['reviewed_at']='2099-01-01'
        with self.assertRaises(ValueError): validate_public(raw)
        output=dashboard(self.raw,[],'uncommitted')
        self.assertTrue(output['publication']['draft'])
        self.assertEqual(len(output['layer_tracking']['layers']),5)
        for original,article in zip(sorted(self.raw['articles'],key=lambda a:a['rank']),output['articles']):
            self.assertEqual(article.get('reviewed_at'),original.get('reviewed_at'))

if __name__=='__main__': unittest.main()
