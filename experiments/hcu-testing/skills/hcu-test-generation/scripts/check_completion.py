"""核对补测完成记录及工件身份；只检查证据一致性，不自动关闭缺口。"""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re


def _check_v1(plan, data, root):
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)
    def sha(value):
        return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)
    require(data.get('schema_version') == 1 and plan.get('plan_schema_version') == 1, 'Unsupported completion/plan schema')
    require(data['repository'] == plan['repository'] and data['audit_source_commit'] == plan['source_commit'],
            'Completion belongs to another audit')
    artifacts = {}
    for ref in data['evidence']:
        require(ref['id'] not in artifacts and sha(ref['sha256']), 'Unique artifact ID and SHA256 required')
        full = (root / ref['path']).resolve()
        require(not Path(ref['path']).is_absolute() and root in full.parents and full.is_file(), 'Artifact escapes evidence root or missing')
        require(hashlib.sha256(full.read_bytes()).hexdigest() == ref['sha256'], 'Artifact hash changed')
        artifacts[ref['id']] = json.loads(full.read_text(encoding='utf-8'))
    tasks = {t['id']: t for t in plan['tasks']}
    scenarios = {p['task_id']: {s['scenario_id']: s for s in p['scenarios']} for p in plan['planning']}
    records = data['tasks']
    require(len(records) == len(tasks) and {r['task_id'] for r in records} == tasks.keys(), 'Completion must retain exactly selected tasks')
    validated = []
    def refs(ids):
        require(isinstance(ids, list) and ids and set(ids) <= artifacts.keys(), 'Missing completion evidence')
    def run(id, revision):
        require(id in artifacts, 'Run artifact missing')
        a = artifacts[id]
        require(a['source_commit'] == revision['source_commit'] and a.get('patch_sha256') == revision.get('patch_sha256'), 'Tested revision/patch differs from artifact')
        require(not a.get('dirty') or sha(a.get('patch_sha256')), 'Dirty run lacks actual patch identity')
        require(a.get('command'), 'Run command missing')
        cases = a['cases']
        require(cases and len({c['id'] for c in cases}) == len(cases), 'Run cases empty or duplicate')
        require(all(c['outcome'] in {'passed', 'failed', 'error', 'skipped', 'xfailed'} for c in cases), 'Invalid run outcome')
        expected = dict(tests=len(cases), failed=sum(c['outcome'] == 'failed' for c in cases),
                        errors=sum(c['outcome'] == 'error' for c in cases),
                        skipped=sum(c['outcome'] in {'skipped', 'xfailed'} for c in cases))
        require(a['counts'] == expected, 'Run counts disagree with cases')
        return a, {c['id']: c for c in cases}
    for r in records:
        task = tasks[r['task_id']]
        planned = scenarios[r['task_id']]
        require(r['status'] in {'implemented_unverified', 'validated', 'blocked', 'needs_review'}, 'Invalid completion status')
        require(isinstance(r.get('validated_scope'), str) and r['validated_scope'].strip(), 'Bounded validation scope required')
        actual = r['scenario_results']
        require(len(actual) == len(planned) and {s['scenario_id'] for s in actual} == planned.keys(), 'Missing/duplicate/unplanned scenario')
        require(all(s['outcome'] in {'passed', 'failed', 'skipped', 'not_run'} for s in actual), 'Invalid scenario outcome')
        acceptance = r['acceptance_results']
        require(len(acceptance) == len(task['acceptance']) and {a['condition'] for a in acceptance} == set(task['acceptance']),
                'Acceptance conditions missing, duplicated or rewritten')
        require(all(a['status'] in {'met', 'unmet', 'unknown'} for a in acceptance), 'Invalid acceptance status')
        for a in acceptance:
            if a['status'] == 'met':
                refs(a['evidence'])
        revision = r['tested_revision']
        require(re.fullmatch('[0-9a-f]{40}', revision['source_commit']), 'Tested commit required')
        require(revision.get('patch_sha256') is None or sha(revision['patch_sha256']), 'Invalid patch identity')
        for s in actual:
            if s['outcome'] != 'not_run':
                artifact, cases = run(s['evidence'], revision)
                require(s['test_id'] in cases and cases[s['test_id']]['outcome'] == s['outcome'], 'Scenario result differs from run')
                if s['outcome'] == 'passed':
                    require(artifact.get('exit_code') == 0 and artifact.get('status') == 'pass', 'Positive evidence is not a passing run')
        if r['status'] != 'validated':
            continue
        require(not r.get('unresolved_prerequisites') and not plan.get('unselected_dependencies'), 'Unresolved prerequisites/dependencies')
        require(all(a['status'] == 'met' for a in acceptance), 'Validated task has unmet acceptance')
        require(all(s['outcome'] == 'passed' for s in actual), 'Validated task has unexecuted/failed scenarios')
        required = task.get('required_evidence', ['positive', 'negative_control', 'ci_selection'])
        require(set(required) <= {'positive', 'negative_control', 'ci_selection', 'ci_execution'}, 'Unknown required evidence type')
        if 'negative_control' in required:
            controls = r['negative_controls']
            require({c['scenario_id'] for c in controls} == planned.keys(), 'Negative controls do not cover planned scenarios')
            for c in controls:
                require(c.get('mutation') and c.get('target_assertion'), 'Negative control rationale required')
                require(c['baseline_evidence'] == next(s['evidence'] for s in actual if s['scenario_id'] == c['scenario_id']),
                        'Negative control baseline differs from positive run')
                require(c['test_id'] == next(s['test_id'] for s in actual if s['scenario_id'] == c['scenario_id']),
                        'Negative control targets a different test')
                mutated = c['tested_revision']
                require(mutated['source_commit'] == revision['source_commit'] and sha(mutated.get('patch_sha256')) and
                        mutated['patch_sha256'] != revision.get('patch_sha256'), 'Negative control needs isolated mutation identity')
                artifact, cases = run(c['evidence'], mutated)
                require(artifact.get('exit_code') == 1 and artifact.get('status') == 'test_failure', 'Negative control did not fail as a test')
                require(c['test_id'] in cases and cases[c['test_id']]['outcome'] == 'failed' and c.get('failure_kind') == 'target_assertion',
                        'Import/setup/error failure is not a negative control')
        for kind in ('ci_selection', 'ci_execution'):
            if kind not in required:
                continue
            refs([r.get(kind)])
            artifact = artifacts[r[kind]]
            require(artifact.get('source_commit') == revision['source_commit'] and artifact.get('patch_sha256') == revision.get('patch_sha256'),
                    'CI evidence has wrong revision')
            require(artifact.get('lane') in task['lanes'], 'CI evidence has wrong lane')
            ids = {s['test_id'] for s in actual}
            if kind == 'ci_selection':
                require(artifact.get('command') and not artifact.get('unresolved_gates') and ids <= set(artifact['selected_ids']),
                        'CI collection does not select all required cases')
            else:
                artifact, cases = run(r[kind], revision)
                require(artifact.get('run_id') and artifact.get('job_id') and artifact.get('attempt') and artifact.get('source_identity') == 'verified',
                        'Actual CI run identity missing')
                require(ids <= cases.keys() and all(cases[i]['outcome'] == 'passed' for i in ids), 'Required CI cases not passed')
        validated.append(r['task_id'])
    return dict(status='evidence_consistent', validated_tasks=validated,
                limitation='Hashes and identities checked; oracle independence, assertion meaning, log authenticity and acceptance still require review. No gap auto-closed.')


def _check_v2(plan, data, root):
    """多方法协议；已填证据的一致性与 validated 的完整性分别检查。"""
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def sha(value):
        return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)

    def unique_index(items, key, reason):
        require(isinstance(items, list), reason)
        require(all(isinstance(item, dict) and nonempty(item.get(key)) for item in items), reason)
        require(len({item[key] for item in items}) == len(items), reason)
        return {item[key]: item for item in items}

    root = root.resolve()
    require(plan.get('plan_schema_version') == 1, 'Unsupported completion/plan schema')
    require(data['repository'] == plan['repository'] and data['audit_source_commit'] == plan['source_commit'],
            'Completion belongs to another audit')

    def checked_file(ref, parent):
        relative = ref.get('path')
        require(nonempty(relative) and not Path(relative).is_absolute() and
                not PureWindowsPath(relative).drive and not PureWindowsPath(relative).root,
                'Artifact path must be relative')
        full = (parent / relative).resolve()
        require(root in full.parents and full.is_file(), 'Artifact escapes evidence root or missing')
        require(sha(ref.get('sha256')), 'Artifact SHA256 required')
        require(hashlib.sha256(full.read_bytes()).hexdigest() == ref['sha256'], 'Artifact hash changed')
        return full

    artifacts = {}
    for id, ref in unique_index(data['evidence'], 'id', 'Unique artifact IDs required').items():
        full = checked_file(ref, root)
        artifact = json.loads(full.read_text(encoding='utf-8'))
        require(isinstance(artifact, dict), 'Artifact must be a JSON object')
        if 'raw_artifacts' in artifact:
            raw = unique_index(artifact['raw_artifacts'], 'path', 'Unique raw artifact paths required')
            for raw_ref in raw.values():
                checked_file(raw_ref, full.parent)
        artifacts[id] = artifact

    def refs(ids, required=True):
        require(isinstance(ids, list) and (ids or not required) and
                all(nonempty(id) and id in artifacts for id in ids), 'Missing completion evidence')

    def revision_identity(revision):
        require(isinstance(revision, dict) and isinstance(revision.get('source_commit'), str) and
                re.fullmatch('[0-9a-f]{40}', revision['source_commit']), 'Tested commit required')
        require(revision.get('patch_sha256') is None or sha(revision['patch_sha256']), 'Invalid patch identity')

    def command(artifact):
        value = artifact.get('command')
        require(nonempty(value) or isinstance(value, list) and value and all(nonempty(x) for x in value),
                'Run command missing')
        require(type(artifact.get('exit_code')) is int and nonempty(artifact.get('status')), 'Run status/exit code required')
        require(artifact.get('raw_artifacts'), 'Raw run/selection artifacts required')

    def identity(artifact, revision):
        require(artifact.get('source_commit') == revision['source_commit'] and
                artifact.get('patch_sha256') == revision.get('patch_sha256'), 'Tested revision/patch differs from artifact')
        require(not artifact.get('dirty') or sha(artifact.get('patch_sha256')), 'Dirty run lacks actual patch identity')

    def run(id, revision):
        refs([id])
        artifact = artifacts[id]
        identity(artifact, revision)
        command(artifact)
        cases = unique_index(artifact['cases'], 'id', 'Run cases empty or duplicate')
        require(cases, 'Run cases empty or duplicate')
        require(all(c['outcome'] in {'passed', 'failed', 'error', 'skipped', 'xfailed'} for c in cases.values()),
                'Invalid run outcome')
        require(artifact.get('tested_sha', artifact['source_commit']) == artifact['source_commit'],
                'Run tested SHA differs from source commit')
        for case in cases.values():
            for key in ('run_id', 'job_id', 'attempt', 'tested_sha', 'source_identity', 'source_commit', 'patch_sha256'):
                if key not in case:
                    continue
                parent_key = 'source_commit' if key == 'tested_sha' else key
                require(parent_key in artifact and type(case[key]) is type(artifact[parent_key]) and
                        case[key] == artifact[parent_key], 'Case identity differs from parent run: ' + key)
        expected = dict(tests=len(cases), failed=sum(c['outcome'] == 'failed' for c in cases.values()),
                        errors=sum(c['outcome'] == 'error' for c in cases.values()),
                        skipped=sum(c['outcome'] in {'skipped', 'xfailed'} for c in cases.values()))
        require(artifact['counts'] == expected, 'Run counts disagree with cases')
        if artifact['status'] == 'pass':
            require(artifact['exit_code'] == 0 and not expected['failed'] and not expected['errors'],
                    'Passing run contradicts cases/exit code')
        return artifact, cases

    tasks = unique_index(plan['tasks'], 'id', 'Duplicate/incomplete planned task')
    planning = unique_index(plan['planning'], 'task_id', 'Duplicate/incomplete planned task')
    require(planning.keys() == tasks.keys(), 'Planning must retain exactly selected tasks')
    records = unique_index(data['tasks'], 'task_id', 'Duplicate/incomplete completion task')
    require(records.keys() == tasks.keys(), 'Completion must retain exactly selected tasks')
    validated = []
    for task_id, record in records.items():
        task = tasks[task_id]
        planned = unique_index(planning[task_id]['scenarios'], 'scenario_id', 'Duplicate/incomplete planned scenario')
        actual = unique_index(record['scenario_results'], 'scenario_id', 'Missing/duplicate/unplanned scenario')
        require(actual.keys() == planned.keys() and actual, 'Missing/duplicate/unplanned scenario')
        require(record['status'] in {'implemented_unverified', 'validated', 'blocked', 'needs_review'}, 'Invalid completion status')
        require(nonempty(record.get('validated_scope')), 'Bounded validation scope required')
        revision = record['tested_revision']
        revision_identity(revision)
        required = task.get('required_evidence', ['positive', 'negative_control', 'ci_selection'])
        require(isinstance(required, list) and all(kind in {'positive', 'negative_control', 'ci_selection', 'ci_execution'}
                                                 for kind in required), 'Unknown required evidence type')
        acceptance = unique_index(record['acceptance_results'], 'condition', 'Acceptance conditions missing, duplicated or rewritten')
        require(len(acceptance) == len(task['acceptance']) and acceptance.keys() == set(task['acceptance']),
                'Acceptance conditions missing, duplicated or rewritten')
        for result in acceptance.values():
            require(result['status'] in {'met', 'unmet', 'unknown'}, 'Invalid acceptance status')
            if result.get('evidence') is not None or result['status'] == 'met':
                refs(result.get('evidence'), required=result['status'] == 'met')
        methods = {}
        for scenario_id, scenario in actual.items():
            require(not {'test_id', 'covered_test_ids', 'outcome', 'evidence'} & scenario.keys(),
                    'V2 scenarios use tests only, not representative test fields')
            tests = scenario['tests']
            require(isinstance(tests, list) and tests and all(isinstance(t, dict) for t in tests), 'Scenario tests required')
            ids = [test.get('test_id') for test in tests]
            if None in ids:
                require(ids == [None], 'Unknown test must be the sole not_run placeholder')
            else:
                require(all(nonempty(id) for id in ids) and len(set(ids)) == len(ids), 'Duplicate/invalid scenario test ID')
            methods[scenario_id] = {test['test_id']: test for test in tests}
            for test in tests:
                require(test['outcome'] in {'passed', 'failed', 'error', 'skipped', 'xfailed', 'not_run'}, 'Invalid test outcome')
                if test['outcome'] == 'not_run':
                    require(test.get('evidence') is None and nonempty(test.get('reason')), 'Not-run test needs reason and null evidence')
                    continue
                require(nonempty(test['test_id']), 'Executed test ID required')
                artifact, cases = run(test['evidence'], revision)
                require(test['test_id'] in cases and cases[test['test_id']]['outcome'] == test['outcome'], 'Test result differs from run')
                if test['outcome'] == 'passed':
                    require(artifact['exit_code'] == 0 and artifact['status'] == 'pass', 'Positive evidence is not a passing run')
        controls = record.get('negative_controls', [])
        require(isinstance(controls, list), 'Negative controls must be a list')
        seen_controls = set()
        for control in controls:
            scenario_id, test_id = control['scenario_id'], control['test_id']
            require(scenario_id in methods and test_id in methods[scenario_id], 'Negative control targets a different scenario/test')
            baseline = methods[scenario_id][test_id]
            require(baseline['outcome'] == 'passed' and control['baseline_evidence'] == baseline['evidence'],
                    'Negative control baseline differs from passed positive test')
            require(nonempty(control.get('mutation')) and nonempty(control.get('target_assertion')), 'Negative control rationale required')
            key = (scenario_id, test_id, control['evidence'])
            require(key not in seen_controls, 'Duplicate negative control')
            seen_controls.add(key)
            mutated = control['tested_revision']
            revision_identity(mutated)
            require(mutated['source_commit'] == revision['source_commit'] and sha(mutated.get('patch_sha256')) and
                    mutated['patch_sha256'] != revision.get('patch_sha256'), 'Negative control needs isolated mutation identity')
            artifact, cases = run(control['evidence'], mutated)
            require(artifact['exit_code'] == 1 and artifact['status'] == 'test_failure', 'Negative control did not fail as a test')
            require(test_id in cases and cases[test_id]['outcome'] == 'failed' and control.get('failure_kind') == 'target_assertion',
                    'Import/setup/error failure is not a negative control')
        ci = {}
        for kind in ('ci_selection', 'ci_execution'):
            if record.get(kind) is None:
                continue
            refs([record[kind]])
            artifact = artifacts[record[kind]]
            identity(artifact, revision)
            command(artifact)
            require(artifact.get('lane') in task['lanes'], 'CI evidence has wrong lane')
            if kind == 'ci_selection':
                ids = artifact['selected_ids']
                require(isinstance(ids, list) and all(nonempty(id) for id in ids) and len(set(ids)) == len(ids), 'Invalid selected IDs')
                require(isinstance(artifact.get('unresolved_gates'), list), 'Selection gates must be a list')
                require(artifact['status'] != 'pass' or artifact['exit_code'] == 0, 'Passing selection has nonzero exit code')
                ci[kind] = artifact, set(ids)
            else:
                artifact, cases = run(record[kind], revision)
                require(artifact.get('run_id') and artifact.get('job_id') and type(artifact.get('attempt')) is int and
                        artifact['attempt'] > 0 and artifact.get('source_identity') == 'verified', 'Actual CI run identity missing')
                ci[kind] = artifact, cases
        if record['status'] != 'validated':
            continue
        require(not record.get('unresolved_prerequisites') and not plan.get('unselected_dependencies'), 'Unresolved prerequisites/dependencies')
        require(all(result['status'] == 'met' for result in acceptance.values()), 'Validated task has unmet acceptance')
        require(all(test['outcome'] == 'passed' for tests in methods.values() for test in tests.values()),
                'Validated task has unexecuted/failed tests')
        if 'negative_control' in required:
            require({control['scenario_id'] for control in controls} == planned.keys(), 'Negative controls do not cover planned scenarios')
        ids = {id for tests in methods.values() for id in tests}
        for kind in ('ci_selection', 'ci_execution'):
            if kind not in required:
                continue
            require(kind in ci, 'Required CI evidence missing')
            artifact, selected = ci[kind]
            if kind == 'ci_selection':
                require(artifact['status'] == 'pass' and artifact['exit_code'] == 0 and not artifact['unresolved_gates'] and ids <= selected,
                        'CI collection does not select all required cases successfully')
            else:
                require(artifact['status'] == 'pass' and artifact['exit_code'] == 0, 'Required CI execution is not a passing run')
                require(ids <= selected.keys() and all(selected[id]['outcome'] == 'passed' for id in ids), 'Required CI cases not passed')
        validated.append(task_id)
    return dict(status='evidence_consistent', validated_tasks=validated,
                limitation='Hashes and identities checked; oracle independence, assertion meaning, log authenticity and acceptance still require review. No gap auto-closed.')


def check(plan, data, root):
    if data.get('schema_version') == 2:
        return _check_v2(plan, data, root)
    return _check_v1(plan, data, root)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--completion', type=Path, required=True)
    a = p.parse_args()
    try:
        print(json.dumps(check(json.loads(a.plan.read_text(encoding='utf-8')),
                               json.loads(a.completion.read_text(encoding='utf-8')),
                               a.completion.resolve().parent), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps(dict(status='invalid_completion', reason=str(exc)), ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
