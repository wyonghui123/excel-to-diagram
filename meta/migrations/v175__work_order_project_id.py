# -*- coding: utf-8 -*-
"""[v175 2026-11-01] 工单归集到项目（项目侧 P2 / B1）

依据:
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §0.1 P2
  docs/specs/spec-project-type-object-model-research-2026-10-31.md §2.2

设计:
  · 只做一件事：`work_orders` 增加可空 `project_id` + 过滤索引，
    使工单能进入项目 360 的履约段（project.yaml child_sections 原生过滤）
  · 列由 `meta/schemas/work_order.yaml` 声明、sync_schema 生成；
    本迁移对存量库补 ALTER COLUMN（与 v172 的 sales_order* 三处挂载同构）
  · 不声明 reference 关系、不加真外键：与 P1 三处挂载保持一致，
    避免「存量库有列无 FK / 全新建库有 FK」的双源漂移
  · 可空语义：空 = 未归集到项目，旧链路行为不变（工单不进入任何项目 360）

幂等:
  列 / 索引先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删索引；**保留** project_id 列（SQLite 删列不可逆，且空值不影响旧链路）。
"""
import sqlite3
import sys
from pathlib import Path

WORK_ORDER_TABLE = 'work_orders'
PROJECT_COLUMN = 'project_id'
PROJECT_INDEX = 'idx_work_order_project'

PROJECT_COLUMN_DDL = (
    'ALTER TABLE {0} ADD COLUMN {1} INTEGER NULL'.format(
        WORK_ORDER_TABLE, PROJECT_COLUMN)
)

INDEX_DDL = (
    'CREATE INDEX IF NOT EXISTS {0} ON {1}({2})'.format(
        PROJECT_INDEX, WORK_ORDER_TABLE, PROJECT_COLUMN)
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


def _do_column(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, WORK_ORDER_TABLE):
        print('  - [SKIP] 表 {0} 不存在（由工单波次迁移负责）'.format(WORK_ORDER_TABLE))
        return
    if PROJECT_COLUMN in _columns(conn, WORK_ORDER_TABLE):
        print('  - [SKIP] 列 {0}.{1} 已存在'.format(WORK_ORDER_TABLE, PROJECT_COLUMN))
        return
    conn.execute(PROJECT_COLUMN_DDL)
    print('  - [ALTER] 列 {0}.{1}'.format(WORK_ORDER_TABLE, PROJECT_COLUMN))


def _do_index(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, WORK_ORDER_TABLE):
        print('  - [SKIP] 索引 {0} 依赖表不存在'.format(PROJECT_INDEX))
        return
    if PROJECT_COLUMN not in _columns(conn, WORK_ORDER_TABLE):
        print('  - [SKIP] 索引 {0} 依赖列不存在'.format(PROJECT_INDEX))
        return
    if _index_exists(conn, PROJECT_INDEX):
        print('  - [SKIP] 索引 {0} 已存在'.format(PROJECT_INDEX))
        return
    conn.execute(INDEX_DDL)
    print('  - [ADD] 索引 {0}'.format(PROJECT_INDEX))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v175] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v175] 开始: 工单归集到项目（P2 B1）')
        _do_column(conn)
        _do_index(conn)
        conn.commit()
        print('[v175] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v175] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v175 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, WORK_ORDER_TABLE):
            print('[v175 verify] FAIL: 缺表 {0}'.format(WORK_ORDER_TABLE))
            ok = False
        else:
            if PROJECT_COLUMN not in _columns(conn, WORK_ORDER_TABLE):
                print('[v175 verify] FAIL: 缺列 {0}.{1}'.format(
                    WORK_ORDER_TABLE, PROJECT_COLUMN))
                ok = False
            if not _index_exists(conn, PROJECT_INDEX):
                print('[v175 verify] FAIL: 缺索引 {0}'.format(PROJECT_INDEX))
                ok = False
        print('[v175 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v175 rollback] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _index_exists(conn, PROJECT_INDEX):
            conn.execute('DROP INDEX IF EXISTS {0}'.format(PROJECT_INDEX))
            print('  - [DROP] 索引 {0}'.format(PROJECT_INDEX))
        conn.commit()
        print('[v175 rollback] 完成（{0}.{1} 列保留）'.format(
            WORK_ORDER_TABLE, PROJECT_COLUMN))
        return True
    except Exception as e:
        conn.rollback()
        print('[v175 rollback] 失败: %s' % e)
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
