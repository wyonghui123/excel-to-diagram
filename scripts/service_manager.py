#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一服务管理器 - 多智能体协作场景下的前后端服务管理

设计原则:
  1. service_status.json 是单一事实源（磁盘文件，跨沙箱可读）
  2. 端口检测优先于 PID 检测（sandbox 权限隔离下 Get-Process 不可靠）
  3. 所有操作幂等：start 已运行=no-op, stop 已停止=no-op
  4. 管理锁防止并发管理操作（120s 超时）
  5. 无终端依赖：使用 subprocess DETACHED_PROCESS 启动，不占用终端槽位

用法:
  python scripts/service_manager.py status     # 查看服务状态
  python scripts/service_manager.py start      # 启动前后端（幂等）
  python scripts/service_manager.py stop       # 停止前后端
  python scripts/service_manager.py restart    # 重启前后端
  python scripts/service_manager.py start-fe   # 仅启动前端
  python scripts/service_manager.py start-be   # 仅启动后端
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = PROJECT_ROOT / ".service_status.json"
LOCK_FILE = PROJECT_ROOT / ".service_manager.lock"
LOG_FILE = PROJECT_ROOT / ".service_manager.log"

SERVICES = {
    "frontend": {
        "port": 3004,
        "display_name": "Frontend (Vite)",
        "start_cmd": ["npm", "run", "dev"],
        "wait_seconds": 8,
    },
    "backend": {
        "port": 3010,
        "display_name": "Backend (Python)",
        "start_cmd": ["npm", "run", "dev:python"],
        "wait_seconds": 5,
    },
}

MANAGEMENT_LOCK_TIMEOUT = 120


def _log(msg: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _check_port(port: int) -> bool:
    """检查端口是否被监听（跨平台，不依赖 Get-Process）"""
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                return True
        except OSError:
            pass
    return False


def _read_status() -> dict:
    """读取服务状态文件"""
    if not STATUS_FILE.exists():
        return {}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_status(status: dict):
    """写入服务状态文件"""
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


def _acquire_lock() -> bool:
    """获取管理锁，防止并发管理操作"""
    deadline = time.time() + MANAGEMENT_LOCK_TIMEOUT
    while time.time() < deadline:
        try:
            if LOCK_FILE.exists():
                lock_age = time.time() - LOCK_FILE.stat().st_mtime
                if lock_age > 300:
                    LOCK_FILE.unlink(missing_ok=True)
                    _log("Cleaned stale lock file")
                else:
                    _log(f"Waiting for lock (age={lock_age:.0f}s)...")
                    time.sleep(2)
                    continue
            LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
            return True
        except OSError:
            time.sleep(2)
    _log("ERROR: Could not acquire management lock")
    return False


def _release_lock():
    """释放管理锁"""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _find_and_kill_process(port: int) -> bool:
    """根据端口查找并终止进程"""
    killed = False
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            output = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                timeout=10,
            )
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid_str = parts[-1]
                    try:
                        pid = int(pid_str)
                        if pid == 0 or pid == 4:
                            continue
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True,
                            timeout=10,
                        )
                        _log(f"Killed PID {pid} on port {port}")
                        killed = True
                    except (ValueError, subprocess.SubprocessError):
                        pass
        except subprocess.SubprocessError:
            pass
    return killed


def status_command():
    """查看服务状态"""
    status = _read_status()
    all_healthy = True

    print("\n  Service Status")
    print("  " + "=" * 50)

    for name, config in SERVICES.items():
        port = config["port"]
        is_listening = _check_port(port)
        known = status.get(name, {})
        known_pid = known.get("pid", "?")
        known_time = known.get("started_at", "?")
        healthy = "RUNNING" if is_listening else "STOPPED"

        if is_listening:
            print(f"  {config['display_name']:<25s} : {healthy}  "
                  f"(port={port}, pid={known_pid}, since={known_time})")
        else:
            print(f"  {config['display_name']:<25s} : {healthy}  "
                  f"(port={port})")
            all_healthy = False

    print("  " + "=" * 50)

    if not status:
        print("  No status file found -- services may not have been started via service_manager")
    else:
        print(f"  Status file: {STATUS_FILE}")

    if all_healthy:
        print("  Summary: ALL SERVICES HEALTHY")
    else:
        print("  Summary: SOME SERVICES NOT RUNNING")

    return 0 if all_healthy else 1


def stop_command(name: str = None):
    """停止服务"""
    if not _acquire_lock():
        return 1

    try:
        names = [name] if name else list(SERVICES.keys())
        status = _read_status()

        for svc_name in names:
            config = SERVICES[svc_name]
            port = config["port"]
            _log(f"Stopping {config['display_name']}...")

            if not _check_port(port):
                _log(f"  {config['display_name']} already stopped")
                status.pop(svc_name, None)
                continue

            # 尝试通过 PID 终止
            known = status.get(svc_name, {})
            known_pid = known.get("pid")
            killed = False

            if known_pid:
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(known_pid)],
                        capture_output=True,
                        timeout=10,
                    )
                    time.sleep(2)
                    if not _check_port(port):
                        killed = True
                        _log(f"  Stopped via PID {known_pid}")
                except subprocess.SubprocessError:
                    pass

            if not killed:
                if _find_and_kill_process(port):
                    _log(f"  Stopped via port {port} scan")

            # 等待端口释放
            for _ in range(10):
                if not _check_port(port):
                    break
                time.sleep(1)

            if _check_port(port):
                _log(f"  WARNING: Port {port} still in use after stop attempt")
            else:
                _log(f"  {config['display_name']} stopped")
                status.pop(svc_name, None)

        _write_status(status)
        return 0
    finally:
        _release_lock()


def start_command(name: str = None):
    """启动服务（幂等：已运行则跳过）"""
    if not _acquire_lock():
        return 1

    try:
        names = [name] if name else list(SERVICES.keys())
        status = _read_status()

        for svc_name in names:
            config = SERVICES[svc_name]
            port = config["port"]

            if _check_port(port):
                _log(f"{config['display_name']} already running on port {port}")
                continue

            _log(f"Starting {config['display_name']}...")

            # 使用 DETACHED_PROCESS 不占用终端槽位
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(
                config["start_cmd"],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )

            # 等待端口就绪
            ready = False
            for i in range(config["wait_seconds"] * 2):
                time.sleep(0.5)
                if _check_port(port):
                    ready = True
                    break

            if ready:
                status[svc_name] = {
                    "port": port,
                    "pid": proc.pid,
                    "started_at": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                }
                _log(f"  {config['display_name']} started (PID={proc.pid}, port={port})")
            else:
                _log(f"  WARNING: {config['display_name']} process spawned but port {port} not responding")

        _write_status(status)
        return 0
    finally:
        _release_lock()


def restart_command(name: str = None):
    """重启服务"""
    ret = stop_command(name)
    if ret != 0:
        _log("Stop failed, but continuing with start...")
    time.sleep(2)
    return start_command(name)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    command = sys.argv[1]
    target = None
    if len(sys.argv) > 2:
        arg = sys.argv[2]
        if "fe" in arg or "front" in arg:
            target = "frontend"
        elif "be" in arg or "back" in arg:
            target = "backend"

    if command == "status":
        return status_command()
    elif command == "start":
        return start_command(target)
    elif command == "start-fe":
        return start_command("frontend")
    elif command == "start-be":
        return start_command("backend")
    elif command == "stop":
        return stop_command(target)
    elif command == "restart":
        return restart_command(target)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
