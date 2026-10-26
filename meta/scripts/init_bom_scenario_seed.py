# -*- coding: utf-8 -*-
"""BOM / 配置域场景种子数据（SCN- 前缀）

用途
----
为物料结构（BOM）、模型配置、销售订单展开三条链路准备**按场景划分**的可重复测试数据，
供后端场景测试、API E2E 与前端 Playwright 用例共用。

场景清单
--------
S1  多层标准生产结构        SCN-FG-BIKE     4 行组件（含半成品、原料、虚拟件、半成品件）
S2  半成品子结构            SCN-SUB-FRAME   有自有生产结构，但非虚拟件 → 展开不递归
S3  虚拟件穿透              SCN-PHANTOM-KIT 生产结构，随 S1 展开穿透为叶子
S4  替代组                  SCN-FG-PUMP     SEAL 组：A 必选锚点 + B 可选替代
S5  可选 / 默认 / 数量区间  SCN-FG-DESK     必选桌面 + 默认抽屉(1~3) + 非默认台灯
S6  销售可配置模型          SCN-MODEL-PC    必选组件 + 选项类容器 + 服务行 + 特征 + 互斥规则
S7  选项类结构              SCN-OC-COLOR    min_select 1 / max_select 2，三个颜色选项
S8  单位换算链路            SCN-FG-BOX-PARENT / SCN-FG-BADUOM  结构基准单位 BOX / 跨量纲 KG
S9  版本与生效期            SCN-FG-VER      生产双版本（2026 / 2027）+ 销售双替代号
S10 展开入口                SCN-SO-BOM-1    草稿订单 + 两条待展开行（模型 / 整箱）

约定
----
· 所有业务编码以 ``SCN-`` 开头，``cleanup`` 只处理该前缀，不触碰其它数据。
· 幂等：按业务键 SELECT 后 UPDATE / INSERT，可重复执行。
· 不经过 BO 层与守卫拦截（直接写表），因此数据必须自身满足 R1~R18 口径。

用法
----
    python -m meta.scripts.init_bom_scenario_seed            # 写入（幂等）
    python -m meta.scripts.init_bom_scenario_seed --cleanup  # 仅清理
    python -m meta.scripts.init_bom_scenario_seed --reset    # 清理后重写
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCN = 'SCN-'
ITEM_GROUP_ID = 4          # FEIG1 前端验证物料组
UOM_FEA = 2                # 个（QTY 组基本单位）
UOM_KG = 12                # 千克（WGT 组基本单位）
UOM_BOX = 15               # 箱（QTY 组，1 箱 = 12 个）

ORDER_NO = 'SCN-SO-BOM-1'
ORDER_DATE = '2026-10-26'

# (code, name, item_type, base_uom, structure_role)
_ITEMS: List[tuple] = [
    ('SCN-FG-BIKE', '场景成品-自行车', 'goods', UOM_FEA, 'none'),
    ('SCN-SUB-FRAME', '场景半成品-车架', 'goods', UOM_FEA, 'none'),
    ('SCN-SUB-WHEEL', '场景半成品-车轮', 'goods', UOM_FEA, 'none'),
    ('SCN-PHANTOM-KIT', '场景虚拟件-包装套件', 'goods', UOM_FEA, 'none'),
    ('SCN-RAW-STEEL', '场景原料-钢材', 'goods', UOM_KG, 'none'),
    ('SCN-RAW-ALU', '场景原料-铝材', 'goods', UOM_KG, 'none'),
    ('SCN-RAW-BOLT', '场景原料-螺栓', 'goods', UOM_FEA, 'none'),
    ('SCN-RAW-NUT', '场景原料-螺母', 'goods', UOM_FEA, 'none'),
    ('SCN-FG-PUMP', '场景成品-水泵', 'goods', UOM_FEA, 'none'),
    ('SCN-RAW-SEAL-A', '场景原料-密封件A', 'goods', UOM_FEA, 'none'),
    ('SCN-RAW-SEAL-B', '场景原料-密封件B', 'goods', UOM_FEA, 'none'),
    ('SCN-FG-DESK', '场景成品-书桌', 'goods', UOM_FEA, 'none'),
    ('SCN-SUB-TOP', '场景半成品-桌面', 'goods', UOM_FEA, 'none'),
    ('SCN-OPT-DRAWER', '场景选件-抽屉', 'goods', UOM_FEA, 'none'),
    ('SCN-OPT-LAMP', '场景选件-台灯', 'goods', UOM_FEA, 'none'),
    ('SCN-MODEL-PC', '场景模型-电脑', 'goods', UOM_FEA, 'model'),
    ('SCN-COMP-CPU', '场景组件-CPU', 'goods', UOM_FEA, 'none'),
    ('SCN-OC-COLOR', '场景选项类-颜色', 'goods', UOM_FEA, 'option_class'),
    ('SCN-OPT-RED', '场景选项-红色', 'goods', UOM_FEA, 'none'),
    ('SCN-OPT-BLUE', '场景选项-蓝色', 'goods', UOM_FEA, 'none'),
    ('SCN-OPT-GREEN', '场景选项-绿色', 'goods', UOM_FEA, 'none'),
    ('SCN-SVC-INSTALL', '场景服务-上门安装', 'service', UOM_FEA, 'none'),
    ('SCN-FG-BOX-PARENT', '场景成品-整箱饮品', 'goods', UOM_FEA, 'none'),
    ('SCN-RAW-CAN', '场景原料-罐装饮品', 'goods', UOM_FEA, 'none'),
    ('SCN-FG-BADUOM', '场景成品-结构单位跨量纲', 'goods', UOM_FEA, 'none'),
    ('SCN-RAW-BADCOMP', '场景原料-跨量纲组件', 'goods', UOM_FEA, 'none'),
    ('SCN-FG-VER', '场景成品-多版本', 'goods', UOM_FEA, 'none'),
    ('SCN-VER-A-COMP', '场景组件-版本A件', 'goods', UOM_FEA, 'none'),
    ('SCN-VER-B-COMP', '场景组件-版本B件', 'goods', UOM_FEA, 'none'),
]


def _line(line_no: int, component: str, **extra) -> Dict[str, Any]:
    row = {'line_no': line_no, 'component': component}
    row.update(extra)
    return row


# key → 结构头 + 行定义
_STRUCTURES: List[Dict[str, Any]] = [
    {
        'key': 'S1-BIKE',
        'item': 'SCN-FG-BIKE', 'usage': 'production', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'description': 'S1 多层标准生产结构',
        'lines': [
            _line(10, 'SCN-SUB-FRAME', qty_per=1),
            _line(20, 'SCN-RAW-STEEL', qty_per=2.5),
            _line(30, 'SCN-PHANTOM-KIT', qty_per=1, phantom_flag=1),
            _line(40, 'SCN-SUB-WHEEL', qty_per=2),
        ],
    },
    {
        'key': 'S2-FRAME',
        'item': 'SCN-SUB-FRAME', 'usage': 'production', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'description': 'S2 半成品子结构（非虚拟件，不递归）',
        'lines': [
            _line(10, 'SCN-RAW-ALU', qty_per=1.8),
            _line(20, 'SCN-RAW-STEEL', qty_per=0.6),
        ],
    },
    {
        'key': 'S3-KIT',
        'item': 'SCN-PHANTOM-KIT', 'usage': 'production', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'description': 'S3 虚拟件自身的生产结构',
        'lines': [
            _line(10, 'SCN-RAW-BOLT', qty_per=4),
            _line(20, 'SCN-RAW-NUT', qty_per=4),
        ],
    },
    {
        'key': 'S4-PUMP',
        'item': 'SCN-FG-PUMP', 'usage': 'production', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'description': 'S4 替代组（必选锚点 + 可选替代）',
        'lines': [
            _line(10, 'SCN-RAW-SEAL-A', qty_per=1, substitute_group_code='SEAL'),
            _line(20, 'SCN-RAW-SEAL-B', qty_per=1, optional_flag=1,
                  substitute_group_code='SEAL'),
        ],
    },
    {
        'key': 'S5-DESK',
        'item': 'SCN-FG-DESK', 'usage': 'production', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'description': 'S5 可选 / 默认 / 数量区间',
        'lines': [
            _line(10, 'SCN-SUB-TOP', qty_per=1),
            _line(20, 'SCN-OPT-DRAWER', qty_per=1, optional_flag=1,
                  default_flag=1, default_qty=2, min_qty=1, max_qty=3),
            _line(30, 'SCN-OPT-LAMP', qty_per=1, optional_flag=1),
        ],
    },
    {
        'key': 'S6-PC',
        'item': 'SCN-MODEL-PC', 'usage': 'sales', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'description': 'S6 销售可配置模型',
        'lines': [
            _line(10, 'SCN-COMP-CPU', qty_per=1),
            _line(20, 'SCN-OC-COLOR', qty_per=1),
            _line(30, 'SCN-SVC-INSTALL', fixed_qty=1),
        ],
    },
    {
        'key': 'S7-COLOR',
        'item': 'SCN-OC-COLOR', 'usage': 'sales', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'min_select': 1, 'max_select': 2,
        'valid_from': '2026-01-01', 'description': 'S7 选项类结构（1~2 项）',
        'lines': [
            _line(10, 'SCN-OPT-RED', qty_per=1, optional_flag=1, default_flag=1),
            _line(20, 'SCN-OPT-BLUE', qty_per=1, optional_flag=1),
            _line(30, 'SCN-OPT-GREEN', qty_per=1, optional_flag=1,
                  min_qty=1, max_qty=3),
        ],
    },
    {
        'key': 'S8-BOX',
        'item': 'SCN-FG-BOX-PARENT', 'usage': 'sales', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_BOX,
        'valid_from': '2026-01-01', 'description': 'S8 结构基准单位 = 箱（1 箱 = 12 个）',
        'lines': [
            _line(10, 'SCN-RAW-CAN', qty_per=12),
        ],
    },
    {
        'key': 'S8-BADUOM',
        'item': 'SCN-FG-BADUOM', 'usage': 'sales', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_KG,
        'valid_from': '2026-01-01', 'description': 'S8 结构基准单位与父项基本单位跨量纲',
        'lines': [
            _line(10, 'SCN-RAW-BADCOMP', qty_per=1),
        ],
    },
    {
        'key': 'S9-VER-PROD-A',
        'item': 'SCN-FG-VER', 'usage': 'production', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'valid_to': '2026-12-31',
        'description': 'S9 生产版本 A（2026 年内有效）',
        'lines': [_line(10, 'SCN-VER-A-COMP', qty_per=1)],
    },
    {
        'key': 'S9-VER-PROD-B',
        'item': 'SCN-FG-VER', 'usage': 'production', 'alternative_no': 1,
        'revision': 'B', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2027-01-01', 'description': 'S9 生产版本 B（2027 起有效）',
        'lines': [_line(10, 'SCN-VER-B-COMP', qty_per=1)],
    },
    {
        'key': 'S9-VER-SALES-1',
        'item': 'SCN-FG-VER', 'usage': 'sales', 'alternative_no': 1,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'description': 'S9 销售替代号 1（优先选中）',
        'lines': [_line(10, 'SCN-VER-A-COMP', qty_per=1)],
    },
    {
        'key': 'S9-VER-SALES-2',
        'item': 'SCN-FG-VER', 'usage': 'sales', 'alternative_no': 2,
        'revision': 'A', 'base_qty': 1, 'base_uom': UOM_FEA,
        'valid_from': '2026-01-01', 'description': 'S9 销售替代号 2（次选）',
        'lines': [_line(10, 'SCN-VER-B-COMP', qty_per=1)],
    },
]

# 模型特征的平台层属性定义（tenant_id = 0）
_ATTRIBUTE_DEFINITION = {
    'tenant_id': 0,
    'code': 'scn_finish',
    'name': '场景-表面处理',
    'data_type': 'string',
    'usage_class': 'descriptive',
    'value_domain_type': 'none',
    'multi_value_flag': 0,
    'is_configurable': 1,
    'status': 'active',
    'revision': 1,
}

_STRUCTURE_ATTRIBUTES = [
    {'structure': 'S6-PC', 'attribute_code': 'scn_finish',
     'required_flag': 0, 'default_value_text': 'matte', 'seq': 1},
]

# 规则：S6 模型中「红色」与「蓝色」互斥
_RULES = [
    {
        'structure': 'S6-PC',
        'code': 'SCN-RULE-COLOR-EXCLUDE',
        'rule_type': 'exclude',
        'severity': 'blocking',
        'priority': 100,
        'message': '红色与蓝色不可同时选择',
        'status': 'active',
        'terms': [
            {'seq': 1, 'clause': 'if', 'target_type': 'structure_line',
             'target_key': ('S7-COLOR', 10), 'operator': 'selected'},
            {'seq': 2, 'clause': 'then', 'target_type': 'structure_line',
             'target_key': ('S7-COLOR', 20), 'operator': 'selected'},
        ],
    },
]

_ORDER = {
    'order_no': ORDER_NO,
    'order_type_id': 1,
    'order_date': ORDER_DATE,
    'status': 'draft',
    'customer_account_id': 4,
    'org_id': 318,
    'sales_org_id': 318,
    'currency_id': 8,
    'exchange_rate': 1.0,
    'description': 'SCN 场景订单：BOM 展开测试用',
}

_ORDER_LINES = [
    {'line_no': '10', 'line_type_id': 101, 'item': 'SCN-MODEL-PC',
     'qty': 1.0, 'uom_id': UOM_FEA, 'unit_price': 100.0},
    {'line_no': '20', 'line_type_id': 101, 'item': 'SCN-FG-BOX-PARENT',
     'qty': 24.0, 'uom_id': UOM_FEA, 'unit_price': 12.0},
    {'line_no': '30', 'line_type_id': 101, 'item': 'SCN-FG-BADUOM',
     'qty': 1.0, 'uom_id': UOM_FEA, 'unit_price': 5.0},
]


# ---------------------------------------------------------------- 写入辅助

def _one(ds, sql: str, params: Iterable[Any]) -> Optional[Dict[str, Any]]:
    rows = ds.query(sql, list(params))
    return rows[0] if rows else None


def _upsert(ds, table: str, key_sql: str, key_params: Iterable[Any],
            data: Dict[str, Any]) -> Any:
    existing = _one(ds, key_sql, key_params)
    if existing:
        changed = {k: v for k, v in data.items() if existing.get(k) != v}
        if changed:
            ds.update(table, existing['id'], changed)
        return existing['id']
    return ds.insert(table, data)


def _item_id(ds, code: str) -> Any:
    row = _one(ds, 'SELECT id FROM items WHERE code = ?', [code])
    if not row:
        raise LookupError(f'物料不存在: {code}')
    return row['id']


def _upsert_item(ds, row: tuple) -> Any:
    code, name, item_type, base_uom, role = row
    data = {
        'code': code,
        'name': name,
        'item_type': item_type,
        'item_group_id': ITEM_GROUP_ID,
        'base_uom': base_uom,
        'structure_role': role,
        'config_match_policy': 'no',
        'config_materialize_policy': 'off',
        'status': 'active',
    }
    return _upsert(ds, 'items', 'SELECT id FROM items WHERE code = ?', [code], data)


def _upsert_structure(ds, spec: Dict[str, Any]) -> Any:
    item_id = _item_id(ds, spec['item'])
    data = {
        'item_id': item_id,
        'usage': spec['usage'],
        'alternative_no': spec['alternative_no'],
        'revision': spec['revision'],
        'base_qty': spec['base_qty'],
        'base_uom_id': spec['base_uom'],
        'min_select': spec.get('min_select'),
        'max_select': spec.get('max_select'),
        'status': 'active',
        'valid_from': spec['valid_from'],
        'valid_to': spec.get('valid_to'),
        'description': spec.get('description'),
    }
    sql = ('SELECT id FROM item_structures WHERE item_id = ? AND usage = ? '
           'AND alternative_no = ? AND revision = ?')
    return _upsert(ds, 'item_structures', sql,
                   [item_id, spec['usage'], spec['alternative_no'], spec['revision']],
                   data)


def _upsert_line(ds, structure_id: Any, line: Dict[str, Any]) -> Any:
    data = {
        'structure_id': structure_id,
        'line_no': line['line_no'],
        'component_item_id': _item_id(ds, line['component']),
        'qty_per': line.get('qty_per'),
        'fixed_qty': line.get('fixed_qty'),
        'scrap_rate': line.get('scrap_rate', 0),
        'optional_flag': line.get('optional_flag', 0),
        'default_flag': line.get('default_flag', 0),
        'default_qty': line.get('default_qty'),
        'min_qty': line.get('min_qty'),
        'max_qty': line.get('max_qty'),
        'valid_from': line.get('valid_from'),
        'valid_to': line.get('valid_to'),
        'operation_seq': line.get('operation_seq'),
        'phantom_flag': line.get('phantom_flag', 0),
        'substitute_group_code': line.get('substitute_group_code'),
        'included_in_base_price': line.get('included_in_base_price', 0),
        'bom_price': line.get('bom_price'),
        'note': line.get('note'),
    }
    sql = 'SELECT id FROM item_structure_lines WHERE structure_id = ? AND line_no = ?'
    return _upsert(ds, 'item_structure_lines', sql,
                   [structure_id, line['line_no']], data)


def _upsert_attribute_definition(ds) -> Any:
    data = dict(_ATTRIBUTE_DEFINITION)
    return _upsert(ds, 'attribute_definitions',
                   'SELECT id FROM attribute_definitions WHERE tenant_id = ? AND code = ?',
                   [data['tenant_id'], data['code']], data)


def _upsert_attribute_scope(ds, definition_id: Any) -> Any:
    data = {
        'tenant_id': 0,
        'attribute_id': definition_id,
        'scope_type': 'object',
        'scope_ref': 'item',
        'required_flag': 0,
        'seq': 10,
        'status': 'active',
        'description': 'SCN 场景：物料对象可用特征',
    }
    sql = ('SELECT id FROM attribute_scopes WHERE tenant_id = ? AND attribute_id = ? '
           'AND scope_type = ? AND scope_ref = ?')
    return _upsert(ds, 'attribute_scopes', sql,
                   [0, definition_id, data['scope_type'], data['scope_ref']], data)


def _upsert_structure_attribute(ds, structure_id: Any, row: Dict[str, Any]) -> Any:
    data = {
        'structure_id': structure_id,
        'attribute_code': row['attribute_code'],
        'required_flag': row.get('required_flag', 0),
        'default_value_text': row.get('default_value_text'),
        'seq': row.get('seq', 1),
        'ui_widget': row.get('ui_widget'),
    }
    sql = 'SELECT id FROM item_structure_attributes WHERE structure_id = ? AND attribute_code = ?'
    return _upsert(ds, 'item_structure_attributes', sql,
                   [structure_id, data['attribute_code']], data)


def _upsert_rule(ds, structure_id: Any, rule: Dict[str, Any],
                 line_ids: Dict[tuple, Any]) -> Any:
    data = {
        'structure_id': structure_id,
        'code': rule['code'],
        'rule_type': rule['rule_type'],
        'severity': rule['severity'],
        'priority': rule['priority'],
        'message': rule['message'],
        'status': rule['status'],
        'description': rule.get('description'),
    }
    rule_id = _upsert(ds, 'config_rules',
                      'SELECT id FROM config_rules WHERE structure_id = ? AND code = ?',
                      [structure_id, rule['code']], data)
    for term in rule.get('terms') or []:
        if term.get('target_key'):
            target_line_id = line_ids[tuple(term['target_key'])]
        else:
            target_line_id = term.get('target_line_id')
        term_data = {
            'rule_id': rule_id,
            'seq': term['seq'],
            'clause': term['clause'],
            'target_type': term['target_type'],
            'target_line_id': target_line_id,
            'target_class_item_id': term.get('target_class_item_id'),
            'attribute_code': term.get('attribute_code'),
            'operator': term['operator'],
            'value_text': term.get('value_text'),
            'value_number': term.get('value_number'),
            'value_number_to': term.get('value_number_to'),
            'value_list': term.get('value_list'),
        }
        _upsert(ds, 'config_rule_terms',
                'SELECT id FROM config_rule_terms WHERE rule_id = ? AND seq = ?',
                [rule_id, term['seq']], term_data)
    return rule_id


def _upsert_order(ds, order: Dict[str, Any]) -> Any:
    data = dict(order)
    return _upsert(ds, 'sales_orders',
                   'SELECT id FROM sales_orders WHERE order_no = ?',
                   [order['order_no']], data)


def _upsert_order_line(ds, order_id: Any, line: Dict[str, Any]) -> Any:
    data = {
        'order_id': order_id,
        'line_no': line['line_no'],
        'line_type_id': line['line_type_id'],
        'item_id': _item_id(ds, line['item']),
        'qty': line['qty'],
        'uom_id': line['uom_id'],
        'unit_price': line.get('unit_price'),
        'status': 'open',
        'pricing_mode': 'standalone',
    }
    sql = 'SELECT id FROM sales_order_lines WHERE order_id = ? AND line_no = ?'
    return _upsert(ds, 'sales_order_lines', sql,
                   [order_id, line['line_no']], data)


# ---------------------------------------------------------------- 对外接口

def ensure_schemas_registered() -> None:
    """写表前需要把 YAML schema 注册进全局 registry（table_name 白名单依赖它）。"""
    from meta.core import table_name_validator
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    register_from_directory(get_yaml_schema_dir())
    table_name_validator.invalidate_cache()


def seed_bom_scenario_data(ds) -> Dict[str, Any]:
    """写入全部 SCN 场景数据；返回引用映射（items / structures / lines / rules / order）。"""
    ensure_schemas_registered()
    items: Dict[str, Any] = {}
    for row in _ITEMS:
        items[row[0]] = _upsert_item(ds, row)

    structures: Dict[str, Any] = {}
    line_ids: Dict[tuple, Any] = {}
    for spec in _STRUCTURES:
        structure_id = _upsert_structure(ds, spec)
        structures[spec['key']] = structure_id
        for line in spec['lines']:
            line_ids[(spec['key'], line['line_no'])] = _upsert_line(
                ds, structure_id, line)

    definition_id = _upsert_attribute_definition(ds)
    _upsert_attribute_scope(ds, definition_id)
    for row in _STRUCTURE_ATTRIBUTES:
        _upsert_structure_attribute(ds, structures[row['structure']], row)

    rules: Dict[str, Any] = {}
    for rule in _RULES:
        rules[rule['code']] = _upsert_rule(ds, structures[rule['structure']],
                                           rule, line_ids)

    order_id = _upsert_order(ds, _ORDER)
    order_lines: Dict[str, Any] = {}
    for line in _ORDER_LINES:
        order_lines[line['line_no']] = _upsert_order_line(ds, order_id, line)

    ds.commit()
    return {
        'items': items,
        'structures': structures,
        'lines': line_ids,
        'rules': rules,
        'attribute_definition_id': definition_id,
        'order': order_id,
        'order_lines': order_lines,
    }


_CLEANUP_SQL = [
    # 订单行先解绑配置与父子关系，否则删 configurations 时被子行 / 父行引用
    ('sales_order_lines.unlink',
     "UPDATE sales_order_lines SET configuration_id = NULL, parent_line_id = NULL "
     f"WHERE order_id IN (SELECT id FROM sales_orders WHERE order_no = '{ORDER_NO}')"),
    # 配置实例（结构上的求解结果）
    ('configuration_components',
     "DELETE FROM configuration_components WHERE configuration_id IN ("
     "SELECT c.id FROM configurations c JOIN item_structures s ON s.id = c.structure_id "
     "JOIN items i ON i.id = s.item_id WHERE i.code LIKE 'SCN-%' AND i.code NOT LIKE 'SCN-SO-%')"),
    ('configuration_values',
     "DELETE FROM configuration_values WHERE configuration_id IN ("
     "SELECT c.id FROM configurations c JOIN item_structures s ON s.id = c.structure_id "
     "JOIN items i ON i.id = s.item_id WHERE i.code LIKE 'SCN-%' AND i.code NOT LIKE 'SCN-SO-%')"),
    ('configurations',
     "DELETE FROM configurations WHERE structure_id IN ("
     "SELECT s.id FROM item_structures s JOIN items i ON i.id = s.item_id "
     "WHERE i.code LIKE 'SCN-%' AND i.code NOT LIKE 'SCN-SO-%')"),
    # 规则与特征
    ('config_rule_terms',
     "DELETE FROM config_rule_terms WHERE rule_id IN ("
     "SELECT r.id FROM config_rules r JOIN item_structures s ON s.id = r.structure_id "
     "JOIN items i ON i.id = s.item_id WHERE i.code LIKE 'SCN-%' AND i.code NOT LIKE 'SCN-SO-%')"),
    ('config_rules',
     "DELETE FROM config_rules WHERE structure_id IN ("
     "SELECT s.id FROM item_structures s JOIN items i ON i.id = s.item_id "
     "WHERE i.code LIKE 'SCN-%' AND i.code NOT LIKE 'SCN-SO-%')"),
    ('item_structure_attributes',
     "DELETE FROM item_structure_attributes WHERE structure_id IN ("
     "SELECT s.id FROM item_structures s JOIN items i ON i.id = s.item_id "
     "WHERE i.code LIKE 'SCN-%' AND i.code NOT LIKE 'SCN-SO-%')"),
    # 结构与行
    ('item_structure_lines',
     "DELETE FROM item_structure_lines WHERE structure_id IN ("
     "SELECT s.id FROM item_structures s JOIN items i ON i.id = s.item_id "
     "WHERE i.code LIKE 'SCN-%' AND i.code NOT LIKE 'SCN-SO-%')"),
    ('item_structures',
     "DELETE FROM item_structures WHERE item_id IN (SELECT id FROM items "
     "WHERE code LIKE 'SCN-%' AND code NOT LIKE 'SCN-SO-%')"),
    # 订单与行
    ('sales_order_lines',
     "DELETE FROM sales_order_lines WHERE order_id IN ("
     f"SELECT id FROM sales_orders WHERE order_no = '{ORDER_NO}')"),
    ('sales_orders',
     f"DELETE FROM sales_orders WHERE order_no = '{ORDER_NO}'"),
    # 物料与换算
    ('item_uom_conversions',
     "DELETE FROM item_uom_conversions WHERE item_id IN ("
     "SELECT id FROM items WHERE code LIKE 'SCN-%' AND code NOT LIKE 'SCN-SO-%')"),
    ('items', "DELETE FROM items WHERE code LIKE 'SCN-%' AND code NOT LIKE 'SCN-SO-%'"),
    # 属性定义与范围
    ('attribute_scopes',
     "DELETE FROM attribute_scopes WHERE attribute_id IN ("
     "SELECT id FROM attribute_definitions WHERE code = 'scn_finish')"),
    ('attribute_definitions',
     "DELETE FROM attribute_definitions WHERE code = 'scn_finish' AND tenant_id = 0"),
]


def cleanup_bom_scenario_data(ds) -> Dict[str, int]:
    """按反向依赖顺序清理 SCN- 前缀数据；返回各表删除行数。"""
    ensure_schemas_registered()
    counts: Dict[str, int] = {}
    for table, sql in _CLEANUP_SQL:
        result = ds.execute(sql)
        rowcount = getattr(result, 'rowcount', None)
        counts[table] = -1 if rowcount is None or rowcount < 0 else rowcount
    ds.commit()
    return counts


def reset_bom_scenario_data(ds) -> Dict[str, Any]:
    """先清理再写入，返回种子引用映射。"""
    cleanup_bom_scenario_data(ds)
    return seed_bom_scenario_data(ds)


def _main(argv: List[str]) -> int:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    from meta.core.datasource import get_data_source  # noqa: E402
    from meta.tests.test_utils import get_meta_db_path  # noqa: E402

    ds = get_data_source('sqlite', database=str(get_meta_db_path()))
    action = argv[1] if len(argv) > 1 else ''

    if action == '--cleanup':
        counts = cleanup_bom_scenario_data(ds)
        print('[cleanup]', counts)
    elif action == '--reset':
        seed = reset_bom_scenario_data(ds)
        print('[reset] structures=%d lines=%d order=%s'
              % (len(seed['structures']), len(seed['lines']), seed['order']))
    else:
        seed = seed_bom_scenario_data(ds)
        print('[seed] items=%d structures=%d lines=%d rules=%d order=%s'
              % (len(seed['items']), len(seed['structures']),
                 len(seed['lines']), len(seed['rules']), seed['order']))
    return 0


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))
