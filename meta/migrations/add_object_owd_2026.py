# -*- coding: utf-8 -*-
"""
迁移脚本: 创建 object_owd 表 (FR-012 对象基线 OWD)

【背景 2026-07-26】
Spec 12_implementation_plan §3.2 / Spec 10_unified_permission_final:
  FR-012 对象基线共享 (OWD, Object Wide Defaults)
  借鉴 Salesforce OWD 概念, 为每个 BO 定义默认可见性:
    - private:          仅 owner 可见 (默认)
    - public_read:      所有用户可读
    - public_read_write: 所有用户可读写

  OWD 在 derivation_pipeline.derive() Step 2 加载, 作为最低优先级的兜底 intent:
    - source='owd'
    - 优先级低于 manual / derived / menu
    - 当角色无任何配置时, 使用 OWD 作为基线

新表结构:
    object_owd(bo_id, default_visibility, default_permission_level, description)

执行:
    python meta/migrations/add_object_owd_2026.py

回滚:
    python meta/migrations/add_object_owd_2026.py --down
"""
import sqlite3
import os
import sys


def get_db_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )


def up():
    """创建 object_owd 表"""
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='object_owd'
    """)
    if cursor.fetchone():
        print("object_owd 表已存在，无需处理")
        conn.close()
        return

    print("创建 object_owd 表...")
    cursor.execute("""
        CREATE TABLE object_owd (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bo_id VARCHAR(100) NOT NULL UNIQUE,
            default_visibility VARCHAR(50) NOT NULL DEFAULT 'private',
            default_permission_level VARCHAR(50) NOT NULL DEFAULT 'none',
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CHECK (default_visibility IN ('private', 'public_read', 'public_read_write')),
            CHECK (default_permission_level IN ('none', 'read', 'write', 'admin'))
        )
    """)
    print("  ✓ object_owd 表创建成功")

    # 索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_object_owd_bo
        ON object_owd (bo_id)
    """)
    print("  ✓ 创建索引 (bo_id)")

    # 为现有 BO 插入默认 OWD (private + none)
    # 即: 无显式配置时, BO 默认完全私有 (仅 owner 可见)
    bo_ids = [
        'product', 'version', 'domain', 'sub_domain',
        'service_module', 'business_object', 'relationship',
        'user', 'role', 'menu', 'enum_type', 'enum_value',
        'annotation', 'audit_log', 'change_event',
    ]
    for bo_id in bo_ids:
        cursor.execute(
            "INSERT OR IGNORE INTO object_owd (bo_id, default_visibility, default_permission_level, description) "
            "VALUES (?, ?, ?, ?)",
            [bo_id, 'private', 'none', f'Default OWD for {bo_id} (auto-created)']
        )
    print(f"  ✓ 插入 {len(bo_ids)} 个默认 OWD 记录 (private + none)")

    conn.commit()
    conn.close()
    print("迁移完成")


def down():
    """删除 object_owd 表"""
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='object_owd'
    """)
    if not cursor.fetchone():
        print("object_owd 表不存在，无需处理")
        conn.close()
        return

    print("删除 object_owd 表...")
    cursor.execute("DROP TABLE IF EXISTS object_owd")
    print("  ✓ object_owd 表已删除")
    conn.commit()
    conn.close()
    print("回滚完成")


if __name__ == '__main__':
    if '--down' in sys.argv:
        down()
    else:
        up()
