# -*- coding: utf-8 -*-
"""
迁移脚本: 给 role_dimension_scopes 表添加 bo_id 列

【背景 2026-06-04】
按 Spec v1.3 (data-permission-unified-model)，管理维度升级为公共维度。
- bo_id = NULL  → 公共维度（影响所有声明了 dimension_bindings 的 BO）
- bo_id = 'domain' → BO 级覆盖（只影响特定 BO）

默认值 NULL，零数据迁移，兼容现有数据（视为公共维度）。

执行：
    python meta/migrations/add_role_dim_scope_bo_id_2026.py

回滚：
    python meta/migrations/add_role_dim_scope_bo_id_2026.py --down
"""
import sqlite3
import os
import sys


def get_db_path():
    # meta/migrations/add_role_dim_scope_bo_id_2026.py -> meta/architecture.db
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )


def add_bo_id_column():
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT sqlite_version()")
    print(f"SQLite 版本: {cursor.fetchone()[0]}")

    cursor.execute("PRAGMA table_info(role_dimension_scopes)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"role_dimension_scopes 现有列: {columns}")

    if 'bo_id' in columns:
        print("bo_id 列已存在，无需处理")
        conn.close()
        return

    print("添加 bo_id 列（ALTER TABLE ADD COLUMN）...")
    try:
        cursor.execute(
            "ALTER TABLE role_dimension_scopes ADD COLUMN bo_id VARCHAR(50) NULL"
        )
        conn.commit()
        print("✓ bo_id 列已添加（默认 NULL，所有现有记录视为公共维度）")
    except Exception as e:
        print(f"✗ 迁移失败: {e}")
        raise

    # 验证
    cursor.execute("PRAGMA table_info(role_dimension_scopes)")
    new_columns = [row[1] for row in cursor.fetchall()]
    print(f"新列: {new_columns}")
    if 'bo_id' in new_columns:
        print("✓ 验证通过：bo_id 已添加")
    else:
        print("✗ 验证失败：bo_id 仍不存在")

    # 索引（可选，加速 bo_id 查询）
    print("创建 idx_role_dim_scope_bo_id 索引...")
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_role_dim_scope_bo_id "
            "ON role_dimension_scopes(bo_id)"
        )
        conn.commit()
        print("✓ 索引已创建")
    except Exception as e:
        print(f"⚠ 索引创建失败（非阻塞）: {e}")

    conn.close()
    print("迁移完成")


def drop_bo_id_column():
    """回滚：删除 bo_id 列"""
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(role_dimension_scopes)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'bo_id' not in columns:
        print("bo_id 列不存在，无需回滚")
        conn.close()
        return

    print("删除 bo_id 列（回滚）...")
    try:
        cursor.execute("ALTER TABLE role_dimension_scopes DROP COLUMN bo_id")
        conn.commit()
        print("✓ bo_id 列已删除")
    except Exception as e:
        print(f"✗ 回滚失败: {e}")
        raise

    conn.close()
    print("回滚完成")


if __name__ == '__main__':
    if '--down' in sys.argv:
        drop_bo_id_column()
    else:
        add_bo_id_column()
