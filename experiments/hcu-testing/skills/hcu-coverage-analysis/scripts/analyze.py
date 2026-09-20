"""Validate coverage evidence and report missing executable Python lines."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo), *args], text=True).strip()


def changed_lines(repo, base, head):
    subprocess.run(['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo), 'merge-base', '--is-ancestor', base, head], check=True)
    patch = git(repo, 'diff', '--no-ext-diff', '--unified=0', base, head, '--', '*.py')
    changed, path = {}, None
    for line in patch.splitlines():
        if line.startswith('+++ b/'):
            path = line[6:]
            changed.setdefault(path, set())
        elif line.startswith('@@') and path is not None:
            m = re.search(r'\+(\d+)(?:,(\d+))? @@', line)
            if m:
                start, count = int(m[1]), int(m[2] or 1)
                changed[path].update(range(start, start + count))
    return changed


def analyze(repo, data, changes=None):
    if not isinstance(data.get('files'), dict) or not data['files']:
        raise ValueError('Missing or empty files mapping')
    rows = []
    for filename, values in data['files'].items():
        source = (repo / filename).resolve()
        try:
            relative = source.relative_to(repo).as_posix()
        except ValueError:
            raise ValueError('Coverage source escapes checkout')
        if not source.is_file() or source.suffix != '.py':
            raise ValueError('Missing/non-Python source: ' + relative)
        executed, missing = values.get('executed_lines'), values.get('missing_lines')
        if not isinstance(executed, list) or not isinstance(missing, list):
            raise ValueError('Missing line data: ' + relative)
        length = len(source.read_text(encoding='utf-8').splitlines())
        # coverage.py 7.6.1 can trace line 1 for an imported zero-byte module,
        # while correctly reporting zero executable statements. This is not
        # source coverage and must not be counted as a covered line.
        summary = values.get('summary', {})
        if (length == 0 and executed == [1] and missing == [] and
                summary.get('num_statements') == 0 and summary.get('covered_lines') == 0):
            executed = []
        if any(type(n) is not int or not 1 <= n <= length for n in executed + missing):
            raise ValueError('Invalid line number: ' + relative)
        executed, missing = set(executed), set(missing)
        if executed & missing:
            raise ValueError('Executed/missing lines overlap')
        if changes is not None:
            from coverage import Coverage
            # Runtime traces can contain non-statement lines (e.g. module docstrings).
            # Use coverage.py's public analysis API to identify actual statements.
            _, statements, _, _, _ = Coverage().analysis2(str(source))
            selected = changes.get(relative, set())
            executed, missing = executed & selected & set(statements), missing & selected & set(statements)
            total, covered = len(executed | missing), len(executed)
        else:
            summary = values.get('summary', {})
            total, covered = summary.get('num_statements'), summary.get('covered_lines')
            if (type(total) is not int or type(covered) is not int or
                    not 0 <= covered <= total or total != covered + len(missing)):
                raise ValueError('Invalid coverage.py statement summary: ' + relative)
        if total:
            rows.append({'file': relative, 'statements': total, 'covered': covered,
                         'missing_lines': sorted(missing), 'line_coverage': round(100 * covered / total, 2)})
    if not rows:
        raise ValueError('No executable Python statements match requested scope')
    return sorted(rows, key=lambda row: (row['line_coverage'], -len(row['missing_lines']), row['file']))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--coverage', type=Path, required=True)
    p.add_argument('--tested-commit', required=True)
    p.add_argument('--base-ref')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        repo = a.repo.resolve()
        head = git(repo, 'rev-parse', 'HEAD')
        if head != a.tested_commit or git(repo, 'status', '--porcelain'):
            raise ValueError('Tested commit mismatch or dirty checkout')
        changes = changed_lines(repo, a.base_ref, head) if a.base_ref else None
        rows = analyze(repo, json.loads(a.coverage.read_text(encoding='utf-8')), changes)
        total, covered = sum(x['statements'] for x in rows), sum(x['covered'] for x in rows)
        report = {'status': 'valid', 'source_commit': head, 'base_ref': a.base_ref,
                  'scope': 'changed_lines' if changes is not None else 'reported_python_files',
                  'statements': total, 'covered': covered, 'line_coverage': round(100 * covered / total, 2),
                  'files': rows, 'device_kernel_coverage': 'not_measured'}
        with a.output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
        print(json.dumps(report))
        return 0
    except (OSError, ValueError, TypeError, ImportError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'status': 'invalid_evidence', 'reason': str(exc)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
