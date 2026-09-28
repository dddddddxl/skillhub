"""Check a selected functional-audit handoff without sibling-skill dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def check(repo, backlog, selected):
    def git(*args):
        return subprocess.check_output(['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo), *args], text=True).strip()
    if backlog.get('schema_version') not in (1, 2) or backlog.get('source_commit') != git('rev-parse', 'HEAD') or git('status', '--porcelain'):
        raise ValueError('Unsupported/stale handoff or dirty checkout; refresh the audit')
    if not isinstance(backlog.get('source_fingerprints'), dict) or not backlog['source_fingerprints']:
        raise ValueError('Source fingerprints required')
    for path, expected in backlog['source_fingerprints'].items():
        full = (repo / path).resolve()
        if Path(path).is_absolute() or repo not in full.parents or not full.is_file() or hashlib.sha256(full.read_bytes()).hexdigest() != expected:
            raise ValueError('Changed or invalid source evidence: ' + path)
    tasks = {}
    for task in backlog['tasks']:
        if task['id'] in tasks or not task.get('cases') or not task.get('acceptance') or not task.get('prerequisites'):
            raise ValueError('Duplicate or incomplete task')
        if task.get('route') not in {'upstream_first', 'write', 'validate_existing', 'repair_selection', 'clarify_requirement'}:
            raise ValueError('Unknown task route')
        for case in task['cases']:
            if not all(isinstance(case.get(k), str) and case[k].strip() for k in ('name', 'inputs', 'expected', 'oracle', 'negative_control')):
                raise ValueError('Incomplete case contract')
        tasks[task['id']] = task
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= set(tasks):
        raise ValueError('Select unique existing task IDs explicitly')
    if backlog['schema_version'] == 2:
        target = backlog['target']
        if target['ref'] != 'refs/heads/' + target['branch'] or git('rev-parse', '--verify', target['ref']) != backlog['source_commit']:
            raise ValueError('Target branch moved; refresh audit')
        visiting, done = set(), set()
        def visit(id):
            if id not in tasks or id in visiting:
                raise ValueError('Unknown or cyclic task dependency')
            if id in done: return
            visiting.add(id)
            for dependency in tasks[id].get('depends_on', []): visit(dependency)
            visiting.remove(id); done.add(id)
        for id in tasks: visit(id)
    dependencies=set()
    def collect_dependencies(id, trail):
        if id in trail or id not in tasks:
            raise ValueError('Unknown or cyclic task dependency')
        for dep in tasks[id].get('depends_on', []):
            if dep not in dependencies:
                collect_dependencies(dep, trail | {id})
                dependencies.add(dep)
    for id in selected:collect_dependencies(id,set())
    actions={'clarify_requirement':'investigate_contract', 'validate_existing':'verify_existing',
             'repair_selection':'propose_ci_repair', 'upstream_first':'search_then_adapt_or_write', 'write':'design_then_write'}
    scenario_map, seen = {}, set()
    for id in selected:
        scenario_map[id] = []
        for i, case in enumerate(tasks[id]['cases']):
            sid = case.get('id', id + ':' + str(i + 1))
            if not isinstance(sid, str) or not sid.strip() or sid in seen:
                raise ValueError('Scenario IDs must be nonempty and unique across selected tasks')
            seen.add(sid)
            scenario_map[id].append(dict(case, scenario_id=sid,
                identity_mode='explicit' if 'id' in case else 'legacy_ordinal'))
    result = {'plan_schema_version': 1, 'status': 'ready_for_review', 'repository': backlog['repository'], 'source_commit': backlog['source_commit'],
            'platform': backlog['scope']['platform'], 'tasks': [tasks[x] for x in selected],
            'scope': backlog['scope'], 'source_fingerprints': backlog['source_fingerprints'],
            'evidence': backlog.get('evidence', []),
            'unselected_dependencies': sorted(dependencies-set(selected)),
            'planning': [{'task_id':id, 'next_action':actions[tasks[id]['route']],
                          'framework':'inspect_repository', 'test_location':'prefer_existing_test',
                          'scenarios':scenario_map[id]}
                         for id in selected],
            'authorization': 'No code, CI or execution changes authorized by this check'}
    for key in ('target','runtime','recent_prs','analysis'):
        if key in backlog:result[key]=backlog[key]
    return result


def save_plan(path,repo,result):
    path,repo=path.resolve(),repo.resolve()
    if path==repo or repo in path.parents:
        raise ValueError('Plan output must be outside the target checkout')
    with path.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--backlog', required=True, type=Path)
    p.add_argument('--task', action='append', required=True)
    p.add_argument('--output', type=Path, help='New plan JSON outside target checkout; never executes tests')
    a = p.parse_args()
    try:
        result=check(a.repo.resolve(), json.loads(a.backlog.read_text(encoding='utf-8')), a.task)
        if a.output:
            save_plan(a.output,a.repo,result)
            print(json.dumps(dict(status=result['status'],output=str(a.output.resolve()),selected_tasks=a.task),ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
