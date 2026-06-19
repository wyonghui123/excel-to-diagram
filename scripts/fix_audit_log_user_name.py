#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[D.1] 数据修复脚本: 统一 audit_logs.user_name

问题:
  - 同一人有多个名称: "Admin (admin)", "系统管理员", "admin", "Self Updated Name (admin)"
  - 业务人员看到 5 个不同的人名, 实际是 1-2 个真实用户

解决:
  - 优先用 users.display_name, 缺失时用 username, 最后 user_id
  - 一次性数据修复, 不影响新数据 (新数据由 D.2 interceptor 规范化)
"""
import sqlite3
import sys
import os
from datetime import datetime
from collections import defaultdict

DB_PATH = "meta/architecture.db"

# 备份路径
BACKUP_PATH = f"meta/architecture.db.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB not found: {DB_PATH}")
        sys.exit(1)

    # 备份
    print(f"[1/4] Backing up DB to {BACKUP_PATH}")
    import shutil
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"   [OK] Backup done")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 查询所有 user 的 display_name
    print(f"\n[2/4] Loading user display_name map")
    cur.execute("""
        SELECT id, display_name, username, COALESCE(email, '') as email
        FROM users
    """)
    user_map = {}
    for r in cur.fetchall():
        # 优先级: display_name > username > email 前缀
        canonical = r['display_name'] or r['username']
        if not canonical and r['email']:
            canonical = r['email'].split('@')[0]
        if not canonical:
            canonical = f"user_{r['id']}"
        user_map[str(r['id'])] = canonical

    print(f"   [OK] Loaded {len(user_map)} users")
    for uid, name in list(user_map.items())[:5]:
        print(f"   - user_id={uid} -> '{name}'")

    # 统计当前 user_name 分布
    print(f"\n[3/4] Analyzing current user_name distribution")
    cur.execute("""
        SELECT user_name, COUNT(*) as cnt
        FROM audit_logs
        GROUP BY user_name
        ORDER BY cnt DESC
    """)
    print(f"   Current unique user_name values:")
    for r in cur.fetchall():
        print(f"   - {r['user_name']!r:40s} {r['cnt']:5d}")

    # 修复: 关联 user_id, 把 user_name 改为 canonical
    print(f"\n[4/4] Fixing user_name based on user_id")
    updates = 0
    updates_by_user = defaultdict(int)
    for user_id, canonical in user_map.items():
        # 修复逻辑:
        # 1. user_id 匹配 + user_name != canonical
        # 2. 也要修复 user_id 为空/0 但 user_name 包含 user_id 的情况 (例如 "Admin (admin)" -> "系统管理员")
        cur.execute("""
            UPDATE audit_logs
            SET user_name = ?
            WHERE user_id = ?
              AND (user_name IS NULL
                   OR user_name != ?
                   OR user_name LIKE '(%'   -- '(admin)' 等括号形式
                   OR user_name LIKE '%)%'  -- 'Admin (admin)' 等带括号
                   OR user_name LIKE '% (%' -- 'Self Updated Name (admin)'
                   )
        """, (canonical, user_id, canonical))
        if cur.rowcount > 0:
            updates += cur.rowcount
            updates_by_user[canonical] += cur.rowcount

    # 处理 system 用户 (user_id=0 / NULL)
    cur.execute("""
        UPDATE audit_logs
        SET user_name = 'system'
        WHERE (user_id IS NULL OR user_id = '0' OR user_id = 0)
          AND (user_name IS NULL OR user_name = '' OR user_name != 'system')
    """)
    if cur.rowcount > 0:
        updates += cur.rowcount
        updates_by_user['system'] += cur.rowcount

    # [FIX 2026-06-19] 处理 'unknown' / 'guest' 等残留
    cur.execute("""
        UPDATE audit_logs
        SET user_name = 'system'
        WHERE user_name IN ('unknown', 'guest', 'anonymous', 'Anonymous')
          AND user_name != 'system'
    """)
    if cur.rowcount > 0:
        updates += cur.rowcount
        updates_by_user['system (from unknown/guest)'] += cur.rowcount

    # [FIX 2026-06-19] 处理 lowercase 'admin' (应该是 'Admin' 大写)
    cur.execute("""
        UPDATE audit_logs
        SET user_name = 'Admin'
        WHERE user_name = 'admin'
    """)
    if cur.rowcount > 0:
        updates += cur.rowcount
        updates_by_user['Admin (from admin)'] += cur.rowcount

    # [FIX 2026-06-19] 处理空字符串 (应该是 'system')
    cur.execute("""
        UPDATE audit_logs
        SET user_name = 'system'
        WHERE user_name = '' OR user_name IS NULL
    """)
    if cur.rowcount > 0:
        updates += cur.rowcount
        updates_by_user['system (from empty)'] += cur.rowcount

    conn.commit()

    print(f"\n[OK] Total updated: {updates} records")
    print(f"   By user:")
    for name, cnt in sorted(updates_by_user.items(), key=lambda x: -x[1]):
        print(f"   - {name:30s} {cnt:5d}")

    # 验证
    cur.execute("""
        SELECT user_name, COUNT(*) as cnt
        FROM audit_logs
        GROUP BY user_name
        ORDER BY cnt DESC
    """)
    print(f"\n[VERIFY] After fix - unique user_name values:")
    for r in cur.fetchall():
        print(f"   - {r['user_name']!r:40s} {r['cnt']:5d}")

    conn.close()
    print(f"\n[DONE] DB: {DB_PATH}")
    print(f"[DONE] Backup: {BACKUP_PATH}")


if __name__ == '__main__':
    main()