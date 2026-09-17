#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ports.json 维护脚本 - P0-3 自动清理 stale 端口 (2026-07-17 协调智能体创建)

问题:
- .coord/ports.json 列出 4 个已分配端口 (3011-3015)
- 对应的 worktree 已删除 (49 -> 12 branch 清理时删了)
- ports.json 永远显示 stale 数据, 协调智能体无法准确知道哪些 agent 活着

功能:
- sync: 扫描实际 wt, 标记 ports.json 中 stale 端口
- list: 列出 ports.json 当前状态 + wt 状态 + stale 标记
- clean: 删除 ports.json 中 stale 端口 (需 PM 决策)
- allocate <agent> <port>: 添加新端口分配 (替代 allocate_ports.py 的一部分)

用法:
  python scripts/_ports_sync.py list
  python scripts/_ports_sync.py sync
  python scripts/_ports_sync.py clean --dry-run
  python scripts/_ports_sync.py allocate agent-x 3013
"""
import argparse
import json
import msvcrt
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# V007.71 路径: 从 paths.json 读 (P0-1) 但 fallback 到硬编码
PATHS_FILE = Path("D:/filework/.coord/paths.json")
DEFAULT_PATHS = {
    "worktree_base": "D:/filework/worktrees",
    "ports_registry": "D:/filework/.coord/ports.json",
    "main_repo": "D:/filework/excel-to-diagram",
}


def load_paths() -> dict:
    """从 paths.json 读路径配置, fallback 到默认"""
    if PATHS_FILE.exists():
        try:
            with open(PATHS_FILE, encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_PATHS


def load_ports() -> dict:
    """读 ports.json"""
    paths = load_paths()
    p = Path(paths["ports_registry"])
    if not p.exists():
        return {"reserved": {}, "allocated": {}}
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {"reserved": {}, "allocated": {}}


def _lock_path() -> Path:
    """获取 ports.json 的锁文件路径"""
    paths = load_paths()
    return Path(paths["ports_registry"]).with_suffix(".lock")


def _acquire_lock():
    """获取 ports.json 文件锁 (Windows msvcrt, 阻塞式)"""
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock, "w")
    # 阻塞等待独占锁, 最多 10 秒
    deadline = time.time() + 10
    while True:
        try:
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
            return fd
        except OSError:
            if time.time() > deadline:
                fd.close()
                raise TimeoutError("ports.json lock timeout (10s)")
            time.sleep(0.1)


def _release_lock(fd):
    """释放 ports.json 文件锁"""
    try:
        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    fd.close()
    try:
        _lock_path().unlink()
    except OSError:
        pass


def save_ports(ports: dict):
    """写 ports.json (带文件锁, 防止并发写入)"""
    import time
    fd = None
    try:
        fd = _acquire_lock()
        paths = load_paths()
        p = Path(paths["ports_registry"])
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ports, f, indent=2, ensure_ascii=False)
        print(f"  saved: {p}")
    finally:
        if fd:
            _release_lock(fd)


def list_worktrees() -> list:
    """列出所有 wt 路径 (git worktree list)"""
    paths = load_paths()
    main_repo = paths["main_repo"]
    try:
        r = subprocess.run(
            ["git", "-C", main_repo, "worktree", "list", "--porcelain"],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        if r.returncode != 0:
            return []
        wts = []
        for line in r.stdout.split("\n"):
            if line.startswith("worktree "):
                wts.append(line[9:].strip())
        return wts
    except Exception:
        return []


def wt_exists(wt_path: str) -> bool:
    """检查 wt 路径是否存在"""
    if not wt_path:
        return False
    # 兼容反斜杠和正斜杠
    p = Path(wt_path.replace("\\", "/"))
    return p.exists() and (p / ".git").exists() or _is_wt_workdir(p)


def _is_wt_workdir(p: Path) -> bool:
    """检查是否是有效 wt (有 .git 文件)"""
    git_file = p / ".git"
    if git_file.is_file():
        return True
    return False


def cmd_list():
    """列出 ports 状态 + wt 状态"""
    ports = load_ports()
    wts = list_worktrees()
    wt_set = {wt.replace("\\", "/") for wt in wts}

    print("=" * 70)
    print("PORTS REGISTRY SYNC STATUS")
    print("=" * 70)
    print(f"\nActual worktrees: {len(wts)}")
    for wt in wts:
        print(f"  - {wt}")

    print(f"\nReserved ports:")
    for port, info in ports.get("reserved", {}).items():
        print(f"  {port}: {info}")

    print(f"\nAllocated ports:")
    stale_count = 0
    active_count = 0
    for port, info in ports.get("allocated", {}).items():
        wt_path = info.get("worktree", "")
        wt_path_norm = wt_path.replace("\\", "/")
        is_stale = wt_path_norm not in wt_set
        marker = "[STALE]" if is_stale else "[ACTIVE]"
        if is_stale:
            stale_count += 1
        else:
            active_count += 1
        owner = info.get("owner", "?")
        branch = info.get("branch", "?")
        status = info.get("status", "?")
        print(f"  {port}: {owner} ({branch}) status={status} {marker}")
        if is_stale:
            print(f"      -> stale worktree: {wt_path}")

    print(f"\nSummary: {active_count} active, {stale_count} stale")


def cmd_sync():
    """扫描实际 wt, 标记 stale 端口 (不删除, 只更新状态)"""
    ports = load_ports()
    wts = list_worktrees()
    wt_set = {wt.replace("\\", "/") for wt in wts}
    updated = 0

    for port, info in ports.get("allocated", {}).items():
        wt_path = info.get("worktree", "")
        wt_path_norm = wt_path.replace("\\", "/")
        is_stale = wt_path_norm not in wt_set
        current_status = info.get("status", "")

        if is_stale and current_status != "stale":
            info["status"] = "stale"
            info["stale_detected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            info["stale_reason"] = f"worktree not in git worktree list ({len(wts)} wts)"
            updated += 1
            print(f"  {port}: marked stale (wt={wt_path})")
        elif not is_stale and current_status == "stale":
            info["status"] = "active"
            info["stale_cleared_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            updated += 1
            print(f"  {port}: cleared stale (wt={wt_path})")

    if updated > 0:
        save_ports(ports)
        print(f"\nUpdated {updated} entries")
    else:
        print("\nNo changes needed")


def cmd_clean(dry_run: bool = True):
    """删除 stale 端口 (PM 决策)"""
    ports = load_ports()
    wts = list_worktrees()
    wt_set = {wt.replace("\\", "/") for wt in wts}
    to_remove = []

    for port, info in ports.get("allocated", {}).items():
        wt_path = info.get("worktree", "")
        wt_path_norm = wt_path.replace("\\", "/")
        if wt_path_norm not in wt_set:
            to_remove.append(port)

    if not to_remove:
        print("No stale ports to clean")
        return

    print(f"Stale ports to remove ({len(to_remove)}):")
    for port in to_remove:
        info = ports["allocated"][port]
        print(f"  {port}: {info.get('owner', '?')} -> {info.get('worktree', '?')}")

    if dry_run:
        print("\n[DRY-RUN] No changes made. Run without --dry-run to apply.")
    else:
        for port in to_remove:
            del ports["allocated"][port]
        save_ports(ports)
        print(f"\nRemoved {len(to_remove)} stale ports")


def cmd_allocate(agent: str, port: int):
    """分配端口 (类似 allocate_ports.py 但写入协调层, 检查全段冲突)"""
    ports = load_ports()

    # [v3.3] 检查 reserved 段 (主仓库端口)
    if str(port) in ports.get("reserved", {}):
        print(f"  ERROR: port {port} is reserved for main ({ports['reserved'][str(port)]['description']})")
        return

    # [v3.3] 检查 persistent 段 (release-prep/integration)
    for p_str, info in ports.get("persistent", {}).items():
        for field in ("backend_port", "frontend_port"):
            if info.get(field) == port:
                print(f"  ERROR: port {port} conflicts with persistent entry '{info.get('owner')}' "
                      f"(field={field}, key={p_str})")
                return
        try:
            if int(p_str) == port:
                print(f"  ERROR: port {port} is persistent key for '{info.get('owner')}'")
                return
        except ValueError:
            pass

    # [v3.3] 检查 allocated 段
    if str(port) in ports.get("allocated", {}):
        existing = ports["allocated"][str(port)]
        print(f"  ERROR: port {port} already allocated to {existing.get('owner')}")
        return

    # [v3.3] 检查运行时状态 (端口是否正在使用)
    for section in ("reserved", "persistent", "allocated"):
        for p_str, info in ports.get(section, {}).items():
            if info.get("runtime_status") == "running" and info.get("runtime_pid"):
                for field in ("backend_port", "frontend_port"):
                    if info.get(field) == port:
                        print(f"  ERROR: port {port} is runtime-running by '{info.get('owner')}' "
                              f"(PID={info.get('runtime_pid')})")
                        return

    paths = load_paths()
    wt_path = f"{paths['worktree_base']}/{agent}"
    branch_name = f"agent/{agent}"

    ports["allocated"][str(port)] = {
        "owner": agent,
        "branch": branch_name,
        "worktree": wt_path,
        "role": "agent-worktree",
        "status": "active",
        "allocated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_ports(ports)
    print(f"  allocated: {port} -> {agent} (wt: {wt_path})")


def main():
    parser = argparse.ArgumentParser(
        description="ports.json 维护脚本 - P0-3 自动清理 stale 端口"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出 ports 状态 + wt 状态")

    sub.add_parser("sync", help="扫描实际 wt, 标记 stale 端口")

    clean_p = sub.add_parser("clean", help="删除 stale 端口 (PM 决策)")
    clean_p.add_argument("--dry-run", action="store_true", default=True)
    clean_p.add_argument("--apply", dest="dry_run", action="store_false")

    alloc_p = sub.add_parser("allocate", help="分配端口给 agent")
    alloc_p.add_argument("agent")
    alloc_p.add_argument("port", type=int)

    args = parser.parse_args()

    if args.cmd == "list":
        cmd_list()
    elif args.cmd == "sync":
        cmd_sync()
    elif args.cmd == "clean":
        cmd_clean(dry_run=args.dry_run)
    elif args.cmd == "allocate":
        cmd_allocate(args.agent, args.port)


if __name__ == "__main__":
    main()