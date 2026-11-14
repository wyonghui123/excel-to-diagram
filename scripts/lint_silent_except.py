# -*- coding: utf-8 -*-
"""[FR-011] 静默异常检查（基线白名单模式）

规则：`except ...:` 的 body 只有 `pass`（或 `...`）视为静默吞异常。
允许显式标注豁免：

    except Exception:
        pass  # silent-ok: 可选依赖缺失时保持降级

历史存量记录在 `scripts/silent_except_baseline.txt`（按 文件|函数|异常类型 计数），
基线之外的任何新增静默异常都会让 CI 失败；清理完一个位置后执行
`--update-baseline` 收紧基线。

用法：
    python scripts/lint_silent_except.py [--max-detail 20] [--update-baseline]

退出码：0 无新增；1 存在基线外静默异常。
"""
from __future__ import annotations

import argparse
import ast
import collections
import os
import sys
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIRS = ('meta', 'scripts')
SKIP_PARTS = {'tests', '__tests__', 'node_modules', 'frontend_dist_files', '.git'}
EXEMPT_MARKERS = ('silent-ok', 'noqa: silent-except')
BASELINE = os.path.join(ROOT, 'scripts', 'silent_except_baseline.txt')


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel_path: str, lines: List[str]):
        self.rel_path = rel_path
        self.lines = lines
        self.scope: List[str] = []
        self.hits: List[Tuple[str, int]] = []

    def visit_FunctionDef(self, node):  # noqa: N802
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ExceptHandler(self, node: ast.ExceptHandler):  # noqa: N802
        if self._is_silent(node) and not self._exempt(node):
            exc_type = ast.unparse(node.type) if node.type else 'bare'
            key = '{0}|{1}|{2}'.format(
                self.rel_path, '.'.join(self.scope) or '<module>', exc_type)
            self.hits.append((key, node.lineno))
        self.generic_visit(node)

    @staticmethod
    def _is_silent(node: ast.ExceptHandler) -> bool:
        body = [n for n in node.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        if not body:
            return True
        return len(body) == 1 and isinstance(body[0], ast.Pass)

    def _exempt(self, node: ast.ExceptHandler) -> bool:
        start = max(0, node.lineno - 1)
        end = min(len(self.lines), getattr(node, 'end_lineno', node.lineno) + 1)
        window = ' '.join(self.lines[start:end])
        return any(marker in window for marker in EXEMPT_MARKERS)


def collect() -> Tuple[collections.Counter, Dict[str, List[int]]]:
    counts: collections.Counter = collections.Counter()
    locations: Dict[str, List[int]] = collections.defaultdict(list)
    for base in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, base)):
            dirnames[:] = [d for d in dirnames if d not in SKIP_PARTS]
            for name in filenames:
                if not name.endswith('.py'):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, ROOT).replace('\\', '/')
                try:
                    with open(full, 'r', encoding='utf-8') as fh:
                        source = fh.read()
                    tree = ast.parse(source, filename=full)
                except (OSError, UnicodeDecodeError, SyntaxError):
                    continue
                visitor = _Visitor(rel, source.splitlines())
                visitor.visit(tree)
                for key, lineno in visitor.hits:
                    counts[key] += 1
                    locations[key].append(lineno)
    return counts, locations


def load_baseline() -> collections.Counter:
    baseline: collections.Counter = collections.Counter()
    if not os.path.exists(BASELINE):
        return baseline
    with open(BASELINE, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, _, count = line.rpartition('||')
            if not key:
                continue
            try:
                baseline[key] = int(count)
            except ValueError:
                continue
    return baseline


def write_baseline(counts: collections.Counter) -> None:
    with open(BASELINE, 'w', encoding='utf-8') as fh:
        fh.write('# FR-011 静默异常基线（由 scripts/lint_silent_except.py --update-baseline 生成）\n')
        fh.write('# 格式：文件|函数|异常类型||出现次数\n')
        for key in sorted(counts):
            fh.write('{0}||{1}\n'.format(key, counts[key]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-detail', type=int, default=20)
    parser.add_argument('--update-baseline', action='store_true')
    args = parser.parse_args()

    counts, locations = collect()
    if args.update_baseline:
        write_baseline(counts)
        print('baseline updated: {0} entries / {1} occurrences'.format(
            len(counts), sum(counts.values())))
        return 0

    baseline = load_baseline()
    new_violations: List[Tuple[str, int]] = []
    for key, count in counts.items():
        allowed = baseline.get(key, 0)
        if count <= allowed:
            continue
        extra = count - allowed
        line_numbers = locations.get(key, [])
        for lineno in line_numbers[-extra:]:
            new_violations.append((key, lineno))

    total = sum(counts.values())
    print('silent-except: total={0}, baseline={1}, new={2}'.format(
        total, sum(baseline.values()), len(new_violations)))
    for key, lineno in new_violations[: max(0, args.max_detail)]:
        rel, scope, exc_type = key.split('|', 2)
        print('  {0}:{1}  {2} ({3})'.format(rel, lineno, exc_type, scope))
    return 1 if new_violations else 0


if __name__ == '__main__':
    sys.exit(main())