# -*- coding: utf-8 -*-
"""承诺层：策略表登记 + 统一入口委托。"""

from meta.services.commitment_policies import (
    PEG_SOFT,
    ROW_DEMAND_POLICIES,
)
from meta.services.commitment_service import CommitmentService


def _svc():
    from meta.tests.inventory_test_doubles import MemDS, build_db
    return CommitmentService(MemDS(build_db()))


def test_service_request_policy_is_registered():
    policy = ROW_DEMAND_POLICIES['service_request']
    assert policy['demand_object_type'] == 'service_order'
    assert policy['qty_field'] == 'qty'
    assert policy['peg_type'] == PEG_SOFT
    assert policy['doc_table'] == 'service_requests'
    assert policy['line_table'] == 'service_request_lines'


def test_reservation_service_reads_the_same_policy_table():
    from meta.services.inventory_reservation_service import (
        ROW_DEMAND_POLICIES as SERVICE_POLICIES,
    )
    assert SERVICE_POLICIES is ROW_DEMAND_POLICIES


def test_facade_sync_delegates_to_reservation_engine():
    result = _svc().sync('unknown_doc', 1)
    assert result['created'] == 0
    assert result['reason'] == 'POLICY_NOT_REGISTERED'


def test_facade_exposes_low_level_service():
    service = _svc()
    assert service.reservations is not None


def test_receipt_posted_handler_registered():
    from meta.services.commitment_handlers import HANDLERS
    assert 'receipt.posted' in HANDLERS


def test_register_is_idempotent():
    from meta.services.commitment_handlers import HANDLERS, register

    calls = []

    def handler(payload):
        calls.append(payload)

    register('x.event', handler)
    register('x.event', handler)
    assert HANDLERS['x.event'] == [handler]


def test_dispatch_invokes_receipt_handler(monkeypatch):
    from meta.services import commitment_handlers
    from meta.services.commitment_service import CommitmentService

    seen = []
    monkeypatch.setattr(
        CommitmentService, 'fulfill_work_order_components',
        lambda self, work_order_id, completed_qty=None, tx_id=0: seen.append(
            (work_order_id, completed_qty)))

    commitment_handlers.dispatch('receipt.posted', {
        'data_source': object(),
        'work_order_id': 77,
        'completed_qty': 3.0,
    })
    assert seen == [(77, 3.0)]
