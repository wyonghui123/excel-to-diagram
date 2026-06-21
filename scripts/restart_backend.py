#!/usr/bin/env python3
"""
restart_backend.py - Restart backend using pythonw (no popup)

Called by watchdog_v30.ps1 instead of service_manager.ps1 to avoid
powershell.exe popup windows.

V2.1 重大修复 (2026-06-21): find_existing_backend() 现在同时查找 python.exe 和 pythonw.exe
事故背景: 之前只查 pythonw.exe，导致旧 python.exe 启动的后端进程没被杀掉，
         请求一直被旧代码处理，修复看似生效但实际无效。

Usage:
    pythonw scripts/restart_backend.py
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(r"d:\filework\excel-to-diagram")
BACKEND_PORT = 3010


def is_port_listening(port):
    """Check if a port is listening"""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result == 0
    except Exception:
        return False


def find_existing_backend():
    """Find existing python OR pythonw processes running waitress_server.

    V2.1 修复 (2026-06-21): 同时查找 python.exe 和 pythonw.exe。
    之前只查 pythonw.exe，导致旧 python.exe 启动的后端进程没被杀掉。
    """
    all_pids = set()

    # V2.1 修复: 同时查找 python.exe 和 pythonw.exe
    for image_name in ("python.exe", "pythonw.exe"):
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image_name}",
                 "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace"
            )
            for line in result.stdout.strip().split("\n"):
                if image_name.lower() not in line.lower():
                    continue
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                        all_pids.add(pid)
                    except Exception:
                        continue
        except Exception:
            continue

    # 对每个候选 PID，验证命令行是否包含 waitress_server.py
    pids = []
    for pid in all_pids:
        try:
            wmic = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}",
                 "get", "CommandLine", "/VALUE"],
                capture_output=True, text=True, timeout=5,
                encoding="utf-8", errors="replace"
            )
            if "waitress_server" in wmic.stdout:
                pids.append(pid)
        except Exception:
            continue
    return pids


def kill_existing_backend():
    """Kill existing backend processes (python.exe AND pythonw.exe)

    V2.1 修复 (2026-06-21): 杀所有 waitress_server.py 启动的 python 进程。
    """
    pids = find_existing_backend()
    killed = []
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=10
            )
            killed.append(pid)
        except Exception:
            continue
    return killed


def start_backend():
    """Start backend using pythonw (no console)"""
    backend_script = REPO_DIR / "waitress_server.py"
    log_out = REPO_DIR / "backend.out"
    log_err = REPO_DIR / "backend.err"

    # Kill existing first
    kill_existing_backend()

    # Use CREATE_NO_WINDOW flag (0x08000000) + DETACHED_PROCESS (0x00000008)
    # to ensure no console window is shown
    flags = 0x08000000  # CREATE_NO_WINDOW

    creationflags = flags

    # Start via pythonw.exe
    pythonw_exe = Path(r"C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe")
    if not pythonw_exe.exists():
        # Try generic pythonw
        import shutil
        pythonw_exe = shutil.which("pythonw") or shutil.which("pythonw.exe")

    if not pythonw_exe:
        print("ERROR: pythonw.exe not found", file=sys.stderr)
        return False

    try:
        # Open log files
        # 🆕 v3.20: waitress_server.py port 来自 env AGENT_PORT
        env = os.environ.copy()
        env["AGENT_PORT"] = str(BACKEND_PORT)
        env["PYTHONIOENCODING"] = "utf-8"

        with open(log_out, "ab") as fout, open(log_err, "ab") as ferr:
            proc = subprocess.Popen(
                [str(pythonw_exe), str(backend_script)],
                cwd=str(REPO_DIR),
                stdout=fout,
                stderr=ferr,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
                env=env,
            )
            print(f"Backend started: PID={proc.pid}, AGENT_PORT={BACKEND_PORT}")
            return True
    except Exception as e:
        print(f"ERROR starting backend: {e}", file=sys.stderr)
        return False


def main():
    # Wait briefly before restart
    import time
    time.sleep(1)

    # Verify port is closed
    if is_port_listening(BACKEND_PORT):
        print(f"Port {BACKEND_PORT} still listening, killing existing")
        kill_existing_backend()
        time.sleep(2)

    # Start backend
    if start_backend():
        # Wait for startup (v3.24: increased from 10s to 30s, waitress needs ~15s)
        for _ in range(30):
            time.sleep(1)
            if is_port_listening(BACKEND_PORT):
                print(f"Backend READY on port {BACKEND_PORT}")
                return 0
        print(f"Backend started but port {BACKEND_PORT} not listening after 30s")
        return 1
    else:
        print("Failed to start backend")
        return 2


if __name__ == "__main__":
    sys.exit(main())