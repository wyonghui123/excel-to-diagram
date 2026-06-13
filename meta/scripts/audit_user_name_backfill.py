#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_user_name_backfill.py — 历史 user_name 标准化 (FR-006)

策略:
  - 当前 user_name 已经是 "V3.17 Test" 这种 (只有 display_name, 没 username 括号)
  - 或者 "admin" 这种纯 username
  - 目标: 标准化为 "display_name (username)"

实际可行方案:
  - 简单清洗: 把 "V3.17 Test" (我们刚清的那种) 删了, 已经是 Step 4 做了
  - 对剩余的: 如果 user_name 不含 "(", 把它作为 username, 查询 users 表拿 display_name
  - 如果 user_id 在 users 存在, 用 display_name; 不存在保留原 user_name
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB = Path(__file__).parent.parent / "architecture.db"


def backfill():
    conn = sqlite3.connect(str(DB))
    try:
        # 1. 找 user_name 不含括号 且 user_id > 0 的记录
        cur = conn.execute("""
            SELECT id, user_id, user_name
            FROM audit_logs
            WHERE user_name IS NOT NULL
              AND user_name != ''
              AND user_name NOT LIKE '%(%'
              AND user_id IS NOT NULL AND user_id != '' AND user_id != '0'
        """)
        rows = cur.fetchall()
        print(f"  [STATS] 待处理: {len(rows)} 条 (user_name 不含括号)")

        # 2. 拉所有 users (id, username, display_name) 用于查找
        cur = conn.execute("SELECT id, username, display_name FROM users")
        users_map = {r[0]: {"username": r[1] or "", "display_name": r[2] or ""} for r in cur.fetchall()}

        updated = 0
        skipped = 0
        for rid, uid, uname in rows:
            try:
                uid_int = int(uid) if isinstance(uid, (str, int)) else 0
            except Exception:
                skipped += 1
                continue
            u = users_map.get(uid_int)
            if not u:
                skipped += 1
                continue
            username = u["username"]
            display = u["display_name"]
            # 标准化: 跟 audit_constants.normalize_user_name 一致
            if not display or display == username:
                new_name = username or uname
            else:
                new_name = f"{display} ({username})"
            if new_name and new_name != uname:
                conn.execute("UPDATE audit_logs SET user_name=? WHERE id=?", (new_name, rid))
                updated += 1
        conn.commit()
        print(f"  [DONE] updated={updated}, skipped={skipped}")

        # 3. 验证: 100% 含括号 (除了 anonymous / username-only)
        cur = conn.execute("""
            SELECT COUNT(*) FROM audit_logs
            WHERE user_name IS NOT NULL AND user_name != ''
              AND user_name NOT LIKE '%(%'
              AND user_id IS NOT NULL AND user_id != '' AND user_id != '0'
        """)
        remain = cur.fetchone()[0]
        print(f"  [VERIFY] 仍不含括号: {remain} 条 (应是 0 或只有 anonymous)")
    finally:
        conn.close()


if __name__ == "__main__":
    backfill()
