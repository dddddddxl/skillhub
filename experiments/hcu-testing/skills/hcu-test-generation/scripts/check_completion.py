"""核对补测完成记录及工件身份；只检查证据一致性，不自动关闭缺口。"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def check(plan, data, root):
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
