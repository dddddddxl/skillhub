"""Validate traceable review records, not the truth of agent-authored business claims."""
from collections import Counter


def validate(d, refs, require):
    a = d.get('analysis')
    if a is None:
        require(d['scope'].get('analysis_depth') != 'behavior', 'Behavior review needs analysis records')
        return
    require(d['schema_version'] == 2 and a.get('schema_version') == 1, 'Analysis requires v2 audit / v1 analysis')
    features = {f['id']: f for f in d['features']}
    tasks = {t['id']: t for t in d['tasks']}
    lanes = set(d['scope']['lanes'])
    def string(x):
        return isinstance(x, str) and bool(x.strip())
    def evidence(ids):
        require(isinstance(ids, list) and ids and all(x in refs for x in ids), 'Analysis evidence missing')
        require(any(refs[x]['kind'] == 'source' for x in ids), 'Analysis requires source evidence')
    inventory, seen, mapped = a['feature_inventory'], set(), set()
    require(isinstance(inventory, list) and inventory, 'Feature denominator ledger required')
    for row in inventory:
        require(string(row.get('id')) and row['id'] not in seen and string(row.get('name')), 'Unique inventory ID/name required')
        seen.add(row['id'])
        require(row['status'] in {'reviewed', 'deferred', 'excluded', 'unknown'}, 'Invalid inventory status')
        require(row['basis'] in {'documented', 'inferred', 'unsupported', 'unknown'} and string(row['reason']), 'Feature basis/reason required')
        evidence(row['evidence'])
        require(isinstance(row['feature_ids'], list) and set(row['feature_ids']) <= features.keys(), 'Inventory maps unknown features')
        require(row['status'] != 'reviewed' or bool(row['feature_ids']), 'Reviewed inventory needs behavior contracts')
        require(row['status'] != 'excluded' or not row['feature_ids'], 'Excluded inventory cannot claim reviewed coverage')
        follow = row['followups']
        require(isinstance(follow, list) and set(follow) <= tasks.keys(), 'Unknown inventory followup')
        require(row['status'] not in {'deferred', 'unknown'} or bool(follow), 'Unreviewed feature needs followup')
        mapped.update(row['feature_ids'])
    require(mapped == features.keys(), 'Reviewed features missing from denominator ledger')
    if d['scope']['extent'] == 'repository_reviewed':
        require(all(r['status'] in {'reviewed', 'excluded'} for r in inventory), 'Repository review still has unreviewed inventory')
    scenarios = {}
    require(isinstance(a['scenarios'], list) and a['scenarios'], 'Behavior scenarios required')
    for s in a['scenarios']:
        require(string(s.get('id')) and s['id'] not in scenarios and s['feature_id'] in features, 'Unique scenario ID / feature required')
        require(all(string(s.get(k)) for k in ('inputs', 'expected', 'oracle', 'failure_mode')), 'Scenario contract incomplete')
        require(s['status'] in {'supported', 'gap', 'unknown'}, 'Invalid scenario assertion status')
        require(s['lanes'] and set(s['lanes']) <= lanes, 'Scenario lane mismatch')
        evidence(s['evidence'])
        f = features[s['feature_id']]
        mapped_tests = {(t['path'], c) for t in f['tests'] for c in t.get('case_ids', [])}
        require(isinstance(s['tests'], list), 'Scenario tests must be a list')
        for t in s['tests']:
            require((t['path'], t['id']) in mapped_tests and string(t.get('assertion')), 'Scenario test/assertion not mapped to feature')
            evidence(t['evidence'])
            require(any(refs[e]['kind'] == 'source' and refs[e]['path'] == t['path'] for e in t['evidence']), 'Assertion needs own test source')
        require(s['status'] != 'supported' or bool(s['tests']), 'Supported scenario needs assertion mapping')
        follow = s['followups']
        require(isinstance(follow, list) and set(follow) <= tasks.keys(), 'Invalid scenario followup')
        require(s['status'] == 'supported' or bool(follow), 'Uncovered scenario needs followup')
        if s['status'] != 'supported':
            require(any(any(c.get('id') == s['id'] for c in tasks[t]['cases']) for t in follow),
                    'Gap scenario ID must reach authoring backlog unchanged')
        scenarios[s['id']] = s
    for fid, f in features.items():
        for lane, cell in f['lanes'].items():
            relevant = [s for s in scenarios.values() if s['feature_id'] == fid and lane in s['lanes']]
            require(relevant or cell['coverage'] == 'not_applicable', 'Feature lane needs explicit behavior scenarios')
            if cell['coverage'] == 'supported':
                require(all(s['status'] == 'supported' for s in relevant), 'Supported feature has uncovered scenarios')
            if cell['execution'] == 'passed' and cell.get('execution_requirements') is not None:
                for s in relevant:
                    keys = {(t['path'], t['id']) for t in s['tests']}
                    require(keys and any({(c['path'], c['id']) for c in g['cases']} <= keys
                                         for g in cell['execution_requirements']),
                            'Execution requirements omit a required behavior scenario')
    changes = {c['id']: c for p in d['recent_prs']['items'] for c in p.get('changes', [])}
    seen = set()
    for impact in a['pr_impacts']:
        cid = impact['change_id']
        require(cid in changes and cid not in seen, 'Unique known PR behavior impact required')
        seen.add(cid)
        require(all(string(impact.get(k)) for k in ('before', 'after', 'trigger', 'risk', 'exclusions')), 'PR before/after/trigger/risk/exclusions required')
        evidence(impact['evidence'])
        for field in ('entrypoints', 'callers', 'backend_paths'):
            require(isinstance(impact[field], list) and impact[field] and all(string(x) for x in impact[field]), 'PR impact needs ' + field)
        ids = impact['scenario_ids']
        require(ids and set(ids) <= scenarios.keys(), 'PR impact scenarios missing')
        require(all(scenarios[s]['feature_id'] in changes[cid]['feature_ids'] for s in ids), 'PR impact maps unrelated behavior')
        if changes[cid]['coverage'] == 'supported':
            require(all(scenarios[s]['status'] == 'supported' for s in ids), 'Supported PR has uncovered scenarios')
    require(seen == changes.keys(), 'PR behavior changes missing impact review')
    a['summary'] = dict(inventory=dict(Counter(r['status'] for r in inventory)),
                        scenarios=dict(Counter(s['status'] for s in scenarios.values())),
                        pr_impacts=len(seen), scope='Reviewed ledger only; not whole-repository coverage percentage')


def markdown(d):
    a = d.get('analysis')
    if not a:
        return '\n行为深审：旧报告未提供功能分母台账和场景追踪，不能据此声称已完成深审。\n'
    def esc(v):
        return str(v).replace('|', '\\|').replace('\n', ' ')
    lines = ['## 功能分母台账', '', '| 候选功能 | 依据 | 审阅状态 | 行为合同 | 原因 |', '|---|---|---|---|---|']
    for r in a['feature_inventory']:
        lines.append('| ' + ' | '.join(map(esc, [r['id'] + ' ' + r['name'], r['basis'], r['status'], ','.join(r['feature_ids']), r['reason']])) + ' |')
    lines += ['', '## 行为场景追踪', '', '| 场景 / 功能 | 通道 | 输入 | 预期 / oracle | 可检出错误 | 断言状态 | 测例 |', '|---|---|---|---|---|---|---|']
    for s in a['scenarios']:
        lines.append('| ' + ' | '.join(map(esc, [s['id'] + '/' + s['feature_id'], ','.join(s['lanes']), s['inputs'], s['expected'] + ' / ' + s['oracle'], s['failure_mode'], s['status'], ','.join(t['id'] for t in s['tests'])])) + ' |')
    lines += ['', '## PR 行为影响链', '', '| 变更 | 之前 → 之后 | 触发条件 | 入口 / 调用方 / 后端 | 必测场景 | 排除项与理由 |', '|---|---|---|---|---|---|']
    for p in a['pr_impacts']:
        lines.append('| ' + ' | '.join(map(esc, [p['change_id'], p['before'] + ' → ' + p['after'], p['trigger'], ';'.join(p['entrypoints'] + p['callers'] + p['backend_paths']), ','.join(p['scenario_ids']), p['exclusions']])) + ' |')
    return '\n'.join(lines) + '\n'
