#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Agent 间事件通知系统 - v3.3 新增 (P1-M1)

基于 .coord/events.jsonl 的 append-only 事件日志。
Agent 启动时读最近 N 条事件, 了解其他 Agent 的进度。

用法:
  python scripts/_events.py log <type> <message> [--agent <name>]  # 记录事件
  python scripts/_events.py recent [--limit 20]                    # 读最近事件
  python scripts/_events.py tail                                   # 持续监听 (类似 tail -f)
  python scripts/_events.py since <timestamp>                      # 读某时间后的事件

事件类型:
  - HANDOVER_READY     Agent 完成 HANDOVER, 等待协调智能体
  - CHERRY_PICKED      协调智能体 cherry-pick 完成
  - PM_REVIEW_READY    3006/3011 已就绪, 等 PM 验证
  - PM_VERIFIED        PM 验证通过
  - DEPLOYED           部署完成
  - SERVICE_STARTED    Agent 启动了服务
  - SERVICE_STOPPED    Agent 停止了服务
  - CONFLICT_DETECTED  检测到端口/资源冲突
  - RECOVERED          异常恢复完成
  - CUSTOM             自定义事件
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wt_service import load_paths


def _events_path() -> Path:
    """获取 events.jsonl 路径"""
    paths = load_paths()
    p = Path(paths.get("events_log", ".coord/events.jsonl"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_with_lock(file_path: Path, line: str):
    """带文件锁的 append (防止多 Agent 并发写入交错)

    使用 msvcrt.locking (Windows) 或 fcntl.flock (Linux)
    """
    import msvcrt
    with open(file_path, "a", encoding="utf-8") as f:
        # 锁定文件末尾 1 字节 (Windows msvcrt 方式)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        except (OSError, IOError):
            pass  # 锁失败不阻塞写入 (best-effort)
        try:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            try:
                # 解锁: 先 seek 回 0
                f.seek(0, 2)  # 回到末尾
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except (OSError, IOError):
                pass


def cmd_log(event_type: str, message: str, agent: str = None):
    """记录事件到 events.jsonl"""
    agent = agent or os.environ.get("AGENT_NAME", "unknown")
    event = {
        "timestamp": _now_iso(),
        "type": event_type,
        "agent": agent,
        "message": message,
        "pid": os.getpid(),
    }
    p = _events_path()
    _append_with_lock(p, json.dumps(event, ensure_ascii=False))
    print(f"  [LOGGED] {event_type}: {message} (agent={agent})")


def cmd_recent(limit: int = 20):
    """读最近 N 条事件"""
    p = _events_path()
    if not p.exists():
        print("  No events yet.")
        return

    lines = p.read_text(encoding="utf-8").strip().split("\n")
    events = []
    for line in lines[-limit:]:
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not events:
        print("  No events yet.")
        return

    print("=" * 80)
    print(f"  RECENT EVENTS (last {len(events)})")
    print("=" * 80)
    for e in events:
        ts = e.get("timestamp", "?")[:19]
        etype = e.get("type", "?")
        agent = e.get("agent", "?")
        msg = e.get("message", "")
        print(f"  [{ts}] {etype:20s} | {agent:20s} | {msg}")


def cmd_since(timestamp: str):
    """读某时间后的所有事件"""
    p = _events_path()
    if not p.exists():
        print("  No events yet.")
        return

    events = []
    for line in p.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            try:
                e = json.loads(line)
                if e.get("timestamp", "") >= timestamp:
                    events.append(e)
            except json.JSONDecodeError:
                pass

    print(f"  Events since {timestamp}: {len(events)}")
    for e in events:
        ts = e.get("timestamp", "?")[:19]
        etype = e.get("type", "?")
        agent = e.get("agent", "?")
        msg = e.get("message", "")
        print(f"  [{ts}] {etype:20s} | {agent:20s} | {msg}")


def cmd_tail():
    """持续监听新事件 (类似 tail -f)"""
    p = _events_path()
    print(f"  Tailing {p} (Ctrl+C to stop)")
    last_size = p.stat().st_size if p.exists() else 0

    try:
        while True:
            time.sleep(2)
            if not p.exists():
                continue
            current_size = p.stat().st_size
            if current_size > last_size:
                with open(p, "rb") as f:
                    f.seek(last_size)
                    new_data = f.read().decode("utf-8", errors="replace")
                for line in new_data.strip().split("\n"):
                    if line.strip():
                        try:
                            e = json.loads(line)
                            ts = e.get("timestamp", "?")[:19]
                            etype = e.get("type", "?")
                            agent = e.get("agent", "?")
                            msg = e.get("message", "")
                            print(f"  [{ts}] {etype:20s} | {agent:20s} | {msg}")
                        except json.JSONDecodeError:
                            pass
                last_size = current_size
    except KeyboardInterrupt:
        print("\n  Stopped")


def main():
    parser = argparse.ArgumentParser(description="Agent event log (v3.3)")
    parser.add_argument("command", choices=["log", "recent", "since", "tail"])
    parser.add_argument("arg1", nargs="?", help="event type (for log) or timestamp (for since)")
    parser.add_argument("arg2", nargs="?", help="message (for log)")
    parser.add_argument("--agent", help="agent name")
    parser.add_argument("--limit", type=int, default=20, help="number of events to show")
    args = parser.parse_args()

    if args.command == "log":
        if not args.arg1 or not args.arg2:
            print("Usage: _events.py log <type> <message> [--agent <name>]")
            return 1
        cmd_log(args.arg1, args.arg2, args.agent)
    elif args.command == "recent":
        cmd_recent(args.limit)
    elif args.command == "since":
        if not args.arg1:
            print("Usage: _events.py since <timestamp>")
            return 1
        cmd_since(args.arg1)
    elif args.command == "tail":
        cmd_tail()


if __name__ == "__main__":
    sys.exit(main() or 0)
