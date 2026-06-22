#!/usr/bin/env python3
"""
session_start_bootstrap.py - V3.5 P5 重写版

替代之前的 session_start_bootstrap.ps1：
- 不用 PowerShell（容易触发 sandbox skip）
- 不用管道 / 2>&1
- 不用 Select-Object -First N
- 不用 ForEach-Object

全部用 Python 标准库 subprocess + pathlib + json
"""
import subprocess
import json
import sys
import os
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path("d:/filework/excel-to-diagram")
DEBUG_DIR = PROJECT_ROOT / ".trae" / "debug"
STATUS_FILE = DEBUG_DIR / "session_start_status.json"


def run_simple(cmd, cwd=None, timeout=10):
    """简单 subprocess 调用，无管道"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=cwd, timeout=timeout
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


def check_port(port):
    """通过 ss 检查端口（不用 powershell Get-NetTCPConnection）"""
    try:
        result = subprocess.run(
            ["ss", "-tln", "sport", "=", str(port)],
            capture_output=True, text=True, timeout=5
        )
        # ss 输出格式: LISTEN 0 128 *:3010 *:*
        if "LISTEN" in result.stdout:
            # 找 PID
            ss_pid = subprocess.run(
                ["ss", "-tlnp", "sport", "=", str(port)],
                capture_output=True, text=True, timeout=5
            )
            pid = None
            for line in ss_pid.stdout.split("\n"):
                if "pid=" in line:
                    # 提取 pid
                    import re
                    m = re.search(r'pid=(\d+)', line)
                    if m:
                        pid = int(m.group(1))
                        break
            return {"status": "running", "port": port, "pid": pid}
        return {"status": "down", "port": port}
    except FileNotFoundError:
        # 没有 ss 命令，fallback 到 netstat
        return check_port_netstat(port)
    except Exception as e:
        return {"status": "error", "port": port, "error": str(e)}


def check_port_netstat(port):
    """netstat fallback"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                return {"status": "running", "port": port, "pid": pid}
        return {"status": "down", "port": port}
    except Exception as e:
        return {"status": "error", "port": port, "error": str(e)}


def main():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    status = {
        "timestamp": datetime.now().isoformat(),
        "project_root": str(PROJECT_ROOT),
    }

    # Backend / Frontend check
    status["backend"] = check_port(3010)
    status["frontend"] = check_port(3004)

    # Git status
    git_status = run_simple(["git", "status", "--short"], cwd=str(PROJECT_ROOT))
    if git_status["ok"]:
        files = [l for l in git_status["stdout"].split("\n") if l.strip()]
        status["git"] = {
            "clean": len(files) == 0,
            "file_count": len(files),
            "files": files[:50],  # 限 50
        }
    else:
        status["git"] = {"error": git_status["stderr"]}

    # Git branch
    branch = run_simple(["git", "branch", "--show-current"], cwd=str(PROJECT_ROOT))
    if branch["ok"]:
        status["git"]["branch"] = branch["stdout"]

    # Git HEAD
    head = run_simple(["git", "log", "--oneline", "-1"], cwd=str(PROJECT_ROOT))
    if head["ok"]:
        status["git"]["head"] = head["stdout"]

    # Worktree list
    worktrees = run_simple(["git", "worktree", "list"], cwd=str(PROJECT_ROOT))
    if worktrees["ok"]:
        status["worktrees"] = [
            line for line in worktrees["stdout"].split("\n") if line.strip()
        ]

    # Write status file (Python I/O 不会被 sandbox 吞)
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Cannot write status file: {e}", file=sys.stderr)
        sys.exit(1)

    # 短输出（避免缓冲）
    b = status.get("backend", {}).get("status", "?")
    f_ = status.get("frontend", {}).get("status", "?")
    branch_name = status.get("git", {}).get("branch", "?")
    uncommitted = status.get("git", {}).get("file_count", "?")
    print(f"[SessionStart] Backend: {b}, Frontend: {f_}, Branch: {branch_name}, Uncommitted: {uncommitted}")
    print(f"[SessionStart] Status: {STATUS_FILE}")


if __name__ == "__main__":
    main()