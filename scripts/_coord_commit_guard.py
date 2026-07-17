#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
协调智能体 commit 防护脚本 (2026-07-17 创建, P0 修复后续防护)

问题:
- 2026-07-17 协调智能体 P0 commit 包含 dev agent 代码 (06704f8 / 427b888)
- 用 git add -A 把 meta/ 等协调智能体禁改路径也 add 进去

功能:
- safe-add <wt-path>: 只 add 协调智能体允许的文件
- check <wt-path>: 检查 working tree, 找出协调智能体禁改的文件
- list-excludes: 列出当前排除名单

用法:
  python scripts/_coord_commit_guard.py check D:/filework/worktrees/release-prep
  python scripts/_coord_commit_guard.py safe-add D:/filework/worktrees/release-prep
  python scripts/_coord_commit_guard.py list-excludes
"""
import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

# 加载排除名单
EXCLUDE_FILE = Path("D:/filework/.coord/exclude_patterns.json")

def load_excludes() -> list:
    if EXCLUDE_FILE.exists():
        try:
            with open(EXCLUDE_FILE, encoding="utf-8-sig") as f:
                data = json.load(f)
            return data.get("exclude_patterns", [])
        except Exception:
            pass
    return []


def is_excluded(path: str, excludes: list) -> bool:
    """检查路径是否在排除名单"""
    p = path.replace("\\", "/")
    for pat in excludes:
        # fnmatch 不支持 ** 模式, 简单转换
        if "**" in pat:
            # meta/** => meta/ 开头 + 任意后缀
            prefix = pat.replace("/**", "/")
            if p.startswith(prefix):
                return True
        elif fnmatch.fnmatch(p, pat):
            return True
    return False


def get_modified_files(wt_path: str) -> list:
    """获取 wt 的所有 modified + untracked 文件"""
    r = subprocess.run(
        ["git", "-C", wt_path, "status", "--porcelain"],
        capture_output=True, encoding="utf-8", errors="replace",
        timeout=10,
    )
    files = []
    for line in r.stdout.split("\n"):
        if not line.strip():
            continue
        # 格式: "XY filename" (XY 是 2 字符 status)
        if len(line) >= 4:
            status = line[:2]
            filepath = line[3:].strip()
            # 处理重命名: "old -> new"
            if " -> " in filepath:
                filepath = filepath.split(" -> ")[1]
            files.append((status.strip(), filepath))
    return files


def cmd_check(wt_path: str):
    """检查 working tree, 找出协调智能体禁改的文件"""
    excludes = load_excludes()
    files = get_modified_files(wt_path)

    print(f"Checking {wt_path}")
    print(f"Total modified files: {len(files)}")
    print(f"Exclude patterns: {len(excludes)}")
    print()

    allowed = []
    blocked = []

    for status, fp in files:
        if is_excluded(fp, excludes):
            blocked.append((status, fp))
        else:
            allowed.append((status, fp))

    print(f"[OK] Allowed for coord commit: {len(allowed)}")
    for s, f in allowed[:30]:
        print(f"    {s} {f}")

    print()
    print(f"[X] BLOCKED (dev agent domain): {len(blocked)}")
    for s, f in blocked[:30]:
        print(f"    {s} {f}")

    if blocked:
        print()
        print("[!] WARNING: 协调智能体 commit 不能包含上述 BLOCKED 文件!")
        print("[!] These are dev agent domain (§0.8.4)")
        return 1
    return 0


def cmd_safe_add(wt_path: str):
    """只 add 协调智能体允许的文件 (排除名单外)"""
    excludes = load_excludes()
    files = get_modified_files(wt_path)

    added = []
    blocked = []

    for status, fp in files:
        if is_excluded(fp, excludes):
            blocked.append(fp)
            continue
        # Add this file
        r = subprocess.run(
            ["git", "-C", wt_path, "add", fp],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        if r.returncode == 0:
            added.append(fp)
        else:
            print(f"  FAIL to add {fp}: {r.stderr[:200]}")

    print(f"Added {len(added)} files")
    for f in added[:20]:
        print(f"  + {f}")
    print()
    print(f"Blocked {len(blocked)} files (dev agent domain)")
    for f in blocked[:20]:
        print(f"  X {f}")

    if blocked:
        print()
        print("[!] 这些文件没被 add. 协调智能体不能 commit 它们.")
        print("[!] 如果需要, 让 dev agent 自行 commit.")
    return 0


def cmd_list_excludes():
    """列出当前排除名单"""
    excludes = load_excludes()
    if not EXCLUDE_FILE.exists():
        print(f"Exclude file not found: {EXCLUDE_FILE}")
        return 1
    print(f"Exclude patterns from {EXCLUDE_FILE}:")
    for p in excludes:
        print(f"  {p}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="协调智能体 commit 防护脚本 - 防止 L2 §0.8.4 违规"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check_p = sub.add_parser("check", help="检查 working tree, 列出禁改文件")
    check_p.add_argument("wt_path")

    add_p = sub.add_parser("safe-add", help="只 add 协调智能体允许的文件")
    add_p.add_argument("wt_path")

    sub.add_parser("list-excludes", help="列出排除名单")

    args = parser.parse_args()

    if args.cmd == "check":
        return cmd_check(args.wt_path)
    elif args.cmd == "safe-add":
        return cmd_safe_add(args.wt_path)
    elif args.cmd == "list-excludes":
        return cmd_list_excludes()
    return 0


if __name__ == "__main__":
    sys.exit(main())