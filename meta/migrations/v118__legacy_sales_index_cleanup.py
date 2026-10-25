# -*- coding: utf-8 -*-
"""[v118 2026-10-25] 清理由对象级泛化遗留的 sales_ 前缀索引名

背景:
  v114 把 control_parameter_values 的列 sales_document_type_id / sales_line_type_id
  改名为 document_type_id / line_type_id；v115 把表 sales_line_type_assignments
  改名为 line_type_assignments。
  SQLite 的 RENAME COLUMN / RENAME TO 只改列名与表名，**不重命名索引**，
  于是四个改名之前建的索引仍带 sales_ 前缀。

处置明细:
  control_parameter_values
    idx_control_parameter_values_sales_document_type_id
        -> idx_control_parameter_values_document_type_id   (DROP + CREATE，保留覆盖)
    idx_control_parameter_values_sales_line_type_id
        -> idx_control_parameter_values_line_type_id       (DROP + CREATE，保留覆盖)
  line_type_assignments
    idx_sales_line_type_assignments_item_group_id
        -> 直接 DROP（等价的 idx_line_type_assignments_item_group_id 已存在）
    idx_sales_line_type_assignments_sales_line_type_id
        -> idx_line_type_assignments_line_type_id          (DROP + CREATE，保留覆盖)

  这三个 RENAME 项必须"先建后删"吗? 不需要 —— 索引不承载数据，
  同列新旧两个索引并存一瞬无副作用，这里统一按"先删旧、后建新"处理，
  并用 _index_exists 保证幂等。

幂等:
  每一步都先查 sqlite_master，重复执行无副作用。

回滚:
  删除新名索引，按原列恢复旧名索引。
"""
import sqlite3
from pathlib import Path

# (表名, 旧索引名, 新索引名, 索引列)
RENAMES = (
    ('control_parameter_values',
     'idx_control_parameter_values_sales_document_type_id',
     'idx_control_parameter_values_document_type_id',
     'document_type_id'),
    ('control_parameter_values',
     'idx_control_parameter_values_sales_line_type_id',
     'idx_control_parameter_values_line_type_id',
     'line_type_id'),
    ('line_type_assignments',
     'idx_sales_line_type_assignments_sales_line_type_id',
     'idx_line_type_assignments_line_type_id',
     'line_type_id'),
)

# (表名, 旧索引名, 索引列) —— 已有等价新名索引，直接删除
DROP_ONLY = (
    ('line_type_assignments',
     'idx_sales_line_type_assignments_item_group_id',
     'item_group_id'),
)

LEGACY_INDEXES = tuple(r[1] for r in RENAMES) + tuple(d[1] for d in DROP_ONLY)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _create_index(conn: sqlite3.Connection, name: str, table: str, column: str) -> None:
    conn.execute('CREATE INDEX "%s" ON "%s"(%s)' % (name, table, column))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v118] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v118] 开始: 清理 sales_ 前缀索引名')
        for table, old, new, column in RENAMES:
            if not _table_exists(conn, table):
                print('  - 表 %s 不存在, 跳过 %s' % (table, old))
                continue
            if _index_exists(conn, old):
                conn.execute('DROP INDEX "%s"' % old)
                print('  - DROP %s' % old)
            if not _index_exists(conn, new):
                _create_index(conn, new, table, column)
                print('  - CREATE %s ON %s(%s)' % (new, table, column))
        for table, old, column in DROP_ONLY:
            if not _table_exists(conn, table):
                print('  - 表 %s 不存在, 跳过 %s' % (table, old))
                continue
            if _index_exists(conn, old):
                conn.execute('DROP INDEX "%s"' % old)
                print('  - DROP %s (等价索引已存在)' % old)
        conn.commit()
        print('[v118] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v118] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v118 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        live = [n for n in LEGACY_INDEXES if _index_exists(conn, n)]
        if live:
            print('[v118 verify] FAIL: 旧索引仍存在 %s' % live)
            return False
        missing = [n for _, _, n, _ in RENAMES if not _index_exists(conn, n)]
        if missing:
            print('[v118 verify] FAIL: 新索引缺失 %s' % missing)
            return False
        print('[v118 verify] OK: 旧索引已清理，新索引已就位')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v118 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for table, old, new, column in RENAMES:
            if not _table_exists(conn, table):
                continue
            if _index_exists(conn, new):
                conn.execute('DROP INDEX "%s"' % new)
            if not _index_exists(conn, old):
                conn.execute('CREATE INDEX "%s" ON "%s"(%s)' % (old, table, column))
        for table, old, column in DROP_ONLY:
            if not _table_exists(conn, table):
                continue
            if not _index_exists(conn, old):
                conn.execute('CREATE INDEX "%s" ON "%s"(%s)' % (old, table, column))
        conn.commit()
        print('[v118 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v118 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else get_meta_db_path()
    if '--rollback' in sys.argv:
        rollback(db)
    else:
        migrate(db)
        verify(db)
