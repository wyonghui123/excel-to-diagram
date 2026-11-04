# -*- coding: utf-8 -*-
"""期初库存导入 —— INV-1 FR-013。

依据:
  .trae/specs/excel-to-diagram/define-inventory-model/spec.md FR-013 / TR-002

口径:
  ① 期初是余额初始化，生成 OPENING 分录；允许 unrestricted / inspection / blocked。
  ② 幂等键 = opening:{batch_no}；同一导入批次重复执行自动跳过，不重复记账。
  ③ 整批导入在一个事务内；任一行失败整体回滚，不产生半批数据。
  ④ 期初导入不受 inventory_posting_enabled 开关限制（开关是日常过账过渡开关）。
"""

import logging
import zlib
from typing import Any, Dict, List, Optional

from meta.services.inventory_guard_service import InventoryError
from meta.services.inventory_posting_service import InventoryPostingService

logger = logging.getLogger(__name__)


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False

TYPE_OPENING = 'OPENING'


class InventoryOpeningService:
    def __init__(self, data_source,
                 posting: Optional[InventoryPostingService] = None):
        self.ds = data_source
        self.posting = posting or InventoryPostingService(data_source)

    def import_opening(self, rows: List[Dict[str, Any]], batch_no: Any,
                       created_by: Any = None,
                       transaction_date: Any = None) -> Dict[str, Any]:
        """导入期初库存；返回 created / existing / skipped 统计。"""
        if _blank(batch_no):
            raise InventoryError('INV_OPENING_BATCH_REQUIRED',
                                 '期初导入批次号不能为空')
        if not rows:
            return {'batch_no': batch_no, 'created': 0, 'existing': [],
                    'rows': 0}

        event_key = 'opening:%s' % batch_no
        source_doc_id = zlib.crc32(str(batch_no).encode('utf-8'))
        entries = []
        for index, row in enumerate(rows, start=1):
            entries.append({
                'transaction_type': TYPE_OPENING,
                'transaction_date': row.get('transaction_date'),
                'org_id': row.get('org_id'),
                'location_id': row.get('location_id'),
                'item_id': row.get('item_id'),
                'uom_id': row.get('uom_id'),
                'qty': row.get('qty'),
                'batch_id': row.get('batch_id'),
                'stock_status': row.get('stock_status') or 'unrestricted',
                'source_line_id': row.get('line_no') or index,
                'source_event_key': event_key,
                'created_by': created_by,
                'remark': row.get('remark') or '期初库存导入 %s' % batch_no,
            })

        with self.ds.transaction():
            result = self.posting.post(
                entries,
                {
                    'source_doc_type': 'opening',
                    'source_doc_id': source_doc_id,
                    'source_event_key': event_key,
                    'transaction_date': transaction_date,
                    'created_by': created_by,
                    'remark': '期初库存导入 %s' % batch_no,
                },
                allow_non_unrestricted=True,
                ignore_switch=True,
            )
        logger.info('[inventory] opening batch=%s rows=%s created=%s existing=%s',
                    batch_no, len(rows), result.get('created'),
                    len(result.get('existing') or []))
        return {
            'batch_no': batch_no,
            'event_key': event_key,
            'rows': len(rows),
            'created': result.get('created', 0),
            'existing': result.get('existing') or [],
            'transactions': result.get('transactions') or [],
        }
