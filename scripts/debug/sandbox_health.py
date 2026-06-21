"""
Sandbox health check for Trae IDE L5 isolation detection.

Background:
    Trae IDE L5 sandbox may enter a "blocking" state where:
    - Shell command stdout/stderr is silently swallowed
    - File writes via shell are blocked
    - Commands return exit 0 but produce no output or side effects

    This tool detects the L5 sandbox state by:
    1. Running shell commands and checking if output appears
    2. Writing files via shell and checking if they exist
    3. Writing files via Python (different syscall path)
    4. Reporting a comprehensive sandbox state

Usage:
    python scripts/debug/sandbox_health.py                # Full check
    python scripts/debug/sandbox_health.py --json         # JSON output to stdout
    python scripts/debug/sandbox_health.py --no-stdout    # File output only
    python scripts/debug/sandbox_health.py --watch        # Continuous monitoring

Output:
    - Console: short status (OK / DEGRADED / BLOCKED)
    - File: .trae/debug/sandbox_health_report.json (full report)
    - File: .trae/debug/sandbox_health.log (timestamped log)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Allow running as standalone script
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.debug.utils.sandbox_safe import (
        DEBUG_DIR,
        QUERIES_DIR,
        MARKERS_DIR,
        PROJECT_ROOT as _SS_ROOT,
        check_sandbox_via_files,
        file_marker,
        log_sandbox_event,
        output,
    )
except ImportError:
    # Standalone fallback
    DEBUG_DIR = PROJECT_ROOT / ".trae" / "debug"
    QUERIES_DIR = DEBUG_DIR / "queries"
    MARKERS_DIR = DEBUG_DIR / "markers"
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    QUERIES_DIR.mkdir(parents=True, exist_ok=True)
    MARKERS_DIR.mkdir(parents=True, exist_ok=True)

    def check_sandbox_via_files():
        test_file = DEBUG_DIR / f"_test_{int(time.time()*1000)}.txt"
        result = {"file_write_ok": False, "file_read_ok": False}
        try:
            test_file.write_text("test", encoding="utf-8")
            result["file_write_ok"] = test_file.exists()
            if result["file_write_ok"]:
                result["file_read_ok"] = test_file.read_text(encoding="utf-8") == "test"
                test_file.unlink()
        except Exception as e:
            result["error"] = str(e)
        return result

    def file_marker(name, state, extra=None):
        marker_path = MARKERS_DIR / f"{name}.state.json"
        data = {"name": name, "state": state, "timestamp": datetime.now().isoformat()}
        if extra:
            data["extra"] = extra
        marker_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return marker_path

    def log_sandbox_event(event, **details):
        log_file = DEBUG_DIR / "sandbox_logs" / "events.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {"timestamp": datetime.now().isoformat(), "event": event, **details}
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return log_file

    def output(data, prefix="debug", also_stdout=True, indent=2):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = QUERIES_DIR / f"{prefix}_{ts}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=indent, default=str), encoding="utf-8")
        if also_stdout:
            try:
                print(f"[OK] {path.name}", flush=True)
            except Exception:
                pass
        return path


def test_shell_stdout() -> dict:
    """Test if shell command stdout is being delivered."""
    marker = f"SANDBOX_TEST_{int(time.time())}"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Write-Host {marker}"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        stdout_has_marker = marker in (result.stdout or "")
        return {
            "exit_code": result.returncode,
            "stdout_length": len(result.stdout or ""),
            "stderr_length": len(result.stderr or ""),
            "stdout_has_marker": stdout_has_marker,
            "ok": stdout_has_marker,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "ok": False, "error": "timeout"}
    except FileNotFoundError:
        return {"exit_code": -1, "ok": False, "error": "powershell not found"}
    except Exception as e:
        return {"exit_code": -1, "ok": False, "error": str(e)}


def test_shell_file_write() -> dict:
    """Test if shell can write a file that we can then read back."""
    ts = int(time.time() * 1000)
    test_path = PROJECT_ROOT / ".trae" / "debug" / f"_shell_write_test_{ts}.txt"
    expected = f"shell_test_{ts}"
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f'Set-Content -Path "{test_path}" -Value "{expected}" -Encoding UTF8',
            ],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        if test_path.exists():
            actual = test_path.read_text(encoding="utf-8").strip()
            ok = actual == expected
            try:
                test_path.unlink()
            except Exception:
                pass
            return {"ok": ok, "exit_code": result.returncode, "match": actual == expected}
        return {"ok": False, "exit_code": result.returncode, "error": "file not created"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def test_python_io() -> dict:
    """Test Python's own I/O (different syscall path from shell)."""
    return check_sandbox_via_files()


def test_git_operations() -> dict:
    """Test if git operations are returning output."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        return {
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout_length": len(result.stdout or ""),
            "has_output": bool((result.stdout or "").strip()),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def compute_overall_state(tests: dict) -> str:
    """Compute overall sandbox state from individual tests."""
    shell_stdout_ok = tests.get("shell_stdout", {}).get("ok", False)
    shell_write_ok = tests.get("shell_write", {}).get("ok", False)
    python_io_ok = tests.get("python_io", {}).get("file_write_ok", False)
    git_ok = tests.get("git_operations", {}).get("ok", False)

    if shell_stdout_ok and shell_write_ok and git_ok:
        return "OK"
    if not python_io_ok:
        return "BLOCKED"  # Even Python I/O is broken
    if not shell_stdout_ok and not shell_write_ok:
        return "DEGRADED"  # Shell blocked but Python I/O works
    return "DEGRADED"


def run_full_check(also_stdout: bool = True) -> dict:
    """Run the full sandbox health check and return a report dict."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "project_root": str(PROJECT_ROOT),
        "python_version": sys.version,
        "pid": os.getpid(),
        "tests": {
            "shell_stdout": test_shell_stdout(),
            "shell_write": test_shell_file_write(),
            "python_io": test_python_io(),
            "git_operations": test_git_operations(),
        },
    }
    report["overall_state"] = compute_overall_state(report["tests"])

    # Recommendations
    recs = []
    state = report["overall_state"]
    if state == "OK":
        recs.append("[OK] Sandbox is healthy. Normal operations should work.")
    elif state == "DEGRADED":
        recs.append("[!] Shell stdout is blocked but Python I/O works.")
        recs.append("[!] Recommendation: Use Write/Read tools instead of shell commands.")
        recs.append("[!] Debug output should go to .trae/debug/queries/ files.")
    elif state == "BLOCKED":
        recs.append("[X] Severe sandbox degradation. Even Python I/O may be unstable.")
        recs.append("[X] Recommendation: Restart Trae IDE to recover.")
        recs.append("[X] Avoid all shell commands until recovery.")
    report["recommendations"] = recs

    # Write report to file
    output(report, prefix="sandbox_health_report", also_stdout=also_stdout)

    # Log event
    log_sandbox_event("sandbox_health_check", state=state, **report["tests"])

    return report


def watch_loop(interval: int = 30) -> None:
    """Continuously monitor sandbox state at given interval."""
    print(f"[WATCH] Monitoring sandbox every {interval}s. Ctrl+C to stop.")
    file_marker("sandbox_watch", "running", extra={"interval": interval})
    try:
        while True:
            report = run_full_check(also_stdout=False)
            state = report["overall_state"]
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] {state}", flush=True)
            if state == "BLOCKED":
                print("[!] Sandbox blocked. Consider restarting Trae IDE.", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        file_marker("sandbox_watch", "stopped")
        print("\n[WATCH] Stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Trae IDE L5 sandbox health check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument(
        "--no-stdout",
        action="store_true",
        help="Skip stdout, only write to file (sandbox-safe mode)",
    )
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="Continuously monitor")
    args = parser.parse_args()

    if args.watch:
        watch_loop(args.watch)
        return

    also_stdout = not args.no_stdout
    if args.json:
        also_stdout = False

    report = run_full_check(also_stdout=also_stdout)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    # Print short status
    state = report["overall_state"]
    if state == "OK":
        print(f"\n[OK] Sandbox state: {state}")
    elif state == "DEGRADED":
        print(f"\n[!] Sandbox state: {state}")
        for r in report["recommendations"]:
            print(f"  {r}")
    else:
        print(f"\n[X] Sandbox state: {state}")
        for r in report["recommendations"]:
            print(f"  {r}")

    # Exit code reflects state for scripting
    if state == "OK":
        sys.exit(0)
    elif state == "DEGRADED":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
