#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 baseline 是否完好"""
import sqlite3
from pathlib import Path

baseline = Path(r'd:\filework\excel-to-diagram\meta\architecture.db.baseline')
print(f"=== {baseline} ===")
print(f"Size: {baseline.stat().st_size:,}")

conn = sqlite3.connect(str(baseline), timeout=5)
result = conn.execute('PRAGMA integrity_check').fetchone()
print(f"integrity_check: {result[0][:100]}")

# 关键表
for table in ['users', 'products', 'business_objects', 'audit_logs', 'scheduled_tasks']:
    try:
        count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        print(f"  {table}: {count} rows")
    except Exception as e:
        print(f"  {table}: ERROR {e}")

conn.close()
