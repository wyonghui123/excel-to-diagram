# -*- coding: utf-8 -*-
"""销售订单价格 / 税务端到端链路（P2 项 6 · 真链路集成）

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §3.6 / §3.7 / §3.8
      docs/superpowers/specs/2026-10-27-sales-order-business-type-and-rounding-spec.md
      FR-005 / FR-010（税额按税码方向 + 币种精度舍入）

口径:
  · 真建表（registry + SchemaGenerator）+ 真 `SalesOrderPricingService` →
    `PricingDeterminationService` → `PricingService`，**不使用桩**；
  · 定价域 10 表按 yaml 真建表，订单/币种/税码等业务表手写最小 DDL；
  · 取价主数据：物料键（`key_fields=["item_id"]`）+ 单槽序列 + 过程
    `lookup_amount * base`，费率 120，qty=2 ⇒ 金额 240、单价 120；
  · 税务是**快照式**回写：`SalesOrderAmountService.recompute_line` 只更新订单行
    金额列、`recompute_order` 只汇总抬头，均不新增 `calc_results` 行（与定价结果链
    物理隔离）。

【为什么键表用 item_id 而不是 item_code】
  `PricingDeterminationService._slot_keys` 只注入 `item_id / customer_account_id /
  org_id / customer_group_id` 四类因子，**没有** item_id → item_code 映射；
  声明 `key_fields=["item_code"]` 时该槽位会因取不到值被置 None（引擎跳过），
  真链路将拿不到价。故此处按生产口径用 `item_id` 建键。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import logging
import sqlite3
from contextlib import contextmanager

import pytest

pytestmark = pytest.mark.unit

from meta.core.models import registry
from meta.core.schema_generator import SchemaGenerator
from meta.services.sales_order_amount_service import SalesOrderAmountService
from meta.services.sales_order_pricing_service import SalesOrderPricingService
from meta.tests.factories._raw_sql_bridge import insert, update

# 定价域按 yaml 真建表（与 test_configuration_price.py 同口径）
PRICING_TABLES = [
    'key_schema', 'lookup_sequence', 'rate_type', 'rate_table', 'rate_record',
    'calc_procedure', 'calc_procedure_step', 'calc_result', 'calc_detail',
    'pricing_determination',
]

ORDER_ID = 1001
LINE_ID = 2001
ITEM_ID = 1
RATE_TABLE_ID = 1
KEY_SCHEMA_ID = 1
SEQUENCE_ID = 1
PROCEDURE_ID = 1
RATE_TYPE_ID = 1
RATE_RECORD_ID = 1
TAX_CODE_ID = 1
TAX_RATE_ID = 1
CURRENCY_ID = 1

NOW = '2026-10-25 00:00:00'
ORDER_DATE = '2026-10-25'
RATE = 120.0
QTY = 2.0
NET = RATE * QTY           # 240.0
TAX_PERCENT = 13.0
TAX = 31.2                 # 240 × 13% = 31.2
GROSS = 271.2


class _SqliteDS:
    """最小数据源：query / execute / insert / update / transaction。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])

    def insert(self, table, data):
        columns = list(data.keys())
        sql = (f"INSERT INTO {table} ({', '.join(columns)}) "
               f"VALUES ({', '.join('?' for _ in columns)})")
        cur = self.conn.execute(sql, [data[col] for col in columns])
        return cur.lastrowid

    def update(self, table, row_id, data):
        assignments = ', '.join(f'{key} = ?' for key in data)
        self.conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            [*data.values(), row_id])

    @contextmanager
    def transaction(self):
        try:
            yield self
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()


@pytest.fixture()
def env():
    previous_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), 'meta', 'schemas'))
    finally:
        logging.disable(previous_level)

    conn = sqlite3.connect(':memory:')
    conn.executescript(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT, status TEXT);

        CREATE TABLE currencies (
            id INTEGER PRIMARY KEY, code TEXT, decimal_places INTEGER);

        CREATE TABLE type_definitions (
            id INTEGER PRIMARY KEY, code TEXT, document_category TEXT);

        CREATE TABLE tax_codes (
            id INTEGER PRIMARY KEY, code TEXT, rounding TEXT);

        CREATE TABLE tax_rates (
            id INTEGER PRIMARY KEY, tax_code_id INTEGER, rate_percent REAL,
            effective_from TEXT, effective_to TEXT);

        CREATE TABLE sales_orders (
            id INTEGER PRIMARY KEY, status TEXT, order_type_id INTEGER,
            order_date TEXT, price_date TEXT, currency_id INTEGER,
            sales_org_id INTEGER, customer_account_id INTEGER,
            pricing_status TEXT, header_discount_percent REAL,
            header_surcharge_percent REAL, exchange_rate REAL,
            exchange_rate_type TEXT, exchange_rate_date TEXT,
            price_list_id INTEGER, pricing_procedure_id INTEGER,
            net_amount REAL, tax_amount REAL, gross_amount REAL,
            updated_at TEXT);

        CREATE TABLE sales_order_lines (
            id INTEGER PRIMARY KEY, order_id INTEGER, line_no TEXT,
            item_id INTEGER, qty REAL, unit_price REAL, price_source TEXT,
            price_trace TEXT, status TEXT, tax_code_id INTEGER,
            header_discount_amount REAL, header_surcharge_amount REAL,
            net_amount REAL, tax_base_amount REAL, tax_rate_percent REAL,
            tax_amount REAL, gross_amount REAL, updated_at TEXT);
        """
    )
    gen = SchemaGenerator('sqlite')
    for name in PRICING_TABLES:
        mo = registry.get(name)
        assert mo is not None, f'{name} 未注册'
        conn.execute(gen.generate_create_table(mo))
        for index_sql in gen.generate_create_index(mo):
            conn.execute(index_sql)

    ds = _SqliteDS(conn)
    _seed(ds)
    yield ds
    conn.close()


def _seed(ds):
    """一份可跑通的最小配置：取价主数据 + 税务主数据 + 一张草稿订单。"""
    insert(ds, 'items', rows=[
        dict(id=ITEM_ID, code='ITEM-A', name='物料A', status='active'),
    ])

    insert(ds, 'currencies', id=CURRENCY_ID, code='CNY', decimal_places=2)
    insert(ds, 'type_definitions', id=1, code='SO_STD',
           document_category='standard')

    # ---- 取价主数据 ----
    insert(ds, 'rate_types', id=RATE_TYPE_ID, code='PRICE_BASE', name='基本价格',
           rate_class='price', calc_type='percent', rate_source='rate_record',
           sign='+', rounding=None, exclusion_group_id=None, manual_allowed=0,
           mandatory=0, statistical=0, lookup_sequence_id=None,
           created_at=NOW, updated_at=NOW)
    insert(ds, 'rate_tables', id=RATE_TABLE_ID, code='PL_STD', name='标准价目表',
           type='standard', currency='CNY', owner_org_id=None, status='approved',
           created_at=NOW, updated_at=NOW)
    insert(ds, 'key_schemas', id=KEY_SCHEMA_ID, code='KEY_ITEM', name='物料键',
           key_fields='["item_id"]', created_at=NOW, updated_at=NOW)
    insert(ds, 'lookup_sequences', id=SEQUENCE_ID, code='SEQ_ITEM', name='物料序列',
           steps='[{"seq":1,"key_schema_id":1}]',
           created_at=NOW, updated_at=NOW)
    insert(ds, 'rate_records', id=RATE_RECORD_ID, code='RC_ITEM',
           rate_table_id=RATE_TABLE_ID, key_schema_id=KEY_SCHEMA_ID,
           keys='{"item_id": 1}', rate_type_id=RATE_TYPE_ID, rate=RATE,
           hit_policy='exclusive', priority=1, status='active', rate_qty=1,
           created_at=NOW, updated_at=NOW)

    insert(ds, 'calc_procedures', id=PROCEDURE_ID, code='PROC_ITEM', name='物料过程',
           procedure_type='pricing', result_semantic='price', currency='CNY',
           subtotal_keys=None, created_at=NOW, updated_at=NOW)
    insert(ds, 'calc_procedure_steps', id=1, calc_procedure_id=PROCEDURE_ID,
           seq=1, element_type='formula', rate_type_id=RATE_TYPE_ID,
           condition=None, params='{"expr": "lookup_amount * base"}',
           rolling=0, base_step=None, subtotal_key=None,
           created_at=NOW, updated_at=NOW)

    insert(ds, 'pricing_determinations', id=1, code='PD_STD', name='标准规则',
           sales_org_id=None, order_type_id=None,
           rate_table_id=RATE_TABLE_ID, calc_procedure_id=PROCEDURE_ID,
           lookup_sequence_id=SEQUENCE_ID, currency=None, seq=100,
           valid_from=None, valid_to=None, status='active', description=None,
           created_at=NOW, updated_at=NOW)

    # ---- 税务主数据 ----
    insert(ds, 'tax_codes', id=TAX_CODE_ID, code='TAX_STD', rounding='round')
    insert(ds, 'tax_rates', id=TAX_RATE_ID, tax_code_id=TAX_CODE_ID,
           rate_percent=TAX_PERCENT, effective_from='2026-01-01',
           effective_to=None)

    # ---- 草稿订单 + 一行 ----
    insert(ds, 'sales_orders', id=ORDER_ID, status='draft', order_type_id=1,
           order_date=ORDER_DATE, price_date=None, currency_id=CURRENCY_ID,
           sales_org_id=None, customer_account_id=None,
           pricing_status='pending', header_discount_percent=0,
           header_surcharge_percent=0, exchange_rate=None,
           exchange_rate_type=None, exchange_rate_date=None,
           price_list_id=None, pricing_procedure_id=None,
           net_amount=0, tax_amount=0, gross_amount=0, updated_at=NOW)
    insert(ds, 'sales_order_lines', id=LINE_ID, order_id=ORDER_ID,
           line_no='1', item_id=ITEM_ID, qty=QTY, unit_price=None,
           price_source=None, price_trace=None, status='open',
           tax_code_id=TAX_CODE_ID, header_discount_amount=0,
           header_surcharge_amount=0, net_amount=0, tax_base_amount=0,
           tax_rate_percent=None, tax_amount=0, gross_amount=0,
           updated_at=NOW)


# ─────────────────────────────────────────────────────────────────────────────
# 查询助手
# ─────────────────────────────────────────────────────────────────────────────

def _calc_results(ds):
    return ds.query(
        "SELECT * FROM calc_results WHERE document_type = 'sales_order'"
        " AND document_id = ? ORDER BY id", [ORDER_ID])


def _active_results(ds):
    return ds.query(
        "SELECT * FROM calc_results WHERE document_type = 'sales_order'"
        " AND document_id = ? AND status = 'active'", [ORDER_ID])


def _line(ds):
    return ds.query('SELECT * FROM sales_order_lines WHERE id = ?', [LINE_ID])[0]


def _order(ds):
    return ds.query('SELECT * FROM sales_orders WHERE id = ?', [ORDER_ID])[0]


def _pricing(ds):
    return SalesOrderPricingService(ds)


# ─────────────────────────────────────────────────────────────────────────────
# 用例
# ─────────────────────────────────────────────────────────────────────────────

class TestSalesOrderPricingE2E:

    def test_line_price_persists_line_level_calc_result(self, env):
        """真链路取价：回写单价 + 落一条行级 active 结果。"""
        got = _pricing(env).price_line(LINE_ID, force=True)

        assert got is not None
        assert got['pricing_status'] == 'determined'
        assert got['reason'] is None
        assert got['unit_price'] == pytest.approx(RATE)
        assert got['price_source'] == 'rate_table'

        line = _line(env)
        assert line['unit_price'] == pytest.approx(RATE)
        assert line['price_source'] == 'rate_table'
        assert line['price_trace']

        rows = _calc_results(env)
        assert len(rows) == 1
        row = rows[0]
        assert row['document_line_id'] == LINE_ID
        assert row['level'] == 'line'
        assert row['status'] == 'active'
        assert row['document_type'] == 'sales_order'
        assert row['document_id'] == ORDER_ID
        assert row['base'] == pytest.approx(QTY)
        assert row['amount'] == pytest.approx(NET)
        assert row['net_amount'] == pytest.approx(NET)
        assert row['currency'] == 'CNY'

    def test_reprice_invalidates_previous_result(self, env):
        """同宿主重取价：旧结果作废，active 结果始终恰一条。"""
        service = _pricing(env)
        first = service.price_line(LINE_ID, force=True)
        assert first['pricing_status'] == 'determined'

        second = service.price_line(LINE_ID, force=True)
        assert second['pricing_status'] == 'determined'

        rows = _calc_results(env)
        assert len(rows) == 2
        assert [r['status'] for r in rows] == ['invalid', 'active']

        active = _active_results(env)
        assert len(active) == 1
        assert active[0]['id'] != rows[0]['id']
        assert active[0]['document_line_id'] == LINE_ID
        assert active[0]['level'] == 'line'

    def test_tax_is_amount_snapshot_not_calc_result(self, env):
        """税务只回写订单行金额列；calc_results 无税相关新增行。"""
        _pricing(env).price_line(LINE_ID, force=True)
        before = _calc_results(env)

        # 行级计算走 recompute_line，抬头汇总走 recompute_order（服务职责分离）
        amount = SalesOrderAmountService(env)
        amount.recompute_line(LINE_ID)
        totals = amount.recompute_order(ORDER_ID)

        line = _line(env)
        assert line['net_amount'] == pytest.approx(NET)
        assert line['tax_base_amount'] == pytest.approx(NET)
        assert line['tax_rate_percent'] == pytest.approx(TAX_PERCENT)
        assert line['tax_amount'] == pytest.approx(TAX)
        assert line['gross_amount'] == pytest.approx(GROSS)

        order = _order(env)
        assert order['net_amount'] == pytest.approx(NET)
        assert order['tax_amount'] == pytest.approx(TAX)
        assert order['gross_amount'] == pytest.approx(GROSS)
        assert totals['net_amount'] == pytest.approx(NET)

        after = _calc_results(env)
        assert len(after) == len(before) == 1
        assert env.query(
            "SELECT * FROM calc_results WHERE result_semantic LIKE '%tax%'"
            " OR process_code LIKE '%TAX%'") == []

    def test_confirmed_order_tax_snapshot_immutable(self, env):
        """已确认单据：改税率后重取价被拒（None），税务快照保持不变。"""
        _pricing(env).price_line(LINE_ID, force=True)
        amount = SalesOrderAmountService(env)
        amount.recompute_line(LINE_ID)
        amount.recompute_order(ORDER_ID)

        update(env, 'sales_orders', {'id': ORDER_ID}, status='confirmed')
        update(env, 'tax_rates', {'id': TAX_RATE_ID}, rate_percent=20.0)

        got = _pricing(env).price_line(LINE_ID, force=True)
        assert got is None

        line = _line(env)
        assert line['tax_rate_percent'] == pytest.approx(TAX_PERCENT)
        assert line['tax_amount'] == pytest.approx(TAX)
        assert line['gross_amount'] == pytest.approx(GROSS)
        assert line['unit_price'] == pytest.approx(RATE)
