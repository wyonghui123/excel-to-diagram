# -*- coding: utf-8 -*-
"""深度分析: user_name 'other' 是什么 / v2 字段分布 / 可恢复性"""
import sqlite3
import json
import collections

DB = r'd:/filework/excel-to-diagram/meta/architecture.db'
c = sqlite3.connect(DB, timeout=10)
cur = c.cursor()

print('=== user_name "other" 1397 条样本 (8条) ===')
for r in cur.execute("""
    SELECT id, action, object_type, object_id, user_name
    FROM audit_logs
    WHERE user_name NOT LIKE '%(%'
      AND user_name NOT IN ('', 'admin', 'system', 'anonymous')
      AND user_name IS NOT NULL
    ORDER BY id DESC LIMIT 8
"""):
    print(f'  ID={r[0]:5d} {r[1]:<14} {r[2]:<20}#{r[3]:<5} user_name={r[4]!r}')

print()
print('=== user_name Top 20 分布 ===')
for r in cur.execute("""
    SELECT user_name, COUNT(*) AS n FROM audit_logs
    GROUP BY user_name ORDER BY n DESC LIMIT 20
"""):
    print(f'  {r[0]!r}: {r[1]}')

print()
print('=== log_category 分布 ===')
for r in cur.execute("""
    SELECT log_category, COUNT(*) FROM audit_logs GROUP BY log_category ORDER BY 2 DESC
"""):
    print(f'  {r[0]!r}: {r[1]}')

print()
print('=== log_level 分布 ===')
for r in cur.execute("""
    SELECT log_level, COUNT(*) FROM audit_logs GROUP BY log_level ORDER BY 2 DESC
"""):
    print(f'  {r[0]!r}: {r[1]}')

print()
print('=== parent_object_type 分布 (Top 10) ===')
for r in cur.execute("""
    SELECT parent_object_type, COUNT(*) FROM audit_logs
    WHERE parent_object_type IS NOT NULL
    GROUP BY parent_object_type ORDER BY 2 DESC LIMIT 10
"""):
    print(f'  {r[0]}: {r[1]}')

print()
print('=== 最新 3 条 DELETE_BLOCKED 完整可读性 ===')
for r in cur.execute("""
    SELECT id, object_type, object_id, user_name, trace_id, extra_data, log_level
    FROM audit_logs
    WHERE action = 'DELETE_BLOCKED'
    ORDER BY id DESC LIMIT 3
"""):
    print(f'  ID={r[0]} {r[1]}#{r[2]} user={r[3]!r} trace={r[4][:8] if r[4] else None}')
    try:
        ed = json.loads(r[5] or '{}')
        print(f'    keys: {list(ed.keys())}')
        print(f'    message: {ed.get("message") or ed.get("error_message")}')
        print(f'    error_code: {ed.get("error_code")}')
        print(f'    recovery: {ed.get("recovery") or ed.get("hint") or ed.get("recovery_suggestion") or ed.get("suggestion") or "NONE"}')
    except Exception as e:
        print(f'    parse fail: {e}')

print()
print('=== AUDIT_WRITE_FAILED 3条 (可恢复性 / 重试机制) ===')
for r in cur.execute("""
    SELECT id, object_type, object_id, user_name, trace_id, extra_data, error_message, status, retry_count
    FROM audit_logs
    WHERE action = 'AUDIT_WRITE_FAILED'
    ORDER BY id DESC LIMIT 3
"""):
    print(f'  ID={r[0]} {r[1]}#{r[2]} user={r[3]!r} trace={r[4][:8] if r[4] else None}')
    print(f'    status={r[7]} retry={r[8]} error={(r[6] or "")[:80]}')
    print(f'    extra: {(r[5] or "")[:200]}')

print()
print('=== 看 created_at 索引 / 关联关系 ===')
for r in cur.execute("PRAGMA index_list(audit_logs)"):
    print(f'  index: {r}')

print()
print('=== trace_id 唯一性 (跨多表关联) ===')
n_total = cur.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
n_unique_trace = cur.execute("SELECT COUNT(DISTINCT trace_id) FROM audit_logs WHERE trace_id IS NOT NULL").fetchone()[0]
n_per_trace = cur.execute("""
    SELECT trace_id, COUNT(*) AS n FROM audit_logs
    WHERE trace_id IS NOT NULL
    GROUP BY trace_id ORDER BY n DESC LIMIT 5
""").fetchall()
print(f'  总日志: {n_total}, 唯一 trace_id: {n_unique_trace}')
print(f'  每个 trace 平均日志数: {n_total / max(n_unique_trace, 1):.1f}')
print('  Top 5 单 trace 最多:')
for r in n_per_trace:
    print(f'    {r[0][:8]}: {r[1]} 条')

# 看 cascade chain (一次删除产生多少审计)
print()
print('=== Cascade chain 分析: 一次删除产生多少审计日志? ===')
print('  找 user_group 被删除的 trace, 看 DISSOCIATE 数量:')
for r in cur.execute("""
    SELECT trace_id, COUNT(*) AS n
    FROM audit_logs
    WHERE action = 'DISSOCIATE'
      AND extra_data LIKE '%cascade_reason%'
      AND trace_id IS NOT NULL
    GROUP BY trace_id
    HAVING n > 1
    ORDER BY n DESC LIMIT 5
"""):
    print(f'    trace {r[0][:8]}: {r[1]} 条 cascade DISSOCIATE')

print()
print('=== 旧数据 vs 新数据对比 (按 created_at 划分) ===')
old_n = cur.execute("""
    SELECT COUNT(*) FROM audit_logs
    WHERE action='DISSOCIATE'
      AND (trace_id IS NULL OR trace_id = '')
      AND created_at < '2026-06-12 13:00'
""").fetchone()[0]
new_n = cur.execute("""
    SELECT COUNT(*) FROM audit_logs
    WHERE action='DISSOCIATE'
      AND created_at >= '2026-06-12 13:00'
""").fetchone()[0]
new_miss = cur.execute("""
    SELECT COUNT(*) FROM audit_logs
    WHERE action='DISSOCIATE'
      AND (trace_id IS NULL OR trace_id = '')
      AND created_at >= '2026-06-12 13:00'
""").fetchone()[0]
print(f'  修复前 (created_at < 13:00) 缺 trace_id 的 DISSOCIATE: {old_n}')
print(f'  修复后 (created_at >= 13:00) 总 DISSOCIATE: {new_n}, 缺 trace_id: {new_miss} (0%目标)')
