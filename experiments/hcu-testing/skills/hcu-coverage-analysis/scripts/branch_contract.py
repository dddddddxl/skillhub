"""V2 branch/runtime/PR invariants. Source semantics still require review."""
import collections
import datetime as dt
from pathlib import PurePosixPath
import re


def validate_v2(d, repo, refs, runs, git, require):
    def string(x):
        return isinstance(x, str) and bool(x.strip())
    def sha(x):
        return isinstance(x, str) and re.fullmatch(r'[0-9a-f]{40}', x)
    target = d['target']
    require(string(target.get('branch')) and target.get('ref') == 'refs/heads/' + target['branch'], 'Exact local branch ref required')
    require(git(repo, 'rev-parse', '--verify', target['ref']).strip() == d['source_commit'], 'Branch tip differs from audited snapshot')
    tasks = {t['id']: t for t in d['tasks']}
    def follow(ids, needed=False):
        require(isinstance(ids, list) and len(ids) == len(set(ids)) and set(ids) <= tasks.keys(), 'Invalid shared followups')
        require(not needed or bool(ids), 'Missing shared followup')
    for task in tasks.values():
        follow(task.get('depends_on', []))
    done, visiting = set(), set()
    def visit(id):
        require(id not in visiting, 'Cyclic task dependencies')
        if id in done:
            return
        visiting.add(id)
        for dep in tasks[id].get('depends_on', []):
            visit(dep)
        visiting.remove(id)
        done.add(id)
    for id in tasks:
        visit(id)
    runtime = d['runtime']
    require(runtime['status'] in {'observed', 'partial', 'unavailable'} and string(runtime['reason']), 'Runtime inventory status/reason required')
    follow(runtime.get('followups', []), runtime['status'] != 'observed')
    ids = runtime['evidence']
    require(isinstance(ids, list) and len(ids) == len(set(ids)) and set(ids) <= runs.keys(), 'Runtime references must be run artifacts')
    require(runtime['status'] != 'observed' or bool(ids), 'Observed inventory needs artifacts')
    observed = []
    identities = set()
    for id in ids:
        run = runs[id]
        for key in ('repository', 'branch', 'lane', 'platform', 'source_locator', 'run_id', 'job_id'):
            require(string(run.get(key)), 'Run missing ' + key)
        require(sha(run.get('source_commit')), 'Run checkout SHA required')
        require(run['source_commit'] == refs[id]['source_commit'] and run['platform'] == refs[id]['platform'], 'Run metadata differs from evidence')
        require(type(run.get('attempt')) is int and run['attempt'] > 0, 'Run attempt required')
        require(run.get('source_identity') in {'verified', 'unresolved'}, 'Run source identity required')
        require(run.get('granularity') in {'case', 'file'}, 'Run granularity required')
        identity = (run['repository'], run['run_id'], run['job_id'], run['attempt'])
        require(identity not in identities, 'Duplicate job attempt artifacts')
        identities.add(identity)
        cases = run['cases']
        require(isinstance(cases, list), 'Observed cases required')
        case_ids = set()
        for case in cases:
            require(string(case.get('id')) and case['id'] not in case_ids, 'Unique observed IDs required')
            case_ids.add(case['id'])
            path = case.get('path', '')
            require(string(path) and '\\' not in path and ':' not in path and not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts, 'Invalid observed relative path')
            require(case['outcome'] in {'passed', 'failed', 'error', 'skipped', 'xfailed', 'running', 'blocked'}, 'Invalid case outcome')
        counts = run['counts']
        expected = dict(tests=len(cases), failed=sum(c['outcome'] == 'failed' for c in cases),
                        errors=sum(c['outcome'] == 'error' for c in cases),
                        skipped=sum(c['outcome'] in {'skipped', 'xfailed'} for c in cases))
        require(all(type(counts.get(k)) is int and counts[k] == v for k,v in expected.items()), 'Counts do not match observed records')
        require(run.get('status') in {'pass', 'test_failure', 'execution_failure', 'no_tests_executed', 'environment_blocked', 'timeout', 'running'}, 'Invalid run status')
        if run['status'] == 'pass':
            require(any(c['outcome'] == 'passed' for c in cases) and all(c['outcome'] in {'passed','skipped','xfailed'} for c in cases), 'Passing artifact has no pass or has failures/unresolved cases')
        current = (run['repository'] == d['repository'] and run['branch'] == target['branch'] and
                   run['platform'] == d['scope']['platform'] and run['source_commit'] == d['source_commit'] and run['source_identity'] == 'verified')
        observed.append(dict(evidence=id, sha256=refs[id]['sha256'], current_identity=current, **run))
    d['observed_tests'] = observed
    features = {f['id']:f for f in d['features']}
    for f in features.values():
        finding = f['finding']
        require(finding['kind'] in {'confirmed_gap','risk','improvement','unknown','supported'} and finding['confidence'] in {'high','medium','low'}, 'Finding classification required')
        require(string(finding['rationale']) and string(finding['counterevidence']), 'Finding needs rationale and counterevidence')
        for lane, cell in f['lanes'].items():
            require(cell['scheduling'] in {'verified','conditional','unknown','not_applicable'}, 'Scheduling axis required')
            needs = (cell['coverage'] in {'partial','gap','unknown'} or cell['selection'] in {'excluded','disabled','conditional','unknown'} or cell['scheduling'] in {'conditional','unknown'})
            follow(cell['followups'], needs)
            observations = cell.get('observations', [])
            require(isinstance(observations, list), 'Observation list required')
            selected = []
            for obs in observations:
                require(obs['evidence'] in ids and obs['evidence'] in cell['evidence'], 'Observation not referenced by cell/runtime')
                run = next(r for r in observed if r['evidence'] == obs['evidence'])
                require(run['current_identity'] and run['lane'] == lane, 'Observation has wrong branch/SHA/platform/repository/lane or unresolved build')
                cases = {c['id']:c for c in run['cases']}
                require(obs['case_ids'] and len(set(obs['case_ids'])) == len(obs['case_ids']) and set(obs['case_ids']) <= cases.keys(), 'Unknown observed test IDs')
                chosen = [cases[id] for id in obs['case_ids']]
                require(all(c['path'] in {t['path'] for t in f['tests']} for c in chosen), 'Observation belongs to another feature test')
                if cell['execution'] == 'passed':
                    require(run['granularity'] == 'case', 'File-only pass cannot establish specific behavior execution')
                    require(all(any(c['path'] == t['path'] and c['id'] in t.get('case_ids', []) for t in f['tests']) for c in chosen), 'Passing case ID not mapped to this behavior assertion')
                selected += chosen
            if cell['execution'] != 'not_verified':
                require(bool(selected), 'Execution requires test observations')
                outcomes = {c['outcome'] for c in selected}
                acceptable = {'passed': outcomes == {'passed'}, 'failed': bool(outcomes & {'failed','error'}),
                              'skipped': outcomes <= {'skipped','xfailed'}, 'blocked': bool(outcomes & {'blocked'})}
                require(acceptable.get(cell['execution'], False), 'Observed outcomes do not support execution claim')
                if cell['execution'] == 'passed':
                    require(cell['selection'] == 'included' and cell['scheduling'] == 'verified', 'Pass requires current selected/scheduled lane')
    prs = d['recent_prs']
    require(string(prs['since']) and string(prs['until']) and prs['status'] in {'reviewed','partial','unavailable'} and string(prs['reason']), 'PR window/status required')
    def timestamp(value):
        parsed = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed
    require(timestamp(prs['since']) <= timestamp(prs['until']), 'Invalid PR time window')
    follow(prs.get('followups', []), prs['status'] != 'reviewed')
    changes, pr_ids = {}, set()
    for pr in prs['items']:
        require(string(pr['id']) and pr['id'] not in pr_ids and string(pr['url']), 'Unique PR ID/URL required')
        pr_ids.add(pr['id'])
        require(pr['base_branch'] == target['branch'] and sha(pr['base_sha']) and sha(pr['head_sha']), 'PR target/ref mismatch')
        require(pr['state'] in {'open','merged','closed'} and pr['in_target'] in {'yes','no','unknown'}, 'Invalid PR state/inclusion')
        require(pr['state'] != 'open' or pr['in_target'] != 'yes', 'Open PR cannot be treated as landed')
        require(pr['review'] in {'reviewed','deferred','excluded'} and string(pr['reason']), 'PR review rationale required')
        follow(pr.get('followups', []), pr['review'] == 'deferred')
        require(pr['review'] != 'reviewed' or bool(pr['changes']), 'Reviewed PR needs behavior changes')
        require(prs['status'] != 'reviewed' or pr['review'] != 'deferred', 'PR scope includes deferred reviews')
        for change in pr.get('changes', []):
            require(string(change['id']) and change['id'] not in changes and string(change['description']), 'Unique behavior change required')
            require(change['feature_ids'] and set(change['feature_ids']) <= features.keys(), 'Change needs feature mapping')
            require(change['coverage'] in {'supported','partial','gap','unknown'}, 'Invalid PR coverage')
            require(change['evidence'] and set(change['evidence']) <= refs.keys(), 'Change evidence required')
            follow(change['followups'], change['coverage'] != 'supported')
            changes[change['id']] = change
    for f in features.values():
        require(isinstance(f['change_ids'], list) and set(f['change_ids']) <= changes.keys(), 'Dangling feature change IDs')
        for id in f['change_ids']:
            require(f['id'] in changes[id]['feature_ids'], 'Inconsistent PR/feature mapping')
    for id,change in changes.items():
        require(all(id in features[f]['change_ids'] for f in change['feature_ids']), 'Missing reverse PR mapping')


def overview(d):
    def esc(s):
        return str(s).replace('|','\\|').replace('\n',' ')
    lines=['# 分支测试缺口审计 v2','',f"分支：`{d['target']['branch']}`；SHA：`{d['source_commit']}`",'',
           '## 实际 CI 观察（不是配置文件数）','',d['runtime']['status']+'：'+d['runtime']['reason'],'',
           '| Run / Job / Attempt | 分支 / SHA | 通道 | 粒度 | 已通过 / 失败 / 跳过 | 当前身份 |','|---|---|---|---|---|---|']
    for r in d['observed_tests']:
        c=r['counts']
        passed=sum(x['outcome']=='passed' for x in r['cases'])
        vals=[f"{r['run_id']}/{r['job_id']}/{r['attempt']}",r['branch']+' / '+r['source_commit'],r['lane'],r['granularity'],f"{passed} / {c['failed']+c['errors']} / {c['skipped']}",r['current_identity']]
        lines.append('| '+' | '.join(map(esc,vals))+' |')
    if not d['observed_tests']:
        lines+=['','没有可核验测试 ID 的 CI 工件；实际跑了哪些仍未知。']
    lines+=['','## 四个独立维度','','| 功能 | lane | 断言设计 | 有效选择 | 分支调度 | 实际执行 | 分类 / 置信 | 后续任务 |','|---|---|---|---|---|---|---|---|']
    for f in d['features']:
        for lane,c in f['lanes'].items():
            vals=[f['id'],lane,c['coverage'],c['selection'],c['scheduling'],c['execution'],f['finding']['kind']+'/'+f['finding']['confidence'],','.join(c['followups'])]
            lines.append('| '+' | '.join(map(esc,vals))+' |')
    lines+=['','## 近期 PR 行为覆盖','',d['recent_prs']['since']+' → '+d['recent_prs']['until']+'；'+d['recent_prs']['status']+'：'+d['recent_prs']['reason'],'',
            '| PR | 状态 / 已进入目标 | 行为变化 | 功能 | 设计覆盖 | 任务 |','|---|---|---|---|---|---|']
    changes=[]
    for pr in d['recent_prs']['items']:
        for c in pr.get('changes',[]):
            changes.append(c)
            lines.append('| '+' | '.join(map(esc,[pr['id'],pr['state']+'/'+pr['in_target'],c['description'],','.join(c['feature_ids']),c['coverage'],','.join(c['followups'])]))+' |')
        if not pr.get('changes'):
            lines.append('| '+' | '.join(map(esc,[pr['id'],pr['state']+'/'+pr['in_target'],pr['review']+': '+pr['reason'],'—','unknown',','.join(pr.get('followups',[]))]))+' |')
    counts=collections.Counter(c['coverage'] for c in changes)
    lines+=['',f"本轮业务合同数：{len(d['features'])}；审阅 PR 行为变化数：{len(changes)}；变化覆盖计数：{dict(counts)}。",'代码行/分支覆盖率：本报告未计算；仅独立、同 SHA 的仪器化工件可以支持该百分比。','',
            '## 反证复核','']
    for f in d['features']:
        lines.append('- '+f['id']+'：'+f['finding']['rationale']+'；反证/边界：'+f['finding']['counterevidence'])
    lines+=['','以下保留详细源证据和任务；v2 的 supported 仅指断言设计，不要求选择/调度已证实。','']
    return '\n'.join(lines)
