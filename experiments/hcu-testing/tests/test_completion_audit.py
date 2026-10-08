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


class CompletionV2Tests(unittest.TestCase):
    put = CompletionTests.put
    check = CompletionTests.check

    def put_raw(self, id, payload):
        raw = self.root / (id + '.log')
        raw.write_text('synthetic raw evidence: ' + id, encoding='utf-8')
        payload['raw_artifacts'] = [dict(path=raw.name, sha256=hashlib.sha256(raw.read_bytes()).hexdigest())]
        self.put(id, payload)

    def setUp(self):
        CompletionTests.setUp(self)
        self.data['schema_version'] = 2
        self.record = self.data['tasks'][0]
        self.ids = ['test::dedup', 'test::bounds', 'test::arguments', 'test::additional']
        self.scenario = dict(scenario_id='G1:dedup', tests=[
            dict(test_id=id, outcome='passed', evidence='POS') for id in self.ids])
        self.record['scenario_results'] = [self.scenario]
        self.positive.update(counts=dict(tests=4, failed=0, errors=0, skipped=0),
                             cases=[dict(id=id, outcome='passed') for id in self.ids])
        self.negative.update(counts=dict(tests=4, failed=1, errors=0, skipped=0),
                             cases=[dict(id=id, outcome='failed' if id == self.ids[0] else 'passed') for id in self.ids])
        self.selection = dict(**self.revision, lane='pr', command=['collect-only'], status='pass', exit_code=0,
                              selected_ids=list(self.ids), unresolved_gates=[])
        self.put_raw('POS', self.positive)
        self.put_raw('NEG', self.negative)
        self.put_raw('SEL', self.selection)

    def test_multi_method_scenario_validates_without_requiring_mutation_for_each_extra_method(self):
        self.assertEqual(self.check()['validated_tasks'], ['G1'])

    def test_multiple_mutations_and_multiple_targets_may_share_a_scenario(self):
        for suffix, target in [('C', self.ids[0]), ('D', self.ids[1])]:
            control = dict(self.record['negative_controls'][0], test_id=target, evidence=suffix,
                           tested_revision=dict(self.revision, patch_sha256=suffix.lower()*64), mutation='fault ' + suffix)
            negative = dict(self.negative, patch_sha256=suffix.lower()*64,
                            cases=[dict(id=id, outcome='failed' if id == target else 'passed') for id in self.ids])
            self.put_raw(suffix, negative)
            self.record['negative_controls'].append(control)
        self.assertEqual(self.check()['validated_tasks'], ['G1'])

    def test_methods_can_reference_distinct_positive_runs(self):
        self.put_raw('POS2', copy.deepcopy(self.positive))
        self.scenario['tests'][1]['evidence'] = 'POS2'
        self.assertEqual(self.check()['validated_tasks'], ['G1'])

    def test_representative_fields_cannot_be_mixed_into_v2(self):
        for field in ('test_id', 'covered_test_ids', 'outcome', 'evidence'):
            with self.subTest(field=field):
                self.scenario[field] = 'legacy'
                with self.assertRaisesRegex(ValueError, 'representative'):
                    self.check()
                del self.scenario[field]

    def test_missing_duplicate_or_unknown_method_rejected(self):
        original = copy.deepcopy(self.scenario['tests'])
        for tests in ([], original * 2, [dict(original[0], test_id='not-in-run')]):
            with self.subTest(tests=tests):
                self.scenario['tests'] = tests
                with self.assertRaises(ValueError):
                    self.check()

    def test_each_claimed_method_is_checked_in_unverified_records(self):
        self.record['status'] = 'implemented_unverified'
        self.positive['cases'][-1]['outcome'] = 'skipped'
        self.positive['counts']['skipped'] = 1
        self.put('POS', self.positive)
        with self.assertRaisesRegex(ValueError, 'differs from run'):
            self.check()

    def test_error_xfailed_and_skipped_are_recordable_but_cannot_validate(self):
        self.record['negative_controls'] = []
        for outcome in ('error', 'xfailed', 'skipped', 'failed'):
            with self.subTest(outcome=outcome):
                self.record['status'] = 'implemented_unverified'
                self.scenario['tests'] = [dict(test_id=self.ids[0], outcome=outcome, evidence='RESULT')]
                result = dict(self.positive, status='test_failure' if outcome in {'error', 'failed'} else 'pass',
                              exit_code=1 if outcome in {'error', 'failed'} else 0,
                              cases=[dict(id=self.ids[0], outcome=outcome)],
                              counts=dict(tests=1, failed=int(outcome == 'failed'), errors=int(outcome == 'error'),
                                          skipped=int(outcome in {'xfailed', 'skipped'})))
                self.put_raw('RESULT', result)
                self.assertEqual(self.check()['validated_tasks'], [])
                self.record['status'] = 'validated'
                with self.assertRaisesRegex(ValueError, 'unexecuted/failed'):
                    self.check()

    def test_unknown_not_run_placeholder_is_preserved(self):
        self.record.update(status='needs_review', negative_controls=[], ci_selection=None)
        self.scenario['tests'] = [dict(test_id=None, outcome='not_run', evidence=None, reason='No environment')]
        self.assertEqual(self.check()['validated_tasks'], [])
        self.scenario['tests'].append(dict(test_id=self.ids[0], outcome='passed', evidence='POS'))
        with self.assertRaisesRegex(ValueError, 'sole not_run'):
            self.check()

    def test_not_run_cannot_claim_evidence_or_omit_reason(self):
        self.record.update(status='blocked', negative_controls=[], ci_selection=None)
        for test in (dict(test_id=self.ids[0], outcome='not_run', evidence='POS', reason='blocked'),
                     dict(test_id=self.ids[0], outcome='not_run', evidence=None)):
            with self.subTest(test=test):
                self.scenario['tests'] = [test]
                with self.assertRaisesRegex(ValueError, 'Not-run'):
                    self.check()

    def test_each_status_checks_filled_negative_controls(self):
        self.record['negative_controls'][0]['test_id'] = 'unrelated'
        for status in ('implemented_unverified', 'blocked', 'needs_review', 'validated'):
            with self.subTest(status=status):
                self.record['status'] = status
                with self.assertRaisesRegex(ValueError, 'different scenario/test'):
                    self.check()

    def test_negative_baseline_must_match_the_target_method(self):
        self.record['status'] = 'implemented_unverified'
        self.put_raw('POS2', copy.deepcopy(self.positive))
        self.record['negative_controls'][0]['baseline_evidence'] = 'POS2'
        with self.assertRaisesRegex(ValueError, 'baseline differs'):
            self.check()

    def test_negative_baseline_must_be_declared_passed(self):
        self.record['status'] = 'implemented_unverified'
        self.scenario['tests'][0] = dict(test_id=self.ids[0], outcome='not_run', evidence=None, reason='unknown')
        with self.assertRaisesRegex(ValueError, 'baseline differs'):
            self.check()

    def test_negative_error_and_wrong_mutation_revision_rejected_when_unverified(self):
        self.record['status'] = 'implemented_unverified'
        self.negative['cases'][0]['outcome'] = 'error'
        self.negative['counts'].update(failed=0, errors=1)
        self.put('NEG', self.negative)
        with self.assertRaisesRegex(ValueError, 'Import/setup'):
            self.check()
        self.record['negative_controls'][0]['tested_revision'] = self.revision
        with self.assertRaisesRegex(ValueError, 'isolated mutation'):
            self.check()

    def test_duplicate_negative_control_rejected(self):
        self.record['negative_controls'] *= 2
        with self.assertRaisesRegex(ValueError, 'Duplicate negative'):
            self.check()

    def test_negative_controls_cover_each_planned_scenario(self):
        self.plan['planning'][0]['scenarios'].append(dict(scenario_id='G1:other'))
        self.record['scenario_results'].append(dict(self.scenario, scenario_id='G1:other'))
        with self.assertRaisesRegex(ValueError, 'cover planned scenarios'):
            self.check()

    def test_blocked_selection_preserved_but_cannot_validate(self):
        self.selection.update(status='selection_blocked', exit_code=1, selected_ids=[], unresolved_gates=['existing registration'])
        self.put('SEL', self.selection)
        self.record['status'] = 'implemented_unverified'
        self.assertEqual(self.check()['validated_tasks'], [])
        self.record['status'] = 'validated'
        with self.assertRaisesRegex(ValueError, 'select all required'):
            self.check()

    def test_selection_checks_all_methods_not_only_first(self):
        self.selection['selected_ids'] = self.ids[:-1]
        self.put('SEL', self.selection)
        with self.assertRaisesRegex(ValueError, 'select all required'):
            self.check()

    def test_filled_selection_checks_identity_even_when_not_required(self):
        self.record['status'] = 'needs_review'
        self.plan['tasks'][0]['required_evidence'] = ['positive']
        self.selection['source_commit'] = 'c'*40
        self.put('SEL', self.selection)
        with self.assertRaisesRegex(ValueError, 'revision/patch'):
            self.check()

    def test_selection_cannot_claim_pass_with_failing_exit_code(self):
        self.record['status'] = 'implemented_unverified'
        self.selection['exit_code'] = 1
        self.put('SEL', self.selection)
        with self.assertRaisesRegex(ValueError, 'Passing selection'):
            self.check()

    def test_unverified_ci_execution_still_requires_actual_identity(self):
        self.record.update(status='implemented_unverified', ci_execution='CI')
        ci = dict(self.positive, lane='pr')
        self.put_raw('CI', ci)
        with self.assertRaisesRegex(ValueError, 'Actual CI'):
            self.check()
        ci.update(run_id='run-1', job_id='job-1', attempt=1, source_identity='verified')
        self.put('CI', ci)
        self.assertEqual(self.check()['validated_tasks'], [])

    def test_required_ci_execution_checks_all_methods(self):
        self.plan['tasks'][0]['required_evidence'] = ['positive', 'negative_control', 'ci_selection', 'ci_execution']
        self.record['ci_execution'] = 'CI'
        ci = dict(self.positive, lane='pr', run_id='run-1', job_id='job-1', attempt=1, source_identity='verified')
        self.put_raw('CI', ci)
        self.assertEqual(self.check()['validated_tasks'], ['G1'])
        ci.update(cases=self.positive['cases'][:-1], counts=dict(tests=3, failed=0, errors=0, skipped=0))
        self.put('CI', ci)
        with self.assertRaisesRegex(ValueError, 'Required CI cases'):
            self.check()

    def test_missing_ci_is_allowed_only_before_validation(self):
        self.record.update(status='implemented_unverified', ci_selection=None)
        self.assertEqual(self.check()['validated_tasks'], [])
        self.record['status'] = 'validated'
        with self.assertRaisesRegex(ValueError, 'Required CI evidence'):
            self.check()

    def test_required_ci_cannot_validate_a_failed_run_with_passing_required_cases(self):
        self.plan['tasks'][0]['required_evidence'] = ['ci_execution']
        self.record['ci_execution'] = 'CI'
        for status, exit_code in [('error', 2), ('test_failure', 1)]:
            with self.subTest(status=status):
                ci = dict(self.positive, lane='pr', run_id='run-1', job_id='job-1', attempt=1,
                          source_identity='verified', status=status, exit_code=exit_code)
                self.put_raw('CI', ci)
                self.record['status'] = 'implemented_unverified'
                self.assertEqual(self.check()['validated_tasks'], [])
                self.record['status'] = 'validated'
                with self.assertRaisesRegex(ValueError, 'CI execution is not a passing run'):
                    self.check()

    def test_explicit_case_identity_must_match_parent_ci_in_every_status(self):
        self.record['ci_execution'] = 'CI'
        ci = dict(copy.deepcopy(self.positive), lane='pr', run_id='run-1', job_id='job-1', attempt=2,
                  source_identity='verified')
        mismatches = dict(run_id='run-2', job_id='job-2', attempt=1, tested_sha='c'*40,
                          source_identity='unknown', source_commit='c'*40, patch_sha256='c'*64)
        for field, value in mismatches.items():
            for status in ('implemented_unverified', 'blocked', 'needs_review', 'validated'):
                with self.subTest(field=field, status=status):
                    self.record['status'] = status
                    ci['cases'] = copy.deepcopy(self.positive['cases'])
                    ci['cases'][0][field] = value
                    self.put_raw('CI', ci)
                    with self.assertRaisesRegex(ValueError, 'Case identity differs'):
                        self.check()

    def test_matching_optional_case_identity_is_accepted_without_inventing_missing_fields(self):
        self.plan['tasks'][0]['required_evidence'] = ['ci_execution']
        self.record['ci_execution'] = 'CI'
        ci = dict(copy.deepcopy(self.positive), lane='pr', run_id='run-1', job_id='job-1', attempt=2,
                  source_identity='verified')
        ci['cases'][0].update(run_id='run-1', job_id='job-1', attempt=2, tested_sha=self.revision['source_commit'],
                              source_identity='verified', **self.revision)
        self.put_raw('CI', ci)
        self.assertEqual(self.check()['validated_tasks'], ['G1'])
        self.assertNotIn('attempt', ci['cases'][1])

    def test_case_identity_without_a_parent_identity_is_not_verifiable(self):
        self.positive['cases'][0]['attempt'] = 1
        self.put('POS', self.positive)
        with self.assertRaisesRegex(ValueError, 'Case identity differs'):
            self.check()

    def test_raw_hash_checked_for_all_statuses_and_even_unused_evidence(self):
        self.put_raw('UNUSED', {})
        (self.root / 'UNUSED.log').write_text('changed')
        for status in ('implemented_unverified', 'blocked', 'needs_review', 'validated'):
            with self.subTest(status=status):
                self.record['status'] = status
                with self.assertRaisesRegex(ValueError, 'hash changed'):
                    self.check()

    def test_missing_or_omitted_raw_artifact_rejected(self):
        (self.root / 'POS.log').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.check()
        self.positive.pop('raw_artifacts')
        self.put('POS', self.positive)
        with self.assertRaisesRegex(ValueError, 'Raw run/selection'):
            self.check()

    def test_raw_relative_path_is_resolved_from_its_json_directory(self):
        nested = self.root / 'artifacts'
        nested.mkdir()
        (self.root / 'POS.log').rename(nested / 'POS.log')
        (self.root / 'POS.json').rename(nested / 'POS.json')
        next(ref for ref in self.data['evidence'] if ref['id'] == 'POS')['path'] = 'artifacts/POS.json'
        self.assertEqual(self.check()['validated_tasks'], ['G1'])

    def test_raw_paths_cannot_escape_or_use_absolute_paths(self):
        for path in ('../outside.log', str(self.root / 'POS.log'), 'C:\\outside.log', '\\outside.log'):
            with self.subTest(path=path):
                self.positive['raw_artifacts'][0]['path'] = path
                self.put('POS', self.positive)
                with self.assertRaisesRegex(ValueError, 'relative|escapes'):
                    self.check()

    def test_supplemental_acceptance_references_checked_when_unmet(self):
        self.record['status'] = 'implemented_unverified'
        self.record['acceptance_results'][0].update(status='unmet', evidence=['MISSING'])
        with self.assertRaisesRegex(ValueError, 'Missing completion'):
            self.check()


if __name__ == '__main__':
    unittest.main()
