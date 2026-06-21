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

# V4.0 根因修复：直接启动 python -u waitress_server.py（不再走 powershell 嵌套）
# 背景：V3 链 powershell → service_manager.ps1 → pythonw.exe → waitress（4 层嵌套，每层超时不同，
#       导致 service_manager.py 等 8 秒就退出，但后端实际需要 30+ 秒启动）。
#       修复：直接调用 python，单一超时 60 秒，简单可靠。
SERVICES = {
    "frontend": {
        "port": 3004,
        "display_name": "Frontend (Vite)",
        "service_name": "frontend",
        "start_cmd": ["npm", "run", "dev"],
        "wait_seconds": 30,  # V4.0: 8 → 30（前端启动较慢）
    },
    "backend": {
        "port": 3010,
        "display_name": "Backend (Waitress)",
        "service_name": "backend",
        # V4.0: 直接启动 python（不再走 powershell 中间层）
        "start_cmd": ["python", "-u", "waitress_server.py"],
        "wait_seconds": 60,  # V4.0: 8 → 60（meta.server.py 初始化 + waitress 监听需 30+ 秒）
    },
}

MANAGEMENT_LOCK_TIMEOUT = 120
STARTUP_STATE_FILE = PROJECT_ROOT / ".startup_state.json"  # V4.0: 启动状态跟踪文件


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


def _get_current_git_commit() -> str:
    """获取当前 git commit hash (V2.1 增强 - 防止调试旧代码)"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def _check_code_version_stale() -> dict:
    """检查关键代码版本是否比后端启动时间新（V2.1 增强）"""
    if not STATUS_FILE.exists():
        return {"stale": False}

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            status = json.load(f)
    except Exception:
        return {"stale": False}

    backend_info = status.get("backend", {})
    started_at = backend_info.get("started_at")
    if not started_at:
        return {"stale": False}

    # 检查关键文件是否比启动时间更新
    try:
        backend_start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return {"stale": False}

    stale_files = []
    critical_files = [
        "meta/core/action_executor.py",
        "meta/core/interceptors/write_scope_interceptor.py",
        "meta/server.py",
    ]

    for f in critical_files:
        file_path = PROJECT_ROOT / f
        if not file_path.exists():
            continue
        # V2.1 增强：同时检查 git commit 时间 + 文件 mtime
        commit_time = ""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%cI", "--", f],
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                commit_time = result.stdout.strip()
        except Exception:
            pass

        # 文件 mtime（捕获未提交修改）
        mtime = ""
        try:
            mt = file_path.stat().st_mtime
            mtime = datetime.fromtimestamp(mt, tz=timezone.utc).isoformat()
        except OSError:
            pass

        latest = max([t for t in (commit_time, mtime) if t], default="")
        if not latest:
            continue
        try:
            file_dt = datetime.fromisoformat(latest)
            if file_dt > backend_start_dt:
                stale_files.append(f)
        except ValueError:
            continue

    return {"stale": len(stale_files) > 0, "stale_files": stale_files, "started_at": started_at}


def _read_status() -> dict:
    """读取服务状态文件（兼容 utf-8-sig BOM）"""
    if not STATUS_FILE.exists():
        return {}
    try:
        # V2.1 修复：兼容 watchdog 写的 utf-8-sig BOM 文件
        for encoding in ("utf-8-sig", "utf-8"):
            try:
                with open(STATUS_FILE, "r", encoding=encoding) as f:
                    return json.load(f)
            except UnicodeDecodeError:
                continue
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_status(status: dict):
    """写入服务状态文件"""
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


# V4.0: 启动状态跟踪（区分"启动中"vs"启动失败"vs"未启动"）
def _write_startup_state(svc_name: str, state: str, pid: int = None, port: int = None, error: str = None):
    """写入启动状态
    
    Args:
        state: 'starting' | 'ready' | 'failed' | 'stale'
    """
    states = {}
    if STARTUP_STATE_FILE.exists():
        try:
            with open(STARTUP_STATE_FILE, "r", encoding="utf-8") as f:
                states = json.load(f)
        except Exception:
            states = {}
    
    states[svc_name] = {
        "state": state,
        "pid": pid,
        "port": port,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": error,
    }
    
    try:
        with open(STARTUP_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(states, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _read_startup_state() -> dict:
    """读取启动状态"""
    if not STARTUP_STATE_FILE.exists():
        return {}
    try:
        with open(STARTUP_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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


def _kill_all_backend_processes() -> int:
    """V2.1 新增 - 杀掉所有 waitress_server.py 启动的 python 进程

    背景：2026-06-21 调试事故 - 旧后端进程（python.exe）未杀掉，
          但端口被新 pythonw.exe 占用前的瞬间，旧进程可能仍在 TIME_WAIT。
          更根本的问题：旧 python.exe 进程没有被显式清理。

    Returns:
        int: 杀掉的进程数量
    """
    if sys.platform != "win32":
        return 0

    # 用 wmic 找所有带 waitress_server.py 的 python 进程
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "name='python.exe' or name='pythonw.exe'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return 0

        killed = 0
        for line in result.stdout.splitlines():
            if "waitress_server.py" not in line:
                continue
            # CSV 格式: Node,CommandLine,ProcessId
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue
            pid_str = parts[-1].strip()
            try:
                pid = int(pid_str)
                if pid == os.getpid():  # 避免杀自己
                    continue
                taskkill = subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=10,
                )
                if taskkill.returncode == 0:
                    _log(f"Killed stale backend PID {pid} (waitress_server.py)")
                    killed += 1
            except (ValueError, subprocess.SubprocessError):
                pass
        return killed
    except (subprocess.SubprocessError, FileNotFoundError):
        return 0


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
        known_code = known.get("code_version", "NOT SET")  # V2.1 新增
        known_health = known.get("health_url", f"http://localhost:{port}/health")  # V2.1 新增
        healthy = "RUNNING" if is_listening else "STOPPED"

        if is_listening:
            print(f"  {config['display_name']:<25s} : {healthy}  "
                  f"(port={port}, pid={known_pid}, since={known_time})")
            # V2.1 新增：显示 code_version 和 health_url
            if known_code and known_code != "NOT SET":
                print(f"  {'':<25s}   commit={known_code[:12]}")
                print(f"  {'':<25s}   health={known_health}")
        else:
            print(f"  {config['display_name']:<25s} : {healthy}  "
                  f"(port={port})")
            all_healthy = False

    print("  " + "=" * 50)

    # V2.1 新增：检测代码版本是否 stale（防止"调试旧代码"事故）
    stale_info = _check_code_version_stale()
    if stale_info.get("stale"):
        print()
        print("  [!!!] WARNING: Code version stale !!!")
        print(f"  Backend started: {stale_info.get('started_at', '?')}")
        print(f"  Stale files (modified after start):")
        for sf in stale_info.get("stale_files", []):
            print(f"    - {sf}")
        print()
        print("  >>> Run: python scripts/service_manager.py restart-be")
        print("  >>> Or:  python scripts/debug_backend.py restart-if-stale")
        all_healthy = False

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

            # V2.1 增强：先杀掉所有 waitress_server.py 启动的 python 进程
            # 防止旧 python.exe 进程残留（即使不在 LISTEN 端口）
            if svc_name == "backend":
                killed_count = _kill_all_backend_processes()
                if killed_count > 0:
                    _log(f"  V2.1: Killed {killed_count} stale backend processes")

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

            # V2.1 增强：再杀一次所有 waitress_server.py 进程（兜底）
            if svc_name == "backend":
                _kill_all_backend_processes()

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
                _write_startup_state(svc_name, "ready")  # V4.0
                continue

            _log(f"Starting {config['display_name']}...")
            _write_startup_state(svc_name, "starting", port=port)  # V4.0: 标记启动中

            # 使用 DETACHED_PROCESS 不占用终端槽位
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(
                config["start_cmd"],
                cwd=str(PROJECT_ROOT),
                stdout=open(PROJECT_ROOT / "scripts" / "logs" / f"{config['service_name']}.out", "ab"),
                stderr=open(PROJECT_ROOT / "scripts" / "logs" / f"{config['service_name']}.err", "ab"),
                creationflags=creation_flags,
            )

            # 等待端口就绪（V4.0: wait_seconds * 2 = 60*2 = 120 次 * 0.5s = 60 秒）
            ready = False
            for i in range(config["wait_seconds"] * 2):
                time.sleep(0.5)
                if _check_port(port):
                    ready = True
                    break

            if ready:
                # 获取启动时的 git commit（V2.1 增强 - 防止"调试旧代码 3 小时"事故）
                code_version = _get_current_git_commit()
                # 健康检查 URL（V2.1 增强 - 避免 /api/v1/health 410 误判）
                health_url = config.get("health_url", f"http://localhost:{port}/health")

                status[svc_name] = {
                    "port": port,
                    "pid": proc.pid,
                    "started_at": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "code_version": code_version,  # V2.1 新增
                    "health_url": health_url,      # V2.1 新增
                }
                _log(f"  {config['display_name']} started (PID={proc.pid}, port={port}, commit={code_version[:8]})")
                _write_startup_state(svc_name, "ready", proc.pid, port)  # V4.0: 标记就绪
            else:
                # V4.0: 失败时记录详细错误
                _write_startup_state(svc_name, "failed", proc.pid, port, "port not listening within timeout")
                _log(f"  WARNING: {config['display_name']} process spawned but port {port} not responding")
                _log(f"  V4.0: Check {PROJECT_ROOT / 'scripts' / 'logs' / f'{config['service_name']}.err'}")

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
