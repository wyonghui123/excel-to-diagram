# -*- coding: utf-8 -*-
"""销售员默认值解析 —— 订单抬头 salesperson_id 的自动带出（W1-D）。

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
      §6.3（订单接线）/ §6.5（W1-R16 ~ W1-R18）

解析链：

    salesperson = assignment(客户, 销售组织, active, 有效期覆盖基准日, is_primary=1)
                  ?? assignment(客户, NULL,   active, 有效期覆盖基准日, is_primary=1)
                  ?? NULL

- 只认 `is_primary=1`、`customer_salesperson_assignments.status='active'`，
  且销售员本身 `status='active'` 的行（W1-R17）。
- 有效期口径：`valid_from`（含）~ `valid_to`（不含）；任一为空按无界处理。
  基准日取订单 `price_date`；为空时忽略有效期约束（避免带不出销售员）。
- 读侧异常一律 fail-open + WARNING：默认值补全不应把保存路径打死。
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _is_blank(value: Any) -> bool:
    return value is None or value == ''


class SalespersonService:
    """按客户 + 销售组织 + 基准日解析主销售员。"""

    def __init__(self, data_source):
        self.ds = data_source

    def resolve(self, customer_account_id: Any, sales_org_id: Any,
                price_date: Any = None) -> Optional[int]:
        """返回主销售员 id；无匹配返回 None。"""
        if _is_blank(customer_account_id):
            return None

        sql = [
            'SELECT a.salesperson_id FROM customer_salesperson_assignments a '
            'JOIN salespersons s ON s.id = a.salesperson_id '
            'WHERE a.customer_account_id = ? AND a.is_primary = 1 '
            "AND a.status = 'active' AND s.status = 'active' "
            'AND (a.sales_org_id = ? OR a.sales_org_id IS NULL)'
        ]
        params = [customer_account_id, sales_org_id]
        if not _is_blank(price_date):
            sql.append('AND (a.valid_from IS NULL OR a.valid_from <= ?) '
                       'AND (a.valid_to IS NULL OR a.valid_to > ?)')
            params.extend([price_date, price_date])
        # 组织专属优先于「所有组织通用」
        sql.append('ORDER BY CASE WHEN a.sales_org_id IS NULL THEN 1 ELSE 0 END, '
                   'a.id LIMIT 1')

        try:
            rows = self.ds.query(' '.join(sql), params)
        except Exception as e:  # 读侧异常 → fail-open
            logger.warning('[salesperson] 读取主销售员失败: %s', e)
            return None
        if not rows:
            return None
        value = rows[0].get('salesperson_id')
        return None if _is_blank(value) else value
