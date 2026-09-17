#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
协调智能体操作日志 - v3.3 新增 (P1-M3)

Append-only 操作审计日志, 记录协调智能体的所有决策和操作。

用法:
  python scripts/_coord_log.py log <action> <detail>          # 记录操作
  python scripts/_coord_log.py recent [--limit 20]            # 读最近操作
  python scripts/_coord_log.py search <keyword>               # 搜索操作
  python scripts/_coord_log.py audit                           # 审计检查 (违规检测)

日志格式 (JSONL):
  {"timestamp": "...", "action": "...", "detail": "...", "session": "..."}
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wt_service import load_paths


def _log_path() -> Path:
    paths = load_paths()
    p = Path(paths.get("log_dir", ".coord")) / "coordination.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_with_lock(file_path: Path, line: str):
    """带文件锁的 append (防止多 Agent 并发写入交错)"""
    import msvcrt
    with open(file_path, "a", encoding="utf-8") as f:
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        except (OSError, IOError):
            pass
        try:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            try:
                f.seek(0, 2)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except (OSError, IOError):
                pass


# 违规检测规则
VIOLATION_PATTERNS = {
    "modified_src": {"pattern": "modified src/", "severity": "HIGH", "rule": "§0.8.4 禁止改 src/"},
    "modified_meta": {"pattern": "modified meta/", "severity": "HIGH", "rule": "§0.8.4 禁止改 meta/"},
    "modified_frontend": {"pattern": "modified frontend/src/", "severity": "HIGH", "rule": "§0.8.4 禁止改 frontend/src/"},
    "git_add_A": {"pattern": "git add -A", "severity": "HIGH", "rule": "L2_violation: 应用 explicit file list"},
    "main_commit": {"pattern": "commit in main", "severity": "CRITICAL", "rule": "L2 NoMain: 禁止在主工作树 commit"},
    "force_push": {"pattern": "push --force", "severity": "CRITICAL", "rule": "禁止 force push"},
    "reset_hard": {"pattern": "reset --hard", "severity": "HIGH", "rule": "禁止 git reset --hard"},
}


def cmd_log(action: str, detail: str):
    """记录协调操作"""
    entry = {
        "timestamp": _now_iso(),
        "action": action,
        "detail": detail,
        "session": os.environ.get("TRADE_SESSION_ID", "unknown"),
        "pid": os.getpid(),
    }
    p = _log_path()
    _append_with_lock(p, json.dumps(entry, ensure_ascii=False))
    print(f"  [LOGGED] {action}: {detail[:80]}")


def cmd_recent(limit: int = 20):
    """读最近操作"""
    p = _log_path()
    if not p.exists():
        print("  No coordination log yet.")
        return

    lines = p.read_text(encoding="utf-8").strip().split("\n")
    entries = []
    for line in lines[-limit:]:
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not entries:
        print("  No coordination log yet.")
        return

    print("=" * 80)
    print(f"  COORDINATION LOG (last {len(entries)})")
    print("=" * 80)
    for e in entries:
        ts = e.get("timestamp", "?")[:19]
        action = e.get("action", "?")
        detail = e.get("detail", "")
        session = e.get("session", "?")[:8]
        print(f"  [{ts}] {action:25s} | {session} | {detail}")


def cmd_search(keyword: str):
    """搜索操作"""
    p = _log_path()
    if not p.exists():
        print("  No coordination log yet.")
        return

    matches = []
    for line in p.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip() and keyword.lower() in line.lower():
            try:
                matches.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    print(f"  Found {len(matches)} matches for '{keyword}':")
    for e in matches:
        ts = e.get("timestamp", "?")[:19]
        action = e.get("action", "?")
        detail = e.get("detail", "")
        print(f"  [{ts}] {action:25s} | {detail}")


def cmd_audit():
    """审计检查: 扫描日志中的违规操作"""
    p = _log_path()
    if not p.exists():
        print("  No coordination log yet.")
        return

    entries = []
    for line in p.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    print("=" * 80)
    print("  COORDINATION AUDIT")
    print(f"  Total entries: {len(entries)}")
    print("=" * 80)

    violations = []
    for e in entries:
        detail = e.get("detail", "").lower()
        action = e.get("action", "").lower()
        combined = f"{action} {detail}"

        for vname, vinfo in VIOLATION_PATTERNS.items():
            if vinfo["pattern"].lower() in combined:
                violations.append({
                    "timestamp": e.get("timestamp"),
                    "violation": vname,
                    "severity": vinfo["severity"],
                    "rule": vinfo["rule"],
                    "detail": e.get("detail", ""),
                })

    if violations:
        print(f"\n  [VIOLATIONS] {len(violations)} found:")
        for v in violations:
            print(f"    [{v['severity']}] {v['timestamp'][:19]} {v['violation']}")
            print(f"      rule: {v['rule']}")
            print(f"      detail: {v['detail'][:100]}")
    else:
        print(f"\n  [OK] No violations found in {len(entries)} entries")


def main():
    parser = argparse.ArgumentParser(description="Coordination audit log (v3.3)")
    parser.add_argument("command", choices=["log", "recent", "search", "audit"])
    parser.add_argument("arg1", nargs="?", help="action (for log) or keyword (for search)")
    parser.add_argument("arg2", nargs="?", help="detail (for log)")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if args.command == "log":
        if not args.arg1 or not args.arg2:
            print("Usage: _coord_log.py log <action> <detail>")
            return 1
        cmd_log(args.arg1, args.arg2)
    elif args.command == "recent":
        cmd_recent(args.limit)
    elif args.command == "search":
        if not args.arg1:
            print("Usage: _coord_log.py search <keyword>")
            return 1
        cmd_search(args.arg1)
    elif args.command == "audit":
        cmd_audit()


if __name__ == "__main__":
    sys.exit(main() or 0)
