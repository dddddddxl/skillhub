"""Read-only GitHub branch, CI jobs/artifacts and recent PR metadata discovery.

No logs/test payloads or credentials are persisted. Metadata is NOT test execution
evidence. Defaults bound cost and explicitly report truncation.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'


def request(path):
    url = API + path if path.startswith('/') else path
    if not url.startswith(API + '/'):
        raise ValueError('Unexpected API pagination origin')
    headers = {'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'hcu-branch-audit'}
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization']='Bearer '+token
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=30) as response:
            return json.load(response),response.headers.get('Link','')
    except urllib.error.HTTPError as exc:
        raise RuntimeError('GitHub HTTP '+str(exc.code)+'; access/rate-limit evidence unavailable') from None
    except urllib.error.URLError:
        raise RuntimeError('GitHub connection unavailable') from None


def pages(path,key,max_pages,fetch=request):
    items=[]
    for _ in range(max_pages):
        payload,links=fetch(path)
        items.extend(payload if key is None else payload[key])
        match=re.search(r'<([^>]+)>; rel="next"',links)
        if not match:
            return items,False
        path=match.group(1)
    return items,True


def collect(repository,branch,since,max_pages=2,max_runs=10,max_prs=20,fetch=request):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Expected OWNER/REPO')
    prefix='/repos/'+repository
    branch_info,_=fetch(prefix+'/branches/'+urllib.parse.quote(branch,safe=''))
    query=urllib.parse.urlencode({'branch':branch,'created':'>='+since,'per_page':100})
    runs,rt=pages(prefix+'/actions/runs?'+query,'workflow_runs',max_pages,fetch)
    prs,pt=pages(prefix+'/pulls?'+urllib.parse.urlencode(dict(state='all',base=branch,sort='updated',direction='desc',per_page=100)),None,max_pages,fetch)
    prs=[p for p in prs if p['updated_at']>=since]
    result=dict(repository='https://github.com/'+repository,branch=branch,source_commit=branch_info['commit']['sha'],
                observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),since=since,
                limitations=['Metadata only: read job logs/test artifacts to identify actual test IDs and checkout/wheel SHA.',
                              'Branch-filtered runs can miss default-branch or external dispatch targeting this branch.',
                              'All event types queried; jobs refer to latest attempt, prior attempts need separate inspection.'],
                truncated=dict(runs=rt or len(runs)>max_runs,prs=pt or len(prs)>max_prs),runs=[],prs=[])
    for run in runs[:max_runs]:
        row={k:run.get(k) for k in ('id','name','event','head_branch','head_sha','run_attempt','status','conclusion','html_url','created_at','updated_at','path')}
        try:
            jobs,jt=pages(prefix+'/actions/runs/'+str(run['id'])+'/jobs?per_page=100','jobs',max_pages,fetch)
            artifacts,at=pages(prefix+'/actions/runs/'+str(run['id'])+'/artifacts?per_page=100','artifacts',max_pages,fetch)
            row['jobs']=[{k:j.get(k) for k in ('id','name','status','conclusion','html_url','started_at','completed_at','steps')} for j in jobs]
            row['artifacts']=[{k:a.get(k) for k in ('id','name','size_in_bytes','expired','created_at','workflow_run')} for a in artifacts]
            row['truncated']=dict(jobs=jt,artifacts=at)
        except (RuntimeError,KeyError) as exc:
            row['evidence_unavailable']=str(exc)
        result['runs'].append(row)
    for pr in prs[:max_prs]:
        # Pull detail is necessary: merge_commit_sha on an open PR is not a
        # landed merge, and list payloads alone don't establish merged_at.
        full,_=fetch(prefix+'/pulls/'+str(pr['number']))
        result['prs'].append(dict(id=str(full['number']),url=full['html_url'],title=full['title'],
            state='merged' if full.get('merged_at') else full['state'],updated_at=full['updated_at'],
            merged_at=full.get('merged_at'),base_branch=full['base']['ref'],base_sha=full['base']['sha'],
            head_sha=full['head']['sha'],merge_sha=full.get('merge_commit_sha'),
            diff_review='not_reviewed',in_target='unknown'))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository',required=True);p.add_argument('--branch',required=True)
    p.add_argument('--since',required=True,help='UTC ISO timestamp, e.g. 2026-09-01T00:00:00Z')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--max-pages',type=int,default=2);p.add_argument('--max-runs',type=int,default=10);p.add_argument('--max-prs',type=int,default=20)
    a=p.parse_args()
    try:
        if not all(1<=n<=100 for n in (a.max_pages,a.max_runs,a.max_prs)) or a.output.exists():
            raise ValueError('Positive bounds <=100 and a new output path required')
        since=dt.datetime.fromisoformat(a.since.replace('Z','+00:00'))
        if since.tzinfo is None:
            raise ValueError('since requires timezone')
        canonical=since.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        result=collect(a.repository,a.branch,canonical,a.max_pages,a.max_runs,a.max_prs)
        with a.output.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps(dict(status='metadata_collected',runs=len(result['runs']),prs=len(result['prs']),truncated=result['truncated'])))
        return 0
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        print(json.dumps(dict(status='unavailable',reason=str(exc))))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
