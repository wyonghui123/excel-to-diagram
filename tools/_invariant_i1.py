#!/usr/bin/env python3
"""[2026-09-16] invariant I1: server.py 进程 cwd 检查.

通过 /proc 直接读 PID, 不依赖 shell grep 模式 (避免 pgrep 匹配 bash 自身).
"""
import os

PID = None
CMDLINE = ""
# 遍历 /proc, 找 cmdline 含 server.py 且是 python 启动的
for entry in sorted(os.listdir("/proc"), key=lambda x: int(x) if x.isdigit() else 0):
    if not entry.isdigit():
        continue
    try:
        with open(f"/proc/{entry}/cmdline", "rb") as f:
            cmdline = f.read().replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        if "server.py" in cmdline and "python" in cmdline and "awk" not in cmdline:
            PID = entry
            CMDLINE = cmdline
            break
    except (PermissionError, FileNotFoundError, ProcessLookupError):
        continue

if PID:
    try:
        CWD = os.readlink(f"/proc/{PID}/cwd")
    except (PermissionError, FileNotFoundError):
        CWD = "READLINK_DENIED"
    print(f"PID={PID}")
    print(f"CWD={CWD}")
    print(f"CMDLINE={CMDLINE}")
else:
    print("PID=")
    print("CWD=NO_SERVER")
    print("CMDLINE=")
