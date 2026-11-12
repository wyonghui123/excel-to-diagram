# -*- coding: utf-8 -*-
"""INV-4 调整单服务测试（spec define-inventory-adjustment FR-001/002/003/008/009/010）。

覆盖:
  · 单号生成 / 默认复核口径；
  · 无行、手工 count_difference、draft 未 release 过账的拦截；
  · 数量增加 / 减少 / 报废（含 blocked 批次）落账与余额；
  · 状态变更成对分录、transfer_group_id、批次 quality_status 不变（TBD-5）；
  · 红冲单据 / 事务 / 余额回滚 / 重复红冲；
  · 取消与删除（行）守卫。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import re

import pytest

pytestmark = pytest.mark.unit

from meta.core.interceptors.permission_interceptor import PermissionDenied
from meta.services.inventory_adjustment_service import (
    INV_ADJ_NO_LINES, INV_ADJ_RELEASE_REQUIRED, INV_ADJ_STATUS_PAIR_INVALID,
    INV_ADJ_TYPE_FORBIDDEN, INV_ALREADY_REVERSED, INV_DOC_POSTED_LOCKED,
)
from meta.services.inventory_guard_service import (
    INV_BATCH_BLOCKED, InventoryError,
)
from meta.tests import inventory_adjustment_doubles as adj
from meta.tests import inventory_test_doubles as inv


def _rows(conn, sql, params=None):
    return inv.MemDS(conn).query(sql, params or [])


def _create(conn, adj_type='qty_increase', qty=5.0, reason_code=None,
            lines=None):
    service = adj.adjustment_service(conn)
    payload = {
        'adjustment_type': adj_type,
        'org_id': inv.ORG_ID,
        'location_id': inv.LOCATION_ID,
        'posting_date': adj.DEFAULT_DATE,
    }
    if reason_code is not None:
        payload['reason_code'] = reason_code
    header = service.prepare_create(payload)
    header_id = adj.insert_adjustment(conn, header)
    if lines is None:
        lines = [{}]
    for spec in lines:
        spec = dict(spec)
        spec.setdefault('qty', qty)
        if adj_type in ('qty_increase', 'opening'):
            spec.setdefault('to_stock_status', 'unrestricted')
        elif adj_type in ('qty_decrease', 'scrap'):
            spec.setdefault('from_stock_status', 'unrestricted')
            spec.setdefault('cost_center_id', 1)
            spec.setdefault('expense_account_code', '6601.01')
        adj.add_adjustment_line(conn, header_id, **spec)
    return header_id, header, service


# ---------------- 创建归一 ----------------

def test_prepare_create_generates_monthly_no_draft_and_release_required():
    conn = adj.build_adjustment_db()
    service = adj.adjustment_service(conn)

    data = service.prepare_create({
        'adjustment_type': 'qty_increase',
        'org_id': inv.ORG_ID,
        'location_id': inv.LOCATION_ID,
        'posting_date': adj.DEFAULT_DATE,
        'reason_code': 'correction',
    })

    assert re.fullmatch(r'ADJ-\d{6}-000001', data['adjustment_no'])
    assert data['status'] == 'draft'
    assert data['posting_date'] == adj.DEFAULT_DATE
    # FR-006 / TBD-1：默认要求复核
    default = conn.execute(
        'SELECT default_value FROM control_parameter_defs '
        'WHERE code=?', ['inventory_adjustment_release_required']).fetchone()
    assert default[0] == '1'


def test_post_without_lines_returns_no_lines_and_manual_count_diff_forbidden():
    conn = adj.build_adjustment_db()
    # 关闭复核要求，让 post 直接触发行校验
    inv.set_param(conn, 'inventory_adjustment_release_required', '0')
    conn.commit()

    header_id, _header, service = _create(conn, 'qty_increase', lines=[])
    with pytest.raises(InventoryError) as exc:
        service.post(header_id)
    assert exc.value.code == INV_ADJ_NO_LINES

    with pytest.raises(InventoryError) as exc:
        service.prepare_create({
            'adjustment_type': 'count_difference',
            'org_id': inv.ORG_ID,
            'location_id': inv.LOCATION_ID,
        })
    assert exc.value.code == INV_ADJ_TYPE_FORBIDDEN


# ---------------- 数量调整 ----------------

def test_release_required_blocks_draft_post_then_release_allows_post():
    conn = adj.build_adjustment_db()
    header_id, header, service = _create(conn, 'qty_increase', 5.0)

    with pytest.raises(InventoryError) as exc:
        service.post(header_id)
    assert exc.value.code == INV_ADJ_RELEASE_REQUIRED

    service.release(header_id)
    result = service.post(header_id)

    assert result['created'] == 1
    assert result['status'] == 'posted'
    tx = _rows(conn, 'SELECT * FROM inventory_transactions')[0]
    assert tx['source_doc_type'] == 'inventory_adjustment'
    assert tx['source_doc_id'] == header_id
    assert tx['source_event_key'] == 'adjustment:%s' % header['adjustment_no']
    assert tx['direction'] == 'in'
    assert adj.balance_qty(conn) == 5.0

    posted = _rows(conn, 'SELECT status, posted_at FROM inventory_adjustments '
                         'WHERE id=?', [header_id])[0]
    assert posted['status'] == 'posted'
    assert posted['posted_at']


def test_qty_decrease_reduces_balance_and_scrap_allows_blocked_batch():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)

    header_id, _header, service = _create(conn, 'qty_decrease', 4)
    service.release(header_id)
    service.post(header_id)
    assert adj.balance_qty(conn) == 6.0
    tx = _rows(conn, 'SELECT direction, stock_status FROM inventory_transactions '
                     'ORDER BY id DESC LIMIT 1')[0]
    assert tx['direction'] == 'out' and tx['stock_status'] == 'unrestricted'

    # blocked 批次 + blocked 桶：报废放行（FR-009 allow_blocked_batch）
    conn.execute("UPDATE batches SET quality_status='blocked' WHERE id=?",
                 [inv.BATCH_ID])
    conn.commit()
    adj.post_balance(conn, 5, batch_id=inv.BATCH_ID, stock_status='blocked')

    scrap_id, _header, scrap_service = _create(
        conn, 'scrap', 3, reason_code='scrap',
        lines=[{'batch_id': inv.BATCH_ID, 'from_stock_status': 'blocked'}])
    scrap_service.release(scrap_id)
    result = scrap_service.post(scrap_id)

    assert result['created'] == 1
    assert adj.balance_qty(conn, batch_id=inv.BATCH_ID,
                           stock_status='blocked') == 2.0
    assert adj.balance_qty(conn) == 6.0
    scrap_tx = _rows(
        conn,
        'SELECT ty.code, t.direction FROM inventory_transactions t '
        'JOIN inventory_transaction_types ty ON ty.id=t.transaction_type_id '
        "WHERE t.source_event_key=? ORDER BY t.id DESC LIMIT 1",
        ['adjustment:%s' % _header['adjustment_no']])[0]
    assert scrap_tx['code'] == 'SCRAP' and scrap_tx['direction'] == 'out'


# ---------------- 状态变更 ----------------

def test_status_transfer_rejects_identical_from_to():
    conn = adj.build_adjustment_db()
    header_id, _header, service = _create(conn, 'status_transfer', 6, lines=[])

    with pytest.raises(InventoryError) as exc:
        service.prepare_line_create(header_id, {
            'item_id': inv.ITEM_ID,
            'qty': 6,
            'from_stock_status': 'inspection',
            'to_stock_status': 'inspection',
        })
    assert exc.value.code == INV_ADJ_STATUS_PAIR_INVALID


def test_status_transfer_posts_pair_and_keeps_batch_quality_status():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 6, batch_id=inv.BATCH_ID,
                     stock_status='inspection')

    header_id, _header, service = _create(
        conn, 'status_transfer', 6,
        lines=[{'batch_id': inv.BATCH_ID,
                'from_stock_status': 'inspection',
                'to_stock_status': 'blocked'}])
    service.release(header_id)
    result = service.post(header_id)
    assert result['created'] == 2

    txs = _rows(conn, 'SELECT * FROM inventory_transactions ORDER BY id')
    out = [t for t in txs
           if str(t['source_line_id'] or '').endswith(':out')][0]
    inn = [t for t in txs
           if str(t['source_line_id'] or '').endswith(':in')][0]
    assert out['transfer_group_id'] == inn['transfer_group_id']
    assert out['transfer_group_id']
    assert str(out['source_line_id']).endswith(':out')
    assert str(inn['source_line_id']).endswith(':in')

    assert adj.balance_qty(conn, batch_id=inv.BATCH_ID,
                           stock_status='inspection') == 0.0
    assert adj.balance_qty(conn, batch_id=inv.BATCH_ID,
                           stock_status='blocked') == 6.0
    # TBD-5：状态变更不同步批次主数据
    quality = conn.execute(
        'SELECT quality_status FROM batches WHERE id=?',
        [inv.BATCH_ID]).fetchone()[0]
    assert quality == 'unrestricted'


# ---------------- 红冲 / 取消 ----------------

def test_reverse_creates_red_document_and_rolls_back_balance():
    conn = adj.build_adjustment_db()
    header_id, header, service = _create(conn, 'qty_increase', 5)
    service.release(header_id)
    service.post(header_id)

    result = service.reverse(header_id)
    assert result['created'] == 1
    reversal_id = result['reversal_adjustment_id']

    reversal = _rows(conn, 'SELECT * FROM inventory_adjustments WHERE id=?',
                     [reversal_id])[0]
    assert reversal['reversal_of_adjustment_id'] == header_id
    assert reversal['adjustment_type'] == 'qty_increase'
    assert reversal['status'] == 'posted'
    assert reversal['adjustment_no'] == result['reversal_adjustment_no']

    original = _rows(conn,
                     'SELECT status FROM inventory_adjustments WHERE id=?',
                     [header_id])[0]
    assert original['status'] == 'reversed'

    reversal_txs = _rows(
        conn,
        'SELECT ty.code, t.source_event_key, t.reversal_of_transaction_id '
        'FROM inventory_transactions t '
        'JOIN inventory_transaction_types ty ON ty.id=t.transaction_type_id '
        'WHERE t.reversal_of_transaction_id IS NOT NULL')
    assert len(reversal_txs) == 1
    assert reversal_txs[0]['code'] == 'REVERSAL'
    assert reversal_txs[0]['source_event_key'] == 'reversal:%s' % \
        header['adjustment_no']
    assert adj.balance_qty(conn) == 0.0

    with pytest.raises(InventoryError) as exc:
        service.reverse(header_id)
    assert exc.value.code == INV_ALREADY_REVERSED


def test_reverse_goes_through_reversal_orchestrator(monkeypatch):
    """D2：红冲必须经 ReversalOrchestrator（声明式写面 + 红字单创建器）。"""
    from meta.core import reversal_orchestrator

    conn = adj.build_adjustment_db()
    header_id, _header, service = _create(conn, 'qty_increase', 5)
    service.release(header_id)
    service.post(header_id)

    seen = []
    real_execute = reversal_orchestrator.execute

    def spy(ds, **kwargs):
        seen.append(kwargs.get('schema_id'))
        return real_execute(ds, **kwargs)

    monkeypatch.setattr(reversal_orchestrator, 'execute', spy)
    result = service.reverse(header_id)

    assert seen == ['inventory_adjustment']
    assert result['reversal_adjustment_id']


def test_cancel_allows_draft_and_released_only():
    conn = adj.build_adjustment_db()

    draft_id, _draft, draft_service = _create(conn, 'qty_increase', 1)
    assert draft_service.cancel(draft_id)['status'] == 'cancelled'

    released_id, _released, released_service = _create(conn, 'qty_increase', 1)
    released_service.release(released_id)
    assert released_service.cancel(released_id)['status'] == 'cancelled'

    posted_id, _posted, posted_service = _create(conn, 'qty_increase', 1)
    posted_service.release(posted_id)
    posted_service.post(posted_id)
    with pytest.raises(InventoryError) as exc:
        posted_service.cancel(posted_id)
    assert exc.value.code == INV_DOC_POSTED_LOCKED


# ---------------- 删除 / 行守卫 ----------------

def test_deletable_and_line_guards_reject_non_draft_documents():
    conn = adj.build_adjustment_db()
    header_id, _header, service = _create(conn, 'qty_increase', 2)
    line_id = _rows(conn, 'SELECT id FROM inventory_adjustment_lines '
                          'WHERE adjustment_id=?', [header_id])[0]['id']

    assert service.assert_deletable(header_id)['status'] == 'draft'
    service.release(header_id)
    with pytest.raises(InventoryError) as exc:
        service.assert_deletable(header_id)
    assert exc.value.code == INV_DOC_POSTED_LOCKED

    service.post(header_id)
    with pytest.raises(InventoryError) as exc:
        service.prepare_line_create(header_id, {
            'item_id': inv.ITEM_ID, 'qty': 1,
            'to_stock_status': 'unrestricted'})
    assert exc.value.code == INV_DOC_POSTED_LOCKED

    with pytest.raises(InventoryError) as exc:
        service.prepare_line_update(header_id, line_id,
                                    {'qty': 3})
    assert exc.value.code == INV_DOC_POSTED_LOCKED

    with pytest.raises(InventoryError) as exc:
        service.assert_line_deletable(header_id, line_id)
    assert exc.value.code == INV_DOC_POSTED_LOCKED


# ---------------- 幂等 / 期初权限 / 批次冻结边界 ----------------

def test_repeat_post_is_idempotent_and_keeps_balance():
    """FR-010：同一调整单重复 post 返回 created=0，不产生第二条事务。"""
    conn = adj.build_adjustment_db()
    header_id, _header, service = _create(conn, 'qty_increase', 5)

    service.release(header_id)
    first = service.post(header_id)
    assert first['created'] == 1

    second = service.post(header_id)
    assert second['created'] == 0
    assert second['existing'] == 1
    assert adj.balance_qty(conn) == 5.0
    assert len(_rows(conn, 'SELECT id FROM inventory_transactions')) == 1


def test_opening_requires_opening_permission():
    """FR-013：opening 仅对持有 inventory_adjustment_opening 的用户开放。"""
    conn = adj.build_adjustment_db()
    service = adj.adjustment_service(conn)
    payload = {
        'adjustment_type': 'opening',
        'org_id': inv.ORG_ID,
        'location_id': inv.LOCATION_ID,
        'posting_date': adj.DEFAULT_DATE,
        'reason_code': 'opening',
    }

    with pytest.raises(PermissionDenied) as exc:
        service.prepare_create(payload)
    assert 'inventory_adjustment:opening' in str(exc.value)

    allowed = {'username': 'op',
               'permissions': ['inventory_adjustment:opening']}
    header = service.prepare_create(payload, allowed)
    header_id = adj.insert_adjustment(conn, header)
    adj.add_adjustment_line(conn, header_id, qty=7,
                            to_stock_status='unrestricted')

    service.release(header_id, allowed)
    result = service.post(header_id, user_info=allowed)
    assert result['created'] == 1
    code = _rows(
        conn,
        'SELECT ty.code FROM inventory_transactions t '
        'JOIN inventory_transaction_types ty ON ty.id=t.transaction_type_id')[0]
    assert code['code'] == 'OPENING'
    assert adj.balance_qty(conn) == 7.0


def test_blocked_batch_unrestricted_outbound_is_rejected():
    """FR-009：blocked 批次从 unrestricted 出库仍被 INV-1 规则拦截。"""
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 5, batch_id=inv.BATCH_ID)
    conn.execute("UPDATE batches SET quality_status='blocked' WHERE id=?",
                 [inv.BATCH_ID])
    conn.commit()

    header_id, _header, service = _create(
        conn, 'qty_decrease', 2, lines=[{'batch_id': inv.BATCH_ID}])
    service.release(header_id)
    with pytest.raises(InventoryError) as exc:
        service.post(header_id)
    assert exc.value.code == INV_BATCH_BLOCKED
    assert adj.balance_qty(conn, batch_id=inv.BATCH_ID) == 5.0


def test_status_transfer_from_blocked_bucket_allows_blocked_batch():
    """FR-009：blocked 批次从 blocked 桶转 unrestricted 允许（盘点/状态变更场景）。"""
    conn = adj.build_adjustment_db()
    conn.execute("UPDATE batches SET quality_status='blocked' WHERE id=?",
                 [inv.BATCH_ID])
    conn.commit()
    adj.post_balance(conn, 5, batch_id=inv.BATCH_ID,
                     stock_status='blocked')

    header_id, _header, service = _create(
        conn, 'status_transfer', 5,
        lines=[{'batch_id': inv.BATCH_ID,
                'from_stock_status': 'blocked',
                'to_stock_status': 'unrestricted'}])
    service.release(header_id)
    result = service.post(header_id)

    assert result['created'] == 2
    assert adj.balance_qty(conn, batch_id=inv.BATCH_ID,
                           stock_status='blocked') == 0.0
    assert adj.balance_qty(conn, batch_id=inv.BATCH_ID,
                           stock_status='unrestricted') == 5.0
