#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 baseline 恢复 architecture.db"""
import shutil
from pathlib import Path

baseline = Path(r'd:\filework\excel-to-diagram\meta\architecture.db.baseline')
corrupted = Path(r'd:\filework\excel-to-diagram\meta\architecture.db')
wal = corrupted.with_suffix('.db-wal')
shm = corrupted.with_suffix('.db-shm')

# 1. 备份当前损坏 DB
corrupted_backup = corrupted.with_suffix('.db.corrupt-final')
shutil.copy2(str(corrupted), str(corrupted_backup))
print(f"[OK] Backed up corrupted DB to {corrupted_backup}")

# 2. 删除 WAL/SHM（baseline 没有）
if wal.exists():
    wal.unlink()
    print(f"[OK] Removed {wal.name}")
if shm.exists():
    shm.unlink()
    print(f"[OK] Removed {shm.name}")

# 3. 复制 baseline → 主 DB
shutil.copy2(str(baseline), str(corrupted))
print(f"[OK] Restored {corrupted} from baseline")

# 4. 验证
import sqlite3
conn = sqlite3.connect(str(corrupted), timeout=5)
result = conn.execute('PRAGMA integrity_check').fetchone()
print(f"\nintegrity_check: {result[0]}")
print(f"Size: {corrupted.stat().st_size:,} bytes")

# 关键表数据
for table in ['users', 'products', 'versions', 'business_objects', 'audit_logs', 'scheduled_tasks']:
    try:
        count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        print(f"  {table}: {count} rows")
    except Exception as e:
        print(f"  {table}: ERROR {e}")

conn.close()
