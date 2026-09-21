"""Index source candidates and render evidence-backed functional audit handoffs.

Standard library only. This validates agent-authored mappings, not semantics.
It never imports tests, executes CI commands, or infers features from filenames.
"""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SELECTION = {'included', 'conditional', 'excluded', 'disabled', 'unknown', 'not_applicable'}
COVERAGE = {'supported', 'partial', 'gap', 'unknown', 'not_applicable'}
EXECUTION = {'not_verified', 'passed', 'failed', 'skipped', 'blocked'}
ROUTES = {'upstream_first', 'write', 'validate_existing', 'repair_selection', 'clarify_requirement'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo), *args], text=True)


def inside(root, path):
    require(text(path) and not Path(path).is_absolute(), 'Evidence path must be relative')
    full = (root / path).resolve()
    require(root in full.parents and full.is_file(), 'Missing or escaping file: ' + path)
    return full


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(repo):
    paths = git(repo, 'ls-files', '-z').split('\0')
    result = dict(source_commit=git(repo, 'rev-parse', 'HEAD').strip(), dirty=bool(git(repo, 'status', '--porcelain')),
                  scope='Tracked lexical candidates only; not feature or effective CI coverage', workflows=[], tests=[], documents=[])
    for path in filter(None, paths):
        p = Path(path)
        parts = {x.lower() for x in p.parts}
        name = p.name.lower()
        group = None
        if path.startswith('.github/workflows/') or name in {'jenkinsfile', '.gitlab-ci.yml', 'azure-pipelines.yml'}:
            group = 'workflows'
        elif parts & {'test', 'tests', 'testing'} or name.startswith('test_') or name.endswith(('_test.py', '_test.cc', '_test.cpp')):
            group = 'tests'
        elif p.suffix.lower() in {'.md', '.rst'}:
            group = 'documents'
        if group:
            full = (repo / path).resolve()
            if repo in full.parents and full.is_file():
                result[group].append({'path': path, 'sha256': digest(full)})
    return result


def validate(data, repo, evidence_root):
    data = copy.deepcopy(data)
    require(data.get('schema_version') in (1, 2), 'Unsupported schema')
    v2 = data['schema_version'] == 2
    require(text(data.get('repository')), 'Repository is required')
    require(data.get('source_commit') == git(repo, 'rev-parse', 'HEAD').strip(), 'Source commit mismatch')
    require(not git(repo, 'status', '--porcelain').strip(), 'Dirty checkout: refresh isolated audit snapshot')
    scope = data['scope']
    require(text(scope.get('platform')) and text(scope.get('feature_basis')), 'Scope platform and feature basis required')
    lanes = scope['lanes']
    require(isinstance(lanes, list) and lanes and all(text(x) for x in lanes) and len(set(lanes)) == len(lanes), 'Unique lanes required')
    require(scope.get('extent') in {'bounded', 'repository_reviewed'}, 'Invalid scope extent')
    require(isinstance(scope.get('limitations'), list) and all(text(x) for x in scope['limitations']), 'Limitations must be a list')
    require(scope['extent'] != 'bounded' or bool(scope['limitations']), 'Bounded audit must state limitations')
    refs, fingerprints, runs = {}, {}, {}
    for ref in data['evidence']:
        require(text(ref.get('id')) and ref['id'] not in refs and text(ref.get('claim')), 'Unique evidence ID and claim required')
        require(ref['kind'] in ({'source', 'run', 'artifact'} if v2 else {'source', 'run'}), 'Invalid evidence kind')
        full = inside(repo if ref['kind'] == 'source' else evidence_root, ref['path'])
        ref['sha256'] = digest(full)
        if ref['kind'] == 'source':
            length = len(full.read_text(encoding='utf-8').splitlines())
            require(type(ref.get('start')) is int and type(ref.get('end')) is int and 1 <= ref['start'] <= ref['end'] <= length,
                    'Invalid source line range: ' + ref['id'])
            fingerprints[ref['path']] = ref['sha256']
        elif ref['kind'] == 'run':
            require(text(ref.get('source_commit')) and text(ref.get('platform')), 'Run provenance required')
            try:
                payload = json.loads(full.read_text(encoding='utf-8'))
                runs[ref['id']] = payload if isinstance(payload, dict) else {}
            except (ValueError, UnicodeError):
                runs[ref['id']] = {}
        refs[ref['id']] = ref

    def references(ids, source=False):
        require(isinstance(ids, list) and ids and all(x in refs for x in ids), 'Missing/dangling evidence reference')
        if source:
            require(any(refs[x]['kind'] == 'source' for x in ids), 'Source evidence required')

    features = {}
    needs_task = set()
    def matches_run(id, state):
        ref, run = refs[id], runs.get(id, {})
        statuses = {'passed': {'pass'}, 'failed': {'test_failure', 'execution_failure'},
                    'skipped': {'no_tests_executed'}, 'blocked': {'environment_blocked', 'timeout'}}
        if (ref['kind'] != 'run' or ref.get('source_commit') != data['source_commit'] or ref.get('platform') != scope['platform'] or
                run.get('source_commit') != data['source_commit'] or run.get('status') not in statuses[state]):
            return False
        if state == 'passed':
            c = run.get('counts', {})
            return (isinstance(c, dict) and all(type(c.get(k, 0)) is int for k in ('tests', 'skipped', 'failed', 'errors')) and
                    0 <= c.get('skipped', 0) < c.get('tests', 0) and c.get('failed', 0) == c.get('errors', 0) == 0)
        return True
    for feature in data['features']:
        fid = feature['id']
        require(text(fid) and fid not in features and text(feature.get('name')) and text(feature.get('requirement')), 'Unique feature and behavior contract required')
        references(feature['evidence'], source=True)
        require(isinstance(feature['tests'], list), 'Tests must be a list')
        for test in feature['tests']:
            inside(repo, test['path'])
            references(test['evidence'], source=True)
            require(any(refs[x]['kind'] == 'source' and refs[x]['path'] == test['path'] for x in test['evidence']), 'Test needs evidence from its own file')
            require(test['assertion_kind'] in {'smoke', 'behavior', 'numerical', 'error', 'performance', 'unknown'} and text(test.get('assertion')), 'Assertion review required')
        require(set(feature['lanes']) == set(lanes), 'Every feature must assess every declared lane')
        for lane, cell in feature['lanes'].items():
            require(cell['selection'] in SELECTION and cell['coverage'] in COVERAGE and cell['execution'] in EXECUTION, 'Invalid matrix state')
            require(text(cell.get('reason')), 'Matrix rationale required')
            references(cell['evidence'], source=True)
            if cell['coverage'] == 'supported':
                require((v2 or cell['selection'] == 'included') and bool(feature['tests']) and all(t['assertion_kind'] != 'unknown' for t in feature['tests']),
                        'Supported design requires included tests and reviewed assertions')
            if cell['coverage'] == 'not_applicable':
                require(cell['selection'] == 'not_applicable', 'Not-applicable states must agree')
            if cell['execution'] != 'not_verified' and not v2:
                require(any(matches_run(x, cell['execution']) for x in cell['evidence']), 'Execution claim needs matching structured run evidence and counts')
            if cell['execution'] == 'passed':
                require(cell['selection'] == 'included', 'Passed lane cannot be excluded, disabled or unresolved')
            if cell['coverage'] in {'partial', 'gap', 'unknown'}:
                needs_task.add((fid, lane))
        features[fid] = feature
    require(bool(features), 'No reviewed features')
    task_ids, addressed = set(), set()
    for task in data['tasks']:
        require(text(task.get('id')) and task['id'] not in task_ids, 'Duplicate/empty task ID')
        task_ids.add(task['id'])
        require(task['feature_id'] in features and task['priority'] in {'P0', 'P1', 'P2'} and task['route'] in ROUTES, 'Invalid task routing')
        require(task['lanes'] and set(task['lanes']) <= set(lanes) and text(task.get('reason')), 'Task lanes and rationale required')
        references(task['evidence'], source=True)
        for field in ('prerequisites', 'acceptance', 'search'):
            require(isinstance(task[field], list) and task[field] and all(text(x) for x in task[field]), 'Task requires ' + field)
        require(isinstance(task['cases'], list) and task['cases'], 'Concrete scenarios required')
        for case in task['cases']:
            require(all(text(case.get(k)) for k in ('name', 'inputs', 'expected', 'oracle', 'negative_control')), 'Case needs inputs, expectation, oracle and negative control')
        addressed.update((task['feature_id'], lane) for lane in task['lanes'])
    if not v2:
        require(needs_task <= addressed, 'Unaddressed gap/unknown matrix cells: ' + str(sorted(needs_task - addressed)))
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from branch_contract import validate_v2
        validate_v2(data, repo, refs, runs, git, require)
    data['source_fingerprints'] = fingerprints
    data['validation_scope'] = 'References, hashes and structural consistency checked; semantic judgments are agent-authored'
    return data


def markdown(data):
    def esc(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    scope = data['scope']
    if data['schema_version'] == 2:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from branch_contract import overview
        # Keep the legacy detailed source/assertion/backlog tables, prefixed by
        # independent axes and actual observation/PR matrices.
        old = copy.deepcopy(data)
        old['schema_version'] = 1
        return overview(data) + '\n' + markdown(old)
    lines = ['# 功能测试覆盖审计', '', f"仓库：{data['repository']}", f"版本：`{data['source_commit']}`", '',
             f"范围：{scope['extent']}；平台：{scope['platform']}", '功能分母依据：' + scope['feature_basis'], '',
             '本报告区分静态设计覆盖与实际执行证据；不提供推测的全仓功能覆盖率。', '', '## 限制与未知', '']
    lines += ['- ' + x for x in scope['limitations']] or ['- 未另列限制；这不代表穷尽所有功能组合。']
    lines += ['', '## 功能 × 测试通道', '', '| 功能 / 行为 | 通道 | 选择状态 | 设计覆盖 | 执行证据 | 依据 |', '|---|---|---|---|---|---|']
    for feature in data['features']:
        for lane, cell in feature['lanes'].items():
            lines.append('| ' + ' | '.join(map(esc, [feature['id'] + ' ' + feature['requirement'], lane, cell['selection'], cell['coverage'], cell['execution'], cell['reason'] + ' [' + ', '.join(cell['evidence']) + ']'])) + ' |')
    counts = collections.Counter(c['coverage'] for f in data['features'] for c in f['lanes'].values())
    lines += ['', '设计覆盖：supported=限定行为有断言支撑；partial=部分覆盖；gap=已确认缺口；unknown=证据不足；not_applicable=不属该通道合同。',
              '执行证据：not_verified=未核验实际运行；静态 supported 不等于执行通过。', '',
              '矩阵单元统计（仅限上述范围，不是功能覆盖百分比）：' + json.dumps(dict(counts), ensure_ascii=False),
              '', '## 已有测例与断言范围', '', '| 功能 | 测例 | 断言类型 | 实际检查范围 |', '|---|---|---|---|']
    for feature in data['features']:
        for test in feature['tests']:
            lines.append('| ' + ' | '.join(map(esc, [feature['id'], test['path'], test['assertion_kind'], test['assertion']])) + ' |')
    lines += ['', '## 补测与修复任务', '']
    for task in sorted(data['tasks'], key=lambda x: (x['priority'], x['id'])):
        lines += [f"### {task['id']} · {task['priority']} · {task['route']}", '', task['reason'], '',
                  f"关联：{task['feature_id']}；通道：{', '.join(task['lanes'])}", '', '前置条件：' + '; '.join(task['prerequisites']), '',
                  '| 场景 | 输入 | 预期 | 判定依据 | 反向验证 |', '|---|---|---|---|---|']
        for case in task['cases']:
            lines.append('| ' + ' | '.join(esc(case[k]) for k in ('name', 'inputs', 'expected', 'oracle', 'negative_control')) + ' |')
        lines += ['', '验收：' + '; '.join(task['acceptance']), '检索方向：' + '; '.join(task['search']), '证据：' + ', '.join(task['evidence']), '']
    lines += ['## 证据索引', '']
    for ref in data['evidence']:
        suffix = f":{ref['start']}-{ref['end']}" if ref['kind'] == 'source' else ' (' + ref['kind'] + ' artifact)'
        lines += [f"- {ref['id']}: `{ref['path']}{suffix}` — {ref['claim']}；SHA256 `{ref['sha256']}`"]
    lines += ['', '交接：test-backlog.json。由下一个 Skill 核对版本并选择任务，不自动执行、启用 CI 或发布。', '', data['validation_scope'], '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['inventory', 'render'])
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    try:
        repo, out = a.repo.resolve(), a.output.resolve()
        require(repo != out and repo not in out.parents, 'Output must be outside checkout')
        if a.mode == 'inventory':
            result = inventory(repo)
            with out.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
        else:
            require(a.input is not None, 'Render requires --input')
            result = validate(json.loads(a.input.read_text(encoding='utf-8')), repo, a.input.resolve().parent)
            out.mkdir(parents=True, exist_ok=False)
            (out / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            backlog = {k: result[k] for k in ('schema_version', 'repository', 'source_commit', 'scope', 'tasks', 'evidence', 'source_fingerprints')}
            if result['schema_version'] == 2:
                for key in ('target', 'runtime', 'recent_prs'):
                    backlog[key] = result[key]
                (out / 'observed-tests.json').write_text(json.dumps(result['observed_tests'], ensure_ascii=False, indent=2), encoding='utf-8')
                (out / 'pr-change-matrix.json').write_text(json.dumps(result['recent_prs'], ensure_ascii=False, indent=2), encoding='utf-8')
            (out / 'test-backlog.json').write_text(json.dumps(backlog, ensure_ascii=False, indent=2), encoding='utf-8')
            (out / 'report.md').write_text(markdown(result), encoding='utf-8')
        print(json.dumps({'status': 'valid', 'mode': a.mode, 'output': str(out)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'status': 'invalid_audit', 'reason': str(exc)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
