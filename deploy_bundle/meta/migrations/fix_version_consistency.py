# -*- coding: utf-8 -*-
"""
数据修复脚本：修复 relationships 表中 version_id 与引用的 BOs 版本不一致的问题

问题描述：
- relationships 表中 version_id=1 的记录引用的 source_bo_id/target_bo_id 属于 version_id=2
- 这导致数据不一致，树视图和列表视图的数据不匹配

解决方案：
- 将引用的 BOs 版本不匹配的 relationships 的 version_id 更新为 2
- 使 relationships 与其引用的 BOs 版本一致

执行方式：
    python -m meta.migrations.fix_version_consistency

注意：此脚本会修改数据，执行前请备份数据库
"""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from meta.tests.test_utils import get_test_db_path


def fix_version_consistency():
    """修复 relationships 的版本一致性问题"""
    db_path = get_test_db_path()
    print(f"数据库路径: {db_path}")

    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 查找 version_id 不匹配的 relationships
    # 对于每条 relationship，检查其 source_bo_id 和 target_bo_id 的 version_id
    # 如果 source_bo 或 target_bo 的 version_id 与 relationship 的 version_id 不同，需要修复
    cursor.execute("""
        SELECT r.id, r.version_id, r.source_bo_id, r.target_bo_id,
               bo_src.version_id as src_bo_version,
               bo_tgt.version_id as tgt_bo_version
        FROM relationships r
        LEFT JOIN business_objects bo_src ON r.source_bo_id = bo_src.id
        LEFT JOIN business_objects bo_tgt ON r.target_bo_id = bo_tgt.id
        WHERE r.source_bo_id IS NOT NULL OR r.target_bo_id IS NOT NULL
    """)

    rows = cursor.fetchall()
    inconsistent = []

    for row in rows:
        rel_id, rel_v, src_bo, tgt_bo, src_v, tgt_v = row

        # 获取有效的版本（取 source_bo 和 target_bo 版本中的最大值）
        effective_version = rel_v
        if src_v is not None:
            effective_version = max(effective_version, src_v)
        if tgt_v is not None:
            effective_version = max(effective_version, tgt_v)

        if effective_version != rel_v:
            inconsistent.append({
                'id': rel_id,
                'old_version': rel_v,
                'new_version': effective_version,
                'source_bo': src_bo,
                'source_bo_version': src_v,
                'target_bo': tgt_bo,
                'target_bo_version': tgt_v
            })

    print(f"\n找到 {len(inconsistent)} 条版本不一致的 relationships:")

    if not inconsistent:
        print("  无需修复")
        conn.close()
        return True

    for item in inconsistent:
        print(f"  关系 {item['id']}: version {item['old_version']} -> {item['new_version']}")
        print(f"    source_bo={item['source_bo']}(v{item['source_bo_version']}), "
              f"target_bo={item['target_bo']}(v{item['target_bo_version']})")

    # 执行修复
    print(f"\n执行修复...")
    fixed_count = 0
    for item in inconsistent:
        try:
            cursor.execute(
                "UPDATE relationships SET version_id = ? WHERE id = ?",
                (item['new_version'], item['id'])
            )
            fixed_count += 1
        except sqlite3.Error as e:
            print(f"  修复关系 {item['id']} 失败: {e}")

    conn.commit()

    # 验证修复
    cursor.execute("""
        SELECT r.id, r.version_id, bo_src.version_id, bo_tgt.version_id
        FROM relationships r
        JOIN business_objects bo_src ON r.source_bo_id = bo_src.id
        JOIN business_objects bo_tgt ON r.target_bo_id = bo_tgt.id
        WHERE r.version_id != bo_src.version_id OR r.version_id != bo_tgt.version_id
    """)
    remaining = cursor.fetchall()

    print(f"\n修复完成:")
    print(f"  已修复: {fixed_count} 条")
    print(f"  仍不一致: {len(remaining)} 条")

    conn.close()

    return len(remaining) == 0


if __name__ == '__main__':
    print("=" * 60)
    print("Relationships 版本一致性修复")
    print("=" * 60)

    if fix_version_consistency():
        print("\n修复成功!")
    else:
        print("\n修复完成，但仍有数据不一致")
