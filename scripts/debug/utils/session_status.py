"""
Session start status reader - Read .trae/debug/session_start_status.json

This is a sandbox-safe tool for the AI agent to query environment status
without depending on shell commands that might be swallowed by L5 sandbox.

Background:
    Trae IDE SessionStart hook writes a status JSON file:
    `.trae/debug/session_start_status.json`

    The file contains:
    - timestamp: when status was collected
    - project_root: detected project root
    - backend: {status, pid, port} for port 3010
    - frontend: {status, pid, port} for port 3004
    - git: {clean, file_count, branch}
    - worktrees: list of worktree paths

Usage:
    # As Python module
    from scripts.debug.utils.session_status import read_session_status, print_session_status
    status = read_session_status()
    print_session_status(status)

    # As CLI
    python scripts/debug/utils/session_status.py
    python scripts/debug/utils/session_status.py --json --safe-output
    python scripts/debug/utils/session_status.py --watch
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Import safe-io helper
try:
    from scripts.debug.utils.safe_io import emit_safe_output
except ImportError:
    def emit_safe_output(data, prefix, output_dir=None, also_stdout=True):
        out_dir = Path(output_dir) if output_dir else (Path(__file__).resolve().parent.parent.parent / ".trae" / "debug" / "queries")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        out_file = out_dir / f"{prefix}_{ts}.json"
        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        if also_stdout:
            print(f"[SAFE_OUTPUT] {out_file}")
        return out_file


# Project root resolution
def _find_project_root() -> Path:
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / ".trae").is_dir() or (p / ".git").exists():
            return p
    return cwd


PROJECT_ROOT = _find_project_root()
SESSION_STATUS_FILE = PROJECT_ROOT / ".trae" / "debug" / "session_start_status.json"


def read_session_status(file_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Read the session start status file.

    Args:
        file_path: Custom path, or None to use default

    Returns:
        Status dict, or None if file doesn't exist
    """
    path = file_path or SESSION_STATUS_FILE
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e), "_file": str(path)}


def format_status_human(status: Optional[Dict[str, Any]]) -> str:
    """
    Format status dict as human-readable text.

    Args:
        status: Status dict from read_session_status()

    Returns:
        Multi-line formatted string
    """
    if status is None:
        return "[X] SessionStart status file not found. Hook may not have run.\n" \
               f"Expected: {SESSION_STATUS_FILE}"

    if "_error" in status:
        return f"[X] Failed to read status: {status['_error']}"

    lines = []
    lines.append("=" * 70)
    lines.append("Session Start Status")
    lines.append("=" * 70)
    lines.append(f"  Timestamp   : {status.get('timestamp', '?')}")
    lines.append(f"  Project     : {status.get('project_root', '?')}")
    lines.append("")

    backend = status.get("backend", {})
    backend_status = backend.get("status", "unknown")
    backend_icon = "[OK]" if backend_status == "running" else "[X]"
    lines.append(f"  Backend     : {backend_icon} {backend_status} (port {backend.get('port', '?')}, PID {backend.get('pid', '?')})")

    frontend = status.get("frontend", {})
    frontend_status = frontend.get("status", "unknown")
    frontend_icon = "[OK]" if frontend_status == "running" else "[X]"
    lines.append(f"  Frontend    : {frontend_icon} {frontend_status} (port {frontend.get('port', '?')}, PID {frontend.get('pid', '?')})")
    lines.append("")

    git_info = status.get("git", {})
    git_clean = git_info.get("clean", True)
    git_icon = "[OK]" if git_clean else "[!]"
    lines.append(f"  Git         : {git_icon} branch={git_info.get('branch', '?')}, uncommitted={git_info.get('file_count', '?')} files")
    lines.append("")

    worktrees = status.get("worktrees", [])
    if worktrees:
        lines.append(f"  Worktrees   : {len(worktrees)}")
        for wt in worktrees[:10]:
            lines.append(f"    - {wt}")
        if len(worktrees) > 10:
            lines.append(f"    ... and {len(worktrees) - 10} more")
    else:
        lines.append("  Worktrees   : (none)")
    lines.append("=" * 70)
    return "\n".join(lines)


def wait_for_session_status(timeout: int = 10, poll_interval: float = 0.5) -> Optional[Dict[str, Any]]:
    """
    Wait for the session_start_status.json file to appear.

    Useful right after a new session starts, when the hook may not have
    finished writing yet.

    Args:
        timeout: Max wait time in seconds
        poll_interval: Sleep between polls in seconds

    Returns:
        Status dict, or None if timeout
    """
    start = time.time()
    while time.time() - start < timeout:
        status = read_session_status()
        if status is not None:
            return status
        time.sleep(poll_interval)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Read .trae/debug/session_start_status.json (sandbox-safe)",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--safe-output", action="store_true",
                        help="V3.5: Write to .trae/debug/queries/ (sandbox-safe)")
    parser.add_argument("--safe-output-dir", metavar="DIR", help="Custom output dir")
    parser.add_argument("--wait", type=int, metavar="SECS", default=0,
                        help="Wait up to N seconds for status file to appear")
    parser.add_argument("--watch", type=int, metavar="SECS", default=0,
                        help="Continuously watch status file, polling every N seconds")
    parser.add_argument("--file", type=Path, help="Custom status file path")
    args = parser.parse_args()

    if args.watch > 0:
        # Watch mode
        print(f"[WATCH] Monitoring session_start_status.json every {args.watch}s. Ctrl+C to stop.")
        try:
            while True:
                status = read_session_status(args.file)
                ts = datetime.now().strftime("%H:%M:%S")
                if status is None:
                    print(f"[{ts}] [X] status file not found")
                else:
                    backend = status.get("backend", {})
                    frontend = status.get("frontend", {})
                    git = status.get("git", {})
                    print(
                        f"[{ts}] "
                        f"backend={backend.get('status', '?')}, "
                        f"frontend={frontend.get('status', '?')}, "
                        f"branch={git.get('branch', '?')}, "
                        f"uncommitted={git.get('file_count', 0)}"
                    )
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\n[WATCH] Stopped.")
        return

    # Read once
    if args.wait > 0:
        status = wait_for_session_status(args.wait)
    else:
        status = read_session_status(args.file)

    if args.safe_output:
        emit_safe_output(
            {"status": status, "file": str(args.file or SESSION_STATUS_FILE)},
            prefix="session_status",
            output_dir=args.safe_output_dir,
        )
        return

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_status_human(status))


if __name__ == "__main__":
    main()
