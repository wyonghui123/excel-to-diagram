#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用 sqlite3 .recover 从损坏 DB 恢复数据"""
import sqlite3
import shutil
from pathlib import Path

corrupted = Path(r'd:\filework\excel-to-diagram\meta\architecture.db')
recovered = Path(r'd:\filework\excel-to-diagram\meta\architecture_recovered2.db')

if recovered.exists():
    recovered.unlink()

# sqlite3.connect() 可以连接损坏的 DB
src = sqlite3.connect(str(corrupted), timeout=30)
try:
    # 提取 SQL dump
    for line in src.iterdump():
        pass  # 只为触发读
except Exception as e:
    print(f"iterdump failed: {e}")

# 用 .recover
try:
    cursor = src.cursor()
    cursor.execute(".recover")
    sql_text = cursor.fetchone()
    if sql_text:
        print(f"Got {len(sql_text[0])} chars of recovery SQL")
        Path(r'd:\filework\excel-to-diagram\test_temp\recover.sql').write_text(sql_text[0], encoding='utf-8')
        print("Saved to recover.sql")
except Exception as e:
    print(f".recover failed: {e}")

src.close()

# 试 dump
print("\n=== Try .dump (ignore errors) ===")
src = sqlite3.connect(str(corrupted), timeout=30)
dump_lines = []
try:
    for line in src.iterdump():
        dump_lines.append(line)
except Exception as e:
    print(f"iterdump stopped at: {e}, got {len(dump_lines)} lines")
src.close()

if dump_lines:
    print(f"Got {len(dump_lines)} dump lines")
    Path(r'd:\filework\excel-to-diagram\test_temp\dump.sql').write_text('\n'.join(dump_lines), encoding='utf-8')
    print("Saved to dump.sql")
