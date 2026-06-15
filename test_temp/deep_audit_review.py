# -*- coding: utf-8 -*-
"""
[MODULE] 深入审查审计日志问题
"""
import sqlite3
import json
import os

DB_PATH = r'd:/filework/excel-to-diagram/meta/architecture.db'


def main():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=" * 80)
    print("  深入审计日志审查")
    print("=" * 80)

    # 1. trace_id 缺失 - 按 action 分类
    print("\n[1] trace_id 缺失按 action 分类:")
    cur.execute("""
        SELECT action, object_type, COUNT(*) as cnt
        FROM audit_logs
        WHERE (trace_id IS NULL OR trace_id = '')
          AND created_at >= datetime('now', '-10 minutes')
        GROUP BY action, object_type
        ORDER BY cnt DESC
        LIMIT 20
    """)
    for r in cur.fetchall():
        print(f"  {r['action']:<20} {r['object_type']:<25} {r['cnt']} 条")

    # 2. trace_id 缺失 - 抽样看完整记录
    print("\n[2] trace_id 缺失 - 完整记录样本 (DISSOCIATE):")
    cur.execute("""
        SELECT id, action, object_type, object_id, field_name, user_id, user_name, ip_address, user_agent, extra_data, new_value, old_value
        FROM audit_logs
        WHERE (trace_id IS NULL OR trace_id = '')
          AND action = 'DISSOCIATE'
          AND created_at >= datetime('now', '-10 minutes')
        LIMIT 3
    """)
    for r in cur.fetchall():
        print(f"\n  ID={r['id']} {r['action']} {r['object_type']}#{r['object_id']}")
        print(f"    user: {r['user_name']} ({r['user_id']}) ip={r['ip_address']}")
        print(f"    field: {r['field_name']}")
        print(f"    user_agent: {r['user_agent']}")
        print(f"    new_value: {str(r['new_value'])[:150]}")
        print(f"    old_value: {str(r['old_value'])[:150]}")
        print(f"    extra_data: {str(r['extra_data'])[:150]}")

    # 3. trace_id 缺失 - CREATE 样本
    print("\n[3] trace_id 缺失 - 完整记录样本 (CREATE role_permissions):")
    cur.execute("""
        SELECT id, action, object_type, object_id, field_name, user_id, user_name, ip_address, user_agent, extra_data, new_value
        FROM audit_logs
        WHERE (trace_id IS NULL OR trace_id = '')
          AND action = 'CREATE'
          AND object_type = 'role_permissions'
          AND created_at >= datetime('now', '-10 minutes')
        LIMIT 3
    """)
    for r in cur.fetchall():
        print(f"\n  ID={r['id']} {r['action']} {r['object_type']}#{r['object_id']}")
        print(f"    user: {r['user_name']} ({r['user_id']}) ip={r['ip_address']}")
        print(f"    field: {r['field_name']}")
        print(f"    user_agent: {r['user_agent']}")
        print(f"    new_value: {str(r['new_value'])[:200]}")
        print(f"    extra_data: {str(r['extra_data'])[:200]}")

    # 4. trace_id 缺失率 - 整体
    print("\n[4] trace_id 缺失率 (按 action):")
    cur.execute("""
        SELECT action,
               COUNT(*) as total,
               SUM(CASE WHEN trace_id IS NULL OR trace_id = '' THEN 1 ELSE 0 END) as missing
        FROM audit_logs
        WHERE created_at >= datetime('now', '-10 minutes')
        GROUP BY action
        ORDER BY total DESC
    """)
    for r in cur.fetchall():
        rate = r['missing'] / r['total'] * 100 if r['total'] else 0
        print(f"  {r['action']:<20} total={r['total']:>5} missing={r['missing']:>5} ({rate:.1f}%)")

    # 5. target_display 缺失 - 实际数据
    print("\n[5] target_display 缺失 - new_value 完整内容:")
    cur.execute("""
        SELECT id, action, object_type, object_id, user_name, new_value, extra_data
        FROM audit_logs
        WHERE action IN ('ASSOCIATE', 'DISSOCIATE')
          AND created_at >= datetime('now', '-10 minutes')
          AND (new_value IS NOT NULL AND new_value != '')
        LIMIT 5
    """)
    for r in cur.fetchall():
        nv = r['new_value']
        try:
            p = json.loads(nv) if isinstance(nv, str) else nv
            print(f"\n  ID={r['id']} {r['action']} {r['object_type']}#{r['object_id']}")
            print(f"    user: {r['user_name']}")
            print(f"    parsed keys: {list(p.keys()) if isinstance(p, dict) else type(p).__name__}")
            if isinstance(p, dict):
                for k, v in p.items():
                    print(f"      {k} = {str(v)[:80]}")
        except Exception as e:
            print(f"  ID={r['id']} parse error: {e}, raw: {str(nv)[:100]}")

    # 6. DELETE_BLOCKED - 详细数据
    print("\n[6] DELETE_BLOCKED 实际数据:")
    cur.execute("""
        SELECT id, object_type, object_id, user_name, ip_address, new_value, extra_data
        FROM audit_logs
        WHERE action = 'DELETE_BLOCKED'
        ORDER BY id DESC
        LIMIT 5
    """)
    for r in cur.fetchall():
        print(f"\n  ID={r['id']} {r['object_type']}#{r['object_id']} by {r['user_name']} ip={r['ip_address']}")
        print(f"    new_value: {str(r['new_value'])[:200]}")
        print(f"    extra_data: {str(r['extra_data'])[:200]}")

    # 7. user_agent 缺失按 action
    print("\n[7] user_agent 缺失按 action:")
    cur.execute("""
        SELECT action,
               COUNT(*) as total,
               SUM(CASE WHEN user_agent IS NULL OR user_agent = '' THEN 1 ELSE 0 END) as missing
        FROM audit_logs
        WHERE created_at >= datetime('now', '-10 minutes')
        GROUP BY action
        HAVING total > 10
        ORDER BY total DESC
    """)
    for r in cur.fetchall():
        rate = r['missing'] / r['total'] * 100 if r['total'] else 0
        print(f"  {r['action']:<20} total={r['total']:>5} missing={r['missing']:>5} ({rate:.1f}%)")

    # 8. user_name 类型分布
    print("\n[8] user_name 实际内容样本:")
    cur.execute("""
        SELECT DISTINCT user_name
        FROM audit_logs
        WHERE created_at >= datetime('now', '-10 minutes')
          AND user_name IS NOT NULL AND user_name != ''
        LIMIT 20
    """)
    for r in cur.fetchall():
        print(f"  - '{r['user_name']}'")

    # 9. v2 字段 (action_kind, outcome) 缺失率
    print("\n[9] v2 字段填充情况:")
    for col in ['action_kind', 'outcome', 'parent_action_id', 'log_category', 'log_level']:
        cur.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN {col} IS NULL OR {col} = '' THEN 1 ELSE 0 END) as missing
            FROM audit_logs
            WHERE created_at >= datetime('now', '-10 minutes')
        """)
        r = cur.fetchone()
        rate = r['missing'] / r['total'] * 100 if r['total'] else 0
        print(f"  {col:<25} total={r['total']:>5} missing={r['missing']:>5} ({rate:.1f}%)")

    conn.close()


if __name__ == '__main__':
    main()
