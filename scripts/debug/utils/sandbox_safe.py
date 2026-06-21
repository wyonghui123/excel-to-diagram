"""
Sandbox-safe I/O utilities for Trae IDE L5 sandbox bypass.

Background:
    Trae IDE L5 sandbox may completely block shell command side effects:
    - stdout/stderr are silently swallowed
    - File writes via PowerShell/Python are blocked
    - Even MCP Filesystem write_file may be blocked in some states
    - But the command returns exit 0 (false success)

Strategy:
    - Use Write tool / Read tool (not affected by sandbox)
    - Output to well-known file paths in .trae/debug/
    - Always return short status messages that are less likely to be swallowed
    - Provide detection helpers to identify sandbox state

Usage:
    from scripts.debug.utils.sandbox_safe import output, read_output, file_marker

    # Write structured data
    output({"key": "value"}, prefix="query_result")

    # Read previous output
    data = read_output("query_result_20260621_123456_123.json")

    # Mark execution state
    file_marker("my_task", "running")
    file_marker("my_task", "done", extra={"count": 42})
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Project root resolution: walk up until we find .trae/ or .git/
def _find_project_root() -> Path:
    """Find project root by walking up directories."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / ".trae").is_dir() or (p / ".git").exists():
            return p
    # Fallback: use cwd
    return cwd


PROJECT_ROOT = _find_project_root()
DEBUG_DIR = PROJECT_ROOT / ".trae" / "debug"
QUERIES_DIR = DEBUG_DIR / "queries"
MARKERS_DIR = DEBUG_DIR / "markers"
SANDBOX_LOGS_DIR = DEBUG_DIR / "sandbox_logs"

# Ensure dirs exist
for _d in (DEBUG_DIR, QUERIES_DIR, MARKERS_DIR, SANDBOX_LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _timestamp() -> str:
    """Generate a sortable timestamp for filenames."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # ms precision


def output(
    data: Any,
    prefix: str = "debug",
    *,
    also_stdout: bool = True,
    indent: int = 2,
) -> Path:
    """
    Write data to a file in .trae/debug/queries/ and optionally print to stdout.

    This is the sandbox-safe replacement for print(json.dumps(...)).
    The returned file path can be passed to the Read tool to retrieve the data.

    Args:
        data: Any JSON-serializable object
        prefix: Filename prefix (e.g., "user_context", "query_result")
        also_stdout: If True, also print short path to stdout
        indent: JSON indentation level

    Returns:
        Path to the written file
    """
    filename = f"{prefix}_{_timestamp()}.json"
    file_path = QUERIES_DIR / filename

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent, default=str)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        # Fallback: write error marker
        err_path = MARKERS_DIR / f"{prefix}_ERROR_{_timestamp()}.txt"
        err_path.write_text(
            f"output() failed: {e}\n{traceback.format_exc()}\n"
            f"Data was: {repr(data)[:500]}",
            encoding="utf-8",
        )
        if also_stdout:
            print(f"[SANDBOX_SAFE_ERROR] {err_path}")
        return err_path

    if also_stdout:
        # Short message, less likely to be swallowed than full JSON
        try:
            print(f"[OK] {file_path.name}")
            sys.stdout.flush()
        except Exception:
            pass

    return file_path


def read_output(filename: str) -> Optional[Any]:
    """
    Read a previously written output file from .trae/debug/queries/.

    This is the sandbox-safe replacement for parsing captured stdout.
    Use the Read tool to read the file directly, OR use this function.

    Args:
        filename: Just the filename (not full path), e.g., "user_context_20260621.json"

    Returns:
        Parsed JSON data, or None if file not found
    """
    file_path = QUERIES_DIR / filename
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e), "_file": str(file_path)}


def list_outputs(prefix: Optional[str] = None, limit: int = 20) -> list[Path]:
    """
    List recent output files, optionally filtered by prefix.

    Args:
        prefix: If given, only return files starting with this prefix
        limit: Max number of files to return (most recent first)

    Returns:
        List of file paths, most recent first
    """
    pattern = f"{prefix}_*.json" if prefix else "*.json"
    files = sorted(QUERIES_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def file_marker(
    name: str,
    state: str,
    *,
    extra: Optional[dict] = None,
) -> Path:
    """
    Write a state marker file for tracking long-running operations.

    Useful for detecting sandbox issues: if the marker stays "running"
    but the calling code claims "done", the sandbox probably swallowed output.

    Args:
        name: Marker name (e.g., "backend_restart", "db_query")
        state: State string (e.g., "running", "done", "failed")
        extra: Optional dict to include in the marker

    Returns:
        Path to the marker file
    """
    marker_path = MARKERS_DIR / f"{name}.state.json"
    data = {
        "name": name,
        "state": state,
        "timestamp": datetime.now().isoformat(),
        "pid": os.getpid(),
    }
    if extra:
        data["extra"] = extra
    with open(marker_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    return marker_path


def read_marker(name: str) -> Optional[dict]:
    """
    Read a state marker file.

    Args:
        name: Marker name

    Returns:
        Marker data dict, or None if not found
    """
    marker_path = MARKERS_DIR / f"{name}.state.json"
    if not marker_path.exists():
        return None
    try:
        with open(marker_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def check_sandbox_via_files() -> dict:
    """
    Detect sandbox L5 state by writing and reading test files.

    This works even when shell commands are blocked because we use
    Python's built-in file I/O, which goes through a different syscall path.

    Returns:
        Dict with sandbox state detection results:
        - file_write_ok: True if Python can write files
        - file_read_ok: True if Python can read files
        - cwd_writable: True if current directory is writable
        - debug_dir_writable: True if .trae/debug/ is writable
    """
    test_file = DEBUG_DIR / f"_sandbox_test_{_timestamp()}.txt"
    test_content = f"sandbox_test_{int(time.time())}"

    result = {
        "test_time": datetime.now().isoformat(),
        "file_write_ok": False,
        "file_read_ok": False,
        "cwd_writable": False,
        "debug_dir_writable": False,
        "test_file": str(test_file),
    }

    # Test 1: Write to debug dir
    try:
        test_file.write_text(test_content, encoding="utf-8")
        if test_file.exists():
            result["file_write_ok"] = True
            result["debug_dir_writable"] = True
    except Exception as e:
        result["write_error"] = str(e)

    # Test 2: Read back
    try:
        if test_file.exists():
            content = test_file.read_text(encoding="utf-8")
            result["file_read_ok"] = content == test_content
    except Exception as e:
        result["read_error"] = str(e)

    # Test 3: Write to cwd
    try:
        cwd_test = Path.cwd() / f"_sandbox_cwd_test_{_timestamp()}.txt"
        cwd_test.write_text("test", encoding="utf-8")
        if cwd_test.exists():
            result["cwd_writable"] = True
            cwd_test.unlink()
    except Exception as e:
        result["cwd_error"] = str(e)

    # Cleanup
    try:
        if test_file.exists():
            test_file.unlink()
    except Exception:
        pass

    return result


def log_sandbox_event(event: str, **details) -> Path:
    """
    Append a sandbox-related event to the sandbox event log.

    Useful for tracking when sandbox issues occur across the session.

    Args:
        event: Event name (e.g., "stdout_swallowed", "file_write_blocked")
        **details: Additional context to log

    Returns:
        Path to the log file
    """
    log_file = SANDBOX_LOGS_DIR / "events.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        "pid": os.getpid(),
        **details,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()
    return log_file


# Convenience: print wrapper that logs to file if sandbox swallows
def safe_print(message: str, *, prefix: str = "info") -> bool:
    """
    Print to stdout AND log to file. Returns True if stdout succeeded.

    Use this for important status messages that you MUST see even if
    the sandbox is blocking stdout.

    The file can be read with the Read tool as a backup channel.
    """
    log_file = DEBUG_DIR / "safe_print.log"
    success = False
    try:
        print(message, flush=True)
        success = True
    except Exception as e:
        log_sandbox_event("stdout_blocked", message=message, error=str(e))

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {prefix}: {message}\n")
            f.flush()
    except Exception:
        pass

    return success


__all__ = [
    "DEBUG_DIR",
    "QUERIES_DIR",
    "MARKERS_DIR",
    "SANDBOX_LOGS_DIR",
    "PROJECT_ROOT",
    "output",
    "read_output",
    "list_outputs",
    "file_marker",
    "read_marker",
    "check_sandbox_via_files",
    "log_sandbox_event",
    "safe_print",
]
