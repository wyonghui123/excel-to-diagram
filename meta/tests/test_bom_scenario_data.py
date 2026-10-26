# -*- coding: utf-8 -*-
"""BOM / 配置域场景数据测试 —— 按场景验证种子数据与三条链路。

覆盖:
  S1/S2/S3  多层展开、半成品不递归、虚拟件穿透
  S4        替代组（必选锚点 + 可选替代）
  S5        可选 / 默认 / 数量区间
  S6/S7     模型配置、选项类基数、互斥规则、特征取值
  S8        单位换算（整箱 → 个；跨量纲报错）
  S9        版本与生效期、销售替代号选取
  S10       销售订单行展开（含服务行、幂等、E1 前提）
  守卫      R3 / R5 / R6 / R8 / R11 / R17 / S3 / D1

数据来源: meta/scripts/init_bom_scenario_seed.py（SCN- 前缀，按场景命名）。
隔离方式: 复制真实库到临时目录后写入种子，不触碰 meta/architecture.db。
"""

import os
import shutil

import pytest

from meta.core.datasource import get_data_source
from meta.scripts.init_bom_scenario_seed import seed_bom_scenario_data
from meta.services.item_structure_config_service import ItemStructureConfigService
from meta.services.item_structure_explode_service import ItemStructureExplodeService
from meta.services.item_structure_guard_service import (
    ItemStructureGuardError,
    ItemStructureGuardService,
)
from meta.services.sales_order_expand_service import (
    SalesOrderExpandError,
    SalesOrderExpandService,
)
from meta.tests.test_utils import get_meta_db_path

pytestmark = pytest.mark.unit

AS_OF = '2026-10-26'


# ---------------------------------------------------------------- 工具


def _item_id(ds, code):
    rows = ds.query('SELECT id FROM items WHERE code = ?', [code])
    assert rows, f'物料不存在: {code}'
    return rows[0]['id']


def _codes(ds, item_ids):
    ids = [i for i in item_ids if i is not None]
    if not ids:
        return {}
    placeholders = ', '.join('?' * len(ids))
    rows = ds.query(
        f'SELECT id, code FROM items WHERE id IN ({placeholders})', ids)
    return {row['id']: row['code'] for row in rows}


def _by_no(result):
    return {line['line_no']: line for line in result['lines']}


def _components(result):
    return {row['component_key']: row for row in result['components']}


def _new_order(ds, order_no, status='draft'):
    order_id = ds.insert('sales_orders', {
        'order_no': order_no,
        'order_type_id': 1,
        'order_date': AS_OF,
        'status': status,
        'customer_account_id': 4,
        'org_id': 318,
        'sales_org_id': 318,
        'currency_id': 8,
        'exchange_rate': 1.0,
        'description': 'SCN 测试临时订单',
    })
    ds.commit()
    return order_id


def _new_order_line(ds, order_id, item_code, qty=1.0, line_no='10'):
    line_id = ds.insert('sales_order_lines', {
        'order_id': order_id,
        'line_no': line_no,
        'line_type_id': 101,
        'item_id': _item_id(ds, item_code),
        'qty': qty,
        'uom_id': 2,
        'unit_price': 1.0,
        'status': 'open',
        'pricing_mode': 'standalone',
    })
    ds.commit()
    return line_id


# ---------------------------------------------------------------- fixture


@pytest.fixture(scope='module')
def ctx(tmp_path_factory):
    """复制真实库 → 写入 SCN 场景数据；全模块共享一份。"""
    base = get_meta_db_path()
    assert os.path.exists(base), f'真实库不存在: {base}'
    db_path = tmp_path_factory.mktemp('bom_scenario') / 'scn.db'
    shutil.copy2(base, db_path)

    ds = get_data_source('sqlite', database=str(db_path))
    seed = seed_bom_scenario_data(ds)
    yield {'ds': ds, 'seed': seed}


# ---------------------------------------------------------------- S1 ~ S3 展开


def test_s1_multilevel_with_phantom_penetration(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    result = ItemStructureExplodeService(ds).explode_item(
        _item_id(ds, 'SCN-FG-BIKE'), qty=2, as_of=AS_OF)

    assert result['structure_id'] == seed['structures']['S1-BIKE']
    assert result['revision'] == 'A'
    assert result['warnings'] == []
    assert [line['path'] for line in result['lines']] == [
        '10', '20', '30.10', '30.20', '40']

    totals = {line['path']: line['total_qty'] for line in result['lines']}
    assert totals == {'10': 2.0, '20': 5.0, '30.10': 8.0,
                      '30.20': 8.0, '40': 4.0}

    codes = _codes(ds, [line['component_item_id'] for line in result['lines']])
    component_codes = set(codes.values())
    # 虚拟件本身不产出，穿透为叶子；半成品不递归到自己的下层
    assert 'SCN-PHANTOM-KIT' not in component_codes
    assert 'SCN-SUB-FRAME' in component_codes
    assert 'SCN-RAW-ALU' not in component_codes


def test_s2_half_product_structure_stands_alone(ctx):
    ds = ctx['ds']
    result = ItemStructureExplodeService(ds).explode_item(
        _item_id(ds, 'SCN-SUB-FRAME'), qty=1, as_of=AS_OF)
    totals = {line['line_no']: line['total_qty'] for line in result['lines']}
    assert totals == {10: 1.8, 20: 0.6}


def test_s3_sales_usage_not_enabled_for_explode(ctx):
    ds = ctx['ds']
    result = ItemStructureExplodeService(ds).explode_item(
        _item_id(ds, 'SCN-FG-BOX-PARENT'), usage='sales', as_of=AS_OF)
    assert result['lines'] == []
    assert result['warnings'][0]['rule'] == 'item_structure_usage_not_enabled'


# ---------------------------------------------------------------- S4 替代组


def test_s4_substitute_group(ctx):
    ds = ctx['ds']
    svc = ItemStructureExplodeService(ds)
    item = _item_id(ds, 'SCN-FG-PUMP')

    default = svc.explode_item(item, as_of=AS_OF)
    assert [line['line_no'] for line in default['lines']] == [10]
    assert default['skipped_optional'] == 0
    assert len(default['substitutes']) == 1
    group = default['substitutes'][0]
    assert group['group_code'] == 'SEAL'
    assert group['component_item_id'] == _item_id(ds, 'SCN-RAW-SEAL-A')
    assert [member['line_no'] for member in group['components']] == [20]

    full = svc.explode_item(item, include_optional=True, as_of=AS_OF)
    assert [line['line_no'] for line in full['lines']] == [10, 20]


# ---------------------------------------------------------------- S5 可选 / 默认


def test_s5_optional_default_and_qty_range(ctx):
    ds = ctx['ds']
    svc = ItemStructureExplodeService(ds)
    item = _item_id(ds, 'SCN-FG-DESK')

    default = svc.explode_item(item, qty=2, as_of=AS_OF)
    assert [line['line_no'] for line in default['lines']] == [10]
    assert default['skipped_optional'] == 2

    full = svc.explode_item(item, qty=2, include_optional=True, as_of=AS_OF)
    assert [line['line_no'] for line in full['lines']] == [10, 20, 30]
    totals = {line['line_no']: line['total_qty'] for line in full['lines']}
    # 展开不消费 default_qty：用量按父数量 × qty_per / base_qty
    assert totals == {10: 2.0, 20: 2.0, 30: 2.0}


# ---------------------------------------------------------------- S6 / S7 配置


def test_s6_default_configuration(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    result = ItemStructureConfigService(ds).validate(
        seed['structures']['S6-PC'], as_of=AS_OF)

    assert result['valid'] is True, result['message']
    comps = _components(result)
    assert set(comps) == {'L0010', 'L0020.L0010', 'L0030'}

    codes = _codes(ds, [row['component_item_id'] for row in comps.values()])
    assert codes[comps['L0010']['component_item_id']] == 'SCN-COMP-CPU'
    assert codes[comps['L0020.L0010']['component_item_id']] == 'SCN-OPT-RED'
    assert codes[comps['L0030']['component_item_id']] == 'SCN-SVC-INSTALL'
    assert comps['L0030']['qty'] == 1.0
    assert {row['uom_code'] for row in comps.values()} == {'FEA'}

    values = {row['attribute_code']: row for row in result['values']}
    assert values['scn_finish']['value_text'] == 'matte'
    assert values['scn_finish']['source'] == 'default'


def test_s6_rule_conflict_when_red_and_blue(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    red = seed['lines'][('S7-COLOR', 10)]
    blue = seed['lines'][('S7-COLOR', 20)]

    result = ItemStructureConfigService(ds).validate(
        seed['structures']['S6-PC'],
        selections={red: True, blue: True}, as_of=AS_OF)

    assert result['valid'] is False
    assert result['error_code'] == 'CONFIG_CONFLICT'
    assert result['rule'] == 'config_conflict'
    assert result['conflicts']


def test_s6_rule_allows_blue_after_red_deselected(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    red = seed['lines'][('S7-COLOR', 10)]
    blue = seed['lines'][('S7-COLOR', 20)]

    result = ItemStructureConfigService(ds).validate(
        seed['structures']['S6-PC'],
        selections={red: False, blue: True}, as_of=AS_OF)

    assert result['valid'] is True, result['message']
    comps = _components(result)
    assert set(comps) == {'L0010', 'L0020.L0020', 'L0030'}
    codes = _codes(ds, [row['component_item_id'] for row in comps.values()])
    assert codes[comps['L0020.L0020']['component_item_id']] == 'SCN-OPT-BLUE'


def test_s6_characteristic_user_value(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    result = ItemStructureConfigService(ds).validate(
        seed['structures']['S6-PC'],
        attribute_values={'scn_finish': 'glossy'}, as_of=AS_OF)
    values = {row['attribute_code']: row for row in result['values']}
    assert values['scn_finish']['value_text'] == 'glossy'
    assert values['scn_finish']['source'] == 'user'


def test_s6_undeclared_characteristic_rejected(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    result = ItemStructureConfigService(ds).validate(
        seed['structures']['S6-PC'],
        attribute_values={'scn_unknown': 'x'}, as_of=AS_OF)
    assert result['valid'] is False
    assert result['error_code'] == 'CONFIG_INVALID_VALUE'
    assert result['rule'] == 'configuration_value_undeclared'


def test_s7_cardinality_and_qty_bounds(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    svc = ItemStructureConfigService(ds)
    structure = seed['structures']['S7-COLOR']
    red = seed['lines'][('S7-COLOR', 10)]
    blue = seed['lines'][('S7-COLOR', 20)]
    green = seed['lines'][('S7-COLOR', 30)]

    default = svc.validate(structure, as_of=AS_OF)
    assert default['valid'] is True
    assert set(_components(default)) == {'L0010'}

    too_many = svc.validate(
        structure, selections={red: True, blue: True, green: True}, as_of=AS_OF)
    assert too_many['valid'] is False
    assert too_many['rule'] == 'item_structure_select_too_many'
    assert too_many['error_code'] == 'CONFIG_CONFLICT'

    too_few = svc.validate(
        structure, selections={red: False, blue: False, green: False}, as_of=AS_OF)
    assert too_few['valid'] is False
    assert too_few['rule'] == 'item_structure_select_too_few'

    qty_range = svc.validate(
        structure, selections={green: True}, quantities={green: 4}, as_of=AS_OF)
    assert qty_range['valid'] is False
    assert qty_range['rule'] == 'item_structure_select_qty_range'
    assert qty_range['error_code'] == 'CONFIG_INVALID_VALUE'

    unknown = svc.validate(structure, selections={999999: True}, as_of=AS_OF)
    assert unknown['valid'] is False
    assert unknown['rule'] == 'item_structure_select_line_unknown'


# ------------------------------------------------- HTTP 契约：字符串 key 归一化


def test_http_string_keys_align_with_int_line_ids(ctx):
    """JSON 对象的 key 恒为字符串，显式选择必须仍能命中 structure_line id。"""
    ds, seed = ctx['ds'], ctx['seed']
    red = str(seed['lines'][('S7-COLOR', 10)])
    blue = str(seed['lines'][('S7-COLOR', 20)])

    result = ItemStructureConfigService(ds).validate(
        seed['structures']['S6-PC'],
        selections={red: True, blue: True}, as_of=AS_OF)

    assert result['valid'] is False
    assert result['rule'] == 'config_conflict', result['message']


def test_http_string_keys_quantity_bounds(ctx):
    """quantities 的字符串 key 同样需与行 id 对齐（否则误报 unknown）。"""
    ds, seed = ctx['ds'], ctx['seed']
    green = str(seed['lines'][('S7-COLOR', 30)])

    result = ItemStructureConfigService(ds).validate(
        seed['structures']['S7-COLOR'],
        selections={green: True}, quantities={green: '4'}, as_of=AS_OF)

    assert result['valid'] is False
    assert result['rule'] == 'item_structure_select_qty_range', result['message']


# ---------------------------------------------------------------- S8 单位换算


def test_s8_box_structure_component_qty(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    result = ItemStructureConfigService(ds).validate(
        seed['structures']['S8-BOX'], qty=2, as_of=AS_OF)
    assert result['valid'] is True
    comps = _components(result)
    assert comps['L0010']['qty'] == 24.0
    assert comps['L0010']['uom_code'] == 'FEA'


# ---------------------------------------------------------------- S9 版本


def test_s9_version_by_effective_date(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    svc = ItemStructureExplodeService(ds)
    item = _item_id(ds, 'SCN-FG-VER')

    old = svc.explode_item(item, as_of='2026-10-26')
    assert old['structure_id'] == seed['structures']['S9-VER-PROD-A']
    assert old['revision'] == 'A'

    new = svc.explode_item(item, as_of='2027-06-01')
    assert new['structure_id'] == seed['structures']['S9-VER-PROD-B']
    assert new['revision'] == 'B'


def test_s9_sales_alternative_no_preferred(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    order_id = _new_order(ds, 'SCN-SO-VER-ALT')
    line_id = _new_order_line(ds, order_id, 'SCN-FG-VER')

    result = SalesOrderExpandService(ds).expand(order_id, line_id, as_of=AS_OF)
    assert result['structure_id'] == seed['structures']['S9-VER-SALES-1']
    assert [row['item_code'] for row in result['lines']] == ['SCN-VER-A-COMP']


# ---------------------------------------------------------------- S10 订单行展开


def test_s10_expand_model_line(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    order_id = seed['order']
    line_id = seed['order_lines']['10']
    svc = SalesOrderExpandService(ds)

    result = svc.expand(order_id, line_id, as_of=AS_OF)

    assert result['pricing_mode'] == 'bundle_price'
    assert result['structure_id'] == seed['structures']['S6-PC']
    assert result['configuration_id']
    assert result['config_hash']
    assert result['component_count'] == 3
    assert [row['component_no'] for row in result['lines']] == [
        'L0010', 'L0020.L0010', 'L0030']
    assert [row['item_code'] for row in result['lines']] == [
        'SCN-COMP-CPU', 'SCN-OPT-RED', 'SCN-SVC-INSTALL']

    service_row = [row for row in result['lines']
                   if row['item_code'] == 'SCN-SVC-INSTALL'][0]
    assert service_row['is_service'] is True
    assert service_row['line_type_code'] == 'SVC'

    parent = ds.query(
        'SELECT configuration_id, pricing_mode FROM sales_order_lines WHERE id = ?',
        [line_id])[0]
    assert parent['configuration_id'] == result['configuration_id']
    assert parent['pricing_mode'] == 'bundle_price'

    # 子行不能再展开；父行不能重复展开
    child_id = result['lines'][0]['id']
    with pytest.raises(SalesOrderExpandError) as exc:
        svc.expand(order_id, child_id, as_of=AS_OF)
    assert exc.value.rule == 'line_is_component'

    with pytest.raises(SalesOrderExpandError) as exc:
        svc.expand(order_id, line_id, as_of=AS_OF)
    assert exc.value.rule == 'line_already_expanded'


def test_s10_expand_pricing_mode_invalid(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    with pytest.raises(SalesOrderExpandError) as exc:
        SalesOrderExpandService(ds).expand(
            seed['order'], seed['order_lines']['20'],
            pricing_mode='standalone', as_of=AS_OF)
    assert exc.value.rule == 'pricing_mode_invalid'


def test_s10_expand_box_line_converts_uom(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    result = SalesOrderExpandService(ds).expand(
        seed['order'], seed['order_lines']['20'], as_of=AS_OF)

    assert result['component_count'] == 1
    row = result['lines'][0]
    assert row['item_code'] == 'SCN-RAW-CAN'
    # 24 个（订单行单位） = 2 箱 × 每箱 12 个
    assert row['qty'] == 24.0
    assert row['uom_code'] == 'FEA'


def test_s10_expand_cross_dimension_uom_rejected(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    with pytest.raises(SalesOrderExpandError) as exc:
        SalesOrderExpandService(ds).expand(
            seed['order'], seed['order_lines']['30'], as_of=AS_OF)
    assert exc.value.rule == 'uom_conversion_not_found'

    line = ds.query(
        'SELECT configuration_id FROM sales_order_lines WHERE id = ?',
        [seed['order_lines']['30']])[0]
    assert line['configuration_id'] is None


def test_s10_expand_requires_draft_order(ctx):
    ds = ctx['ds']
    order_id = _new_order(ds, 'SCN-SO-CONFIRMED', status='confirmed')
    line_id = _new_order_line(ds, order_id, 'SCN-MODEL-PC')

    with pytest.raises(SalesOrderExpandError) as exc:
        SalesOrderExpandService(ds).expand(order_id, line_id, as_of=AS_OF)
    assert exc.value.rule == 'expand_order_not_draft'


def test_s10_expand_line_guards(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    svc = SalesOrderExpandService(ds)
    order_id = seed['order']

    with pytest.raises(SalesOrderExpandError) as exc:
        svc.expand(order_id, 99999999, as_of=AS_OF)
    assert exc.value.rule == 'line_not_found'

    other_order = _new_order(ds, 'SCN-SO-OTHER')
    with pytest.raises(SalesOrderExpandError) as exc:
        svc.expand(other_order, seed['order_lines']['10'], as_of=AS_OF)
    assert exc.value.rule == 'line_order_mismatch'


# ---------------------------------------------------------------- 守卫拒绝


def test_guard_r3_qty_exclusive(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    guard = ItemStructureGuardService(ds)
    with pytest.raises(ItemStructureGuardError) as exc:
        guard.validate_line_write({
            'structure_id': seed['structures']['S1-BIKE'],
            'component_item_id': _item_id(ds, 'SCN-RAW-BOLT'),
            'qty_per': 1, 'fixed_qty': 1,
        })
    assert exc.value.rule == 'item_structure_line_qty_exclusive'


def test_guard_r6_default_requires_optional(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    guard = ItemStructureGuardService(ds)
    with pytest.raises(ItemStructureGuardError) as exc:
        guard.validate_line_write({
            'structure_id': seed['structures']['S1-BIKE'],
            'component_item_id': _item_id(ds, 'SCN-RAW-BOLT'),
            'qty_per': 1, 'optional_flag': 0, 'default_flag': 1,
        })
    assert exc.value.rule == 'item_structure_line_default_requires_optional'


def test_guard_r5_optional_qty_range(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    guard = ItemStructureGuardService(ds)
    with pytest.raises(ItemStructureGuardError) as exc:
        guard.validate_line_write({
            'structure_id': seed['structures']['S5-DESK'],
            'component_item_id': _item_id(ds, 'SCN-OPT-LAMP'),
            'qty_per': 1, 'optional_flag': 1, 'min_qty': 3, 'max_qty': 1,
        })
    assert exc.value.rule == 'item_structure_line_qty_range'


def test_guard_r8_substitute_anchor_duplicate(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    guard = ItemStructureGuardService(ds)
    with pytest.raises(ItemStructureGuardError) as exc:
        guard.validate_line_write({
            'structure_id': seed['structures']['S4-PUMP'],
            'component_item_id': _item_id(ds, 'SCN-RAW-SEAL-B'),
            'qty_per': 1, 'optional_flag': 0, 'substitute_group_code': 'SEAL',
        })
    assert exc.value.rule == 'item_structure_substitute_anchor_duplicate'


def test_guard_r11_service_component_in_production(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    guard = ItemStructureGuardService(ds)
    with pytest.raises(ItemStructureGuardError) as exc:
        guard.validate_line_write({
            'structure_id': seed['structures']['S1-BIKE'],
            'component_item_id': _item_id(ds, 'SCN-SVC-INSTALL'),
            'fixed_qty': 1,
        })
    assert exc.value.rule == 'item_structure_component_service_item'


def test_guard_r17_base_uom_incompatible(ctx):
    ds = ctx['ds']
    guard = ItemStructureGuardService(ds)
    with pytest.raises(ItemStructureGuardError) as exc:
        guard.validate_structure_write({
            'item_id': _item_id(ds, 'SCN-FG-BADUOM'),
            'base_uom_id': 12, 'base_qty': 1, 'valid_from': AS_OF,
            'usage': 'production', 'alternative_no': 1,
        })
    assert exc.value.rule == 'item_structure_base_uom_incompatible'


def test_guard_s3_select_bounds_requires_option_class(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    guard = ItemStructureGuardService(ds)
    with pytest.raises(ItemStructureGuardError) as exc:
        guard.validate_structure_write({
            'item_id': _item_id(ds, 'SCN-FG-BIKE'),
            'min_select': 1,
        })
    assert exc.value.rule == 'item_structure_select_requires_option_class'


def test_guard_d1_structure_with_lines_not_deletable(ctx):
    ds, seed = ctx['ds'], ctx['seed']
    guard = ItemStructureGuardService(ds)
    with pytest.raises(ItemStructureGuardError) as exc:
        guard.validate_structure_delete(seed['structures']['S1-BIKE'])
    assert exc.value.rule == 'item_structure_in_use'
