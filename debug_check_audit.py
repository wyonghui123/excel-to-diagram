# -*- coding: utf-8 -*-
import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cur = conn.cursor()
cur.execute("SELECT id, object_type, object_id, action, error_message, created_at FROM audit_logs WHERE object_type='user_group' AND action='DELETE' ORDER BY created_at DESC LIMIT 10")
for row in cur.fetchall():
    print(row)

cur.execute("SELECT COUNT(*) FROM audit_logs WHERE object_type='user_group' AND action='DELETE'")
print('Total user_group DELETE logs:', cur.fetchone()[0])

cur.execute("PRAGMA table_info(audit_logs)")
print('audit_logs columns:')
for c in cur.fetchall():
    print(' -', c)
