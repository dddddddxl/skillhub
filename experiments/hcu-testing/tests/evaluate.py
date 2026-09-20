"""Reproduce private-node evaluation from an isolated /evaluation mount."""
import json
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    evaluation = root.parents[2]
    checks = []
    def check(name, argv, expected=0, cwd=root):
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=90)
        checks.append({'name': name, 'expected_exit': expected, 'actual_exit': p.returncode,
                       'pass': p.returncode == expected, 'stdout': p.stdout, 'stderr': p.stderr})
    check('helper_invariants', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_helpers.py', '-v'])
    check('runner_cli', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_runner_cli.py', '-v'])
    for skill in sorted((root / 'skills').iterdir()):
        check(skill.name + '_structure', [sys.executable, str(evaluation / 'quick_validate.py'), str(skill)])
    source = evaluation / 'coverage-source'
    check('catalog_validation', [sys.executable, 'scripts/validate_skills.py'], cwd=source)
    check('catalog_drift', [sys.executable, 'scripts/generate_catalog.py', '--check'], cwd=source)
    analyzer = root / 'skills/hcu-coverage-analysis/scripts/analyze.py'
    common = [sys.executable, str(analyzer), '--coverage', str(evaluation / 'coverage.json'),
              '--output', str(evaluation / 'must-not-exist.json')]
    check('reject_wrong_commit', common + ['--repo', str(source), '--tested-commit', '0' * 40], 2)
    head = subprocess.check_output(['git', '-c', 'safe.directory=' + str(source), '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    check('reject_dirty_source', common + ['--repo', str(evaluation / 'mutation-source'), '--tested-commit', head], 2)
    check('reject_empty_changed_scope', common + ['--repo', str(source), '--tested-commit', head, '--base-ref', head], 2)
    for name, directory, expected in [('hardware', 'results-hcu-2', 'pass'), ('mutation', 'results-mutation', 'test_failure')]:
        result = json.loads((evaluation / directory / 'result.json').read_text())
        checks.append({'name': name, 'pass': result['status'] == expected, 'result': result})
    report = {'passed': sum(bool(c['pass']) for c in checks), 'total': len(checks), 'checks': checks}
    (evaluation / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'],
                      'failed_checks': [c['name'] for c in checks if not c['pass']]}))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    sys.exit(main())
