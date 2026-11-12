# -*- coding: utf-8 -*-
"""承诺平台入口。

对上层（拦截器、单据服务、事件处理器）暴露统一承诺动作：同步、释放、
关单校验、工单组件核销。低层原语仍在 InventoryReservationService，
本类只负责收敛入口，不重复实现预留逻辑。
"""


class CommitmentService:
    """承诺动作统一入口。"""

    def __init__(self, data_source, reservations=None):
        from meta.services.inventory_reservation_service import (
            InventoryReservationService)
        self._reservations = reservations or InventoryReservationService(
            data_source)

    @property
    def reservations(self):
        return self._reservations

    def sync(self, source_doc_type, doc_id):
        """按策略同步单据行需求（幂等）。"""
        return self._reservations.sync_document_row_demands(
            source_doc_type, doc_id)

    def release(self, source_doc_type, doc_id, line_id=None, reason=''):
        """释放单据（或单行）承诺。"""
        return self._reservations.release_by_source(
            source_doc_type, doc_id, line_id=line_id, reason=reason)

    def assert_closable(self, source_doc_type, doc_id):
        """关单前置校验：仍有未核销承诺时拒绝。"""
        return self._reservations.assert_source_closable(
            source_doc_type, doc_id)

    def fulfill_work_order_components(self, work_order_id, completed_qty=None,
                                      tx_id=0):
        """按累计完工量核销工单组件承诺。"""
        return self._reservations.fulfill_work_order_components(
            work_order_id, completed_qty=completed_qty, tx_id=tx_id)
