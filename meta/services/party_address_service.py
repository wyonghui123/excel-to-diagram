# -*- coding: utf-8 -*-
"""往来单位默认地址解析 —— 订单收货 / 收票地址的自动带出（W1-C）。

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
      §5.3（订单侧接线）/ §5.5（W1-R13 ~ W1-R15）

解析链：

    ship_to_address = party_address(ship_to_party_id           , role='ship_to', is_default=1)
                      ?? party_address(售达方对应 party         , role='ship_to', is_default=1)
                      ?? NULL

    bill_to_address = party_address(bill_to_account 对应 party , role='bill_to', is_default=1)
                      ?? party_address(售达方对应 party         , role='bill_to', is_default=1)
                      ?? NULL

- 只认 `is_default=1`、`party_addresses.status='active'` 且地址本身 `active` 的行（W1-R14）。
- 地址留空不构成校验失败（W1-R15）：解析不到即返回 None。
- 读侧异常一律 fail-open + WARNING：默认值补全不应把保存路径打死。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ROLE_SHIP_TO = 'ship_to'
ROLE_BILL_TO = 'bill_to'

#: 订单抬头由本服务带出的字段
ADDRESS_FIELDS = ('ship_to_address_id', 'bill_to_address_id')

#: 抬头变更后需要重算地址的维度
PARTY_FIELDS = ('customer_account_id', 'ship_to_party_id', 'bill_to_account_id')


def _is_blank(value: Any) -> bool:
    return value is None or value == ''


class PartyAddressService:
    """按往来单位 + 地址角色解析默认地址。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    def resolve(self, context: dict) -> Dict[str, Any]:
        """返回 `{ship_to_address_id: int|None, bill_to_address_id: int|None}`。"""
        context = context or {}
        customer_party = self.account_party_id(context.get('customer_account_id'))
        ship_party = context.get('ship_to_party_id') or customer_party
        bill_party = self.account_party_id(context.get('bill_to_account_id')) \
            or customer_party
        return {
            'ship_to_address_id': self.default_address_id(ship_party, ROLE_SHIP_TO),
            'bill_to_address_id': self.default_address_id(bill_party, ROLE_BILL_TO),
        }

    def default_address_id(self, party_id: Any, role: str) -> Optional[int]:
        """该往来单位在该角色下的启用默认地址；无则 None。"""
        if _is_blank(party_id):
            return None
        try:
            rows = self.ds.query(
                'SELECT pa.address_id FROM party_addresses pa '
                'JOIN addresses a ON a.id = pa.address_id '
                'WHERE pa.party_id = ? AND pa.role = ? AND pa.is_default = 1 '
                "AND pa.status = 'active' AND a.status = 'active' "
                'ORDER BY pa.id LIMIT 1',
                [party_id, role])
        except Exception as e:  # 读侧异常 → fail-open
            logger.warning('[party_address] 读取默认地址失败: %s', e)
            return None
        if not rows:
            return None
        value = rows[0].get('address_id')
        return None if _is_blank(value) else value

    def account_party_id(self, customer_account_id: Any) -> Optional[int]:
        """客户档案 → 对手侧 party（客户档案挂在 party_relation 之上 1:1）。"""
        if _is_blank(customer_account_id):
            return None
        try:
            rows = self.ds.query(
                'SELECT pr.party2_id FROM customer_accounts ca '
                'JOIN party_relations pr ON pr.id = ca.relation_id '
                'WHERE ca.id = ?',
                [customer_account_id])
        except Exception as e:  # 读侧异常 → fail-open
            logger.warning('[party_address] 读取客户对应伙伴失败: %s', e)
            return None
        if not rows:
            return None
        value = rows[0].get('party2_id')
        return None if _is_blank(value) else value
