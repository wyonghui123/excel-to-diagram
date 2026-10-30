# -*- coding: utf-8 -*-
"""v156 接管 Gen1 队列/账本表 provisioning（task_queues / task_executions）

背景
  这两张表的 DDL 过去分散在三处：`init_task_seed.py` 裸 DDL、
  `meta/schemas/task_queue.yaml`、`meta/schemas/task_execution.yaml`。
  YAML 双轨在本 change 删除后，建表唯一真源收敛到
  `meta/core/task_infra_schema.py`。

  本迁移让「只跑迁移、不跑启动种子」的部署也能拿到这两张表。

幂等
  - `CREATE TABLE IF NOT EXISTS`；表已存在 → 跳过（含存量库若干列的差异，不覆盖）

回滚（rollback）
  - 两张表均为运行账本（task_executions 有历史数据），回滚不做破坏性删除；
    no-op 返回 True。
"""
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from meta.core.task_infra_schema import (  # noqa: E402
    INFRA_TABLES,
    TASK_EXECUTION_TABLE,
    TASK_QUEUE_TABLE,
    ensure_task_infra_tables,
)


class _SqliteConnAdapter:
    """最小 data_source 适配器：只实现 ensure_task_infra_tables 用到的 execute/commit"""

    dialect = 'sqlite'

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, command, params=None):
        cursor = self._conn.cursor()
        if params:
            return cursor.execute(command, params)
        return cursor.execute(command)

    def commit(self):
        self._conn.commit()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> list:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v156] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v156] 接管 task_queues / task_executions provisioning')
        ensure_task_infra_tables(_SqliteConnAdapter(conn))
        conn.commit()
        for name, _ddl, _cols in INFRA_TABLES:
            print(f'  {name}: {_table_exists(conn, name)}')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v156] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v156 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        ok = True
        for name, _ddl, expected in INFRA_TABLES:
            if not _table_exists(conn, name):
                print(f'[v156 verify] FAIL: {name} 不存在')
                ok = False
                continue
            actual = set(_columns(conn, name))
            missing = [c for c in expected if c not in actual]
            if missing:
                print(f'[v156 verify] FAIL: {name} 缺列 {missing}')
                ok = False
        if ok:
            print(f'[v156 verify] OK: {TASK_QUEUE_TABLE} / {TASK_EXECUTION_TABLE} 就位')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """no-op：运行账本表不做破坏性删除"""
    print('[v156] rollback: no-op（运行账本表保留）')
    return True


downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v156] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v156] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v156] verify: {"PASS" if _v else "FAIL"}')
