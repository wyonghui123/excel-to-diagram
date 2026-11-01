# -*- coding: utf-8 -*-
"""需求入口服务（M1）—— 提交取号与免审批判定。

依据:
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §2 M1
  docs/specs/spec-shared-service-center-object-model-2026-10-31.md §3.2 / S-D5
  docs/specs/spec-procurement-task-object-model-2026-10-31.md §3.2.1

口径:
  · 编号在「创建」时生成（业务键校验要求非空），格式 `{前缀}-{YYYYMMDD}-{6 位流水}`；
    提交时若仍缺号再补（兼容直接提交的调用方）。取号跟随调用方事务：极少数并发
    提交可能撞唯一约束，由数据库唯一索引兜底报错，不做独立事务取号
    （见 bo_api._allocate_sales_order_no 的硬约束说明）。
  · 审批策略为空即免审批：service_request 行引用的目录项
    `requires_approval = false` 且 `approval_policy` 为空/空对象时，提交直接落 approved。
  · requisition 在本里程碑没有治理配置载体（审批开关属 M3 的法人对/组织对配置），
    一律视为免审批。
  · 本服务不发写 SQL，只回答「要不要转 approved」；实际状态由状态机规则落库。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SERVICE_REQUEST_OBJECT = 'service_request'
REQUISITION_OBJECT = 'requisition'

#: 对象 → (表名, 单号列, 单号前缀)
_DOC_NO_SPEC = {
    SERVICE_REQUEST_OBJECT: ('service_requests', 'request_no', 'SR'),
    REQUISITION_OBJECT: ('requisitions', 'requisition_no', 'RQ'),
}

#: 「空审批策略」的等价文本（JSON 存空对象/空数组时也视为无策略）
_EMPTY_POLICY_TEXTS = ('', 'null', '{}', '[]', '""')


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


class DemandEntryService:
    """需求入口提交逻辑（只读查询 + 取号建议）。"""

    def __init__(self, data_source):
        self._ds = data_source

    # ---------------- 提交取号 ----------------

    def allocate_document_no(self, object_type: str, payload: Dict[str, Any]) -> Optional[str]:
        """提交时补单号；已带单号或不支撑的对象返回 None（不覆盖人工值）。"""
        spec = _DOC_NO_SPEC.get(object_type)
        if not spec:
            return None
        _, column, prefix = spec
        if not _blank(payload.get(column)):
            return None
        return self._next_document_no(spec[0], column, prefix)

    def _next_document_no(self, table: str, column: str, prefix: str) -> str:
        from datetime import datetime

        day = datetime.now().strftime('%Y%m%d')
        pattern = f'{prefix}-{day}-'
        rows = self._ds.query(
            f'SELECT {column} AS v FROM {table} '
            f'WHERE {column} LIKE ? ORDER BY {column} DESC LIMIT 1',
            [f'{pattern}%'],
        )
        last = rows[0]['v'] if rows else None
        seq = 1
        if last:
            try:
                seq = int(str(last).rsplit('-', 1)[-1]) + 1
            except (TypeError, ValueError):
                seq = 1
        return f'{pattern}{seq:06d}'

    # ---------------- 免审批判定 ----------------

    def is_approval_exempt(self, object_type: str, record_id: Any) -> bool:
        """提交后是否可直接落 approved（免审批）。"""
        if object_type == REQUISITION_OBJECT:
            # M1 无审批策略载体 → 免审批
            return True
        if object_type != SERVICE_REQUEST_OBJECT:
            return True
        if record_id in (None, ''):
            return False
        return not self._request_needs_approval(record_id)

    def _request_needs_approval(self, request_id: Any) -> bool:
        """任一行引用的目录项要求审批即需审批（goods 行 / 无目录项视为免审批）。"""
        rows = self._ds.query(
            'SELECT c.requires_approval AS requires_approval, '
            '       c.approval_policy AS approval_policy '
            'FROM service_request_lines l '
            'JOIN service_catalog_items c ON c.id = l.catalog_item_id '
            'WHERE l.request_id = ? AND l.status <> ?',
            [request_id, 'cancelled'],
        )
        for row in rows:
            if int(row.get('requires_approval') or 0) == 1:
                return True
            policy = row.get('approval_policy')
            if not (isinstance(policy, str) and policy.strip() in _EMPTY_POLICY_TEXTS):
                if policy is not None:
                    return True
        return False

    # ---------------- 行级合法性（A2） ----------------

    def validate_line(self, object_type: str, payload: Dict[str, Any]) -> None:
        """service 行必须有 catalog_item_id；goods 行必须有 item_id 且 qty>0。"""
        if object_type != 'service_request_line':
            return
        line_type = payload.get('line_type') or 'service'
        if line_type == 'service':
            if payload.get('catalog_item_id') in (None, ''):
                raise ValueError('服务请求行（service）必须选择目录项')
            return
        if line_type == 'goods':
            if payload.get('item_id') in (None, ''):
                raise ValueError('服务请求行（goods）必须选择物料')
            qty = payload.get('qty')
            if qty in (None, '') or float(qty) <= 0:
                raise ValueError('服务请求行（goods）数量必须大于 0')
