#!/usr/bin/env python3
"""[FIX 2026-06-24] 修正 log_category='workflow' 非法值 → 'business'.

背景: SUBFLOW 动作被错误分类为 'workflow' (非标准枚举).
      标准枚举只有: business, security, authz, access, admin, system, cascade.
"""
import sqlite3

DB = r'd:/filework/excel-to-diagram/meta/architecture.db'
con = sqlite3.connect(DB)
cur = con.cursor()

cur.execute("""
  UPDATE audit_logs
  SET log_category = 'business'
  WHERE log_category = 'workflow'
""")
updated = cur.rowcount
con.commit()
print(f"[Cleanup] Updated {updated} records: log_category 'workflow' -> 'business'")

cur.execute("SELECT COUNT(*) FROM audit_logs WHERE log_category NOT IN ('business', 'security', 'authz', 'access', 'admin', 'system', 'cascade')")
remaining = cur.fetchone()[0]
print(f"[Verify] Remaining non-standard category records: {remaining}")
con.close()
