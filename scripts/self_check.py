#!/usr/bin/env python3
"""
self_check.py - Coordinator Self-Check Tool v1.0

每次回复前跑这个脚本，检测：
1. 当前 cwd 是否在主工作树（违规风险）
2. 主工作树 modified 文件数量
3. 最近的 git 操作历史
4. .agent-violations.json 状态
5. Worktree 状态

Usage:
    python scripts/self_check.py
    python scripts/self_check.py --verbose
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(r"d:\filework\excel-to-diagram")
VIOLATIONS_FILE = Path(r"d:\filework\excel-to-diagram\.agent-violations.json")


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


def check_worktree_status():
    """Check git status"""
    return run_git(["status", "--porcelain"])


def count_worktrees():
    """Count worktrees"""
    out = run_git(["worktree", "list"])
    return len([l for l in out.split("\n") if l.strip()])


def check_violations():
    """Check violations count"""
    try:
        if VIOLATIONS_FILE.exists():
            data = json.loads(VIOLATIONS_FILE.read_text(encoding="utf-8"))
            return data.get("L2_violations", 0)
    except Exception:
        pass
    return 0


def get_current_branch():
    """Get current branch"""
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"])


def main():
    print("=" * 70)
    print("  COORDINATOR SELF-CHECK v1.0")
    print("=" * 70)
    print()

    # 1. Current location
    cwd = os.getcwd()
    in_main = "excel-to-diagram" in cwd and "worktree" not in cwd.lower()
    in_wt = "worktree" in cwd.lower()

    print(f"[1] Current Location")
    print(f"    CWD: {cwd}")
    if in_main and not in_wt:
        print(f"    Status: [WARN] In MAIN worktree (L2 risk)")
    elif in_wt:
        print(f"    Status: [OK] In WORKTREE")
    else:
        print(f"    Status: [?] Unknown")
    print()

    # 2. Branch
    branch = get_current_branch()
    print(f"[2] Current Branch")
    print(f"    {branch}")
    if branch == "main":
        print(f"    Status: [WARN] On main branch (should be in worktree)")
    print()

    # 3. Main worktree status
    status_output = check_worktree_status()
    modified_count = len([l for l in status_output.split("\n") if l.strip() and l[1] == "M"])
    untracked_count = len([l for l in status_output.split("\n") if l.strip() and l.startswith("??")])
    print(f"[3] Main Worktree Status")
    print(f"    Modified: {modified_count}")
    print(f"    Untracked: {untracked_count}")
    if modified_count > 0:
        print(f"    Status: [WARN] Main worktree has modifications")
    else:
        print(f"    Status: [OK] Clean")
    print()

    # 4. Worktrees
    wt_count = count_worktrees()
    print(f"[4] Worktrees")
    print(f"    Count: {wt_count}")
    print(f"    Status: {'[OK]' if wt_count > 0 else '[WARN] No worktrees'}")
    print()

    # 5. Violations
    v_count = check_violations()
    print(f"[5] Violations")
    print(f"    L2 count: {v_count}")
    if v_count == 0:
        print(f"    Status: [OK] No violations")
    elif v_count <= 2:
        print(f"    Status: [OK] Within target (2/session)")
    else:
        print(f"    Status: [WARN] Above target")
    print()

    # 6. Overall assessment
    print("=" * 70)
    risk_score = 0
    if in_main and not in_wt:
        risk_score += 30
    if branch == "main":
        risk_score += 20
    if modified_count > 10:
        risk_score += 10
    if v_count > 2:
        risk_score += 20

    if risk_score == 0:
        verdict = "[OK] SAFE - proceed normally"
        color = "OK"
    elif risk_score < 30:
        verdict = "[WARN] CAUTION - be careful with writes"
        color = "WARN"
    else:
        verdict = "[HIGH] DANGER - L2 violation risk"
        color = "HIGH"

    print(f"  VERDICT: {verdict}")
    print(f"  Risk Score: {risk_score}/100")
    print("=" * 70)

    return 0 if risk_score < 30 else 1


if __name__ == "__main__":
    sys.exit(main())