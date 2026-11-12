# -*- coding: utf-8 -*-
"""[v207 2026-11-04] 项目任务执行守卫索引（G15 P1-5）

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.2 / §5

设计:
  · 只做一件事：确保 `project_tasks(project_id, status)` 索引存在，
    供 G4（engineered 项目 activity 任务计数）/ G9（任务引用检查）高频查询使用
  · 索引在 v179 已随项目任务表建出，本迁移对存量库 / 旧分支库做幂等补齐
  · 只建索引、不改列、不建表；重复执行打印 [SKIP]，DB 终态一致

幂等:
  索引先查后用；重复执行不报错。

回滚:
  仅删索引（表与数据保留）。
"""
import sqlite3
import sys
from pathlib import Path

TASK_TABLE = 'project_tasks'
INDEX_NAME = 'idx_project_task_project_status'
INDEX_DDL = (
    'CREATE INDEX IF NOT EXISTS {0} ON {1}(project_id, status)'.format(
        INDEX_NAME, TASK_TABLE)
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _do_index(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TASK_TABLE):
        print('  - [SKIP] 表 {0} 不存在（由 v179 项目任务迁移负责）'.format(
            TASK_TABLE))
        return
    if _index_exists(conn, INDEX_NAME):
        print('  - [SKIP] 索引 {0} 已存在'.format(INDEX_NAME))
        return
    conn.execute(INDEX_DDL)
    print('  - [ADD] 索引 {0}'.format(INDEX_NAME))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v207] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v207] 开始: 项目任务执行守卫索引（G15 P1-5）')
        _do_index(conn)
        conn.commit()
        print('[v207] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v207] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v207 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, TASK_TABLE):
            print('[v207 verify] FAIL: 缺表 {0}'.format(TASK_TABLE))
            ok = False
        elif not _index_exists(conn, INDEX_NAME):
            print('[v207 verify] FAIL: 缺索引 {0}'.format(INDEX_NAME))
            ok = False
        print('[v207 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v207 rollback] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _index_exists(conn, INDEX_NAME):
            conn.execute('DROP INDEX IF EXISTS {0}'.format(INDEX_NAME))
            print('  - [DROP] 索引 {0}'.format(INDEX_NAME))
        conn.commit()
        print('[v207 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v207 rollback] 失败: %s' % e)
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
