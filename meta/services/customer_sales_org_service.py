# -*- coding: utf-8 -*-
"""客户销售组织默认值解析 —— 账户级默认值的组织段覆盖（W1-B）。

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
      §4.3（解析链）/ §4.5（W1-R10 ~ W1-R12）

解析链（逐字段回退，禁止整行覆盖 · W1-R10）：

    默认值(field) = 组织行存在且该字段非空 ? 组织行.field : 账户行.field

- 组织行按 `(customer_account_id, sales_org_id)` 取，且只认 `status='active'`；
  停用行不再作为默认值来源。
- 未配置组织行时输出与账户级完全一致（零回归）。
- 账户行没有的字段（如 currency_id）只取组织行，取不到即不输出。
- 读侧异常一律 fail-open + WARNING：默认值补全不应把保存路径打死。

字段名映射（组织行 → 账户行）：

    payment_term_id        → default_payment_term_id
    incoterm_code          → default_incoterm_code
    tax_classification_id  → tax_classification_id
    rate_table_id          → default_rate_table_id
    currency_id            → （账户无此字段）
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: 组织段可覆盖的全部字段（对象契约）
OVERRIDE_FIELDS = (
    'payment_term_id',
    'incoterm_code',
    'tax_classification_id',
    'rate_table_id',
    'currency_id',
)

#: 销售订单抬头当前消费的覆盖字段（其余字段暂无消费者）
ORDER_DEFAULT_FIELDS = ('payment_term_id', 'incoterm_code')

#: 组织行字段 → 账户行字段；None 表示账户级无对应来源
_ACCOUNT_SOURCE: Dict[str, Optional[str]] = {
    'payment_term_id': 'default_payment_term_id',
    'incoterm_code': 'default_incoterm_code',
    'tax_classification_id': 'tax_classification_id',
    'rate_table_id': 'default_rate_table_id',
    'currency_id': None,
}


def _is_blank(value: Any) -> bool:
    return value is None or value == ''


class CustomerSalesOrgService:
    """按客户档案 + 销售组织解析默认值的组织段覆盖。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    def resolve(self, customer_account_id: Any, sales_org_id: Any,
                fields=OVERRIDE_FIELDS) -> Dict[str, Any]:
        """返回 `{field: value}`；只含非空值，未定义字段不出现。

        `customer_account_id` 缺失时直接返回空（无可回退的账户级来源）。
        """
        if _is_blank(customer_account_id):
            return {}

        override = self.load_override(customer_account_id, sales_org_id)
        account = self.load_account_defaults(customer_account_id)

        resolved: Dict[str, Any] = {}
        for field in fields:
            value = override.get(field)
            if _is_blank(value):
                source = _ACCOUNT_SOURCE.get(field)
                value = account.get(source) if source else None
            if not _is_blank(value):
                resolved[field] = value
        return resolved

    def load_override(self, customer_account_id: Any,
                      sales_org_id: Any) -> Dict[str, Any]:
        """读该客户在该销售组织下的启用差异行；无行/缺组织返回空。"""
        if _is_blank(customer_account_id) or _is_blank(sales_org_id):
            return {}
        columns = ', '.join(OVERRIDE_FIELDS)
        try:
            rows = self.ds.query(
                'SELECT {0} FROM customer_sales_orgs '
                'WHERE customer_account_id = ? AND sales_org_id = ? '
                "AND status = 'active' LIMIT 1".format(columns),
                [customer_account_id, sales_org_id])
        except Exception as e:  # 读侧异常 → fail-open
            logger.warning('[customer_sales_org] 读取组织差异失败: %s', e)
            return {}
        return rows[0] if rows else {}

    def load_account_defaults(self, customer_account_id: Any) -> Dict[str, Any]:
        """读账户级默认值（回退来源）。"""
        if _is_blank(customer_account_id):
            return {}
        try:
            rows = self.ds.query(
                'SELECT default_payment_term_id, default_incoterm_code, '
                'tax_classification_id, default_rate_table_id '
                'FROM customer_accounts WHERE id = ?',
                [customer_account_id])
        except Exception as e:  # 读侧异常 → fail-open
            logger.warning('[customer_sales_org] 读取客户档案默认值失败: %s', e)
            return {}
        return rows[0] if rows else {}
