"""Behavior-depth contracts and immutable source navigation."""
import copy
import unittest
import test_branch_audit as branch
import test_functional_audit as legacy
from test_functional_audit import load, ROOT

source = load(ROOT / 'skills/hcu-coverage-analysis/scripts/source_index.py')


class DepthTests(unittest.TestCase):
    git = legacy.AuditTests.git
    validate = legacy.AuditTests.validate

    def setUp(self):
        branch.BranchAuditTests.setUp(self)
        self.data['scope']['analysis_depth'] = 'behavior'
        self.data['tasks'][0]['cases'][0]['id'] = 'G1:dedup'
        self.data['analysis'] = dict(schema_version=1, feature_inventory=[
            dict(id='I1', name='API', basis='documented', status='reviewed', reason='Read public contract',
                 feature_ids=['F1'], evidence=['R'], followups=[])],
            scenarios=[dict(id='G1:dedup', feature_id='F1', lanes=['pr', 'daily'], inputs='[2,1,2]',
                            expected='[1,2]', oracle='Explicit specification', failure_mode='Duplicates remain',
                            status='gap', tests=[], evidence=['R','T'], followups=['G1'])], pr_impacts=[])

    def test_valid_depth_records_and_stable_handoff(self):
        d = self.validate()
        self.assertEqual(d['analysis']['summary']['scenarios'], {'gap': 1})
        plan = legacy.handoff.check(self.repo, d, ['G1'])
        self.assertEqual(plan['planning'][0]['scenarios'][0]['scenario_id'], 'G1:dedup')
        self.assertEqual(plan['analysis'], d['analysis'])
        self.assertIn('G1:dedup', legacy.audit.markdown(d))

    def test_missing_depth_data_rejected(self):
        del self.data['analysis']
        with self.assertRaisesRegex(ValueError, 'analysis records'):
            self.validate()

    def test_unreviewed_function_cannot_be_hidden_as_whole_repo(self):
        self.data['scope']['extent'] = 'repository_reviewed'
        row = copy.deepcopy(self.data['analysis']['feature_inventory'][0])
        row.update(id='I2', status='deferred', feature_ids=[], followups=['G1'])
        self.data['analysis']['feature_inventory'].append(row)
        with self.assertRaisesRegex(ValueError, 'unreviewed'):
            self.validate()

    def test_supported_feature_cannot_hide_gap_scenario(self):
        self.data['features'][0]['lanes']['pr']['coverage'] = 'supported'
        with self.assertRaisesRegex(ValueError, 'uncovered scenarios'):
            self.validate()

    def test_gap_must_reach_generation_with_same_id(self):
        self.data['tasks'][0]['cases'][0]['id'] = 'renamed'
        with self.assertRaisesRegex(ValueError, 'unchanged'):
            self.validate()

    def test_pr_needs_behavior_impact_not_only_changed_file(self):
        branch.BranchAuditTests.pr(self)
        with self.assertRaisesRegex(ValueError, 'missing impact'):
            self.validate()
        self.data['analysis']['pr_impacts'] = [
            dict(change_id='C7', before='Sort only', after='Dedup and sort', trigger='Repeated items',
                 risk='Unexpected duplicate outputs', exclusions='GPU path not applicable to CPU API',
                 entrypoints=['sort_items'], callers=['public API users'], backend_paths=['CPU'],
                 scenario_ids=['G1:dedup'], evidence=['R','T'])]
        self.assertEqual(self.validate()['analysis']['summary']['pr_impacts'], 1)

    def test_source_index_no_import_and_ignores_dirty_tree(self):
        first = source.build(self.repo)
        (self.repo / 'api.py').write_text('raise RuntimeError("not the committed source")')
        second = source.build(self.repo)
        self.assertTrue(second['working_tree_ignored'])
        self.assertEqual(first['files'], second['files'])
        api = next(r for r in first['files'] if r['path'] == 'api.py')
        self.assertEqual(api['symbols'][0]['name'], 'sort_items')
        self.assertEqual({c['callee'] for c in api['calls']}, {'sorted','set'})

    def test_source_budget_and_scope_do_not_silently_hide_files(self):
        result = source.build(self.repo, max_files=1)
        self.assertEqual(result['candidate_count'], 2)
        self.assertEqual(len(result['deferred_paths']), 1)
        self.assertEqual(len(source.build(self.repo, ['api.py'])['files']), 1)
        with self.assertRaises(ValueError):
            source.build(self.repo, ['../outside'])

    def test_source_aliases_and_inheritance_are_navigation_only(self):
        (self.repo / 'api.py').write_text('from backend import run as kernel\nclass TestBase:\n    def test_call(self):\n        kernel()\nclass TestHCU(TestBase):\n    pass\n')
        self.git('add', '.')
        self.git('-c','user.name=fixture','-c','user.email=f@example.invalid','commit','-qm','index')
        r = next(r for r in source.build(self.repo)['files'] if r['path'] == 'api.py')
        self.assertEqual(r['imports'][0]['alias'], 'kernel')
        self.assertEqual(r['symbols'][-1]['bases'], ['TestBase'])
        self.assertEqual(r['calls'][0]['caller'], 'TestBase.test_call')


if __name__ == '__main__':
    unittest.main()
