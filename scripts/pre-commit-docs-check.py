#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Git pre-commit hook: 检查 docs/ 下变更文件的链接有效性

安装方法：
    ln -s ../../scripts/pre-commit-docs-check.py .git/hooks/pre-commit
    # 或 Windows: copy scripts\pre-commit-docs-check.py .git\hooks\pre-commit

行为：
    - 检测本次 commit 中 docs/ 下的变更文件
    - 仅对这些文件运行 link-check（快速反馈）
    - 发现问题：阻止 commit，提示修复
    - 无问题：允许 commit
"""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

# 颜色
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def get_changed_docs():
    """获取本次 commit 中 docs/ 下的变更文件"""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'],
            cwd=ROOT, capture_output=True, text=True, check=True
        )
        files = result.stdout.strip().split('\n')
        return [f for f in files if f.startswith('docs/') and f.endswith('.md')]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def main():
    print(f'{YELLOW}[pre-commit] Documentation check{RESET}')
    print()

    changed = get_changed_docs()
    if not changed:
        print(f'{GREEN}[OK] No docs/ files changed, skipping{RESET}')
        return 0

    print(f'[INFO] {len(changed)} docs/ files in this commit:')
    for f in changed[:10]:
        print(f'  - {f}')
    if len(changed) > 10:
        print(f'  ... and {len(changed) - 10} more')
    print()

    # 运行 link-check
    try:
        from check_doc_links import scan_file
    except ImportError as e:
        print(f'{RED}[ERROR] Cannot import check_doc_links: {e}{RESET}')
        return 0  # 允许 commit（避免阻塞）

    total_issues = 0
    files_with_issues = 0

    for rel_path in changed:
        full_path = ROOT / rel_path
        if not full_path.exists():
            continue
        issues = scan_file(full_path, check_external=False)
        if issues:
            files_with_issues += 1
            total_issues += len(issues)
            print(f'{RED}[FAIL] {rel_path}{RESET}')
            for status, link, line_num in issues[:5]:
                icon = '[MISSING]' if status == 'missing' else '[ANCHOR]'
                print(f'  L{line_num:4d} {icon} {link[:100]}')
            if len(issues) > 5:
                print(f'  ... and {len(issues) - 5} more issues')
            print()

    if total_issues > 0:
        print(f'{RED}[FAIL] {total_issues} issues in {files_with_issues} files{RESET}')
        print()
        print('Options:')
        print('  1. Fix the broken links')
        print('  2. Update references: python scripts/fix_broken_links.py')
        print('  3. Skip this check: git commit --no-verify')
        print()
        return 1

    print(f'{GREEN}[OK] All {len(changed)} files passed link check{RESET}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n[ABORT]')
        sys.exit(1)
