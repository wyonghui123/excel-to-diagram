#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 DB 健康状态"""
import sqlite3
from pathlib import Path

db_path = Path(r'd:\filework\excel-to-diagram\meta\architecture.db')
print(f"=== {db_path} ===")
print(f"Size: {db_path.stat().st_size:,} bytes")

# WAL
wal = db_path.with_suffix('.db-wal')
shm = db_path.with_suffix('.db-shm')
print(f"WAL: {wal.stat().st_size:,} bytes" if wal.exists() else "WAL: not exists")
print(f"SHM: {shm.stat().st_size:,} bytes" if shm.exists() else "SHM: not exists")

# Open and check
conn = sqlite3.connect(str(db_path), timeout=5)
try:
    result = conn.execute('PRAGMA integrity_check').fetchone()
    print(f"\nPRAGMA integrity_check: {result[0]}")
except Exception as e:
    print(f"\n[!] Cannot open DB: {e}")
    raise

# Journal mode
journal = conn.execute('PRAGMA journal_mode').fetchone()
print(f"journal_mode: {journal[0]}")

# WAL checkpoint
wal_state = conn.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
print(f"wal_checkpoint: busy={wal_state[0]} log_frames={wal_state[1]} checkpointed_frames={wal_state[2]}")

# _bak_ tables
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '\\_bak\\_%' ESCAPE '\\'")
baks = [r[0] for r in cur.fetchall()]
print(f"\n_bak_ residual tables: {len(baks)}")
for b in baks[:10]:
    print(f"  - {b}")

# sqlite_master corruption check
cur = conn.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")
objects = cur.fetchall()
print(f"\nObjects: {len(objects)}")
for typ, name in objects[:10]:
    print(f"  {typ}: {name}")

conn.close()
