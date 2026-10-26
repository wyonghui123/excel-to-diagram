# -*- coding: utf-8 -*-
"""销售订单主数据补齐场景种子数据（SCN-SO-MD- 前缀）

用途
----
为销售订单主数据补齐（items.sales_uom / division）准备独立测试数据，
覆盖详细设计 §8.1 的验收场景 S1~S9。

约定
----
· 业务编码统一 SCN-SO-MD- 前缀，--cleanup 只删该前缀。
· 幂等：按业务键 SELECT 后 UPDATE / INSERT，可重复执行。
· 直接写表，不经过守卫；I-SU-3 / I-SU-4 本身就是「故意不一致」的样本，
  用于验证守卫在改基本单位 / 建物料时会被拒绝。

场景清单
--------
| 编码 | 数据 |
|---|---|
| I-SU-1 | 基本单位 KG（12），销售单位 BOX（15），物料级换算 1 BOX = 10 KG |
| I-SU-2 | 基本单位 KG（12），无销售单位 |
| I-SU-3 | 基本单位 KG（12），销售单位 BOX（15），无任何物料级换算（改基本单位用） |
| I-SU-4 | 基本单位 KG（12），销售单位 L（13），无换算 |
| D01 / D02 | 产品组：D01 active / D02 inactive |

用法
----
    python -m meta.scripts.init_sales_order_master_data_scenario            # 写入（幂等）
    python -m meta.scripts.init_sales_order_master_data_scenario --verify   # 自检 S1~S9
    python -m meta.scripts.init_sales_order_master_data_scenario --cleanup  # 仅清理
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# 真实库固定 id（meta/architecture.db）
UOM_KG = 12
UOM_BOX = 15
UOM_L = 13

SALES_ORG_ID = 318
LINE_TYPE_STD = 101
ORDER_TYPE_STD = 1
ITEM_GROUP_ID = 4           # FEIG1 前端验证物料组（items.item_group_id NOT NULL）

CODE_PREFIX = 'SCN-SO-MD-'
P_ITEMS = CODE_PREFIX + 'ITEM-'
P_DIV = CODE_PREFIX + 'DIV-'

_ITEMS: List[Dict[str, Any]] = [
    {'code': P_ITEMS + 'SU1', 'name': '场景主数据-销售单位有换算',
     'item_type': 'goods', 'base_uom': UOM_KG, 'sales_uom': UOM_BOX,
     'status': 'active'},
    {'code': P_ITEMS + 'SU2', 'name': '场景主数据-无销售单位',
     'item_type': 'goods', 'base_uom': UOM_KG, 'sales_uom': None,
     'status': 'active'},
    {'code': P_ITEMS + 'SU3', 'name': '场景主数据-销售单位BOX无换算',
     'item_type': 'goods', 'base_uom': UOM_KG, 'sales_uom': UOM_BOX,
     'status': 'active'},
    {'code': P_ITEMS + 'SU4', 'name': '场景主数据-销售单位L无换算',
     'item_type': 'goods', 'base_uom': UOM_KG, 'sales_uom': UOM_L,
     'status': 'active'},
]

# I-SU-1 的物料级换算：1 BOX = 10 KG
_ITEM_CONV: List[Dict[str, Any]] = [
    {'item': P_ITEMS + 'SU1', 'uom_id': UOM_BOX, 'factor': '10.0'},
]

_DIVISIONS: List[Dict[str, Any]] = [
    {'code': P_DIV + 'D01', 'name': '场景主数据-启用产品组', 'status': 'active'},
    {'code': P_DIV + 'D02', 'name': '场景主数据-停用产品组', 'status': 'inactive'},
]

# 清理顺序：子表先删
_CLEANUP_SQL: List[Tuple[str, str]] = [
    ('item_uom_conversions',
     'DELETE FROM item_uom_conversions WHERE item_id IN ('
     f"SELECT id FROM items WHERE code LIKE '{P_ITEMS}%')"),
    ('items', f"DELETE FROM items WHERE code LIKE '{P_ITEMS}%'"),
    ('divisions', f"DELETE FROM divisions WHERE code LIKE '{P_DIV}%'"),
]


def _one(ds, sql: str, params: list) -> Dict[str, Any]:
    rows = ds.query(sql, params)
    return rows[0] if rows else None


def _item_id(ds, code: str) -> Any:
    row = _one(ds, 'SELECT id FROM items WHERE code = ?', [code])
    assert row, f'场景物料不存在：{code}（请先执行 seed）'
    return row['id']


def seed_master_data_scenario(ds) -> Dict[str, int]:
    """幂等写入：4 物料 + 1 换算 + 2 产品组。"""
    counts = {'items': 0, 'conversions': 0, 'divisions': 0}

    for it in _ITEMS:
        existing = _one(ds, 'SELECT id FROM items WHERE code = ?', [it['code']])
        if existing:
            ds.execute(
                'UPDATE items SET name=?, base_uom=?, sales_uom=?, '
                'item_type=?, status=? WHERE code=?',
                [it['name'], it['base_uom'], it['sales_uom'],
                 it['item_type'], it['status'], it['code']])
        else:
            ds.execute(
                'INSERT INTO items '
                '(code, name, base_uom, sales_uom, item_type, item_group_id, '
                ' status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                [it['code'], it['name'], it['base_uom'], it['sales_uom'],
                 it['item_type'], ITEM_GROUP_ID, it['status']])
        counts['items'] += 1

    for conv in _ITEM_CONV:
        item_id = _item_id(ds, conv['item'])
        existing = _one(
            ds, 'SELECT id FROM item_uom_conversions WHERE item_id=? AND uom_id=?',
            [item_id, conv['uom_id']])
        if existing:
            ds.execute('UPDATE item_uom_conversions SET factor=? WHERE id=?',
                       [conv['factor'], existing['id']])
        else:
            ds.execute(
                'INSERT INTO item_uom_conversions (item_id, uom_id, factor) '
                'VALUES (?, ?, ?)', [item_id, conv['uom_id'], conv['factor']])
        counts['conversions'] += 1

    for div in _DIVISIONS:
        existing = _one(ds, 'SELECT id FROM divisions WHERE code = ?', [div['code']])
        if existing:
            ds.execute('UPDATE divisions SET name=?, status=? WHERE code=?',
                       [div['name'], div['status'], div['code']])
        else:
            ds.execute('INSERT INTO divisions (code, name, status) VALUES (?, ?, ?)',
                       [div['code'], div['name'], div['status']])
        counts['divisions'] += 1

    ds.commit()
    return counts


def cleanup_master_data_scenario(ds) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table, sql in _CLEANUP_SQL:
        result = ds.execute(sql)
        rowcount = getattr(result, 'rowcount', None)
        counts[table] = -1 if rowcount is None or rowcount < 0 else rowcount
    ds.commit()
    return counts


# ---------------------------------------------------------------- 自检 S1~S9

def _draft_guard(ds):
    """把父单固定为草稿的守卫替身：其余查询仍走真实库。"""
    from meta.services.sales_order_guard_service import SalesOrderGuardService

    class _DraftGuard(SalesOrderGuardService):
        def _load_order(self, order_id):
            return {'id': order_id, 'status': 'draft',
                    'order_type_id': ORDER_TYPE_STD}

    return _DraftGuard(ds)


def _run_checks(ds) -> List[Tuple[str, bool, str]]:
    from meta.services.sales_order_guard_service import (
        SalesOrderGuardError, SalesOrderGuardService)
    from meta.services.uom_conversion_guard_service import (
        UomConversionGuardError, UomConversionGuardService)

    checks: List[Tuple[str, bool, str]] = []

    def check(name, fn):
        try:
            checks.append((name, True, fn()))
        except AssertionError as e:
            checks.append((name, False, str(e)))
        except Exception as e:
            checks.append((name, False, f'{type(e).__name__}: {e}'))

    su1 = _item_id(ds, P_ITEMS + 'SU1')
    su2 = _item_id(ds, P_ITEMS + 'SU2')
    su3 = _item_id(ds, P_ITEMS + 'SU3')
    guard = SalesOrderGuardService(ds)
    draft = _draft_guard(ds)
    uom_guard = UomConversionGuardService(ds)

    def s1():
        got = guard.service_line_defaults({'item_id': su1})
        assert str(got.get('uom_id')) == str(UOM_BOX), f'实际 {got}'
        return f'默认单位 = BOX({UOM_BOX})'

    def s2():
        got = guard.service_line_defaults({'item_id': su2})
        assert str(got.get('uom_id')) == str(UOM_KG), f'实际 {got}'
        return f'默认单位 = KG({UOM_KG})（回退基本单位）'

    def s3():
        got = guard.service_line_defaults({'item_id': su1, 'uom_id': UOM_KG})
        assert not got.get('uom_id'), f'显式单位被覆盖：{got}'
        return '显式 KG 不被覆盖'

    def s4():
        try:
            draft.validate_line_write(
                {'order_id': 1, 'line_type_id': LINE_TYPE_STD, 'item_id': su1,
                 'uom_id': UOM_L, 'qty': 2}, is_create=True)
        except SalesOrderGuardError as e:
            assert e.rule == 'item_uom_incompatible', e.rule
            return 'L 与 KG 跨组不可换算 → item_uom_incompatible'
        raise AssertionError('不可换算单位未被拦截')

    def s5():
        try:
            uom_guard.validate_item_update(su3, UOM_L)
        except UomConversionGuardError as e:
            assert e.rule == 'sales_uom_incompatible_with_base', e.rule
            return '改基本单位为 L 被拒 → sales_uom_incompatible_with_base'
        raise AssertionError('改基本单位未被拦截')

    def s6():
        try:
            uom_guard.validate_item_sales_uom(None, UOM_L, UOM_KG)
        except UomConversionGuardError as e:
            assert e.rule == 'sales_uom_incompatible', e.rule
            return '创建时销售单位 L 与 KG 不可换算 → sales_uom_incompatible'
        raise AssertionError('创建校验未拦截')

    def s7():
        guard.validate_order_write(
            {'sales_org_id': SALES_ORG_ID, 'division_code': P_DIV + 'D01'},
            is_create=True)
        return f'{P_DIV}D01 可写入订单抬头'

    def s8():
        try:
            guard.validate_order_write(
                {'sales_org_id': SALES_ORG_ID, 'division_code': P_DIV + 'D02'},
                is_create=True)
        except SalesOrderGuardError as e:
            assert e.rule == 'division_inactive', e.rule
            return 'D02 已停用 → division_inactive'
        raise AssertionError('停用产品组未被拦截')

    def s9():
        draft.validate_line_write(
            {'order_id': 1, 'line_type_id': LINE_TYPE_STD, 'item_id': su1,
             'uom_id': UOM_L, 'qty': 2, 'description': '仅改描述'},
            old_data={'item_id': su1, 'uom_id': UOM_L}, is_create=False)
        return '单位未变化时不再校验（R-SU-5）'

    check('S1 行不填单位 → BOX', s1)
    check('S2 无销售单位 → KG', s2)
    check('S3 显式 KG 不被覆盖', s3)
    check('S4 不可换算单位被拒', s4)
    check('S5 改基本单位被拒', s5)
    check('S6 创建时不可换算被拒', s6)
    check('S7 启用产品组可写入', s7)
    check('S8 停用产品组被拒', s8)
    check('S9 单位未变化不校验', s9)
    return checks


def verify_master_data_scenario(ds) -> int:
    checks = _run_checks(ds)
    width = max(len(name) for name, _, _ in checks)
    for name, passed, detail in checks:
        print('%s %s  %s' % ('[PASS]' if passed else '[FAIL]',
                            name.ljust(width), detail))
    failed = [c for c in checks if not c[1]]
    print('\n合计 %d 项：通过 %d，失败 %d'
          % (len(checks), len(checks) - len(failed), len(failed)))
    return 1 if failed else 0


def _main(argv: List[str]) -> int:
    from meta.core.datasource import get_data_source
    from meta.tests.test_utils import get_meta_db_path

    ds = get_data_source('sqlite', database=str(get_meta_db_path()))
    action = argv[1] if len(argv) > 1 else ''

    if action == '--cleanup':
        print('[cleanup]', cleanup_master_data_scenario(ds))
        return 0
    if action == '--verify':
        return verify_master_data_scenario(ds)

    seed = seed_master_data_scenario(ds)
    print('[seed] items=%d conversions=%d divisions=%d'
          % (seed['items'], seed['conversions'], seed['divisions']))
    return 0


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))
