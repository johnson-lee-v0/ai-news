"""Publication boundaries use reviewed public JSON and temporary build directories."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from scripts.build_site import ROOT, OUTPUTS, READING_REVIEW_BASIS, build, dashboard, reading_content_hash, validate_public


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

    def test_snapshot_capacity_keeps_finite_bounds_and_evidence_checks(self):
        raw=deepcopy(self.raw)
        for index in range(len(raw['articles']),42):
            item=deepcopy(raw['articles'][0]);item['id']='synthetic-capacity-article-'+str(index)
            item['rank']=index+1;raw['articles'].append(item)
        for index in range(len(raw['sources']),151):
            source=deepcopy(raw['sources'][0]);source['id']='synthetic-capacity-source-'+str(index)
            raw['sources'].append(source)
        validate_public(raw)
        self.assertEqual((len(raw['articles']),len(raw['sources'])),(42,151))
        for section in ('articles','sources'):
            oversized=deepcopy(raw)
            extra=deepcopy(oversized[section][0]);extra['id']='synthetic-over-limit'
            oversized[section].append(extra)
            with self.assertRaisesRegex(ValueError,'small and populated'):
                validate_public(oversized)
        invalid=deepcopy(raw);invalid['articles'][0]['source_id']='synthetic-unreviewed-source'
        with self.assertRaisesRegex(ValueError,'unknown public source'):
            validate_public(invalid)
        stale=deepcopy(raw);stale['articles'][0]['observation']='Changed synthetic observation'
        with self.assertRaisesRegex(ValueError,'does not match the current research content'):
            validate_public(stale)

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

    def test_public_takeaways_preserve_reviewed_content_and_coverage_limits(self):
        before=deepcopy(self.raw)
        output=dashboard(self.raw,[],'a'*40)
        self.assertEqual(self.raw,before)
        self.assertEqual(output['brief']['bullets'],before['bullets'])
        self.assertEqual(output['brief']['priority_takeaways'],[])
        self.assertNotIn('priority_questions',output['brief'])
        for domain in output['coverage']['domains']:
            self.assertTrue(domain['takeaway'])
            self.assertNotIn('?',domain['takeaway'])
            self.assertNotIn('question',domain)
            self.assertIn(domain['status'],('snapshot','gap'))
        for original,item in zip(sorted(before['articles'],key=lambda a:a['rank']),output['articles']):
            for field in ('implication','counterevidence','uncertainty','published_at','url'):
                self.assertEqual(item.get(field),original.get(field))

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

    def test_financing_sources_must_be_reviewed_and_not_future(self):
        raw=deepcopy(self.raw);raw['ledger'][0]['source_url']='https://example.com/not-reviewed'
        with self.assertRaises(ValueError): validate_public(raw)
        raw=deepcopy(self.raw);raw['ledger'][0]['sources']=[{'url':raw['sources'][0]['url'],'date':'2099-01-01','title':'Synthetic future source'}]
        with self.assertRaises(ValueError): validate_public(raw)
        raw=deepcopy(self.raw);raw['sources'][0]['source_date']='2099-01-01'
        with self.assertRaises(ValueError): validate_public(raw)

    def test_financing_flow_and_supplemental_private_fields_rejected(self):
        raw=deepcopy(self.raw);raw['ledger'][0]['flow_type']='guessed cash'
        with self.assertRaises(ValueError): validate_public(raw)
        raw=deepcopy(self.raw);raw['ledger'][0]['sources']=[{'url':raw['sources'][0]['url'],'date':'2026-01-01','title':'Synthetic source','private_note':'excluded'}]
        with self.assertRaises(ValueError): validate_public(raw)

    def reading_review(self):
        return {'key_takeaway':'Synthetic concise reading takeaway.',
                'worth_reading':'skim','rationale':'Synthetic reading rationale.',
                'basis':READING_REVIEW_BASIS,
                'reviewed_at':datetime.now(timezone.utc).isoformat(),
                'content_hash':reading_content_hash(self.raw['articles'][0])}

    def test_reading_review_cannot_survive_changed_research_content(self):
        for field in ('title','observation','summary','implication','uncertainty','counterevidence'):
            with self.subTest(field=field):
                raw=deepcopy(self.raw)
                raw['articles'][0][field]='Changed synthetic research content'
                with self.assertRaisesRegex(ValueError,'does not match the current research content'):
                    validate_public(raw)
        item=deepcopy(self.raw['articles'][0])
        digest=reading_content_hash(item)
        item['rank']=999
        item['reviewed_at']='2026-01-01T00:00:00Z'
        item['reading_review']['reviewed_at']='2026-11-01T00:00:00Z'
        self.assertEqual(reading_content_hash(item),digest)

    def test_reading_review_preserves_evidence_and_its_older_review_date(self):
        raw=deepcopy(self.raw)
        raw['articles'][0]['reading_review']=self.reading_review()
        before=deepcopy(raw)
        validate_public(raw)
        output=dashboard(raw,[],'a'*40)
        self.assertEqual(raw,before)
        self.assertEqual(output['publication']['reviewed_at'],before['reviewed_at'])
        for item in output['articles']:
            original=next(a for a in before['articles'] if a['id']==item['id'])
            for field in ('reading_review','reviewed_at','published_at','observation','implication','uncertainty'):
                self.assertEqual(item.get(field),original.get(field))

    def test_reading_review_requires_exact_bounded_and_honest_fields(self):
        for field,value in [('worth_reading','buy'),('key_takeaway',''),('key_takeaway','x'*351),
                            ('rationale','x'*501),('basis','All originals newly verified'),
                            ('reviewed_at','2099-01-01T00:00:00Z'),('reviewed_at','2020-01-01T00:00:00Z'),
                            ('reviewed_at','2026-11-03'),('reviewed_at','invalid')]:
            with self.subTest(field=field,value=value):
                raw=deepcopy(self.raw);review=self.reading_review();review[field]=value
                raw['articles'][0]['reading_review']=review
                with self.assertRaises(ValueError): validate_public(raw)
        for mode in ('extra','missing'):
            raw=deepcopy(self.raw);review=self.reading_review()
            if mode=='extra': review['private_note']='Synthetic excluded field'
            else: review.pop('basis')
            raw['articles'][0]['reading_review']=review
            with self.assertRaises(ValueError): validate_public(raw)

if __name__=='__main__': unittest.main()
