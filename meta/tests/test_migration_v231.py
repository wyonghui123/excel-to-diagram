# -*- coding: utf-8 -*-
"""v231 work_order MTS 迁移测试。

覆盖:
  · order_id / order_line_id 由 NOT NULL 放宽为 NULL（12-step 重建）；
  · item_id / planned_qty 新增列；
  · 数据与索引保留、迁移幂等、verify / rollback。
"""

import importlib
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

_MODULE = importlib.import_module('meta.migrations.v231__work_order_mts')

#: 迁移前的严格表：order_id / order_line_id NOT NULL
_STRICT_DDL = """
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_no TEXT NOT NULL,
    order_type TEXT NOT NULL,
    schedule_id INTEGER,
    order_id INTEGER NOT NULL,
    order_line_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    source_demand_type TEXT,
    source_demand_id INTEGER,
    created_at TEXT
);
CREATE INDEX idx_work_order_source_demand
    ON work_orders(source_demand_type, source_demand_id);
"""


def _make_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(_STRICT_DDL)
    conn.execute(
        "INSERT INTO work_orders (work_order_no, order_type, order_id, "
        "order_line_id, status) VALUES ('WO-1', 'production', 10, 100, 'New')")
    conn.commit()
    conn.close()


def _columns(path):
    conn = sqlite3.connect(str(path))
    try:
        return {row[1]: row[3] for row in
                conn.execute('PRAGMA table_info(work_orders)').fetchall()}
    finally:
        conn.close()


def test_migration_relaxes_notnull_and_adds_columns(tmp_path):
    db = tmp_path / 'migrate_v231.db'
    _make_db(db)

    assert _MODULE.migrate(db, skip_backup=True) is True
    assert _MODULE.verify(db) is True

    columns = _columns(db)
    assert columns['order_id'] == 0
    assert columns['order_line_id'] == 0
    assert 'item_id' in columns and columns['item_id'] == 0
    assert 'planned_qty' in columns and columns['planned_qty'] == 0

    conn = sqlite3.connect(str(db))
    try:
        # 存量数据保留
        row = conn.execute(
            'SELECT work_order_no, order_id, order_line_id FROM work_orders'
        ).fetchone()
        assert row == ('WO-1', 10, 100)
        # 索引保留
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='work_orders'").fetchall()}
        assert 'idx_work_order_source_demand' in names
        # MTS 行（NULL 订单 / 订单行）可写入
        conn.execute(
            "INSERT INTO work_orders (work_order_no, order_type, order_id, "
            "order_line_id, status, source_demand_type, item_id, planned_qty) "
            "VALUES ('WO-2', 'production', NULL, NULL, 'New', 'manual', 500, 5)")
        conn.commit()
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / 'migrate_v231_twice.db'
    _make_db(db)

    assert _MODULE.migrate(db, skip_backup=True) is True
    assert _MODULE.migrate(db, skip_backup=True) is True
    assert _MODULE.verify(db) is True


def test_rollback_drops_new_columns_but_keeps_relaxed_notnull(tmp_path):
    db = tmp_path / 'rollback_v231.db'
    _make_db(db)
    assert _MODULE.migrate(db, skip_backup=True) is True

    assert _MODULE.rollback(db) is True

    columns = _columns(db)
    assert 'item_id' not in columns
    assert 'planned_qty' not in columns
    # 回滚不恢复 NOT NULL（存量数据可能为 NULL）
    assert columns['order_id'] == 0
    assert columns['order_line_id'] == 0
    assert _MODULE.verify(db) is False