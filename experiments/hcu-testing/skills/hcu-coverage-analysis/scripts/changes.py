"""Rename-aware PR diff navigation from existing immutable Git objects.

No fetch, checkout, import or target mutation. Hunk counts are not coverage.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def collect(repo,base,head,target,mode='merge-base'):
    def git(*args):
        return subprocess.check_output(['git','-c','safe.directory='+str(repo),'-C',str(repo),*args])
    for value in (base,head,target):
        if not re.fullmatch(r'[0-9a-f]{40}',value):
            raise ValueError('Use full immutable commit SHAs, not option-like refs')
        git('cat-file','-e',value+'^{commit}')
    merge_base=git('merge-base',base,head).decode().strip()
    if mode not in {'merge-base','exact'}:raise ValueError('Invalid diff mode')
    diff_base=merge_base if mode=='merge-base' else base
    if diff_base==head:raise ValueError('Empty merge-base/head comparison: obtain the original PR diff or explicit pre-merge parent; do not treat this as no behavior changes')
    raw=git('diff','--name-status','-z','--find-renames',diff_base,head,'--').decode('utf-8').split('\0')
    files=[]
    while raw and raw[0]:
        status=raw.pop(0);old=raw.pop(0)
        new=raw.pop(0) if status.startswith(('R','C')) else old
        files.append(dict(status=status,old_path=old,path=new))
    patch=git('diff','--no-ext-diff','--no-textconv','--find-renames','--unified=3',diff_base,head,'--')
    ancestry=subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',head,target],capture_output=True)
    if ancestry.returncode not in (0,1):
        raise ValueError('Cannot resolve target ancestry')
    return dict(base_sha=base,head_sha=head,target_sha=target,merge_base=merge_base,diff_base=diff_base,mode=mode,
                head_ancestor_of_target=ancestry.returncode==0,
                inclusion_note='Ancestry only: squash/cherry-pick/revert semantics need review; inspect merge SHA and actual behavior.',
                files=files,patch_sha256=hashlib.sha256(patch).hexdigest(),patch=patch.decode('utf-8',errors='replace'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('base','head','target'):p.add_argument('--'+arg,required=True)
    p.add_argument('--mode',choices=['merge-base','exact'],default='merge-base')
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        repo,out=a.repo.resolve(),a.output.resolve()
        if repo==out or repo in out.parents or out.exists():raise ValueError('Use new output outside checkout')
        result=collect(repo,a.base,a.head,a.target,a.mode)
        with out.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps(dict(status='diff_collected',files=len(result['files']))))
        return 0
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print(json.dumps(dict(status='unavailable',reason=str(exc))))
        return 2


if __name__=='__main__':raise SystemExit(main())
