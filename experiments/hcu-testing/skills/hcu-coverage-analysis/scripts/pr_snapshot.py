"""只读采集单个 GitHub PR 的 CI 元数据；不运行 PR 代码、不下载日志。"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request
import urllib.error

API = 'https://api.github.com'


def client(use_git_credential=False):
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token and use_git_credential:
        result = subprocess.run(
            ['git', '-c', 'credential.interactive=false', 'credential', 'fill'],
            input='protocol=https\nhost=github.com\n\n', text=True,
            capture_output=True, timeout=20,
            env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
        if result.returncode:
            raise ValueError('GitHub 已有凭据不可用；未启动交互登录')
        token = dict(line.split('=', 1) for line in result.stdout.splitlines()
                     if '=' in line).get('password')
    def fetch(path):
        url = API + path if path.startswith('/') else path
        if not url.startswith(API + '/'):
            raise ValueError('分页 URL 必须属于 GitHub API')
        headers = {'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'hcu-pr-ci-review'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.load(r), r.headers.get('Link', '')
        except urllib.error.HTTPError as e:
            raise RuntimeError('GitHub HTTP %s；未读取到该接口证据' % e.code) from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError('GitHub 网络不可用') from None
    return fetch


def collect(repository, number, fetch, max_pages=2, max_runs=8):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or number < 1:
        raise ValueError('需要 OWNER/REPO 和正整数 PR 编号')
    prefix = '/repos/' + repository
    pr, _ = fetch(prefix + '/pulls/' + str(number))
    result = dict(snapshot_version=1, repository='https://github.com/' + repository,
                  captured_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                  pr=dict(number=number, url=pr['html_url'], title=pr['title'],
                          state='merged' if pr.get('merged_at') else pr['state'],
                          base_branch=pr['base']['ref'], base_sha=pr['base']['sha'],
                          head_sha=pr['head']['sha'], merge_sha=pr.get('merge_commit_sha'),
                          head_repository=pr['head']['repo']['full_name'] if pr['head'].get('repo') else None),
                  endpoints={}, runs=[], checks=[], statuses=[], files=[])
    def get(label, route, key=None, paged=True):
        values, next_route = [], route
        try:
            for _ in range(max_pages if paged else 1):
                body, link = fetch(next_route)
                if not paged:
                    result['endpoints'][label] = dict(status='available', url=API + route, truncated=False)
                    return body
                batch = body if key is None else body[key]
                if not isinstance(batch, list):
                    raise ValueError('列表接口返回类型不符')
                values.extend(batch)
                match = re.search(r'<([^>]+)>; rel="next"', link)
                if not match:
                    break
                next_route = match.group(1)
            result['endpoints'][label] = dict(status='available', url=API + route,
                                             truncated=bool(match))
        except (RuntimeError, KeyError, ValueError) as exc:
            result['endpoints'][label] = dict(status='unavailable', url=API + route,
                                             truncated=True, reason=str(exc))
            if not paged:
                return None
        return values
    files = get('files', prefix + '/pulls/%s/files?per_page=100' % number)
    result['files'] = [{k: f.get(k) for k in ('filename', 'previous_filename', 'status', 'additions', 'deletions', 'patch')}
                       for f in files]
    result['files_complete'] = (len(files) == pr.get('changed_files') and
                               result['endpoints']['files']['status'] == 'available' and
                               not result['endpoints']['files']['truncated'])
    head = result['pr']['head_sha']
    checks = get('head_checks', prefix + '/commits/' + head + '/check-runs?per_page=100&filter=all', 'check_runs')
    result['checks'] = [dict(id=c['id'], name=c['name'], head_sha=c['head_sha'], status=c['status'],
                             conclusion=c.get('conclusion'), url=c.get('html_url'),
                             app_id=c.get('app', {}).get('id'), started_at=c.get('started_at'),
                             completed_at=c.get('completed_at')) for c in checks]
    statuses = get('head_statuses', prefix + '/commits/' + head + '/statuses?per_page=100')
    result['statuses'] = [dict(id=s['id'], context=s['context'], state=s['state'], sha=head,
                               url=s.get('target_url'), created_at=s['created_at']) for s in statuses]
    candidates = {}
    for relation, sha in [('pr_head', head), ('merge_candidate', result['pr']['merge_sha'])]:
        if not sha or (relation == 'merge_candidate' and sha == head):
            continue
        query = urllib.parse.urlencode(dict(head_sha=sha, per_page=100))
        for run in get(relation + '_runs', prefix + '/actions/runs?' + query, 'workflow_runs'):
            candidates.setdefault(run['id'], dict(run, relation=relation))
    result['run_details_truncated'] = len(candidates) > max_runs
    # Preserve every discovered candidate even when detailed job pages are budgeted.
    for index, run in enumerate(candidates.values()):
        row = {k: run.get(k) for k in ('id', 'name', 'event', 'head_sha', 'head_branch', 'path',
                                      'status', 'conclusion', 'run_attempt', 'html_url', 'created_at')}
        row['relation'] = run['relation']
        row['jobs'] = []
        row['detail_status'] = 'deferred_budget'
        if index < max_runs:
            attempt = run['run_attempt']
            route = prefix + '/actions/runs/%s/attempts/%s/jobs?per_page=100' % (run['id'], attempt)
            jobs = get('jobs:%s:%s' % (run['id'], attempt), route, 'jobs')
            row['jobs'] = [{k: j.get(k) for k in ('id', 'name', 'status', 'conclusion', 'html_url', 'steps')}
                           for j in jobs]
            row['detail_status'] = result['endpoints']['jobs:%s:%s' % (run['id'], attempt)]['status']
        result['runs'].append(row)
    branch = urllib.parse.quote(pr['base']['ref'], safe='')
    result['required_status_checks'] = get('legacy_protection', prefix + '/branches/' + branch +
                                           '/protection/required_status_checks', paged=False)
    result['branch_rules'] = get('branch_rules', prefix + '/rules/branches/' + branch)
    # No polling loop: detect a moving PR and ask the caller to capture a new snapshot.
    end = get('pr_recheck', prefix + '/pulls/' + str(number), paged=False)
    result['capture_consistent'] = bool(end and end['head']['sha'] == head and
                                       end['base']['sha'] == result['pr']['base_sha'] and
                                       end.get('merge_commit_sha') == result['pr']['merge_sha'])
    result['limitations'] = [
        '元数据不证明测试源码、安装 wheel 或具体测例实际执行；需要 job 日志及逐测试结果。',
        'head/merge SHA 查询可能遗漏 pull_request_target、workflow_dispatch 和外部调度；按 workflow、PR checks 链接及调度系统补查。',
        '合并提交上的 push/release 构建属于合入后证据，不能回填为 PR head 的测试通过。',
        'checks 保留重跑记录，statuses 保留历史；分析时核对最新 attempt、同名 check 的 app 身份和时间。',
        '权限不足、404、分页预算用未知表示，不推断门禁不存在。']
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository', required=True)
    p.add_argument('--pr', required=True, type=int)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--max-pages', type=int, default=2)
    p.add_argument('--max-runs', type=int, default=8)
    p.add_argument('--git-credential', action='store_true', help='使用已有 GitHub Git 凭据；不打印或保存凭据')
    a = p.parse_args()
    try:
        if a.output.exists() or not (1 <= a.max_pages <= 20 and 1 <= a.max_runs <= 50):
            raise ValueError('输出须为新文件；max-pages 1..20，max-runs 1..50')
        data = collect(a.repository, a.pr, client(a.git_credential), a.max_pages, a.max_runs)
        with a.output.open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(json.dumps(dict(status='captured', consistent=data['capture_consistent'],
                              files_complete=data['files_complete'], runs=len(data['runs'])), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='unavailable', reason=str(exc)), ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
