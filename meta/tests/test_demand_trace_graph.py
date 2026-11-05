# -*- coding: utf-8 -*-
"""DOC_FLOW 阶段 4 验收：统一追溯读面 / 跨层对账 / 只读护栏

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.10 / §6 阶段 4

覆盖:
  · AC-16 v_demand_trace_graph 同时投影执行层与计划层；YAML 与迁移 SQL 一致
  · AC-17 同一 SO 行计划核销量 vs 执行出库量不一致 → TRACE_EDGE_QTY_MISMATCH
  · AC-18 只读护栏 READ_ONLY_VIEW；发运服务不直插 demand_trace_links
"""

import os
import re
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_reconcile import scan
from meta.core.yaml_loader import load_yaml_file
from meta.migrations import v215__doc_flow_stage2_rules as v215
from meta.migrations import v222__doc_flow_return_shipment_rule as v222
from meta.services.trace_graph_service import TraceGraphService

_SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')

TRACE_DDL = """
CREATE TABLE IF NOT EXISTS demand_trace_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supply_object_type VARCHAR(30) NOT NULL,
    supply_object_id INTEGER NOT NULL,
    supply_line_id INTEGER NOT NULL DEFAULT 0,
    demand_object_type VARCHAR(30) NOT NULL,
    demand_object_id INTEGER NOT NULL,
    demand_line_id INTEGER NOT NULL DEFAULT 0,
    trace_type VARCHAR(20) NOT NULL DEFAULT 'allocation',
    peg_type VARCHAR(10) NOT NULL DEFAULT 'soft',
    allocated_qty REAL NOT NULL DEFAULT 0,
    plan_version VARCHAR(40),
    valid_from DATETIME,
    valid_to DATETIME,
    source_doc_type VARCHAR(50),
    source_doc_id INTEGER,
    source_line_id INTEGER,
    remark TEXT,
    computed_at DATETIME,
    created_at DATETIME
)
"""

SHIPMENT_LINE_DDL = """
CREATE TABLE IF NOT EXISTS shipment_lines (
    id INTEGER PRIMARY KEY,
    order_line_id INTEGER
)
"""

VIEW_COLUMNS = (
    'layer', 'id', 'relation',
    'source_object_type', 'source_object_id', 'source_line_id',
    'target_object_type', 'target_object_id', 'target_line_id',
    'qty', 'signed_qty', 'status',
    'peg_type', 'plan_version', 'valid_from', 'valid_to', 'occurred_at',
)


def _db(*, with_view=True, with_shipment_lines=False):
    conn = sqlite3.connect(':memory:')
    conn.execute(v215.EDGE_TABLE_DDL)
    for _, ddl in v215.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v215.CONSUMED_VIEW_DDL)
    conn.execute(TRACE_DDL)
    if with_shipment_lines:
        conn.execute(SHIPMENT_LINE_DDL)
    if with_view:
        assert v222._do_upgrade(conn) is True
    return conn


def _insert_edge(conn, edge_id, source_bo, source_id, target_bo, target_id,
                 qty, *, rule_id='so_schedule_to_shipment_line',
                 status='active', sign='normal',
                 source_item='', target_item=''):
    conn.execute(
        'INSERT INTO doc_flow_edges (id, source_bo, source_id, source_item, '
        'target_bo, target_id, target_item, quantity, amount, currency, unit, '
        'quantity_sign, rule_id, derived_at, derived_by, status, pool, '
        'source_instance_id, target_instance_id, derive_key) VALUES '
        '(?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [edge_id, source_bo, str(source_id), source_item, target_bo,
         str(target_id), target_item, qty, '', '3', sign, rule_id,
         '2026-11-01', 'tester', status, 'sales_delivery', '', '', ''])


def _insert_trace(conn, supply_type, supply_id, supply_line,
                  demand_type, demand_id, demand_line, qty, *,
                  trace_type='reservation', peg_type='soft',
                  valid_to=None, computed_at='2026-11-01'):
    conn.execute(
        'INSERT INTO demand_trace_links ('
        'supply_object_type, supply_object_id, supply_line_id, '
        'demand_object_type, demand_object_id, demand_line_id, '
        'trace_type, peg_type, allocated_qty, plan_version, '
        'valid_from, valid_to, source_doc_type, source_doc_id, '
        'source_line_id, remark, computed_at, created_at) VALUES '
        '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [supply_type, supply_id, supply_line, demand_type, demand_id,
         demand_line, trace_type, peg_type, qty, None, None, valid_to,
         None, None, None, None, computed_at, computed_at])


# ─────────────────────────────────────────────
# AC-16 统一追溯读面
# ─────────────────────────────────────────────

def test_view_projects_execution_and_plan_layers():
    conn = _db()
    _insert_edge(conn, 'edge-1', 'sales_order_schedule', 77,
                 'shipment_line', 88, 10.0)
    _insert_trace(conn, 'shipment', 900, 0,
                  'sales_order_line', 77, 0, 10.0)
    _insert_trace(conn, 'shipment', 901, 0,
                  'sales_order_line', 77, 0, 5.0,
                  valid_to='2026-10-01')

    rows = conn.execute(
        'SELECT {0} FROM v_demand_trace_graph ORDER BY layer, id'.format(
            ', '.join(VIEW_COLUMNS))).fetchall()
    assert len(rows) == 3

    by_id = {row[1]: dict(zip(VIEW_COLUMNS, row)) for row in rows}
    assert set(by_id) == {'E:edge-1', 'T:1', 'T:2'}

    execution = by_id['E:edge-1']
    assert execution['layer'] == 'execution'
    assert execution['relation'] == 'so_schedule_to_shipment_line'
    assert execution['source_object_type'] == 'sales_order_schedule'
    assert execution['target_object_type'] == 'shipment_line'
    assert execution['signed_qty'] == pytest.approx(10.0)
    assert execution['status'] == 'active'
    assert execution['peg_type'] is None

    plan_active = by_id['T:1']
    assert plan_active['layer'] == 'plan'
    assert plan_active['relation'] == 'reservation'
    assert plan_active['peg_type'] == 'soft'
    assert plan_active['signed_qty'] == pytest.approx(10.0)
    assert plan_active['status'] == 'active'

    plan_expired = by_id['T:2']
    assert plan_expired['status'] == 'expired'
    assert plan_expired['signed_qty'] == pytest.approx(0.0)


def test_view_yaml_matches_migration_sql():
    raw = load_yaml_file(os.path.join(_SCHEMA_DIR, 'demand_trace_graph.yaml'))
    assert raw is not None
    assert raw.object_type.value == 'view'
    assert not raw.write_anchor

    with open(os.path.join(_SCHEMA_DIR, 'demand_trace_graph.yaml'),
              encoding='utf-8') as fh:
        import yaml
        data = yaml.safe_load(fh)

    norm = lambda s: re.sub(r'\s+', ' ', s or '').strip()
    assert norm(data['view_definition']) == norm(v222.VIEW_SQL)
    assert data.get('write_anchor') is None
    assert data['import_export']['auto_crud'] is False
    action_ids = [a['id'] for a in data['actions']]
    assert action_ids == ['demand_trace_graph_read', 'demand_trace_graph_list']


def test_trace_service_walks_both_directions():
    conn = _db()
    _insert_edge(conn, 'e1', 'sales_order_schedule', 77,
                 'shipment_line', 88, 10.0)
    _insert_edge(conn, 'e2', 'shipment_line', 88,
                 'inventory_transaction', 900, 10.0,
                 rule_id='shipment_line_to_issue_txn')

    svc = TraceGraphService(conn)
    down = svc.trace('sales_order_schedule', 77, direction='down', max_depth=2)
    assert {(n['object_type'], n['object_id']) for n in down['nodes']} == {
        ('sales_order_schedule', '77'),
        ('shipment_line', '88'),
        ('inventory_transaction', '900'),
    }
    assert {link['id'] for link in down['links']} == {'E:e1', 'E:e2'}

    up = svc.trace('inventory_transaction', 900, direction='up', max_depth=2)
    assert {(n['object_type'], n['object_id']) for n in up['nodes']} == {
        ('inventory_transaction', '900'),
        ('shipment_line', '88'),
        ('sales_order_schedule', '77'),
    }


def test_trace_service_returns_empty_without_view():
    conn = _db(with_view=False)
    _insert_edge(conn, 'e1', 'sales_order_schedule', 77,
                 'shipment_line', 88, 10.0)

    svc = TraceGraphService(conn)
    assert svc.list_links(source_object_type='sales_order_schedule') == []
    result = svc.trace('sales_order_schedule', 77)
    assert result['links'] == []
    assert result['nodes'][0]['object_id'] == '77'


def test_migration_skips_when_base_tables_missing(tmp_path):
    db_path = str(tmp_path / 'empty.db')
    sqlite3.connect(db_path).close()
    v222.migrate(db_path)
    result = v222.verify(db_path)
    assert result['ok'] is True
    assert result['checks']['skipped_without_base_tables'] is True


def test_schema_sync_degrades_when_view_create_fails():
    """VIEW 建表失败只降级告警，不中断整轮 schema sync。"""
    from meta.core.models import ObjectType
    from meta.core.schema_generator import SchemaMigrator

    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'demand_trace_graph.yaml'))
    assert obj.object_type == ObjectType.VIEW

    class _FailingDS:
        dialect = 'sqlite'

        def table_exists(self, name):
            return False

        def get_table_columns(self, name):
            return []

        def execute(self, sql, params=None):
            raise RuntimeError('no such table: doc_flow_edges')

        def commit(self):
            pass

    executed = SchemaMigrator(_FailingDS()).migrate([obj])
    assert executed  # CREATE VIEW 语句已生成，仅执行期降级


# ─────────────────────────────────────────────
# AC-17 跨层对账
# ─────────────────────────────────────────────

def _trace_edge_env(plan_qty=10.0, exec_qty=12.0, *, with_trace=True,
                    with_shipment_lines=True):
    conn = _db(with_shipment_lines=with_shipment_lines)
    if with_shipment_lines:
        conn.execute('INSERT INTO shipment_lines (id, order_line_id) VALUES (55, 77)')
    _insert_edge(conn, 'edge-1', 'shipment_line', 55,
                 'inventory_transaction', 900, exec_qty,
                 rule_id='shipment_line_to_issue_txn')
    if with_trace:
        _insert_trace(conn, 'shipment', 900, 0,
                      'sales_order_line', 77, 0, plan_qty)
    return conn


def test_cross_layer_quantity_mismatch_is_reported():
    report = scan(_trace_edge_env(plan_qty=10.0, exec_qty=12.0))
    assert 'TRACE_EDGE_QTY_MISMATCH' in report.codes()
    assert report.ok is False


def test_cross_layer_equal_quantity_is_clean():
    report = scan(_trace_edge_env(plan_qty=10.0, exec_qty=10.0))
    assert 'TRACE_EDGE_QTY_MISMATCH' not in report.codes()


def test_cross_layer_one_sided_is_not_reported():
    report = scan(_trace_edge_env(exec_qty=10.0, with_trace=False))
    assert 'TRACE_EDGE_QTY_MISMATCH' not in report.codes()


def test_cross_layer_skips_without_shipment_lines():
    report = scan(_trace_edge_env(with_shipment_lines=False))
    assert 'TRACE_EDGE_QTY_MISMATCH' not in report.codes()


# ─────────────────────────────────────────────
# AC-18 只读护栏 + 写边界
# ─────────────────────────────────────────────

def test_view_write_is_rejected_as_readonly():
    from meta.core.models import registry
    from meta.services.manage_service import CreateRequest, ManageService

    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'demand_trace_graph.yaml'))
    added = registry.get(obj.id) is None
    if added:
        registry.register(obj)
    try:
        svc = ManageService.__new__(ManageService)
        result = svc.create(CreateRequest(
            object_type='demand_trace_graph', data={'id': 'E:edge-1'}))
        assert result.success is False
        assert result.error == 'READ_ONLY_VIEW'
    finally:
        if added:
            registry._objects.pop(obj.id, None)


def test_shipment_service_does_not_insert_trace_directly():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'services', 'shipment_service.py')
    with open(path, encoding='utf-8') as fh:
        source = fh.read()
    assert 'INSERT INTO demand_trace_links' not in source
    assert 'DemandTraceService' in source
