import importlib.util
import json
from pathlib import Path
import sys
import os
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/hcu-test-runner/scripts'
sys.path.insert(0, str(SCRIPTS))
import run_sglang as adapter


class NativeEvidenceTests(unittest.TestCase):
    def log(self, summary='Ran 9 tests in 0.1s\n\nOK', passed=True, filename='/tmp/test.py'):
        return summary + '\n========== TIMINGS BEGIN ==========\n' + json.dumps(dict(file=filename, passed=passed)) + '\n========== TIMINGS END ==========\n'

    def status(self, log, rc=0, timeout=False):
        return adapter.classify_native(rc, log, Path('/tmp/test.py'), timeout)[0]

    def test_pass(self):
        self.assertEqual(self.status(self.log()), 'pass')

    def test_all_skipped(self):
        self.assertEqual(self.status(self.log('Ran 9 tests in 0.1s\n\nOK (skipped=9)')), 'no_tests_executed')

    def test_empty(self):
        self.assertEqual(self.status(self.log('Ran 0 tests in 0.1s\n\nOK')), 'no_tests_executed')

    def test_partial_skip(self):
        self.assertEqual(self.status(self.log('Ran 9 tests in 0.1s\n\nOK (skipped=2)')), 'pass')

    def test_failure(self):
        self.assertEqual(self.status(self.log(), 1), 'execution_failure')

    def test_timeout(self):
        self.assertEqual(self.status(self.log(), -9, True), 'timeout')

    def test_unknown_summary(self):
        self.assertEqual(self.status(self.log('all good')), 'native_success_unverified')

    def test_wrong_file(self):
        self.assertEqual(self.status(self.log(filename='/tmp/other.py')), 'invalid_report')

    def test_missing_report(self):
        self.assertEqual(self.status('Ran 9 tests in 1s\nOK'), 'invalid_report')

    def test_false_timing(self):
        self.assertEqual(self.status(self.log(passed=False)), 'invalid_report')

    def test_whitelist_from_workflow(self):
        import yaml
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'workflow.yml'
            command = 'python3 run_suite.py --hw hcu --suite small --include-file registered/a.py'
            path.write_text(yaml.safe_dump({'jobs': {'test': {'steps': [{'run': command}]}}}))
            self.assertEqual(adapter.workflow_files(path, 'small'), ['registered/a.py'])
            with self.assertRaises(ValueError):
                adapter.workflow_files(path, 'missing')
            path.write_text(yaml.safe_dump({'jobs': {'test': {'steps': [{'run': command}, {'run': command}]}}}))
            with self.assertRaises(ValueError):
                adapter.workflow_files(path, 'small')

    def test_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'test').mkdir()
            (root / 'outside.py').touch()
            with self.assertRaises(ValueError):
                adapter.validate_paths(root, ['../outside.py'])


class NativeCLITests(unittest.TestCase):
    """Fixture protocol tests, distinct from real SGLang verification."""
    def run_case(self, body, extra=()):
        import yaml
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / 'source'
            (repo / 'test/registered').mkdir(parents=True)
            (repo / '.github/workflows').mkdir(parents=True)
            (repo / 'python/sglang').mkdir(parents=True)
            (repo / 'python/sglang/__init__.py').touch()
            (repo / 'test/registered/test_sample.py').write_text(body)
            command = 'python3 run_suite.py --hw hcu --suite small --include-file registered/test_sample.py'
            (repo / '.github/workflows/pr-test-hcu.yml').write_text(yaml.safe_dump({'jobs': {'test': {'steps': [{'run': command}]}}}))
            (repo / 'test/run_suite.py').write_text('''import sys, subprocess, json
from pathlib import Path
path = Path('registered/test_sample.py').resolve()
if '--list' in sys.argv:
    print('  - ' + str(path) + ' (est_time=1.0)')
    sys.exit(0)
p = subprocess.run([sys.executable, str(path)])
print('========== TIMINGS BEGIN ==========')
print(json.dumps({'file': str(path), 'passed': p.returncode == 0}))
print('========== TIMINGS END ==========')
sys.exit(p.returncode)
''')
            env = dict(os.environ, PYTHONPATH=str(repo / 'python'))
            out = root / 'results'
            proc = subprocess.run([sys.executable, str(SCRIPTS / 'run_sglang.py'), '--repo', str(repo), '--output', str(out),
                                   '--suite', 'small', '--include-file', 'registered/test_sample.py', '--execute', '--timeout', '3', *extra],
                                  env=env, capture_output=True, text=True)
            self.assertTrue((out / 'result.json').is_file(), proc.stderr)
            return proc.returncode, json.loads((out / 'result.json').read_text())

    def test_actual_pass(self):
        rc, result = self.run_case('import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.assertEqual(2+2,4)\nunittest.main()\n')
        self.assertEqual((rc, result['status']), (0, 'pass'))

    def test_actual_failure(self):
        rc, result = self.run_case('import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.assertEqual(2+2,5)\nunittest.main()\n')
        self.assertNotEqual(rc, 0)
        self.assertEqual(result['status'], 'execution_failure')

    def test_actual_skip(self):
        rc, result = self.run_case('import unittest\nclass T(unittest.TestCase):\n @unittest.skip("fixture")\n def test_x(self): pass\nunittest.main()\n')
        self.assertNotEqual(rc, 0)
        self.assertEqual(result['status'], 'no_tests_executed')

    def test_actual_timeout(self):
        rc, result = self.run_case('import time\ntime.sleep(30)\n')
        self.assertNotEqual(rc, 0)
        self.assertEqual(result['status'], 'timeout')


if __name__ == '__main__':
    unittest.main()
