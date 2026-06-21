#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
后端调试 SOP - V2 元反馈新增（解决"调试旧代码 3 小时"事故）

背景：2026-06-21 另一个 Agent 调试后端时，反复调试一个 17:27 启动的旧进程，
但 20:31 已经 commit 了修复，导致浪费 3+ 小时。

本工具强制执行"修复 → 验证"前必须证明后端在运行新代码。

用法：
    # 完整调试前检查（推荐 - 所有步骤）
    python scripts/debug_backend.py check

    # 快速验证（仅检查代码版本 vs 运行版本）
    python scripts/debug_backend.py check --quick

    # 自动重启（如果检测到代码版本不匹配）
    python scripts/debug_backend.py restart-if-stale

    # 启动前 import 验证（避免循环导入）
    python scripts/debug_backend.py verify-imports

    # 完整诊断报告（含环境探测 + 后端状态 + 日志分析）
    python scripts/debug_backend.py diagnose
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 强制 UTF-8 输出（避免 trae-sandbox + PowerShell 中文乱码）
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = PROJECT_ROOT / ".service_status.json"
BACKEND_LOG = PROJECT_ROOT / "scripts/logs/backend.out"
BACKEND_ERR = PROJECT_ROOT / "scripts/logs/backend.err"
BACKEND_HEALTH_URL = "http://localhost:3010/health"  # 注意：不是 /api/v1/health（已弃用）
FRONTEND_HEALTH_URL = "http://localhost:3004/"

# 关键代码文件（修改后必须重启才能生效）
CRITICAL_FILES = [
    "meta/core/action_executor.py",
    "meta/core/interceptors/write_scope_interceptor.py",
    "meta/core/interceptors/__init__.py",
    "meta/services/import_export_service.py",
    "meta/services/query_service.py",
    "meta/services/auth_middleware.py",
    "meta/server.py",
]


def _log(msg: str, color: str = ""):
    icons = {
        "OK": "[OK]",
        "FAIL": "[X]",
        "WARN": "[!]",
        "INFO": "[i]",
    }
    icon = icons.get(color, "[?]")
    print(f"{icon} {msg}")


def _run(cmd, cwd=None, timeout=30):
    """执行命令（带超时）"""
    try:
        return subprocess.run(
            cmd, cwd=cwd or str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        _log(f"命令执行失败: {e}", "FAIL")
        return None


def get_git_commit_for_file(filepath: str) -> str:
    """获取某个文件的最后一次 commit hash"""
    result = _run(["git", "log", "-1", "--format=%H", "--", filepath])
    if result and result.returncode == 0:
        return result.stdout.strip()
    return ""


def get_git_commit_time_for_file(filepath: str) -> str:
    """获取某个文件的最后一次 commit 时间（包含未提交修改的检测）"""
    result = _run(["git", "log", "-1", "--format=%cI", "--", filepath])
    if result and result.returncode == 0:
        return result.stdout.strip()
    return ""


def get_file_mtime(filepath: str) -> str:
    """获取文件的本地修改时间（mtime）- 捕获未提交的修改"""
    file_path = PROJECT_ROOT / filepath
    if not file_path.exists():
        return ""
    try:
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return ""


def check_process_ownership() -> dict:
    """V2.1 新增 - 检查后端进程所有者一致性（防旧 python.exe 残留）

    关键检测：
    1. status.json 里的 PID == 端口 3010 LISTEN 的 PID
    2. 只有 1 个 waitress_server.py 进程在跑

    事故背景：2026-06-21 - restart_backend.py 只杀 pythonw.exe，
              旧 python.exe 进程（PID 16420/18060）残留导致请求被旧代码处理。
    """
    # status.json PID
    status_pid = 0
    if STATUS_FILE.exists():
        try:
            for encoding in ("utf-8-sig", "utf-8"):
                try:
                    with open(STATUS_FILE, "r", encoding=encoding) as f:
                        data = json.load(f)
                    status_pid = data.get("backend", {}).get("pid", 0)
                    break
                except UnicodeDecodeError:
                    continue
        except Exception:
            pass

    # 端口 3010 LISTEN 的 PID
    port_pid = 0
    try:
        import socket as sock_mod
        s = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
        s.settimeout(3)
        # 先检查端口是否 LISTEN
        if s.connect_ex(("127.0.0.1", 3010)) == 0:
            # 用 netstat 找 LISTEN 的 PID
            result = _run(["netstat", "-ano"], timeout=15)
            if result:
                for line in result.stdout.splitlines():
                    if ":3010" in line and "LISTENING" in line:
                        parts = line.strip().split()
                        try:
                            pid = int(parts[-1])
                            if pid > 4:
                                port_pid = pid
                                break
                        except (ValueError, IndexError):
                            continue
        s.close()
    except OSError:
        pass

    # 所有 waitress_server.py 启动的 python 进程
    all_pids = []
    if sys.platform == "win32":
        try:
            result = _run(
                ["wmic", "process", "where",
                 "name='python.exe' or name='pythonw.exe'",
                 "get", "ProcessId,CommandLine", "/format:csv"],
                timeout=15
            )
            if result:
                for line in result.stdout.splitlines():
                    if "waitress_server.py" not in line:
                        continue
                    parts = line.strip().split(",")
                    if len(parts) < 3:
                        continue
                    try:
                        pid = int(parts[-1].strip())
                        if pid != os.getpid():
                            all_pids.append(pid)
                    except ValueError:
                        continue
        except Exception:
            pass

    result = {
        "status_pid": status_pid,
        "port_pid": port_pid,
        "all_pids": all_pids,
        "consistent": False,
        "issues": [],
    }

    # 关键检测 1: status PID == port PID
    if status_pid and port_pid and status_pid != port_pid:
        result["issues"].append(
            f"status.json PID={status_pid} != 端口 3010 LISTEN PID={port_pid} "
            f"（端口被旧进程占用！修复未生效！）"
        )

    # 关键检测 2: 多个 waitress 进程（说明旧进程未杀）
    if len(all_pids) > 1:
        result["issues"].append(
            f"发现 {len(all_pids)} 个 waitress_server.py 进程: {all_pids} "
            f"（旧进程残留！）"
        )

    # 关键检测 3: port PID 不在 waitress 进程列表
    if port_pid and port_pid not in all_pids:
        result["issues"].append(
            f"端口 LISTEN 的 PID {port_pid} 不是 waitress_server.py 进程"
        )

    result["consistent"] = len(result["issues"]) == 0
    return result


def get_running_backend_info() -> dict:
    """从 .service_status.json 读取后端启动信息"""
    if not STATUS_FILE.exists():
        return {}

    try:
        # service_manager 写文件可能用 utf-8-sig (with BOM)，兼容两种
        for encoding in ("utf-8-sig", "utf-8"):
            try:
                with open(STATUS_FILE, "r", encoding=encoding) as f:
                    data = json.load(f)
                return data.get("backend", {})
            except UnicodeDecodeError:
                continue
        return {}
    except Exception as e:
        _log(f"读取 service_status.json 失败: {e}", "WARN")
        return {}


def check_code_version_stale() -> dict:
    """检查代码版本是否比后端启动时间新（关键检测）"""
    info = get_running_backend_info()
    if not info:
        return {"stale": False, "reason": "no_backend_running"}

    started_at = info.get("started_at", "")
    running_commit = info.get("code_version", "")

    if not started_at:
        return {"stale": False, "reason": "no_started_at"}

    # 检测关键文件是否有比启动时间更新的 commit
    stale_files = []
    try:
        backend_start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return {"stale": False, "reason": "invalid_started_at"}

    for f in CRITICAL_FILES:
        file_path = PROJECT_ROOT / f
        if not file_path.exists():
            continue
        # V2.1 增强：同时检查 git commit 时间 + 文件 mtime（捕获未提交修改）
        commit_time = get_git_commit_time_for_file(f)
        mtime = get_file_mtime(f)
        latest_change = max([t for t in (commit_time, mtime) if t], default="")
        if not latest_change:
            continue
        try:
            file_dt = datetime.fromisoformat(latest_change)
            if file_dt > backend_start_dt:
                reason = "未提交修改" if mtime and mtime > commit_time else "新 commit"
                stale_files.append({
                    "file": f,
                    "commit_time": commit_time,
                    "mtime": mtime,
                    "backend_start": started_at,
                    "reason": reason,
                })
        except ValueError:
            continue

    return {
        "stale": len(stale_files) > 0,
        "stale_files": stale_files,
        "running_commit": running_commit,
        "started_at": started_at,
    }


def check_backend_health() -> dict:
    """检查后端健康（端口 + /health 端点）"""
    result = {"port_listening": False, "health_endpoint_ok": False, "details": ""}

    # 端口检测 - 直接用 socket（Test-NetConnection 在沙箱下超时）
    import socket as sock_mod
    try:
        s = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
        s.settimeout(3)
        port_ok = (s.connect_ex(("127.0.0.1", 3010)) == 0)
        s.close()
        result["port_listening"] = port_ok
    except OSError:
        result["port_listening"] = False

    # HTTP /health 端点
    health_result = _run(
        ["curl.exe", "-s", "-o", "NUL", "-w", "%{http_code}", BACKEND_HEALTH_URL],
        timeout=10
    )
    if health_result and health_result.stdout.strip() in ("200", "204"):
        result["health_endpoint_ok"] = True
        result["details"] = f"/health returned {health_result.stdout.strip()}"
    else:
        result["details"] = f"/health returned {health_result.stdout.strip() if health_result else 'timeout'}"

    return result


def verify_imports() -> dict:
    """验证关键模块可以正常 import（避免循环导入）"""
    test_modules = [
        ("meta.server", "create_app"),
        ("meta.core.action_executor", "ActionExecutor"),
        ("meta.core.interceptors.write_scope_interceptor", "WriteScopeInterceptor"),
    ]

    results = []
    for module, symbol in test_modules:
        test_code = (
            f"import sys; sys.path.insert(0, r'd:/filework/excel-to-diagram'); "
            f"from {module} import {symbol}; print('[OK] {module}.{symbol}')"
        )
        result = _run(["python", "-c", test_code], timeout=30)
        success = result and "[OK]" in result.stdout
        results.append({
            "module": module,
            "symbol": symbol,
            "success": success,
            "error": result.stderr[:500] if result and not success else "",
        })

    return {"results": results}


def analyze_backend_log() -> dict:
    """分析后端日志（编码安全）"""
    if not BACKEND_LOG.exists():
        return {"available": False}

    # 强制 UTF-8 + errors='replace' 处理编码错误
    try:
        with open(BACKEND_LOG, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return {"available": False, "error": str(e)}

    # 找最近的错误
    recent_errors = []
    for line in lines[-200:]:  # 只看最近 200 行
        if "ERROR" in line or "Traceback" in line or "FATAL" in line:
            recent_errors.append(line.strip())

    return {
        "available": True,
        "total_lines": len(lines),
        "recent_errors": recent_errors[-10:],  # 最近 10 个错误
    }


def cmd_check(args):
    """完整检查（核心 SOP）"""
    print("=" * 70)
    print('后端调试检查 SOP - V2 元反馈（防「调试旧代码 3 小时」事故）')
    print("=" * 70)

    # Step 1: 沙箱状态（V2 铁律 9）
    print()
    print("[Step 1/6] 沙箱状态检查")
    sandbox_result = _run(["python", "scripts/check_sandbox_status.py"], timeout=15)
    if sandbox_result and "HEALTHY" in sandbox_result.stdout:
        _log("沙箱 HEALTHY", "OK")
    else:
        _log("沙箱可能异常，继续但要小心", "WARN")

    # Step 2: 环境探测（env_doctor）
    print()
    print("[Step 2/6] 环境探测")
    env_result = _run(["python", "scripts/env_doctor.py"], timeout=15)
    if env_result and "BLOCK" in env_result.stdout:
        _log("env_doctor 报告 BLOCK，详情见上方输出", "WARN")

    # Step 3: 关键代码版本 vs 后端启动时间（核心）
    print()
    print("[Step 3/6] 关键代码版本 vs 后端启动时间")
    version_info = check_code_version_stale()
    if version_info["stale"]:
        _log(f"!!! 关键文件比后端启动时间更新 !!!", "FAIL")
        for sf in version_info["stale_files"]:
            _log(f"  - {sf['file']} (commit: {sf['commit_time']})", "FAIL")
        _log(f"后端启动时间: {version_info['started_at']}", "INFO")
        _log(f"建议: 必须重启后端，否则调试的是旧代码", "FAIL")
    else:
        _log(f"代码版本一致（后端启动: {version_info.get('started_at', 'N/A')}）", "OK")

    # V2.1 新增: 进程所有者一致性检查（防旧 python.exe 残留）
    print()
    print("[Step 3.5/6] 进程所有者一致性检查（V2.1 防旧进程残留）")
    pid_consistency = check_process_ownership()
    if pid_consistency["consistent"]:
        _log(f"PID 一致 (status={pid_consistency['status_pid']}, port={pid_consistency['port_pid']}, total={len(pid_consistency['all_pids'])})", "OK")
    else:
        _log(f"!!! 进程所有者不一致 !!!", "FAIL")
        for issue in pid_consistency["issues"]:
            _log(f"  - {issue}", "FAIL")
        _log(f"建议: python scripts/verify_backend_owner.py --fix", "FAIL")

    # Step 4: Import 验证（避免循环导入）
    if not args.quick:
        print()
        print("[Step 4/6] 关键模块 import 验证")
        import_info = verify_imports()
        for r in import_info["results"]:
            if r["success"]:
                _log(f"{r['module']}.{r['symbol']}", "OK")
            else:
                _log(f"{r['module']}.{r['symbol']} - {r['error'][:100]}", "FAIL")

    # Step 5: 后端健康检查
    print()
    print("[Step 5/6] 后端健康检查")
    health_info = check_backend_health()
    if health_info["port_listening"]:
        _log(f"端口 3010 监听中", "OK")
    else:
        _log(f"端口 3010 未监听", "FAIL")
    _log(f"{health_info['details']}", "INFO" if health_info["health_endpoint_ok"] else "WARN")

    # Step 6: 日志分析
    if not args.quick:
        print()
        print("[Step 6/6] 后端日志分析（最近错误）")
        log_info = analyze_backend_log()
        if log_info.get("available"):
            _log(f"日志总行数: {log_info['total_lines']}", "INFO")
            if log_info["recent_errors"]:
                _log(f"最近错误 {len(log_info['recent_errors'])} 条:", "WARN")
                for err in log_info["recent_errors"][:5]:
                    print(f"    {err[:200]}")
            else:
                _log("无最近错误", "OK")
        else:
            _log(f"日志文件不可用: {log_info.get('error', 'N/A')}", "WARN")

    print()
    print("=" * 70)
    if version_info["stale"]:
        _log("结论: 必须重启后端！执行: python scripts/service_manager.py restart-be", "FAIL")
        sys.exit(1)
    else:
        _log("结论: 可以开始调试", "OK")


def cmd_restart_if_stale(args):
    """如果代码版本 stale，自动重启"""
    print("[debug_backend] 检查代码版本...")
    version_info = check_code_version_stale()

    if not version_info["stale"]:
        _log("代码版本一致，无需重启", "OK")
        return

    _log(f"代码版本 stale！需要重启后端", "FAIL")
    for sf in version_info["stale_files"]:
        _log(f"  - {sf['file']}", "FAIL")

    print()
    print("[debug_backend] 执行重启...")
    result = _run(["python", "scripts/service_manager.py", "restart-be"], timeout=60)
    if result and result.returncode == 0:
        _log("重启成功", "OK")
    else:
        _log("重启失败，请手动检查", "FAIL")
        if result:
            print(result.stdout[-500:])
            print(result.stderr[-500:])


def cmd_verify_imports(args):
    """只做 import 验证"""
    print("[debug_backend] 验证关键模块 import...")
    import_info = verify_imports()
    all_ok = True
    for r in import_info["results"]:
        if r["success"]:
            _log(f"{r['module']}.{r['symbol']}", "OK")
        else:
            _log(f"{r['module']}.{r['symbol']}", "FAIL")
            print(f"    错误: {r['error']}")
            all_ok = False
    sys.exit(0 if all_ok else 1)


def cmd_diagnose(args):
    """完整诊断（包含日志 + 编码）"""
    print("=" * 70)
    print("后端完整诊断报告")
    print("=" * 70)
    print()

    # 1. service_status.json
    print("[1/5] service_status.json")
    info = get_running_backend_info()
    if info:
        print(f"  PID:        {info.get('pid', 'N/A')}")
        print(f"  Port:       {info.get('port', 'N/A')}")
        print(f"  Started at: {info.get('started_at', 'N/A')}")
        print(f"  Code ver:   {info.get('code_version', 'NOT SET')[:12]}")
    else:
        print("  [WARN] 后端未运行")
    print()

    # 2. 代码版本
    print("[2/5] 代码版本")
    for f in CRITICAL_FILES[:5]:
        ct = get_git_commit_time_for_file(f)
        ch = get_git_commit_for_file(f)
        if ch:
            print(f"  {f}: {ch[:8]} ({ct})")
    print()

    # 3. 端口 + 健康
    print("[3/5] 端口 + 健康检查")
    health = check_backend_health()
    print(f"  Port 3010: {'OK' if health['port_listening'] else 'FAIL'}")
    print(f"  /health:   {'OK' if health['health_endpoint_ok'] else 'FAIL'} ({health['details']})")
    print()

    # 4. 后端日志分析
    print("[4/5] 后端日志分析")
    log = analyze_backend_log()
    if log.get("available"):
        print(f"  Total lines: {log['total_lines']}")
        print(f"  Recent errors: {len(log['recent_errors'])}")
        for e in log['recent_errors'][:3]:
            print(f"    {e[:150]}")
    print()

    # 5. import 验证
    print("[5/5] import 验证")
    imp = verify_imports()
    for r in imp["results"]:
        print(f"  {r['module']}.{r['symbol']}: {'OK' if r['success'] else 'FAIL'}")
    print()
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="后端调试 SOP - V2 元反馈",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    chk = sub.add_parser("check", help="完整检查（推荐作为调试第一步）")
    chk.add_argument("--quick", action="store_true", help="快速检查（仅代码版本 vs 运行版本）")

    sub.add_parser("restart-if-stale", help="如果代码版本 stale，自动重启后端")
    sub.add_parser("verify-imports", help="验证关键模块 import（避免循环导入）")
    sub.add_parser("diagnose", help="完整诊断报告")

    args = parser.parse_args()

    if args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "restart-if-stale":
        cmd_restart_if_stale(args)
    elif args.cmd == "verify-imports":
        cmd_verify_imports(args)
    elif args.cmd == "diagnose":
        cmd_diagnose(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()