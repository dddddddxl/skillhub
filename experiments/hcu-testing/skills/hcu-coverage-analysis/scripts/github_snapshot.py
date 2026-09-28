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


def collect(repository,branch,since,max_pages=2,max_runs=10,max_prs=20,fetch=request,workflows=()):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Expected OWNER/REPO')
    prefix='/repos/'+repository
    workflows=list(dict.fromkeys(workflows))
    if len(workflows)>10 or any(not re.fullmatch(r'[A-Za-z0-9_.-]+',w) for w in workflows):
        raise ValueError('At most 10 workflow filenames or IDs required')
    branch_info,_=fetch(prefix+'/branches/'+urllib.parse.quote(branch,safe=''))
    query=urllib.parse.urlencode({'branch':branch,'created':'>='+since,'per_page':100})
    routes=[]
    def route(label,path):
        try:
            found,truncated=pages(path,'workflow_runs',max_pages,fetch)
            routes.append(dict(route=label,status='collected',truncated=truncated,candidate_ids=[r['id'] for r in found]))
            return found
        except (RuntimeError,KeyError):
            routes.append(dict(route=label,status='unavailable',truncated=None,candidate_ids=[]))
            return []
    branch_runs=route('target_branch',prefix+'/actions/runs?'+query)
    pr_status='collected'
    try:
        prs,pt=pages(prefix+'/pulls?'+urllib.parse.urlencode(dict(state='all',base=branch,sort='updated',direction='desc',per_page=100)),None,max_pages,fetch)
    except (RuntimeError,KeyError):
        prs,pt=[],False
        pr_status='unavailable'
    prs=[p for p in prs if p['updated_at']>=since]
    result=dict(repository='https://github.com/'+repository,branch=branch,source_commit=branch_info['commit']['sha'],
                observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),since=since,
                limitations=['Metadata only: read job logs/test artifacts to identify actual test IDs and checkout/wheel SHA.',
                              'Branch-filtered runs can miss default-branch or external dispatch targeting this branch.',
                              'All event types queried; jobs refer to latest attempt, prior attempts need separate inspection.'],
                truncated=dict(runs=False,prs=pt or len(prs)>max_prs),runs=[],prs=[],discovery_routes=routes,pr_discovery_status=pr_status)
    groups=[branch_runs]
    result['pr_candidates'] = [
        dict(id=str(pr['number']), url=pr.get('html_url'), title=pr.get('title'),
             updated_at=pr['updated_at'], base_branch=pr.get('base', {}).get('ref'),
             head_sha=pr.get('head', {}).get('sha'), review='not_reviewed',
             detail_status='selected' if i < max_prs else 'deferred_budget')
        for i, pr in enumerate(prs)]
    for pr in prs[:max_prs]:
        try:
            full,_=fetch(prefix+'/pulls/'+str(pr['number']))
        except (RuntimeError,KeyError):
            result.setdefault('unavailable_pr_details',[]).append(pr['number'])
            next(p for p in result['pr_candidates'] if p['id'] == str(pr['number']))['detail_status'] = 'unavailable'
            continue
        result['prs'].append(dict(id=str(full['number']),url=full['html_url'],title=full['title'],
            state='merged' if full.get('merged_at') else full['state'],updated_at=full['updated_at'],
            merged_at=full.get('merged_at'),base_branch=full['base']['ref'],base_sha=full['base']['sha'],
            head_sha=full['head']['sha'],merge_sha=full.get('merge_commit_sha'),
            diff_review='not_reviewed',in_target='unknown'))
        q=urllib.parse.urlencode(dict(head_sha=full['head']['sha'],created='>='+since,per_page=100))
        groups.append(route('pr_head:'+str(pr['number']),prefix+'/actions/runs?'+q))
    for index,workflow in enumerate(workflows):
        q=urllib.parse.urlencode(dict(created='>='+since,per_page=100))
        groups.insert(1+index,route('workflow:'+workflow,prefix+'/actions/workflows/'+workflow+'/runs?'+q))
    # Round-robin route sampling prevents a busy wheel-publishing branch from
    # consuming the whole detail budget before PR/nightly routes are inspected.
    candidates={}
    for i in range(max((len(g) for g in groups),default=0)):
        for group in groups:
            if i<len(group):candidates.setdefault(group[i]['id'],group[i])
    result['truncated']['runs']=any(r['truncated'] for r in routes) or len(candidates)>max_runs
    result['discovery_incomplete']=pr_status=='unavailable' or bool(result.get('unavailable_pr_details')) or any(r['status']=='unavailable' for r in routes)
    result['limitations']+=['PR-head matches and workflow-wide runs are candidates, not proof of target checkout; merge-ref and older PR heads may still be missing.',
        'Workflow routes have no branch filter. Inspect their checkout/input logs, including unrelated candidates; no external scheduler discovery is implied.',
        'Only max_runs candidates receive job/artifact detail, round-robin across routes; all candidate metadata and route bounds are retained.']
    selected=list(candidates)[:max_runs]
    result['run_candidates']=[dict(id=r['id'],head_sha=r.get('head_sha'),head_branch=r.get('head_branch'),event=r.get('event'),path=r.get('path'),html_url=r.get('html_url'),
        discovered_via=[x['route'] for x in routes if r['id'] in x['candidate_ids']],detail_status='selected' if r['id'] in selected else 'deferred_budget') for r in candidates.values()]
    for run in list(candidates.values())[:max_runs]:
        row={k:run.get(k) for k in ('id','name','event','head_branch','head_sha','run_attempt','status','conclusion','html_url','created_at','updated_at','path')}
        row['discovered_via']=[x['route'] for x in routes if run['id'] in x['candidate_ids']]
        row['truncated']={}
        for kind,fields in [('jobs',('id','name','status','conclusion','html_url','started_at','completed_at','steps')),
                            ('artifacts',('id','name','size_in_bytes','expired','created_at','workflow_run'))]:
            # A denied artifact endpoint must not discard readable job metadata.
            try:
                values,truncated=pages(prefix+'/actions/runs/'+str(run['id'])+'/'+kind+'?per_page=100',kind,max_pages,fetch)
                row[kind]=[{k:v.get(k) for k in fields} for v in values]
                row['truncated'][kind]=truncated
            except (RuntimeError,KeyError):
                row.setdefault('evidence_unavailable',[]).append(kind)
        result['runs'].append(row)
    result['detail_incomplete']=any(r.get('evidence_unavailable') or any(r['truncated'].values()) for r in result['runs'])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository',required=True);p.add_argument('--branch',required=True)
    p.add_argument('--since',required=True,help='UTC ISO timestamp, e.g. 2026-09-01T00:00:00Z')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--max-pages',type=int,default=2);p.add_argument('--max-runs',type=int,default=10);p.add_argument('--max-prs',type=int,default=20)
    p.add_argument('--workflow',action='append',default=[],help='Repeat reviewed workflow filenames/IDs to inspect across branches')
    a=p.parse_args()
    try:
        if not all(1<=n<=100 for n in (a.max_pages,a.max_runs,a.max_prs)) or a.output.exists():
            raise ValueError('Positive bounds <=100 and a new output path required')
        since=dt.datetime.fromisoformat(a.since.replace('Z','+00:00'))
        if since.tzinfo is None:
            raise ValueError('since requires timezone')
        canonical=since.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        result=collect(a.repository,a.branch,canonical,a.max_pages,a.max_runs,a.max_prs,workflows=a.workflow)
        with a.output.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps(dict(status='metadata_collected',runs=len(result['runs']),prs=len(result['prs']),truncated=result['truncated'],
            discovery_incomplete=result['discovery_incomplete'],detail_incomplete=result['detail_incomplete'])))
        return 0
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        print(json.dumps(dict(status='unavailable',reason=str(exc))))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
