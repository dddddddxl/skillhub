"""Completion must agree with actual per-case evidence and the selected plan."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from test_functional_audit import load, ROOT

completion = load(ROOT / 'skills/hcu-test-generation/scripts/check_completion.py')


class CompletionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.revision = dict(source_commit='a'*40, patch_sha256=None)
        self.plan = dict(plan_schema_version=1, repository='fixture', source_commit='a'*40,
                         unselected_dependencies=[], tasks=[
                             dict(id='G1', lanes=['pr'], acceptance=['reject duplicates'])],
                         planning=[dict(task_id='G1', scenarios=[dict(scenario_id='G1:dedup')])])
        self.data = dict(schema_version=1, repository='fixture', audit_source_commit='a'*40, evidence=[], tasks=[
            dict(task_id='G1', status='validated', validated_scope='CPU duplicate behavior',
                 tested_revision=self.revision, unresolved_prerequisites=[],
                 scenario_results=[dict(scenario_id='G1:dedup', test_id='test::dedup', outcome='passed', evidence='POS')],
                 acceptance_results=[dict(condition='reject duplicates', status='met', evidence=['POS','NEG'])],
                 negative_controls=[dict(scenario_id='G1:dedup', test_id='test::dedup', baseline_evidence='POS',
                                         tested_revision=dict(source_commit='a'*40, patch_sha256='b'*64), evidence='NEG',
                                         mutation='remove dedup', target_assertion='unique output', failure_kind='target_assertion')],
                 ci_selection='SEL', ci_execution=None)])
        self.positive = dict(**self.revision, command=['python','-m','pytest'], exit_code=0, status='pass',
                             counts=dict(tests=1, failed=0, errors=0, skipped=0),
                             cases=[dict(id='test::dedup', outcome='passed')])
        self.negative = dict(self.positive, patch_sha256='b'*64, exit_code=1, status='test_failure',
                             counts=dict(tests=1, failed=1, errors=0, skipped=0),
                             cases=[dict(id='test::dedup', outcome='failed')])
        self.put('POS', self.positive)
        self.put('NEG', self.negative)
        self.put('SEL', dict(**self.revision, lane='pr', command=['collect-only'],
                            selected_ids=['test::dedup'], unresolved_gates=[]))

    def put(self, id, payload):
        path = self.root / (id + '.json')
        path.write_text(json.dumps(payload), encoding='utf-8')
        self.data['evidence'] = [r for r in self.data['evidence'] if r['id'] != id]
        self.data['evidence'].append(dict(id=id, path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

    def check(self):
        return completion.check(self.plan, self.data, self.root)

    def test_consistent_local_evidence_does_not_claim_ci_execution(self):
        self.assertEqual(self.check()['validated_tasks'], ['G1'])
        self.assertIsNone(self.data['tasks'][0]['ci_execution'])

    def test_missing_or_duplicate_scenario_rejected(self):
        for scenarios in ([], self.data['tasks'][0]['scenario_results'] * 2):
            with self.subTest(scenarios=scenarios):
                self.data['tasks'][0]['scenario_results'] = scenarios
                with self.assertRaises(ValueError):
                    self.check()

    def test_skip_cannot_be_passed(self):
        self.positive.update(cases=[dict(id='test::dedup', outcome='skipped')],
                             counts=dict(tests=1, failed=0, errors=0, skipped=1))
        self.put('POS', self.positive)
        with self.assertRaises(ValueError):
            self.check()

    def test_negative_import_error_not_target_failure(self):
        self.negative.update(cases=[dict(id='test::dedup', outcome='error')],
                             counts=dict(tests=1, failed=0, errors=1, skipped=0))
        self.put('NEG', self.negative)
        with self.assertRaisesRegex(ValueError, 'Import/setup'):
            self.check()

    def test_changed_evidence_hash_rejected(self):
        (self.root / 'POS.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            self.check()

    def test_wrong_tested_patch_rejected(self):
        self.data['tasks'][0]['tested_revision'] = dict(self.revision, patch_sha256='c'*64)
        with self.assertRaisesRegex(ValueError, 'revision/patch'):
            self.check()

    def test_wrong_counts_rejected(self):
        self.positive['counts']['tests'] = 2
        self.put('POS', self.positive)
        with self.assertRaisesRegex(ValueError, 'counts'):
            self.check()

    def test_dirty_run_without_patch_identity_rejected(self):
        self.positive['dirty'] = True
        self.put('POS', self.positive)
        with self.assertRaisesRegex(ValueError, 'Dirty run'):
            self.check()

    def test_negative_control_cannot_use_unrelated_failed_test(self):
        self.data['tasks'][0]['negative_controls'][0]['test_id'] = 'unrelated'
        with self.assertRaisesRegex(ValueError, 'different test'):
            self.check()

    def test_required_real_ci_cannot_use_local_result(self):
        self.plan['tasks'][0]['required_evidence'] = ['positive','negative_control','ci_execution']
        self.data['tasks'][0]['ci_execution'] = 'POS'
        self.positive['lane'] = 'pr'
        self.put('POS', self.positive)
        with self.assertRaisesRegex(ValueError, 'Actual CI'):
            self.check()

    def test_unselected_dependency_prevents_validated(self):
        self.plan['unselected_dependencies'] = ['G2']
        with self.assertRaisesRegex(ValueError, 'dependencies'):
            self.check()

    def test_unexecuted_needs_review_preserved(self):
        record = self.data['tasks'][0]
        record['status'] = 'needs_review'
        record['scenario_results'][0]['outcome'] = 'not_run'
        record['acceptance_results'][0]['status'] = 'unknown'
        self.assertEqual(self.check()['validated_tasks'], [])

    def test_missing_ci_selection_cannot_validate(self):
        self.data['tasks'][0]['ci_selection'] = None
        with self.assertRaises(ValueError):
            self.check()


if __name__ == '__main__':
    unittest.main()
