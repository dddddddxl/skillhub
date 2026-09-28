"""Audit-to-authoring handoff invariants; no project tests are executed."""
import copy,json,unittest
import test_functional_audit as legacy


class GenerationTests(unittest.TestCase):
    git=legacy.AuditTests.git
    def setUp(self):
        legacy.AuditTests.setUp(self)
        self.backlog=legacy.audit.validate(self.data,self.repo,self.root)

    def check(self,selected=None):return legacy.handoff.check(self.repo,self.backlog,selected or ['G1'])

    def test_only_selected_tasks_receive_scenarios(self):
        other=copy.deepcopy(self.backlog['tasks'][0]);other['id']='G2';self.backlog['tasks'].append(other)
        d=self.check()
        self.assertEqual([p['task_id'] for p in d['planning']],['G1'])
        self.assertEqual(d['planning'][0]['scenarios'][0]['scenario_id'],'G1:1')
        self.assertEqual(d['planning'][0]['scenarios'][0]['oracle'],self.backlog['tasks'][0]['cases'][0]['oracle'])
        self.assertNotIn('scenario_id',self.backlog['tasks'][0]['cases'][0])

    def test_repair_and_validation_do_not_route_to_authoring(self):
        for route,action in [('repair_selection','propose_ci_repair'),('validate_existing','verify_existing'),('clarify_requirement','investigate_contract')]:
            with self.subTest(route=route):
                self.backlog['tasks'][0]['route']=route
                self.assertEqual(self.check()['planning'][0]['next_action'],action)

    def test_framework_not_forced_to_pytest(self):
        self.assertEqual(self.check()['planning'][0]['framework'],'inspect_repository')
        self.assertEqual(self.check()['planning'][0]['test_location'],'prefer_existing_test')

    def test_explicit_scenario_ids_survive_reordering(self):
        first = self.backlog['tasks'][0]['cases'][0]
        first['id'] = 'G1:boundary'
        second = dict(first, id='G1:fallback', name='fallback')
        self.backlog['tasks'][0]['cases'].append(second)
        before = {s['name']: s['scenario_id'] for s in self.check()['planning'][0]['scenarios']}
        self.backlog['tasks'][0]['cases'].reverse()
        after = {s['name']: s['scenario_id'] for s in self.check()['planning'][0]['scenarios']}
        self.assertEqual(before, after)
        self.assertEqual(self.check()['planning'][0]['scenarios'][0]['identity_mode'], 'explicit')

    def test_duplicate_explicit_scenario_ids_rejected(self):
        case = self.backlog['tasks'][0]['cases'][0]
        case['id'] = 'G1:boundary'
        self.backlog['tasks'][0]['cases'].append(dict(case))
        with self.assertRaises(ValueError):
            self.check()

    def test_transitive_unselected_dependencies_reported(self):
        t=self.backlog['tasks'][0];t['depends_on']=['G2']
        t2=copy.deepcopy(t);t2.update(id='G2',depends_on=['G3'])
        t3=copy.deepcopy(t);t3.update(id='G3',depends_on=[])
        self.backlog['tasks'] += [t2,t3]
        self.assertEqual(self.check()['unselected_dependencies'],['G2','G3'])
        self.assertEqual(self.check(['G1','G2'])['unselected_dependencies'],['G3'])

    def test_v1_dependency_cycle_cannot_recurse_forever(self):
        self.backlog['tasks'][0]['depends_on']=['G1']
        with self.assertRaises(ValueError):self.check()

    def test_v2_context_preserved(self):
        branch=self.git('symbolic-ref','--short','HEAD').strip()
        self.backlog.update(schema_version=2,target=dict(branch=branch,ref='refs/heads/'+branch),runtime={'status':'partial'},recent_prs={'items':[]})
        d=self.check()
        for k in ('target','runtime','recent_prs','source_fingerprints','evidence'):
            self.assertEqual(d[k],self.backlog[k])

    def test_new_plan_roundtrip_does_not_touch_checkout(self):
        path=self.root/'plan.json';d=self.check();legacy.handoff.save_plan(path,self.repo,d)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['planning'],d['planning'])
        self.assertEqual(self.git('status','--porcelain').strip(),'')
        with self.assertRaises(FileExistsError):legacy.handoff.save_plan(path,self.repo,d)

    def test_output_inside_target_is_rejected(self):
        with self.assertRaises(ValueError):legacy.handoff.save_plan(self.repo/'plan.json',self.repo,self.check())
        self.assertFalse((self.repo/'plan.json').exists())


if __name__=='__main__':unittest.main()
