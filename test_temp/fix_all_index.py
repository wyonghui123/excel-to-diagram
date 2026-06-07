#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量 REINDEX 所有索引"""
import sqlite3
from pathlib import Path

db_path = Path(r'd:\filework\excel-to-diagram\meta\architecture.db')

conn = sqlite3.connect(str(db_path), timeout=30)

# 1. 获取所有索引名
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
indexes = [r[0] for r in cur.fetchall()]
print(f"Found {len(indexes)} indexes")

# 2. 逐个 REINDEX
fixed = 0
for idx in indexes:
    try:
        conn.execute(f"REINDEX {idx}")
        conn.commit()
    except Exception as e:
        print(f"[!] REINDEX {idx} failed: {e}")
    else:
        # 检查是否还有错
        result = conn.execute('PRAGMA integrity_check').fetchone()
        if '***' in result[0]:
            print(f"[!] {idx}: still corrupt")
        else:
            print(f"[OK] {idx}: integrity OK")
            fixed += 1
            break  # 修好了

print(f"\nFixed: {fixed}/{len(indexes)}")
print(f"Final: {result[0][:200]}")
conn.close()
