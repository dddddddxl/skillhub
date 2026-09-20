"""Run bounded real-project generation/mutation/coverage evaluation offline.

All writable artifacts and mutation clones are under a new output directory.
The supplied SGLang checkout is never edited. Requires pytest, coverage, git.
"""
import argparse
import hashlib
import difflib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
GENERATED = Path(__file__).with_name('test_sglang_metrics_generated.py')
TARGET = 'python/sglang/srt/observability/utils.py'
EXISTING = 'test/registered/unit/observability/test_metrics_utils.py'
ANALYZER = ROOT / 'skills/hcu-coverage-analysis/scripts/analyze.py'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image-id', required=True)
    a = p.parse_args()
    repo, out = a.repo.resolve(), a.output.resolve()
    if repo == out or repo in out.parents:
        p.error('Output must be outside checkout')
    out.mkdir(parents=True, exist_ok=False)
    records = []
    def run(name, cmd, source=repo, expected=0, env_extra=None):
        env = dict(os.environ, PYTHONPATH=str(source / 'python'), PYTHONDONTWRITEBYTECODE='1', **(env_extra or {}))
        proc = subprocess.run(cmd, cwd=source, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        (out / (name + '.log')).write_text(proc.stdout)
        record = dict(name=name, command=cmd, cwd=str(source), returncode=proc.returncode, expected=expected)
        records.append(record)
        (out / 'commands.json').write_text(json.dumps(records, indent=2))
        if proc.returncode != expected:
            raise RuntimeError(name + ' unexpected result; see ' + str(out / (name + '.log')))
        print(name + ': expected exit ' + str(expected), flush=True)
        return proc.stdout
    sha = run('source-sha', ['git', '-c', 'safe.directory=' + str(repo), 'rev-parse', 'HEAD']).strip()
    assert not run('source-clean-before', ['git', '-c', 'safe.directory=' + str(repo), 'status', '--porcelain']).strip()
    identity = run('source-identity', [sys.executable, '-c', 'import sglang.srt.observability.utils as m; print(m.__file__)']).strip().splitlines()[-1]
    assert Path(identity).resolve() == repo / TARGET
    evidence = dict(source_commit=sha, image_id=a.image_id, source_file=TARGET,
                    source_sha256=hashlib.sha256((repo / TARGET).read_bytes()).hexdigest(),
                    generated_test_sha256=hashlib.sha256(GENERATED.read_bytes()).hexdigest(), device_tests=False)
    (out / 'provenance.json').write_text(json.dumps(evidence, indent=2))
    for name, paths in [('baseline', [str(repo / EXISTING)]), ('augmented', [str(repo / EXISTING), str(GENERATED)])]:
        datafile = str(out / (name + '.coverage'))
        env = {'COVERAGE_FILE': datafile}
        run(name, [sys.executable, '-m', 'coverage', 'run', '--rcfile=/dev/null', '--branch', '--include=' + str(repo / TARGET), '-m', 'pytest',
                   '--noconftest', '-p', 'no:cacheprovider', '-q', *paths, '--junitxml=' + str(out / (name + '.xml'))], env_extra=env)
        run(name + '-json', [sys.executable, '-m', 'coverage', 'json', '--rcfile=/dev/null', '-o', str(out / (name + '-coverage.json'))], env_extra=env)
        run(name + '-analysis', [sys.executable, str(ANALYZER), '--repo', str(repo), '--coverage', str(out / (name + '-coverage.json')),
                                '--tested-commit', sha, '--output', str(out / (name + '-analysis.json'))])
    run('wrong-commit-rejected', [sys.executable, str(ANALYZER), '--repo', str(repo), '--coverage', str(out / 'augmented-coverage.json'),
                                '--tested-commit', '0' * 40, '--output', str(out / 'must-not-exist.json')], expected=2)
    assert not (out / 'must-not-exist.json').exists()
    mutations = [
        ('drop-default-normalization', 'return sorted(set(default_buckets))', 'return list(default_buckets)'),
        ('exponential-off-by-one', 'start * (width**i)', 'start * (width**(i + 1))'),
    ]
    for name, old, new in mutations:
        clone = out / name
        # A detached Python source snapshot is sufficient for these CPU tests.
        # Avoid clone ownership exceptions or shared Git object dependencies.
        clone.mkdir()
        shutil.copytree(repo / 'python', clone / 'python', ignore=shutil.ignore_patterns('__pycache__'))
        (clone / EXISTING).parent.mkdir(parents=True)
        shutil.copy2(repo / EXISTING, clone / EXISTING)
        path = clone / TARGET
        original = path.read_text()
        assert original.count(old) == 1
        path.write_text(original.replace(old, new))
        (out / (name + '.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True), path.read_text().splitlines(True),
                                                                       fromfile='a/' + TARGET, tofile='b/' + TARGET)))
        # Mutation must survive the existing suite and be killed by generated tests.
        run(name + '-baseline', [sys.executable, '-m', 'pytest', '--noconftest', '-p', 'no:cacheprovider', '-q', str(clone / EXISTING),
                                '--junitxml=' + str(out / (name + '-baseline.xml'))], source=clone)
        run(name + '-generated', [sys.executable, '-m', 'pytest', '--noconftest', '-p', 'no:cacheprovider', '-q', str(GENERATED),
                                 '--junitxml=' + str(out / (name + '-generated.xml'))], source=clone, expected=1)
    assert not run('source-clean-after', ['git', '-c', 'safe.directory=' + str(repo), 'status', '--porcelain']).strip()
    evidence['status'] = 'complete'
    (out / 'verification.json').write_text(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
