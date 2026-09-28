"""校验 PR 行为/CI 审查证据，渲染中文报告及兼容补测清单；不执行目标代码。"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def text(value):
    return isinstance(value, str) and bool(value.strip())


def safe_path(value):
    return (text(value) and '\\' not in value and ':' not in value and
            not PurePosixPath(value).is_absolute() and '..' not in PurePosixPath(value).parts)


def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo),
                                    *args], stderr=subprocess.PIPE)


def validate(repo, snapshot, analysis, evidence_root):
    repo, evidence_root = repo.resolve(), evidence_root.resolve()
    require(snapshot.get('snapshot_version') == 1 and analysis.get('review_version') == 1,
            '不支持的快照/审查版本')
    pr = snapshot['pr']
    for key in ('base_sha', 'head_sha'):
        require(re.fullmatch('[0-9a-f]{40}', pr[key]), '需要完整 base/head SHA')
    require(snapshot.get('capture_consistent') is True, 'PR 在采集中移动或复核失败，请重新采集')
    require(analysis.get('head_sha') == pr['head_sha'], '分析对应的 PR head 已过期')
    require(git(repo, 'rev-parse', 'HEAD').decode().strip() == pr['head_sha'] and
            not git(repo, 'status', '--porcelain').strip(), '请使用干净的 PR head 副本')
    diff_base = analysis.get('diff_base') or git(repo, 'merge-base', pr['base_sha'], pr['head_sha']).decode().strip()
    require(re.fullmatch('[0-9a-f]{40}', diff_base) and diff_base != pr['head_sha'],
            'diff 基线无效；合入后 base 可能已包含 head，请恢复原始 PR 基线')
    if analysis.get('diff_base'):
        require(text(analysis.get('diff_base_reason')), '显式 diff 基线需要说明来源')
    git(repo, 'merge-base', '--is-ancestor', diff_base, pr['head_sha'])
    changed = set(git(repo, 'diff', '--name-only', '-z', '--no-renames', diff_base, pr['head_sha'], '--').decode('utf-8').strip('\0').split('\0'))
    require('' not in changed, '未取得有效 PR diff')
    if snapshot.get('files_complete'):
        api_paths = {f['filename'] for f in snapshot['files']}
        api_paths.update(f['previous_filename'] for f in snapshot['files'] if f.get('previous_filename'))
        require(changed == api_paths, '本地 diff 文件集合与 GitHub PR 不一致；检查原始 base/head')
    evidence, fingerprints = {}, {}
    for item in analysis['evidence']:
        item = dict(item)
        require(text(item.get('id')) and item['id'] not in evidence and text(item.get('claim')), '证据 ID/说明无效或重复')
        require(safe_path(item.get('path')), '证据路径必须为相对路径且不能逃逸')
        if item['kind'] == 'source':
            require(item['revision'] in {pr['head_sha'], pr['base_sha'], diff_base}, '源码证据 revision 不属于 PR 基线/head')
            tree = git(repo, 'ls-tree', item['revision'], '--', item['path']).decode()
            require(tree.startswith(('100644 blob ', '100755 blob ')), '源码证据必须为普通 Git 文件')
            raw = git(repo, 'show', item['revision'] + ':' + item['path'])
            lines = raw.decode('utf-8').splitlines()
            require(isinstance(item.get('start'), int) and isinstance(item.get('end'), int) and
                    1 <= item['start'] <= item['end'] <= len(lines), '源码证据行号越界')
            if item['revision'] == pr['head_sha']:
                full = (repo / item['path']).resolve()
                require(repo in full.parents and full.is_file(), 'head 工作文件缺失/逃逸')
                fingerprints[item['path']] = digest(full.read_bytes())
        elif item['kind'] == 'artifact':
            full = (evidence_root / item['path']).resolve()
            require(evidence_root in full.parents and full.is_file(), '工件必须位于审查输入目录之内')
            raw = full.read_bytes()
        else:
            raise ValueError('未知证据类型')
        item['sha256'] = digest(raw)
        evidence[item['id']] = item
    def refs(ids):
        require(isinstance(ids, list) and ids and set(ids) <= set(evidence), '证据引用缺失或未知')
    def source_refs(ids, path=None):
        refs(ids)
        require(any(evidence[e]['kind'] == 'source' and evidence[e]['revision'] == pr['head_sha']
                    and (path is None or evidence[e]['path'] == path) for e in ids), '缺少匹配 head 文件的源码证据')
    files = analysis['files']
    require(len({f['path'] for f in files}) == len(files) and {f['path'] for f in files} == changed,
            '每个 PR 变更文件必须记录已审/待审/排除，不能用样本代表整个 PR')
    for f in files:
        require(f['status'] in {'reviewed', 'deferred', 'excluded'} and text(f['reason']), '文件审查状态/理由无效')
    observations = {}
    jobs = {(str(r['id']), r['run_attempt'], str(j['id'])): (r, j)
            for r in snapshot['runs'] for j in r.get('jobs', [])}
    for o in analysis.get('observations', []):
        require(o['id'] not in observations, '运行观测 ID 重复')
        refs(o['evidence'])
        require(o.get('identity') == 'verified' and text(o.get('identity_reason')), '逐测例运行需要已核验 checkout/build 身份说明')
        require(o['tested_sha'] == pr['head_sha'], '本模式逐测例通过只接受 PR head；合并提交证据单列，不回填 head')
        key = (str(o['run_id']), o['attempt'], str(o['job_id']))
        require(key in jobs, '观测的 run/job/attempt 不在快照中；补采该 attempt 后复核')
        require(jobs[key][1]['status'] == 'completed', '未完成 job 不能作为已完成执行证据')
        # Logs/results must exist as artifacts, not a source filename or PR body claim.
        require(any(evidence[e]['kind'] == 'artifact' for e in o['evidence']), '需要真实执行日志/结果工件')
        cases = o['cases']
        require(cases and len({(c['path'], c['id']) for c in cases}) == len(cases), '测例身份重复或为空')
        require(all(safe_path(c['path']) and text(c['id']) and c['outcome'] in {'passed', 'failed', 'error', 'skipped', 'xfailed'} for c in cases), '测例结果无效')
        observations[o['id']] = o
    behaviors = {}
    for b in analysis['behaviors']:
        require(text(b['id']) and b['id'] not in behaviors, '行为 ID 无效或重复')
        require(b['changed_paths'] and set(b['changed_paths']) <= changed, '行为必须关联本 PR 改动')
        require(all(text(b.get(k)) for k in ('name', 'before', 'after', 'trigger', 'risk', 'oracle', 'counterevidence')), '行为缺少改前/改后、触发条件、oracle 或替代覆盖检索说明')
        source_refs(b['evidence'])
        require(b['design'] in {'supported', 'partial', 'gap', 'unknown'}, '未知设计覆盖状态')
        require(b['selection'] in {'included', 'excluded', 'conditional', 'unknown'}, '未知选择状态')
        refs(b['selection_evidence'])
        require(text(b.get('selection_reason')), '选择状态必须解释实际 gate/matrix/selector')
        tests = b['tests']
        require(len({(t['path'], t['id']) for t in tests}) == len(tests), '重复测试映射')
        for t in tests:
            require(safe_path(t['path']) and text(t['id']) and text(t['assertion']), '测试映射必须包含 ID 与具体断言')
            source_refs(t['evidence'], t['path'])
        require(b['design'] != 'supported' or tests, '没有已读断言不能声明设计支持')
        outcomes = []
        attempts = {}
        for oid in b.get('observations', []):
            require(oid in observations, '未知执行观测')
            o = observations[oid]
            run_key = str(o['run_id'])
            require(not attempts or run_key in attempts,
                    '同一行为不能拼接多个 run 的通过子集；按单次运行或更细行为分别报告')
            require(run_key not in attempts or attempts[run_key] == o['attempt'],
                    '同一行为不能拼接同一个 run 的多个 attempt；选定一次完整执行')
            attempts[run_key] = o['attempt']
            require(o['lane'] == b['lane'] and o['platform'] == b['platform'], '测例执行 lane/platform 不匹配')
            outcomes.extend(c for c in o['cases'] if (c['path'], c['id']) in {(t['path'], t['id']) for t in tests})
        # Conservative all-required cases; do not hide a failed rerun in a passing subset.
        execution = 'not_verified'
        if any(c['outcome'] in {'failed', 'error'} for c in outcomes):
            execution = 'failed'
        elif any(c['outcome'] in {'skipped', 'xfailed'} for c in outcomes):
            execution = 'skipped'
        elif tests and {(c['path'], c['id']) for c in outcomes} == {(t['path'], t['id']) for t in tests}:
            require(b['selection'] == 'included', '未被选中的场景不能声明在此 lane 通过')
            execution = 'passed'
        if 'execution' in b:
            require(b['execution'] == execution, '执行结论与逐测例证据不一致')
        behaviors[b['id']] = dict(b, execution=execution)
    require(behaviors, '至少审阅一个 PR 行为')
    for f in files:
        if f['status'] == 'reviewed':
            require(any(f['path'] in b['changed_paths'] for b in behaviors.values()), '已审文件缺少行为映射')
    findings = analysis['findings']
    require(len({f['id'] for f in findings}) == len(findings), '发现 ID 重复')
    for f in findings:
        require(f['kind'] in {'coverage_gap', 'selection_gap', 'test_failure', 'infrastructure_failure', 'evidence_gap'}, '未知 finding 类型')
        require(f['severity'] in {'P0', 'P1', 'P2'} and f['confidence'] in {'high', 'medium', 'low'}, '优先级/置信度无效')
        require(all(text(f.get(k)) for k in ('title', 'impact', 'recommendation')), '发现缺少影响或建议')
        require(f['behavior_ids'] and set(f['behavior_ids']) <= set(behaviors), '发现未关联 PR 行为')
        refs(f['evidence'])
        if f['kind'] == 'coverage_gap':
            require(any(behaviors[x]['design'] in {'partial', 'gap'} for x in f['behavior_ids']), '证据未知不能自动判为缺测例')
        if f['kind'] == 'selection_gap':
            require(any(behaviors[x]['selection'] in {'excluded', 'conditional'} for x in f['behavior_ids']), '选择证据未知不能自动判为CI漏选')
        if f['kind'] == 'test_failure':
            require(any(behaviors[x]['execution'] == 'failed' for x in f['behavior_ids']), '元数据红灯不能冒充产品测试失败')
        if f['kind'] == 'infrastructure_failure':
            require(any(evidence[x]['kind'] == 'artifact' for x in f['evidence']), '环境失败必须附实际日志工件；仅红灯应标为证据缺口')
    for b in behaviors.values():
        if b['design'] != 'supported' or b['selection'] != 'included' or b['execution'] != 'passed':
            require(any(b['id'] in f['behavior_ids'] for f in findings), '未完成覆盖/选择/执行的行为需要明确跟进项')
    tasks = [dict(t) for t in analysis.get('tasks', [])]
    require(len({t['id'] for t in tasks}) == len(tasks), '补测任务 ID 重复')
    case_ids = set()
    for t in tasks:
        require(t['feature_id'] in behaviors and t['route'] in {'write', 'upstream_first', 'validate_existing', 'repair_selection', 'clarify_requirement'}, '任务路由无效')
        require(isinstance(t['cases'], list) and t['cases'], '补测任务需要场景数组')
        for field in ('acceptance', 'prerequisites'):
            require(isinstance(t[field], list) and t[field] and all(text(x) for x in t[field]),
                    '补测任务的验收/前置条件必须为非空字符串数组')
        t.setdefault('lanes', [behaviors[t['feature_id']]['lane']])
        require(isinstance(t['lanes'], list) and t['lanes'] and all(text(x) for x in t['lanes']), '任务需要有效 lanes')
        default_required = ['positive', 'negative_control', 'ci_selection', 'ci_execution']
        t.setdefault('required_evidence', default_required)
        require(isinstance(t['required_evidence'], list) and t['required_evidence'] and
                set(t['required_evidence']) <= set(default_required), '任务验收证据类型无效')
        if set(t['required_evidence']) != set(default_required):
            require(text(t.get('required_evidence_reason')), '缩小PR补测验收证据范围需要说明理由')
        require(t['priority'] in {'P0', 'P1', 'P2'} and text(t['reason']), '任务优先级/理由无效')
        refs(t['evidence'])
        for c in t['cases']:
            require(all(text(c.get(k)) for k in ('id', 'name', 'inputs', 'expected', 'oracle', 'negative_control')), '任务缺少稳定场景 ID/测试合同')
            require(c['id'] not in case_ids, '任务场景 ID 重复')
            case_ids.add(c['id'])
    require(text(analysis.get('summary')) and isinstance(analysis.get('limitations'), list) and
            all(text(x) for x in analysis['limitations']), '需要中文摘要与审查限制字符串数组')
    incomplete = (not snapshot.get('files_complete') or any(f['status'] == 'deferred' for f in files) or
                  snapshot.get('run_details_truncated') or
                  any(e['status'] != 'available' or e.get('truncated') for e in snapshot['endpoints'].values()))
    verdict = 'needs_evidence'
    if any(f['kind'] in {'coverage_gap', 'selection_gap', 'test_failure', 'infrastructure_failure'} for f in findings):
        verdict = 'changes_recommended'
    elif not incomplete and all(b['design'] == 'supported' and b['selection'] == 'included' and b['execution'] == 'passed' for b in behaviors.values()):
        verdict = 'no_material_gaps_found'
    result = dict(review_version=1, repository=snapshot['repository'], pr=pr, diff_base=diff_base,
                  captured_at=snapshot['captured_at'], verdict=verdict, evidence_incomplete=incomplete,
                  summary=analysis['summary'], files=files, behaviors=list(behaviors.values()), findings=findings,
                  observations=list(observations.values()), evidence=list(evidence.values()), tasks=tasks,
                  ci=dict(checks=snapshot['checks'], statuses=snapshot['statuses'], runs=snapshot['runs'], endpoints=snapshot['endpoints']),
                  limitations=analysis['limitations'] + snapshot.get('limitations', []))
    context = dict(number=pr['number'], url=pr['url'], base_sha=pr['base_sha'], head_sha=pr['head_sha'],
                   diff_base=diff_base, head_repository=pr.get('head_repository'), captured_at=snapshot['captured_at'])
    backlog = dict(schema_version=1, origin_mode='pr_ci_review', repository=snapshot['repository'],
                   source_commit=pr['head_sha'], pr_context=context,
                   scope=dict(platform=analysis['platform'], extent='bounded', lanes=sorted({b['lane'] for b in behaviors.values()}),
                              limitations=result['limitations']), tasks=tasks, evidence=list(evidence.values()),
                   source_fingerprints=fingerprints)
    return result, backlog


LABELS = {'supported': '断言支持', 'partial': '部分', 'gap': '缺口', 'unknown': '未知',
          'included': '选中', 'excluded': '未选中', 'conditional': '条件选择',
          'not_verified': '未核验', 'passed': '已核验通过', 'failed': '失败', 'skipped': '跳过',
          'changes_recommended': '建议补充或修正测试/CI', 'needs_evidence': '需要补充证据',
          'no_material_gaps_found': '已审范围内未发现实质缺口', 'reviewed': '已审', 'deferred': '待审',
          'success': '成功', 'failure': '失败', 'cancelled': '取消', 'completed': '完成',
          'in_progress': '运行中', 'queued': '排队中', 'pr_head': 'PR head 元数据匹配',
          'merge_candidate': '合并提交候选（单列）', 'high': '高', 'medium': '中', 'low': '低'}


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', '<br>')


def render(d):
    pr = d['pr']
    lines = ['# PR CI 审查报告', '', '[%s #%s](%s)' % (d['repository'], pr['number'], pr['url']),
             '', '- PR 标题：' + pr['title'], '- 目标分支：`' + pr['base_branch'] + '`',
             '- Diff base：`' + d['diff_base'] + '`', '- PR head：`' + pr['head_sha'] + '`',
             '- 采集时间：' + d['captured_at'], '- 审查结论：' + LABELS[d['verdict']],
             '- 合并门禁：未作自动批准；分支规则与管理员策略由调用方核对。',
             '', d['summary'], '', '## 审查范围', '',
             '| 变更文件 | 状态 | 理由 |', '|---|---|---|']
    for f in d['files']:
        lines.append('| %s | %s | %s |' % (cell(f['path']), LABELS[f['status']], cell(f['reason'])))
    lines += ['', '## CI 运行元数据', '', '| Run / attempt | Workflow / 事件 | 版本关系 | Job | 状态 |', '|---|---|---|---|---|']
    if not d['ci']['runs']:
        lines.append('| 未取得 | — | — | — | 未知；不能据此认定从未运行 |')
    for r in d['ci']['runs']:
        for j in r['jobs'] or [dict(name='未取得 job 明细', conclusion=None, status=r['status'])]:
            lines.append('| [%s](%s) / %s | %s / %s | %s | %s | %s |' % (
                r['id'], r['html_url'], r['run_attempt'], cell(r['name']), r['event'],
                LABELS[r['relation']], cell(j['name']), LABELS.get(j['conclusion'] or j['status'], j['conclusion'] or j['status'])))
    lines += ['', 'Checks / 外部 status 记录：%s / %s；完整身份、历史及接口可见性见 review.json。' % (len(d['ci']['checks']), len(d['ci']['statuses'])),
              '', '绿色 job 仅表示 job 状态；具体行为通过须由对应版本、平台、lane、test ID 的结果证明。',
              '', '## PR 行为与测试', '', '| ID / 行为 | 改前 → 改后 | 必测触发条件 | 断言设计 | CI 选择 | 具体行为执行 |', '|---|---|---|---|---|---|']
    for b in d['behaviors']:
        lines.append('| %s / %s | %s → %s | %s | %s | %s | %s |' % (
            b['id'], cell(b['name']), cell(b['before']), cell(b['after']), cell(b['trigger']),
            LABELS[b['design']], LABELS[b['selection']], LABELS[b['execution']]))
    lines += ['', '代码行/分支/内核覆盖率：未测量。上述状态是已审行为结论，不是全仓覆盖百分比。', '', '## 审查意见', '']
    for f in sorted(d['findings'], key=lambda f: (f['severity'], f['id'])):
        lines += ['### [%s] %s · %s' % (f['severity'], f['title'], f['id']), '',
                  '- 类型：' + f['kind'] + '；置信度：' + LABELS[f['confidence']],
                  '- 影响：' + f['impact'], '- 建议：' + f['recommendation'],
                  '- 证据：' + ', '.join(f['evidence']), '']
    lines += ['## 补测交接', '', '| 任务 | 行为 | 路由 | 场景 ID |', '|---|---|---|---|']
    for t in d['tasks']:
        lines.append('| %s | %s | %s | %s |' % (t['id'], t['feature_id'], t['route'], ', '.join(c['id'] for c in t['cases'])))
    if not d['tasks']:
        lines.append('| 无代码补测任务 | — | 先补证据或澄清需求 | — |')
    lines += ['', '## 限制与待核实', ''] + ['- ' + x for x in d['limitations']]
    lines += ['', '## 证据索引', '']
    for e in d['evidence']:
        location = (e.get('revision', '')[:12] + ' ' + e['path'] +
                    (':%s–%s' % (e['start'], e['end']) if e['kind'] == 'source' else ''))
        lines.append('- %s：`%s` — %s；SHA256 `%s`' % (e['id'], location.strip(), e['claim'], e['sha256']))
    lines += ['', '校验验证版本、引用和记录一致性；行为判断与日志身份仍须人工/agent 复核。', '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'snapshot', 'input', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    try:
        repo, out = a.repo.resolve(), a.output.resolve()
        require(not out.exists() and out != repo and repo not in out.parents, '输出须为 checkout 外的新目录')
        snapshot = json.loads(a.snapshot.read_text(encoding='utf-8'))
        analysis = json.loads(a.input.read_text(encoding='utf-8'))
        review, backlog = validate(repo, snapshot, analysis, a.input.parent)
        review['snapshot_sha256'] = digest(a.snapshot.read_bytes())
        backlog['pr_context']['snapshot_sha256'] = review['snapshot_sha256']
        out.mkdir(parents=True)
        for name, data in [('review.json', review), ('test-backlog.json', backlog)]:
            (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        (out / 'report.md').write_text(render(review), encoding='utf-8')
        print(json.dumps(dict(status='review_validated', verdict=review['verdict'],
                              files=len(review['files']), behaviors=len(review['behaviors']), tasks=len(backlog['tasks'])), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='invalid_review', reason=str(exc)), ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
