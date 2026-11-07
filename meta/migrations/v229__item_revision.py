# -*- coding: utf-8 -*-
"""[v229 2026-11-07] 主数据版本：items 补 revision_no

依据:
  docs/specs/bo-metadata-gap-2026-11-06（T8.3-b 收敛决策，2026-11-07）
  「revision 只用于主数据（item），其他单据暂不启用」
  schema 声明见 meta/schemas/items.yaml（revision_no 字段 + revision_policy）

范围:
  1. items 补 revision_no INTEGER NOT NULL DEFAULT 1（存在则 SKIP）
  2. 建索引 idx_items_revision_no（幂等）

回滚:
  只删索引；列保留（SQLite ALTER 无法安全回退，且旧代码可忽略该列）。
"""
import sqlite3
import sys
from pathlib import Path

MIGRATION_NAME = 'v229__item_revision'

TABLE = 'items'
COLUMN = 'revision_no'
INDEX = 'idx_items_revision_no'


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _index_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn, table):
    return {r[1] for r in conn.execute("PRAGMA table_info({0})".format(table)).fetchall()}


def migrate(db_path, skip_backup=False):
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError('数据库不存在: {0}'.format(db_path))

    if not skip_backup:
        backup = db_path.with_suffix(db_path.suffix + '.bak_v229')
        if not backup.exists():
            import shutil
            shutil.copy2(str(db_path), str(backup))
            print('[v229] 备份: {0}'.format(backup))

    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print('[v229] [SKIP] 表 {0} 不存在'.format(TABLE))
            return

        if COLUMN in _columns(conn, TABLE):
            print('[v229] [SKIP] {0}.{1} 已存在'.format(TABLE, COLUMN))
        else:
            conn.execute(
                "ALTER TABLE {0} ADD COLUMN {1} INTEGER NOT NULL DEFAULT 1".format(
                    TABLE, COLUMN)
            )
            print('[v229] ADD COLUMN {0}.{1}'.format(TABLE, COLUMN))

        if _index_exists(conn, INDEX):
            print('[v229] [SKIP] 索引 {0} 已存在'.format(INDEX))
        else:
            conn.execute(
                "CREATE INDEX {0} ON {1}({2})".format(INDEX, TABLE, COLUMN)
            )
            print('[v229] CREATE INDEX {0}'.format(INDEX))

        conn.commit()
    finally:
        conn.close()


def verify(db_path):
    conn = sqlite3.connect(str(Path(db_path)))
    try:
        if not _table_exists(conn, TABLE):
            return {'ok': False, 'error': '表 {0} 不存在'.format(TABLE)}
        if COLUMN not in _columns(conn, TABLE):
            return {'ok': False, 'error': '列 {0}.{1} 缺失'.format(TABLE, COLUMN)}
        return {'ok': True, 'error': None}
    finally:
        conn.close()


def rollback(db_path):
    conn = sqlite3.connect(str(Path(db_path)))
    try:
        if _index_exists(conn, INDEX):
            conn.execute("DROP INDEX {0}".format(INDEX))
            print('[v229] DROP INDEX {0}'.format(INDEX))
        conn.commit()
        print('[v229] 列 {0}.{1} 保留（SQLite 限制）'.format(TABLE, COLUMN))
    finally:
        conn.close()


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    migrate(target)
    print(verify(target))
