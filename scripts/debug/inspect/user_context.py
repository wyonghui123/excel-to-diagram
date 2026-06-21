#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户调试上下文查询工具 - 调试基础设施 P0 (v2026.06.21)

背景：2026-06-21 复盘两次调试事故（SM/BO 误拦 + 字段映射错误），
     Agent 反复查询 user_roles / role_dimension_scopes / data_permissions。
     每次调试都"重新勘察"用户上下文，浪费大量时间。

核心功能：
- 一键输出用户的完整调试上下文
- 避免反复 SQL 查询
- 支持快照保存（用于跨 session 复用）

用法：
    # 一键输出用户上下文
    python scripts/debug/inspect/user_context.py TEST333

    # 保存快照到 .trae/debug/snapshots/
    python scripts/debug/inspect/user_context.py TEST333 --save

    # 输出 JSON（用于程序处理）
    python scripts/debug/inspect/user_context.py TEST333 --json

    # 显示历史快照列表
    python scripts/debug/inspect/user_context.py --list-snapshots

    # 对比两个快照
    python scripts/debug/inspect/user_context.py --diff snapshot1.json snapshot2.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SNAPSHOTS_DIR = PROJECT_ROOT / ".trae" / "debug" / "snapshots"


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}", file=sys.stderr)


def ensure_snapshots_dir():
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def get_user_id(username: str) -> Optional[int]:
    """查询用户的 user_id"""
    sql = f"SELECT id FROM users WHERE username = '{username}';"
    result = run_sql(sql)
    if result:
        try:
            return int(result[0].strip())
        except (ValueError, IndexError):
            return None
    return None


def get_user_groups(user_id: int) -> List[Dict]:
    """查询用户所属组"""
    sql = f"""SELECT g.id, g.name FROM groups g
              JOIN user_groups ug ON g.id = ug.group_id
              WHERE ug.user_id = {user_id};"""
    results = run_sql(sql)
    return [{"group_id": int(r.split('|')[0]), "name": r.split('|')[1]}
            for r in results if '|' in r]


def get_user_roles(user_id: int) -> List[Dict]:
    """查询用户关联的角色"""
    sql = f"""SELECT r.id, r.name FROM roles r
              JOIN user_roles ur ON r.id = ur.role_id
              WHERE ur.user_id = {user_id};"""
    results = run_sql(sql)
    roles = []
    for r in results:
        if '|' in r:
            rid, name = r.split('|', 1)
            roles.append({"role_id": int(rid), "name": name})
    return roles


def get_role_scopes(role_id: int) -> List[Dict]:
    """查询角色的 dim scope 配置"""
    sql = f"""SELECT dimension_code, dimension_values, inherit_children, scope_mode, bo_id
              FROM role_dimension_scopes
              WHERE role_id = {role_id};"""
    results = run_sql(sql)
    scopes = []
    for r in results:
        if '|' in r:
            parts = r.split('|')
            if len(parts) >= 5:
                scopes.append({
                    "dimension_code": parts[0],
                    "dimension_values": parts[1],
                    "inherit_children": parts[2],
                    "scope_mode": parts[3],
                    "bo_id": parts[4] if parts[4] else None,
                })
    return scopes


def get_data_permissions(role_id: int) -> Dict:
    """查询角色对应的数据权限引擎输出"""
    # 这是 mock，实际查询需要调用 DimensionScopeEngine
    # 这里只做基础信息收集
    return {
        "note": "Use meta/services/dimension_scope_engine.py for full output",
    }


def load_dotenv(dotenv_path: Optional[Path] = None) -> bool:
    """自动加载 .env 文件到 os.environ"""
    if dotenv_path is None:
        dotenv_path = PROJECT_ROOT / ".env"

    if not dotenv_path.exists():
        return False

    try:
        with open(dotenv_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        return True
    except (OSError, UnicodeDecodeError):
        return False


def run_sql(sql: str, timeout: int = 30) -> List[str]:
    """执行 SQL 查询（通过 psql 或 sqlite3）

    Returns:
        List of pipe-separated rows
    """
    # V3.3 修复：自动加载 .env
    if not os.environ.get("DATABASE_URL"):
        if load_dotenv():
            _log("已加载 .env 文件", "INFO")

    # 检测数据库类型
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgres"):
        # PostgreSQL
        try:
            result = subprocess.run(
                ["psql", "-t", "-A", "-F", "|", "-c", sql, db_url],
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.splitlines() if line.strip()]
            _log(f"psql 失败: {result.stderr}", "FAIL")
            return []
        except FileNotFoundError:
            _log("psql 未安装，无法查询 PostgreSQL", "FAIL")
            return []
    else:
        # 假设 MySQL 或 SQLite - 尝试常见工具
        # 实际实现应该根据项目配置
        _log(f"数据库类型未识别 (DATABASE_URL={db_url!r})，需要配置", "WARN")
        return []


def collect_user_context(username: str) -> Dict:
    """收集用户的完整调试上下文"""
    _log(f"查询用户 {username} 的上下文...", "INFO")

    user_id = get_user_id(username)
    if not user_id:
        return {"error": f"用户不存在: {username}"}

    context = {
        "username": username,
        "user_id": user_id,
        "groups": get_user_groups(user_id),
        "roles": [],
        "scopes_by_role": {},
        "data_permissions": {},
        "collected_at": datetime.now().isoformat(),
    }

    roles = get_user_roles(user_id)
    context["roles"] = roles

    for role in roles:
        rid = role["role_id"]
        context["scopes_by_role"][rid] = get_role_scopes(rid)
        context["data_permissions"][rid] = get_data_permissions(rid)

    return context


def print_context(context: Dict):
    """格式化输出用户上下文"""
    if "error" in context:
        _log(context["error"], "FAIL")
        return

    print("=" * 70)
    print(f"用户调试上下文: {context['username']}")
    print("=" * 70)
    print()
    print(f"## 身份")
    print(f"  user_id: {context['user_id']}")
    print()
    print(f"## 所属组")
    if context["groups"]:
        for g in context["groups"]:
            print(f"  - id={g['group_id']} name={g['name']}")
    else:
        print("  (none)")
    print()
    print(f"## 关联角色")
    if context["roles"]:
        for r in context["roles"]:
            print(f"  - role_id={r['role_id']} name={r['name']}")
    else:
        print("  (none)")
    print()
    print(f"## Dim Scope 配置（按角色）")
    for rid, scopes in context["scopes_by_role"].items():
        role_name = next((r["name"] for r in context["roles"] if r["role_id"] == rid), "?")
        print(f"  role_id={rid} ({role_name}):")
        if scopes:
            for s in scopes:
                print(f"    - {s['dimension_code']}={s['dimension_values']} "
                      f"inherit={s['inherit_children']} mode={s['scope_mode']}")
        else:
            print("    (no scope config)")
    print()
    print(f"## 数据权限")
    for rid, dp in context["data_permissions"].items():
        print(f"  role_id={rid}: {dp}")
    print()
    print(f"## 收集时间")
    print(f"  {context['collected_at']}")
    print("=" * 70)


def save_snapshot(context: Dict) -> Path:
    """保存用户上下文快照"""
    ensure_snapshots_dir()
    username = context.get("username", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_path = SNAPSHOTS_DIR / f"{username}-{timestamp}.json"

    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    _log(f"快照保存: {snapshot_path}", "OK")
    return snapshot_path


def list_snapshots():
    """列出所有快照"""
    ensure_snapshots_dir()
    snapshots = sorted(SNAPSHOTS_DIR.glob("*.json"), reverse=True)
    if not snapshots:
        print("没有快照")
        return
    print("=" * 70)
    print(f"用户上下文快照（{len(snapshots)} 个）")
    print("=" * 70)
    for s in snapshots:
        stat = s.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {s.name}  ({size} bytes, {mtime})")


def diff_snapshots(snap1_path: Path, snap2_path: Path):
    """对比两个快照的差异"""
    with open(snap1_path, encoding="utf-8") as f:
        snap1 = json.load(f)
    with open(snap2_path, encoding="utf-8") as f:
        snap2 = json.load(f)

    print("=" * 70)
    print(f"对比快照")
    print(f"  旧: {snap1_path.name}")
    print(f"  新: {snap2_path.name}")
    print("=" * 70)
    print()

    # 角色对比
    roles1 = {r["role_id"] for r in snap1.get("roles", [])}
    roles2 = {r["role_id"] for r in snap2.get("roles", [])}

    if roles1 != roles2:
        print(f"## 角色变化")
        print(f"  新增: {roles2 - roles1}")
        print(f"  删除: {roles1 - roles2}")
        print()

    # Scope 对比
    for rid in roles1 | roles2:
        s1 = snap1.get("scopes_by_role", {}).get(str(rid), [])
        s2 = snap2.get("scopes_by_role", {}).get(str(rid), [])
        if s1 != s2:
            print(f"## Role {rid} Scope 变化")
            print(f"  旧: {s1}")
            print(f"  新: {s2}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description="用户调试上下文查询工具 - V2.1 调试基础设施 P0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("username", nargs="?", help="用户名")
    parser.add_argument("--save", action="store_true",
                        help="保存快照到 .trae/debug/snapshots/")
    parser.add_argument("--json", action="store_true",
                        help="输出 JSON 格式")
    parser.add_argument("--list-snapshots", action="store_true",
                        help="列出所有快照")
    parser.add_argument("--diff", nargs=2, metavar=("SNAP1", "SNAP2"),
                        help="对比两个快照")

    args = parser.parse_args()

    if args.list_snapshots:
        list_snapshots()
        return 0

    if args.diff:
        snap1 = SNAPSHOTS_DIR / args.diff[0]
        snap2 = SNAPSHOTS_DIR / args.diff[1]
        if not snap1.exists():
            _log(f"快照不存在: {snap1}", "FAIL")
            return 1
        if not snap2.exists():
            _log(f"快照不存在: {snap2}", "FAIL")
            return 1
        diff_snapshots(snap1, snap2)
        return 0

    if not args.username:
        parser.print_help()
        return 1

    context = collect_user_context(args.username)

    if args.json:
        print(json.dumps(context, ensure_ascii=False, indent=2))
    else:
        print_context(context)

    if args.save:
        save_snapshot(context)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)