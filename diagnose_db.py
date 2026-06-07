import os
import sqlite3
import time

db_path = 'meta/architecture.db'
wal_path = db_path + '-wal'
shm_path = db_path + '-shm'

print('=== 数据库文件状态 ===')
print(f'DB 文件: {db_path}')
print(f'  大小: {os.path.getsize(db_path) / 1024 / 1024:.2f} MB')

if os.path.exists(wal_path):
    print(f'WAL 文件: {wal_path}')
    print(f'  大小: {os.path.getsize(wal_path) / 1024 / 1024:.2f} MB')
else:
    print(f'WAL 文件: 不存在')

if os.path.exists(shm_path):
    print(f'SHM 文件: {shm_path}')
    print(f'  大小: {os.path.getsize(shm_path) / 1024:.2f} KB')
else:
    print(f'SHM 文件: 不存在')

# 检查数据库连接和锁状态
print('\n=== 数据库内部状态 ===')
try:
    conn = sqlite3.connect(db_path, timeout=5)
    
    # 检查journal_mode
    cursor = conn.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    print(f'Journal Mode: {journal_mode}')
    
    # 检查WAL checkpoint状态
    cursor = conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    result = cursor.fetchone()
    print(f'WAL Checkpoint: {result}')
    
    # 检查表数量
    cursor = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
    table_count = cursor.fetchone()[0]
    print(f'Tables: {table_count}')
    
    # 检查总行数（主要表）
    tables_to_check = ['enum_types', 'enum_values', 'audit_logs', 'users']
    for table in tables_to_check:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f'{table}: {count} rows')
        except Exception as e:
            print(f'{table}: ERROR - {e}')
    
    # 检查是否有锁定的查询
    print('\n=== 性能测试 ===')
    
    # 测试简单查询
    start = time.time()
    cursor = conn.execute("SELECT COUNT(*) FROM enum_types")
    count = cursor.fetchone()[0]
    elapsed = time.time() - start
    print(f'Simple query (COUNT enum_types): {elapsed*1000:.2f}ms')
    
    # 测试复杂查询
    start = time.time()
    cursor = conn.execute("""
        SELECT et.*, (SELECT COUNT(*) FROM enum_values ev WHERE ev.enum_type_id = et.id) as value_count 
        FROM enum_types et 
        LIMIT 10
    """)
    rows = cursor.fetchall()
    elapsed = time.time() - start
    print(f'Complex query (enum_types with value_count): {elapsed*1000:.2f}ms, rows={len(rows)}')
    
    # 测试audit_logs查询
    start = time.time()
    cursor = conn.execute("""
        SELECT status, COUNT(*) as cnt 
        FROM audit_logs 
        GROUP BY status
    """)
    status_counts = cursor.fetchall()
    elapsed = time.time() - start
    print(f'Audit logs by status: {elapsed*1000:.2f}ms')
    for row in status_counts:
        print(f'  {row[0]}: {row[1]}')
    
    conn.close()
    
except Exception as e:
    print(f'Error: {e}')