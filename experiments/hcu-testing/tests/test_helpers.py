import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys


ROOT = Path(__file__).resolve().parents[1]


def module(skill, filename):
    spec = importlib.util.spec_from_file_location(filename, ROOT / 'skills' / skill / 'scripts' / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runner = module('hcu-test-runner', 'run_tests.py')
coverage = module('hcu-coverage-analysis', 'analyze.py')


class EvidenceTests(unittest.TestCase):
    def classify(self, xml, rc=0):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'junit.xml'
            path.write_text(xml)
            return runner.classify(rc, path)[0]

    def test_pass(self):
        self.assertEqual(self.classify('<testsuite><testcase/></testsuite>'), 'pass')

    def test_all_skip_not_pass(self):
        self.assertEqual(self.classify('<testsuite><testcase><skipped/></testcase></testsuite>'), 'no_tests_executed')

    def test_no_cases(self):
        self.assertEqual(self.classify('<testsuite/>'), 'no_tests_executed')

    def test_xml_failure_overrides_zero(self):
        self.assertEqual(self.classify('<testsuite><testcase><failure/></testcase></testsuite>'), 'test_failure')

    def test_exit_failure_overrides_xml(self):
        self.assertEqual(self.classify('<testsuite><testcase/></testsuite>', 1), 'test_failure')

    def test_malformed(self):
        self.assertEqual(self.classify('broken'), 'invalid_report')

    def test_timeout(self):
        self.assertEqual(runner.classify(-9, Path('missing'), True)[0], 'timeout')

    def test_actual_process_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            rc, timed_out = runner.run_process([sys.executable, '-c', 'import time; time.sleep(30)'], d, Path(d) / 'log', 1)
            self.assertTrue(timed_out)
            self.assertNotEqual(rc, 0)

    def test_coverage_and_changed_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / 'a.py').write_text('x=1\ny=2\nz=3\n')
            data = {'files': {'a.py': {'executed_lines': [1], 'missing_lines': [2, 3]}}}
            rows = coverage.analyze(root, data, {'a.py': {1, 2}})
            self.assertEqual(rows[0]['line_coverage'], 50)
            self.assertEqual(rows[0]['missing_lines'], [2])

    def test_invalid_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / 'a.py').write_text('x=1\n')
            for files in [{}, {'../a.py': {}}, {'a.py': {'executed_lines': [2], 'missing_lines': []}},
                          {'a.py': {'executed_lines': [1], 'missing_lines': [1]}}]:
                with self.subTest(files=files), self.assertRaises(ValueError):
                    coverage.analyze(root, {'files': files})

    def test_traced_docstring_does_not_inflate_statement_count(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / 'a.py').write_text('"""Docstring"""\nx=1\ny=2\n')
            data = {'files': {'a.py': {'executed_lines': [1, 2], 'missing_lines': [3],
                                    'summary': {'covered_lines': 1, 'num_statements': 2}}}}
            row = coverage.analyze(root, data)[0]
            self.assertEqual(row['statements'], 2)
            self.assertEqual(row['line_coverage'], 50)
            row = coverage.analyze(root, data, {'a.py': {1, 2, 3}})[0]
            self.assertEqual(row['statements'], 2)
            self.assertEqual(row['line_coverage'], 50)

    def test_empty_module_trace_is_not_a_statement(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / 'empty.py').touch()
            (root / 'a.py').write_text('x=1\n')
            data = {'files': {
                'empty.py': {'executed_lines': [1], 'missing_lines': [],
                             'summary': {'covered_lines': 0, 'num_statements': 0}},
                'a.py': {'executed_lines': [1], 'missing_lines': [],
                         'summary': {'covered_lines': 1, 'num_statements': 1}},
            }}
            rows = coverage.analyze(root, data)
            self.assertEqual([(r['file'], r['statements']) for r in rows], [('a.py', 1)])
            data['files']['empty.py']['executed_lines'] = [2]
            with self.assertRaises(ValueError):
                coverage.analyze(root, data)


if __name__ == '__main__':
    unittest.main()
