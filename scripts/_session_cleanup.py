#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Agent 会话结束清理 hook - v3.3 新增 (P1-S3)

防止 Agent 会话意外结束后留下孤儿进程和 stale 状态。

用法:
  python scripts/_session_cleanup.py register <wt-name>   # 注册当前会话的 wt
  python scripts/_session_cleanup.py cleanup <wt-name>    # 清理指定 wt
  python scripts/_session_cleanup.py cleanup-all          # 清理所有注册的 wt
  python scripts/_session_cleanup.py status               # 查看注册状态

工作原理:
  1. Agent 启动自验证时调用 register, 记录 wt_name + PID 到 .coord/sessions.json
  2. 会话结束时 (正常或异常) 调用 cleanup, 停止服务 + 清理状态
  3. watchdog 定期扫描 sessions.json, 检测 PID 已不存在的会话, 自动清理
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wt_service import load_paths, _now_iso


def _sessions_path() -> Path:
    paths = load_paths()
    p = Path(paths.get("main_repo", ".")) / ".coord" / "sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_sessions() -> dict:
    p = _sessions_path()
    if not p.exists():
        return {"sessions": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"sessions": {}}


def _save_sessions(data: dict):
    p = _sessions_path()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_pid_alive(pid: int) -> bool:
    """检查 PID 是否还在运行"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return True  # 无法判断, 假设存活


def cmd_register(wt_name: str):
    """注册当前会话"""
    data = _load_sessions()
    pid = os.getpid()
    data["sessions"][wt_name] = {
        "pid": pid,
        "registered_at": _now_iso(),
        "status": "active",
    }
    _save_sessions(data)
    print(f"  [REGISTERED] {wt_name} (PID={pid})")
    print(f"  会话结束时请运行: _session_cleanup.py cleanup {wt_name}")


def cmd_cleanup(wt_name: str):
    """清理指定 wt 的服务"""
    data = _load_sessions()

    # 停止服务
    try:
        from _wt_service import cmd_stop
        print(f"  [CLEANUP] Stopping services for {wt_name}...")
        cmd_stop(wt_name)
    except Exception as e:
        print(f"  [WARN] stop failed: {e}")

    # 更新 sessions.json
    if wt_name in data["sessions"]:
        data["sessions"][wt_name]["status"] = "cleaned"
        data["sessions"][wt_name]["cleaned_at"] = _now_iso()
        del data["sessions"][wt_name]
        _save_sessions(data)

    # 记录事件
    try:
        from _events import cmd_log
        cmd_log("SERVICE_STOPPED", f"session cleanup for {wt_name}", wt_name)
    except Exception:
        pass

    print(f"  [DONE] {wt_name} cleaned up")


def cmd_cleanup_all():
    """清理所有注册的 wt (用于 watchdog 或手动全清理)"""
    data = _load_sessions()
    sessions = data.get("sessions", {})

    if not sessions:
        print("  No active sessions to clean up")
        return

    print(f"  Found {len(sessions)} session(s)")

    # 先检查 PID 是否还活着
    dead_sessions = []
    for wt_name, info in sessions.items():
        pid = info.get("pid")
        if pid and not _is_pid_alive(pid):
            dead_sessions.append(wt_name)
            print(f"  [DEAD] {wt_name} (PID={pid} not alive)")

    # 清理死会话
    for wt_name in dead_sessions:
        print(f"  [AUTO-CLEANUP] {wt_name} (PID dead)")
        cmd_cleanup(wt_name)

    if not dead_sessions:
        print("  All sessions still active (PIDs alive)")


def cmd_status():
    """查看注册状态"""
    data = _load_sessions()
    sessions = data.get("sessions", {})

    print("=" * 70)
    print("  SESSION REGISTRY")
    print(f"  Generated: {_now_iso()}")
    print("=" * 70)

    if not sessions:
        print("  No active sessions")
        return

    for wt_name, info in sessions.items():
        pid = info.get("pid", "?")
        registered = info.get("registered_at", "?")[:19]
        alive = _is_pid_alive(pid) if isinstance(pid, int) else "?"
        status = info.get("status", "?")

        alive_str = "ALIVE" if alive else "DEAD" if alive is False else "?"
        print(f"\n  [{status}] {wt_name}")
        print(f"    PID: {pid} ({alive_str})")
        print(f"    Registered: {registered}")

    print(f"\n  Dead sessions can be cleaned: _session_cleanup.py cleanup-all")


def main():
    parser = argparse.ArgumentParser(description="Session cleanup hook (v3.3 P1-S3)")
    parser.add_argument("command", choices=["register", "cleanup", "cleanup-all", "status"])
    parser.add_argument("wt_name", nargs="?")
    args = parser.parse_args()

    if args.command == "register":
        if not args.wt_name:
            print("Usage: _session_cleanup.py register <wt-name>")
            return 1
        cmd_register(args.wt_name)
    elif args.command == "cleanup":
        if not args.wt_name:
            print("Usage: _session_cleanup.py cleanup <wt-name>")
            return 1
        cmd_cleanup(args.wt_name)
    elif args.command == "cleanup-all":
        cmd_cleanup_all()
    elif args.command == "status":
        cmd_status()


if __name__ == "__main__":
    sys.exit(main() or 0)
