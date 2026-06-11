# -*- coding: utf-8 -*-
"""
V1 Cleanup Migration: 删除 `role.is_super_admin` + `role.priority` 字段

设计依据: spec-auth-object-category-v2-2026-06-10.md §4 FR-V1-001 + FR-V1-002 + FR-V1-004

执行步骤:
  1. 备份 (创建 roles_v1_backup 临时表)
  2. 数据迁移: 确保原 is_super_admin=true 角色的 user 拥有 '*' 权限
     (实际 schema 通过 group_roles + role_permissions 实现, 已有 admin 角色绑定 '*' permission)
  3. 删除字段 (SQLite 3.35+ 支持 DROP COLUMN)
  4. 验证

回滚 (downgrade):
  1. 恢复 2 列
  2. 从 backup 表恢复原 is_super_admin / priority 值

用法:
  # Dry-run 模式 (只 SELECT, 不修改)
  python meta/scripts/migrate_v1_cleanup.py --dry-run

  # 真运行
  python meta/scripts/migrate_v1_cleanup.py

  # 回滚
  python meta/scripts/migrate_v1_cleanup.py --downgrade
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, 'meta', 'architecture.db')

# 备份表名 (V1 临时备份, 部署后可手工 DROP)
BACKUP_TABLE = 'roles_v1_backup'

# 标记: 数据迁移来源 (用于 audit log 追溯)
MIGRATION_TAG = 'V1_MIGRATION_2026_06_10'


def get_conn():
    """获取 SQLite 连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def column_exists(conn, table, column):
    """检查列是否存在"""
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = [row['name'] for row in cur.fetchall()]
    return column in cols


def table_exists(conn, table):
    """检查表是否存在"""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        [table]
    )
    return cur.fetchone() is not None


def pre_check(conn, dry_run=False):
    """
    迁移前检查: 列出将被删除的字段及关联数据
    """
    print("=" * 60)
    print(f"[{'DRY-RUN' if dry_run else 'EXECUTE'}] V1 Cleanup Migration")
    print(f"  DB: {DB_PATH}")
    print(f"  Tag: {MIGRATION_TAG}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 60)

    has_super_admin = column_exists(conn, 'roles', 'is_super_admin')
    has_priority = column_exists(conn, 'roles', 'priority')

    print("\n[Pre-check] Roles 表字段状态:")
    print(f"  is_super_admin 列: {'存在 (将被删除)' if has_super_admin else '不存在 (无需处理)'}")
    print(f"  priority 列:      {'存在 (将被删除)' if has_priority else '不存在 (无需处理)'}")

    if not has_super_admin and not has_priority:
        print("\n[INFO] 两个字段都不存在, 迁移已完成或从未存在. 无需操作.")
        return False

    # 统计将被影响的数据
    if has_super_admin:
        cur = conn.execute("SELECT COUNT(*) AS c FROM roles WHERE is_super_admin = 1")
        super_admin_count = cur.fetchone()['c']
        print(f"\n[Pre-check] is_super_admin=1 的角色数: {super_admin_count}")

        if super_admin_count > 0:
            cur = conn.execute(
                "SELECT id, code, name FROM roles WHERE is_super_admin = 1"
            )
            print("  这些角色将被备份:")
            for row in cur.fetchall():
                print(f"    - id={row['id']}, code={row['code']}, name={row['name']}")

    if has_priority:
        cur = conn.execute("SELECT COUNT(*) AS c FROM roles WHERE priority IS NOT NULL AND priority != 0")
        priority_nonzero = cur.fetchone()['c']
        print(f"\n[Pre-check] priority 非 0 的角色数: {priority_nonzero}")

    # 验证 admin user 是否已通过角色获得 '*' 权限
    cur = conn.execute("""
        SELECT COUNT(DISTINCT u.id) AS c
        FROM users u
        JOIN user_group_members ugm ON u.id = ugm.user_id
        JOIN group_roles gr ON ugm.group_id = gr.group_id
        JOIN role_permissions rp ON gr.role_id = rp.role_id
        JOIN permissions p ON rp.permission_id = p.id
        WHERE p.code = '*'
    """)
    admin_via_perm = cur.fetchone()['c']
    print(f"\n[Pre-check] 通过角色获得 '*' 权限的 user 数: {admin_via_perm}")
    if admin_via_perm == 0:
        print("  [WARN] 没有 user 通过角色获得 '*' 权限! migration 后 admin 将无法登录.")

    return True


def backup_data(conn):
    """
    Step 1: 备份 (仅保留有 is_super_admin=1 或 priority 非 0 的行)
    """
    print("\n[Step 1] 备份数据到 roles_v1_backup ...")

    if table_exists(conn, BACKUP_TABLE):
        print(f"  备份表 {BACKUP_TABLE} 已存在, 跳过创建")
        return

    # 创建备份表 (结构同 roles)
    conn.execute(f"""
        CREATE TABLE {BACKUP_TABLE} AS
        SELECT * FROM roles
        WHERE 1=0
    """)

    # 插入被删除字段值非默认的行
    has_super_admin = column_exists(conn, 'roles', 'is_super_admin')
    has_priority = column_exists(conn, 'roles', 'priority')

    conditions = []
    if has_super_admin:
        conditions.append("is_super_admin = 1")
    if has_priority:
        conditions.append("priority IS NOT NULL AND priority != 0")

    if conditions:
        where_clause = " OR ".join(conditions)
        conn.execute(f"""
            INSERT INTO {BACKUP_TABLE}
            SELECT * FROM roles WHERE {where_clause}
        """)
        cur = conn.execute(f"SELECT COUNT(*) AS c FROM {BACKUP_TABLE}")
        print(f"  备份完成: {cur.fetchone()['c']} 行")
    else:
        conn.execute(f"DROP TABLE {BACKUP_TABLE}")
        print(f"  字段都不存在, 跳过备份表创建")


def migrate_admin_permissions(conn, dry_run=False):
    """
    Step 2: 数据迁移 - 确保原 is_super_admin=true 角色的 user 通过 * 权限识别为 admin

    注意: 当前 schema 没有 user_permissions 表, admin 识别通过
    group_roles → role_permissions → permissions( code='*' ) 实现.
    seed_role_permissions 已确保 admin 角色绑定 '*' permission.
    此步骤主要是 verification, 必要时补登 '*' 权限给 admin 角色.
    """
    print("\n[Step 2] 数据迁移: 确保 admin 角色拥有 '*' 权限 ...")

    if not column_exists(conn, 'roles', 'is_super_admin'):
        print("  is_super_admin 列已不存在, 跳过迁移")
        return

    cur = conn.execute("SELECT id, code FROM roles WHERE is_super_admin = 1")
    super_admin_roles = cur.fetchall()

    if not super_admin_roles:
        print("  没有 is_super_admin=true 的角色, 跳过")
        return

    # 检查 '*' permission 是否存在
    cur = conn.execute("SELECT id FROM permissions WHERE code = '*'")
    row = cur.fetchone()
    if not row:
        print("  [ERROR] permissions 表中没有 code='*' 的权限!")
        print("  请先运行 init_auth.py 或 permission_sync_service 初始化权限表")
        sys.exit(1)
    wildcard_perm_id = row['id']

    for role in super_admin_roles:
        role_id = role['id']
        role_code = role['code']

        # 检查该角色是否已有 '*' 权限
        cur = conn.execute(
            "SELECT 1 FROM role_permissions WHERE role_id = ? AND permission_id = ?",
            [role_id, wildcard_perm_id]
        )
        if cur.fetchone():
            print(f"  角色 {role_code} 已有 '*' 权限, 跳过")
            continue

        if dry_run:
            print(f"  [DRY-RUN] 角色 {role_code} 需绑定 '*' 权限 (permission_id={wildcard_perm_id})")
        else:
            conn.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                [role_id, wildcard_perm_id]
            )
            print(f"  角色 {role_code} 已绑定 '*' 权限")


def drop_columns(conn, dry_run=False):
    """
    Step 3: 删除字段 (SQLite 3.35+ supports DROP COLUMN)
    """
    print("\n[Step 3] 删除字段 ...")

    has_super_admin = column_exists(conn, 'roles', 'is_super_admin')
    has_priority = column_exists(conn, 'roles', 'priority')

    if has_super_admin:
        if dry_run:
            print(f"  [DRY-RUN] ALTER TABLE roles DROP COLUMN is_super_admin")
        else:
            conn.execute("ALTER TABLE roles DROP COLUMN is_super_admin")
            print("  is_super_admin 已删除")

    if has_priority:
        if dry_run:
            print(f"  [DRY-RUN] ALTER TABLE roles DROP COLUMN priority")
        else:
            conn.execute("ALTER TABLE roles DROP COLUMN priority")
            print("  priority 已删除")


def post_check(conn):
    """
    Step 4: 迁移后验证
    """
    print("\n[Step 4] 迁移后验证 ...")

    assert not column_exists(conn, 'roles', 'is_super_admin'), \
        "is_super_admin 字段仍存在!"
    assert not column_exists(conn, 'roles', 'priority'), \
        "priority 字段仍存在!"
    print("  [OK] is_super_admin + priority 字段已删除")

    # 验证 admin user 仍能通过 '*' 通配识别
    cur = conn.execute("""
        SELECT COUNT(DISTINCT u.id) AS c
        FROM users u
        JOIN user_group_members ugm ON u.id = ugm.user_id
        JOIN group_roles gr ON ugm.group_id = gr.group_id
        JOIN role_permissions rp ON gr.role_id = rp.role_id
        JOIN permissions p ON rp.permission_id = p.id
        WHERE p.code = '*'
    """)
    admin_count = cur.fetchone()['c']
    print(f"  [OK] 拥有 '*' 权限的 user 数: {admin_count}")
    assert admin_count >= 1, "至少应有 1 个 user 拥有 '*' 权限 (admin)"


def downgrade(conn):
    """
    回滚: 恢复 2 字段 + 从备份表恢复值
    """
    print("\n" + "=" * 60)
    print("[DOWNGRADE] V1 Cleanup Migration Rollback")
    print("=" * 60)

    if not table_exists(conn, BACKUP_TABLE):
        print(f"  [ERROR] 备份表 {BACKUP_TABLE} 不存在, 无法回滚")
        sys.exit(1)

    has_super_admin = column_exists(conn, 'roles', 'is_super_admin')
    has_priority = column_exists(conn, 'roles', 'priority')

    # 恢复 priority 列
    if not has_priority:
        conn.execute("ALTER TABLE roles ADD COLUMN priority INTEGER DEFAULT 0")
        print("  priority 列已恢复")

    # 恢复 is_super_admin 列
    if not has_super_admin:
        conn.execute("ALTER TABLE roles ADD COLUMN is_super_admin INTEGER DEFAULT 0")
        print("  is_super_admin 列已恢复")

    # 从备份表恢复数据
    cur = conn.execute(f"SELECT COUNT(*) AS c FROM {BACKUP_TABLE}")
    backup_count = cur.fetchone()['c']
    print(f"  备份表有 {backup_count} 行")

    if backup_count > 0:
        # 根据 id 恢复 priority 和 is_super_admin 值
        for col in ['priority', 'is_super_admin']:
            if column_exists(conn, BACKUP_TABLE, col) if False else True:
                # 简化: 直接更新
                conn.execute(f"""
                    UPDATE roles
                    SET {col} = (
                        SELECT {col} FROM {BACKUP_TABLE} WHERE {BACKUP_TABLE}.id = roles.id
                    )
                    WHERE id IN (SELECT id FROM {BACKUP_TABLE})
                """)
                print(f"  {col} 值已从备份恢复")

    # 删除备份表
    conn.execute(f"DROP TABLE {BACKUP_TABLE}")
    print(f"  备份表 {BACKUP_TABLE} 已删除")

    print("\n[DOWNGRADE] 完成. roles 表已恢复 V1 之前状态.")


def main():
    parser = argparse.ArgumentParser(description='V1 Cleanup Migration')
    parser.add_argument('--dry-run', action='store_true', help='只读模式, 不修改 DB')
    parser.add_argument('--downgrade', action='store_true', help='回滚迁移')
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB not found: {DB_PATH}")
        sys.exit(1)

    conn = get_conn()
    try:
        if args.downgrade:
            downgrade(conn)
        else:
            need_migrate = pre_check(conn, dry_run=args.dry_run)
            if not need_migrate:
                return

            if args.dry_run:
                print("\n[DRY-RUN] 不会执行修改, 只显示计划")
                return

            backup_data(conn)
            migrate_admin_permissions(conn)
            drop_columns(conn)
            post_check(conn)
            conn.commit()
            print("\n[SUCCESS] V1 迁移完成!")
            print("  - role.is_super_admin 列已删除")
            print("  - role.priority 列已删除")
            print(f"  - 数据已备份到 {BACKUP_TABLE}")
            print("  - 备份表部署后可手工 DROP TABLE 删除")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
