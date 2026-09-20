"""End-to-end reporting checks in disposable projects."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/hcu-test-runner/scripts/run_tests.py'


class RunnerCLITests(unittest.TestCase):
    def run_case(self, text, extra=None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / 'source'
            repo.mkdir()
            (repo / 'test_sample.py').write_text(text)
            out = root / 'result'
            p = subprocess.run([sys.executable, str(SCRIPT), '--repo', str(repo), '--output', str(out),
                                '--timeout', '2', *(extra or []), '--', 'test_sample.py', '-q'],
                               capture_output=True, text=True)
            return p.returncode, json.loads((out / 'result.json').read_text())

    def test_passing(self):
        rc, result = self.run_case('def test_ok():\n    assert 2 + 2 == 4\n')
        self.assertEqual(rc, 0)
        self.assertEqual(result['status'], 'pass')
        self.assertIsNone(result['dirty'])
        self.assertEqual(len(result['selected_test_sha256']['test_sample.py']), 64)

    def test_failing(self):
        rc, result = self.run_case('def test_bad():\n    assert False\n')
        self.assertNotEqual(rc, 0)
        self.assertEqual(result['status'], 'test_failure')

    def test_skipped(self):
        rc, result = self.run_case('import pytest\n@pytest.mark.skip(reason="sample")\ndef test_skip(): pass\n')
        self.assertNotEqual(rc, 0)
        self.assertEqual(result['status'], 'no_tests_executed')

    def test_timeout(self):
        rc, result = self.run_case('import time\ndef test_slow(): time.sleep(30)\n')
        self.assertNotEqual(rc, 0)
        self.assertEqual(result['status'], 'timeout')


if __name__ == '__main__':
    unittest.main()
