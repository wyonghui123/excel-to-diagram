# -*- coding: utf-8 -*-
"""v154 任务域六表 provisioning（迁移可交付）

背景
  Gen2 任务域六表（tasks / task_templates / workflows / workflow_runs /
  task_events / task_worklogs）没有 YAML schema，唯一建表入口是
  `meta/api/manage_api.py` 的 `init_services()` 懒调用
  `ensure_task_tables()` / `ensure_task_event_tables()`。headless 部署
  （只跑迁移、不初始化 manage API）会缺表 —— 任务域功能静默不可用。

本迁移做什么
  1. 用最小 sqlite3 data_source 适配器包住 `sqlite3.Connection`；
  2. 把六表名登记进表名安全白名单（table_name_validator）；
  3. 直接复用 `task_schema.build_task_meta_objects()` +
     `task_event_schema.build_task_event_meta_objects()` 的 MetaObject 定义，
     走 `sync_schema_from_meta()` 建表 + 补列 + 建索引。

幂等
  - 表已存在 → 跳过建表；缺列 → ALTER TABLE ADD COLUMN；索引
    `CREATE INDEX IF NOT EXISTS` —— 重复执行终态一致（可重复跑）。

回滚（rollback）
  - 六表均为新增对象，回滚不做破坏性删除（避免误删运行期数据）；
    no-op 返回 True。
"""
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v154__provision_task_domain_tables.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from meta.core.schema_generator import sync_schema_from_meta  # noqa: E402
from meta.core.table_name_validator import register_table_name  # noqa: E402
from meta.core.task_schema import (  # noqa: E402
    TASK_TABLE,
    TASK_TEMPLATE_TABLE,
    WORKFLOW_RUN_TABLE,
    WORKFLOW_TABLE,
    build_task_meta_objects,
)
from meta.core.task_event_schema import (  # noqa: E402
    TASK_EVENT_TABLE,
    WORKLOG_TABLE,
    build_task_event_meta_objects,
)

# 六表名（顺序：定义层 → 实例层 → 事件账）
TASK_DOMAIN_TABLES = (
    WORKFLOW_TABLE,
    TASK_TEMPLATE_TABLE,
    WORKFLOW_RUN_TABLE,
    TASK_TABLE,
    TASK_EVENT_TABLE,
    WORKLOG_TABLE,
)


class _SqliteConnAdapter:
    """最小 data_source 适配器：只实现 sync_schema_from_meta 用到的方法。

    SchemaMigrator 需要 `dialect` / `execute()`（返回 cursor）/ `commit()` /
    `table_exists()` / `get_table_columns()`，全部直通到 sqlite3.Connection。
    """

    dialect = "sqlite"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, command, params=None):
        cursor = self._conn.cursor()
        if params:
            return cursor.execute(command, params)
        return cursor.execute(command)

    def commit(self):
        self._conn.commit()

    def table_exists(self, table_name: str) -> bool:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None

    def get_table_columns(self, table_name: str) -> dict:
        cursor = self._conn.execute('PRAGMA table_info("{0}")'.format(table_name))
        columns = {}
        for row in cursor.fetchall():
            columns[row[1]] = {
                "type": row[2],
                "required": row[3] == 1,
                "default": row[4],
                "primary_key": row[5] == 1,
            }
        return columns


def _all_meta_objects():
    """六表 MetaObject（4 定义/实例 + 2 事件账）。"""
    return build_task_meta_objects() + build_task_event_meta_objects()


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v154] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v154] 任务域六表 provisioning（幂等）')
        for name in TASK_DOMAIN_TABLES:
            register_table_name(name)
        sync_schema_from_meta(_SqliteConnAdapter(conn), _all_meta_objects())
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v154] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """校验六表存在且 MetaObject 期望列齐全（允许实际多列）。"""
    if not db_path.exists():
        print('[v154 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        missing_tables = []
        missing_columns = {}
        counts = {}
        for obj in _all_meta_objects():
            table = obj.table_name
            rows = conn.execute('PRAGMA table_info("{0}")'.format(table)).fetchall()
            if not rows:
                missing_tables.append(table)
                continue
            actual = {r[1] for r in rows}
            counts[table] = len(actual)
            expected = {f.db_column for f in obj.get_persistent_fields()}
            absent = expected - actual
            if absent:
                missing_columns[table] = sorted(absent)

        if missing_tables or missing_columns:
            print(f'[v154 verify] FAIL: 缺表={missing_tables} 缺列={missing_columns}')
            return False

        detail = ' '.join(f'{t}={n}' for t, n in counts.items())
        print(f'[v154 verify] OK: 六表齐全且列完整（{detail}）')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """no-op：六表为新增对象，回滚不做破坏性删除，避免误删运行期数据。"""
    print('[v154] rollback: 六表为新增对象，不做破坏性删除')
    return True


downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _args = [a for a in sys.argv[1:] if a != '--rollback']
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v154] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v154] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v154] verify: {"PASS" if _v else "FAIL"}')
