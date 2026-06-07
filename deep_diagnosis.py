"""
后端API超时根因分析工具

系统性诊断：
1. 数据库连接获取时间
2. 拦截器链执行时间
3. 视图配置构建时间
4. 内存和线程状态
"""

import time
import threading
import sqlite3
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("后端API超时根因分析")
print("=" * 60)

# 1. 数据库连接测试
print("\n【1】数据库连接测试")
db_path = 'meta/architecture.db'

start = time.time()
for i in range(10):
    conn = sqlite3.connect(db_path, timeout=5)
    cursor = conn.execute("SELECT 1")
    cursor.fetchone()
    conn.close()
elapsed = time.time() - start
print(f"  10次连接/查询/关闭: {elapsed*1000:.2f}ms (平均 {elapsed*1000/10:.2f}ms/次)")

# 2. 连接池压力测试
print("\n【2】连接池压力测试（模拟并发）")
results = []
def db_worker(worker_id):
    try:
        start = time.time()
        conn = sqlite3.connect(db_path, timeout=30)
        
        # 执行复杂查询
        cursor = conn.execute("""
            SELECT et.*, 
                   (SELECT COUNT(*) FROM enum_values ev WHERE ev.enum_type_id = et.id) as value_count 
            FROM enum_types et
            ORDER BY et.name
            LIMIT 20
        """)
        rows = cursor.fetchall()
        
        # 写入测试（在事务中）
        conn.execute("BEGIN")
        cursor = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE status='failed'")
        failed_count = cursor.fetchone()[0]
        conn.rollback()
        
        conn.close()
        elapsed = time.time() - start
        results.append((worker_id, elapsed, len(rows), failed_count))
    except Exception as e:
        results.append((worker_id, -1, 0, str(e)))

threads = []
for i in range(5):
    t = threading.Thread(target=db_worker, args=(i,))
    threads.append(t)
    t.start()

start = time.time()
for t in threads:
    t.join(timeout=60)
total_elapsed = time.time() - start

print(f"  5个线程并发执行: {total_elapsed:.2f}s")
for worker_id, elapsed, rows, failed in sorted(results):
    if elapsed > 0:
        print(f"    Worker {worker_id}: {elapsed*1000:.2f}ms, rows={rows}, failed_audit={failed}")
    else:
        print(f"    Worker {worker_id}: ERROR - {failed}")

# 3. WAL锁检测
print("\n【3】WAL锁检测")
try:
    conn = sqlite3.connect(db_path, timeout=5)
    
    # 检查是否有未完成的写事务
    cursor = conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    checkpoint_result = cursor.fetchone()
    print(f"  WAL Checkpoint结果: {checkpoint_result}")
    print(f"    - WAL中待checkpoint的页数: {checkpoint_result[0]}")
    print(f"    - checkpointed的页数: {checkpoint_result[1]}")
    print(f"    - 数据库文件中的页数: {checkpoint_result[2]}")
    
    # 检查数据库锁状态
    cursor = conn.execute("PRAGMA lock_status")
    locks = cursor.fetchall()
    print(f"  当前锁状态:")
    for lock in locks:
        if lock[1] != 'unlocked':
            print(f"    {lock[0]}: {lock[1]} [WARNING]")
    
    # 检查是否有长时间运行的读事务
    cursor = conn.execute("PRAGMA busy_timeout")
    busy_timeout = cursor.fetchone()[0]
    print(f"  Busy Timeout设置: {busy_timeout}ms")
    
    conn.close()
except Exception as e:
    print(f"  锁检测失败: {e}")

# 4. 文件系统检查
print("\n【4】文件系统状态")
files_to_check = [
    'meta/architecture.db',
    'meta/architecture.db-wal', 
    'meta/architecture.db-shm'
]
for f in files_to_check:
    if os.path.exists(f):
        size = os.path.getsize(f)
        mtime = os.path.getmtime(f)
        mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
        print(f"  {f}:")
        print(f"    大小: {size/1024/1024:.2f} MB")
        print(f"    修改时间: {mtime_str}")
    else:
        print(f"  {f}: 不存在")

# 5. 线程和内存检查
print("\n【5】运行时环境")
print(f"  活跃线程数: {threading.active_count()}")
print(f"  当前线程: {threading.current_thread().name}")
for t in threading.enumerate():
    if t != threading.main_thread():
        print(f"    - {t.name} (daemon={t.daemon})")

# 6. audit_logs性能深度分析
print("\n【6】audit_logs表深度分析")
try:
    conn = sqlite3.connect(db_path, timeout=5)
    
    # 按时间分布
    cursor = conn.execute("""
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as cnt,
            SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed_cnt
        FROM audit_logs 
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 7
    """)
    daily_stats = cursor.fetchall()
    print("  最近7天审计日志统计:")
    for row in daily_stats:
        print(f"    {row[0]}: 总计={row[1]}, 失败={row[2]}")
    
    # 失败日志的错误类型分析
    cursor = conn.execute("""
        SELECT error_message, COUNT(*) as cnt 
        FROM audit_logs 
        WHERE status='failed' AND error_message IS NOT NULL AND error_message != ''
        GROUP BY error_message
        ORDER BY cnt DESC
        LIMIT 5
    """)
    error_types = cursor.fetchall()
    print("  失败日志错误类型TOP5:")
    for row in error_types:
        msg = row[0][:50] + '...' if len(row[0]) > 50 else row[0]
        print(f"    [{row[1]}次] {msg}")
    
    # 索引使用情况
    cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM audit_logs WHERE status='failed'")
    plan = cursor.fetchall()
    print("  失败查询执行计划:")
    for row in plan:
        print(f"    {row}")
    
    conn.close()
except Exception as e:
    print(f"  分析失败: {e}")

print("\n" + "=" * 60)
print("分析完成")
print("=" * 60)