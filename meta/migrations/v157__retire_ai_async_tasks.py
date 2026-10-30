# -*- coding: utf-8 -*-
"""v157 退役 ai_async_tasks（Gen1 AI 异步任务表）

背景
  任务体系两代收口完成后，AI 异步任务队列已无运行时读写路径，表实测 0 行。
  本迁移同步删除 `meta/schemas/ai_async_task.yaml`（新库不再生成该表），
  并负责存量库的物理退役。

本迁移做什么
  RENAME ai_async_tasks → ai_async_tasks_pre_v157_backup → DROP
  （沿用 v155 / v071 / v138 的「RENAME → DROP backup」模式，避免直接 DROP 未知数据）

幂等
  - 表不存在 → 直接返回 True（已退役或从未建过）

回滚（rollback）
  - 重建空表（结构照 `meta/schemas/generated_schema.sql` 的 ai_async_tasks DDL）；
    数据不回滚（本表已 0 行，且无运行时写入路径）。
"""
import sqlite3
import sys
from pathlib import Path

TABLE = 'ai_async_tasks'
BACKUP = 'ai_async_tasks_pre_v157_backup'

# rollback 用：历史 DDL（与删除前的 generated_schema.sql 一致）
LEGACY_DDL = '''CREATE TABLE IF NOT EXISTS ai_async_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type VARCHAR(200) NOT NULL,
    session_id VARCHAR(200),
    agent_id VARCHAR(200),
    parent_task_id INTEGER,
    request TEXT NOT NULL,
    context TEXT,
    priority INTEGER DEFAULT 50,
    queue VARCHAR(200) DEFAULT 'ai_normal',
    status VARCHAR(200) DEFAULT 'pending',
    worker_id VARCHAR(200),
    started_at DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER,
    result TEXT,
    error_message TEXT,
    tokens_used INTEGER,
    cost REAL,
    model_used VARCHAR(200),
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    timeout INTEGER DEFAULT 300,
    tenant_id INTEGER,
    user_id INTEGER,
    created_at DATETIME,
    updated_at DATETIME
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
        print(f'[v157] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v157] 退役 ai_async_tasks（Gen1 AI 异步任务表）')
        if not _table_exists(conn, TABLE):
            print('  ai_async_tasks 不存在，已退役，跳过')
            return True
        cnt = _row_count(conn, TABLE)
        conn.execute(f'ALTER TABLE "{TABLE}" RENAME TO "{BACKUP}"')
        conn.execute(f'DROP TABLE IF EXISTS "{BACKUP}"')
        conn.commit()
        print(f'  RENAME+DROP {TABLE} → {BACKUP} ({cnt} rows)')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v157] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v157 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        leftovers = [t for t in (TABLE, BACKUP) if _table_exists(conn, t)]
        if leftovers:
            print(f'[v157 verify] FAIL: 旧表仍在: {leftovers}')
            return False
        print('[v157 verify] OK: ai_async_tasks 已退役')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """重建空表（结构回滚；数据不回滚）"""
    if not db_path.exists():
        print(f'[v157] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(LEGACY_DDL)
        conn.commit()
        print('  rollback: 重建空表 ai_async_tasks')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v157] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v157] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v157] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v157] verify: {"PASS" if _v else "FAIL"}')
