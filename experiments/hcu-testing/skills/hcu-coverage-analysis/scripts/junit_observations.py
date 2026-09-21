"""Normalize per-test JUnit observations with explicit, reviewed job identity.

No inference from green job status or classname to source path. Retains only
test identities/outcomes, not failure payloads or request/model data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def normalize(xml,context):
    if len(xml)>20*1024*1024 or b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
        raise ValueError('Oversized XML or DTD/entity declaration rejected')
    root=ET.fromstring(xml)
    cases=[]
    seen=set()
    for node in root.iter():
        if node.tag.rsplit('}',1)[-1]!='testcase':continue
        id='::'.join(x for x in (node.get('classname'),node.get('name')) if x)
        if not id or id in seen:raise ValueError('Missing or duplicate testcase identity; preserve suite/attempt boundaries')
        seen.add(id)
        path=node.get('file') or context.get('case_paths',{}).get(id) or context.get('test_file')
        if not path:raise ValueError('No explicit source path for '+id)
        tags={child.tag.rsplit('}',1)[-1] for child in node}
        outcome='error' if 'error' in tags else 'failed' if 'failure' in tags else 'skipped' if 'skipped' in tags else 'passed'
        cases.append(dict(id=id,path=path,outcome=outcome))
    counts=dict(tests=len(cases),failed=sum(c['outcome']=='failed' for c in cases),errors=sum(c['outcome']=='error' for c in cases),skipped=sum(c['outcome']=='skipped' for c in cases))
    status='test_failure' if counts['failed'] or counts['errors'] else 'pass' if any(c['outcome']=='passed' for c in cases) else 'no_tests_executed'
    keys=('repository','branch','lane','platform','source_commit','source_identity','run_id','job_id','attempt','source_locator')
    if any(key not in context for key in keys):raise ValueError('Reviewed job/source context required')
    return dict({key:context[key] for key in keys},granularity='case',status=status,counts=counts,cases=cases,
                original_artifact_sha256=hashlib.sha256(xml).hexdigest())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('junit','context','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.exists():raise ValueError('Output exists')
        result=normalize(a.junit.read_bytes(),json.loads(a.context.read_text(encoding='utf-8')))
        with a.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps(dict(status=result['status'],counts=result['counts'])))
        return 0
    except (OSError,ValueError,ET.ParseError) as exc:
        print(json.dumps(dict(status='unavailable',reason=str(exc))))
        return 2


if __name__=='__main__':raise SystemExit(main())
