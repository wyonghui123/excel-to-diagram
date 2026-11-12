# -*- coding: utf-8 -*-
"""规则挂起（holds）测试 —— spec §10.4 A 纯派生方案。

覆盖:
  · apply 幂等 / 部分唯一索引 uq_holds_active 防重复；
  · release = UPDATE released_at 不删行，可再次挂起；
  · active 查询重复 released_at IS NULL 并命中部分索引（非 SCAN TABLE）；
  · 盘点 submit 超容差行落 hold、容差内不落；
  · approve / cancel 释放 hold（历史行保留）；
  · 表与两个部分索引由 v231 安装。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v231__rule_hold as v231
from meta.services.inventory_count_service import (
    CNT_LINE_OBJECT, INV_COUNT_HELD, TOLERANCE_RULE_ID,
)
from meta.services.inventory_guard_service import InventoryError
from meta.services.rule_hold_service import RuleHoldService
from meta.tests import inventory_adjustment_doubles as adj
from meta.tests import inventory_test_doubles as inv


def _ds(conn):
    return inv.MemDS(conn)


def _holds(conn):
    return _ds(conn).query('SELECT * FROM holds ORDER BY id')


def _create_count(conn, **payload):
    service = adj.count_service(conn)
    data = service.prepare_create(dict(
        {'org_id': inv.ORG_ID, 'location_id': inv.LOCATION_ID}, **payload))
    return adj.insert_count(conn, data), data, service


def _lines(conn, count_id):
    return _ds(conn).query(
        'SELECT * FROM inventory_count_lines WHERE count_id=? ORDER BY line_no',
        [count_id])


def _set_counted(conn, line_id, qty, reason=None):
    conn.execute(
        'UPDATE inventory_count_lines SET counted_qty=?, variance_reason=? '
        'WHERE id=?', [qty, reason, line_id])
    conn.commit()


# ---------------- 表 / 索引 ----------------

def test_v231_installs_table_and_partial_indexes():
    conn = adj.build_adjustment_db()
    tables = {row['name'] for row in _ds(conn).query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'holds' in tables
    indexes = {row['name']: row['sql'] for row in _ds(conn).query(
        "SELECT name, sql FROM sqlite_master WHERE type='index' "
        "AND name IN ('idx_holds_active', 'uq_holds_active')")}
    assert 'idx_holds_active' in indexes
    assert 'uq_holds_active' in indexes
    for sql in indexes.values():
        assert 'released_at IS NULL' in sql


def test_yaml_declares_both_partial_indexes():
    from meta.core.models import registry
    from meta.core.schema_generator import SchemaGenerator

    gen = SchemaGenerator()
    obj = registry.get('rule_hold')
    table_ddl = gen.generate_create_table(obj)
    index_ddl = '\n'.join(gen.generate_create_index(obj))
    assert 'CREATE TABLE IF NOT EXISTS holds' in table_ddl
    for column in ('object_type', 'record_id', 'rule_key', 'released_at'):
        assert column in table_ddl
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_holds_active' in index_ddl
    assert 'CREATE INDEX IF NOT EXISTS idx_holds_active' in index_ddl
    assert index_ddl.count('WHERE released_at IS NULL') == 2


def test_active_query_uses_partial_index_not_scan():
    conn = adj.build_adjustment_db()
    plan = conn.execute(
        'EXPLAIN QUERY PLAN SELECT 1 FROM holds WHERE object_type = ? '
        'AND record_id = ? AND released_at IS NULL',
        ['inventory_count_line', 1]).fetchall()
    detail = ' '.join(str(row[3]) for row in plan)
    assert 'SCAN holds' not in detail
    assert 'INDEX' in detail.upper()


# ---------------- 服务：apply / release ----------------

def test_apply_is_idempotent_and_unique_index_guards_duplicates():
    conn = adj.build_adjustment_db()
    svc = RuleHoldService(_ds(conn))

    assert svc.apply(CNT_LINE_OBJECT, 1, TOLERANCE_RULE_ID,
                     code='X', reason='超容差', applied_by='u1') is True
    assert svc.apply(CNT_LINE_OBJECT, 1, TOLERANCE_RULE_ID,
                     code='X', reason='重复', applied_by='u1') is False
    assert len(_holds(conn)) == 1
    assert svc.is_held(CNT_LINE_OBJECT, 1, TOLERANCE_RULE_ID) is True
    assert svc.active_holds(CNT_LINE_OBJECT, 1)[0]['reason'] == '超容差'

    # 部分唯一索引兜底：绕过服务直插同键 active 行必须失败
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            'INSERT INTO holds (object_type, record_id, rule_key, applied_at) '
            'VALUES (?, ?, ?, ?)',
            [CNT_LINE_OBJECT, 1, TOLERANCE_RULE_ID, '2026-11-10 00:00:00'])


def test_release_updates_timestamp_keeps_row_and_allows_reapply():
    conn = adj.build_adjustment_db()
    svc = RuleHoldService(_ds(conn))
    svc.apply(CNT_LINE_OBJECT, 2, TOLERANCE_RULE_ID, applied_by='u1')

    assert svc.release(CNT_LINE_OBJECT, 2, rule_key=TOLERANCE_RULE_ID,
                       released_by='u2') == 1
    assert svc.is_held(CNT_LINE_OBJECT, 2) is False
    row = _holds(conn)[0]
    assert row['released_by'] == 'u2'
    assert row['released_at'] is not None

    # 释放不删行；再次挂起产生新的 active 行（历史保留）
    assert svc.apply(CNT_LINE_OBJECT, 2, TOLERANCE_RULE_ID,
                     applied_by='u1') is True
    assert len(_holds(conn)) == 2
    assert svc.release(CNT_LINE_OBJECT, 2, rule_key='other_rule') == 0


# ---------------- 盘点接线 ----------------

def test_submit_over_tolerance_creates_hold_and_approve_releases():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 12, reason='盘亏')

    result = service.submit(count_id, {'username': 'submitter'})
    assert result['status'] == 'submitted'
    assert result['over_tolerance_lines'] == [1]

    holds = _holds(conn)
    assert len(holds) == 1
    assert holds[0]['object_type'] == CNT_LINE_OBJECT
    assert holds[0]['record_id'] == line['id']
    assert holds[0]['rule_key'] == TOLERANCE_RULE_ID
    assert holds[0]['code'] == 'INV_COUNT_TOLERANCE_EXCEEDED'
    assert holds[0]['reason'] == '盘亏'
    assert holds[0]['applied_by'] == 'submitter'
    assert holds[0]['released_at'] is None

    assert service.approve(count_id, {'username': 'approver'})['status'] == 'approved'
    holds = _holds(conn)
    assert len(holds) == 1
    assert holds[0]['released_by'] == 'approver'
    assert holds[0]['released_at'] is not None


def test_submit_within_tolerance_creates_no_hold():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 10.2)

    assert service.submit(count_id)['status'] == 'approved'
    assert _holds(conn) == []


def test_cancel_releases_active_hold_without_deleting_rows():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 12, reason='盘亏')
    service.submit(count_id)

    assert service.cancel(count_id, {'username': 'canceller'})['status'] == 'cancelled'
    holds = _holds(conn)
    assert len(holds) == 1
    assert holds[0]['released_by'] == 'canceller'
    assert holds[0]['released_at'] is not None
    assert v231.TABLE == 'holds'


def test_approve_releases_all_active_rules_not_only_tolerance():
    """审批放行必须清空本单所有规则的 active holds，不能只放 tolerance 规则。"""
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 12, reason='盘亏')
    service.submit(count_id, {'username': 'submitter'})

    # 其他规则（非容差）也挂起同一行
    assert service.holds.apply(CNT_LINE_OBJECT, line['id'], 'R-INV-OTHER',
                               code='OTHER', applied_by='submitter') is True
    assert len([h for h in _holds(conn) if h['released_at'] is None]) == 2

    service.approve(count_id, {'username': 'approver'})
    holds = _holds(conn)
    assert len(holds) == 2
    assert all(h['released_at'] is not None for h in holds)
    assert all(h['released_by'] == 'approver' for h in holds)


def test_post_blocked_while_active_hold():
    """可存不可过：存在 active hold 时过账被拒绝。"""
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 12, reason='盘亏')
    service.submit(count_id, {'username': 'submitter'})
    service.approve(count_id, {'username': 'approver'})

    # 审批后才由其他规则（如质量挂起）产生的 hold
    assert service.holds.apply(CNT_LINE_OBJECT, line['id'], 'R-INV-QUALITY',
                               code='QUALITY_HOLD', applied_by='inspector') is True
    with pytest.raises(InventoryError) as exc:
        service.post(count_id, {'username': 'poster'})
    assert exc.value.code == INV_COUNT_HELD
    assert exc.value.details['lines'] == [1]

    # 释放后不再因 hold 被拦截
    service.holds.release(CNT_LINE_OBJECT, line['id'])
    assert service.holds.is_held(CNT_LINE_OBJECT, line['id']) is False


# ---------------- 查询 / 删除级联 ----------------

def test_list_holds_returns_active_holds_with_line_no():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 12, reason='盘亏')
    service.submit(count_id, {'username': 'submitter'})

    items = service.list_holds(count_id)
    assert len(items) == 1
    assert items[0]['line_id'] == line['id']
    assert items[0]['line_no'] == 1
    assert items[0]['holds'][0]['rule_key'] == TOLERANCE_RULE_ID
    assert items[0]['holds'][0]['reason'] == '盘亏'

    service.approve(count_id, {'username': 'approver'})
    assert service.list_holds(count_id) == []


def test_line_delete_via_interceptor_releases_active_holds():
    from types import SimpleNamespace

    from meta.core.interceptors.inventory_count_guard_interceptor import (
        InventoryCountGuardInterceptor,
    )

    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn)
    service.start(count_id)
    values = service.prepare_line_create(
        count_id, {'item_id': inv.ITEM_ID, 'counted_qty': 1})
    line_id = adj.insert_row(conn, 'inventory_count_lines', values)
    assert service.holds.apply(CNT_LINE_OBJECT, line_id, 'R-INV-OTHER',
                               code='OTHER', applied_by='u1') is True

    context = SimpleNamespace(
        meta_object=SimpleNamespace(id='inventory_count_line'),
        action='crud_delete', params={'id': line_id}, object_id=line_id,
        data_source=_ds(conn), old_data={'count_id': count_id},
        user_info={'username': 'deleter'})
    InventoryCountGuardInterceptor().before_action(context)

    assert service.holds.is_held(CNT_LINE_OBJECT, line_id) is False
    row = _holds(conn)[0]
    assert row['released_by'] == 'deleter'
    assert row['released_at'] is not None


def test_release_holds_for_count_releases_every_line():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    extra = service.prepare_line_create(
        count_id, {'item_id': inv.ITEM_ID, 'counted_qty': 0.5})
    extra_id = adj.insert_row(conn, 'inventory_count_lines', extra)
    line = [row for row in _lines(conn, count_id)
            if row['source_balance_id']][0]
    _set_counted(conn, line['id'], 12, reason='盘亏')
    service.submit(count_id, {'username': 'submitter'})
    assert service.holds.apply(CNT_LINE_OBJECT, extra_id, 'R-INV-OTHER',
                               applied_by='u1') is True

    assert service.release_holds_for_count(
        count_id, {'username': 'deleter'}) == 2
    assert service.list_holds(count_id) == []
    assert all(row['released_at'] is not None for row in _holds(conn))