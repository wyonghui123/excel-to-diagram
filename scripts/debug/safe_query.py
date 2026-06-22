#!/usr/bin/env python3
"""
V3.5 sandbox-safe query wrapper - 统一调试入口

This is a sandbox-aware Python wrapper that:
1. Auto-detects L5 sandbox state before executing
2. Routes output to file (sandbox-safe) instead of stdout
3. Provides unified interface for all debug queries
4. Logs to .trae/debug/sandbox_logs/ for audit

Background:
    Trae IDE's L5 sandbox can swallow stdout, file writes, and other side effects.
    This wrapper:
    - Pre-checks sandbox health (via scripts/debug/sandbox_health.py)
    - If sandbox is BLOCKED, refuses to run and tells user to restart IDE
    - If sandbox is DEGRADED, runs but warns
    - If sandbox is OK, runs normally and writes output to file

Usage (as a module):
    from scripts.debug.safe_query import SafeQuery
    with SafeQuery("my_query", sandbox_aware=True) as sq:
        result = some_long_computation()
        sq.write(result)
        # Auto writes to .trae/debug/queries/my_query_<ts>.json

Usage (as a CLI):
    # Run a Python query script in sandbox-safe mode
    python scripts/debug/safe_query.py run my_script.py arg1 arg2

    # Pre-check sandbox only
    python scripts/debug/safe_query.py health

    # Run with explicit safe-output
    python scripts/debug/safe_query.py safe-output my_script.py arg1 arg2
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEBUG_DIR = PROJECT_ROOT / ".trae" / "debug"
QUERIES_DIR = DEBUG_DIR / "queries"
SANDBOX_LOGS_DIR = DEBUG_DIR / "sandbox_logs"
MARKERS_DIR = DEBUG_DIR / "markers"

SANDBOX_HEALTH_SCRIPT = SCRIPT_DIR / "sandbox_health.py"
SESSION_STATUS_FILE = DEBUG_DIR / "session_start_status.json"


def _ensure_dirs():
    for d in [DEBUG_DIR, QUERIES_DIR, SANDBOX_LOGS_DIR, MARKERS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _log_event(event_type: str, data: Dict[str, Any]):
    """Log sandbox event for audit trail"""
    _ensure_dirs()
    log_file = SANDBOX_LOGS_DIR / f"{datetime.now().strftime('%Y%m%d')}.log"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        **data,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check_sandbox_health() -> Dict[str, Any]:
    """
    Run sandbox_health.py and parse result.

    Returns:
        Dict with keys: status (OK/DEGRADED/BLOCKED), checks: {...}
    """
    if not SANDBOX_HEALTH_SCRIPT.exists():
        return {"status": "UNKNOWN", "error": "sandbox_health.py not found"}

    try:
        result = subprocess.run(
            [sys.executable, str(SANDBOX_HEALTH_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        # Try to parse JSON from last line
        lines = result.stdout.strip().splitlines()
        if lines:
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        pass
        return {
            "status": "UNKNOWN",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def read_session_status() -> Optional[Dict[str, Any]]:
    """Read session_start_status.json if available"""
    if not SESSION_STATUS_FILE.exists():
        return None
    try:
        with open(SESSION_STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class SafeQuery:
    """
    Context manager for sandbox-safe debug queries.

    Usage:
        with SafeQuery("my_query") as sq:
            data = some_query()
            sq.write(data)
    """

    def __init__(
        self,
        prefix: str,
        output_dir: Optional[Path] = None,
        sandbox_aware: bool = True,
        fail_on_blocked: bool = False,
    ):
        self.prefix = prefix
        self.output_dir = Path(output_dir) if output_dir else QUERIES_DIR
        self.sandbox_aware = sandbox_aware
        self.fail_on_blocked = fail_on_blocked
        self.output_file: Optional[Path] = None
        self.health: Optional[Dict[str, Any]] = None
        self._buffer: List[Any] = []

    def __enter__(self):
        _ensure_dirs()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self.sandbox_aware:
            self.health = check_sandbox_health()
            status = self.health.get("status", "UNKNOWN")
            _log_event("safe_query_start", {
                "prefix": self.prefix,
                "sandbox_status": status,
            })

            if status == "BLOCKED":
                msg = (
                    f"[BLOCKED] L5 sandbox is blocked. "
                    f"User should restart Trae IDE. Skipping query '{self.prefix}'."
                )
                _log_event("safe_query_blocked", {"prefix": self.prefix})
                if self.fail_on_blocked:
                    raise RuntimeError(msg)
                else:
                    print(msg, file=sys.stderr)
            elif status == "DEGRADED":
                print(
                    f"[!] L5 sandbox DEGRADED - query '{self.prefix}' will write to file "
                    f"to bypass stdout issues.",
                    file=sys.stderr,
                )

        # Generate output filename
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        self.output_file = self.output_dir / f"{self.prefix}_{ts}.json"
        return self

    def write(self, data: Any, append: bool = False):
        """Write data to output file (and buffer for later flush)"""
        self._buffer.append(data)
        mode = "a" if append else "w"
        try:
            with open(self.output_file, mode, encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            _log_event("safe_query_write_error", {
                "prefix": self.prefix,
                "error": str(e),
            })

    def write_line(self, data: Any):
        """Append a line to output (for streaming results)"""
        mode = "a" if self.output_file and self.output_file.exists() else "w"
        try:
            with open(self.output_file, mode, encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            _log_event("safe_query_write_line_error", {
                "prefix": self.prefix,
                "error": str(e),
            })

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            error_data = {
                "error": str(exc_val),
                "traceback": traceback.format_exc(),
                "prefix": self.prefix,
                "timestamp": datetime.now().isoformat(),
            }
            _log_event("safe_query_exception", error_data)
            try:
                error_file = self.output_file.with_suffix(".error.json") if self.output_file else None
                if error_file:
                    with open(error_file, "w", encoding="utf-8") as f:
                        json.dump(error_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # Print success path so user can find it
        if self.output_file:
            print(f"[SAFE_OUTPUT] {self.output_file}")
            _log_event("safe_query_end", {
                "prefix": self.prefix,
                "output_file": str(self.output_file),
            })

        return False  # Don't suppress exceptions


def cmd_health(args):
    """Print sandbox health status"""
    health = check_sandbox_health()
    if args.json:
        print(json.dumps(health, ensure_ascii=False, indent=2))
    else:
        status = health.get("status", "UNKNOWN")
        icon = {
            "OK": "[OK]",
            "DEGRADED": "[!]",
            "BLOCKED": "[X]",
            "ERROR": "[X]",
            "UNKNOWN": "[?]",
        }.get(status, "[?]")
        print(f"{icon} Sandbox status: {status}")
        checks = health.get("checks", {})
        if checks:
            print("Checks:")
            for name, result in checks.items():
                check_icon = "[OK]" if result == "ok" else "[X]"
                print(f"  {check_icon} {name}: {result}")
    return 0 if health.get("status") == "OK" else 1


def cmd_session(args):
    """Print session start status"""
    status = read_session_status()
    if status is None:
        print("[X] session_start_status.json not found. Hook may not have run.")
        return 1

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"Branch: {status.get('git', {}).get('branch', '?')}")
        print(f"Uncommitted: {status.get('git', {}).get('file_count', '?')}")
        for service in ["backend", "frontend"]:
            svc = status.get(service, {})
            print(f"{service}: {svc.get('status', '?')} (port {svc.get('port', '?')}, PID {svc.get('pid', '?')})")
    return 0


def cmd_run(args):
    """Run a script with sandbox-safe output"""
    script = Path(args.script)
    if not script.exists():
        print(f"[X] Script not found: {script}", file=sys.stderr)
        return 1

    # If --safe-output, wrap in SafeQuery
    if args.safe_output:
        prefix = args.prefix or script.stem
        with SafeQuery(prefix, fail_on_blocked=args.fail_on_blocked) as sq:
            # Run the script and capture output
            cmd = [sys.executable, str(script)] + args.args
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=args.timeout,
                    cwd=str(PROJECT_ROOT),
                )
                sq.write({
                    "script": str(script),
                    "args": args.args,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                })
                return result.returncode
            except subprocess.TimeoutExpired:
                sq.write({"error": f"Timeout after {args.timeout}s"})
                return 124
    else:
        # Direct execution
        cmd = [sys.executable, str(script)] + args.args
        return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(
        description="V3.5 sandbox-safe query wrapper - 统一调试入口",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # health
    p_health = sub.add_parser("health", help="Check sandbox health")
    p_health.add_argument("--json", action="store_true")
    p_health.set_defaults(func=cmd_health)

    # session
    p_session = sub.add_parser("session", help="Read session start status")
    p_session.add_argument("--json", action="store_true")
    p_session.set_defaults(func=cmd_session)

    # status (auto_status 集成)
    p_status = sub.add_parser("status", help="Auto-detect environment status (uses auto_status.py)")
    p_status.add_argument("--safe-output", action="store_true", help="Write to file")
    p_status.add_argument("--json", action="store_true")
    p_status.add_argument("--watch", action="store_true", help="Watch mode")
    p_status.add_argument("--interval", type=int, default=60)
    p_status.set_defaults(func=cmd_status)

    # run
    p_run = sub.add_parser("run", help="Run a script with sandbox-safe output")
    p_run.add_argument("script", help="Script to run")
    p_run.add_argument("args", nargs="*", help="Arguments to pass")
    p_run.add_argument("--safe-output", action="store_true", help="Write output to file")
    p_run.add_argument("--prefix", help="Output file prefix")
    p_run.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    p_run.add_argument("--fail-on-blocked", action="store_true",
                       help="Exit non-zero if sandbox is blocked")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
