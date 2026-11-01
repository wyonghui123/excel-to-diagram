# -*- coding: utf-8 -*-
"""收货单守卫服务 —— 卸载 ReceiptGuardInterceptor 的写前校验。

依据: docs/specs/spec-receipt-object-model-2026-11-01.md §5.3（R-RC-0 ~ R-RC-18）

口径:
  · 状态迁移（draft → posted / cancelled、posted → reversed）只有
    `ReceiptService.post / cancel / reverse` 三个入口；本服务只校验「能不能迁」，
    不写任何业务字段（拦截器负责委托服务）。
  · 抬头创建（BO crud_create）复用 `ReceiptService.prepare_header`：来源校验、
    单据类型 R-RC-0、默认值带出、取号（R-RC-8 必须在事务外）。
  · R-RC-6 / R-RC-12：`posted` 之后数量、计划行、行号、批次序列冻结；
    仅允许补齐 `actual_arrival_date` 与 `remark`。
  · 红字单只能由 `reverse` 产生：标准单不得带 `reversal_of_receipt_id`，
    前端也不得直接把 `document_category` 写成 return 的单据「造」红字单。
"""

import logging
from typing import Any, Dict, Optional

from meta.services.receipt_service import (
    DOC_CATEGORY_RETURN,
    DOC_CATEGORY_STANDARD,
    ReceiptError,
    ReceiptService,
    STATUS_CANCELLED,
    STATUS_DRAFT,
    STATUS_POSTED,
    STATUS_REVERSED,
)

logger = logging.getLogger(__name__)

#: 已过账 / 已冲销后仍允许变更的字段（R-RC-12：时间类字段允许补齐）
POSTED_EDITABLE_FIELDS = ('status', 'actual_arrival_date', 'remark', 'updated_at')
#: 生成后不可变的头字段（R-RC-1 / R-RC-6）
IMMUTABLE_FIELDS = ('receipt_no', 'document_type_id', 'source_doc_type',
                    'source_doc_id', 'reversal_of_receipt_id')
#: 允许由用户直接触发的状态迁移（reversed 只能由 reverse 产生）
TRANSITION_TARGETS = (STATUS_POSTED, STATUS_CANCELLED)


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _status(value: Any) -> str:
    return str(value or '').strip().lower()


class ReceiptGuardService:
    """收货单头 / 行的写前校验。"""

    def __init__(self, data_source):
        self.ds = data_source
        self.service = ReceiptService(data_source)

    # ------------------------------------------------------------------ 抬头
    def prepare_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """归一化 BO 新建入参（单据类型 / 默认值 / 取号），返回可持久化的抬头。"""
        header, _order, doc_type = self.service.prepare_header(dict(data or {}))
        if doc_type.get('document_category') == DOC_CATEGORY_STANDARD \
                and not _blank(header.get('reversal_of_receipt_id')):
            raise ReceiptError('标准收货单不得引用冲销原单',
                               field_name='reversal_of_receipt_id',
                               rule='RC_DOC_TYPE_INVALID')
        if doc_type.get('document_category') == DOC_CATEGORY_RETURN \
                and _blank(header.get('reversal_of_receipt_id')):
            raise ReceiptError('红字收货单必须引用原单',
                               field_name='reversal_of_receipt_id',
                               rule='RC_DOC_TYPE_INVALID')
        return header

    def validate_header_update(self, data: Dict[str, Any],
                               old_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """校验抬头更新；返回目标状态（无状态变更时返回 None）。"""
        data = dict(data or {})
        old = dict(old_data or {})
        old_status = _status(old.get('status')) or STATUS_DRAFT
        target = _status(data.get('status')) if 'status' in data else old_status

        for field in IMMUTABLE_FIELDS:
            if field not in data:
                continue
            if _blank(old.get(field)):
                continue
            if data[field] != old.get(field):
                raise ReceiptError(
                    '收货单字段 %s 生成后不可修改' % field,
                    field_name=field, rule='RC_FIELD_IMMUTABLE')

        if old_status in (STATUS_POSTED, STATUS_REVERSED):
            changed = [key for key in data
                       if key not in POSTED_EDITABLE_FIELDS
                       and data.get(key) != old.get(key)]
            if changed:
                raise ReceiptError(
                    '已过账 / 已冲销的收货单仅允许补齐到货时间与备注',
                    field_name=changed[0], rule='RC_POSTED_IMMUTABLE')

        if target != old_status:
            if target not in TRANSITION_TARGETS:
                raise ReceiptError(
                    '收货单状态不允许从 %s 迁移到 %s' % (old_status, target),
                    field_name='status', rule='RC_STATE_INVALID')
        return None if target == old_status else target

    def validate_delete(self, receipt_id: Any) -> None:
        self.service.assert_deletable(receipt_id)

    # ------------------------------------------------------------------ 行
    def validate_line_create(self, data: Dict[str, Any],
                             receipt_id: Any = None) -> Dict[str, Any]:
        payload = dict(data or {})
        return self.service.validate_new_line(
            payload, receipt_id or payload.get('receipt_id'))

    def validate_line_update(self, line_id: Any,
                             patch: Dict[str, Any]) -> Dict[str, Any]:
        return self.service.update_line(line_id, dict(patch or {}))

    def validate_line_delete(self, line_id: Any) -> None:
        self.service.assert_line_deletable(line_id)
