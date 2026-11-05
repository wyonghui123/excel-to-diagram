# -*- coding: utf-8 -*-
"""v219 - 建立统一追溯只读视图 v_demand_trace_graph

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.10 / §6 阶段 4

口径:
1. 只读投影：执行层 doc_flow_edges + 计划层 demand_trace_links，UNION ALL
   成统一列族；两表各自保持权威，不做数据迁移。
2. 同库前提：SQLite 视图不能跨库 UNION。两基表任一缺失时 [SKIP]，不建空表
   stub、不跨库 ATTACH。
3. 刷新策略：schema_generator 只发 `CREATE VIEW IF NOT EXISTS`，定义变更不会
   生效；本迁移用 DROP VIEW + CREATE VIEW 负责刷新（YAML 仍是元数据真源）。
4. 视图 SQL 必须与 meta/schemas/demand_trace_graph.yaml 的 view_definition
   一致（test_demand_trace_graph.py 锁定）。

[ALLOW_DESTRUCTIVE] upgrade 会 DROP VIEW IF EXISTS；只重建投影，不动表数据。
"""

from __future__ import annotations

import os
import sqlite3

MIGRATION_NAME = 'v219__demand_trace_graph_view'

VIEW_NAME = 'v_demand_trace_graph'
EDGE_TABLE = 'doc_flow_edges'
TRACE_TABLE = 'demand_trace_links'

#: 统一列族（17 列）；与 demand_trace_graph.yaml 的 view_definition 逐字一致
VIEW_SQL = """\
SELECT
  'execution' AS layer,
  'E:' || e.id AS id,
  e.rule_id AS relation,
  e.source_bo AS source_object_type,
  e.source_id AS source_object_id,
  COALESCE(e.source_item, '') AS source_line_id,
  e.target_bo AS target_object_type,
  e.target_id AS target_object_id,
  COALESCE(e.target_item, '') AS target_line_id,
  e.quantity AS qty,
  CASE WHEN e.quantity_sign = 'red' THEN -e.quantity ELSE e.quantity END AS signed_qty,
  e.status AS status,
  NULL AS peg_type,
  NULL AS plan_version,
  NULL AS valid_from,
  NULL AS valid_to,
  e.derived_at AS occurred_at
FROM doc_flow_edges e
UNION ALL
SELECT
  'plan' AS layer,
  'T:' || CAST(t.id AS TEXT) AS id,
  t.trace_type AS relation,
  t.supply_object_type AS source_object_type,
  CAST(t.supply_object_id AS TEXT) AS source_object_id,
  COALESCE(NULLIF(CAST(t.supply_line_id AS TEXT), '0'), '') AS source_line_id,
  t.demand_object_type AS target_object_type,
  CAST(t.demand_object_id AS TEXT) AS target_object_id,
  COALESCE(NULLIF(CAST(t.demand_line_id AS TEXT), '0'), '') AS target_line_id,
  t.allocated_qty AS qty,
  CASE WHEN t.valid_to IS NULL THEN t.allocated_qty ELSE 0 END AS signed_qty,
  CASE WHEN t.valid_to IS NULL THEN 'active' ELSE 'expired' END AS status,
  t.peg_type AS peg_type,
  t.plan_version AS plan_version,
  t.valid_from AS valid_from,
  t.valid_to AS valid_to,
  t.computed_at AS occurred_at
FROM demand_trace_links t"""

VIEW_DDL = 'CREATE VIEW IF NOT EXISTS {0} AS\n{1}'.format(VIEW_NAME, VIEW_SQL)


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


def _do_upgrade(conn):
    if not (_table_exists(conn, EDGE_TABLE) and _table_exists(conn, TRACE_TABLE)):
        missing = [
            name for name in (EDGE_TABLE, TRACE_TABLE)
            if not _table_exists(conn, name)
        ]
        print('  - [SKIP] 缺基表 %s，不建视图 %s' % (', '.join(missing), VIEW_NAME))
        return False

    if _view_exists(conn, VIEW_NAME):
        conn.execute('DROP VIEW %s' % VIEW_NAME)
        print('  - [OK] 重建视图 %s（DROP + CREATE）' % VIEW_NAME)
    else:
        print('  - [OK] 建视图 %s' % VIEW_NAME)
    conn.execute(VIEW_DDL)
    return True


def migrate(db_path, skip_backup=False):
    print('[v219] 建立统一追溯只读视图')
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
        both_base = (_table_exists(conn, EDGE_TABLE)
                     and _table_exists(conn, TRACE_TABLE))
        view_exists = _view_exists(conn, VIEW_NAME)
        checks = {
            'view_exists': view_exists,
            'skipped_without_base_tables': (not both_base and not view_exists),
        }
        return {
            'ok': checks['view_exists'] or checks['skipped_without_base_tables'],
            'checks': checks,
        }
    finally:
        conn.close()
