#!/usr/bin/env python3
"""
write_wrapper.py - Path Safety Wrapper v1.0

替代 Trae IDE Write wrapper，在写文件前检查路径：
1. 检测主工作树路径
2. 检测孤儿 worktree
3. 输出警告或阻止

Usage:
    python scripts/write_wrapper.py <path>
    python scripts/write_wrapper.py <path> --confirm
"""

import os
import sys
from pathlib import Path

REPO_DIR = Path(r"d:\filework\excel-to-diagram")


def check_path(path_str):
    """Check if path is safe to write"""
    path = Path(path_str).resolve()

    result = {
        "path": str(path),
        "in_main_worktree": False,
        "in_real_worktree": False,
        "is_orphan": False,
        "verdict": "OK",
        "risk_level": 0,
        "warnings": [],
    }

    # Check 1: Is path in main worktree?
    try:
        path.relative_to(REPO_DIR)
        result["in_main_worktree"] = True
    except ValueError:
        pass

    # Check 2: Is path in a real worktree?
    parent = REPO_DIR.parent
    wt_dirs = []
    if parent.exists():
        for item in parent.iterdir():
            if item.is_dir() and "worktree" in item.name.lower():
                git_path = item / ".git"
                if git_path.exists():
                    wt_dirs.append(item.resolve())

    for wt in wt_dirs:
        try:
            path.relative_to(wt)
            result["in_real_worktree"] = True
            break
        except ValueError:
            continue

    # Check 3: Is path in an orphan?
    if parent.exists():
        for item in parent.iterdir():
            if item.is_dir() and "worktree" in item.name.lower():
                git_path = item / ".git"
                if not git_path.exists():
                    try:
                        path.relative_to(item.resolve())
                        result["is_orphan"] = True
                        result["warnings"].append(f"Orphan: {item.name}")
                        break
                    except ValueError:
                        continue

    # Decision logic
    if result["in_main_worktree"]:
        result["verdict"] = "L2_VIOLATION"
        result["risk_level"] = 90
        result["warnings"].append(
            "Writing to MAIN WORKTREE (L2 violation)"
        )
    elif result["is_orphan"]:
        result["verdict"] = "ORPHAN_RISK"
        result["risk_level"] = 70
        result["warnings"].append(
            "Writing to ORPHAN worktree (git doesn't know about it)"
        )
    elif result["in_real_worktree"]:
        result["verdict"] = "SAFE"
        result["risk_level"] = 5
    else:
        result["verdict"] = "OUTSIDE_REPO"
        result["risk_level"] = 50
        result["warnings"].append("Outside any known worktree")

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python write_wrapper.py <path> [--confirm]")
        sys.exit(1)

    target = sys.argv[1]
    confirmed = "--confirm" in sys.argv

    result = check_path(target)

    print("=" * 60)
    print("  WRITE WRAPPER CHECK v1.0")
    print("=" * 60)
    print(f"Target: {result['path']}")
    print()
    print(f"In main worktree:  {result['in_main_worktree']}")
    print(f"In real worktree:  {result['in_real_worktree']}")
    print(f"Is orphan:         {result['is_orphan']}")
    print()
    print(f"Verdict: {result['verdict']}")
    print(f"Risk:    {result['risk_level']}/100")
    if result["warnings"]:
        print()
        print("Warnings:")
        for w in result["warnings"]:
            print(f"  - {w}")
    print()

    if result["verdict"] == "L2_VIOLATION":
        if not confirmed:
            print("[BLOCKED] L2 violation. Use --confirm to override.")
            sys.exit(2)
        print("[CONFIRMED] L2 violation acknowledged. Proceeding.")
    elif result["verdict"] == "ORPHAN_RISK":
        print("[WARN] Orphan detected. File will be lost.")
    elif result["verdict"] == "SAFE":
        print("[OK] Safe to write.")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())