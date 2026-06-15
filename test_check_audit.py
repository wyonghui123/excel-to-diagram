# -*- coding: utf-8 -*-
"""清理调试表 + 检查 created_by 完整覆盖"""
import sqlite3

DB_PATH = 'd:/filework/excel-to-diagram/meta/architecture.db'

# 业务表 (排除 auth 和关系表, 这些表不在 v1.1 owner refactor 范围)
BUSINESS_TABLES = [
    'products',
    'versions',
    'domains',
    'sub_domains',
    'service_modules',
    'business_objects',
    'relationships',
    'annotations',
    'enum_types',
    'enum_values',
    'permission_rules',
    'subflow_templates',
]

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("V1.1 后: 验证 owner_id 清理 + created_by 审计覆盖")
    print("=" * 80)

    # 1. 验证 owner_id 已清理
    print("\n[1] owner_id 清理验证")
    print("-" * 80)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        if table.startswith('sqlite_') or table.startswith('_') or table == 'roles_v1_backup':
            continue
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        if 'owner_id' in cols and table != 'products':
            print(f"  [WARN] {table}: 仍有 owner_id!")
        elif 'owner_id' in cols and table == 'products':
            print(f"  [OK] products: 保留 owner_id (顶层实体)")
        else:
            pass  # 无 owner_id, 正常

    # 2. created_by 覆盖检查
    print("\n[2] created_by 审计覆盖检查")
    print("-" * 80)
    for table in BUSINESS_TABLES:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        has_cb = 'created_by' in cols
        marker = '[OK]   ' if has_cb else '[MISS]'
        print(f"  {marker} {table:30} created_by={'YES' if has_cb else 'NO'}")

    # 3. 清理 _debug_versions_new
    print("\n[3] 清理调试表")
    print("-" * 80)
    if '_debug_versions_new' in tables:
        cursor.execute('SELECT COUNT(*) FROM _debug_versions_new')
        count = cursor.fetchone()[0]
        cursor.execute('DROP TABLE _debug_versions_new')
        print(f"  [OK] _debug_versions_new 已删除 (原 {count} 行)")
    else:
        print(f"  [INFO] _debug_versions_new 不存在, 跳过")

    # 4. 检查所有非系统表
    print("\n[4] 完整数据库表清单")
    print("-" * 80)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    all_tables = [row[0] for row in cursor.fetchall()]
    for t in all_tables:
        if t.startswith('sqlite_') or t == 'roles_v1_backup':
            continue
        cursor.execute(f"PRAGMA table_info({t})")
        cols = [row[1] for row in cursor.fetchall()]
        cb = '[CB]' if 'created_by' in cols else '    '
        owner = '[OWNER]' if 'owner_id' in cols else '       '
        print(f"  {cb} {owner} {t}")

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("完成")
    print("=" * 80)

if __name__ == '__main__':
    main()
