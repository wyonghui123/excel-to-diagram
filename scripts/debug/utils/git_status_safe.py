#!/usr/bin/env python3
"""V3.5 sandbox-safe git status reporter"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
os.chdir(PROJECT_ROOT)

result = {
    "timestamp": datetime.now().isoformat(),
    "cwd": str(PROJECT_ROOT),
    "branch": None,
    "uncommitted": [],
    "worktrees": [],
    "errors": [],
}

# git rev-parse
try:
    result["branch"] = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
except Exception as e:
    result["errors"].append(f"rev-parse: {e}")

# git status --short
try:
    status = subprocess.run(
        ["git", "status", "--short"],
        capture_output=True, text=True, timeout=10,
    )
    result["uncommitted"] = [line for line in status.stdout.splitlines() if line.strip()]
    result["uncommitted_count"] = len(result["uncommitted"])
    result["status_stderr"] = status.stderr
except Exception as e:
    result["errors"].append(f"status: {e}")

# git worktree list
try:
    wt = subprocess.run(
        ["git", "worktree", "list"],
        capture_output=True, text=True, timeout=10,
    )
    result["worktrees"] = [line for line in wt.stdout.splitlines() if line.strip()]
except Exception as e:
    result["errors"].append(f"worktree: {e}")

# Write file via Python (sandbox-safe)
out_dir = PROJECT_ROOT / ".trae" / "debug" / "queries"
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / "git_status.json"
out_file.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

# Also print path so we know it worked
print(f"OK: {out_file}")
print(f"branch: {result.get('branch')}")
print(f"uncommitted_count: {result.get('uncommitted_count', 0)}")
print(f"worktrees_count: {len(result.get('worktrees', []))}")
print(f"errors: {result.get('errors', [])}")
