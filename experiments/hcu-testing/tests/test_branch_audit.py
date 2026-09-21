"""Behavioral invariants for branch identity, observed CI and recent PR audits."""
import copy
import json
from pathlib import Path
import unittest

import test_functional_audit as legacy
from test_functional_audit import load, ROOT

snapshot=load(ROOT/'skills/hcu-coverage-analysis/scripts/github_snapshot.py')
changes=load(ROOT/'skills/hcu-coverage-analysis/scripts/changes.py')
junit=load(ROOT/'skills/hcu-coverage-analysis/scripts/junit_observations.py')


class BranchAuditTests(unittest.TestCase):
    git=legacy.AuditTests.git
    validate=legacy.AuditTests.validate

    def setUp(self):
        legacy.AuditTests.setUp(self)
        branch=self.git('symbolic-ref','--short','HEAD').strip()
        self.data.update(schema_version=2,target=dict(branch=branch,ref='refs/heads/'+branch),
            runtime=dict(status='unavailable',reason='No artifacts',evidence=[],followups=['G1']),
            recent_prs=dict(since='2026-09-01',until='2026-09-21',status='unavailable',reason='No metadata',items=[],followups=['G1']))
        for f in self.data['features']:
            f.update(change_ids=[],finding=dict(kind='risk',confidence='medium',rationale='Read assertion',counterevidence='Alternatives inspected; fixture only'))
            for cell in f['lanes'].values():
                cell.update(scheduling='unknown',followups=['G1'],observations=[])

    def observe(self):
        self.data['features'][0]['tests'][0]['case_ids']=['Test::test_api']
        run=dict(repository=self.data['repository'],branch=self.data['target']['branch'],lane='pr',platform='CPU',source_commit=self.data['source_commit'],source_identity='verified',
                 source_locator='https://example.invalid/run/1/job/2',run_id='1',job_id='2',attempt=1,granularity='case',status='pass',
                 counts=dict(tests=1,failed=0,errors=0,skipped=0),cases=[dict(id='Test::test_api',path='test_api.py',outcome='passed')])
        self.save_run(run)
        self.data['evidence'].append(dict(id='RUN',kind='run',path='run.json',claim='Observed case',source_commit=run['source_commit'],platform='CPU'))
        self.data['runtime'].update(status='observed',evidence=['RUN'])
        self.data['features'][0]['lanes']['pr'].update(execution='passed',selection='included',scheduling='verified',evidence=['T','CI','RUN'],observations=[dict(evidence='RUN',case_ids=['Test::test_api'])])
        return run

    def save_run(self,run):
        (self.root/'run.json').write_text(json.dumps(run))

    def pr(self):
        item=dict(id='7',url='https://example.invalid/pr/7',base_branch=self.data['target']['branch'],base_sha=self.data['source_commit'],head_sha=self.data['source_commit'],
            state='open',in_target='no',review='reviewed',reason='Actual diff inspected',changes=[dict(id='C7',description='Dedup behavior',feature_ids=['F1'],coverage='partial',evidence=['R'],followups=['G1'])])
        self.data['recent_prs'].update(status='reviewed',items=[item])
        self.data['features'][0]['change_ids']=['C7']
        return item

    def test_design_independent_of_scheduling_and_selection(self):
        self.data['features'][0]['lanes']['daily'].update(coverage='supported',selection='disabled')
        self.assertEqual(self.validate()['features'][0]['lanes']['daily']['coverage'],'supported')

    def test_wrong_branch_tip_rejected(self):
        self.data['target']['ref']='refs/heads/nonexistent'
        with self.assertRaises(ValueError):self.validate()

    def test_shared_followup_can_cover_many_cells(self):
        self.assertEqual(len(self.validate()['tasks']),1)

    def test_missing_shared_followup_rejected(self):
        self.data['features'][0]['lanes']['daily']['followups']=[]
        with self.assertRaises(ValueError):self.validate()

    def test_pass_has_actual_case_identity(self):
        self.observe()
        self.assertTrue(self.validate()['observed_tests'][0]['current_identity'])

    def test_wrong_lane_case_rejected(self):
        run=self.observe();run['lane']='daily';self.save_run(run)
        with self.assertRaises(ValueError):self.validate()

    def test_wrong_platform_payload_rejected(self):
        run=self.observe();run['platform']='OTHER';self.save_run(run)
        with self.assertRaises(ValueError):self.validate()

    def test_historical_run_cannot_prove_tip(self):
        run=self.observe();run['source_commit']='a'*40;self.data['evidence'][-1]['source_commit']='a'*40;self.save_run(run)
        with self.assertRaises(ValueError):self.validate()

    def test_historical_inventory_retained_without_pass_claim(self):
        run=self.observe();run['source_commit']='a'*40;self.data['evidence'][-1]['source_commit']='a'*40;self.save_run(run)
        self.data['features'][0]['lanes']['pr'].update(execution='not_verified',observations=[])
        self.assertFalse(self.validate()['observed_tests'][0]['current_identity'])

    def test_wrong_case_path_rejected(self):
        run=self.observe();run['cases'][0]['path']='other_test.py';self.save_run(run)
        with self.assertRaises(ValueError):self.validate()

    def test_nonexistent_case_id_rejected(self):
        self.observe();self.data['features'][0]['lanes']['pr']['observations'][0]['case_ids']=['missing']
        with self.assertRaises(ValueError):self.validate()

    def test_other_case_in_same_file_does_not_prove_behavior(self):
        self.observe();self.data['features'][0]['tests'][0]['case_ids']=['Test::unrelated']
        with self.assertRaises(ValueError):self.validate()

    def test_file_only_pass_does_not_prove_behavior(self):
        run=self.observe();run['granularity']='file';self.save_run(run)
        with self.assertRaises(ValueError):self.validate()

    def test_unresolved_wheel_source_rejected(self):
        run=self.observe();run['source_identity']='unresolved';self.save_run(run)
        with self.assertRaises(ValueError):self.validate()

    def test_all_skipped_not_pass(self):
        run=self.observe();run['cases'][0]['outcome']='skipped';run['counts']['skipped']=1;self.save_run(run)
        with self.assertRaises(ValueError):self.validate()

    def test_wrong_counts_rejected(self):
        run=self.observe();run['counts']['tests']=100;self.save_run(run)
        with self.assertRaises(ValueError):self.validate()

    def test_cyclic_dependencies_rejected(self):
        self.data['tasks'][0]['depends_on']=['G1']
        with self.assertRaises(ValueError):self.validate()

    def test_open_pr_not_landed(self):
        self.pr()['in_target']='yes'
        with self.assertRaises(ValueError):self.validate()

    def test_pr_change_mapping(self):
        self.pr();self.assertEqual(self.validate()['recent_prs']['items'][0]['changes'][0]['feature_ids'],['F1'])

    def test_unmapped_pr_change_rejected(self):
        self.pr();self.data['features'][0]['change_ids']=[]
        with self.assertRaises(ValueError):self.validate()

    def test_unreviewed_pr_not_hidden(self):
        item=self.pr();item.update(review='deferred',followups=['G1'])
        with self.assertRaises(ValueError):self.validate()

    def test_no_task_for_change_rejected(self):
        self.pr()['changes'][0]['followups']=[]
        with self.assertRaises(ValueError):self.validate()

    def test_diff_includes_removed_and_renamed_tests(self):
        base=self.data['source_commit']
        self.git('mv','test_api.py','test_new.py')
        (self.repo/'api.py').write_text('def sort_items(x):\n    return x\n')
        self.git('add','.');self.git('-c','user.name=fixture','-c','user.email=f@example.invalid','commit','-qm','change')
        head=self.git('rev-parse','HEAD').strip()
        result=changes.collect(self.repo,base,head,head)
        self.assertTrue(any(f['status'].startswith('R') for f in result['files']))
        self.assertIn('return x',result['patch'])
        self.assertTrue(result['head_ancestor_of_target'])
        with self.assertRaises(ValueError):changes.collect(self.repo,head,head,head)

    def test_prospective_pr_diff_artifact_can_be_cited(self):
        (self.root/'diff.json').write_text('{"patch":"prospective behavior"}')
        self.data['evidence'].append(dict(id='DIFF',kind='artifact',path='diff.json',claim='Pinned PR diff'))
        self.pr()['changes'][0]['evidence']=['DIFF']
        self.assertIn('sha256',self.validate()['evidence'][-1])


class DiscoveryTests(unittest.TestCase):
    def test_pagination_truncation_is_explicit(self):
        def fake(path):return {'workflow_runs':[{'id':1}]},'<https://api.github.com/next>; rel="next"'
        items,truncated=snapshot.pages('/first','workflow_runs',1,fake)
        self.assertEqual(len(items),1);self.assertTrue(truncated)

    def test_discovery_queries_all_events_and_requires_pr_detail(self):
        paths=[]
        def fake(path):
            paths.append(path)
            if '/branches/' in path:return {'commit':{'sha':'a'*40}},''
            if '/actions/runs?' in path:return {'workflow_runs':[]},''
            if '/pulls?' in path:return [dict(number=7,updated_at='2026-09-20T00:00:00Z')],''
            if path.endswith('/pulls/7'):return dict(number=7,html_url='https://example.invalid/7',title='change',state='open',merged_at=None,updated_at='2026-09-20T00:00:00Z',base=dict(ref='release/x',sha='a'*40),head=dict(sha='b'*40)),''
            raise AssertionError(path)
        result=snapshot.collect('o/r','release/x','2026-09-01T00:00:00Z',fetch=fake)
        self.assertFalse(any('event=' in p for p in paths))
        self.assertEqual(result['prs'][0]['state'],'open')
        self.assertIn('/repos/o/r/pulls/7',paths)

    def context(self):
        return dict(repository='r',branch='b',lane='pr',platform='CPU',source_commit='a'*40,source_identity='unresolved',run_id='1',job_id='2',attempt=1,source_locator='url')

    def test_junit_skip_is_not_pass(self):
        result=junit.normalize(b'<testsuite><testcase classname="C" name="t" file="test.py"><skipped/></testcase></testsuite>',self.context())
        self.assertEqual(result['status'],'no_tests_executed')

    def test_junit_does_not_guess_source_from_classname(self):
        with self.assertRaises(ValueError):junit.normalize(b'<testsuite><testcase classname="test_api" name="t"/></testsuite>',self.context())

    def test_junit_keeps_failure_without_payload(self):
        result=junit.normalize(b'<testsuite><testcase name="t" file="test.py"><failure>secret request</failure></testcase></testsuite>',self.context())
        self.assertEqual(result['counts']['failed'],1)
        self.assertNotIn('secret',json.dumps(result))


if __name__=='__main__':unittest.main()
