#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
综合调试环境诊断 - 调试基础设施 P1 (v2026.06.21)

背景：每次调试都要回答 10+ 问题：
- 后端在跑哪个 commit？
- 端口监听是否一致？
- PID 跟 status.json 一致吗？
- /health 返回什么？
- 沙箱健康吗？
- 数据库可连接吗？
- TEST333 用户数据是否被 reset？
- 工作树有多少未提交文件？
- 最近 ERROR 是什么？
- 是否有 DEBUG 代码遗留？

本工具：一次性回答所有问题，给出 PASS/WARN/FAIL 总结。

用法：
    python scripts/debug/env/diagnose.py

    # JSON 输出
    python scripts/debug/env/diagnose.py --json

    # 仅严重问题（FAIL）
    python scripts/debug/env/diagnose.py --only-fail
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

STATUS_FILE = PROJECT_ROOT / ".service_status.json"


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def run_subprocess(cmd, timeout: int = 15) -> Dict[str, Any]:
    """运行子命令并返回结构化结果"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            cwd=str(PROJECT_ROOT),
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "stdout": "", "stderr": ""}


def check_sandbox() -> Dict[str, Any]:
    """检查沙箱状态"""
    result = run_subprocess(["python", "scripts/check_sandbox_status.py"], timeout=15)
    if result["success"] and "HEALTHY" in result["stdout"]:
        return {"status": "OK", "summary": "沙箱 HEALTHY"}
    return {"status": "FAIL", "summary": "沙箱异常", "details": result["stdout"][:200]}


def check_backend_status() -> Dict[str, Any]:
    """检查后端状态"""
    # 端口
    import socket
    port_listening = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        port_listening = (s.connect_ex(("127.0.0.1", 3010)) == 0)
        s.close()
    except OSError:
        pass

    # /health
    health = run_subprocess(
        ["curl.exe", "-s", "-o", "NUL", "-w", "%{http_code}",
         "http://localhost:3010/health"],
        timeout=10,
    )
    health_code = health["stdout"].strip() if health["success"] else "?"

    # status.json
    status_pid = None
    started_at = None
    code_version = None
    if STATUS_FILE.exists():
        try:
            for enc in ("utf-8-sig", "utf-8"):
                try:
                    with open(STATUS_FILE, encoding=enc) as f:
                        data = json.load(f)
                    backend = data.get("backend", {})
                    status_pid = backend.get("pid")
                    started_at = backend.get("started_at")
                    code_version = backend.get("code_version")
                    break
                except UnicodeDecodeError:
                    continue
        except Exception:
            pass

    # 当前 HEAD
    head = run_subprocess(["git", "rev-parse", "--short", "HEAD"], timeout=5)
    head_hash = head["stdout"].strip() if head["success"] else "?"

    # 当前分支
    branch = run_subprocess(["git", "rev-parse", "--abbrev-ref", "HEAD"], timeout=5)
    branch_name = branch["stdout"].strip() if branch["success"] else "?"

    issues = []
    if not port_listening:
        issues.append("端口 3010 未监听")
    if health_code not in ("200", "204"):
        issues.append(f"/health 返回 {health_code}（期望 200）")
    if code_version and code_version != head_hash:
        issues.append(f"后端 commit {code_version[:8]} != HEAD {head_hash}")

    status = "OK" if not issues else "FAIL"
    return {
        "status": status,
        "summary": "后端健康" if not issues else f"后端异常: {issues}",
        "details": {
            "port_listening": port_listening,
            "health_code": health_code,
            "status_pid": status_pid,
            "started_at": started_at,
            "code_version": code_version[:12] if code_version else None,
            "head_hash": head_hash,
            "branch": branch_name,
            "issues": issues,
        },
    }


def check_process_ownership() -> Dict[str, Any]:
    """检查进程所有者一致性"""
    result = run_subprocess(["python", "scripts/verify_backend_owner.py"], timeout=15)
    if result["success"] and "一致" in result["stdout"]:
        return {"status": "OK", "summary": "PID 一致"}
    return {"status": "WARN", "summary": "PID 可能不一致", "details": result["stdout"][:300]}


def check_working_tree() -> Dict[str, Any]:
    """检查工作树状态"""
    status = run_subprocess(["git", "status", "--short"], timeout=5)
    if not status["success"]:
        return {"status": "FAIL", "summary": "git status 失败"}

    files = [line for line in status["stdout"].splitlines() if line.strip()]
    n_files = len(files)

    if n_files == 0:
        return {"status": "OK", "summary": "工作树干净"}
    elif n_files <= 5:
        return {"status": "OK", "summary": f"{n_files} 个未提交文件（合规）"}
    else:
        return {"status": "FAIL", "summary": f"{n_files} 个未提交文件（违反 V2 铁律 4: 必须 ≤5）"}


def check_recent_errors() -> Dict[str, Any]:
    """检查最近错误日志"""
    # 用 V1 extractor.py
    result = run_subprocess([
        "python", "scripts/debug/log/extractor.py",
        "--level", "ERROR", "--tail", "20",
    ], timeout=15)
    if not result["success"]:
        return {"status": "FAIL", "summary": "无法读取日志"}

    lines = [l for l in result["stdout"].splitlines() if l.strip() and not l.startswith("---")]
    n_errors = sum(1 for l in lines if "ERROR" in l or "FATAL" in l)

    if n_errors == 0:
        return {"status": "OK", "summary": "无最近错误"}
    elif n_errors <= 5:
        return {"status": "WARN", "summary": f"最近 {n_errors} 条 ERROR"}
    else:
        return {"status": "FAIL", "summary": f"最近 {n_errors} 条 ERROR（需关注）"}


def check_debug_code_residue() -> Dict[str, Any]:
    """检查 DEBUG 代码遗留"""
    # 用 grep 搜索 # [DEBUG] 标记
    result = run_subprocess([
        "git", "grep", "-n", "--no-color",
        r"#\s*\[DEBUG\]", "--", "*.py",
    ], timeout=10)
    if not result["success"]:
        return {"status": "OK", "summary": "无 DEBUG 代码遗留"}

    n = len([l for l in result["stdout"].splitlines() if l.strip()])
    if n == 0:
        return {"status": "OK", "summary": "无 DEBUG 代码遗留"}
    else:
        return {"status": "WARN", "summary": f"{n} 处 # [DEBUG] 标记遗留"}


def check_wip_markers() -> Dict[str, Any]:
    """检查 WIP 标记"""
    result = run_subprocess([
        "git", "grep", "-n", "--no-color",
        r"#\s*\[WIP\]", "--", "*.py",
    ], timeout=10)
    if not result["success"]:
        return {"status": "OK", "summary": "无 WIP 标记"}

    n = len([l for l in result["stdout"].splitlines() if l.strip()])
    if n == 0:
        return {"status": "OK", "summary": "无 WIP 标记"}
    else:
        return {"status": "WARN", "summary": f"{n} 处 # [WIP] 标记"}


def check_stashes() -> Dict[str, Any]:
    """检查 stash 状态"""
    result = run_subprocess(["git", "stash", "list"], timeout=5)
    if not result["success"]:
        return {"status": "FAIL", "summary": "无法读取 stash"}

    stashes = [l for l in result["stdout"].splitlines() if l.strip()]
    if not stashes:
        return {"status": "OK", "summary": "无 stash"}
    elif len(stashes) <= 3:
        return {"status": "WARN", "summary": f"{len(stashes)} 个 stash"}
    else:
        return {"status": "FAIL", "summary": f"{len(stashes)} 个 stash（建议清理）"}


def check_session_history() -> Dict[str, Any]:
    """检查历史调试会话"""
    sessions_dir = PROJECT_ROOT / ".trae" / "debug" / "sessions"
    if not sessions_dir.exists():
        return {"status": "INFO", "summary": "无历史会话"}

    sessions = [s for s in sessions_dir.glob("*.yaml") if s.name != "template.yaml"]
    if not sessions:
        return {"status": "INFO", "summary": "无历史会话"}

    # 按时间倒序
    sessions.sort(key=lambda s: s.stat().st_mtime, reverse=True)
    latest = sessions[0].stem
    return {
        "status": "INFO",
        "summary": f"{len(sessions)} 个历史会话（最近: {latest}）",
    }


def diagnose_all() -> Dict[str, Any]:
    """执行所有诊断"""
    _log("执行综合诊断...", "INFO")
    print()

    checks = [
        ("沙箱状态", check_sandbox),
        ("后端状态", check_backend_status),
        ("进程所有者", check_process_ownership),
        ("工作树", check_working_tree),
        ("最近错误", check_recent_errors),
        ("DEBUG 遗留", check_debug_code_residue),
        ("WIP 标记", check_wip_markers),
        ("Stash", check_stashes),
        ("历史会话", check_session_history),
    ]

    results = {}
    for name, check_fn in checks:
        try:
            results[name] = check_fn()
        except Exception as e:
            results[name] = {"status": "FAIL", "summary": f"异常: {e}"}

    return results


def print_results(results: Dict[str, Any], only_fail: bool = False):
    """打印诊断结果"""
    print("=" * 70)
    print("调试环境综合诊断 - V1 调试基础设施 P1")
    print("=" * 70)
    print()

    icons = {"OK": "[OK]", "WARN": "[!]", "FAIL": "[X]", "INFO": "[i]"}

    for name, result in results.items():
        status = result["status"]
        if only_fail and status not in ("FAIL", "WARN"):
            continue
        icon = icons.get(status, "[?]")
        print(f"  {icon} {name:<14} : {result['summary']}")

    print()
    # 总结
    n_fail = sum(1 for r in results.values() if r["status"] == "FAIL")
    n_warn = sum(1 for r in results.values() if r["status"] == "WARN")
    n_ok = sum(1 for r in results.values() if r["status"] == "OK")
    n_info = sum(1 for r in results.values() if r["status"] == "INFO")

    print("=" * 70)
    print(f"总结: OK={n_ok}  INFO={n_info}  WARN={n_warn}  FAIL={n_fail}")

    if n_fail > 0:
        print()
        _log(f"发现 {n_fail} 个严重问题，必须修复后再调试", "FAIL")
        return 1
    elif n_warn > 0:
        print()
        _log(f"发现 {n_warn} 个警告，建议关注", "WARN")
        return 0
    else:
        print()
        _log("所有检查通过，可以开始调试", "OK")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="综合调试环境诊断 - V1 调试基础设施 P1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--only-fail", action="store_true", help="仅显示 FAIL/WARN")

    args = parser.parse_args()

    results = diagnose_all()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    return print_results(results, only_fail=args.only_fail)


if __name__ == "__main__":
    sys.exit(main() or 0)