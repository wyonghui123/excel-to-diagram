# -*- coding: utf-8 -*-
"""最小订单量 / 订单倍数（E9 / R-QTY-1~6）守卫测试 + v143 迁移幂等。

依据: docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md §11
      meta/schemas/items.yaml（min_order_qty / order_multiple）
      meta/migrations/v143__item_order_quantity_rules.py

覆盖:
  - 最小订单量：低于拒绝 / 等于通过 / 空 sales_uom 退回 base_uom
  - 订单倍数：非整数倍拒绝 / 整数倍通过 / 两项同时先拒最小量
  - 锚单位换算：锚 KG 行 BOX、锚 BOX 行 KG 双向
  - fail-open：物料读不到 / 未知单位 / convert 返回 None
  - 更新：qty / item_id / uom_id 均未变跳过；任一变化触发
  - 豁免：退货单 / 退货行 / 服务物料 / 两限制为空
  - 迁移：缺列补齐、复跑 SKIP、verify 可空、脏值只报告、rollback 保留列
"""

import importlib.util
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)
# 并发 conftest 的 raw SQL 守卫: DML 以参数形式表达 (factories 白名单内)
from meta.tests.factories._raw_sql_bridge import insert, update

_MIGRATION = (Path(__file__).resolve().parents[1]
              / 'migrations' / 'v143__item_order_quantity_rules.py')


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源：只覆盖守卫 + UomQuantityService 用到的查询
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, types=None, orders=None, items=None,
                 uoms=None, groups=None, item_conversions=None,
                 group_conversions=None):
        self.types = types or {}
        self.orders = orders or {}
        self.items = items or {}
        self.uoms = uoms or {}
        self.groups = groups or {}
        self.item_conversions = item_conversions or {}
        self.group_conversions = group_conversions or {}

    def query(self, sql, params=None):
        p = list(params or [])

        if 'FROM type_definitions WHERE id' in sql:
            row = self.types.get(p[0])
            return [row] if row else []
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        # 同时服务于守卫 _load_item 与 UomQuantityService.resolve
        if 'FROM items WHERE id' in sql:
            row = self.items.get(p[0])
            return [row] if row else []
        if 'FROM item_uom_conversions' in sql:
            factor = self.item_conversions.get((p[0], p[1]))
            return [{'factor': factor}] if factor is not None else []
        if 'FROM uom_conversions' in sql:
            factor = self.group_conversions.get((p[0], p[1]))
            return [{'factor': factor}] if factor is not None else []
        if 'FROM uom_groups WHERE id' in sql:
            row = self.groups.get(p[0])
            return [row] if row else []
        if 'FROM uoms WHERE id IN' in sql:
            return [row for key, row in self.uoms.items() if key in p]
        raise AssertionError('unexpected sql: %s' % sql)


TYPES = {
    1: {'id': 1, 'code': 'TA', 'scope_bo': 'sales_order', 'level': 'header',
        'document_category': 'standard'},
    2: {'id': 2, 'code': 'RE', 'scope_bo': 'sales_order', 'level': 'header',
        'document_category': 'return'},
    101: {'id': 101, 'code': 'STD', 'scope_bo': 'sales_order', 'level': 'line',
          'document_category': None, 'line_category': 'material'},
    102: {'id': 102, 'code': 'SVC', 'scope_bo': 'sales_order', 'level': 'line',
          'document_category': None, 'line_category': 'service'},
    103: {'id': 103, 'code': 'RET', 'scope_bo': 'sales_order', 'level': 'line',
          'document_category': None, 'line_category': 'return'},
}

ORDERS = {
    10: {'id': 10, 'order_no': 'SO-202610-000001', 'order_type_id': 1,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-27',
         'customer_account_id': 501},
    14: {'id': 14, 'order_no': 'SO-202610-000005', 'order_type_id': 2,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-27',
         'customer_account_id': 501},
}

# 单位：1 = KG（组 1 基本单位），2 = BOX（1 BOX = 10 KG），99 = 未知单位
UOMS = {
    1: {'id': 1, 'uom_group_id': 1},
    2: {'id': 2, 'uom_group_id': 1},
}
GROUPS = {
    1: {'id': 1, 'base_uom_id': 1},
}
GROUP_CONVERSIONS = {
    (1, 2): 10,   # 1 BOX = 10 KG
}

# 物料矩阵
ITEMS = {
    # 最小量 50 KG，锚单位退回 base_uom
    2: {'id': 2, 'item_type': 'goods', 'status': 'active', 'base_uom': 1,
        'sales_uom': None, 'min_order_qty': 50, 'order_multiple': None},
    # 服务物料：R-QTY 豁免
    3: {'id': 3, 'item_type': 'service', 'status': 'active', 'base_uom': 1,
        'sales_uom': None, 'min_order_qty': 50, 'order_multiple': 10},
    # 锚单位 = sales_uom（BOX），最小量 5 BOX
    4: {'id': 4, 'item_type': 'goods', 'status': 'active', 'base_uom': 1,
        'sales_uom': 2, 'min_order_qty': 5, 'order_multiple': None},
    # 只有订单倍数 10 KG
    5: {'id': 5, 'item_type': 'goods', 'status': 'active', 'base_uom': 1,
        'sales_uom': None, 'min_order_qty': None, 'order_multiple': 10},
    # 两项都为空：不约束
    6: {'id': 6, 'item_type': 'goods', 'status': 'active', 'base_uom': 1,
        'sales_uom': None, 'min_order_qty': None, 'order_multiple': None},
    # 两项同时存在：最小量 50 KG + 倍数 10 KG
    7: {'id': 7, 'item_type': 'goods', 'status': 'active', 'base_uom': 1,
        'sales_uom': None, 'min_order_qty': 50, 'order_multiple': 10},
}


def _ds(**kwargs):
    return _FakeDS(types=TYPES, orders=ORDERS, items=ITEMS, uoms=UOMS,
                   groups=GROUPS, group_conversions=GROUP_CONVERSIONS,
                   **kwargs)


def _line(**over):
    data = {'order_id': 10, 'line_type_id': 101, 'item_id': 2,
            'uom_id': 1, 'qty': 50, 'description': '测试行'}
    data.update(over)
    return data


def _validate(data, old_data=None, is_create=True):
    SalesOrderGuardService(_ds()).validate_line_write(
        data, old_data=old_data, is_create=is_create)


# ─────────────────────────────────────────────────────────────────────────────
# 最小订单量
# ─────────────────────────────────────────────────────────────────────────────

class TestMinOrderQty:

    def test_below_min_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(qty=49))
        assert e.value.rule == 'qty_below_min_order'
        assert e.value.field_name == 'qty'

    def test_equal_min_passes(self):
        _validate(_line(qty=50))

    def test_blank_sales_uom_falls_back_to_base(self):
        # item 2 无 sales_uom → 锚单位取 base_uom（KG），50 为界
        _validate(_line(item_id=2, uom_id=1, qty=50))
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=2, uom_id=1, qty=49.9))
        assert e.value.rule == 'qty_below_min_order'

    def test_sales_uom_anchor_used(self):
        # item 4 锚单位 BOX，最小量 5 BOX：行单位同锚单位
        _validate(_line(item_id=4, uom_id=2, qty=5))
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=4, uom_id=2, qty=4))
        assert e.value.rule == 'qty_below_min_order'


# ─────────────────────────────────────────────────────────────────────────────
# 订单倍数
# ─────────────────────────────────────────────────────────────────────────────

class TestOrderMultiple:

    def test_non_multiple_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=5, qty=35))
        assert e.value.rule == 'qty_not_order_multiple'
        assert e.value.field_name == 'qty'

    def test_multiple_passes(self):
        _validate(_line(item_id=5, qty=30))

    def test_floating_noise_within_tolerance_passes(self):
        _validate(_line(item_id=5, qty=30.0000005))

    def test_min_checked_before_multiple(self):
        # item 7：45 既低于最小量 50，也不是倍数 10 → 先报最小量
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=7, qty=45))
        assert e.value.rule == 'qty_below_min_order'

        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=7, qty=55))
        assert e.value.rule == 'qty_not_order_multiple'

        _validate(_line(item_id=7, qty=50))


# ─────────────────────────────────────────────────────────────────────────────
# 换算 / fail-open
# ─────────────────────────────────────────────────────────────────────────────

class TestConversionAndFailOpen:

    def test_anchor_kg_line_box(self):
        # item 2 最小量 50 KG → 行单位 BOX 折算为 5
        _validate(_line(item_id=2, uom_id=2, qty=5))
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=2, uom_id=2, qty=4))
        assert e.value.rule == 'qty_below_min_order'

    def test_anchor_box_line_kg(self):
        # item 4 最小量 5 BOX → 行单位 KG 折算为 50
        _validate(_line(item_id=4, uom_id=1, qty=50))
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=4, uom_id=1, qty=45))
        assert e.value.rule == 'qty_below_min_order'

    def test_multiple_converted_to_line_uom(self):
        # item 5 倍数 10 KG → 行单位 BOX 折算为 1 BOX
        _validate(_line(item_id=5, uom_id=2, qty=1))
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=5, uom_id=2, qty=1.5))
        assert e.value.rule == 'qty_not_order_multiple'

    def test_unknown_uom_fail_open(self):
        # 单位 99 无法换算：convert 返回 None → 不判定
        _validate(_line(item_id=2, uom_id=99, qty=1))
        _validate(_line(item_id=5, uom_id=99, qty=3))

    def test_unknown_item_fail_open(self):
        _validate(_line(item_id=999, uom_id=1, qty=1))


# ─────────────────────────────────────────────────────────────────────────────
# 更新：仅 qty / item_id / uom_id 变化时校验
# ─────────────────────────────────────────────────────────────────────────────

_OLD_LINE = {'order_id': 10, 'line_type_id': 101, 'item_id': 2,
             'uom_id': 1, 'qty': 40, 'description': '存量行'}


class TestUpdateSkip:

    def test_other_field_only_skips_legacy_value(self):
        # 存量 40 低于最小量 50，但 qty / item / uom 都没变 → 放行
        data = dict(_OLD_LINE, description='改描述')
        _validate(data, old_data=_OLD_LINE, is_create=False)

    def test_qty_change_triggers(self):
        data = dict(_OLD_LINE, qty=45)
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(data, old_data=_OLD_LINE, is_create=False)
        assert e.value.rule == 'qty_below_min_order'

    def test_uom_change_triggers(self):
        # 换成 BOX：4 < 折算最小量 5
        data = dict(_OLD_LINE, uom_id=2, qty=4)
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(data, old_data=_OLD_LINE, is_create=False)
        assert e.value.rule == 'qty_below_min_order'

    def test_item_change_triggers(self):
        # 换成 item 5（倍数 10 KG）：40 是整数倍 → 通过；35 拒绝
        data = dict(_OLD_LINE, item_id=5, qty=40)
        _validate(data, old_data=_OLD_LINE, is_create=False)

        data = dict(_OLD_LINE, item_id=5, qty=35)
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(data, old_data=_OLD_LINE, is_create=False)
        assert e.value.rule == 'qty_not_order_multiple'


# ─────────────────────────────────────────────────────────────────────────────
# 豁免
# ─────────────────────────────────────────────────────────────────────────────

class TestExemptions:

    def test_return_order_exempt(self):
        _validate(_line(order_id=14, item_id=2, qty=1))

    def test_return_line_exempt(self):
        _validate(_line(line_type_id=103, item_id=2, qty=1))

    def test_service_item_exempt(self):
        _validate(_line(item_id=3, qty=1))

    def test_no_limits_exempt(self):
        _validate(_line(item_id=6, qty=0.1))


# ─────────────────────────────────────────────────────────────────────────────
# v143 迁移幂等
# ─────────────────────────────────────────────────────────────────────────────

def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'v143_item_order_quantity_rules', _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_db(path, with_table=True):
    conn = sqlite3.connect(str(path))
    try:
        if with_table:
            conn.execute('CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)')
            insert(conn, 'items', rows=[{'id': 1, 'name': 'a'},
                                        {'id': 2, 'name': 'b'}])
        conn.commit()
    finally:
        conn.close()
    return path


def _columns(path):
    conn = sqlite3.connect(str(path))
    try:
        return {row[1]: row for row in conn.execute('PRAGMA table_info(items)')}
    finally:
        conn.close()


def _set_item(path, item_id, **values):
    conn = sqlite3.connect(str(path))
    try:
        update(conn, 'items', {'id': item_id}, **values)
        conn.commit()
    finally:
        conn.close()


class TestMigration:

    def test_migrate_adds_columns_and_is_idempotent(self, tmp_path, capsys):
        db = _build_db(tmp_path / 'v143_add.db')
        mod = _load_migration()

        assert mod.verify(db) is False
        assert mod.migrate(db) is True
        assert mod.verify(db) is True

        cols = _columns(db)
        assert cols['min_order_qty'][3] == 0   # notnull == 0 可空
        assert cols['order_multiple'][3] == 0
        assert '[ADD]' in capsys.readouterr().out

        # 复跑：列已存在 → SKIP，不报错
        assert mod.migrate(db) is True
        out = capsys.readouterr().out
        assert out.count('[SKIP]') == 2

    def test_non_positive_values_reported_not_blocked(self, tmp_path, capsys):
        db = _build_db(tmp_path / 'v143_dirty.db')
        mod = _load_migration()
        assert mod.migrate(db) is True
        capsys.readouterr()

        _set_item(db, 1, min_order_qty=0)
        _set_item(db, 2, order_multiple=-2)
        assert mod.migrate(db) is True

        out = capsys.readouterr().out
        assert 'min_order_qty <= 0：1 条' in out
        assert 'order_multiple <= 0：1 条' in out
        assert '只报告，不阻断' in out
        assert mod.verify(db) is True

    def test_rollback_keeps_columns(self, tmp_path):
        db = _build_db(tmp_path / 'v143_keep.db')
        mod = _load_migration()
        assert mod.migrate(db) is True

        assert mod.rollback(db) is True
        assert mod.downgrade is mod.rollback
        cols = _columns(db)
        assert 'min_order_qty' in cols and 'order_multiple' in cols
        assert mod.verify(db) is True

    def test_missing_table_returns_false(self, tmp_path):
        db = _build_db(tmp_path / 'v143_empty.db', with_table=False)
        mod = _load_migration()
        assert mod.migrate(db) is False
        assert mod.verify(db) is False

    def test_missing_db_returns_false(self, tmp_path):
        mod = _load_migration()
        missing = tmp_path / 'no_such.db'
        assert mod.migrate(missing) is False
        assert mod.verify(missing) is False
        assert mod.rollback(missing) is False
