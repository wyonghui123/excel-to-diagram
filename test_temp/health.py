#!/usr/bin/env python3
"""检查 DB 健康"""
import sqlite3
import os

db = r'd:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db, timeout=5)
result = conn.execute('PRAGMA integrity_check').fetchone()
print(f'integrity_check: {result[0]}')
wal_state = conn.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
print(f'wal: busy={wal_state[0]} frames={wal_state[1]} checkpointed={wal_state[2]}')
print(f'Size: {os.path.getsize(db):,}')
wal = db + '-wal'
if os.path.exists(wal):
    print(f'WAL: {os.path.getsize(wal):,}')
conn.close()
