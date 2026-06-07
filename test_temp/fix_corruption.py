#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 scheduled_tasks 索引"""
import sqlite3
import shutil
from pathlib import Path

db_path = Path(r'd:\filework\excel-to-diagram\meta\architecture.db')
backup = db_path.with_suffix('.db.bak.fix')

# 1. 备份
shutil.copy2(str(db_path), str(backup))
print(f"[OK] Backed up to {backup}")

# 2. REINDEX scheduled_tasks
conn = sqlite3.connect(str(db_path), timeout=30)
try:
    conn.execute("REINDEX scheduled_tasks")
    conn.commit()
    print("[OK] REINDEX scheduled_tasks done")
except Exception as e:
    print(f"[!] REINDEX failed: {e}")
    raise

# 3. 验证
result = conn.execute('PRAGMA integrity_check').fetchone()
print(f"After REINDEX: {result[0][:100]}")
conn.close()
