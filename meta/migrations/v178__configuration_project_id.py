# -*- coding: utf-8 -*-
"""[v178 2026-11-01] 配置实例补项目锚点（项目侧 P3 / G10）

依据:
  docs/specs/spec-project-type-object-model-research-2026-10-31.md §2.4 / D6 / G10
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §0.1 P3

设计:
  · D6：配置层不新建表；`configuration.project_id`（可空）+ 既有 `context_json`
    共同承载项目上下文（WBS / 客户 / 合同号仍走 JSON）
  · 本迁移给 `configurations` 补可空 `project_id` + `(project_id, status)` 索引
  · 物化链路（`config_materialize_policy` off/manual/auto）不感知 project_id：
    列可空，空值 = 与项目无关的通用配置，行为与迁移前完全一致（AC-06）
  · 不声明真外键（与 P1 / v175 / v176 / v177 的挂载列同构，避免存量库与新建库 DDL 漂移）

幂等:
  列 / 索引先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删索引；**保留** project_id 列（SQLite 删列不可逆，空值不影响旧链路）。
"""
import sqlite3
import sys
from pathlib import Path

CONFIGURATION_TABLE = 'configurations'
PROJECT_COLUMN = 'project_id'
PROJECT_INDEX = 'idx_configuration_project_status'

PROJECT_COLUMN_DDL = (
    'ALTER TABLE {0} ADD COLUMN {1} INTEGER NULL'.format(
        CONFIGURATION_TABLE, PROJECT_COLUMN)
)

INDEX_DDL = (
    'CREATE INDEX IF NOT EXISTS {0} ON {1}({2}, status)'.format(
        PROJECT_INDEX, CONFIGURATION_TABLE, PROJECT_COLUMN)
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
    if not _table_exists(conn, CONFIGURATION_TABLE):
        print('  - [SKIP] 表 {0} 不存在（由配置模块迁移负责）'.format(
            CONFIGURATION_TABLE))
        return
    if PROJECT_COLUMN in _columns(conn, CONFIGURATION_TABLE):
        print('  - [SKIP] 列 {0}.{1} 已存在'.format(CONFIGURATION_TABLE,
                                                    PROJECT_COLUMN))
        return
    conn.execute(PROJECT_COLUMN_DDL)
    print('  - [ALTER] 列 {0}.{1}'.format(CONFIGURATION_TABLE, PROJECT_COLUMN))


def _do_index(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, CONFIGURATION_TABLE):
        print('  - [SKIP] 索引 {0} 依赖表不存在'.format(PROJECT_INDEX))
        return
    columns = _columns(conn, CONFIGURATION_TABLE)
    if PROJECT_COLUMN not in columns or 'status' not in columns:
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
        print('[v178] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v178] 开始: 配置实例补项目锚点（P3 / G10）')
        _do_column(conn)
        _do_index(conn)
        conn.commit()
        print('[v178] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v178] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v178 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, CONFIGURATION_TABLE):
            print('[v178 verify] FAIL: 缺表 {0}'.format(CONFIGURATION_TABLE))
            ok = False
        else:
            if PROJECT_COLUMN not in _columns(conn, CONFIGURATION_TABLE):
                print('[v178 verify] FAIL: 缺列 {0}.{1}'.format(
                    CONFIGURATION_TABLE, PROJECT_COLUMN))
                ok = False
            if not _index_exists(conn, PROJECT_INDEX):
                print('[v178 verify] FAIL: 缺索引 {0}'.format(PROJECT_INDEX))
                ok = False
        print('[v178 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v178 rollback] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _index_exists(conn, PROJECT_INDEX):
            conn.execute('DROP INDEX IF EXISTS {0}'.format(PROJECT_INDEX))
            print('  - [DROP] 索引 {0}'.format(PROJECT_INDEX))
        conn.commit()
        print('[v178 rollback] 完成（{0}.{1} 列保留）'.format(
            CONFIGURATION_TABLE, PROJECT_COLUMN))
        return True
    except Exception as e:
        conn.rollback()
        print('[v178 rollback] 失败: %s' % e)
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
