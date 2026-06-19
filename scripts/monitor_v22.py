#!/usr/bin/env python3
"""
monitor_v22.py - Integrated Monitor + Violation Detection v2.2

v2.2 新增：
- 集成 violation_auto.py 的违规检测
- 自动记录 L2 violations 到 .agent-violations.json
- 主工作树修改即时告警
- 孤儿 worktree 扫描

Usage:
    pythonw scripts/monitor_v22.py
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(r"d:\filework\excel-to-diagram")
VIOLATIONS_FILE = REPO_DIR / ".agent-violations.json"
LOG_FILE = Path(r"d:\filework\monitor_v22.log")
PORTS_FILE = Path(r"d:\filework\.coord\ports.json")
INTERVAL = 30


def run_git(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def check_port(port):
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("127.0.0.1", port))
        sock.close()
        return True
    except Exception:
        return False


def get_violations():
    if VIOLATIONS_FILE.exists():
        try:
            return json.loads(VIOLATIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"L2_violations": 0, "details": []}


def save_violations(data):
    VIOLATIONS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def check_orphans():
    orphans = []
    parent = REPO_DIR.parent
    if not parent.exists():
        return orphans
    for item in parent.iterdir():
        if item.is_dir() and "worktree" in item.name.lower():
            git_path = item / ".git"
            if not git_path.exists():
                wt_list = run_git(["worktree", "list"])
                if item.name not in wt_list:
                    orphans.append(item.name)
    return orphans


def check_main_status():
    out = run_git(["status", "--porcelain"])
    modified = sum(1 for l in out.split("\n") if l.strip() and len(l) > 1 and l[1] == "M")
    untracked = sum(1 for l in out.split("\n") if l.strip().startswith("??"))
    return modified, untracked


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def detect_and_record_violations(prev_state):
    """Detect violations and auto-record"""
    current = {
        "modified": 0,
        "untracked": 0,
        "orphans": [],
        "v_count": 0,
    }

    current["modified"], current["untracked"] = check_main_status()
    current["orphans"] = check_orphans()

    data = get_violations()
    current["v_count"] = data.get("L2_violations", 0)

    # Auto-record orphan detection
    if current["orphans"] and not prev_state["orphans"]:
        # New orphans detected
        log(f"[WARN] NEW ORPHANS: {current['orphans']}")
        count = data.get("L2_violations", 0) + 1
        data["L2_violations"] = count
        data["last_violation"] = datetime.now().isoformat()
        data["details"].append({
            "id": count,
            "date": datetime.now().isoformat(),
            "reason": "orphan_worktree",
            "details": f"Detected by monitor: {current['orphans']}",
            "source": "monitor_v22"
        })
        save_violations(data)

    # Auto-record main worktree changes
    if current["modified"] > prev_state["modified"] + 20:
        log(f"[WARN] MAIN WORKTREE: {prev_state['modified']} -> {current['modified']} modifications")
        count = data.get("L2_violations", 0) + 1
        data["L2_violations"] = count
        data["last_violation"] = datetime.now().isoformat()
        data["details"].append({
            "id": count,
            "date": datetime.now().isoformat(),
            "reason": "main_modified",
            "details": f"Monitor detected: {prev_state['modified']} -> {current['modified']}",
            "source": "monitor_v22"
        })
        save_violations(data)

    return current


def main():
    log("=" * 60)
    log("Monitor v2.2 STARTED (integrated violation detection)")
    log(f"PID: {os.getpid()}, cwd: {REPO_DIR}")
    log("=" * 60)

    iteration = 0
    prev_state = {
        "modified": 0,
        "untracked": 0,
        "orphans": [],
        "v_count": 0,
    }

    while True:
        iteration += 1
        ts_short = datetime.now().strftime("%H:%M:%S")

        # Service health
        fe_ok = check_port(3004)
        be_ok = check_port(3010)

        # Worktrees
        wt_out = run_git(["worktree", "list"])
        wt_count = len([l for l in wt_out.split("\n") if l.strip()])

        # Stash
        stash_out = run_git(["stash", "list"])
        stash_count = len([l for l in stash_out.split("\n") if l.strip()])

        # Violation detection
        prev_state = detect_and_record_violans(prev_state)

        # Status log
        status = "OK" if fe_ok and be_ok else "WARN"
        log(f"[{ts_short}] #{iteration} {status} fe={'200' if fe_ok else '000'} "
            f"be={'401' if be_ok else '000'} wt={wt_count} "
            f"stash={stash_count} mainM={prev_state['modified']} "
            f"orphans={len(prev_state['orphans'])} "
            f"violations={prev_state['v_count']}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Monitor stopped by user")
        sys.exit(0)