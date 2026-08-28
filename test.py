# -*- coding: utf-8 -*-
"""
Worktree-local test entry (mirrors d:/filework/test.py)

For feat-permission-set-refactor worktree.
Sets TEST_ENTRY=1 to satisfy conftest hard-block.
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path

# Worktree root (this file lives at worktree root)
PROJECT_ROOT = Path('d:/filework/worktrees/feat-permission-set-refactor')
TEST_DIR = PROJECT_ROOT / 'meta' / 'tests'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Worktree test entry')
    parser.add_argument('--file', metavar='PATH', help='单文件 (--file meta/tests/...)')
    parser.add_argument('--all', action='store_true', help='全量测试')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose')
    parser.add_argument('--tb', default='short', help='tb style')
    parser.add_argument('--skip', action='store_true', help='show skip reasons')
    parser.add_argument('--timeout', type=int, default=300, help='timeout seconds')
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    cmd = [sys.executable, '-m', 'pytest']
    if args.all:
        cmd += [str(TEST_DIR), '-v', f'--tb={args.tb}']
    elif args.file:
        cmd += [str(PROJECT_ROOT / args.file), '-v', f'--tb={args.tb}']
    else:
        cmd += [str(TEST_DIR), '-v', f'--tb={args.tb}']
    if args.skip:
        cmd += ['-rs']
    cmd += [f'--timeout={args.timeout}']

    env = os.environ.copy()
    env['TEST_ENTRY'] = '1'

    print(f'[WT-TEST] cmd: {" ".join(cmd)}')
    print(f'[WT-TEST] cwd: {PROJECT_ROOT}')

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            timeout=args.timeout,
            capture_output=False,
        )
        return proc.returncode
    except subprocess.TimeoutExpired:
        print(f'[WT-TEST] TIMEOUT after {args.timeout}s')
        return -1


if __name__ == '__main__':
    sys.exit(main())
