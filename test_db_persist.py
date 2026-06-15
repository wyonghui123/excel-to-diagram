# -*- coding: utf-8 -*-
"""直接测试 SQLite DDL 持久化"""
import sqlite3
import os

DB = 'd:/filework/excel-to-diagram/meta/architecture.db'
SHADOW = 'd:/filework/excel-to-diagram/meta/_test_owner.db'

def main():
    # 复制原 DB 到测试 DB
    import shutil
    shutil.copy2(DB, SHADOW)
    print(f'Copied to {SHADOW}')

    # 检查文件大小
    print(f'Original DB size: {os.path.getsize(DB)} bytes')
    print(f'Shadow DB size: {os.path.getsize(SHADOW)} bytes')

    # 修改 shadow DB
    conn = sqlite3.connect(SHADOW)
    print('\n--- Before drop ---')
    cursor = conn.execute('PRAGMA table_info(versions)')
    cols = [r[1] for r in cursor.fetchall()]
    print(f'versions cols: {cols}')

    # Drop owner_id from versions
    conn.execute('PRAGMA foreign_keys=OFF')

    # 用 12-step
    cur = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='versions'")
    create_sql = cur.fetchone()[0]
    print(f'\nCreate SQL:\n{create_sql}')

    new_table = '_test_v_new'

    # 简单 drop owner_id
    cur = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='versions'")
    sql = cur.fetchone()[0]

    # 替换 owner_id
    import re
    # 找 owner_id 行
    new_sql = re.sub(r'^\s*owner_id\s+INTEGER,?\s*$', '', sql, flags=re.MULTILINE)
    new_sql = new_sql.replace('versions', new_table)

    print(f'\nNew SQL:\n{new_sql[:500]}')

    conn.execute(new_sql)
    conn.execute(f'INSERT INTO {new_table} SELECT * FROM versions')
    conn.execute('DROP TABLE versions')
    conn.execute(f'ALTER TABLE {new_table} RENAME TO versions')
    conn.commit()

    print('\n--- After drop ---')
    cursor = conn.execute('PRAGMA table_info(versions)')
    cols = [r[1] for r in cursor.fetchall()]
    print(f'versions cols: {cols}')

    conn.close()

    # 重新打开看持久化
    print('\n--- Re-open DB to check persistence ---')
    conn2 = sqlite3.connect(SHADOW)
    cursor = conn2.execute('PRAGMA table_info(versions)')
    cols = [r[1] for r in cursor.fetchall()]
    print(f'versions cols (re-opened): {cols}')
    conn2.close()

    # 清理
    os.remove(SHADOW)
    print(f'\nCleaned up {SHADOW}')

if __name__ == '__main__':
    main()
