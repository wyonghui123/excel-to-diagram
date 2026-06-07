import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

print("=" * 60)
print("检查enum_types表结构")
print("=" * 60)

try:
    cursor.execute('PRAGMA table_info(enum_types)')
    columns = cursor.fetchall()
    print('\nenum_types表结构:')
    for col in columns:
        print(f'  {col[1]}: {col[2]}')
    
    # 查看数据样例
    cursor.execute("SELECT * FROM enum_types LIMIT 3")
    rows = cursor.fetchall()
    if rows:
        col_names = [desc[0] for desc in cursor.description]
        print('\n前3条数据:')
        for row in rows:
            print('  ', dict(zip(col_names, row)))
except Exception as e:
    print(f"查询失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("搜索可能相关的审计日志")
print("=" * 60)

# 搜索所有包含"enum"关键词的object_type
try:
    cursor.execute("""
        SELECT DISTINCT object_type 
        FROM audit_logs 
        WHERE object_type LIKE '%enum%' 
           OR object_type LIKE '%Enum%'
           OR object_type LIKE '%ENUM%'
    """)
    types = cursor.fetchall()
    print('\n包含"enum"的object_type:')
    for t in types:
        count = cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE object_type = ?", [t[0]]).fetchone()[0]
        print(f'  {t[0]}: {count}条')
    
    if not types:
        print('  没有找到任何包含"enum"的记录')
        
except Exception as e:
    print(f"搜索失败: {e}")

# 查看最近的操作，看看是否有对枚举的操作
print("\n" + "=" * 60)
print("检查最近的所有审计日志")
print("=" * 60)

try:
    cursor.execute("""
        SELECT id, object_type, object_id, action, field_name, created_at 
        FROM audit_logs 
        ORDER BY created_at DESC 
        LIMIT 20
    """)
    rows = cursor.fetchall()
    print('\n最近20条审计日志:')
    for row in rows:
        print(f'  ID={row[0]:5d} | type={row[1]:20s} | obj_id={row[2]:5d} | action={row[3]:7s} | field={row[4] or "N/A":15s} | time={row[5][:19]}')
        
except Exception as e:
    print(f"查询失败: {e}")

conn.close()