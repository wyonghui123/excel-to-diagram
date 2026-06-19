#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[E.1] 排查脚本: UNKNOWN action 来源分析

问题: 近 7 天 1684 条 action=UNKNOWN
排查:
  1. 按 object_type 分布
  2. 按 user_name 分布 (找出是 system/特定用户)
  3. 按 status 分布 (failed? pending?)
  4. 按 created_at 时间分布 (是否集中在某个时间段)
  5. extra_data / error_message 字段 (是否带错误信息)
"""
import sqlite3
import os
import json
from collections import Counter, defaultdict
from datetime import datetime

DB_PATH = "meta/architecture.db"

if not os.path.exists(DB_PATH):
    print(f"[ERROR] DB not found: {DB_PATH}")
    import sys
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 80)
print(f"UNKNOWN Action 排查报告")
print(f"Generated: {datetime.now().isoformat()}")
print("=" * 80)

# 1. 总数
cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'UNKNOWN'")
total = cur.fetchone()[0]
print(f"\n[1] 总数: {total}")

# 2. 按 object_type
print(f"\n[2] 按 object_type 分布:")
cur.execute("""
    SELECT object_type, COUNT(*) as cnt
    FROM audit_logs
    WHERE action = 'UNKNOWN'
    GROUP BY object_type
    ORDER BY cnt DESC
    LIMIT 20
""")
for r in cur.fetchall():
    print(f"   {r['object_type']:30s} {r['cnt']:5d}")

# 3. 按 user_name
print(f"\n[3] 按 user_name 分布 (前 10):")
cur.execute("""
    SELECT user_name, COUNT(*) as cnt
    FROM audit_logs
    WHERE action = 'UNKNOWN'
    GROUP BY user_name
    ORDER BY cnt DESC
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"   {r['user_name']!r:30s} {r['cnt']:5d}")

# 4. 按 status
print(f"\n[4] 按 status 分布:")
cur.execute("""
    SELECT status, COUNT(*) as cnt
    FROM audit_logs
    WHERE action = 'UNKNOWN'
    GROUP BY status
    ORDER BY cnt DESC
""")
for r in cur.fetchall():
    print(f"   {r['status'] or '(空)':20s} {r['cnt']:5d}")

# 5. 按日期 (近 30 天)
print(f"\n[5] 按日期分布 (近 30 天):")
cur.execute("""
    SELECT DATE(created_at) as d, COUNT(*) as cnt
    FROM audit_logs
    WHERE action = 'UNKNOWN'
      AND DATE(created_at) >= DATE('now', '-30 days')
    GROUP BY DATE(created_at)
    ORDER BY d DESC
""")
for r in cur.fetchall():
    print(f"   {r['d']}  {r['cnt']:5d}")

# 6. extra_data 样本
print(f"\n[6] extra_data 样本 (前 5 条):")
cur.execute("""
    SELECT id, created_at, object_type, user_name, extra_data, error_message
    FROM audit_logs
    WHERE action = 'UNKNOWN'
    ORDER BY created_at DESC
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"   id={r['id']} [{r['created_at']}] {r['object_type']}/{r['user_name']!r}")
    if r['extra_data']:
        print(f"      extra_data: {str(r['extra_data'])[:200]}")
    if r['error_message']:
        print(f"      error_message: {str(r['error_message'])[:200]}")

# 7. 推断根因
print(f"\n[7] 根因分析:")
unknown_by_type = {}
cur.execute("""
    SELECT object_type, COUNT(*) as cnt
    FROM audit_logs
    WHERE action = 'UNKNOWN'
    GROUP BY object_type
""")
for r in cur.fetchall():
    unknown_by_type[r['object_type']] = r['cnt']

# 检查是否全是 __audit_failure__
if unknown_by_type.get('__audit_failure__', 0) > total * 0.9:
    print(f"   -> 99% UNKNOWN 来自 __audit_failure__ 内部记录")
    print(f"   -> 建议: 这些是 async_audit_writer fallback, 应该用 'AUDIT_WRITE_FAILED' 标记")
else:
    # 找出 object_type 分布
    top_types = list(unknown_by_type.items())[:3]
    for obj_type, cnt in top_types:
        if cnt > 100:
            print(f"   -> {obj_type}: {cnt} 条 - 排查 {obj_type} 的写入路径")

# 8. 业务影响
print(f"\n[8] 业务影响:")
print(f"   - 业务人员看到 '未识别操作' 标签: {total} 次")
print(f"   - 影响 {len(unknown_by_type)} 种 object_type")
print(f"   - 影响 {sum(1 for _ in cur.execute('SELECT DISTINCT user_name FROM audit_logs WHERE action = \"UNKNOWN\"'))} 个用户")

# 9. 推荐修复
print(f"\n[9] 推荐修复 (E.2):")
print(f"   a) action_executor.execute() 添加 assertion: action 不能为空")
print(f"   b) async_audit_writer fallback: 强制 action='AUDIT_WRITE_FAILED'")
print(f"   c) 历史 UNKNOWN 归档: 7 天前的 UNKNOWN 移到 audit_logs_archive")
print(f"   d) 业务视图: 隐藏 UNKNOWN action, 用 '内部审计' 替代显示")

conn.close()
print(f"\n[DONE]")