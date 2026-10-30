# -*- coding: utf-8 -*-
"""账本统一 Phase 2 测试（v165 冻结 / 跨库投影 / v166 退役）

覆盖:
  TC-LEDGER-001 v165：pending/running → cancelled，completed/failed 不动
  TC-LEDGER-002 v165：二次执行幂等（更新 0 行）
  TC-LEDGER-003 v165：rollback 把带标记的 cancelled 恢复为 pending
  TC-LEDGER-004 投影工具：task_executions + task_execution_archive → task_events
  TC-LEDGER-005 投影工具：二次执行 0 新增（幂等）
  TC-LEDGER-006 投影工具：--dry-run 不写库；--strict 未完成退出码 1
  TC-LEDGER-007 投影工具：库/表不可用退出码 2
  TC-LEDGER-008 v166：有行且未授权 → 拒绝删表
  TC-LEDGER-009 v166：授权后删表 + verify 通过
  TC-LEDGER-010 v166：表已不存在 → 幂等 True；rollback 重建空表
"""
import json
import os
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# 迁移/投影工具直连临时 SQLite 库，需 raw SQL escape hatch（conftest 按文件声明放行）。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.core.task_infra_schema import TASK_EXECUTION_DDL  # noqa: E402
from meta.migrations import v165__freeze_task_executions as v165  # noqa: E402
from meta.migrations import v166__retire_task_execution_ledger as v166  # noqa: E402
from meta.tools import task_execution_ledger_migrate as ledger  # noqa: E402

ARCHIVE_TABLE = 'task_execution_archive'
ARCHIVE_DDL = TASK_EXECUTION_DDL.replace(
    'task_executions', ARCHIVE_TABLE).replace(
    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n'
    '        archived_at DATETIME DEFAULT CURRENT_TIMESTAMP',
)


# ─────────────────────────────────────────────────────────────────────────────
# 临时库构造
# ─────────────────────────────────────────────────────────────────────────────

def _insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    columns = ', '.join(row.keys())
    marks = ', '.join('?' for _ in row)
    conn.execute(
        'INSERT INTO "{0}" ({1}) VALUES ({2})'.format(table, columns, marks),
        tuple(row.values()),
    )


def _make_app_db(path: Path, executions=(), archive=()) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(TASK_EXECUTION_DDL)
        conn.execute(ARCHIVE_DDL)
        for row in executions:
            _insert(conn, v165.TABLE, row)
        for row in archive:
            _insert(conn, ARCHIVE_TABLE, row)
        conn.commit()
    finally:
        conn.close()
    return path


def _make_platform_db(path: Path) -> Path:
    """用真实 schema 建 task_events / task_worklogs（再释放连接池）。"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.task_event_schema import ensure_task_event_tables

    source = get_data_source('sqlite', database=str(path))
    with source.transaction():
        ensure_task_event_tables(source)
    _clear_data_source_cache_for_testing()
    return path


def _scalar(path: Path, sql: str, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def _table_exists(path: Path, table: str) -> bool:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _status_counts(path: Path) -> dict:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            'SELECT status, COUNT(*) FROM "{0}" GROUP BY status'.format(v165.TABLE)
        ).fetchall()
        return {status: count for status, count in rows}
    finally:
        conn.close()


def _events(path: Path) -> list:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            'SELECT id, task_id, event_type, to_status, payload, occurred_at '
            'FROM task_events ORDER BY id'
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _exec_rows():
    return [
        {'id': 1, 'task_id': 101, 'status': 'pending',
         'queued_at': '2026-09-01 00:00:00'},
        {'id': 2, 'task_id': None, 'status': 'pending',
         'queued_at': '2026-09-01 00:00:00'},
        {'id': 3, 'task_id': 103, 'status': 'running',
         'queued_at': '2026-09-01 00:00:00', 'started_at': '2026-09-01 00:01:00'},
        {'id': 4, 'task_id': 104, 'status': 'completed',
         'completed_at': '2026-09-01 00:02:00'},
        {'id': 5, 'task_id': 105, 'status': 'failed',
         'completed_at': '2026-09-01 00:03:00'},
    ]


def _archive_rows():
    return [
        {'id': 1, 'task_id': 201, 'status': 'completed',
         'completed_at': '2026-08-01 00:00:00',
         'archived_at': '2026-09-01 00:00:00'},
        {'id': 2, 'task_id': None, 'status': 'failed',
         'completed_at': '2026-08-02 00:00:00',
         'archived_at': '2026-09-01 00:00:00'},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# v165 冻结
# ─────────────────────────────────────────────────────────────────────────────

def test_v165_freezes_pending_and_running(tmp_path):
    db = _make_app_db(tmp_path / 'app.db', executions=_exec_rows())

    assert v165.migrate(db) is True
    assert v165.verify(db) is True

    assert _status_counts(db) == {'cancelled': 3, 'completed': 1, 'failed': 1}

    conn = sqlite3.connect(str(db))
    try:
        marked = conn.execute(
            'SELECT COUNT(*) FROM "{0}" WHERE status = ? AND '
            'completed_at IS NOT NULL AND error_message LIKE ?'.format(v165.TABLE),
            ('cancelled', '%' + v165.FROZEN_MARKER + '%'),
        ).fetchone()[0]
    finally:
        conn.close()
    assert marked == 3


def test_v165_is_idempotent(tmp_path):
    db = _make_app_db(tmp_path / 'app.db', executions=_exec_rows())

    assert v165.migrate(db) is True
    assert v165.migrate(db) is True  # 二次执行更新 0 行
    assert _status_counts(db) == {'cancelled': 3, 'completed': 1, 'failed': 1}


def test_v165_rollback_restores_pending(tmp_path):
    db = _make_app_db(tmp_path / 'app.db', executions=_exec_rows())
    assert v165.migrate(db) is True

    assert v165.rollback(db) is True
    assert _status_counts(db) == {'pending': 3, 'completed': 1, 'failed': 1}

    conn = sqlite3.connect(str(db))
    try:
        leftovers = conn.execute(
            'SELECT COUNT(*) FROM "{0}" WHERE error_message IS NOT NULL '
            'OR (status = ? AND completed_at IS NOT NULL AND id NOT IN (4, 5))'
            .format(v165.TABLE), ('cancelled',),
        ).fetchone()[0]
    finally:
        conn.close()
    assert leftovers == 0


def test_v165_verify_passes_when_table_retired(tmp_path):
    db = _make_app_db(tmp_path / 'app.db')
    conn = sqlite3.connect(str(db))
    conn.execute('DROP TABLE "{0}"'.format(v165.TABLE))
    conn.commit()
    conn.close()

    assert v165.verify(db) is True


# ─────────────────────────────────────────────────────────────────────────────
# 跨库投影（Phase 2b）
# ─────────────────────────────────────────────────────────────────────────────

def test_projection_copies_both_sources(tmp_path):
    app_db = _make_app_db(tmp_path / 'app.db',
                          executions=_exec_rows(), archive=_archive_rows())
    plat_db = _make_platform_db(tmp_path / 'platform.db')

    report = ledger.project(str(app_db), str(plat_db))

    assert report['found'] == 7
    assert report['projected'] == 7
    assert report['dry_run'] is False
    assert report['missing_after'] == []

    events = _events(plat_db)
    assert len(events) == 7
    assert {e['event_type'] for e in events} == {ledger.EVENT_TYPE}

    ids = {e['id'] for e in events}
    assert 'gen1-execution:1' in ids
    assert 'gen1-execution:5' in ids
    assert 'gen1-archive:1' in ids
    assert 'gen1-archive:2' in ids

    by_id = {e['id']: e for e in events}
    # task_id 有值 → 归并到同一条计划任务；无值 → 按行派生独立 task_id
    assert by_id['gen1-execution:1']['task_id'] == 'gen1-scheduled-task:101'
    assert by_id['gen1-execution:2']['task_id'] == 'gen1-execution:2'
    assert by_id['gen1-archive:1']['task_id'] == 'gen1-scheduled-task:201'
    assert by_id['gen1-execution:4']['to_status'] == 'completed'
    assert by_id['gen1-execution:3']['to_status'] == 'running'

    payload = json.loads(by_id['gen1-archive:1']['payload'])
    assert payload['status'] == 'completed'
    assert payload['archived_at'] == '2026-09-01 00:00:00'
    assert by_id['gen1-archive:1']['occurred_at'] == '2026-08-01 00:00:00'


def test_projection_is_idempotent(tmp_path):
    app_db = _make_app_db(tmp_path / 'app.db',
                          executions=_exec_rows(), archive=_archive_rows())
    plat_db = _make_platform_db(tmp_path / 'platform.db')

    first = ledger.project(str(app_db), str(plat_db))
    assert first['projected'] == 7

    second = ledger.project(str(app_db), str(plat_db))
    assert second['projected'] == 0
    assert second['would_project'] == 0
    assert second['already_present'] == 7
    assert len(_events(plat_db)) == 7


def test_projection_dry_run_does_not_write(tmp_path):
    app_db = _make_app_db(tmp_path / 'app.db',
                          executions=_exec_rows(), archive=_archive_rows())
    plat_db = _make_platform_db(tmp_path / 'platform.db')

    report = ledger.project(str(app_db), str(plat_db), dry_run=True)
    assert report['dry_run'] is True
    assert report['would_project'] == 7
    assert report['projected'] == 0
    assert _events(plat_db) == []


def test_projection_strict_exit_code(tmp_path):
    app_db = _make_app_db(tmp_path / 'app.db', executions=_exec_rows())
    plat_db = _make_platform_db(tmp_path / 'platform.db')

    base = ['--app-db', str(app_db), '--platform-db', str(plat_db)]
    assert ledger.main(base + ['--dry-run', '--strict']) == 1
    assert ledger.main(base + ['--dry-run']) == 0
    assert ledger.main(base) == 0
    assert len(_events(plat_db)) == 5


def test_projection_errors_return_exit_2(tmp_path):
    plat_db = _make_platform_db(tmp_path / 'platform.db')
    missing_app = tmp_path / 'not-exists.db'

    assert ledger.main(
        ['--app-db', str(missing_app), '--platform-db', str(plat_db)]) == 2

    app_db = _make_app_db(tmp_path / 'app.db', executions=_exec_rows())
    bare_plat = tmp_path / 'bare.db'
    sqlite3.connect(str(bare_plat)).close()
    assert ledger.main(
        ['--app-db', str(app_db), '--platform-db', str(bare_plat)]) == 2


def test_projection_handles_missing_source_tables(tmp_path):
    app_db = tmp_path / 'empty.db'
    sqlite3.connect(str(app_db)).close()
    plat_db = _make_platform_db(tmp_path / 'platform.db')

    report = ledger.project(str(app_db), str(plat_db))
    assert report['found'] == 0
    assert report['projected'] == 0
    assert report['sources']['execution']['exists'] is False
    assert report['sources']['archive']['exists'] is False
    assert ledger.main(
        ['--app-db', str(app_db), '--platform-db', str(plat_db)]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# v166 退役
# ─────────────────────────────────────────────────────────────────────────────

def test_v166_refuses_drop_when_rows_remain(tmp_path, monkeypatch):
    monkeypatch.delenv(v166.ALLOW_ENV, raising=False)
    db = _make_app_db(tmp_path / 'app.db',
                      executions=_exec_rows(), archive=_archive_rows())

    assert v166.migrate(db) is False
    assert _table_exists(db, v165.TABLE)
    assert _table_exists(db, ARCHIVE_TABLE)


def test_v166_drops_tables_after_projection(tmp_path, monkeypatch):
    app_db = _make_app_db(tmp_path / 'app.db',
                          executions=_exec_rows(), archive=_archive_rows())
    plat_db = _make_platform_db(tmp_path / 'platform.db')

    assert ledger.project(str(app_db), str(plat_db))['projected'] == 7

    monkeypatch.setenv(v166.ALLOW_ENV, '1')
    assert v166.migrate(app_db) is True
    assert v166.verify(app_db) is True
    assert not _table_exists(app_db, v165.TABLE)
    assert not _table_exists(app_db, ARCHIVE_TABLE)
    assert not _table_exists(app_db, v165.TABLE + v166.BACKUP_SUFFIX)
    assert not _table_exists(app_db, ARCHIVE_TABLE + v166.BACKUP_SUFFIX)

    assert len(_events(plat_db)) == 7  # 数据已转存事件账


def test_v166_is_idempotent_when_tables_absent(tmp_path):
    db = _make_app_db(tmp_path / 'app.db')
    conn = sqlite3.connect(str(db))
    conn.execute('DROP TABLE "{0}"'.format(v165.TABLE))
    conn.execute('DROP TABLE "{0}"'.format(ARCHIVE_TABLE))
    conn.commit()
    conn.close()

    assert v166.migrate(db) is True
    assert v166.verify(db) is True


def test_v166_rollback_recreates_empty_table(tmp_path, monkeypatch):
    db = _make_app_db(tmp_path / 'app.db', executions=_exec_rows())
    monkeypatch.setenv(v166.ALLOW_ENV, '1')
    assert v166.migrate(db) is True
    assert not _table_exists(db, v165.TABLE)

    assert v166.rollback(db) is True
    assert _table_exists(db, v165.TABLE)
    assert _scalar(db, 'SELECT COUNT(*) FROM "{0}"'.format(v165.TABLE)) == 0
    # archive 不回滚（结构与数据均由 v158 负责）
    assert not _table_exists(db, ARCHIVE_TABLE)
