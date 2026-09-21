"""Contract and CLI checks; fixtures do not prove semantic completeness."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'skills/hcu-coverage-analysis/scripts/audit.py'
HANDOFF = ROOT / 'skills/hcu-test-generation/scripts/check_handoff.py'


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit, handoff = load(AUDIT), load(HANDOFF)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'api.py').write_text('def sort_items(x):\n    return sorted(set(x))\n')
        (self.repo / 'test_api.py').write_text('raise RuntimeError("Inventory must not import me")\n')
        (self.repo / 'README.md').write_text('Public contract: sort and deduplicate.\n')
        (self.repo / '.github/workflows').mkdir(parents=True)
        (self.repo / '.github/workflows/pr.yml').write_text('name: fixture\n')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        sha = self.git('rev-parse', 'HEAD').strip()
        cell = dict(selection='included', coverage='partial', execution='not_verified', reason='Assertions insufficient', evidence=['T', 'CI'])
        self.data = dict(schema_version=1, repository='https://example.invalid/fixture', source_commit=sha,
                         scope=dict(platform='CPU', lanes=['pr', 'daily'], extent='bounded', feature_basis='One documented API', limitations=['Fixture only']),
                         evidence=[dict(id='R', kind='source', path='README.md', start=1, end=1, claim='Contract'),
                                   dict(id='T', kind='source', path='test_api.py', start=1, end=1, claim='Test candidate'),
                                   dict(id='CI', kind='source', path='.github/workflows/pr.yml', start=1, end=1, claim='CI candidate')],
                         features=[dict(id='F1', name='Sort', requirement='Sort and deduplicate', evidence=['R'],
                                        tests=[dict(path='test_api.py', assertion_kind='smoke', assertion='Fixture description, not executed', evidence=['T'])],
                                        lanes={'pr': copy.deepcopy(cell), 'daily': dict(cell, selection='unknown', coverage='unknown')})],
                         tasks=[dict(id='G1', feature_id='F1', priority='P1', lanes=['pr', 'daily'], route='upstream_first', reason='Missing behavior check', evidence=['R', 'T'],
                                     cases=[dict(name='Duplicate input', inputs='[2,1,2]', expected='[1,2]', oracle='Explicit documented result', negative_control='Remove deduplication')],
                                     prerequisites=['CPU'], acceptance=['Assertion rejects duplicate result'], search=['sort_items'])])

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True, stderr=subprocess.STDOUT)

    def validate(self):
        return audit.validate(self.data, self.repo, self.root)

    def test_static_unknown_is_preserved(self):
        data = self.validate()
        report = audit.markdown(data)
        self.assertIn('not_verified', report)
        self.assertEqual(data['features'][0]['lanes']['daily']['coverage'], 'unknown')
        self.assertEqual(len(data['source_fingerprints']), 3)

    def test_inventory_is_nonexecuting_navigation(self):
        result = audit.inventory(self.repo)
        self.assertEqual([x['path'] for x in result['tests']], ['test_api.py'])
        self.assertEqual(len(result['workflows']), 1)
        self.assertEqual(len(result['documents']), 1)

    def test_dangling_reference(self):
        self.data['features'][0]['evidence'] = ['missing']
        with self.assertRaises(ValueError): self.validate()

    def test_escape_reference(self):
        (self.root / 'outside').write_text('data')
        self.data['evidence'][0]['path'] = '../outside'
        with self.assertRaises(ValueError): self.validate()

    def test_line_range(self):
        self.data['evidence'][0]['end'] = 999
        with self.assertRaises(ValueError): self.validate()

    def test_disabled_not_supported(self):
        self.data['features'][0]['lanes']['pr'].update(selection='disabled', coverage='supported')
        with self.assertRaises(ValueError): self.validate()

    def test_pass_needs_run_evidence(self):
        self.data['features'][0]['lanes']['pr']['execution'] = 'passed'
        with self.assertRaises(ValueError): self.validate()

    def test_stale_run_rejected(self):
        (self.root / 'run.json').write_text('{"status":"pass"}')
        self.data['evidence'].append(dict(id='RUN', kind='run', path='run.json', claim='Old result', source_commit='0'*40, platform='CPU'))
        cell = self.data['features'][0]['lanes']['pr']
        cell.update(execution='passed', evidence=['CI', 'RUN'])
        with self.assertRaises(ValueError): self.validate()

    def run_evidence(self, payload):
        (self.root / 'run.json').write_text(json.dumps(payload))
        self.data['evidence'].append(dict(id='RUN', kind='run', path='run.json', claim='Structured result', source_commit=self.data['source_commit'], platform='CPU'))
        self.data['features'][0]['lanes']['pr'].update(execution='passed', evidence=['CI', 'RUN'])

    def test_pass_requires_non_skipped_counts(self):
        self.run_evidence(dict(source_commit=self.data['source_commit'], status='pass', counts=dict(tests=2, skipped=2)))
        with self.assertRaises(ValueError): self.validate()

    def test_verified_run_matches_artifact(self):
        self.run_evidence(dict(source_commit=self.data['source_commit'], status='pass', counts=dict(tests=2, skipped=0)))
        self.assertEqual(self.validate()['features'][0]['lanes']['pr']['execution'], 'passed')

    def test_failed_artifact_cannot_be_called_pass(self):
        self.run_evidence(dict(source_commit=self.data['source_commit'], status='test_failure', counts=dict(tests=2, failed=1)))
        with self.assertRaises(ValueError): self.validate()

    def test_missing_task_for_unknown(self):
        self.data['tasks'][0]['lanes'] = ['pr']
        with self.assertRaises(ValueError): self.validate()

    def test_case_requires_oracle(self):
        self.data['tasks'][0]['cases'][0]['oracle'] = ''
        with self.assertRaises(ValueError): self.validate()

    def test_wrong_commit(self):
        self.data['source_commit'] = '0'*40
        with self.assertRaises(ValueError): self.validate()

    def test_dirty_checkout(self):
        (self.repo / 'api.py').write_text('changed\n')
        with self.assertRaises(ValueError): self.validate()

    def test_handoff_selects_only_requested_tasks(self):
        data = self.validate()
        result = handoff.check(self.repo, data, ['G1'])
        self.assertEqual(result['status'], 'ready_for_review')
        self.assertEqual([x['id'] for x in result['tasks']], ['G1'])
        with self.assertRaises(ValueError): handoff.check(self.repo, data, ['missing'])
        with self.assertRaises(ValueError): handoff.check(self.repo, data, [])

    def test_handoff_rejects_fingerprint_change(self):
        data = self.validate()
        data['source_fingerprints']['README.md'] = '0'*64
        with self.assertRaises(ValueError): handoff.check(self.repo, data, ['G1'])

    def test_cli_report_to_handoff(self):
        input_path = self.root / 'input.json'
        input_path.write_text(json.dumps(self.data))
        output = self.root / 'output'
        command = [sys.executable, str(AUDIT), 'render', '--repo', str(self.repo), '--input', str(input_path), '--output', str(output)]
        p = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for name in ['report.md', 'audit.json', 'test-backlog.json']:
            self.assertTrue((output / name).is_file())
        p = subprocess.run([sys.executable, str(HANDOFF), '--repo', str(self.repo), '--backlog', str(output / 'test-backlog.json'), '--task', 'G1'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)['tasks'][0]['route'], 'upstream_first')
        p = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2, 'Existing outputs must not be overwritten')


if __name__ == '__main__':
    unittest.main()
