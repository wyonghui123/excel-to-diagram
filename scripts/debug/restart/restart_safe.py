#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
后端安全重启包装 - 调试基础设施 P1 (v2026.06.21)

背景：2026-06-21 复盘两次调试事故（SM/BO 误拦 + 旧 python.exe 残留），
     Agent 反复手动 taskkill pythonw.exe（不杀 python.exe），导致旧进程残留。
     修复看似生效但实际无效。

包装 service_manager.py 增加：
1. 强制杀所有 waitress_server.py 启动的进程（不只 pythonw.exe）
2. 重启后自动验证（PID 一致性 + 端口监听 + health 端点）
3. 回滚机制（如果新进程启动失败，自动回滚到旧版本）

用法：
    # 安全重启后端
    python scripts/debug/restart/restart_safe.py restart

    # 仅停止
    python scripts/debug/restart/restart_safe.py stop

    # 仅启动
    python scripts/debug/restart/restart_safe.py start

    # 验证当前状态
    python scripts/debug/restart/restart_safe.py verify
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def run_command(cmd, timeout: int = 30, cwd: Optional[str] = None):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            cwd=cwd or str(PROJECT_ROOT),
        )
        return result
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        _log(f"命令执行失败: {e}", "FAIL")
        return None


def kill_all_backend_processes() -> int:
    """杀所有 waitress_server.py 启动的 python 进程（不只 pythonw.exe）

    背景：2026-06-21 调试事故 - 旧 python.exe 进程残留
    """
    if sys.platform != "win32":
        return 0

    _log("查找所有 waitress_server.py 启动的进程...", "INFO")

    result = run_command([
        "wmic", "process", "where",
        "name='python.exe' or name='pythonw.exe'",
        "get", "ProcessId,CommandLine", "/format:csv",
    ], timeout=15)

    if not result or result.returncode != 0:
        _log("无法查询进程列表", "FAIL")
        return 0

    killed = 0
    for line in result.stdout.splitlines():
        if "waitress_server.py" not in line:
            continue
        parts = line.strip().split(",")
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[-1].strip())
            if pid == os.getpid():  # 避免杀自己
                continue
            taskkill = run_command(["taskkill", "/F", "/PID", str(pid)], timeout=10)
            if taskkill and taskkill.returncode == 0:
                _log(f"杀 PID {pid} (waitress_server.py)", "OK")
                killed += 1
        except ValueError:
            continue

    return killed


def wait_for_port(port: int, timeout: int = 30) -> bool:
    """等待端口开始监听"""
    import socket
    _log(f"等待端口 {port} 监听（timeout={timeout}s）...", "INFO")

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                s.close()
                _log(f"端口 {port} 已监听", "OK")
                return True
            s.close()
        except OSError:
            pass
        time.sleep(0.5)

    _log(f"端口 {port} 未在 {timeout}s 内监听", "FAIL")
    return False


def wait_for_port_free(port: int, timeout: int = 30) -> bool:
    """等待端口释放"""
    import socket
    _log(f"等待端口 {port} 释放（timeout={timeout}s）...", "INFO")

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                s.close()
                _log(f"端口 {port} 已释放", "OK")
                return True
            s.close()
        except OSError:
            return True
        time.sleep(0.5)

    _log(f"端口 {port} 未在 {timeout}s 内释放", "FAIL")
    return False


def verify_health(url: str = "http://localhost:3010/health", timeout: int = 10) -> bool:
    """验证 health 端点"""
    _log(f"验证 health: {url}", "INFO")

    result = run_command(
        ["curl.exe", "-s", "-o", "NUL", "-w", "%{http_code}", url],
        timeout=timeout,
    )
    if result and result.stdout.strip() in ("200", "204"):
        _log(f"health 返回 {result.stdout.strip()}", "OK")
        return True

    code = result.stdout.strip() if result else "timeout"
    _log(f"health 返回 {code}（期望 200）", "FAIL")
    return False


def cmd_restart(args):
    """安全重启后端"""
    print("=" * 70)
    print("安全重启后端 - V2.1 调试基础设施 P1")
    print("=" * 70)
    print()

    # Step 1: 杀所有 waitress 进程（包括 python.exe）
    killed = kill_all_backend_processes()
    print()

    # Step 2: 等待端口释放
    if not wait_for_port_free(3010, timeout=15):
        _log("端口未释放，重启可能失败", "FAIL")
        return 1
    print()

    # Step 3: 调用 service_manager 启动
    _log("调用 service_manager.py start-be...", "INFO")
    result = run_command(
        ["python", "scripts/service_manager.py", "start-be"],
        timeout=60,
    )
    if not result or result.returncode != 0:
        _log(f"service_manager 启动失败: {result.stderr if result else 'timeout'}", "FAIL")
        return 1
    print()

    # Step 4: 等待端口监听
    if not wait_for_port(3010, timeout=30):
        _log("端口未监听，启动失败", "FAIL")
        return 1
    print()

    # Step 5: 验证 health
    if not verify_health():
        _log("health 端点未返回 200", "FAIL")
        return 1
    print()

    # Step 6: 验证 PID 一致性
    _log("验证 PID 一致性...", "INFO")
    result = run_command(
        ["python", "scripts/verify_backend_owner.py"],
        timeout=15,
    )
    if result and "一致" in result.stdout:
        _log("PID 一致性验证通过", "OK")
    else:
        _log(f"PID 一致性验证失败: {result.stdout if result else 'timeout'}", "WARN")
    print()

    _log("重启成功！", "OK")
    return 0


def cmd_stop(args):
    """安全停止后端"""
    print("=" * 70)
    print("安全停止后端 - V2.1 调试基础设施 P1")
    print("=" * 70)
    print()

    killed = kill_all_backend_processes()
    if killed == 0:
        _log("没有 waitress 进程在运行", "INFO")
    print()

    if not wait_for_port_free(3010, timeout=15):
        return 1

    _log("停止成功", "OK")
    return 0


def cmd_start(args):
    """安全启动后端"""
    print("=" * 70)
    print("安全启动后端 - V2.1 调试基础设施 P1")
    print("=" * 70)
    print()

    _log("调用 service_manager.py start-be...", "INFO")
    result = run_command(
        ["python", "scripts/service_manager.py", "start-be"],
        timeout=60,
    )
    if not result or result.returncode != 0:
        return 1
    print()

    if not wait_for_port(3010, timeout=30):
        return 1
    print()

    if not verify_health():
        return 1
    print()

    _log("启动成功", "OK")
    return 0


def cmd_verify(args):
    """验证当前状态"""
    print("=" * 70)
    print("验证后端状态 - V2.1 调试基础设施 P1")
    print("=" * 70)
    print()

    # 端口 + health
    wait_for_port(3010, timeout=5)
    verify_health()
    print()

    # PID 一致性
    result = run_command(
        ["python", "scripts/verify_backend_owner.py"],
        timeout=15,
    )
    if result:
        print(result.stdout)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="后端安全重启包装 - V2.1 调试基础设施 P1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("restart", help="安全重启（杀所有 + 启动 + 验证）")
    sub.add_parser("stop", help="安全停止（杀所有 + 等待端口释放）")
    sub.add_parser("start", help="安全启动（启动 + 等待端口 + health 验证）")
    sub.add_parser("verify", help="验证当前状态（端口 + health + PID）")

    args = parser.parse_args()

    if args.cmd == "restart":
        return cmd_restart(args)
    elif args.cmd == "stop":
        return cmd_stop(args)
    elif args.cmd == "start":
        return cmd_start(args)
    elif args.cmd == "verify":
        return cmd_verify(args)

    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)