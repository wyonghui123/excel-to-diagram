# -*- coding: utf-8 -*-
"""INV-4 盘点单服务测试（spec FR-004 / FR-005 / FR-006 / §9.3.3）。

覆盖:
  · 创建默认 physical / CNT 单号 / posting_block 参数默认；
  · start 快照行（snapshot_qty / stock_status / source_balance_id / base_uom）；
  · submit 未录数、容差内自动审批、超容差必须填原因；
  · approve / post 生成 count_difference 调整单与盘点事务、余额增减；
  · 零差异过账拦截、红冲盘点调整单回滚；
  · cancel 保留快照、行守卫（手工行/快照行/更新白名单/状态校验）。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import re

import pytest

pytestmark = pytest.mark.unit

from meta.services.inventory_count_service import (
    INV_COUNT_INCOMPLETE, INV_COUNT_LINE_LOCKED, INV_COUNT_NO_DIFF,
    INV_COUNT_REASON_REQUIRED, INV_COUNT_STATE_INVALID, INV_DOC_POSTED_LOCKED,
)
from meta.services.inventory_guard_service import InventoryError
from meta.tests import inventory_adjustment_doubles as adj
from meta.tests import inventory_test_doubles as inv


def _rows(conn, sql, params=None):
    return inv.MemDS(conn).query(sql, params or [])


def _create_count(conn, **payload):
    service = adj.count_service(conn)
    data = service.prepare_create(dict(
        {'org_id': inv.ORG_ID, 'location_id': inv.LOCATION_ID}, **payload))
    return adj.insert_count(conn, data), data, service


def _lines(conn, count_id):
    return _rows(conn, 'SELECT * FROM inventory_count_lines WHERE count_id=? '
                       'ORDER BY line_no', [count_id])


def _set_counted(conn, line_id, qty, reason=None):
    conn.execute(
        'UPDATE inventory_count_lines SET counted_qty=?, variance_reason=? '
        'WHERE id=?', [qty, reason, line_id])
    conn.commit()


# ---------------- 创建 ----------------

def test_prepare_create_defaults_physical_and_posting_block_param():
    conn = adj.build_adjustment_db()
    _cid, data, _service = _create_count(conn)

    assert data['count_type'] == 'physical'
    assert re.fullmatch(r'CNT-\d{6}-000001', data['count_no'])
    assert data['status'] == 'draft'
    assert data['snapshot_at'] is None
    assert data['generated_adjustment_id'] is None
    # 参数默认 posting_block=0，容差比例 0
    assert data['posting_block'] == 0
    assert data['tolerance_qty_pct'] == 0.0

    # 参数改为 1 / 数值容差 0.1 后，新单取参数默认（set_numeric_param 覆盖 number 类型）
    inv.set_param(conn, 'inventory_count_posting_block_default', '1')
    adj.set_numeric_param(conn, 'inventory_count_default_tolerance_qty_pct', '0.1')
    conn.commit()
    _cid2, data2, _service2 = _create_count(conn)
    assert data2['posting_block'] == 1
    assert data2['tolerance_qty_pct'] == pytest.approx(0.1)


def test_prepare_create_cycle_type_allowed():
    conn = adj.build_adjustment_db()
    _cid, data, _service = _create_count(conn, count_type='cycle')
    assert data['count_type'] == 'cycle'


def test_tolerance_priority_header_over_parameter():
    """M6a-2：单据头 > 参数行 > def.default_value。"""
    conn = adj.build_adjustment_db()
    adj.set_numeric_param(conn, 'inventory_count_default_tolerance_qty_pct', '0.2')

    # 抬头显式填 0.05：不被参数 0.2 覆盖
    _cid, data, service = _create_count(conn, tolerance_qty_pct=0.05)
    assert data['tolerance_qty_pct'] == pytest.approx(0.05)
    assert service.resolve_tolerance(
        inv.ORG_ID, 0.05)['source']['qty_pct'] == 'header'

    # 抬头留空：回落参数 def.default_value
    _cid2, data2, service2 = _create_count(conn)
    assert data2['tolerance_qty_pct'] == pytest.approx(0.2)
    assert service2.resolve_tolerance(
        inv.ORG_ID)['source']['qty_pct'] == 'default'


def test_tolerance_parameter_row_specificity_beats_default():
    """参数行（specificity_rank 小者优先）> def.default_value。"""
    conn = adj.build_adjustment_db()
    adj.set_numeric_param(conn, 'inventory_count_default_tolerance_qty_pct', '0.1')
    def_id = conn.execute(
        'SELECT id FROM control_parameter_defs WHERE code=?',
        ['inventory_count_default_tolerance_qty_pct']).fetchone()[0]
    conn.executemany(
        'INSERT INTO control_parameter_values '
        '(control_parameter_id, value, org_id, specificity_rank, status) '
        "VALUES (?, ?, ?, ?, 'active')",
        [(def_id, '0.3', inv.ORG_ID, 20), (def_id, '0.25', inv.ORG_ID, 10)])
    conn.commit()

    _cid, data, service = _create_count(conn)
    assert data['tolerance_qty_pct'] == pytest.approx(0.25)
    info = service.params.explain(
        'inventory_count_default_tolerance_qty_pct', {'org_id': inv.ORG_ID})
    assert info['source']['type'] == 'value'
    assert info['source']['specificity_rank'] == 10


def test_tolerance_snapshot_not_drifted_by_parameter_change():
    """落库快照：建单后改参数，submit 仍按抬头快照判定。"""
    conn = adj.build_adjustment_db()
    adj.set_numeric_param(conn, 'inventory_count_default_tolerance_qty_pct', '0.2')
    adj.post_balance(conn, 10)
    count_id, data, service = _create_count(conn)
    assert data['tolerance_qty_pct'] == pytest.approx(0.2)

    # 参数改为 0；抬头快照仍是 0.2 → 5% 差异在容差内
    adj.set_numeric_param(conn, 'inventory_count_default_tolerance_qty_pct', '0')
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 10.5)

    result = service.submit(count_id)
    assert result['status'] == 'approved'
    assert result['over_tolerance_lines'] == []


# ---------------- start 快照 ----------------

def test_start_snapshots_nonzero_balances_with_item_base_uom():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    adj.post_balance(conn, 4, batch_id=inv.BATCH_ID,
                     stock_status='inspection')

    count_id, _data, service = _create_count(conn)
    result = service.start(count_id)

    assert result['status'] == 'counting'
    assert result['lines'] == 2
    header = _rows(conn, 'SELECT status, snapshot_at FROM inventory_counts '
                         'WHERE id=?', [count_id])[0]
    assert header['status'] == 'counting'
    assert header['snapshot_at']

    lines = _lines(conn, count_id)
    assert [line['snapshot_qty'] for line in lines] == [10.0, 4.0]
    assert [line['stock_status'] for line in lines] == [
        'unrestricted', 'inspection']
    for line in lines:
        assert line['uom_id'] == inv.UOM_ID  # items.base_uom
        assert line['source_balance_id']
        assert line['counted_qty'] is None
    assert lines[1]['batch_id'] == inv.BATCH_ID


# ---------------- submit / 容差 / 审批 ----------------

def test_submit_requires_all_counted_qty():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)

    with pytest.raises(InventoryError) as exc:
        service.submit(count_id)
    assert exc.value.code == INV_COUNT_INCOMPLETE


def test_submit_within_tolerance_auto_approves():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 10.2)

    result = service.submit(count_id)
    assert result['status'] == 'approved'
    assert result['over_tolerance_lines'] == []
    stored = _rows(conn, 'SELECT variance_qty FROM inventory_count_lines '
                         'WHERE id=?', [line['id']])[0]
    assert stored['variance_qty'] == pytest.approx(0.2)


def test_submit_over_tolerance_requires_variance_reason():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 12)

    with pytest.raises(InventoryError) as exc:
        service.submit(count_id)
    assert exc.value.code == INV_COUNT_REASON_REQUIRED

    _set_counted(conn, line['id'], 12, reason='盘亏')
    result = service.submit(count_id)
    assert result['status'] == 'submitted'
    assert result['over_tolerance_lines'] == [1]

    assert service.approve(count_id)['status'] == 'approved'


def test_auto_approve_disabled_keeps_submitted_even_in_tolerance():
    conn = adj.build_adjustment_db()
    inv.set_param(conn, 'inventory_count_auto_approve_in_tolerance', '0')
    conn.commit()
    adj.post_balance(conn, 10)

    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 10.2)

    result = service.submit(count_id)
    assert result['status'] == 'submitted'
    assert result['in_tolerance'] is True


# ---------------- post ----------------

def test_post_generates_count_difference_adjustment_and_balances():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    adj.post_balance(conn, 5, batch_id=inv.BATCH_ID,
                     stock_status='inspection')

    count_id, data, service = _create_count(conn, tolerance_qty_abs=10)
    service.start(count_id)
    lines = _lines(conn, count_id)
    for line in lines:
        if line['stock_status'] == 'unrestricted':
            _set_counted(conn, line['id'], 12)   # +2
        else:
            _set_counted(conn, line['id'], 3)    # -2
    service.submit(count_id)
    result = service.post(count_id)

    assert result['status'] == 'posted'
    assert result['created'] == 2
    adjustment_id = result['adjustment_id']

    header = _rows(conn, 'SELECT * FROM inventory_counts WHERE id=?',
                   [count_id])[0]
    assert header['status'] == 'posted'
    assert header['posted_at']
    assert header['generated_adjustment_id'] == adjustment_id

    adjustment = _rows(conn, 'SELECT * FROM inventory_adjustments WHERE id=?',
                       [adjustment_id])[0]
    assert adjustment['adjustment_type'] == 'count_difference'
    assert adjustment['status'] == 'posted'
    assert adjustment['source_count_id'] == count_id
    assert adjustment['reason_text'] == '盘点单 %s 差异' % data['count_no']

    adjustment_lines = _rows(
        conn, 'SELECT * FROM inventory_adjustment_lines '
              'WHERE adjustment_id=? ORDER BY line_no', [adjustment_id])
    assert len(adjustment_lines) == 2
    assert all(line['source_count_line_id'] for line in adjustment_lines)

    txs = _rows(
        conn,
        'SELECT t.*, ty.code FROM inventory_transactions t '
        'JOIN inventory_transaction_types ty ON ty.id=t.transaction_type_id '
        'WHERE t.source_event_key=?',
        ['count:%s' % data['count_no']])
    assert len(txs) == 2
    for tx in txs:
        assert tx['source_doc_type'] == 'inventory_count'
        assert tx['source_doc_id'] == count_id
    assert {tx['code'] for tx in txs} == {'COUNT_INCREASE', 'COUNT_DECREASE'}

    assert adj.balance_qty(conn) == 12.0
    assert adj.balance_qty(conn, batch_id=inv.BATCH_ID,
                           stock_status='inspection') == 3.0


def test_post_zero_difference_is_rejected():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=0.5)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 10)
    service.submit(count_id)
    assert _rows(conn, 'SELECT status FROM inventory_counts WHERE id=?',
                 [count_id])[0]['status'] == 'approved'

    with pytest.raises(InventoryError) as exc:
        service.post(count_id)
    assert exc.value.code == INV_COUNT_NO_DIFF


def test_reverse_count_difference_adjustment_rolls_back_via_count_event_key():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)

    count_id, data, service = _create_count(conn, tolerance_qty_abs=10)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 12)
    service.submit(count_id)
    posted = service.post(count_id)
    assert adj.balance_qty(conn) == 12.0

    adjustment_service = adj.adjustment_service(conn)
    reversal = adjustment_service.reverse(posted['adjustment_id'])
    assert reversal['created'] == 1

    original = _rows(conn, 'SELECT status FROM inventory_adjustments WHERE id=?',
                     [posted['adjustment_id']])[0]
    assert original['status'] == 'reversed'
    assert adj.balance_qty(conn) == 10.0

    reversal_txs = _rows(
        conn,
        'SELECT t.source_event_key, ty.code FROM inventory_transactions t '
        'JOIN inventory_transaction_types ty ON ty.id=t.transaction_type_id '
        'WHERE t.reversal_of_transaction_id IS NOT NULL')
    assert len(reversal_txs) == 1
    assert reversal_txs[0]['code'] == 'REVERSAL'
    assert reversal_txs[0]['source_event_key'] == 'reversal:%s' % \
        posted['adjustment_no']


# ---------------- cancel / 行守卫 ----------------

def test_cancel_counting_keeps_snapshot_lines():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn)
    service.start(count_id)
    assert len(_lines(conn, count_id)) == 1

    result = service.cancel(count_id)
    assert result['status'] == 'cancelled'
    assert _lines(conn, count_id)[0]['snapshot_qty'] == 10.0


def test_posted_count_rejects_post_and_cancel():
    """FR-007：盘点单 posted 后不可再 post / cancel。"""
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, tolerance_qty_abs=10)
    service.start(count_id)
    line = _lines(conn, count_id)[0]
    _set_counted(conn, line['id'], 12)
    service.submit(count_id)
    service.post(count_id)

    with pytest.raises(InventoryError) as exc:
        service.post(count_id)
    assert exc.value.code == INV_COUNT_STATE_INVALID

    with pytest.raises(InventoryError) as exc:
        service.cancel(count_id)
    assert exc.value.code == INV_DOC_POSTED_LOCKED

    with pytest.raises(InventoryError) as exc:
        service.assert_deletable(count_id)
    assert exc.value.code == INV_DOC_POSTED_LOCKED


def test_line_guards_manual_snapshot_and_edit_whitelist():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn)
    service.start(count_id)
    snapshot_line = _lines(conn, count_id)[0]

    # 手工行：snapshot_qty 强制 0，可删除
    manual = service.prepare_line_create(count_id, {
        'item_id': inv.ITEM_ID, 'counted_qty': 5, 'remark': '手工补录'})
    assert manual['snapshot_qty'] == 0
    assert manual['source_balance_id'] is None
    assert manual['line_no'] == 2
    assert manual['location_id'] == inv.LOCATION_ID
    manual_id = adj.insert_row(conn, 'inventory_count_lines', manual)
    assert service.assert_line_deletable(count_id, manual_id)['id'] == manual_id

    # 快照行不可删除
    with pytest.raises(InventoryError) as exc:
        service.assert_line_deletable(count_id, snapshot_line['id'])
    assert exc.value.code == INV_COUNT_LINE_LOCKED

    # 更新白名单：snapshot_qty 等字段被丢弃
    updated = service.prepare_line_update(count_id, snapshot_line['id'], {
        'counted_qty': 11, 'variance_reason': '盘盈', 'remark': '备注',
        'snapshot_qty': 999})
    assert 'snapshot_qty' not in updated
    assert updated['counted_qty'] == 11
    assert updated['variance_reason'] == '盘盈'
    assert updated['remark'] == '备注'

    # 非 counting 状态禁止新增 / 更新 / 删除行
    service.cancel(count_id)
    with pytest.raises(InventoryError) as exc:
        service.prepare_line_create(count_id, {'item_id': inv.ITEM_ID})
    assert exc.value.code == INV_COUNT_STATE_INVALID
    with pytest.raises(InventoryError) as exc:
        service.prepare_line_update(count_id, snapshot_line['id'],
                                    {'counted_qty': 1})
    assert exc.value.code == INV_COUNT_STATE_INVALID
    with pytest.raises(InventoryError) as exc:
        service.assert_line_deletable(count_id, manual_id)
    assert exc.value.code == INV_COUNT_STATE_INVALID
