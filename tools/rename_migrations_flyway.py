#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[P1.5] Migration 重命名工具: 5 个旧文件 → Flyway v<NNN>__<desc>.{py,sql}

执行内容:
  1. 读取 meta/migrations/_rename_mapping.yaml
  2. 对每个 mappings:
     - 复制文件为新名 (软操作, 不删除旧名; CI Lint 允许过渡期共存)
     - 把 schema_migrations.migration_name 从旧名 UPDATE 到新名
  3. 输出执行报告

设计原则 (来自 spec v1.1 §7.2.1):
  - 保留旧文件作 soft copy (过渡期, 旧 deployment 仍可跑)
  - 新部署只识别 v<NNN>__*.{py,sql}
  - 重命名在 schema_migrations 表里 UPDATE migration_name 即可, 不动 checksum 字段

运行:
  python tools/rename_migrations_flyway.py --db-path meta/architecture.db --dry-run
  python tools/rename_migrations_flyway.py --db-path meta/architecture.db         # 实际执行
"""
import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
WORKTREE = SCRIPT_DIR.parent
DEFAULT_META = WORKTREE / "meta"
DEFAULT_DB = DEFAULT_META / "architecture.db"
DEFAULT_MIG_DIR = DEFAULT_META / "migrations"

# 与 meta/migrations/_rename_mapping.yaml 保持硬编码同步 (避免 yaml 依赖)
# 注意: v001 (migrate_system_admin) 在 scripts/ 不在 migrations/, 不在这里处理
RENAMES = [
    {
        "old": "add_change_notification_tables.sql",
        "new": "v003__add_change_notification_tables.sql",
        "dir": "migrations",
        "sql_update": (
            "UPDATE schema_migrations SET migration_name = 'v003__add_change_notification_tables.sql' "
            "WHERE migration_name = 'add_change_notification_tables.sql'"
        ),
    },
    {
        "old": "enhance_audit_log_v2.py",
        "new": "v004__enhance_audit_log_v2.py",
        "dir": "migrations",
        "sql_update": (
            "UPDATE schema_migrations SET migration_name = 'v004__enhance_audit_log_v2.py' "
            "WHERE migration_name = 'enhance_audit_log_v2.py'"
        ),
    },
    {
        "old": "v007_50_add_audit_union_view.py",
        "new": "v005__add_audit_union_view.py",
        "dir": "migrations",
        "sql_update": (
            "UPDATE schema_migrations SET migration_name = 'v005__add_audit_union_view.py' "
            "WHERE migration_name = 'v007_50_add_audit_union_view.py'"
        ),
    },
    {
        "old": "v007_51_add_updated_at_materialized.py",
        "new": "v006__add_updated_at_materialized.py",
        "dir": "migrations",
        "sql_update": (
            "UPDATE schema_migrations SET migration_name = 'v006__add_updated_at_materialized.py' "
            "WHERE migration_name = 'v007_51_add_updated_at_materialized.py'"
        ),
    },
]


def do_rename_files(mig_dir: Path, dry_run: bool):
    """复制文件: old_name -> v<NNN>__new_name (软复制, 不删除旧名)"""
    actions = []
    for r in RENAMES:
        src = mig_dir / r["old"]
        dst = mig_dir / r["new"]
        if not src.exists():
            actions.append(("SKIP", str(src), "源文件不存在"))
            continue
        if dst.exists():
            actions.append(("SKIP", str(dst), "目标文件已存在"))
            continue
        if dry_run:
            actions.append(("DRYRUN_COPY", str(src), str(dst)))
        else:
            shutil.copy2(str(src), str(dst))
            actions.append(("COPIED", str(src), str(dst)))
    return actions


def do_update_db(db_path: Path, dry_run: bool):
    """更新 schema_migrations 表: old_name -> new_name"""
    actions = []
    if not db_path.exists():
        actions.append(("SKIP_DB", str(db_path), "DB 不存在, 跳过"))
        return actions
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        for r in RENAMES:
            cur.execute(
                "SELECT migration_name, checksum FROM schema_migrations WHERE migration_name = ?",
                (r["old"],),
            )
            rows = cur.fetchall()
            if not rows:
                actions.append(("SKIP", r["old"], "DB 无此记录 (可能已重命名)"))
                continue
            if dry_run:
                actions.append(("DRYRUN_UPDATE", r["old"], r["new"]))
            else:
                cur.execute(r["sql_update"])
                affected = cur.rowcount
                conn.commit()
                actions.append(("UPDATED", r["old"], f"{r['new']} (rows={affected})"))
        conn.close()
    except Exception as e:
        actions.append(("ERROR_DB", str(db_path), str(e)))
    return actions


def main():
    parser = argparse.ArgumentParser(description="[P1.5] 重命名 migration 文件为 Flyway 格式")
    parser.add_argument("--db-path", default=str(DEFAULT_DB),
                        help=f"SQLite DB 路径 (默认 {DEFAULT_DB})")
    parser.add_argument("--migrations-dir", default=str(DEFAULT_MIG_DIR),
                        help=f"Migrations 目录 (默认 {DEFAULT_MIG_DIR})")
    parser.add_argument("--dry-run", action="store_true",
                        help="只预览, 不实际改文件/DB")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    mig_dir = Path(args.migrations_dir)

    print("=== Migration Rename (Flyway 格式) ===")
    print(f"Migrations dir: {mig_dir}")
    print(f"DB path: {db_path}")
    print(f"Dry run: {args.dry_run}")
    print()

    # 1. 文件复制
    print("--- File operations ---")
    file_actions = do_rename_files(mig_dir, args.dry_run)
    for action, src, dst in file_actions:
        print(f"  [{action}] {src} -> {dst}")
    print()

    # 2. DB 更新
    print("--- DB updates ---")
    db_actions = do_update_db(db_path, args.dry_run)
    for action, src, dst in db_actions:
        print(f"  [{action}] {src} -> {dst}")
    print()

    # 3. 汇总
    total = len(file_actions) + len(db_actions)
    errors = sum(1 for a in file_actions + db_actions if a[0].startswith("ERROR"))
    print(f"Total: {total} actions, {errors} errors")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
