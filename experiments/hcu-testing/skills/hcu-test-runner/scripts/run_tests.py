"""Bounded pytest execution with explicit evidence; Python 3.8+, standard library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def git(repo, *args):
    root = next((p for p in [repo, *repo.parents] if (p / '.git').exists()), repo)
    p = subprocess.run(['git', '-c', 'safe.directory=' + str(root), '-C', str(repo), *args], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def run_process(argv, cwd, log, timeout):
    with open(log, 'w', encoding='utf-8') as stream:
        p = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                             start_new_session=(os.name == 'posix'))
        try:
            return p.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
            p.wait()
            return p.returncode, True


def classify(exit_code, report, timed_out=False):
    if timed_out:
        return 'timeout', {}
    try:
        root = ET.parse(report).getroot()
        cases = list(root.iter('testcase'))
        counts = {'tests': len(cases), 'failed': 0, 'errors': 0, 'skipped': 0}
        for case in cases:
            for key, tag in [('failed', 'failure'), ('errors', 'error'), ('skipped', 'skipped')]:
                counts[key] += int(case.find(tag) is not None)
        if exit_code != 0 or counts['failed'] or counts['errors']:
            return 'test_failure', counts
        if not cases or counts['skipped'] == len(cases):
            return 'no_tests_executed', counts
        return 'pass', counts
    except (OSError, ET.ParseError):
        return 'invalid_report', {}


PREFLIGHT = '''import json, torch
if not torch.version.hip:
    raise RuntimeError("HCU probe requires a HIP PyTorch runtime")
x = torch.ones(4, device="cuda")
y = x + 1
torch.cuda.synchronize()
assert y.cpu().tolist() == [2.0] * 4
print(json.dumps({"torch": torch.__version__, "hip": torch.version.hip,
 "device": torch.cuda.get_device_name(0), "device_count": torch.cuda.device_count(),
 "tensor_probe": "pass"}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--require-hcu', action='store_true')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--image-id')
    parser.add_argument('tests', nargs=argparse.REMAINDER)
    a = parser.parse_args()
    repo, out = a.repo.resolve(), a.output.resolve()
    tests = a.tests[1:] if a.tests[:1] == ['--'] else a.tests
    if not repo.is_dir() or not tests or a.timeout <= 0:
        parser.error('Existing repo, explicit tests and positive timeout required')
    if repo == out or repo in out.parents:
        parser.error('Output must be outside the checkout')
    if any(x.startswith(('--junit', '--override-ini', '-o')) for x in tests):
        parser.error('Do not override evidence output/configuration')
    out.mkdir(parents=True, exist_ok=False)
    git_status = git(repo, 'status', '--porcelain')
    result = {'schema_version': 1, 'status': 'unknown', 'source_commit': git(repo, 'rev-parse', 'HEAD'),
              'dirty': None if git_status is None else bool(git_status), 'image_id': a.image_id,
              'python': sys.version.split()[0], 'hcu_requested': a.require_hcu,
              'started_at_unix': time.time(), 'tests': tests}
    result['selected_test_sha256'] = {}
    for value in tests:
        candidate = repo / value.split('::', 1)[0]
        if not value.startswith('-') and candidate.is_file():
            result['selected_test_sha256'][value] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    def finish(status, code):
        result['status'] = status
        result['duration_seconds'] = round(time.time() - result['started_at_unix'], 3)
        (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))
        return code
    if a.require_hcu:
        rc, timeout = run_process([sys.executable, '-c', PREFLIGHT], repo, out / 'preflight.log', min(60, a.timeout))
        result['preflight_exit_code'] = rc
        if rc != 0 or timeout:
            return finish('environment_blocked', 2)
        try:
            result['device'] = json.loads((out / 'preflight.log').read_text().strip().splitlines()[-1])
        except (ValueError, IndexError):
            return finish('environment_blocked', 2)
    argv = [sys.executable, '-m', 'pytest', *tests, '--junitxml=' + str(out / 'junit.xml')]
    result['command'] = argv
    rc, timed_out = run_process(argv, repo, out / 'test.log', a.timeout)
    result['exit_code'] = rc
    status, counts = classify(rc, out / 'junit.xml', timed_out)
    result['counts'] = counts
    return finish(status, 0 if status == 'pass' else 1)


if __name__ == '__main__':
    sys.exit(main())
