"""模板行为回归：独立场景、真实断言及无设备收集；不代表 HCU 内核验证。"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ASSETS = Path(__file__).resolve().parents[1] / 'skills/hcu-test-generation/assets'
PRODUCT = '''
def bounded(value):
    if value < 0:
        raise ValueError("negative input")
    return value * 2

def select(cu):
    return "sparse" if cu in (64, 72) else None

def compute(spec):
    import numpy as np
    return np.array([x * 2 for x in spec], dtype="float64")
'''
ADAPTERS = {
    'pytest_logic.py.tpl': '''
def case_specs():
    return [dict(id="G1:normal", kwargs={"value":3}, expected=6),
            dict(id="G1:zero", kwargs={"value":0}, expected=0),
            dict(id="G1:negative", kwargs={"value":-1}, error=ValueError, match="negative input")]

@pytest.fixture
def target():
    from product import bounded
    return bounded
''',
    'pytest_routing.py.tpl': '''
def case_specs():
    return [dict(id="G2:cu64", kwargs={"cu":64}, expected="sparse"),
            dict(id="G2:cu72", kwargs={"cu":72}, expected="sparse"),
            dict(id="G2:cu71", kwargs={"cu":71}, expected=None)]

@pytest.fixture
def select():
    from product import select
    return select
''',
    'pytest_numerical.py.tpl': '''
def case_specs():
    return [dict(id="G3:signed", spec=[-2.0,0.0,3.0], kind="numpy",
                 dtype="float64", rtol=1e-6, atol=1e-8)]

@pytest.fixture
def implementations():
    import numpy as np
    from product import compute
    def reference(spec):
        return np.array([x + x for x in spec], dtype="float64")
    return compute, reference
''',
}


class TemplateTests(unittest.TestCase):
    def run_template(self, name, adapter='', product=PRODUCT, collect=False):
        with tempfile.TemporaryDirectory(prefix='hcu-template-') as tmp:
            root = Path(tmp)
            (root / 'product.py').write_text(product, encoding='utf-8')
            (root / 'test_candidate.py').write_text(
                (ASSETS / name).read_text(encoding='utf-8') + adapter, encoding='utf-8')
            env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONUTF8='1')
            cmd = [sys.executable, '-m', 'pytest', '-q', 'test_candidate.py', '--junitxml=result.xml']
            if collect:
                cmd.append('--collect-only')
            result = subprocess.run(cmd, cwd=root, env=env, capture_output=True,
                                    text=True, encoding='utf-8', timeout=30)
            report = root / 'result.xml'
            result.cases = list(ET.parse(report).iter('testcase')) if report.exists() else []
            return result

    def test_unfilled_templates_fail_at_collection(self):
        for name in ADAPTERS:
            with self.subTest(name=name):
                result = self.run_template(name)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('NotImplementedError', result.stdout)

    def test_real_calls_pass_and_mutations_fail_assertions(self):
        mutations = {
            'pytest_logic.py.tpl': PRODUCT.replace('return value * 2', 'return value * 3'),
            'pytest_routing.py.tpl': PRODUCT.replace('cu in (64, 72)', 'cu == 64'),
            'pytest_numerical.py.tpl': PRODUCT.replace('[x * 2 for x in spec]', '[x * 3 for x in spec]'),
        }
        for name, adapter in ADAPTERS.items():
            with self.subTest(name=name):
                good = self.run_template(name, adapter)
                self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
                bad = self.run_template(name, adapter, mutations[name])
                self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
                self.assertIn('AssertionError', bad.stdout)
                self.assertNotIn('ERROR at setup', bad.stdout)
                self.assertEqual(len(good.cases), len(bad.cases))
                self.assertEqual(len({c.get('name') for c in good.cases}), len(good.cases))

    def test_first_failure_does_not_hide_later_scenarios(self):
        result = self.run_template('pytest_logic.py.tpl', ADAPTERS['pytest_logic.py.tpl'],
                                   PRODUCT.replace('return value * 2', 'return value * 3'))
        self.assertEqual(len(result.cases), 3)
        by_id = {c.get('name'): c for c in result.cases}
        self.assertIsNotNone(by_id['test_logic_contract[G1:normal]'].find('failure'))
        self.assertIsNone(by_id['test_logic_contract[G1:zero]'].find('failure'))
        self.assertIsNone(by_id['test_logic_contract[G1:negative]'].find('failure'))

    def test_empty_and_duplicate_ids_fail_collection(self):
        for name in ADAPTERS:
            for cases in ('[]', '[dict(id="duplicate"), dict(id="duplicate")]'):
                with self.subTest(name=name, cases=cases):
                    result = self.run_template(name, '\ndef case_specs():\n    return ' + cases + '\n')
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn('ValueError', result.stdout)

    def test_collect_does_not_initialize_product_or_device(self):
        for name, adapter in ADAPTERS.items():
            with self.subTest(name=name):
                result = self.run_template(name, adapter, 'raise RuntimeError("device initialization forbidden")',
                                           collect=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn('RuntimeError', result.stdout)

    def test_numerical_rejects_identical_reference_and_invalid_tolerance(self):
        adapter = ADAPTERS['pytest_numerical.py.tpl']
        for changed in (adapter.replace('return compute, reference', 'return compute, compute'),
                        adapter.replace('rtol=1e-6', 'rtol=float("inf")')):
            with self.subTest(adapter=changed):
                result = self.run_template('pytest_numerical.py.tpl', changed)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('AssertionError', result.stdout)

    def test_numerical_rejects_wrong_dtype_shape_and_nan(self):
        for changed in (PRODUCT.replace('dtype="float64"', 'dtype="float32"'),
                        PRODUCT.replace('[x * 2 for x in spec]', '[1.0]'),
                        PRODUCT.replace('[x * 2 for x in spec]', '[float("nan") for x in spec]')):
            with self.subTest(product=changed):
                result = self.run_template('pytest_numerical.py.tpl', ADAPTERS['pytest_numerical.py.tpl'], changed)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('AssertionError', result.stdout)


if __name__ == '__main__':
    unittest.main()
