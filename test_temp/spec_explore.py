# -*- coding: utf-8 -*-
"""探索 audit_logs 实现: 表结构 / 索引 / 触发器 / 实际数据"""
import sqlite3
import json

DB = r'd:/filework/excel-to-diagram/meta/architecture.db'
c = sqlite3.connect(DB, timeout=10)

print('=== audit_logs 表结构 ===')
for r in c.execute('PRAGMA table_info(audit_logs)'):
    print(f'  {r[1]:<32} type={r[2]:<25} notnull={r[3]} default={r[4]!r}')

print('\n=== 索引 ===')
for r in c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='audit_logs'"):
    print(f'  {r[0]}: {(r[1] or "")[:150]}')

print('\n=== 触发器 ===')
for r in c.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'"):
    print(f'  {r[0]} (on {r[1]})')

print('\n=== 关联表 (外键 / 引用) ===')
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%audit%'"):
    print(f'  {r[0]}')

# 数据样本
print('\n=== 样本 (1条, 全字段) ===')
sample = c.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
cols = [d[1] for d in c.execute('PRAGMA table_info(audit_logs)')]
for col, val in zip(cols, sample):
    val_str = str(val)
    if len(val_str) > 200:
        val_str = val_str[:200] + '...'
    print(f'  {col:<30} = {val_str!r}')

# 最近 5 个新数据样本
print('\n=== 最近 5 条 (新数据) ===')
for row in c.execute("""
    SELECT id, action, object_type, object_id, user_name, log_level, log_category,
           parent_object_type, status, ip_address, user_agent, trace_id
    FROM audit_logs ORDER BY id DESC LIMIT 5
"""):
    print(f'  ID={row[0]:5d} {row[1]:<14} {row[2]:<18}#{row[3]:<5} '
          f'user={row[4]!r:<25} lv={row[5]!r:<6} cat={row[6]!r:<10} '
          f'parent={row[7]!r:<15} status={row[8]!r}')
    print(f'    ip={row[9]!r} ua={(row[10] or "")[:60]!r} trace={(row[11] or "")[:8]}')

# log_category 分布
print('\n=== log_category 分布 ===')
for r in c.execute("SELECT log_category, COUNT(*) FROM audit_logs GROUP BY log_category ORDER BY 2 DESC"):
    print(f'  {r[0]!r}: {r[1]}')

print('\n=== log_level 分布 ===')
for r in c.execute("SELECT log_level, COUNT(*) FROM audit_logs GROUP BY log_level ORDER BY 2 DESC"):
    print(f'  {r[0]!r}: {r[1]}')

print('\n=== status 分布 (retry/状态) ===')
for r in c.execute("SELECT status, COUNT(*) FROM audit_logs GROUP BY status"):
    print(f'  {r[0]!r}: {r[1]}')

# trace_id 关联数
n_total = c.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
n_unique_trace = c.execute("SELECT COUNT(DISTINCT trace_id) FROM audit_logs WHERE trace_id IS NOT NULL").fetchone()[0]
print(f'\n=== 关联性: 总 {n_total} 条, 唯一 trace {n_unique_trace}, 平均 {n_total/max(n_unique_trace,1):.1f} 条/trace ===')

# 最长 trace 链
print('\n=== 最长 trace 链 (top 5) ===')
for r in c.execute("""
    SELECT trace_id, COUNT(*) AS n FROM audit_logs
    WHERE trace_id IS NOT NULL
    GROUP BY trace_id ORDER BY n DESC LIMIT 5
"""):
    print(f'  trace {r[0][:8]}: {r[1]} 条')

# 状态字段
print('\n=== status 字段分布 (AUDIT_WRITE_FAILED 才有) ===')
for r in c.execute("SELECT status, COUNT(*) FROM audit_logs GROUP BY status"):
    print(f'  {r[0]!r}: {r[1]}')
