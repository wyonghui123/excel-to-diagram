# -*- coding: utf-8 -*-
"""v214 - 启用 DOC_FLOW 并注册「发运行 → 出库事务」转单规则

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.1 / §6 阶段 0
      meta/core/doc_flow_schema.py（边表 21 列 + 消耗视图）
      meta/core/doc_flow_rule_store.py（规则表 15 列）

背景:
- DOC_FLOW 引擎已实现，但仓库内无任何 app 声明 `doc_flow`，规则表/边表在
  实际库中可能不存在（零启用）。本迁移做最小启用，为 P0「交货确认 → 出库」
  提供边表与规则。
- 迁移编号 v213 已被并发会话的 handling_unit_momp 占用，本迁移顺延 v214。

口径:
1. 规则表在平台库、边表在应用库。单库部署（APP_DB_ROUTING 关闭）下两者同库，
   本迁移自包含建表，不依赖 core 的 DataSource（迁移只拿 db_path）。
2. DDL 必须与 doc_flow_schema._build_edge_meta / rule_store.RULE_TABLE_DDL 一致；
   若后续 core 调整列，需另加迁移对齐。
3. 规则 upsert 只覆盖声明字段，不覆盖 status（运行态由 set_rule_status 管理）。
4. rollback 只删「本迁移注册的规则」与消耗视图，**保留边表**（事实流水不可回滚删除）。

[ALLOW_DESTRUCTIVE] rollback 会 DROP VIEW；不做 DROP TABLE。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

MIGRATION_NAME = 'v214__doc_flow_shipment_issue_rule'

RULE_ID = 'shipment_line_to_issue_txn'

RULE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_rule (
    rule_id          TEXT PRIMARY KEY,
    source_bo        TEXT NOT NULL,
    target_bo        TEXT NOT NULL,
    source_qty_field TEXT NOT NULL DEFAULT 'quantity',
    pool             TEXT NOT NULL DEFAULT 'default',
    status           TEXT NOT NULL DEFAULT 'active',
    check_hook       TEXT,
    map_hook         TEXT,
    create_hook      TEXT,
    field_map        TEXT NOT NULL DEFAULT '{}',
    split_key        TEXT NOT NULL DEFAULT '[]',
    target_line_bo   TEXT NOT NULL DEFAULT '',
    head_fk_field    TEXT NOT NULL DEFAULT '',
    created_at       TEXT,
    updated_at       TEXT
)
"""

EDGE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_edges (
    id                  TEXT NOT NULL,
    source_bo           TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    source_item         TEXT DEFAULT '',
    target_bo           TEXT NOT NULL,
    target_id           TEXT NOT NULL,
    target_item         TEXT DEFAULT '',
    quantity            REAL NOT NULL,
    amount              REAL DEFAULT 0,
    currency            TEXT DEFAULT '',
    unit                TEXT DEFAULT '',
    quantity_sign       TEXT NOT NULL DEFAULT 'normal',
    rule_id             TEXT NOT NULL,
    derived_at          TEXT,
    derived_by          TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'active',
    pool                TEXT NOT NULL DEFAULT 'default',
    source_instance_id  TEXT DEFAULT '',
    target_instance_id  TEXT DEFAULT '',
    derive_key          TEXT DEFAULT ''
)
"""

EDGE_INDEXES = (
    ("uq_doc_flow_idem",
     "CREATE UNIQUE INDEX IF NOT EXISTS uq_doc_flow_idem ON doc_flow_edges("
     "source_bo, source_id, source_item, target_bo, target_id, target_item, rule_id)"),
    ("idx_doc_flow_source",
     "CREATE INDEX IF NOT EXISTS idx_doc_flow_source ON doc_flow_edges("
     "source_bo, source_id, status)"),
    ("idx_doc_flow_target",
     "CREATE INDEX IF NOT EXISTS idx_doc_flow_target ON doc_flow_edges("
     "target_bo, target_id, status)"),
)

CONSUMED_VIEW_DDL = """
CREATE VIEW IF NOT EXISTS v_doc_flow_consumed_qty AS
SELECT source_bo, source_id, source_item, pool,
       SUM(CASE WHEN status='active' AND quantity_sign='normal'
                THEN quantity ELSE 0 END)
     - SUM(CASE WHEN status='active' AND quantity_sign='red'
                THEN quantity ELSE 0 END) AS consumed_qty
FROM doc_flow_edges
GROUP BY source_bo, source_id, source_item, pool
"""

RULE = {
    'rule_id': RULE_ID,
    'source_bo': 'shipment_line',
    'target_bo': 'inventory_transaction',
    'source_qty_field': 'qty',
    'pool': 'inventory_issue',
    'field_map': '{}',
    'split_key': '[]',
    'target_line_bo': '',
    'head_fk_field': '',
}


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _view_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _index_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _do_upgrade(conn):
    now = datetime.now().isoformat(timespec='seconds')

    if _table_exists(conn, 'doc_flow_rule'):
        print('  - [SKIP] 表 doc_flow_rule 已存在')
    else:
        conn.execute(RULE_TABLE_DDL)
        print('  - [OK] 建表 doc_flow_rule')

    if _table_exists(conn, 'doc_flow_edges'):
        print('  - [SKIP] 表 doc_flow_edges 已存在')
    else:
        conn.execute(EDGE_TABLE_DDL)
        print('  - [OK] 建表 doc_flow_edges')

    for name, ddl in EDGE_INDEXES:
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
        else:
            conn.execute(ddl)
            print('  - [OK] 建索引 %s' % name)

    if _view_exists(conn, 'v_doc_flow_consumed_qty'):
        print('  - [SKIP] 视图 v_doc_flow_consumed_qty 已存在')
    else:
        conn.execute(CONSUMED_VIEW_DDL)
        print('  - [OK] 建视图 v_doc_flow_consumed_qty')

    conn.execute(
        """
        INSERT INTO doc_flow_rule
            (rule_id, source_bo, target_bo, source_qty_field, pool, status,
             field_map, split_key, target_line_bo, head_fk_field,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rule_id) DO UPDATE SET
            source_bo=excluded.source_bo,
            target_bo=excluded.target_bo,
            source_qty_field=excluded.source_qty_field,
            pool=excluded.pool,
            field_map=excluded.field_map,
            split_key=excluded.split_key,
            target_line_bo=excluded.target_line_bo,
            head_fk_field=excluded.head_fk_field,
            updated_at=excluded.updated_at
        """,
        [
            RULE['rule_id'], RULE['source_bo'], RULE['target_bo'],
            RULE['source_qty_field'], RULE['pool'],
            RULE['field_map'], RULE['split_key'],
            RULE['target_line_bo'], RULE['head_fk_field'],
            now, now,
        ],
    )
    print('  - [OK] upsert 规则 %s' % RULE_ID)


def migrate(db_path, skip_backup=False):
    print('[v214] 启用 DOC_FLOW 与发运出库规则')
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return
    conn = sqlite3.connect(db_path)
    try:
        _do_upgrade(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path):
    if not os.path.exists(db_path):
        return {'ok': False, 'error': 'db not found'}
    conn = sqlite3.connect(db_path)
    try:
        checks = {
            'rule_table': _table_exists(conn, 'doc_flow_rule'),
            'edge_table': _table_exists(conn, 'doc_flow_edges'),
            'idem_index': _index_exists(conn, 'uq_doc_flow_idem'),
            'source_index': _index_exists(conn, 'idx_doc_flow_source'),
            'consumed_view': _view_exists(conn, 'v_doc_flow_consumed_qty'),
        }
        row = conn.execute(
            'SELECT status FROM doc_flow_rule WHERE rule_id=?', [RULE_ID]
        ).fetchone()
        checks['rule_registered'] = bool(row)
        checks['rule_active'] = bool(row) and row[0] == 'active'
        ok = all(checks.values())
        return {'ok': ok, 'checks': checks}
    finally:
        conn.close()


def rollback(db_path, skip_backup=False):
    """回滚只撤销规则与视图；边表保留（事实流水不可删）。"""
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('DELETE FROM doc_flow_rule WHERE rule_id=?', [RULE_ID])
        conn.execute('DROP VIEW IF EXISTS v_doc_flow_consumed_qty')
        conn.commit()
        print('  - [OK] 已删除规则 %s 与消耗视图（边表保留）' % RULE_ID)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
