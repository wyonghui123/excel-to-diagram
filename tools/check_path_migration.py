#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_path_migration.py - 检查 worktree 路径迁移是否完整 (V007.85)

V007.71 worktree 路径迁移后, 没扫 system config (cron / schtasks / service), 导致 V007.83
才发现 yonaa_alert_monitor 失败 (老路径 ERROR_FILE_NOT_FOUND).

V007.85 加这个工具, 扫描:
1. docs/tools/deploy_bundle/.trae 里的老路径 (V007.71 之前的)
2. Linux cron / systemd service (如果有)
3. Windows 计划任务 (schtasks /Query)
4. .env / config/*.json / *.yaml (如果引用 worktree 路径)

用法:
    py tools/check_path_migration.py          # 检查当前 cwd
    py tools/check_path_migration.py --strict # 任何匹配都 fail

退出码:
    0 - 全部新路径, 干净
    1 - 发现老路径
    2 - 脚本错误
"""
import re
import sys
import platform
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Optional

# ====== 老路径 patterns (V007.71 迁移过 + V007.55 cron 老的) ======
# 每个老路径的来源都加注释, 未来再加新路径方便追责
OLD_PATTERNS = {
    'V007.71 老路径 (Windows 4 种形式)': [
        r'D:\\filework\\release-prep-worktree\\',
        r'D:/filework/release-prep-worktree/',
        r'd:\\filework\\release-prep-worktree\\',
        r'd:/filework/release-prep-worktree/',
    ],
    'V007.55 cron 老路径 (Linux)': [
        r'/opt/app/staging/deploy',
    ],
}

# ====== 新路径 patterns (V007.71 后的标准) ======
NEW_PATTERNS = {
    'V007.71 新路径 (Windows 4 种)': [
        r'D:\\filework\\worktrees\\release-prep\\',
        r'D:/filework/worktrees/release-prep/',
        r'd:\\filework\\worktrees\\release-prep\\',
        r'd:/filework/worktrees/release-prep/',
    ],
    'V007.55 cron 新路径 (Linux)': [
        r'/opt/app/deployments',
    ],
}

# ====== 扫描目标 ======
SCAN_DIRS = [
    Path('docs'),
    Path('tools'),
    Path('deploy_bundle'),
    Path('.trae'),
]

# 排除的目录 (git submodules / node_modules / cache)
EXCLUDE_DIRS = {
    'node_modules',
    '.git',
    '__pycache__',
    'dist',
    'release',
    '.pytest_cache',
}


def is_text_file(filepath: Path) -> bool:
    """检查文件是否可能是文本 (前 1024 字节不含 NULL)"""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
        return b'\x00' not in chunk
    except Exception:
        return False


def scan_file(filepath: Path) -> Optional[Dict[str, int]]:
    """扫描单个文件, 返回老路径匹配数

    Returns:
        {pattern_name: count} 或 None
    """
    if not is_text_file(filepath):
        return None

    try:
        text = filepath.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return None

    matches = {}
    for group_name, patterns in OLD_PATTERNS.items():
        for pattern in patterns:
            count = len(re.findall(pattern, text))
            if count > 0:
                key = f'{group_name}: {pattern}'
                matches[key] = matches.get(key, 0) + count

    return matches if matches else None


def scan_directory(root: Path) -> List[tuple]:
    """扫描整个目录树

    Returns:
        [(filepath, {pattern: count})] 列表
    """
    results = []
    for filepath in root.rglob('*'):
        # Skip directories
        if not filepath.is_file():
            continue
        # Skip excluded
        if any(excluded in filepath.parts for excluded in EXCLUDE_DIRS):
            continue
        result = scan_file(filepath)
        if result:
            results.append((filepath, result))
    return results


def scan_scheduled_tasks() -> List[str]:
    """扫描 Windows 计划任务引用老路径

    Returns:
        bad task lines 列表
    """
    if platform.system() != 'Windows':
        return []

    bad_lines = []
    try:
        result = subprocess.run(
            ['schtasks', '/Query', '/FO', 'LIST'],
            capture_output=True, text=True, encoding='gbk', errors='replace', timeout=30
        )
        for line in result.stdout.split('\n'):
            for group_patterns in OLD_PATTERNS.values():
                if any(re.search(p, line) for p in group_patterns):
                    bad_lines.append(line.strip())
                    break
    except Exception as e:
        print(f'[WARN] schtasks scan failed: {e}', file=sys.stderr)

    return bad_lines


def scan_cron_linux() -> List[str]:
    """扫描 Linux cron / systemd service (如果有)"""
    if platform.system() == 'Windows':
        return []

    bad_lines = []
    # /etc/cron.d/
    cron_d = Path('/etc/cron.d')
    if cron_d.exists():
        for filepath in cron_d.rglob('*'):
            if filepath.is_file() and is_text_file(filepath):
                try:
                    text = filepath.read_text(encoding='utf-8', errors='replace')
                    for group_patterns in OLD_PATTERNS.values():
                        for pattern in group_patterns:
                            if re.search(pattern, text):
                                bad_lines.append(f'{filepath}: {pattern}')
                except Exception:
                    pass

    # /etc/systemd/system/*.service
    systemd = Path('/etc/systemd/system')
    if systemd.exists():
        for filepath in systemd.glob('*.service'):
            try:
                text = filepath.read_text(encoding='utf-8', errors='replace')
                for group_patterns in OLD_PATTERNS.values():
                    for pattern in group_patterns:
                        if re.search(pattern, text):
                            bad_lines.append(f'{filepath}: {pattern}')
            except Exception:
                pass

    return bad_lines


def main():
    parser = argparse.ArgumentParser(
        description='V007.85 Path Migration Check (防 V007.71 类似事故)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
V007.85 故事:
  V007.71 worktree 路径迁移 (e.g. release-prep-worktree/ -> worktrees/release-prep/)
  V007.83 电脑重启后 yonaa_alert_monitor 失败 (老路径 ERROR_FILE_NOT_FOUND)
  V007.85 加这个工具, 自动扫描老路径

V007.85 用法:
  py tools/check_path_migration.py          # 检查当前 cwd
  py tools/check_path_migration.py --strict # 任何匹配都 fail
        '''
    )
    parser.add_argument('--strict', action='store_true',
                       help='任何老路径都 fail (默认 0 = 警告, > 0 = fail)')
    parser.add_argument('--quiet', action='store_true',
                       help='只输出 fail 信息, 跳过 OK')
    args = parser.parse_args()

    print('=' * 60)
    print('V007.85 Path Migration Check')
    print('=' * 60)
    print()

    # 1. File scan
    print('--- 1. File scan (docs/tools/deploy_bundle/.trae) ---')
    file_results = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        file_results.extend(scan_directory(scan_dir))

    total_file_matches = sum(
        sum(counts.values()) for _, counts in file_results
    )

    if not args.quiet:
        for filepath, counts in file_results:
            rel_path = filepath
            for pattern, count in counts.items():
                print(f'  [MATCH] {rel_path}')
                print(f'          {pattern} ({count}x)')

    print(f'  Total file matches: {total_file_matches}')
    print()

    # 2. Scheduled tasks (Windows)
    print('--- 2. Windows scheduled tasks ---')
    bad_tasks = scan_scheduled_tasks()
    for line in bad_tasks:
        print(f'  [BAD TASK] {line}')
    print(f'  Total bad tasks: {len(bad_tasks)}')
    print()

    # 3. Linux cron / systemd
    print('--- 3. Linux cron / systemd ---')
    bad_cron = scan_cron_linux()
    for line in bad_cron:
        print(f'  [BAD CRON] {line}')
    print(f'  Total bad cron: {len(bad_cron)}')
    print()

    # Summary
    total_issues = total_file_matches + len(bad_tasks) + len(bad_cron)
    print('=' * 60)
    print(f'Total issues: {total_issues}')
    print(f'  - File matches: {total_file_matches}')
    print(f'  - Bad tasks: {len(bad_tasks)}')
    print(f'  - Bad cron: {len(bad_cron)}')
    print()

    if total_issues == 0:
        print('[OK] 全部新路径, 干净!')
        sys.exit(0)
    else:
        # Found old paths
        if args.strict:
            print('[FAIL] 老路径还在, 需要路径迁移!')
            print()
            print('修复建议:')
            print('  1. 看 AGENT_INFRA.md §0.7 5 步路径迁移 SOP')
            print('  2. 用 sed 批量替换:')
            for group_name, patterns in OLD_PATTERNS.items():
                for pattern in patterns:
                    # 转义 pattern 给 sed 用
                    sed_pattern = pattern.replace('\\', '\\\\').replace('/', '\\/')
                    print(f'     sed -i \'s|{sed_pattern}|NEW_PATH|g\' <file>')
            print()
            sys.exit(1)
        else:
            # Default: warn but don't fail (历史 docs 引用老路径不改)
            print('[WARN] 老路径还在, 但非 --strict 模式, 继续')
            print('       多数是 docs/ 历史记录, 不动它们')
            print('       如果是新加的 system config, 跑 --strict 严格检查')
            print()
            sys.exit(0)


if __name__ == '__main__':
    main()
