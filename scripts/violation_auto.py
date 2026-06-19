#!/usr/bin/env python3
"""
violation_auto.py - Violation Auto-Detection Tool v1.0

每次 Write 工具调用后跑这个脚本：
1. 检查主工作树是否有新修改
2. 检查是否有未提交的孤儿文件
3. 自动写入 .agent-violations.json
4. 输出违规报告

Usage:
    python scripts/violation_auto.py
    python scripts/violation_auto.py --check-only
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(r"d:\filework\excel-to-diagram")
VIOLATIONS_FILE = REPO_DIR / ".agent-violations.json"


def run_git(args):
    """Run git command"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_violations():
    """Read violations"""
    if VIOLATIONS_FILE.exists():
        try:
            return json.loads(VIOLATIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"L2_violations": 0, "details": [], "version": "1.0"}


def save_violations(data):
    """Save violations"""
    VIOLATIONS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def check_orphan_dirs():
    """Check for orphan directories (worktree without .git)"""
    orphans = []
    parent = REPO_DIR.parent
    for item in parent.iterdir():
        if item.is_dir() and "worktree" in item.name.lower():
            git_path = item / ".git"
            if not git_path.exists():
                # Check if it's a registered worktree
                wt_list = run_git(["worktree", "list"])
                if item.name not in wt_list:
                    orphans.append(str(item))
    return orphans


def check_main_modified():
    """Check main worktree modified files"""
    status = run_git(["status", "--porcelain"])
    modified = []
    untracked = []
    for line in status.split("\n"):
        if not line.strip():
            continue
        if line.startswith("??"):
            untracked.append(line[3:])
        elif len(line) > 1 and line[1] == "M":
            modified.append(line[3:])
    return modified, untracked


def record_violation(reason, details=""):
    """Record a new violation"""
    data = get_violations()
    count = data.get("L2_violations", 0) + 1
    data["L2_violations"] = count
    data["last_violation"] = datetime.now().isoformat()
    data["details"].append({
        "id": count,
        "date": datetime.now().isoformat(),
        "reason": reason,
        "details": details
    })
    save_violations(data)
    return count


def main():
    print("=" * 70)
    print("  VIOLATION AUTO-DETECTION v1.0")
    print("=" * 70)
    print()

    violations_found = []

    # 1. Check orphan directories
    orphans = check_orphan_dirs()
    print(f"[1] Orphan Worktree Check")
    if orphans:
        print(f"    [WARN] Found {len(orphans)} orphan worktree(s):")
        for o in orphans:
            print(f"      - {o}")
        violations_found.append(("orphan_worktree", f"Found {len(orphans)} orphans: {orphans}"))
    else:
        print(f"    [OK] No orphan worktrees")
    print()

    # 2. Check main worktree modifications
    modified, untracked = check_main_modified()
    print(f"[2] Main Worktree Check")
    print(f"    Modified files: {len(modified)}")
    print(f"    Untracked files: {len(untracked)}")

    # High count = potential L2 violation
    if len(modified) > 20:
        print(f"    [WARN] High modification count (potential L2 violation)")
        violations_found.append(("main_modified", f"{len(modified)} modified files"))
    elif len(modified) == 0:
        print(f"    [OK] No modifications")
    print()

    # 3. Summary
    if "--check-only" in sys.argv:
        print("[MODE] Check only - not recording violations")
        return 0 if not violations_found else 1

    # 4. Record violations
    if violations_found:
        print(f"[3] Recording {len(violations_found)} violation(s)...")
        for reason, details in violations_found:
            new_count = record_violation(reason, details)
            print(f"    Recorded #{new_count}: {reason}")
    else:
        print(f"[3] No new violations to record")

    # 5. Show current status
    data = get_violations()
    print()
    print(f"[STATUS]")
    print(f"    Total L2 violations: {data.get('L2_violations', 0)}")
    print(f"    Target: 2/session")
    if data.get("details"):
        last = data["details"][-1]
        print(f"    Last: #{last['id']} at {last['date']}: {last['reason']}")

    print()
    print("=" * 70)
    return 0 if not violations_found else 1


if __name__ == "__main__":
    sys.exit(main())