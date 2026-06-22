#!/usr/bin/env python3
"""
V3.5 sandbox watchdog - 主动监控 + 趋势检测 + 早期预警

Background:
    sandbox_health.py 是"快照式"检查：调用一次、看一次状态。
    但 L5 sandbox 故障往往是渐进式：
        OK → DEGRADED → BLOCKED
    单次检查无法捕捉"正在恶化"的趋势。

    本脚本提供:
    1. 周期性轮询 (默认 30s)
    2. 趋势检测 (连续 N 次 DEGRADED 触发 WARNING)
    3. 状态机: 跟踪 OK -> DEGRADED -> BLOCKED 转换
    4. 早期预警: 在进入 BLOCKED 之前主动提醒
    5. 状态文件: 写入 .trae/debug/watchdog/state.json 供其他工具读取
    6. 历史日志: .trae/debug/watchdog/history.jsonl 记录所有变化

Usage (CLI):
    # 后台启动监控 (推荐在 SessionStart hook 启动)
    python scripts/debug/sandbox_watchdog.py start

    # 单次检查并打印状态
    python scripts/debug/sandbox_watchdog.py check

    # 读取当前状态
    python scripts/debug/sandbox_watchdog.py status

    # 读取最近 20 条历史
    python scripts/debug/sandbox_watchdog.py history --limit 20

    # 自定义轮询间隔运行 (前台)
    python scripts/debug/sandbox_watchdog.py run --interval 15

Usage (as module):
    from scripts.debug.sandbox_watchdog import SandboxWatchdog
    with SandboxWatchdog(interval=30) as wd:
        state = wd.current_state
        print(state.level)  # OK / DEGRADED / BLOCKED
        print(state.trend)  # STABLE / WORSENING / RECOVERING

Output:
    - State file: .trae/debug/watchdog/state.json
    - History:    .trae/debug/watchdog/history.jsonl
    - Alarms:     .trae/debug/watchdog/alarms.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paths - use sandbox_safe's robust project root finder
SCRIPT_DIR = Path(__file__).resolve().parent
try:
    from scripts.debug.utils.sandbox_safe import (
        DEBUG_DIR as _SS_DEBUG_DIR,
        PROJECT_ROOT as _SS_PROJECT_ROOT,
    )
    PROJECT_ROOT = _SS_PROJECT_ROOT
    DEBUG_DIR = _SS_DEBUG_DIR
except Exception:
    # Fallback: walk up to project root
    PROJECT_ROOT = SCRIPT_DIR.parent.parent
    DEBUG_DIR = PROJECT_ROOT / ".trae" / "debug"

WATCHDOG_DIR = DEBUG_DIR / "watchdog"
STATE_FILE = WATCHDOG_DIR / "state.json"
HISTORY_FILE = WATCHDOG_DIR / "history.jsonl"
ALARMS_FILE = WATCHDOG_DIR / "alarms.jsonl"
PID_FILE = WATCHDOG_DIR / "watchdog.pid"

# Health check script
SANDBOX_HEALTH_SCRIPT = SCRIPT_DIR / "sandbox_health.py"

# Trend detection thresholds
DEGRADED_THRESHOLD = 2  # 连续 N 次 DEGRADED 触发 WARNING
BLOCKED_THRESHOLD = 1   # 连续 N 次 BLOCKED 触发 CRITICAL
WORSENING_WINDOW = 5    # 评估趋势的窗口大小


class StateLevel(str, Enum):
    """Sandbox state levels"""
    OK = "OK"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class Trend(str, Enum):
    """State trend over recent checks"""
    STABLE = "STABLE"
    WORSENING = "WORSENING"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"


@dataclass
class CheckResult:
    """Single sandbox health check result"""
    timestamp: str
    level: str  # OK / DEGRADED / BLOCKED / UNKNOWN
    checks: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WatchdogState:
    """Current watchdog state"""
    level: str = "UNKNOWN"
    trend: str = "UNKNOWN"
    last_check: Optional[str] = None
    consecutive_degraded: int = 0
    consecutive_blocked: int = 0
    consecutive_ok: int = 0
    total_checks: int = 0
    state_changes: int = 0
    last_transition: Optional[str] = None
    last_alarm: Optional[str] = None
    last_alarm_level: Optional[str] = None
    watchdog_started: Optional[str] = None
    interval_seconds: int = 30
    pid: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _ensure_dirs() -> None:
    """Ensure watchdog directory exists."""
    WATCHDOG_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    """ISO timestamp."""
    return datetime.now().isoformat()


def _run_sandbox_health() -> CheckResult:
    """
    Run sandbox_health.py and parse the result.

    This is a sandbox-safe version: it reads the JSON output file
    produced by sandbox_health.py rather than relying on stdout.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    expected_prefix = f"sandbox_health_report_{ts}"

    try:
        # Use subprocess but with explicit timeout; sandbox_health.py
        # writes to .trae/debug/queries/ which we then read.
        result = subprocess.run(
            [sys.executable, str(SANDBOX_HEALTH_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(PROJECT_ROOT),
        )

        # Try to parse the latest sandbox_health_report_*.json
        health_dir = DEBUG_DIR / "queries"
        if not health_dir.exists():
            return CheckResult(
                timestamp=_now_iso(),
                level="UNKNOWN",
                error="health queries dir not found",
            )

        candidates = sorted(
            health_dir.glob("sandbox_health_report_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        # Take the first one written after this call
        for candidate in candidates:
            if candidate.stat().st_mtime >= time.time() - 30:
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    level = data.get("overall_state", "UNKNOWN")
                    return CheckResult(
                        timestamp=_now_iso(),
                        level=level,
                        checks=data.get("tests", {}),
                    )
                except Exception as e:
                    return CheckResult(
                        timestamp=_now_iso(),
                        level="UNKNOWN",
                        error=f"parse error: {e}",
                    )

        # Fallback: returncode-based
        return CheckResult(
            timestamp=_now_iso(),
            level="OK" if result.returncode == 0 else ("BLOCKED" if result.returncode == 2 else "DEGRADED"),
            checks={},
            error=f"returncode={result.returncode}, no JSON found",
        )

    except subprocess.TimeoutExpired:
        return CheckResult(timestamp=_now_iso(), level="BLOCKED", error="health check timeout")
    except FileNotFoundError:
        return CheckResult(timestamp=_now_iso(), level="UNKNOWN", error="sandbox_health.py not found")
    except Exception as e:
        return CheckResult(timestamp=_now_iso(), level="UNKNOWN", error=str(e))


def _read_state() -> WatchdogState:
    """Read current state from state file."""
    if not STATE_FILE.exists():
        return WatchdogState()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return WatchdogState(**data)
    except Exception:
        return WatchdogState()


def _write_state(state: WatchdogState) -> None:
    """Write state to file (sandbox-safe)."""
    _ensure_dirs()
    try:
        STATE_FILE.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        # Last resort: append to history as failure marker
        try:
            with open(ALARMS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": _now_iso(),
                    "alarm": "STATE_WRITE_FAILED",
                    "error": str(e),
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass


def _append_history(result: CheckResult, state: WatchdogState) -> None:
    """Append check result to history log."""
    _ensure_dirs()
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": result.timestamp,
                "level": result.level,
                "trend": state.trend,
                "consecutive_degraded": state.consecutive_degraded,
                "consecutive_blocked": state.consecutive_blocked,
                "total_checks": state.total_checks,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _append_alarm(level: str, message: str, state: WatchdogState) -> None:
    """Append alarm to alarms log."""
    _ensure_dirs()
    try:
        with open(ALARMS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": _now_iso(),
                "alarm": level,
                "message": message,
                "state": state.to_dict(),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _compute_trend(history: List[str]) -> Trend:
    """
    Compute trend from recent level history.

    Rules:
    - If all same: STABLE
    - If recent < earlier: WORSENING (OK < DEGRADED < BLOCKED in rank)
    - If recent > earlier: RECOVERING
    """
    if len(history) < 2:
        return Trend.UNKNOWN

    rank = {StateLevel.OK.value: 0, StateLevel.DEGRADED.value: 1, StateLevel.BLOCKED.value: 2, StateLevel.UNKNOWN.value: -1}

    window = history[-WORSENING_WINDOW:]
    recent_half = window[len(window) // 2:]
    earlier_half = window[:len(window) // 2]

    recent_avg = sum(rank.get(x, -1) for x in recent_half) / max(len(recent_half), 1)
    earlier_avg = sum(rank.get(x, -1) for x in earlier_half) / max(len(earlier_half), 1)

    if abs(recent_avg - earlier_avg) < 0.5:
        return Trend.STABLE
    elif recent_avg > earlier_avg:
        return Trend.WORSENING
    else:
        return Trend.RECOVERING


def _evaluate_alarms(result: CheckResult, state: WatchdogState) -> Optional[tuple]:
    """
    Evaluate whether an alarm should be raised.

    Returns:
        (level, message) tuple if alarm, else None.
        level is "WARNING" or "CRITICAL"
    """
    level = result.level

    # CRITICAL: BLOCKED state detected
    if level == StateLevel.BLOCKED.value and state.consecutive_blocked >= BLOCKED_THRESHOLD:
        return (
            "CRITICAL",
            f"L5 sandbox is BLOCKED (consecutive={state.consecutive_blocked}). "
            f"User should restart Trae IDE. Total checks: {state.total_checks}.",
        )

    # WARNING: consecutive DEGRADED exceeds threshold
    if level == StateLevel.DEGRADED.value and state.consecutive_degraded >= DEGRADED_THRESHOLD:
        return (
            "WARNING",
            f"L5 sandbox DEGRADED for {state.consecutive_degraded} consecutive checks. "
            f"Trend: {state.trend}. Consider switching to file-based output.",
        )

    # WARNING: trend worsening
    if state.trend == Trend.WORSENING.value and state.total_checks >= WORSENING_WINDOW:
        return (
            "WARNING",
            f"Sandbox trend is WORSENING over last {WORSENING_WINDOW} checks. "
            f"Current: {level}. Take preventive measures.",
        )

    return None


def _is_running() -> bool:
    """Check if a watchdog process is already running via PID file."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        # Windows: use os.kill with signal 0
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        # Process not running, clean up stale PID file
        try:
            PID_FILE.unlink()
        except Exception:
            pass
        return False


class SandboxWatchdog:
    """
    Watchdog controller - manages periodic sandbox health checks.

    Usage:
        wd = SandboxWatchdog(interval=30)
        wd.start()  # Background
        # ... or ...
        with SandboxWatchdog(interval=30) as wd:
            state = wd.current_state
    """

    def __init__(self, interval: int = 30, alarm_callback=None):
        self.interval = interval
        self.alarm_callback = alarm_callback
        self.state = _read_state()
        if not self.state.watchdog_started:
            self.state.watchdog_started = _now_iso()
        self.state.interval_seconds = interval
        self._stop = False
        self._history: List[str] = []  # recent levels for trend

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    @property
    def current_state(self) -> WatchdogState:
        return self.state

    def _update_history(self, level: str) -> None:
        """Track recent levels for trend analysis."""
        self._history.append(level)
        if len(self._history) > WORSENING_WINDOW * 2:
            self._history = self._history[-WORSENING_WINDOW * 2:]

    def tick(self) -> CheckResult:
        """
        Run a single health check tick and update state.

        Returns the CheckResult for this tick.
        """
        result = _run_sandbox_health()
        prev_level = self.state.level

        # Update counters
        self.state.total_checks += 1
        if result.level == StateLevel.BLOCKED.value:
            self.state.consecutive_blocked += 1
            self.state.consecutive_degraded = 0
            self.state.consecutive_ok = 0
        elif result.level == StateLevel.DEGRADED.value:
            self.state.consecutive_degraded += 1
            self.state.consecutive_blocked = 0
            self.state.consecutive_ok = 0
        elif result.level == StateLevel.OK.value:
            self.state.consecutive_ok += 1
            self.state.consecutive_degraded = 0
            self.state.consecutive_blocked = 0
        else:
            # UNKNOWN: don't reset counters but don't increase them either
            pass

        # Detect state transition
        if prev_level != result.level and prev_level != "UNKNOWN":
            self.state.state_changes += 1
            self.state.last_transition = _now_iso()

        # Update trend
        self._update_history(result.level)
        self.state.trend = _compute_trend(self._history).value

        # Set level
        self.state.level = result.level
        self.state.last_check = result.timestamp
        self.state.pid = os.getpid()

        # Evaluate alarms
        alarm = _evaluate_alarms(result, self.state)
        if alarm:
            self.state.last_alarm = _now_iso()
            self.state.last_alarm_level = alarm[0]
            _append_alarm(alarm[0], alarm[1], self.state)
            if self.alarm_callback:
                try:
                    self.alarm_callback(alarm[0], alarm[1], self.state)
                except Exception:
                    pass

        # Persist
        _write_state(self.state)
        _append_history(result, self.state)

        return result

    def run(self) -> None:
        """Run watchdog loop until interrupted."""
        # Write PID file
        _ensure_dirs()
        try:
            PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass

        # Signal handler
        def handle_stop(signum, frame):
            self._stop = True
        try:
            signal.signal(signal.SIGINT, handle_stop)
            signal.signal(signal.SIGTERM, handle_stop)
        except (ValueError, AttributeError):
            # SIGTERM not available on Windows in some cases
            pass

        try:
            while not self._stop:
                result = self.tick()
                level = result.level
                ts = datetime.now().strftime("%H:%M:%S")
                # Print short status; file is the real channel
                try:
                    if level == StateLevel.OK.value:
                        print(f"[{ts}] [OK] {level} (trend={self.state.trend})", flush=True)
                    elif level == StateLevel.DEGRADED.value:
                        print(
                            f"[{ts}] [!] {level} consecutive={self.state.consecutive_degraded} "
                            f"(trend={self.state.trend})",
                            flush=True,
                        )
                    elif level == StateLevel.BLOCKED.value:
                        print(
                            f"[{ts}] [X] {level} consecutive={self.state.consecutive_blocked} "
                            f"- RESTART TRAE IDE",
                            flush=True,
                        )
                    else:
                        print(f"[{ts}] [?] {level}: {result.error}", flush=True)
                except Exception:
                    pass

                time.sleep(self.interval)
        finally:
            # Cleanup PID file
            try:
                if PID_FILE.exists():
                    pid = int(PID_FILE.read_text(encoding="utf-8").strip())
                    if pid == os.getpid():
                        PID_FILE.unlink()
            except Exception:
                pass


# CLI subcommands --------------------------------------------------------

def cmd_check(args) -> int:
    """Run a single check and print result."""
    wd = SandboxWatchdog(interval=0)
    result = wd.tick()

    if args.json:
        print(json.dumps({
            "result": result.to_dict(),
            "state": wd.current_state.to_dict(),
        }, ensure_ascii=False, indent=2, default=str))
    else:
        level = result.level
        icon = {
            "OK": "[OK]",
            "DEGRADED": "[!]",
            "BLOCKED": "[X]",
            "UNKNOWN": "[?]",
        }.get(level, "[?]")
        print(f"{icon} Sandbox level: {level}")
        print(f"   Trend:          {wd.current_state.trend}")
        print(f"   Total checks:   {wd.current_state.total_checks}")
        print(f"   Consec DEGRADED: {wd.current_state.consecutive_degraded}")
        print(f"   Consec BLOCKED:  {wd.current_state.consecutive_blocked}")
        if result.error:
            print(f"   Error: {result.error}")
        # Print safe output path
        print(f"   [SAFE_OUTPUT] {STATE_FILE}")
    return 0 if level == "OK" else (2 if level == "BLOCKED" else 1)


def cmd_status(args) -> int:
    """Print current state from file."""
    state = _read_state()
    if not state.last_check:
        print("[?] No watchdog data yet. Run `python scripts/debug/sandbox_watchdog.py check` first.")
        return 1

    if args.json:
        print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        level = state.level
        icon = {
            "OK": "[OK]",
            "DEGRADED": "[!]",
            "BLOCKED": "[X]",
            "UNKNOWN": "[?]",
        }.get(level, "[?]")
        print(f"{icon} Current sandbox level: {level}")
        print(f"   Trend:            {state.trend}")
        print(f"   Last check:       {state.last_check}")
        print(f"   Total checks:     {state.total_checks}")
        print(f"   Consec DEGRADED:  {state.consecutive_degraded}")
        print(f"   Consec BLOCKED:   {state.consecutive_blocked}")
        print(f"   State changes:    {state.state_changes}")
        print(f"   Last transition:  {state.last_transition or 'none'}")
        print(f"   Last alarm:       {state.last_alarm or 'none'}")
        print(f"   Watchdog started: {state.watchdog_started}")
        print(f"   Interval:         {state.interval_seconds}s")

    return 0 if level == "OK" else (2 if level == "BLOCKED" else 1)


def cmd_history(args) -> int:
    """Print recent history."""
    if not HISTORY_FILE.exists():
        print("[?] No history file. Run `check` or `start` first.")
        return 1

    lines = []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[X] Failed to read history: {e}")
        return 1

    recent = lines[-args.limit:] if args.limit > 0 else lines
    for line in recent:
        try:
            entry = json.loads(line)
            ts = entry.get("timestamp", "?")[11:19]  # HH:MM:SS
            print(f"  {ts}  {entry.get('level', '?'):<10} trend={entry.get('trend', '?'):<10} consec_deg={entry.get('consecutive_degraded', 0)} consec_blk={entry.get('consecutive_blocked', 0)}")
        except Exception:
            continue
    print(f"\n  Total entries: {len(lines)} (showing last {len(recent)})")
    return 0


def cmd_start(args) -> int:
    """Start watchdog in background (detached)."""
    if _is_running():
        print("[X] Watchdog is already running.")
        return 1

    # Build command to spawn detached
    cmd = [sys.executable, str(Path(__file__).resolve()), "run", "--interval", str(args.interval)]
    print(f"[OK] Starting watchdog: {' '.join(cmd)}")

    # On Windows, use CREATE_NEW_PROCESS_GROUP to detach
    kwargs = {
        "cwd": str(PROJECT_ROOT),
        "stdout": subprocess.DEVNULL if hasattr(subprocess, "DEVNULL") else None,
        "stderr": subprocess.DEVNULL if hasattr(subprocess, "DEVNULL") else None,
    }

    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kwargs["close_fds"] = True

    subprocess.Popen(cmd, **kwargs)
    time.sleep(1)  # Give it a moment to start

    if _is_running():
        print("[OK] Watchdog started successfully")
        print(f"   PID file: {PID_FILE}")
        print(f"   State:    {STATE_FILE}")
    else:
        print("[!] Watchdog start command issued, but PID file not detected yet.")
        print("   Check status in a few seconds: `python scripts/debug/sandbox_watchdog.py status`")
    return 0


def cmd_stop(args) -> int:
    """Stop background watchdog."""
    if not PID_FILE.exists():
        print("[?] No PID file. Watchdog may not be running.")
        return 0

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError) as e:
        print(f"[X] Failed to read PID: {e}")
        return 1

    # Try graceful SIGTERM first
    stopped = False
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"[OK] Sent SIGTERM to PID {pid}")
        time.sleep(1)
        if not _is_running():
            stopped = True
    except OSError:
        # Process already gone
        stopped = True
    except Exception as e:
        print(f"[!] SIGTERM failed: {e}")

    # On Windows, SIGTERM often doesn't reach detached processes; use taskkill
    if not stopped and sys.platform == "win32":
        try:
            # /T = terminate child processes too
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                print(f"[OK] taskkill /F /T /PID {pid} succeeded")
                time.sleep(1)
                if not _is_running():
                    stopped = True
            else:
                print(f"[!] taskkill failed: {result.stderr.strip()}")
        except FileNotFoundError:
            print("[!] taskkill not available")
        except Exception as e:
            print(f"[!] taskkill error: {e}")

    if stopped:
        print("[OK] Watchdog stopped")
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    else:
        print("[X] Watchdog still running. Try: taskkill /F /PID " + str(pid))
        return 1
    return 0


def cmd_run(args) -> int:
    """Run watchdog in foreground."""
    if _is_running():
        print("[X] Watchdog already running. Use `stop` first or check status.")
        return 1

    wd = SandboxWatchdog(interval=args.interval)
    print(f"[OK] Starting watchdog in foreground (interval={args.interval}s)")
    print(f"   State file: {STATE_FILE}")
    print(f"   History:    {HISTORY_FILE}")
    print(f"   Press Ctrl+C to stop\n")
    wd.run()
    return 0


def cmd_alarms(args) -> int:
    """Print recent alarms."""
    if not ALARMS_FILE.exists():
        print("[?] No alarms file. (No alarms triggered yet.)")
        return 0

    lines = []
    try:
        with open(ALARMS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[X] Failed to read alarms: {e}")
        return 1

    recent = lines[-args.limit:] if args.limit > 0 else lines
    for line in recent:
        try:
            entry = json.loads(line)
            ts = entry.get("timestamp", "?")[11:19]
            level = entry.get("alarm", "?")
            msg = entry.get("message", "")[:80]
            icon = "[X]" if level == "CRITICAL" else "[!]"
            print(f"  {ts}  {icon} {level:<10} {msg}")
        except Exception:
            continue
    print(f"\n  Total alarms: {len(lines)} (showing last {len(recent)})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="V3.5 sandbox watchdog - 主动监控 + 趋势检测 + 早期预警",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # check: single health check
    p_check = sub.add_parser("check", help="Run single check + update state")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)

    # status: read current state
    p_status = sub.add_parser("status", help="Read current state from file")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    # history: show recent check history
    p_history = sub.add_parser("history", help="Show recent check history")
    p_history.add_argument("--limit", type=int, default=20, help="Number of recent entries")
    p_history.set_defaults(func=cmd_history)

    # alarms: show triggered alarms
    p_alarms = sub.add_parser("alarms", help="Show triggered alarms")
    p_alarms.add_argument("--limit", type=int, default=20, help="Number of recent alarms")
    p_alarms.set_defaults(func=cmd_alarms)

    # start: spawn background watchdog
    p_start = sub.add_parser("start", help="Start watchdog in background")
    p_start.add_argument("--interval", type=int, default=30, help="Check interval in seconds")
    p_start.set_defaults(func=cmd_start)

    # stop: stop background watchdog
    p_stop = sub.add_parser("stop", help="Stop background watchdog")
    p_stop.set_defaults(func=cmd_stop)

    # run: run watchdog in foreground
    p_run = sub.add_parser("run", help="Run watchdog in foreground")
    p_run.add_argument("--interval", type=int, default=30, help="Check interval in seconds")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
