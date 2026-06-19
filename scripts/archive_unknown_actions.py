#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[E.2] 归档脚本: 把 7 天前的 UNKNOWN 记录移到 audit_logs_archive

效果:
- 业务视图 UNKNOWN 数量 < 100
- 历史 UNKNOWN 仍可查 (在 archive 表)
- 不影响新数据 (E.2 已加 action 校验)
"""
import sqlite3
import os
import sys
from datetime import datetime

DB_PATH = "meta/architecture.db"

if not os.path.exists(DB_PATH):
    print(f"[ERROR] DB not found: {DB_PATH}")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. 备份
import shutil
BACKUP_PATH = f"meta/architecture.db.backup_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
print(f"[1/4] Backing up to {BACKUP_PATH}")
shutil.copy2(DB_PATH, BACKUP_PATH)
print(f"   [OK] Done")

# 2. 创建 archive 表 (如果不存在)
cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs_archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_id INTEGER,
        created_at TEXT,
        object_type TEXT,
        object_id TEXT,
        action TEXT,
        field_name TEXT,
        old_value TEXT,
        new_value TEXT,
        user_id TEXT,
        user_name TEXT,
        ip_address TEXT,
        user_agent TEXT,
        trace_id TEXT,
        transaction_id TEXT,
        parent_object_type TEXT,
        parent_object_id TEXT,
        extra_data TEXT,
        archived_at TEXT,
        archive_reason TEXT
    )
""")
print(f"   [OK] audit_logs_archive table ready")

# 3. 移动 7 天前的 UNKNOWN
print(f"\n[2/4] Moving UNKNOWN records older than 7 days")
cur.execute("""
    SELECT COUNT(*) FROM audit_logs
    WHERE action = 'UNKNOWN'
      AND DATE(created_at) < DATE('now', '-7 days')
""")
to_move = cur.fetchone()[0]
print(f"   Records to move: {to_move}")

if to_move > 0:
    # 复制到 archive
    cur.execute("""
        INSERT INTO audit_logs_archive (
            original_id, created_at, object_type, object_id, action,
            field_name, old_value, new_value,
            user_id, user_name, ip_address, user_agent,
            trace_id, transaction_id,
            parent_object_type, parent_object_id, extra_data,
            archived_at, archive_reason
        )
        SELECT
            id, created_at, object_type, object_id, action,
            field_name, old_value, new_value,
            user_id, user_name, ip_address, user_agent,
            trace_id, transaction_id,
            parent_object_type, parent_object_id, extra_data,
            ?, ?
        FROM audit_logs
        WHERE action = 'UNKNOWN'
          AND DATE(created_at) < DATE('now', '-7 days')
    """, (datetime.now().isoformat(), 'E.2: UNKNOWN action archive 7d+'))

    print(f"   Copied {to_move} to archive")

    # 从 audit_logs 删除
    cur.execute("""
        DELETE FROM audit_logs
        WHERE action = 'UNKNOWN'
          AND DATE(created_at) < DATE('now', '-7 days')
    """)
    print(f"   Deleted {to_move} from audit_logs")

# 4. 验证
print(f"\n[3/4] Verification")
cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'UNKNOWN'")
print(f"   Remaining UNKNOWN: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM audit_logs_archive")
print(f"   Total in archive: {cur.fetchone()[0]}")

conn.commit()
conn.close()
print(f"\n[DONE]")