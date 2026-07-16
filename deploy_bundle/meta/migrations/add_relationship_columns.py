# -*- coding: utf-8 -*-
"""
数据库迁移：为 relationships 表添加缺失的列

根据 meta/schemas/relationship.yaml 中定义的字段，添加数据库表中缺失的列

执行方式：
    python -m meta.migrations.add_relationship_columns

迁移列：
    - source_domain_id, target_domain_id (INTEGER)
    - source_sub_domain_id, target_sub_domain_id (INTEGER)
    - source_service_module_id, target_service_module_id (INTEGER)
    - source_bo_name, target_bo_name (VARCHAR(500))
    - category_label, category_type (VARCHAR(100))
    - domain_relation, sub_domain_relation, module_relation (VARCHAR(200))
    - is_in_scope (BOOLEAN)
    - version_name (VARCHAR(200))
    - source_domain_name, source_sub_domain_name, source_service_module_name (VARCHAR(500))
    - target_domain_name, target_sub_domain_name, target_service_module_name (VARCHAR(500))
    - code (VARCHAR(200))  -- 关系实例编码(KeyTemplate)
    - relation_type (VARCHAR(50))  -- 关系类型
"""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from meta.tests.test_utils import get_test_db_path


def get_existing_columns(cursor):
    """获取表中已存在的列"""
    cursor.execute("PRAGMA table_info(relationships)")
    return {row[1] for row in cursor.fetchall()}


def migrate():
    """执行迁移"""
    db_path = get_test_db_path()
    print(f"数据库路径: {db_path}")

    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    existing_cols = get_existing_columns(cursor)
    print(f"已存在的列: {sorted(existing_cols)}")

    # 根据 schema 定义的列
    new_columns = {
        # 层级ID引用 (INTEGER)
        'source_domain_id': 'INTEGER',
        'source_sub_domain_id': 'INTEGER',
        'source_service_module_id': 'INTEGER',
        'target_domain_id': 'INTEGER',
        'target_sub_domain_id': 'INTEGER',
        'target_service_module_id': 'INTEGER',
        # 名称字段 (VARCHAR 500)
        'source_bo_name': 'VARCHAR(500)',
        'target_bo_name': 'VARCHAR(500)',
        'source_domain_name': 'VARCHAR(500)',
        'source_sub_domain_name': 'VARCHAR(500)',
        'source_service_module_name': 'VARCHAR(500)',
        'target_domain_name': 'VARCHAR(500)',
        'target_sub_domain_name': 'VARCHAR(500)',
        'target_service_module_name': 'VARCHAR(500)',
        # 分类字段 (VARCHAR 100)
        'category_label': 'VARCHAR(100)',
        'category_type': 'VARCHAR(100)',
        # 关系描述字段 (VARCHAR 200)
        'domain_relation': 'VARCHAR(200)',
        'sub_domain_relation': 'VARCHAR(200)',
        'module_relation': 'VARCHAR(200)',
        # 布尔字段
        'is_in_scope': 'BOOLEAN',
        # 版本名称 (VARCHAR 200)
        'version_name': 'VARCHAR(200)',
        # 关系编码 (VARCHAR 200)
        'code': 'VARCHAR(200)',
        # 关系类型 (VARCHAR 50)
        'relation_type': 'VARCHAR(50)',
    }

    added_columns = []
    failed_columns = []

    for col_name, col_type in new_columns.items():
        if col_name in existing_cols:
            print(f"  跳过 {col_name} (已存在)")
            continue

        try:
            sql = f"ALTER TABLE relationships ADD COLUMN {col_name} {col_type}"
            cursor.execute(sql)
            added_columns.append(col_name)
            print(f"  添加 {col_name} ({col_type})")
        except sqlite3.Error as e:
            failed_columns.append((col_name, str(e)))
            print(f"  失败 {col_name}: {e}")

    conn.commit()

    # 验证添加的列
    new_existing_cols = get_existing_columns(cursor)
    print(f"\n迁移后已存在的列: {sorted(new_existing_cols)}")

    conn.close()

    # 输出结果
    print(f"\n迁移完成:")
    print(f"  成功添加: {len(added_columns)} 列")
    for col in added_columns:
        print(f"    - {col}")

    if failed_columns:
        print(f"  失败: {len(failed_columns)} 列")
        for col, err in failed_columns:
            print(f"    - {col}: {err}")
        return False

    return True


def backfill_data():
    """回填已有数据：根据 source_bo_id/target_bo_id 填充关联的 domain_id 等字段

    注意：此回填基于 BOs 的当前 domain 信息。如果 relationships 与 BOs 的版本不匹配，
    回填的 domain_id 可能指向不同版本的数据。这是数据一致性问题，需要在数据层面修复。
    """
    db_path = get_test_db_path()
    print(f"\n开始回填数据...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 检查需要回填的数量
        cursor.execute("""
            SELECT COUNT(*) FROM relationships
            WHERE source_domain_id IS NULL AND source_bo_id IS NOT NULL
        """)
        count = cursor.fetchone()[0]

        if count == 0:
            print("  没有需要回填的数据")
            conn.close()
            return True

        print(f"  找到 {count} 条需要回填的记录")

        # 回填 source_domain_id, target_domain_id
        # 基于 BO -> service_module -> sub_domain -> domain 的关联
        cursor.execute("""
            UPDATE relationships SET
                source_domain_id = (
                    SELECT sd.domain_id
                    FROM business_objects bo
                    JOIN service_modules sm ON bo.service_module_id = sm.id
                    JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                    WHERE bo.id = relationships.source_bo_id
                ),
                target_domain_id = (
                    SELECT sd.domain_id
                    FROM business_objects bo
                    JOIN service_modules sm ON bo.service_module_id = sm.id
                    JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                    WHERE bo.id = relationships.target_bo_id
                ),
                source_sub_domain_id = (
                    SELECT sm.sub_domain_id
                    FROM business_objects bo
                    JOIN service_modules sm ON bo.service_module_id = sm.id
                    WHERE bo.id = relationships.source_bo_id
                ),
                target_sub_domain_id = (
                    SELECT sm.sub_domain_id
                    FROM business_objects bo
                    JOIN service_modules sm ON bo.service_module_id = sm.id
                    WHERE bo.id = relationships.target_bo_id
                ),
                source_service_module_id = (
                    SELECT service_module_id FROM business_objects
                    WHERE id = relationships.source_bo_id
                ),
                target_service_module_id = (
                    SELECT service_module_id FROM business_objects
                    WHERE id = relationships.target_bo_id
                )
            WHERE source_bo_id IS NOT NULL
        """)
        updated = cursor.rowcount
        conn.commit()
        print(f"  成功回填 {updated} 条记录")

    except sqlite3.Error as e:
        print(f"  回填失败: {e}")
        conn.rollback()
        conn.close()
        return False

    conn.close()
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("relationships 表结构迁移")
    print("=" * 60)

    if migrate():
        backfill_data()
        print("\n迁移成功完成!")
    else:
        print("\n迁移失败!")
        sys.exit(1)
