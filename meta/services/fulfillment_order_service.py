# -*- coding: utf-8 -*-
"""履约单建单服务 —— 批次 4a：编号 + 来源订单 / 客户 / 站点校验。

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.18.6
      docs/superpowers/specs/2026-10-29-so-wave3/tasks.md T4.5

口径:
  · 编号 `FO-<yyyyMM>-<3位seq>` 由 `_next_fulfillment_no()` 生成后回填。
  · 校验来源订单（必填且存在）、客户（若传入则必须存在，否则取订单抬头客户）、
    站点（正整数；站点对象批次 5 落地，暂不查表）。
  · **不建任务、不写 `workflow_runs`**（执行实例由 4b 编排批次驱动）。
  · 不写 `fulfillment_status`（INV-1 唯一写入口仍归 sales_order_fulfillment_service）。
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ORDERS_TABLE = 'fulfillment_orders'
SALES_ORDER_TABLE = 'sales_orders'
CUSTOMER_TABLE = 'customer_accounts'
CHANGE_EVENT_TABLE = 'change_events'

STATUS_DRAFT = 'draft'
FULFILLMENT_TYPES = ('delivery', 'pickup', 'onsite', 'remote')


class FulfillmentOrderError(ValueError):
    """履约单守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = '',
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule
        self.details = details or {}


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value: Any) -> bool:
    return value is None or value == ''


class FulfillmentOrderService:
    """履约单建单（业务锚），不含编排。"""

    def __init__(self, data_source):
        self.ds = data_source

    def create_fulfillment_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """创建履约单；返回 `{'id', 'fulfillment_no', 'status', 'fulfillment_type', ...}`。"""
        payload = dict(payload or {})

        order_id = payload.get('order_id')
        if _blank(order_id):
            raise FulfillmentOrderError('履约单必须关联来源订单',
                                        field_name='order_id',
                                        rule='FO_ORDER_REQUIRED')
        order = self._require_order(order_id)

        customer_account_id = payload.get('customer_account_id')
        if _blank(customer_account_id):
            customer_account_id = order.get('customer_account_id')
        else:
            self._require_customer(customer_account_id)

        site_id = payload.get('site_id')
        if not _blank(site_id):
            site_id = self._require_site(site_id)

        fulfillment_type = payload.get('fulfillment_type') or 'delivery'
        if str(fulfillment_type) not in FULFILLMENT_TYPES:
            raise FulfillmentOrderError(
                '履约类型非法：%s' % fulfillment_type,
                field_name='fulfillment_type', rule='FO_TYPE_INVALID')

        planned_date = payload.get('planned_date')
        if not _blank(planned_date):
            planned_date = self._require_date(planned_date)

        fulfillment_no = payload.get('fulfillment_no') \
            or self._next_fulfillment_no()
        status = payload.get('status') or STATUS_DRAFT
        now = _now()
        row = {
            'fulfillment_no': fulfillment_no,
            'order_id': order_id,
            'customer_account_id': customer_account_id,
            'site_id': site_id,
            'fulfillment_type': str(fulfillment_type),
            'status': status,
            'workflow_run_id': None,
            'planned_date': planned_date,
            'notes': payload.get('notes'),
            'created_at': now,
            'updated_at': now,
        }
        fulfillment_id = self._insert(ORDERS_TABLE, row)

        self._append_change_event(fulfillment_id, 'state_change',
                                  {'status': (None, status)})
        return {
            'id': fulfillment_id,
            'fulfillment_no': fulfillment_no,
            'status': status,
            'fulfillment_type': str(fulfillment_type),
            'order_id': order_id,
            'customer_account_id': customer_account_id,
            'site_id': site_id,
            'planned_date': planned_date,
        }

    # -------------------------------------------------------------- 内部

    def _require_order(self, order_id: Any) -> Dict[str, Any]:
        try:
            rows = self.ds.query(
                'SELECT id, customer_account_id FROM %s WHERE id = ?'
                % SALES_ORDER_TABLE, [order_id])
        except Exception as e:
            logger.warning('[fulfillment_order] 读取来源订单失败: %s', e)
            rows = []
        if not rows:
            raise FulfillmentOrderError('来源销售订单不存在',
                                        field_name='order_id',
                                        rule='FO_ORDER_NOT_FOUND')
        return rows[0]

    def _require_customer(self, customer_account_id: Any) -> None:
        try:
            rows = self.ds.query(
                'SELECT id FROM %s WHERE id = ?' % CUSTOMER_TABLE,
                [customer_account_id])
        except Exception as e:
            logger.warning('[fulfillment_order] 读取客户失败: %s', e)
            rows = []
        if not rows:
            raise FulfillmentOrderError('客户不存在',
                                        field_name='customer_account_id',
                                        rule='FO_CUSTOMER_NOT_FOUND')

    @staticmethod
    def _require_site(site_id: Any) -> int:
        """站点对象批次 5 落地，这里只做正整数校验（不查表）。"""
        try:
            value = int(site_id)
        except (TypeError, ValueError):
            raise FulfillmentOrderError('站点必须是正整数：%s' % site_id,
                                        field_name='site_id',
                                        rule='FO_SITE_INVALID')
        if value <= 0:
            raise FulfillmentOrderError('站点必须是正整数：%s' % site_id,
                                        field_name='site_id',
                                        rule='FO_SITE_INVALID')
        return value

    @staticmethod
    def _require_date(value: Any) -> str:
        text = str(value).strip()[:10]
        try:
            datetime.strptime(text, '%Y-%m-%d')
        except ValueError:
            raise FulfillmentOrderError('日期格式非法：%s' % value,
                                        field_name='planned_date',
                                        rule='FO_DATE_INVALID')
        return text

    def _next_fulfillment_no(self) -> str:
        prefix = 'FO-%s-' % datetime.now().strftime('%Y%m')
        rows = self.ds.query(
            'SELECT fulfillment_no FROM %s WHERE fulfillment_no LIKE ? '
            'ORDER BY id DESC LIMIT 1' % ORDERS_TABLE, [prefix + '%'])
        seq = 1
        if rows:
            tail = str(rows[0].get('fulfillment_no')).rsplit('-', 1)[-1]
            try:
                seq = int(tail) + 1
            except ValueError:
                seq = 1
        return '%s%03d' % (prefix, seq)

    def _insert(self, table: str, row: Dict[str, Any]) -> int:
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            table, ', '.join(columns), ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [row[c] for c in columns])
        return int(getattr(cursor, 'lastrowid', 0) or 0)

    def _append_change_event(self, fulfillment_id: Any, event_type: str,
                             changes: Dict[str, Any]) -> None:
        """§10.17 关系 C：复用 change_events（object_type='fulfillment_order'），fail-open。"""
        try:
            changed_fields = list(changes.keys())
            old_values = {k: v[0] for k, v in changes.items()}
            new_values = {k: v[1] for k, v in changes.items()}
            self._insert(CHANGE_EVENT_TABLE, {
                'object_type': 'fulfillment_order',
                'object_id': int(fulfillment_id),
                'event_type': event_type,
                'changed_fields': json.dumps(changed_fields, ensure_ascii=False),
                'old_values': json.dumps(old_values, ensure_ascii=False),
                'new_values': json.dumps(new_values, ensure_ascii=False),
                'payload': None,
                'status': 'pending',
                'created_at': _now(),
            })
        except Exception as e:  # 事件底座不可用时不阻断业务写入
            logger.warning('[fulfillment_order] 写入 change_event 失败: %s', e)
