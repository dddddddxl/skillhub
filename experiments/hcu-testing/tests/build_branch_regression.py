"""Migrate an explicitly supplied reviewed v1 audit to an honest v2 regression.

No CI artifacts or PR reviews are fabricated; missing discovery stays unknown.
This fixture checks reporting mechanics, not a fresh semantic repository audit.
"""
import argparse
import copy
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--branch',required=True)
    a=p.parse_args()
    d=json.loads(a.input.read_text(encoding='utf-8'))
    d.update(schema_version=2,target=dict(branch=a.branch,ref='refs/heads/'+a.branch),
             runtime=dict(status='unavailable',reason='No matching CI job/test artifacts supplied to this regression; native --list is not execution.',evidence=[],followups=['G_RUNTIME']),
             recent_prs=dict(since='2026-09-01T00:00:00Z',until='2026-09-21T23:59:59Z',status='unavailable',reason='Live unauthenticated GitHub discovery returned HTTP 403; this regression does not invent PR review.',items=[],followups=['G_RECENT_PRS']))
    template=d['tasks'][0]
    for id,reason,case in [('G_RUNTIME','Acquire per-job observed test identities for this branch','Match checkout/wheel SHA, lane, job attempt, actual test paths and skip counts'),
                            ('G_RECENT_PRS','Acquire and review recent PR behavior changes targeting this branch','Read base/head diffs and separate merged from prospective changes')]:
        t=copy.deepcopy(template)
        t.update(id=id,reason=reason,route='clarify_requirement',lanes=d['scope']['lanes'],
                 cases=[dict(name=case,inputs='Read-only scoped CI/PR artifacts',expected='Traceable evidence or explicitly unavailable',oracle='Original CI/PR metadata and source',negative_control='Reject wrong branch/SHA or metadata-only pass claims')],
                 prerequisites=['Read access to CI/PR metadata and artifacts'],acceptance=[case],search=['Branch CI jobs and recent PRs'])
        d['tasks'].append(t)
    for f in d['features']:
        f['change_ids']=[]
        f['finding']=dict(kind='risk',confidence='medium',rationale=f['requirement'],counterevidence='See existing assertion descriptions and source rationale; this is a schema regression, not a new independent semantic review.')
        for lane,c in f['lanes'].items():
            c.update(scheduling='not_applicable' if c['selection']=='not_applicable' else 'unknown',observations=[])
            c['followups']=[] if c['selection']=='not_applicable' else ['G_'+f['id'],'G_RUNTIME']
            if lane=='daily' and c['selection']!='not_applicable' and f['id']!='SCHEDULE':
                c['followups'].append('G_SCHEDULE')
        if f['id']=='API':
            f['lanes']['daily']['coverage']='supported'
            f['lanes']['daily']['followups']=['G_SCHEDULE','G_RUNTIME']
            f['lanes']['pr']['followups']=['G_RUNTIME']
    # No new test task for existing supported API assertions solely because
    # branch scheduling/runtime evidence is missing.
    d['tasks']=[t for t in d['tasks'] if t['id']!='G_API']
    for t in d['tasks']:
        if 'daily' in t['lanes'] and t['id'] not in {'G_SCHEDULE','G_RUNTIME','G_RECENT_PRS'}:
            t['depends_on']=['G_SCHEDULE']
    d['scope']['limitations'].append('V2 regression conversion only: actual CI identities and recent PR semantics remain unreviewed; do not count this as a completed fresh branch audit.')
    with a.output.open('x',encoding='utf-8') as stream:json.dump(d,stream,ensure_ascii=False,indent=2)


if __name__=='__main__':main()
