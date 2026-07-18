#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Worktree 生命周期管理器 - v3.3 新增

统一管理 worktree 的创建/删除/清理, 与 ports.json 联动。

用法:
  python scripts/_wt_lifecycle.py list                      # 列出所有 worktree + 状态
  python scripts/_wt_lifecycle.py create <name> [branch]    # 创建 worktree + 注册到 ports.json
  python scripts/_wt_lifecycle.py remove <name>             # 删除 worktree + 清理 ports.json
  python scripts/_wt_lifecycle.py gc                        # 垃圾回收 (清理 stale worktree + 孤儿端口)
  python scripts/_wt_lifecycle.py health                    # 健康检查 (worktree vs ports.json 一致性)

设计原则:
  1. 所有 worktree 创建/删除必须通过本脚本 (单一入口)
  2. 创建时自动分配端口 + 注册到 ports.json
  3. 删除时自动清理 ports.json + git branch
  4. gc 清理: stale worktree (路径不存在但 ports.json 有记录) + 孤儿端口 (端口监听但无 worktree)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 复用 _wt_service.py 的工具函数
sys.path.insert(0, str(Path(__file__).parent))
from _wt_service import (
    load_paths, load_ports, save_ports, find_port_owner,
    check_port, _get_listening_ports, _now_iso
)


def _run_git(args: list, cwd: str = None, timeout: int = 30) -> tuple:
    """运行 git 命令, 返回 (returncode, stdout, stderr)"""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd or str(Path(load_paths()["main_repo"])),
            capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except Exception as e:
        return 1, "", str(e)


def cmd_list():
    """列出所有 worktree + 状态"""
    paths = load_paths()
    wt_base = paths["worktree_base"]

    # git worktree list
    rc, out, _ = _run_git(["worktree", "list", "--porcelain"])
    worktrees = []
    if rc == 0:
        current = {}
        for line in out.split("\n"):
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line[9:], "branches": []}
            elif line.startswith("HEAD "):
                current["head"] = line[5:]
            elif line.startswith("branch "):
                current["branches"].append(line[7:])
            elif line.startswith("detached"):
                current["detached"] = True
        if current:
            worktrees.append(current)

    # ports.json 状态
    ports = load_ports()

    print("=" * 80)
    print("  WORKTREE LIFECYCLE STATUS")
    print(f"  Generated: {_now_iso()}")
    print("=" * 80)

    print(f"\n  Git worktrees: {len(worktrees)}")
    for wt in worktrees:
        path = wt["path"]
        name = Path(path).name
        head = wt.get("head", "unknown")[:8]
        branches = ", ".join(wt.get("branches", [])) or "(detached)"
        dirty = _check_dirty(path)

        # 检查 ports.json 是否有记录
        in_ports = _find_wt_in_ports(name, ports)

        status = "ACTIVE" if Path(path).exists() else "MISSING"
        port_info = f"be={in_ports['be_port']}, fe={in_ports['fe_port']}" if in_ports else "NO_PORTS"

        print(f"\n  [{status}] {name}")
        print(f"    path: {path}")
        print(f"    head: {head}  branch: {branches}")
        print(f"    dirty: {dirty} files  ports: {port_info}")

    # 检查 ports.json 中有记录但 git worktree list 没有的
    git_paths = {wt["path"] for wt in worktrees}
    orphan_ports = []
    for section in ("allocated", "persistent"):
        for port_str, info in ports.get(section, {}).items():
            wt_path = info.get("worktree", "")
            if wt_path and wt_path not in git_paths and Path(wt_path).exists() is False:
                orphan_ports.append((section, port_str, info))

    if orphan_ports:
        print(f"\n  [ORPHAN PORTS] {len(orphan_ports)} port(s) in ports.json but worktree missing:")
        for section, port_str, info in orphan_ports:
            print(f"    - {section}/{port_str}: owner={info.get('owner')}, wt={info.get('worktree')}")
        print(f"    FIX: _wt_lifecycle.py gc")


def _check_dirty(wt_path: str) -> int:
    """检查 worktree 有多少 dirty 文件"""
    rc, out, _ = _run_git(["status", "--porcelain"], cwd=wt_path)
    if rc != 0:
        return -1
    return len([l for l in out.split("\n") if l.strip()])


def _find_wt_in_ports(name: str, ports: dict) -> dict | None:
    """在 ports.json 中查找 worktree 的端口信息"""
    for section in ("allocated", "persistent"):
        for port_str, info in ports.get(section, {}).items():
            if info.get("owner") == name or info.get("worktree", "").endswith(name):
                return {
                    "section": section,
                    "be_port": info.get("backend_port", port_str),
                    "fe_port": info.get("frontend_port", "N/A"),
                }
    return None


def cmd_create(name: str, branch: str = None):
    """创建 worktree + 自动分配端口 + 注册到 ports.json"""
    paths = load_paths()
    wt_base = paths["worktree_base"]
    wt_path = f"{wt_base}/{name}"
    branch = branch or f"agent/{name}"

    if Path(wt_path).exists():
        print(f"  [ERROR] worktree path already exists: {wt_path}")
        return 1

    # 创建 worktree
    rc, out, err = _run_git(["worktree", "add", "-b", branch, wt_path])
    if rc != 0:
        print(f"  [ERROR] git worktree add failed: {err}")
        return 1

    print(f"  [OK] worktree created: {wt_path} (branch: {branch})")

    # 分配端口 (找最小可用)
    ports = load_ports()
    used_ports = set()
    for section in ("reserved", "persistent", "allocated"):
        for port_str, info in ports.get(section, {}).items():
            try:
                used_ports.add(int(port_str))
            except ValueError:
                pass
            for field in ("backend_port", "frontend_port"):
                if info.get(field):
                    used_ports.add(info[field])

    # 分配 backend + frontend 端口对
    be_port = 3020
    while be_port in used_ports:
        be_port += 1
    fe_port = be_port + 50  # frontend 在 backend+50 (如 3020/3070)
    while fe_port in used_ports:
        fe_port += 1

    # 注册到 ports.json
    ports.setdefault("allocated", {})[str(be_port)] = {
        "owner": name,
        "branch": branch,
        "worktree": wt_path,
        "backend_port": be_port,
        "frontend_port": fe_port,
        "role": "agent-worktree",
        "status": "active",
        "created_at": _now_iso(),
    }
    save_ports(ports)
    print(f"  [OK] ports allocated: backend={be_port}, frontend={fe_port}")
    print(f"  [OK] registered in ports.json")

    return 0


def cmd_remove(name: str, force: bool = False):
    """删除 worktree + 清理 ports.json + 删除 branch"""
    paths = load_paths()
    wt_base = paths["worktree_base"]
    wt_path = f"{wt_base}/{name}"

    # 检查 dirty
    if Path(wt_path).exists() and not force:
        dirty = _check_dirty(wt_path)
        if dirty > 0:
            print(f"  [ERROR] worktree has {dirty} dirty files. Use --force to remove anyway.")
            return 1

    # 停服务 (如果在运行)
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from _wt_service import cmd_stop
        cmd_stop(name)
    except Exception:
        pass

    # git worktree remove
    rc, out, err = _run_git(["worktree", "remove", wt_path, "--force" if force else ""])
    if rc != 0:
        print(f"  [WARN] git worktree remove: {err}")
        # 尝试强制删除目录
        if Path(wt_path).exists():
            import shutil
            shutil.rmtree(wt_path, ignore_errors=True)

    print(f"  [OK] worktree removed: {wt_path}")

    # 清理 ports.json
    ports = load_ports()
    removed = 0
    for section in ("allocated", "persistent"):
        to_remove = []
        for port_str, info in ports.get(section, {}).items():
            if info.get("owner") == name or info.get("worktree", "").endswith(name):
                to_remove.append(port_str)
        for port_str in to_remove:
            del ports[section][port_str]
            removed += 1
    if removed:
        save_ports(ports)
        print(f"  [OK] cleaned {removed} port entries from ports.json")

    # 删除 branch (可选)
    branch = f"agent/{name}"
    rc, _, _ = _run_git(["branch", "-D", branch])
    if rc == 0:
        print(f"  [OK] branch deleted: {branch}")

    return 0


def cmd_gc(clean_node_modules: bool = False):
    """垃圾回收: 清理 stale worktree 记录 + 孤儿端口 + (可选) node_modules

    Args:
        clean_node_modules: 清理不活跃 worktree 的 node_modules (P2-S5)
    """
    paths = load_paths()
    ports = load_ports()
    cleaned = 0

    print("=" * 70)
    print("  GARBAGE COLLECTION")
    print(f"  Generated: {_now_iso()}")
    if clean_node_modules:
        print(f"  Mode: INCLUDE node_modules cleanup")
    print("=" * 70)

    # 1. 清理 ports.json 中 worktree 路径不存在的记录
    for section in ("allocated", "persistent"):
        to_remove = []
        for port_str, info in ports.get(section, {}).items():
            wt_path = info.get("worktree", "")
            if wt_path and not Path(wt_path).exists():
                to_remove.append(port_str)
                print(f"\n  [STALE] {section}/{port_str}: owner={info.get('owner')}, wt={wt_path}")
        for port_str in to_remove:
            del ports[section][port_str]
            cleaned += 1
            print(f"    [CLEANED] removed {section}/{port_str}")

    # 2. git worktree prune (清理 git 内部记录)
    rc, _, err = _run_git(["worktree", "prune", "--expire=now"])
    if rc == 0:
        print(f"\n  [OK] git worktree prune done")
    else:
        print(f"\n  [WARN] git worktree prune: {err}")

    # 3. 检查孤儿端口 (端口在监听但 ports.json 无记录)
    actual = _get_listening_ports()
    project_ports = set()
    for section in ("reserved", "persistent", "allocated"):
        for port_str, info in ports.get(section, {}).items():
            try:
                project_ports.add(int(port_str))
            except ValueError:
                pass
            for field in ("backend_port", "frontend_port"):
                if info.get(field):
                    project_ports.add(info[field])

    orphans = [p for p in actual if 3000 <= p <= 3100 and p not in project_ports]
    if orphans:
        print(f"\n  [ORPHAN PORTS] {len(orphans)} port(s) listening but not in ports.json:")
        for port in orphans:
            print(f"    - port {port}: PID={actual[port]}")
        print(f"    FIX: _wt_service.py force-stop-port <port>")

    # 4. (P2-S5) 清理不活跃 worktree 的 node_modules
    if clean_node_modules:
        print(f"\n  [NODE_MODULES CLEANUP]")
        rc, out, _ = _run_git(["worktree", "list", "--porcelain"])
        active_wts = set()
        if rc == 0:
            for line in out.split("\n"):
                if line.startswith("worktree "):
                    active_wts.add(line[9:])

        # 检查 sessions.json 中的活跃会话
        sessions_file = Path(paths.get("main_repo", ".")) / ".coord" / "sessions.json"
        active_sessions = set()
        if sessions_file.exists():
            try:
                import json
                data = json.loads(sessions_file.read_text(encoding="utf-8"))
                for wt_name in data.get("sessions", {}):
                    active_sessions.add(wt_name)
            except Exception:
                pass

        nm_cleaned = 0
        nm_total_saved = 0
        # 扫描 worktrees/ 目录
        wt_base = Path(paths["worktree_base"])
        if wt_base.exists():
            for wt_dir in wt_base.iterdir():
                if not wt_dir.is_dir():
                    continue
                wt_name = wt_dir.name
                nm_path = wt_dir / "frontend" / "node_modules"
                if not nm_path.exists():
                    nm_path = wt_dir / "node_modules"
                if not nm_path.exists():
                    continue

                # 计算大小
                try:
                    import shutil
                    nm_size = sum(f.stat().st_size for f in nm_path.rglob("*") if f.is_file())
                    nm_size_mb = nm_size / (1024 * 1024)
                except Exception:
                    nm_size_mb = 0

                # 判断是否活跃
                is_active = str(wt_dir) in active_wts or wt_name in active_sessions
                if is_active:
                    print(f"    [SKIP] {wt_name}: ACTIVE ({nm_size_mb:.0f}MB)")
                else:
                    print(f"    [CLEAN] {wt_name}: INACTIVE ({nm_size_mb:.0f}MB)")
                    import shutil
                    shutil.rmtree(nm_path, ignore_errors=True)
                    nm_cleaned += 1
                    nm_total_saved += nm_size_mb

        if nm_cleaned:
            print(f"\n  [OK] Cleaned node_modules from {nm_cleaned} inactive worktree(s)")
            print(f"  [OK] Saved ~{nm_total_saved:.0f}MB disk space")
        else:
            print(f"\n  [OK] No inactive worktrees with node_modules")

    if cleaned:
        save_ports(ports)
        print(f"\n  [DONE] Cleaned {cleaned} stale entries, saved ports.json")
    else:
        print(f"\n  [OK] No stale entries found")

    return cleaned


def cmd_health():
    """健康检查: worktree vs ports.json 一致性"""
    print("=" * 70)
    print("  WORKTREE HEALTH CHECK")
    print(f"  Generated: {_now_iso()}")
    print("=" * 70)

    issues = 0

    # 1. git worktree list vs ports.json
    rc, out, _ = _run_git(["worktree", "list", "--porcelain"])
    git_worktrees = set()
    if rc == 0:
        for line in out.split("\n"):
            if line.startswith("worktree "):
                git_worktrees.add(line[9:])

    ports = load_ports()
    ports_worktrees = set()
    for section in ("allocated", "persistent"):
        for _, info in ports.get(section, {}).items():
            wt = info.get("worktree")
            if wt:
                ports_worktrees.add(wt)

    # git 有但 ports.json 没有
    in_git_not_ports = git_worktrees - ports_worktrees
    if in_git_not_ports:
        # 排除主仓库
        main_repo = load_paths().get("main_repo", "")
        in_git_not_ports = {p for p in in_git_not_ports if p != main_repo}
    if in_git_not_ports:
        issues += len(in_git_not_ports)
        print(f"\n  [ISSUE] {len(in_git_not_ports)} worktree(s) in git but not in ports.json:")
        for path in in_git_not_ports:
            print(f"    - {path}")
            print(f"      FIX: _wt_lifecycle.py create {Path(path).name}")

    # ports.json 有但 git 没有
    in_ports_not_git = ports_worktrees - git_worktrees
    if in_ports_not_git:
        issues += len(in_ports_not_git)
        print(f"\n  [ISSUE] {len(in_ports_not_git)} worktree(s) in ports.json but not in git:")
        for path in in_ports_not_git:
            print(f"    - {path}")
            print(f"      FIX: _wt_lifecycle.py gc")

    # 2. 检查每个 worktree 的 dirty 状态
    print(f"\n  [DIRTY CHECK]")
    for wt_path in git_worktrees:
        if not Path(wt_path).exists():
            continue
        dirty = _check_dirty(wt_path)
        name = Path(wt_path).name
        if dirty > 50:
            issues += 1
            print(f"    [WARN] {name}: {dirty} dirty files (>50, may need cleanup)")
        elif dirty > 0:
            print(f"    [INFO] {name}: {dirty} dirty files")

    if issues == 0:
        print(f"\n  [OK] All worktrees healthy")
    else:
        print(f"\n  [TOTAL] {issues} issues found")

    return issues


def main():
    parser = argparse.ArgumentParser(description="Worktree lifecycle manager (v3.3)")
    parser.add_argument("command", choices=["list", "create", "remove", "gc", "health"])
    parser.add_argument("name", nargs="?", help="worktree name")
    parser.add_argument("--branch", help="branch name (for create)")
    parser.add_argument("--force", action="store_true", help="force remove even if dirty")
    parser.add_argument("--clean-node-modules", action="store_true",
                        help="gc: clean node_modules from inactive worktrees")
    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "create":
        if not args.name:
            print("Usage: _wt_lifecycle.py create <name> [--branch <branch>]")
            return 1
        return cmd_create(args.name, args.branch)
    elif args.command == "remove":
        if not args.name:
            print("Usage: _wt_lifecycle.py remove <name> [--force]")
            return 1
        return cmd_remove(args.name, args.force)
    elif args.command == "gc":
        return cmd_gc(clean_node_modules=args.clean_node_modules)
    elif args.command == "health":
        return cmd_health()


if __name__ == "__main__":
    sys.exit(main() or 0)
