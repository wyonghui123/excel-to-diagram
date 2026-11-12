# -*- coding: utf-8 -*-
"""[v184 2026-11-01] 工单工序补作业定义溯源（项目侧 G12）

依据:
  docs/specs/spec-project-type-object-model-research-2026-10-31.md §3 G12 / D4
  docs/specs/tasks-project-g12-g13-execution-boundary-2026-11-01.md P1

口径:
  · 给 `work_order_operations` 补可空 `work_definition_id` /
    `work_definition_operation_id`：工序能说明「照哪条工艺路线第几步」
  · 空值 = 手填工序（保留手填覆盖能力，不改既有数据）
  · 不加真外键：SQLite 不支持对存量表 ALTER 加 FK；删除保护由
    `work_definition_operation.deletion_policy`（restrict）承担
  · 只补参数列，**不触碰执行通道**（G13 仍待定界）

幂等:
  列 / 索引先查后用；重复执行打印 [SKIP]。

回滚:
  删两个索引；**保留**列（SQLite 删列不可逆，空值不影响旧链路）。
"""
import sqlite3
import sys
from pathlib import Path

OPERATION_TABLE = 'work_order_operations'
DEFINITION_COLUMN = 'work_definition_id'
DEFINITION_OP_COLUMN = 'work_definition_operation_id'

COLUMNS = (
    (DEFINITION_COLUMN, 'INTEGER NULL'),
    (DEFINITION_OP_COLUMN, 'INTEGER NULL'),
)

INDEXES = (
    ('idx_work_order_operation_definition', DEFINITION_COLUMN),
    ('idx_work_order_operation_definition_op', DEFINITION_OP_COLUMN),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute('PRAGMA table_info({0})'.format(table))}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _do_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, OPERATION_TABLE):
        print('  - [SKIP] 表 {0} 不存在'.format(OPERATION_TABLE))
        return
    existing = _columns(conn, OPERATION_TABLE)
    for column, ddl in COLUMNS:
        if column in existing:
            print('  - [SKIP] 列 {0}.{1} 已存在'.format(OPERATION_TABLE, column))
            continue
        conn.execute('ALTER TABLE {0} ADD COLUMN {1} {2}'.format(
            OPERATION_TABLE, column, ddl))
        print('  - [ALTER] 列 {0}.{1}'.format(OPERATION_TABLE, column))


def _do_indexes(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, OPERATION_TABLE):
        print('  - [SKIP] 索引依赖表不存在')
        return
    existing = _columns(conn, OPERATION_TABLE)
    for name, column in INDEXES:
        if column not in existing:
            print('  - [SKIP] 索引 {0} 依赖列不存在'.format(name))
            continue
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 {0} 已存在'.format(name))
            continue
        conn.execute(
            'CREATE INDEX IF NOT EXISTS {0} ON {1}({2})'.format(
                name, OPERATION_TABLE, column))
        print('  - [ADD] 索引 {0}'.format(name))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v184] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v184] 开始: 工单工序补作业定义溯源（G12）')
        _do_columns(conn)
        _do_indexes(conn)
        conn.commit()
        print('[v184] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v184] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v184 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, OPERATION_TABLE):
            print('[v184 verify] FAIL: 缺表 {0}'.format(OPERATION_TABLE))
            ok = False
        else:
            existing = _columns(conn, OPERATION_TABLE)
            for column, _ in COLUMNS:
                if column not in existing:
                    print('[v184 verify] FAIL: 缺列 {0}.{1}'.format(
                        OPERATION_TABLE, column))
                    ok = False
            for name, _ in INDEXES:
                if not _index_exists(conn, name):
                    print('[v184 verify] FAIL: 缺索引 {0}'.format(name))
                    ok = False
        print('[v184 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v184 rollback] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _ in INDEXES:
            if _index_exists(conn, name):
                conn.execute('DROP INDEX IF EXISTS {0}'.format(name))
                print('  - [DROP] 索引 {0}'.format(name))
        conn.commit()
        print('[v184 rollback] 完成（溯源列保留）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v184 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)
