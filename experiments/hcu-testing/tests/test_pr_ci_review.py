"""PR 版本、证据、执行状态和补测交接的行为回归；不执行被审代码。"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_functional_audit import load, ROOT

review = load(ROOT / 'skills/hcu-coverage-analysis/scripts/pr_review.py')
snapshot = load(ROOT / 'skills/hcu-coverage-analysis/scripts/pr_snapshot.py')
handoff = load(ROOT / 'skills/hcu-test-generation/scripts/check_handoff.py')
runner = load(ROOT / 'skills/hcu-test-runner/scripts/run_tests.py')


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        (self.repo / 'api.py').write_text('def f(x):\n    return x\n')
        (self.repo / 'test_api.py').write_text('raise RuntimeError("must not import target")\n')
        (self.repo / 'ci.yml').write_text('name: fixture\n')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD').strip()
        (self.repo / 'api.py').write_text('def f(x):\n    return abs(x)\n')
        self.commit()
        self.head = self.git('rev-parse', 'HEAD').strip()
        self.snap = dict(snapshot_version=1, repository='https://github.com/fixture/repo',
            captured_at='2026-09-28T00:00:00Z', capture_consistent=True, files_complete=True,
            files=[dict(filename='api.py')], endpoints={'files':dict(status='available', truncated=False)},
            checks=[], statuses=[], runs=[dict(id=1, run_attempt=2, jobs=[dict(id=3, status='completed')])],
            pr=dict(number=1, url='https://github.com/fixture/repo/pull/1', title='fixture',
                    base_branch='main', base_sha=self.base, head_sha=self.head))
        self.data = dict(review_version=1, head_sha=self.head, platform='CPU', summary='夹具审查', limitations=['仅夹具'],
            files=[dict(path='api.py', status='reviewed', reason='接口变化')],
            evidence=[dict(id=id, kind='source', path=path, revision=self.head, start=1, end=1, claim='已读源码')
                      for id,path in [('S','api.py'),('T','test_api.py'),('CI','ci.yml')]],
            behaviors=[dict(id='B1', name='绝对值', changed_paths=['api.py'], before='原值', after='绝对值',
                trigger='负数', risk='负号错误', oracle='固定输入输出', counterevidence='读取现有测试后仅支持部分',
                evidence=['S'], lane='pr', platform='CPU', design='partial', selection='included',
                selection_reason='fixture selector', selection_evidence=['CI'],
                tests=[dict(path='test_api.py', id='test_f', assertion='夹具断言', evidence=['T'])])],
            findings=[dict(id='F1', kind='coverage_gap', severity='P1', confidence='high', title='负数断言缺失',
                impact='无法识别符号错误', recommendation='补负数场景', behavior_ids=['B1'], evidence=['S','T'])],
            tasks=[dict(id='G1', feature_id='B1', route='write', priority='P1', reason='补缺口', evidence=['S'],
                prerequisites=['CPU'], acceptance=['负控必须失败'], cases=[dict(id='G1-negative', name='负数',
                    inputs='-1', expected='1', oracle='数学绝对值', negative_control='保留负号')])])

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.repo),*args], text=True, stderr=subprocess.PIPE)

    def commit(self):
        self.git('add','.')
        self.git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')

    def validate(self):
        return review.validate(self.repo,self.snap,self.data,self.root)

    def observation(self,outcome='passed'):
        (self.root/'result.json').write_text(json.dumps({'test_f':outcome}))
        self.data['evidence'].append(dict(id='R',kind='artifact',path='result.json',claim='夹具逐测例结果'))
        self.data['observations']=[dict(id='O1',run_id=1,attempt=2,job_id=3,tested_sha=self.head,
            identity='verified',identity_reason='夹具已绑定版本',lane='pr',platform='CPU',evidence=['R'],
            cases=[dict(path='test_api.py',id='test_f',outcome=outcome)])]
        self.data['behaviors'][0]['observations']=['O1']

    def test_job_success_is_not_case_proof(self):
        d,_=self.validate()
        self.assertEqual(d['behaviors'][0]['execution'],'not_verified')

    def test_handoff_preserves_pr_context(self):
        _,b=self.validate()
        p=handoff.check(self.repo,b,['G1'])
        self.assertEqual(p['pr_context']['head_sha'],self.head)
        self.assertEqual(p['tasks'][0]['lanes'],['pr'])
        self.assertIn('ci_execution',p['tasks'][0]['required_evidence'])
        self.assertEqual(p['planning'][0]['scenarios'][0]['scenario_id'],'G1-negative')
        b['pr_context']['head_sha']=self.base
        with self.assertRaises(ValueError): handoff.check(self.repo,b,['G1'])

    def test_stale_or_moving_head(self):
        self.data['head_sha']=self.base
        with self.assertRaises(ValueError): self.validate()
        self.data['head_sha']=self.head
        self.snap['capture_consistent']=False
        with self.assertRaises(ValueError): self.validate()

    def test_dirty_target(self):
        (self.repo/'dirty').write_text('x')
        with self.assertRaises(ValueError): self.validate()

    def test_omitted_diff_file(self):
        self.data['files']=[]
        with self.assertRaises(ValueError): self.validate()

    def test_api_diff_mismatch(self):
        self.snap['files'].append(dict(filename='not_in_diff'))
        with self.assertRaises(ValueError): self.validate()

    def test_unknown_is_not_gap(self):
        self.data['behaviors'][0]['design']='unknown'
        with self.assertRaises(ValueError): self.validate()

    def test_unknown_selection_is_not_proven_omission(self):
        self.data['behaviors'][0]['selection']='unknown'
        self.data['findings'][0]['kind']='selection_gap'
        with self.assertRaises(ValueError): self.validate()

    def test_task_arrays_cannot_be_strings(self):
        for field in ('acceptance','prerequisites','cases','lanes','required_evidence'):
            with self.subTest(field=field):
                saved=copy.deepcopy(self.data['tasks'][0])
                self.data['tasks'][0][field]='NOT_AN_ARRAY'
                with self.assertRaises(ValueError): self.validate()
                self.data['tasks'][0]=saved

    def test_relaxed_task_evidence_needs_reason(self):
        self.data['tasks'][0]['required_evidence']=['positive']
        with self.assertRaises(ValueError): self.validate()
        self.data['tasks'][0]['required_evidence_reason']='只验证局部CPU原型，不关闭CI缺口'
        self.assertEqual(self.validate()[1]['tasks'][0]['required_evidence'],['positive'])

    def test_fully_verified_and_visibility_limits(self):
        self.observation()
        self.data['behaviors'][0]['design']='supported'
        self.data['findings']=[]
        self.assertEqual(self.validate()[0]['verdict'],'no_material_gaps_found')
        self.snap['endpoints']['protection']=dict(status='unavailable')
        self.assertEqual(self.validate()[0]['verdict'],'needs_evidence')

    def test_no_metadata_only_pass(self):
        self.data['behaviors'][0]['execution']='passed'
        with self.assertRaises(ValueError): self.validate()

    def test_case_outcomes(self):
        self.observation()
        for outcome,want in [('passed','passed'),('failed','failed'),('error','failed'),('skipped','skipped'),('xfailed','skipped')]:
            with self.subTest(outcome=outcome):
                self.data['observations'][0]['cases'][0]['outcome']=outcome
                self.assertEqual(self.validate()[0]['behaviors'][0]['execution'],want)

    def test_missing_required_case(self):
        self.observation()
        self.data['behaviors'][0]['tests'].append(dict(path='test_api.py',id='test_boundary',assertion='边界',evidence=['T']))
        self.assertEqual(self.validate()[0]['behaviors'][0]['execution'],'not_verified')

    def test_failed_attempt_not_hidden_by_pass(self):
        self.observation()
        other=copy.deepcopy(self.data['observations'][0]); other['id']='O2'; other['cases'][0]['outcome']='failed'
        self.data['observations'].append(other); self.data['behaviors'][0]['observations'].append('O2')
        self.assertEqual(self.validate()[0]['behaviors'][0]['execution'],'failed')

    def test_wrong_identity_rejected(self):
        self.observation()
        original=copy.deepcopy(self.data['observations'][0])
        for key,value in [('tested_sha',self.base),('attempt',1),('job_id',4),('platform','HCU'),('lane','nightly'),('identity','unknown')]:
            with self.subTest(key=key):
                self.data['observations'][0]=dict(original,**{key:value})
                with self.assertRaises(ValueError): self.validate()

    def test_cannot_union_rerun_subsets(self):
        self.observation()
        self.snap['runs'].append(dict(id=1,run_attempt=1,jobs=[dict(id=4,status='completed')]))
        other=copy.deepcopy(self.data['observations'][0]);other.update(id='O2',attempt=1,job_id=4)
        self.data['observations'].append(other);self.data['behaviors'][0]['observations'].append('O2')
        with self.assertRaises(ValueError): self.validate()
        self.snap['runs'][-1].update(id=2,run_attempt=2)
        other.update(run_id=2,attempt=2)
        with self.assertRaises(ValueError): self.validate()

    def test_source_bounds_and_escape(self):
        self.data['evidence'][0]['end']=999
        with self.assertRaises(ValueError): self.validate()
        self.data['evidence'][0]['end']=1; self.data['evidence'][0]['path']='../outside'
        with self.assertRaises(ValueError): self.validate()

    def test_infra_needs_log_and_product_failure_needs_case(self):
        for kind in ['infrastructure_failure','test_failure']:
            self.data['findings'][0]['kind']=kind
            with self.assertRaises(ValueError): self.validate()

    def test_utf8_runner_environment(self):
        log=self.root/'运行.log'
        rc,timed=runner.run_process([sys.executable,'-c','import os; print(os.environ["PYTHONUTF8"]); print("海光")'],self.root,log,20)
        self.assertEqual((rc,timed),(0,False))
        self.assertEqual(log.read_text(encoding='utf-8').splitlines(),['1','海光'])


class SnapshotTests(unittest.TestCase):
    def fake(self,moving=False,unavailable=False):
        calls=[]
        pr=dict(html_url='https://github.com/f/r/pull/1',title='fixture',state='open',changed_files=1,
            base=dict(ref='main',sha='a'*40),head=dict(sha='b'*40,repo=dict(full_name='f/r')),merge_commit_sha='c'*40)
        def fetch(url):
            calls.append(url)
            if url.endswith('/pulls/1'):
                result=copy.deepcopy(pr)
                if moving and calls.count(url)>1:result['head']['sha']='d'*40
                return result,''
            if 'protection/' in url and unavailable:raise RuntimeError('HTTP 404')
            if '/files?' in url:return [dict(filename='api.py')],''
            if '/check-runs?' in url:return dict(check_runs=[]),''
            if '/actions/runs?' in url:return dict(workflow_runs=[dict(id=1,run_attempt=2,head_sha='b'*40)]),''
            if '/attempts/2/jobs' in url:return dict(jobs=[dict(id=3,status='completed')]),''
            return [],''
        return fetch,calls

    def test_pins_attempt_and_keeps_unknown(self):
        fetch,calls=self.fake(unavailable=True)
        s=snapshot.collect('f/r',1,fetch)
        self.assertTrue(s['capture_consistent']);self.assertTrue(s['files_complete'])
        self.assertTrue(any('/attempts/2/jobs' in x for x in calls))
        self.assertEqual(s['endpoints']['legacy_protection']['status'],'unavailable')

    def test_moving_head(self):
        self.assertFalse(snapshot.collect('f/r',1,self.fake(moving=True)[0])['capture_consistent'])

    def test_pagination_budget(self):
        fetch,_=self.fake()
        def pages(url):
            body,link=fetch(url)
            if '/files?' in url:link='<https://api.github.com/next>; rel="next"'
            return body,link
        s=snapshot.collect('f/r',1,pages,max_pages=1)
        self.assertFalse(s['files_complete'])
        self.assertTrue(s['endpoints']['files']['truncated'])


if __name__=='__main__':unittest.main()
