# -*- coding: utf-8 -*-
"""v155 退役 scheduled_tasks（Gen1 定时配置层）

背景
  9 个 cron 作业已全部迁到进程内调度器（MaintenanceScheduler 8 个运维 +
  PlatformScheduler 的 platform_tick + WorkflowScheduleScheduler），调度配置
  内嵌代码、不落库。遗留 `scheduled_tasks` 表实测 0 行，`init_task_seed_data`
  每次启动还会主动清理它的历史行 —— 该表已无数据承载作用。

  本迁移同步删除 `meta/schemas/scheduled_task.yaml`（新库不再生成该表），
  并负责存量库的物理退役。

本迁移做什么
  RENAME scheduled_tasks → scheduled_tasks_pre_v155_backup → DROP
  （沿用 v071/v138 的「RENAME → DROP backup」模式，避免直接 DROP 未知数据）

幂等
  - 表不存在 → 直接返回 True（已退役或从未建过）

回滚（rollback）
  - 重建空表（结构照 `init_task_seed.py` 历史 DDL）；数据不回滚（本表已 0 行，
    且调度配置的唯一真源在进程内调度器代码）。
"""
import sqlite3
import sys
from pathlib import Path

TABLE = 'scheduled_tasks'
BACKUP = 'scheduled_tasks_pre_v155_backup'

# rollback 用：历史 DDL（与 meta/scripts/init_task_seed.py 删除前一致）
LEGACY_DDL = '''CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(100) DEFAULT 'business',
    handler VARCHAR(200) NOT NULL,
    trigger_mode VARCHAR(50) DEFAULT 'cron',
    schedule VARCHAR(200),
    queue VARCHAR(100) DEFAULT 'business',
    priority INTEGER DEFAULT 50,
    timeout INTEGER DEFAULT 300,
    max_retries INTEGER DEFAULT 3,
    handler_config TEXT DEFAULT '{}',
    description TEXT,
    enabled INTEGER DEFAULT 1,
    last_run_at DATETIME,
    next_run_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)'''


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v155] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v155] 退役 scheduled_tasks（Gen1 定时配置层）')
        if not _table_exists(conn, TABLE):
            print('  scheduled_tasks 不存在，已退役，跳过')
            return True
        cnt = _row_count(conn, TABLE)
        conn.execute(f'ALTER TABLE "{TABLE}" RENAME TO "{BACKUP}"')
        conn.execute(f'DROP TABLE IF EXISTS "{BACKUP}"')
        conn.commit()
        print(f'  RENAME+DROP {TABLE} → {BACKUP} ({cnt} rows)')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v155] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v155 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        leftovers = [t for t in (TABLE, BACKUP) if _table_exists(conn, t)]
        if leftovers:
            print(f'[v155 verify] FAIL: 旧表仍在: {leftovers}')
            return False
        print('[v155 verify] OK: scheduled_tasks 已退役')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """重建空表（结构回滚；数据不回滚）"""
    if not db_path.exists():
        print(f'[v155] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(LEGACY_DDL)
        conn.commit()
        print('  rollback: 重建空表 scheduled_tasks')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v155] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v155] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v155] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v155] verify: {"PASS" if _v else "FAIL"}')
