"""
BUG-V049: 修复 versions 表唯一索引

问题:
  uidx_versions_name 是 name 单字段全局唯一索引，
  导致不同产品的同名版本（如 V1）创建失败。

根因:
  2026-06-13 移除 naming_aspect/code 字段后，index_rule_engine 对
  business_key=True 的 name 字段自动创建单字段唯一索引。
  version.yaml 的 import_export.conflict_key="product_id,name" 声明了
  联合唯一，但引擎不读 conflict_key。

修复:
  1. 删除旧索引 uidx_versions_name (name 单字段全局唯一)
  2. 创建新索引 uidx_versions_product_name (product_id, name 联合唯一)
  3. version.yaml 显式定义 indexes 段，防止引擎重新创建单字段索引

运行: python meta/migrations/fix_version_unique_index.py
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))


def get_db_path():
    db_path = os.environ.get('DB_PATH')
    if db_path:
        return db_path
    default_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db'
    )
    return default_path


def migrate(conn):
    cursor = conn.cursor()

    # Step 1: 检查旧索引是否存在
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND name='uidx_versions_name'"
    )
    old_idx = cursor.fetchone()

    if old_idx:
        print(f"  [V049] Found old index: {old_idx[0]} -> {old_idx[1]}")
        cursor.execute("DROP INDEX IF EXISTS uidx_versions_name")
        print("  [V049] Dropped uidx_versions_name")
    else:
        print("  [V049] Old index uidx_versions_name not found (already removed?)")

    # Step 2: 检查新索引是否已存在
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND name='uidx_versions_product_name'"
    )
    new_idx = cursor.fetchone()

    if new_idx:
        print(f"  [V049] New index already exists: {new_idx[0]} -> {new_idx[1]}")
    else:
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uidx_versions_product_name ON versions(product_id, name)"
        )
        print("  [V049] Created uidx_versions_product_name ON versions(product_id, name)")

    conn.commit()

    # Step 3: 验证
    print("\n  [V049] --- Verification ---")
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='versions'"
    )
    for row in cursor.fetchall():
        unique_mark = " [UNIQUE]" if "UNIQUE" in (row[1] or "") else ""
        print(f"  [V049]   {row[0]}{unique_mark}: {row[1]}")

    # Step 4: 检查是否有数据冲突（同一 name 出现在不同 product 中）
    cursor.execute(
        "SELECT name, COUNT(DISTINCT product_id) as cnt FROM versions GROUP BY name HAVING cnt > 1"
    )
    conflicts = cursor.fetchall()
    if conflicts:
        print(f"\n  [V049] WARNING: {len(conflicts)} version name(s) exist across multiple products:")
        for c in conflicts:
            print(f"  [V049]   name='{c[0]}' appears in {c[1]} products")
    else:
        print("\n  [V049] No cross-product version name conflicts found")


def main():
    db_path = get_db_path()
    print(f"[V049] Database: {db_path}")

    if not os.path.exists(db_path):
        print(f"[V049] ERROR: Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        migrate(conn)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
