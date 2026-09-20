"""Conservative SGLang native-runner adapter. Requires PyYAML and project Python."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
import time

import yaml

from run_tests import PREFLIGHT, git, run_process


def workflow_files(path, suite):
    """Read literal native-runner commands; never evaluate shell or expressions."""
    data = yaml.safe_load(path.read_text())
    matches = []
    for job in data['jobs'].values():
        for step in job.get('steps', []):
            script = step.get('run', '')
            # A command continues only on a backslash-newline.
            for line in re.sub(r'\\\s*\n', ' ', script).splitlines():
                if 'run_suite.py' not in line or line.lstrip().startswith('#'):
                    continue
                tokens = shlex.split(line)
                if 'run_suite.py' not in tokens:
                    continue
                def values(flag):
                    return [tokens[i + 1] for i, value in enumerate(tokens[:-1]) if value == flag]
                if values('--suite') == [suite] and values('--hw') == ['hcu']:
                    files = values('--include-file')
                    if not files or len(files) != len(set(files)):
                        raise ValueError('Explicit unique workflow whitelist required')
                    matches.append(files)
    if len(matches) != 1:
        raise ValueError('Expected one unambiguous native command for the suite')
    return matches[0]


def validate_paths(repo, files):
    root = (repo / 'test').resolve()
    for name in files:
        path = (root / name).resolve()
        if Path(name).is_absolute() or root not in path.parents or not path.is_file():
            raise ValueError('Test must be an existing file inside repo/test: ' + name)


def enabled_files(log):
    return {str(Path(x).resolve()) for x in re.findall(r'^\s*- (.+?) \(est_time=', log, re.M)}


def classify_native(rc, log, selected, timed_out=False):
    if timed_out:
        return 'timeout', {}
    if rc != 0:
        return 'execution_failure', {}
    blocks = re.findall(r'========== TIMINGS BEGIN ==========\s*(.*?)\s*========== TIMINGS END ==========', log, re.S)
    try:
        rows = [json.loads(line) for block in blocks for line in block.splitlines() if line.strip()]
        if len(rows) != 1 or Path(rows[0]['file']).resolve() != selected.resolve() or rows[0]['passed'] is not True:
            return 'invalid_report', {}
    except (ValueError, KeyError, TypeError):
        return 'invalid_report', {}
    # Only unittest's summary is supported for case-level success in this version.
    # File-level success alone can hide all-skipped or empty suites.
    summaries = re.findall(r'^Ran (\d+) tests? in [^\n]+\n\s*OK(?: \(skipped=(\d+)\))?\s*$', log, re.M)
    if len(summaries) != 1:
        return 'native_success_unverified', {'files_succeeded': 1}
    count, skipped = (int(summaries[0][0]), int(summaries[0][1] or 0))
    if skipped > count:
        return 'invalid_report', {}
    counts = {'tests': count, 'skipped': skipped, 'files_succeeded': 1}
    return ('pass' if count > skipped else 'no_tests_executed'), counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--suite', required=True)
    p.add_argument('--include-file', action='append', default=[])
    p.add_argument('--execute', action='store_true')
    p.add_argument('--require-hcu', action='store_true')
    p.add_argument('--timeout', type=int, default=180)
    p.add_argument('--image-id')
    a = p.parse_args()
    repo, out = a.repo.resolve(), a.output.resolve()
    if repo == out or repo in out.parents or a.timeout <= 0:
        p.error('Positive timeout and new output outside checkout required')
    if a.execute and len(a.include_file) != 1:
        p.error('Execution is deliberately bounded to one explicit --include-file')
    workflow = repo / '.github/workflows/pr-test-hcu.yml'
    try:
        whitelist = workflow_files(workflow, a.suite)
        selected = a.include_file or whitelist
        if len(selected) != len(set(selected)) or not set(selected) <= set(whitelist):
            raise ValueError('Selected files must be unique members of workflow whitelist')
        validate_paths(repo, selected)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as e:
        p.error(str(e))
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    state = git(repo, 'status', '--porcelain')
    result = dict(schema_version=1, adapter='sglang-native', source_commit=git(repo, 'rev-parse', 'HEAD'),
                  dirty=None if state is None else bool(state), image_id=a.image_id, suite=a.suite,
                  selected=selected, workflow_whitelist=whitelist, hcu_requested=a.require_hcu,
                  evidence_level='native-log-not-junit', started_at_unix=started)
    paths = [workflow, repo / 'test/run_suite.py'] + [repo / 'test' / name for name in selected]
    result['sha256'] = {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    def finish(status, counts=None):
        result.update(status=status, counts=counts or {}, duration_seconds=round(time.time() - started, 3))
        (out / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps({'status': status, 'counts': result['counts'], 'output': str(out)}))
        return 0 if status in ('pass', 'plan_ready') else 2
    cmd = [sys.executable, 'run_suite.py', '--hw', 'hcu', '--suite', a.suite]
    for name in selected:
        cmd += ['--include-file', name]
    result['collection_command'] = cmd + ['--list']
    rc, expired = run_process(result['collection_command'], repo / 'test', out / 'collection.log', min(60, a.timeout))
    result['collection_exit_code'] = rc
    if rc or expired:
        return finish('collection_failed')
    enabled = enabled_files((out / 'collection.log').read_text())
    if enabled != {str((repo / 'test' / f).resolve()) for f in selected}:
        return finish('selection_not_enabled')
    if not a.execute:
        return finish('plan_ready')
    # Explicit source mode: refuse to silently validate an unrelated installed wheel.
    probe = 'import json,sglang; print(json.dumps({"module":sglang.__file__}))'
    rc, expired = run_process([sys.executable, '-c', probe], repo / 'test', out / 'source-probe.log', min(60, a.timeout))
    try:
        module = Path(json.loads((out / 'source-probe.log').read_text().strip().splitlines()[-1])['module']).resolve()
        result['sglang_module'] = str(module)
        valid_source = (repo / 'python').resolve() in module.parents
    except (ValueError, IndexError, KeyError, TypeError):
        valid_source = False
    if rc or expired or not valid_source:
        return finish('environment_blocked')
    if a.require_hcu:
        rc, expired = run_process([sys.executable, '-c', PREFLIGHT], repo, out / 'preflight.log', min(60, a.timeout))
        result['preflight_exit_code'] = rc
        if rc or expired:
            return finish('environment_blocked')
        try:
            result['device'] = json.loads((out / 'preflight.log').read_text().strip().splitlines()[-1])
        except (ValueError, IndexError):
            return finish('environment_blocked')
    result['command'] = cmd + ['--timeout-per-file', str(a.timeout)]
    rc, expired = run_process(result['command'], repo / 'test', out / 'test.log', a.timeout)
    result['exit_code'] = rc
    status, counts = classify_native(rc, (out / 'test.log').read_text(errors='replace'), repo / 'test' / selected[0], expired)
    return finish(status, counts)


if __name__ == '__main__':
    sys.exit(main())
