#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
脚本一键同步工具 - v3.3 新增 (P1-E4)

解决每次改 scripts/ 要手动 Copy-Item 到 3-5 个 worktree 的痛点。

用法:
  python scripts/_sync_scripts.py list                # 列出需要同步的 worktree
  python scripts/_sync_scripts.py sync                # 同步所有脚本到所有 worktree
  python scripts/_sync_scripts.py sync <script>       # 只同步指定脚本
  python scripts/_sync_scripts.py diff                # 显示哪些脚本不一致
  python scripts/_sync_scripts.py diff <script>       # 显示指定脚本的差异
"""

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

# 需要同步的脚本列表
SYNC_SCRIPTS = [
    "_wt_service.py",
    "_ports_sync.py",
    "self_verify.py",
    "_wt_lifecycle.py",
    "_events.py",
    "_coord_log.py",
    "_coord_commit_guard.py",
    "_config_backup.py",
    "_session_cleanup.py",
    "_sync_scripts.py",
    # v3.3 自动化套件 (2026-07-20)
    "_v33_state.py",
    "handover_v33_hook.py",
    "pm_verify.py",
    "deploy_v33_hook.py",
    "_sync_precommit.py",
]  # 15 scripts: 同步列表 (含 v3.3 自动化套件)

# 需要同步的配置文件 (从 .coord/ 同步)
SYNC_CONFIG = [
    ".coord/paths.json",
]


def _main_repo() -> Path:
    return Path("D:/filework/excel-to-diagram")


def _worktrees() -> list:
    """获取所有 worktree 路径"""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(_main_repo()),
            capture_output=True, encoding="utf-8", errors="replace", timeout=10,
        )
        worktrees = []
        for line in r.stdout.split("\n"):
            if line.startswith("worktree "):
                wt_path = line[9:]
                if wt_path != str(_main_repo()):  # 排除主仓库
                    worktrees.append(Path(wt_path))
        return worktrees
    except Exception:
        return []


def cmd_list():
    """列出需要同步的 worktree"""
    wts = _worktrees()
    print(f"  Worktrees: {len(wts)}")
    for wt in wts:
        print(f"    - {wt}")
    print(f"\n  Scripts to sync: {len(SYNC_SCRIPTS)}")
    for s in SYNC_SCRIPTS:
        print(f"    - {s}")


def cmd_sync(specific_script: str = None):
    """同步脚本到所有 worktree"""
    src = _main_repo() / "scripts"
    wts = _worktrees()
    scripts = [specific_script] if specific_script else SYNC_SCRIPTS

    if not wts:
        print("  No worktrees to sync")
        return

    print(f"  Syncing {len(scripts)} script(s) to {len(wts)} worktree(s)...")

    total = 0
    for wt in wts:
        dst = wt / "scripts"
        if not dst.exists():
            print(f"  [SKIP] {wt.name}: scripts/ not found")
            continue

        for script in scripts:
            src_file = src / script
            if not src_file.exists():
                print(f"  [SKIP] {script}: source not found")
                continue
            try:
                shutil.copy2(src_file, dst / script)
                total += 1
            except PermissionError:
                print(f"  [WARN] {wt.name}/{script}: file locked, skipped")
            except Exception as e:
                print(f"  [WARN] {wt.name}/{script}: {e}")
        print(f"  [OK] {wt.name}: {len(scripts)} scripts synced")

    print(f"\n  Done: {total} file(s) synced")


def cmd_diff(specific_script: str = None):
    """显示哪些脚本不一致"""
    src = _main_repo() / "scripts"
    wts = _worktrees()
    scripts = [specific_script] if specific_script else SYNC_SCRIPTS

    print(f"  Checking {len(scripts)} script(s) across {len(wts)} worktree(s)...")

    diffs_found = False
    for wt in wts:
        dst = wt / "scripts"
        if not dst.exists():
            continue

        for script in scripts:
            src_file = src / script
            dst_file = dst / script
            if not src_file.exists() or not dst_file.exists():
                continue
            if not filecmp.cmp(src_file, dst_file, shallow=False):
                print(f"  [DIFF] {wt.name}/{script}")
                diffs_found = True

    if not diffs_found:
        print("  [OK] All scripts in sync")


def main():
    parser = argparse.ArgumentParser(description="Script sync tool (v3.3 P1-E4)")
    parser.add_argument("command", choices=["list", "sync", "diff"])
    parser.add_argument("script", nargs="?", help="specific script name")
    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "sync":
        cmd_sync(args.script)
    elif args.command == "diff":
        cmd_diff(args.script)


if __name__ == "__main__":
    sys.exit(main() or 0)
