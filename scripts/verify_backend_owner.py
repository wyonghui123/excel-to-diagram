#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
后端进程所有者验证工具 - V2.1 新增

背景：2026-06-21 调试事故复盘：
- 后端被 restart_backend.py 重启，但旧 python.exe 进程（PID 16420/18060）未被杀掉
- 新启动的 pythonw.exe 没有真正在 3010 端口监听
- 请求一直被旧代码处理，修复看似生效但实际无效

核心检测：哪个 PID 实际在监听 3010 端口？
- status.json 里的 PID ≠ netstat 看到的 PID → 后端不一致！

用法：
    # 自动验证
    python scripts/verify_backend_owner.py

    # 强制修复（杀掉所有旧进程后重启）
    python scripts/verify_backend_owner.py --fix

    # 显示所有 waitress_server.py 启动的进程
    python scripts/verify_backend_owner.py --list-all
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = PROJECT_ROOT / ".service_status.json"
BACKEND_PORT = 3010


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def _run(cmd, timeout=15):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return None


def get_status_pid() -> int:
    """从 .service_status.json 读取 backend PID"""
    if not STATUS_FILE.exists():
        return 0
    try:
        for encoding in ("utf-8-sig", "utf-8"):
            try:
                with open(STATUS_FILE, "r", encoding=encoding) as f:
                    data = json.load(f)
                return data.get("backend", {}).get("pid", 0)
            except UnicodeDecodeError:
                continue
    except Exception:
        pass
    return 0


def get_port_listening_pid(port: int = BACKEND_PORT) -> int:
    """从 netstat 找出端口 LISTEN 的 PID"""
    result = _run(["netstat", "-ano"], timeout=15)
    if not result:
        return 0

    for line in result.stdout.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            parts = line.strip().split()
            try:
                pid = int(parts[-1])
                if pid > 4:  # 排除 System (PID 4) 和 Idle (PID 0)
                    return pid
            except (ValueError, IndexError):
                continue
    return 0


def get_all_backend_pids() -> list:
    """找出所有 waitress_server.py 启动的 python 进程 PID"""
    if sys.platform != "win32":
        return []

    result = _run(
        ["wmic", "process", "where",
         "name='python.exe' or name='pythonw.exe'",
         "get", "ProcessId,CommandLine", "/format:csv"],
        timeout=15
    )
    if not result or result.returncode != 0:
        return []

    pids = []
    for line in result.stdout.splitlines():
        if "waitress_server.py" not in line:
            continue
        parts = line.strip().split(",")
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[-1].strip())
            if pid != os.getpid():
                pids.append(pid)
        except ValueError:
            continue
    return pids


def get_pid_command(pid: int) -> str:
    """获取指定 PID 的命令行"""
    if sys.platform != "win32":
        return ""

    result = _run(
        ["wmic", "process", "where", f"ProcessId={pid}",
         "get", "CommandLine", "/format:csv"],
        timeout=10
    )
    if not result or result.returncode != 0:
        return ""

    for line in result.stdout.splitlines():
        if "waitress_server.py" in line or "python" in line.lower():
            parts = line.strip().split(",")
            if len(parts) >= 2:
                return parts[1]
    return ""


def kill_pid(pid: int) -> bool:
    """强制杀掉指定 PID"""
    try:
        result = _run(["taskkill", "/F", "/PID", str(pid)], timeout=10)
        return result and result.returncode == 0
    except Exception:
        return False


def verify_consistency() -> dict:
    """验证后端进程所有者一致性"""
    status_pid = get_status_pid()
    port_pid = get_port_listening_pid()
    all_backend_pids = get_all_backend_pids()

    result = {
        "status_pid": status_pid,
        "port_pid": port_pid,
        "all_backend_pids": all_backend_pids,
        "consistent": False,
        "issues": [],
    }

    # 关键检测 1: status.json 里的 PID 是否在监听端口
    if status_pid and status_pid != port_pid:
        result["issues"].append(
            f"status.json PID={status_pid} != 端口 LISTEN PID={port_pid}"
        )

    # 关键检测 2: 是否有多个 waitress 进程（说明旧进程未杀）
    if len(all_backend_pids) > 1:
        result["issues"].append(
            f"发现 {len(all_backend_pids)} 个 waitress_server.py 进程: {all_backend_pids}"
        )

    # 关键检测 3: 端口 LISTEN 的 PID 是否在 waitress 进程列表里
    if port_pid and port_pid not in all_backend_pids:
        result["issues"].append(
            f"端口 LISTEN 的 PID {port_pid} 不在 waitress_server.py 进程列表里"
        )

    result["consistent"] = len(result["issues"]) == 0
    return result


def cmd_verify(args):
    """验证后端进程所有者一致性"""
    print("=" * 70)
    print("后端进程所有者验证 - V2.1 防「旧进程残留」事故")
    print("=" * 70)
    print()

    result = verify_consistency()

    print(f"status.json PID (我启动的):    {result['status_pid'] or '(none)'}")
    print(f"端口 3010 LISTEN PID (在监听的): {result['port_pid'] or '(none)'}")
    print(f"所有 waitress 进程:            {result['all_backend_pids'] or '(none)'}")
    print()

    if result["status_pid"]:
        cmd = get_pid_command(result["status_pid"])
        print(f"PID {result['status_pid']} 命令行:")
        print(f"  {cmd[:120]}")

    if result["port_pid"] and result["port_pid"] != result["status_pid"]:
        cmd = get_pid_command(result["port_pid"])
        print(f"PID {result['port_pid']} 命令行 (实际监听端口):")
        print(f"  {cmd[:120]}")

    print()
    if result["consistent"]:
        _log("后端进程所有者一致 ✓", "OK")
        return 0

    _log(f"发现 {len(result['issues'])} 个一致性问题:", "FAIL")
    for issue in result["issues"]:
        print(f"  - {issue}")
    print()
    _log("建议: python scripts/verify_backend_owner.py --fix", "WARN")
    return 1


def cmd_fix(args):
    """修复不一致问题（杀掉所有旧进程，重启后端）"""
    print("=" * 70)
    print("修复后端进程所有者不一致")
    print("=" * 70)
    print()

    all_pids = get_all_backend_pids()
    if not all_pids:
        _log("没有 waitress_server.py 进程在运行", "WARN")
        return 1

    _log(f"发现 {len(all_pids)} 个 waitress 进程: {all_pids}", "WARN")
    print()

    if not args.force:
        print("将执行以下操作：")
        print(f"  1. 杀掉所有 {len(all_pids)} 个 waitress 进程")
        print("  2. 用 service_manager 启动新后端")
        print("  3. 验证新 PID 一致")
        print()
        resp = input("确认执行？(y/N): ").strip().lower()
        if resp != "y":
            _log("取消", "INFO")
            return 0

    # Step 1: 杀所有
    killed = []
    for pid in all_pids:
        if kill_pid(pid):
            killed.append(pid)
            _log(f"杀 PID {pid}", "OK")

    _log(f"共杀掉 {len(killed)} 个进程", "INFO")

    # Step 2: 等待端口释放
    print()
    _log("等待端口释放...", "INFO")
    for _ in range(10):
        if get_port_listening_pid() == 0:
            break
        time.sleep(1)

    # Step 3: 用 service_manager 启动
    print()
    _log("用 service_manager 启动新后端...", "INFO")
    result = _run(
        ["python", "scripts/service_manager.py", "start-be"],
        timeout=60
    )
    if result and result.returncode == 0:
        _log("启动成功", "OK")
    else:
        _log("启动失败，请检查", "FAIL")
        return 1

    # Step 4: 验证
    print()
    return cmd_verify(args)


def cmd_list_all(args):
    """列出所有 waitress 进程"""
    print("所有 waitress_server.py 启动的进程:")
    print()

    pids = get_all_backend_pids()
    if not pids:
        print("  (none)")
        return 0

    for pid in pids:
        cmd = get_pid_command(pid)
        print(f"  PID {pid}:")
        print(f"    {cmd[:150]}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="后端进程所有者验证工具 - V2.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--fix", action="store_true",
                        help="修复不一致（杀旧进程 + 重启）")
    parser.add_argument("--force", action="store_true",
                        help="跳过确认（配合 --fix 使用）")
    parser.add_argument("--list-all", action="store_true",
                        help="列出所有 waitress 进程")

    args = parser.parse_args()

    if args.fix:
        return cmd_fix(args)
    elif args.list_all:
        return cmd_list_all(args)
    else:
        return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main() or 0)