#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[PO.5] 一次性脚本: 把已执行但未登记的 migration 补登记到 schema_migrations 表.

背景:
  现有 5 个 migration 已在 prod 执行过, 但只有 1 个 (add_change_notification_tables.sql)
  通过 MigrationRunner 写了 schema_migrations 表. 其余 4 个是 server.py 硬编码 import 调用的,
  没有版本追踪记录.

  如果 P0 激活 run_all_migrations 后不先跑此脚本, runner 会把这 4 个已执行的 migration
  当作 pending 重新执行, 导致:
    - 浪费时间重新跑 Backfill (v007_51 在 265K 行 audit_logs 上跑 MAX+GROUP BY)
    - 重新备份 DB (每次 ~500MB)
    - 误导监控 (日志显示 "executed 4 migrations" 但实际没做任何变更)

使用场景:
  - P0 激活 run_all_migrations 之前
  - 在每个环境 (staging/prod) 各跑一次

执行方式 (在目标环境):
  cd $DEPLOY_DIR/current
  python tools/backfill_schema_migrations.py --db-path meta/architecture.db --dry-run  # 预览
  python tools/backfill_schema_migrations.py --db-path meta/architecture.db            # 执行

注意:
  - canonical_name 用当前实际文件名 (P0 阶段未重命名)
  - P1 重命名时需要同步更新 schema_migrations 表的 migration_name 字段
  - 脚本幂等: 重复跑不报错, 已登记的跳过

版本: v1.0
日期: 2026-07-15
"""

import sqlite3
import hashlib
import argparse
import os
from pathlib import Path
from datetime import datetime


# 已在 prod/staging 执行过但未登记 (或 checksum=NULL) 的 migration 清单
# 注意: canonical_name 用当前实际文件名 (P0 阶段未重命名)
# P1 重命名后会更新 schema_migrations 表
#
# 分两批:
#   批次 A: V007.46 旧代码硬 import 的 scripts/ 迁移 (staging 有 10 条旧记录)
#   批次 B: V007.50+ server.py 硬 import 的 migrations/ 迁移 (prod/staging 都需要)
LEGACY_MIGRATIONS = [
    # === 批次 A: V007.46 scripts/ 迁移 (staging 2026-07-05 已执行) ===
    # (canonical_name, rel_path_from_meta_root, executed_by, notes)

    # A1. add_change_notification_tables.sql: runner 登记但 checksum=NULL
    ("add_change_notification_tables.sql", "migrations/add_change_notification_tables.sql",
     "MigrationRunner", "V007.46 runner 登记, checksum 需补填"),

    # A2. migrate_bo_categories: 无参签名 run_migration()
    ("migrate_bo_categories.py", "scripts/migrate_bo_categories.py",
     "server.py import", "run_migration() 签名, scripts/ 下"),

    # A3. migrate_enum_mutability: 无参签名
    ("migrate_enum_mutability.py", "scripts/migrate_enum_mutability.py",
     "server.py import", "scripts/ 下"),

    # A4. migrate_enums: 无参签名
    ("migrate_enums.py", "scripts/migrate_enums.py",
     "server.py import", "scripts/ 下"),

    # A5. migrate_permission_unified_semantic: 无参签名
    #     (staging 记录被截断为 migrate_permission_unified_semanti)
    ("migrate_permission_unified_semantic.py", "scripts/migrate_permission_unified_semantic.py",
     "server.py import", "VARCHAR(255) 截断, scripts/ 下"),

    # A6. migrate_system_admin: 无参签名 run_migration()
    ("migrate_system_admin.py", "scripts/migrate_system_admin.py",
     "server.py import", "run_migration() 签名, scripts/ 下"),

    # A7. migrate_v1_1_owner_refactor: 无参签名
    ("migrate_v1_1_owner_refactor.py", "scripts/migrate_v1_1_owner_refactor.py",
     "server.py import", "scripts/ 下"),

    # A8. migrate_v1_cleanup: 无参签名
    ("migrate_v1_cleanup.py", "scripts/migrate_v1_cleanup.py",
     "server.py import", "scripts/ 下"),

    # A9. migrate_v318_audit.py: 签名 migrate(db_path)
    #     staging 有两条: id=9 "migrate_v318_audit.py" + id=10 "migrate_v318_audit"
    #     P0 runner 统一用带 .py 的名字, 无 .py 的是旧记录
    ("migrate_v318_audit.py", "scripts/migrate_v318_audit.py",
     "server.py import", "migrate(db_path) 签名, scripts/ 下"),

    # === 批次 B: V007.50+ migrations/ 迁移 (prod 需补登记) ===

    # B1. enhance_audit_log_v2.py: 签名 enhance_audit_log(db_path)
    ("enhance_audit_log_v2.py", "migrations/enhance_audit_log_v2.py",
     "server.py import", "enhance_audit_log(db_path) 签名"),

    # B2. v007_50_add_audit_union_view.py: 签名 migrate(db_path, skip_backup)
    ("v007_50_add_audit_union_view.py", "migrations/v007_50_add_audit_union_view.py",
     "server.py import", "migrate(db_path, skip_backup=True)"),

    # B3. v007_51_add_updated_at_materialized.py: 签名 migrate(db_path, skip_backup)
    ("v007_51_add_updated_at_materialized.py", "migrations/v007_51_add_updated_at_materialized.py",
     "server.py import", "migrate(db_path, skip_backup=True)"),
]


def compute_checksum(file_path: Path) -> str:
    """计算文件的 SHA256 checksum

    与 MigrationRunner._compute_checksum 算法保持一致.
    """
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()  # 64 字符十六进制


def _find_file(meta_root: Path, db_path: Path, rel_path: str) -> Path:
    """多路径尝试查找 migration 源文件"""
    candidates = [
        meta_root / "meta" / rel_path,
        db_path.parent.parent / rel_path,
    ]
    if rel_path.startswith("migrations/"):
        candidates.append(db_path.parent / rel_path)
    if rel_path.startswith("scripts/"):
        candidates.append(db_path.parent / rel_path)
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # 返回默认路径 (可能不存在)


def main():
    parser = argparse.ArgumentParser(
        description='[P0.5] 补登记已执行但未记录的 migration 到 schema_migrations 表'
    )
    parser.add_argument('--db-path', required=True,
                        help='SQLite 数据库路径 (如 meta/architecture.db)')
    parser.add_argument('--dry-run', action='store_true',
                        help='只预览, 不实际写入')
    parser.add_argument('--meta-root', default='.',
                        help='meta/ 目录的父目录 (默认当前目录)')
    args = parser.parse_args()

    db_path = Path(args.db_path)
    meta_root = Path(args.meta_root)

    if not db_path.exists():
        print(f"FATAL: DB not found: {db_path}")
        return 1

    print(f"[INFO] DB path: {db_path}")
    print(f"[INFO] Meta root: {meta_root}")
    print(f"[INFO] Dry run: {args.dry_run}")
    print()

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 1. 确保 schema_migrations 表存在
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name VARCHAR(255) NOT NULL UNIQUE,
            executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checksum VARCHAR(64)
        )
    """)
    conn.commit()

    # 1.5 修复旧记录: 截断名字 / 无后缀重复 / 补填 checksum
    # staging 有 VARCHAR(255) 截断 (migrate_permission_unified_semanti → migrate_permission_unified_semantic.py)
    # 和 migrate_v318_audit (无 .py) 与 migrate_v318_audit.py 重复
    NAME_FIXES = {
        "migrate_permission_unified_semanti": "migrate_permission_unified_semantic.py",
        "migrate_v318_audit": "migrate_v318_audit.py",  # 无 .py → 有 .py (合并重复)
        # 旧代码可能不带 .py 后缀登记
        "migrate_system_admin": "migrate_system_admin.py",
        "migrate_bo_categories": "migrate_bo_categories.py",
        "migrate_enum_mutability": "migrate_enum_mutability.py",
        "migrate_enums": "migrate_enums.py",
        "migrate_v1_1_owner_refactor": "migrate_v1_1_owner_refactor.py",
        "migrate_v1_cleanup": "migrate_v1_cleanup.py",
    }

    fixed_count = 0
    for old_name, new_name in NAME_FIXES.items():
        cur.execute("SELECT id, checksum FROM schema_migrations WHERE migration_name = ?", (old_name,))
        row = cur.fetchone()
        if row:
            old_id, old_checksum = row
            # 检查新名字是否已存在 (重复合并)
            cur.execute("SELECT id FROM schema_migrations WHERE migration_name = ?", (new_name,))
            existing = cur.fetchone()
            if existing:
                # 删除旧记录, 保留新记录
                print(f"[FIX] 删除重复记录 id={old_id} '{old_name}', 保留 id={existing[0]} '{new_name}'")
                cur.execute("DELETE FROM schema_migrations WHERE id = ?", (old_id,))
            else:
                # 重命名
                print(f"[FIX] 重命名 id={old_id}: '{old_name}' → '{new_name}'")
                cur.execute("UPDATE schema_migrations SET migration_name = ? WHERE id = ?", (new_name, old_id))
            fixed_count += 1
    if fixed_count > 0:
        conn.commit()
        print(f"[FIX] 修复了 {fixed_count} 条旧记录")
    else:
        print("[INFO] 无需修复旧记录名字")

    # 2. 查询已登记的
    cur.execute("SELECT migration_name FROM schema_migrations")
    already_registered = {row[0] for row in cur.fetchall()}
    print(f"[INFO] Already registered: {len(already_registered)} migrations")
    for name in sorted(already_registered):
        print(f"  - {name}")
    print()

    # 3. 补登记 + 补填 checksum
    to_register = []
    to_update_checksum = []
    for canonical_name, rel_path, executed_by, notes in LEGACY_MIGRATIONS:
        if canonical_name in already_registered:
            # 检查 checksum 是否需要补填
            cur.execute("SELECT checksum FROM schema_migrations WHERE migration_name = ?", (canonical_name,))
            row = cur.fetchone()
            if row and row[0] is None:
                # checksum=NULL, 需要补填
                file_path = _find_file(meta_root, db_path, rel_path)
                if file_path and file_path.exists():
                    checksum = compute_checksum(file_path)
                    to_update_checksum.append((canonical_name, checksum, executed_by, notes))
                    print(f"[UPDATE] {canonical_name}: checksum=NULL → {checksum[:16]}... ({notes})")
                else:
                    print(f"[WARN] {canonical_name}: checksum=NULL 但源文件未找到, 无法补填")
            else:
                print(f"[SKIP] {canonical_name} already registered with checksum ({notes})")
            continue

        # 尝试找到源文件
        file_path = _find_file(meta_root, db_path, rel_path)

        if not file_path or not file_path.exists():
            print(f"[WARN] {canonical_name}: source file not found at {rel_path}, "
                  f"registering with NULL checksum")
            to_register.append((canonical_name, None, executed_by, notes))
            continue

        checksum = compute_checksum(file_path)
        to_register.append((canonical_name, checksum, executed_by, notes))
        print(f"[TODO] {canonical_name} -> checksum={checksum[:16]}... ({notes})")

    print()

    # 4. dry-run 预览
    total_actions = len(to_register) + len(to_update_checksum)
    if total_actions == 0:
        print("[DONE] Nothing to do, all migrations recorded with checksum")
        conn.close()
        return 0

    if args.dry_run:
        if to_register:
            print(f"[DRY-RUN] Would register {len(to_register)} new migrations:")
            for canonical_name, checksum, executed_by, notes in to_register:
                cs_display = checksum[:16] + "..." if checksum else "NULL"
                print(f"  - {canonical_name} (checksum={cs_display}, executed_by={executed_by})")
        if to_update_checksum:
            print(f"[DRY-RUN] Would update checksum for {len(to_update_checksum)} existing migrations:")
            for canonical_name, checksum, executed_by, notes in to_update_checksum:
                print(f"  - {canonical_name} → checksum={checksum[:16]}...")
        conn.close()
        return 0

    # 5. 执行: 新增记录
    if to_register:
        print(f"[EXEC] Registering {len(to_register)} new migrations...")
        for canonical_name, checksum, executed_by, notes in to_register:
            cur.execute(
                "INSERT INTO schema_migrations (migration_name, checksum) VALUES (?, ?)",
                (canonical_name, checksum)
            )
            cs_display = checksum[:16] + "..." if checksum else "NULL"
            print(f"  [OK] Registered {canonical_name} (checksum={cs_display}, executed_by={executed_by})")

    # 6. 执行: 补填 checksum
    if to_update_checksum:
        print(f"[EXEC] Updating checksum for {len(to_update_checksum)} existing migrations...")
        for canonical_name, checksum, executed_by, notes in to_update_checksum:
            cur.execute(
                "UPDATE schema_migrations SET checksum = ? WHERE migration_name = ?",
                (checksum, canonical_name)
            )
            print(f"  [OK] Updated {canonical_name} → checksum={checksum[:16]}...")

    conn.commit()

    # 7. 验证
    cur.execute("SELECT migration_name, substr(checksum, 1, 16) as checksum_short "
                "FROM schema_migrations ORDER BY id")
    rows = cur.fetchall()
    print()
    print(f"[DONE] schema_migrations now has {len(rows)} records:")
    for name, cs in rows:
        cs_display = cs + "..." if cs else "NULL"
        print(f"  - {name} (checksum={cs_display})")

    conn.close()
    return 0


if __name__ == '__main__':
    exit(main())
