"""Route discovery regression: branch-only metadata must not hide PR/nightly CI."""
import unittest
from urllib.parse import urlparse,parse_qs
from test_functional_audit import load, ROOT

snapshot=load(ROOT/'skills/hcu-coverage-analysis/scripts/github_snapshot.py')


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.paths=[];self.fail=set()

    def fetch(self,path):
        self.paths.append(path)
        parsed=urlparse(path);q=parse_qs(parsed.query);p=parsed.path
        if '/branches/' in p:return {'commit':{'sha':'a'*40}},''
        if '/pulls?' in path:
            if 'pr_list' in self.fail:raise RuntimeError('denied')
            return [dict(number=7,updated_at='2026-09-20T00:00:00Z')],''
        if p.endswith('/pulls/7'):
            if 'pr' in self.fail:raise RuntimeError('denied')
            return dict(number=7,html_url='https://example.invalid/7',title='change',state='open',merged_at=None,updated_at='2026-09-20T00:00:00Z',base=dict(ref='release/x',sha='a'*40),head=dict(sha='b'*40)),''
        if p.endswith('/runs'):
            if 'branch' in q:
                if 'branch' in self.fail:raise RuntimeError('denied')
                ids=[1,4,5]
            elif 'head_sha' in q:
                self.assertEqual(q['head_sha'],['b'*40]);ids=[2]
            else:
                self.assertIn('/workflows/nightly.yml/',p);ids=[3,2]
            return {'workflow_runs':[dict(id=i,event='pull_request_target' if i==2 else 'schedule',head_sha='b'*40 if i==2 else 'a'*40) for i in ids]},''
        if p.endswith('/jobs'):return {'jobs':[dict(id=100,name='test',status='completed',conclusion='skipped')]},''
        if p.endswith('/artifacts'):
            if 'artifacts' in self.fail:raise RuntimeError('denied')
            return {'artifacts':[]},''
        raise AssertionError(path)

    def collect(self,**kw):
        return snapshot.collect('o/r','release/x','2026-09-01T00:00:00Z',fetch=self.fetch,workflows=['nightly.yml'],**kw)

    def test_pr_head_and_default_workflow_found_without_event_filter(self):
        d=self.collect()
        self.assertEqual({r['id'] for r in d['runs']},{1,2,3,4,5})
        self.assertFalse(any('event=' in p for p in self.paths))
        workflow=[p for p in self.paths if '/workflows/' in p][0]
        self.assertNotIn('branch=',workflow)

    def test_duplicate_run_keeps_all_discovery_routes(self):
        d=self.collect();r=next(x for x in d['run_candidates'] if x['id']==2)
        self.assertEqual(set(r['discovered_via']),{'pr_head:7','workflow:nightly.yml'})
        self.assertEqual(sum(x['id']==2 for x in d['runs']),1)

    def test_budget_does_not_hide_candidates_or_starve_workflows(self):
        d=self.collect(max_runs=2)
        self.assertEqual([r['id'] for r in d['runs']],[1,3])
        self.assertTrue(d['truncated']['runs'])
        self.assertEqual(len(d['run_candidates']),5)
        self.assertEqual(sum(x['detail_status']=='deferred_budget' for x in d['run_candidates']),3)

    def test_branch_denial_is_not_empty_history(self):
        self.fail={'branch'};d=self.collect()
        self.assertTrue(d['discovery_incomplete'])
        self.assertEqual(d['discovery_routes'][0]['status'],'unavailable')
        self.assertIn(2,[r['id'] for r in d['runs']])

    def test_pr_detail_denial_keeps_other_routes(self):
        self.fail={'pr'};d=self.collect()
        self.assertEqual(d['unavailable_pr_details'],[7])
        self.assertTrue(d['discovery_incomplete'])
        self.assertIn(3,[r['id'] for r in d['runs']])

    def test_pr_list_denial_keeps_workflow_discovery(self):
        self.fail={'pr_list'};d=self.collect()
        self.assertEqual(d['pr_discovery_status'],'unavailable')
        self.assertTrue(d['discovery_incomplete'])
        self.assertIn(3,[r['id'] for r in d['runs']])

    def test_artifact_denial_preserves_jobs(self):
        self.fail={'artifacts'};d=self.collect()
        self.assertTrue(d['detail_incomplete'])
        for r in d['runs']:
            self.assertEqual(r['jobs'][0]['conclusion'],'skipped')
            self.assertEqual(r['evidence_unavailable'],['artifacts'])
            self.assertNotIn('artifacts',r)

    def test_workflow_input_cannot_change_api_path(self):
        with self.assertRaises(ValueError):snapshot.collect('o/r','x','2026-09-01',fetch=self.fetch,workflows=['../runs?event=push'])
        self.assertEqual(self.paths,[])

    def test_pr_detail_budget_retains_full_candidate_queue(self):
        def fetch(path):
            if '/pulls?' in path:
                return [dict(number=n, updated_at='2026-09-20T00:00:00Z') for n in (7, 8, 9)], ''
            return self.fetch(path)
        d = snapshot.collect('o/r','release/x','2026-09-01T00:00:00Z',fetch=fetch,max_prs=1)
        self.assertEqual([p['id'] for p in d['pr_candidates']], ['7','8','9'])
        self.assertEqual(d['pr_candidates'][1]['detail_status'], 'deferred_budget')
        self.assertTrue(d['truncated']['prs'])


if __name__=='__main__':unittest.main()
