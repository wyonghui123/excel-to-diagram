import sqlite3
import json

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

print("=" * 60)
print("验证enum_type审计日志是否存在")
print("=" * 60)

cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE object_type = 'enum_type'")
count = cursor.fetchone()[0]
print(f'\nenum_type审计日志数量: {count}')

if count > 0:
    cursor.execute("""
        SELECT id, object_type, object_id, action, field_name, old_value, new_value, user_name, created_at 
        FROM audit_logs 
        WHERE object_type = 'enum_type' 
        ORDER BY created_at DESC 
        LIMIT 5
    """)
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]
    print(f'\n前{len(rows)}条记录:')
    for row in rows:
        row_dict = dict(zip(col_names, row))
        print(json.dumps(row_dict, indent=2, ensure_ascii=False))
        print('-' * 40)
        
    # 测试API应该返回的数据
    print("\n" + "=" * 60)
    print("模拟API查询逻辑")
    print("=" * 60)
    
    enum_type_id = 'annotation_category'
    try:
        cursor.execute("""
            SELECT * FROM audit_logs 
            WHERE object_type = 'enum_type' AND object_id = ?
            ORDER BY created_at DESC
            LIMIT 50
        """, [enum_type_id])
        history_rows = cursor.fetchall()
        change_history = []
        for history_row in history_rows:
            history_dict = dict(zip([desc[0] for desc in cursor.description], history_row))
            change_history.append(history_dict)
        
        print(f"\n为枚举类型 '{enum_type_id}' 查询到的变更历史:")
        print(f"记录数: {len(change_history)}")
        if change_history:
            print("\n第一条记录:")
            print(json.dumps(change_history[0], indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"\n查询失败: {e}")
        import traceback
        traceback.print_exc()
else:
    print('\n没有找到enum_type的审计日志!')

conn.close()