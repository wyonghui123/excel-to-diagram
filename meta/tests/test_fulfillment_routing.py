# -*- coding: utf-8 -*-
"""履约路由 + 履约单测试（批次 4a：T4.5）

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.18.3 / §10.18.6

覆盖:
  · 4 条默认路由种子命中（stock / mto / service / mixed 兜底）
  · 表规则按 priority 覆盖种子（高优先级优先）
  · 无规则 / 无命中且无默认 → DEFAULT_ROUTING_MISS
  · 履约单编号 FO-<yyyyMM>-<3位seq> 递增 + 订单 / 客户 / 站点校验
"""

import os
import sqlite3
from datetime import datetime

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.fulfillment_order_service import (
    FulfillmentOrderError,
    FulfillmentOrderService,
)
from meta.services.fulfillment_routing_service import (
    FulfillmentRoutingError,
    FulfillmentRoutingService,
    WORKFLOW_MIXED,
    WORKFLOW_MTO,
    WORKFLOW_SERVICE,
    WORKFLOW_STOCK,
)

_SCHEMA = """
CREATE TABLE fulfillment_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fulfillment_no TEXT,
    order_id INTEGER,
    customer_account_id INTEGER,
    site_id INTEGER,
    fulfillment_type TEXT,
    status TEXT,
    workflow_run_id INTEGER,
    planned_date TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE fulfillment_routing_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    priority INTEGER,
    item_type TEXT,
    procurement_type TEXT,
    delivery_mode TEXT,
    site_id INTEGER,
    workflow_key TEXT,
    is_default INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    remark TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    customer_account_id INTEGER
);
CREATE TABLE customer_accounts (
    id INTEGER PRIMARY KEY,
    name TEXT
);
CREATE TABLE change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT,
    object_id INTEGER,
    event_type TEXT,
    changed_fields TEXT,
    old_values TEXT,
    new_values TEXT,
    payload TEXT,
    status TEXT,
    created_at TEXT
);
"""

#: 与迁移 v158 种子一致的 4 条默认规则
_DEFAULT_RULES = (
    (10, None, 'stock', None, None, WORKFLOW_STOCK, 1),
    (20, None, 'make', None, None, WORKFLOW_MTO, 1),
    (30, None, 'service', None, None, WORKFLOW_SERVICE, 1),
    (100, None, None, None, None, WORKFLOW_MIXED, 1),
)


class _MemDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cursor = self.conn.execute(sql, params or [])
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO sales_orders (id, order_no, customer_account_id) "
        "VALUES (10, 'SO-001', 7)")
    conn.execute("INSERT INTO customer_accounts (id, name) VALUES (7, '测试客户')")
    return conn


def _routing(conn):
    return FulfillmentRoutingService(_MemDS(conn))


def _orders(conn):
    return FulfillmentOrderService(_MemDS(conn))


def _seed_defaults(conn):
    for priority, item_type, procurement_type, delivery_mode, site_id, \
            workflow_key, is_default in _DEFAULT_RULES:
        conn.execute(
            "INSERT INTO fulfillment_routing_rules "
            "(priority, item_type, procurement_type, delivery_mode, site_id, "
            "workflow_key, is_default, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            [priority, item_type, procurement_type, delivery_mode, site_id,
             workflow_key, is_default])


def _add_rule(conn, priority, workflow_key, item_type=None,
              procurement_type=None, delivery_mode=None, site_id=None,
              is_default=0, enabled=1):
    conn.execute(
        "INSERT INTO fulfillment_routing_rules "
        "(priority, item_type, procurement_type, delivery_mode, site_id, "
        "workflow_key, is_default, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [priority, item_type, procurement_type, delivery_mode, site_id,
         workflow_key, is_default, enabled])


# --------------------------------------------------------------- 路由判定


def test_default_rules_resolve_by_procurement_type():
    conn = _db()
    _seed_defaults(conn)
    svc = _routing(conn)

    assert svc.resolve_workflow_key(
        procurement_type='stock', delivery_mode='delivery')['workflow_key'] \
        == WORKFLOW_STOCK
    assert svc.resolve_workflow_key(
        procurement_type='make', delivery_mode='delivery')['workflow_key'] \
        == WORKFLOW_MTO
    result = svc.resolve_workflow_key(
        procurement_type='service', is_field_service=True)
    assert result['workflow_key'] == WORKFLOW_SERVICE
    assert result['matched'] == 'default'
    assert result['inputs']['delivery_mode'] == 'onsite'


def test_wildcard_default_rule_falls_back_to_mixed():
    conn = _db()
    _seed_defaults(conn)
    result = _routing(conn).resolve_workflow_key(procurement_type='buy')
    assert result['workflow_key'] == WORKFLOW_MIXED
    assert result['priority'] == 100


def test_custom_rule_overrides_by_priority():
    conn = _db()
    _seed_defaults(conn)
    _add_rule(conn, priority=1, workflow_key='wf-custom-onsite',
              item_type='goods', delivery_mode='onsite')

    result = _routing(conn).resolve_workflow_key(
        item_type='goods', procurement_type='stock', delivery_mode='onsite')
    assert result['workflow_key'] == 'wf-custom-onsite'
    assert result['matched'] == 'rule'
    assert result['priority'] == 1


def test_disabled_rule_is_ignored():
    conn = _db()
    _seed_defaults(conn)
    _add_rule(conn, priority=1, workflow_key='wf-custom-disabled',
              procurement_type='stock', enabled=0)

    result = _routing(conn).resolve_workflow_key(procurement_type='stock')
    assert result['workflow_key'] == WORKFLOW_STOCK


def test_no_rules_raises_default_routing_miss():
    conn = _db()
    with pytest.raises(FulfillmentRoutingError) as err:
        _routing(conn).resolve_workflow_key(procurement_type='stock')
    assert err.value.rule == 'DEFAULT_ROUTING_MISS'


def test_non_matching_rules_without_default_raise_miss():
    conn = _db()
    _add_rule(conn, priority=10, workflow_key='wf-pickup',
              delivery_mode='pickup')

    with pytest.raises(FulfillmentRoutingError) as err:
        _routing(conn).resolve_workflow_key(procurement_type='stock',
                                            delivery_mode='delivery')
    assert err.value.rule == 'DEFAULT_ROUTING_MISS'


# --------------------------------------------------------------- 履约单建单


def test_create_fulfillment_order_numbering():
    conn = _db()
    svc = _orders(conn)
    prefix = 'FO-%s-' % datetime.now().strftime('%Y%m')

    first = svc.create_fulfillment_order({'order_id': 10})
    second = svc.create_fulfillment_order({'order_id': 10})

    assert first['fulfillment_no'] == prefix + '001'
    assert second['fulfillment_no'] == prefix + '002'
    assert first['status'] == 'draft'
    assert first['fulfillment_type'] == 'delivery'
    assert first['customer_account_id'] == 7
    assert first['site_id'] is None

    rows = conn.execute(
        'SELECT workflow_run_id FROM fulfillment_orders ORDER BY id').fetchall()
    assert [row[0] for row in rows] == [None, None]
    assert conn.execute('SELECT COUNT(*) FROM change_events').fetchone()[0] == 2


def test_create_fulfillment_order_validations():
    conn = _db()
    svc = _orders(conn)

    with pytest.raises(FulfillmentOrderError) as err:
        svc.create_fulfillment_order({})
    assert err.value.rule == 'FO_ORDER_REQUIRED'

    with pytest.raises(FulfillmentOrderError) as err:
        svc.create_fulfillment_order({'order_id': 999})
    assert err.value.rule == 'FO_ORDER_NOT_FOUND'

    with pytest.raises(FulfillmentOrderError) as err:
        svc.create_fulfillment_order({'order_id': 10, 'customer_account_id': 999})
    assert err.value.rule == 'FO_CUSTOMER_NOT_FOUND'

    with pytest.raises(FulfillmentOrderError) as err:
        svc.create_fulfillment_order({'order_id': 10, 'site_id': -1})
    assert err.value.rule == 'FO_SITE_INVALID'

    with pytest.raises(FulfillmentOrderError) as err:
        svc.create_fulfillment_order({'order_id': 10,
                                      'fulfillment_type': 'unknown'})
    assert err.value.rule == 'FO_TYPE_INVALID'


def test_create_fulfillment_order_with_site_and_date():
    conn = _db()
    result = _orders(conn).create_fulfillment_order({
        'order_id': 10, 'site_id': 3, 'fulfillment_type': 'onsite',
        'planned_date': '2026-11-05', 'notes': '现场安装'})

    assert result['site_id'] == 3
    assert result['fulfillment_type'] == 'onsite'
    assert result['planned_date'] == '2026-11-05'
