# -*- coding: utf-8 -*-
"""[v229] 删除 permission_sets.priority 遗留列

依据:
  spec-auth-object-category-v2-2026-06-10.md FR-V1-001
  （V1 简化：permission_set 不再有 priority / is_super_admin）

背景:
  meta/schemas/permission_set.yaml 已移除 priority 字段，
  但存量库 permission_sets 表仍保留该列（schema 漂移），
  导致 /api/v1/permission-sets 响应继续返回 priority。

幂等:
  列存在才 DROP；重复执行打印 [SKIP]。SQLite < 3.35 不支持 DROP COLUMN
  时打印 [KEEP] 并保留（不影响启动）。

回滚:
  重新 ADD COLUMN priority INTEGER DEFAULT 0。
"""
import sqlite3
from pathlib import Path

TABLE = 'permission_sets'
COLUMN = 'priority'


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """migration_runner 以 migrate(db_path, skip_backup=True) 调用。"""
    if not db_path.exists():
        print(f'[v229] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v229] 开始: 删除 permission_sets.priority')
        if COLUMN not in _columns(conn, TABLE):
            print(f'  - [SKIP] {TABLE}.{COLUMN} 不存在')
            return True
        try:
            conn.execute(f'ALTER TABLE {TABLE} DROP COLUMN {COLUMN}')
            print(f'  - [DROP] {TABLE}.{COLUMN}')
        except sqlite3.OperationalError as e:
            print(f'  - [KEEP] 当前 SQLite 不支持 DROP COLUMN: {e}')
        conn.commit()
        print('[v229] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v229] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v229 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = COLUMN not in _columns(conn, TABLE)
        print('[v229 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v229 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if COLUMN in _columns(conn, TABLE):
            print(f'  - [SKIP] {TABLE}.{COLUMN} 已存在')
        else:
            conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} INTEGER DEFAULT 0')
            print(f'  - [ADD] {TABLE}.{COLUMN}')
        conn.commit()
        return True
    finally:
        conn.close()
