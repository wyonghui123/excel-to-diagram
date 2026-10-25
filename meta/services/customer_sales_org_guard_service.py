# -*- coding: utf-8 -*-
"""客户销售组织守卫 —— 销售职能校验（W1-R11）。

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §4.5

规则：
  W1-R11  `sales_org_id` 必须具备 `sales` 职能 —— 服务层校验，不只靠前端的
          候选集收窄（`org_sales_org` 视图）。Excel 导入 / API 直写同样会走到这里。
  W1-R12  `(customer_account_id, sales_org_id)` 唯一 —— 由唯一索引
          `uidx_customer_sales_org_account_org` 兜底，框架把 UNIQUE 约束错误
          翻译成可读消息，本服务不重复实现。

查询失败一律 fail-open + WARNING（沿用 sales_order / currency_rate 守卫口径）。
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

SALES_FUNCTION = 'sales'


class CustomerSalesOrgGuardError(ValueError):
    """客户销售组织守卫拒绝写入。`field_name` / `rule` 供前端定位。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


class CustomerSalesOrgGuardService:
    """客户销售组织写入前的跨对象校验。覆写 `_org_has_function` 即可注入测试数据。"""

    def __init__(self, data_source):
        self.ds = data_source

    def validate_write(self, data: Dict[str, Any]) -> None:
        """创建 / 更新前校验。缺字段交给必填校验兜底，不在此处报错。"""
        sales_org_id = data.get('sales_org_id')
        if _is_blank(sales_org_id):
            return
        if not self._org_has_function(sales_org_id, SALES_FUNCTION):
            raise CustomerSalesOrgGuardError(
                '组织 {0} 不具备销售职能（sales），不能作为销售组织'.format(
                    sales_org_id),
                field_name='sales_org_id', rule='sales_org_not_sales')

    # ---------------- 查询（可覆写） ----------------

    def _org_has_function(self, org_id: Any, function_type: str) -> bool:
        try:
            rows = self.ds.query(
                'SELECT 1 FROM org_functions WHERE org_id = ? AND function_type = ? '
                'LIMIT 1', [org_id, function_type])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning('[customer_sales_org_guard] 读取组织职能 %s 失败: %s',
                           org_id, e)
            return True
        return bool(rows)


def _is_blank(value: Any) -> bool:
    return value is None or value == ''
