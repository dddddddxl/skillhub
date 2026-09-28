"""只读 Python AST 导航索引；不导入仓库代码，不把词法调用推断为真实调用图。"""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tokenize


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def read_blobs(repo, oids):
    """One Git process instead of one process per file on large Windows checkouts."""
    result = {}
    with subprocess.Popen(['git', '-C', str(repo), 'cat-file', '--batch'],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        try:
            for oid in dict.fromkeys(oids):
                process.stdin.write((oid + '\n').encode('ascii'))
                process.stdin.flush()
                header = process.stdout.readline().split()
                if len(header) != 3 or header[1] != b'blob':
                    raise ValueError('Cannot read source blob')
                size = int(header[2])
                raw = process.stdout.read(size)
                if len(raw) != size or process.stdout.read(1) != b'\n':
                    raise ValueError('Truncated source blob')
                result[oid] = raw
        finally:
            process.stdin.close()
            process.stdout.close()
        if process.wait(timeout=10) != 0:
            raise ValueError('Git blob reader failed')
    return result


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return dotted(node.value) + '.' + node.attr
    return '<dynamic>'


class Index(ast.NodeVisitor):
    def __init__(self):
        self.stack = []
        self.symbols, self.calls, self.imports = [], [], []

    def symbol(self, node, kind):
        self.stack.append(node.name)
        row = dict(name='.'.join(self.stack), kind=kind, start=node.lineno,
                   end=node.end_lineno, decorators=[dotted(d) for d in node.decorator_list])
        if isinstance(node, ast.ClassDef):
            row['bases'] = [dotted(b) for b in node.bases]
        self.symbols.append(row)
        self.generic_visit(node)
        self.stack.pop()

    def visit_ClassDef(self, node):
        self.symbol(node, 'class')

    def visit_FunctionDef(self, node):
        self.symbol(node, 'function')

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        self.calls.append(dict(caller='.'.join(self.stack) or '<module>',
                               callee=dotted(node.func), line=node.lineno))
        self.generic_visit(node)

    def visit_Import(self, node):
        self.imports.extend(dict(module=a.name, alias=a.asname, line=node.lineno) for a in node.names)

    def visit_ImportFrom(self, node):
        self.imports.extend(dict(module='.' * node.level + (node.module or ''), name=a.name,
                                 alias=a.asname, line=node.lineno) for a in node.names)


def build(repo, paths=(), max_files=500):
    if max_files < 1:
        raise ValueError('max_files must be positive')
    for path in paths:
        if not path or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or ':' in path or '\\' in path:
            raise ValueError('Use repository-relative POSIX paths')
    commit = git(repo, 'rev-parse', 'HEAD').decode().strip()
    # Read Git blobs, not working files or external symlink targets.
    entries = git(repo, 'ls-tree', '-r', '-z', commit).split(b'\0')
    candidates, non_python = [], 0
    for entry in filter(None, entries):
        metadata, name = entry.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        path = name.decode('utf-8')
        if paths and not any(path == p or path.startswith(p.rstrip('/') + '/') for p in paths):
            continue
        if not path.endswith('.py'):
            non_python += 1
            continue
        candidates.append((path, mode, kind, oid))
    result = dict(schema_version=1, source_commit=commit,
                  working_tree_ignored=bool(git(repo, 'status', '--porcelain').strip()),
                  candidate_count=len(candidates), deferred_paths=[p[0] for p in candidates[max_files:]],
                  non_python_files=non_python, files=[], limitations=[
                      'Lexical navigation only: aliases, polymorphism, reflection and backend dispatch need manual tracing.',
                      'Symbols/calls do not establish supported features, test assertions or CI execution.',
                      'Non-Python code and files beyond the budget are not analyzed; document their review separately.'])
    blobs = read_blobs(repo, [oid for _, mode, kind, oid in candidates[:max_files]
                             if mode != '120000' and kind == 'blob'])
    for path, mode, kind, oid in candidates[:max_files]:
        row = dict(path=path, blob=oid)
        if mode == '120000' or kind != 'blob':
            row.update(status='unresolved', reason='symlink or non-blob')
        else:
            raw = blobs[oid]
            row['sha256'] = hashlib.sha256(raw).hexdigest()
            try:
                encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                tree = ast.parse(raw.decode(encoding), filename=path)
                index = Index()
                index.visit(tree)
                row.update(status='indexed', symbols=index.symbols, calls=index.calls, imports=index.imports)
            except (SyntaxError, UnicodeError, LookupError, RecursionError) as exc:
                row.update(status='unresolved', reason=type(exc).__name__)
        result['files'].append(row)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--path', action='append', default=[])
    p.add_argument('--max-files', type=int, default=500)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        repo, out = a.repo.resolve(), a.output.resolve()
        if out == repo or repo in out.parents:
            raise ValueError('Output must be outside checkout')
        data = build(repo, a.path, a.max_files)
        with out.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        print(json.dumps(dict(status='indexed', files=len(data['files']), deferred=len(data['deferred_paths']))))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps(dict(status='unavailable', reason=str(exc))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
