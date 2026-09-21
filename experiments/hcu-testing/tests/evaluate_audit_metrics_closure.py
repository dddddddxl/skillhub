"""Validate G_METRICS end-to-end on isolated, clean base/candidate snapshots.

Requires the reviewed SGLang runtime, pytest and coverage.py 7.6.1. No models,
network or device access are needed. Leaves evidence and mutation copies.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TEST = 'test/registered/unit/observability/test_metrics_utils.py'
MODULE = 'python/sglang/srt/observability/utils.py'


def main():
    parser = argparse.ArgumentParser()
    for name in ('base', 'candidate', 'backlog', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--image-id', required=True)
    a = parser.parse_args()
    base, candidate, out = a.base.resolve(), a.candidate.resolve(), a.output.resolve()
    if any(out == repo or repo in out.parents for repo in (base, candidate)):
        parser.error('Output must be outside both snapshots')
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(name, argv, repo=candidate, expected=0, extra=None):
        env = dict(os.environ, PYTHONPATH=str(repo / 'python'), PYTHONDONTWRITEBYTECODE='1', **(extra or {}))
        proc = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True, timeout=180)
        (out / (name + '.log')).write_text(proc.stdout + proc.stderr)
        commands.append(dict(name=name, command=argv, cwd=str(repo), returncode=proc.returncode, expected=expected))
        (out / 'commands.json').write_text(json.dumps(commands, indent=2))
        if proc.returncode != expected:
            raise RuntimeError(name + ': unexpected exit; inspect log')
        print(name + ': verified exit ' + str(expected), flush=True)
        return proc.stdout.strip()

    def git(repo, *args):
        return ['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo), *args]

    run('handoff', [sys.executable, str(ROOT / 'skills/hcu-test-generation/scripts/check_handoff.py'),
                    '--repo', str(base), '--backlog', str(a.backlog), '--task', 'G_METRICS'], repo=base)
    base_sha = run('base-sha', git(base, 'rev-parse', 'HEAD'))
    candidate_sha = run('candidate-sha', git(candidate, 'rev-parse', 'HEAD'))
    assert not run('base-clean', git(base, 'status', '--porcelain'))
    assert not run('candidate-clean', git(candidate, 'status', '--porcelain'))
    assert (base / MODULE).read_bytes() == (candidate / MODULE).read_bytes()
    changed = run('changed-files', git(candidate, 'diff', '--name-only', base_sha, candidate_sha)).splitlines()
    assert changed == [TEST], changed
    patch = run('patch', git(candidate, 'diff', '--binary', base_sha, candidate_sha))
    (out / 'G_METRICS.patch').write_text(patch + '\n')
    native = ROOT / 'skills/hcu-test-runner/scripts/run_sglang.py'
    run('native-pr', [sys.executable, str(native), '--repo', str(candidate), '--output', str(out / 'native-pr'),
                      '--suite', 'stage-b-test-1-hcu-small', '--include-file', TEST.removeprefix('test/'),
                      '--execute', '--timeout', '90', '--image-id', a.image_id])
    native_result = json.loads((out / 'native-pr/result.json').read_text())
    assert native_result['status'] == 'pass' and native_result['counts']['tests'] == 14
    for name, repo, sha in [('baseline', base, base_sha), ('candidate', candidate, candidate_sha)]:
        env = {'COVERAGE_FILE': str(out / (name + '.coverage'))}
        run(name + '-tests', [sys.executable, '-m', 'coverage', 'run', '--rcfile=/dev/null', '--include=' + str(repo / MODULE),
                              '-m', 'pytest', '--noconftest', '-p', 'no:cacheprovider', '-q', str(repo / TEST),
                              '--junitxml=' + str(out / (name + '.xml'))], repo=repo, extra=env)
        run(name + '-coverage', [sys.executable, '-m', 'coverage', 'json', '--rcfile=/dev/null', '-o', str(out / (name + '-coverage.json'))], repo=repo, extra=env)
        run(name + '-analysis', [sys.executable, str(ROOT / 'skills/hcu-coverage-analysis/scripts/analyze.py'), '--repo', str(repo),
                                 '--coverage', str(out / (name + '-coverage.json')), '--tested-commit', sha,
                                 '--output', str(out / (name + '-analysis.json'))], repo=repo)
    for name, old, new in [('normalization', 'return sorted(set(default_buckets))', 'return list(default_buckets)'),
                            ('exponent', 'start * (width**i)', 'start * (width**(i + 1))')]:
        mutant = out / ('mutant-' + name)
        mutant.mkdir()
        shutil.copytree(candidate / 'python', mutant / 'python', ignore=shutil.ignore_patterns('__pycache__'))
        (mutant / TEST).parent.mkdir(parents=True)
        shutil.copy2(candidate / TEST, mutant / TEST)
        path = mutant / MODULE
        original = path.read_text()
        assert original.count(old) == 1
        path.write_text(original.replace(old, new))
        for label, test, expected in [('old', base / TEST, 0), ('new', mutant / TEST, 1)]:
            result_dir = out / (name + '-' + label)
            run(name + '-' + label, [sys.executable, str(ROOT / 'skills/hcu-test-runner/scripts/run_tests.py'),
                                     '--repo', str(mutant), '--output', str(result_dir), '--timeout', '90', '--',
                                     str(test), '--noconftest', '-p', 'no:cacheprovider', '-q'], repo=mutant, expected=expected)
            result = json.loads((result_dir / 'result.json').read_text())
            assert result['status'] == ('pass' if label == 'old' else 'test_failure')
            assert result['counts']['errors'] == 0 and result['counts']['skipped'] == 0
    assert not run('base-clean-after', git(base, 'status', '--porcelain'))
    assert not run('candidate-clean-after', git(candidate, 'status', '--porcelain'))
    result = dict(task_id='G_METRICS', status='validated', disposition='adapt_prior_original_tests_into_existing_unittest',
                  base_commit=base_sha, candidate_commit=candidate_sha, image_id=a.image_id,
                  changed_files=changed, patch_sha256=hashlib.sha256((out / 'G_METRICS.patch').read_bytes()).hexdigest(),
                  native_pr_selected_file=True, native_cases=14, cpu_only=True, production_code_changed=False,
                  publication='not_pushed_or_merged', daily_selection='not_assessed')
    (out / 'completion.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
