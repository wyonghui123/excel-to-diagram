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


# 已在 prod 执行过但未登记的 migration 清单 (硬编码, 一次性)
# 注意: canonical_name 用当前实际文件名 (P0 阶段未重命名)
# P1 重命名后会更新 schema_migrations 表
LEGACY_MIGRATIONS = [
    # (canonical_name, rel_path_from_meta_root, executed_by, notes)
    # 1. migrate_system_admin: 不在 migrations 目录, runner 不会扫描, 但也登记以防将来移动
    ("migrate_system_admin.py", "scripts/migrate_system_admin.py",
     "server.py L482", "无参签名 run_migration(), 已在 prod 执行"),

    # 2. add_change_notification_tables.sql: 已通过 runner 登记, 跳过
    ("add_change_notification_tables.sql", "migrations/add_change_notification_tables.sql",
     "server.py L492 via runner", "已通过 runner 登记, 跳过"),

    # 3. enhance_audit_log_v2.py: 签名 enhance_audit_log(db_path), 不兼容新规范
    ("enhance_audit_log_v2.py", "migrations/enhance_audit_log_v2.py",
     "server.py L497", "enhance_audit_log(db_path) 签名"),

    # 4. v007_50_add_audit_union_view.py: 签名 migrate(db_path, skip_backup), 兼容新规范
    ("v007_50_add_audit_union_view.py", "migrations/v007_50_add_audit_union_view.py",
     "server.py L503", "migrate(db_path, skip_backup=True)"),

    # 5. v007_51_add_updated_at_materialized.py: 签名 migrate(db_path, skip_backup), 兼容新规范
    ("v007_51_add_updated_at_materialized.py", "migrations/v007_51_add_updated_at_materialized.py",
     "server.py L511", "migrate(db_path, skip_backup=True)"),
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

    # 2. 查询已登记的
    cur.execute("SELECT migration_name FROM schema_migrations")
    already_registered = {row[0] for row in cur.fetchall()}
    print(f"[INFO] Already registered: {len(already_registered)} migrations")
    for name in sorted(already_registered):
        print(f"  - {name}")
    print()

    # 3. 补登记
    to_register = []
    for canonical_name, rel_path, executed_by, notes in LEGACY_MIGRATIONS:
        if canonical_name in already_registered:
            print(f"[SKIP] {canonical_name} already registered ({notes})")
            continue

        # 尝试找到源文件
        file_path = meta_root / "meta" / rel_path
        if not file_path.exists():
            # 尝试相对于 db_path 的路径
            file_path = db_path.parent.parent / rel_path
        if not file_path.exists():
            # 尝试相对于 db_path.parent/migrations
            if rel_path.startswith("migrations/"):
                file_path = db_path.parent / rel_path
        if not file_path.exists():
            # 尝试相对于 db_path.parent/scripts
            if rel_path.startswith("scripts/"):
                file_path = db_path.parent / rel_path

        if not file_path.exists():
            print(f"[WARN] {canonical_name}: source file not found at {rel_path}, "
                  f"registering with NULL checksum")
            to_register.append((canonical_name, None, executed_by, notes))
            continue

        checksum = compute_checksum(file_path)
        to_register.append((canonical_name, checksum, executed_by, notes))
        print(f"[TODO] {canonical_name} -> checksum={checksum[:16]}... ({notes})")

    print()

    if not to_register:
        print("[DONE] Nothing to register, all migrations already recorded")
        conn.close()
        return 0

    if args.dry_run:
        print(f"[DRY-RUN] Would register {len(to_register)} migrations:")
        for canonical_name, checksum, executed_by, notes in to_register:
            cs_display = checksum[:16] + "..." if checksum else "NULL"
            print(f"  - {canonical_name} (checksum={cs_display}, executed_by={executed_by})")
        conn.close()
        return 0

    # 4. 执行登记
    print(f"[EXEC] Registering {len(to_register)} migrations...")
    for canonical_name, checksum, executed_by, notes in to_register:
        cur.execute(
            "INSERT INTO schema_migrations (migration_name, checksum) VALUES (?, ?)",
            (canonical_name, checksum)
        )
        cs_display = checksum[:16] + "..." if checksum else "NULL"
        print(f"  [OK] Registered {canonical_name} (checksum={cs_display}, executed_by={executed_by})")

    conn.commit()

    # 5. 验证
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
