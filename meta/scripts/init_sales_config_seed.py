# -*- coding: utf-8 -*-
"""销售配置种子数据 —— 行类型 / 单据类型 / 控制参数

依据:
  meta/schemas/type_definition.yaml（类型字典，scope_bo + level 判别）
  meta/schemas/control_parameter_def.yaml（进入门槛 ③：sales 域首期参数 ≤ 12 个）

范围:
  行类型 5 条（STD / SVC / RET / FOC / TXT）→ type_definitions, level='line'
  单据类型 2 条（TA 标准订单 / RE 退货订单）→ type_definitions, level='header'
  控制参数 9 条 = 8 个行为开关 + default_payment_term（ref → payment_term）

幂等: by (scope_bo, level, code) upsert（先 SELECT → UPDATE / INSERT）
      重跑只刷新业务属性，不重置 status（停用≠删除，沿 currency / region 种子同一约定）
      default_payment_term 的 default_value 留空 —— 付款条件属业务主数据，
      种子不预设具体记录，避免引用不存在的主键。

[类型统一 2026-10-25] 旧表 sales_line_types / sales_document_types 已降级为
只读视图，写入统一落到 type_definitions；列名口径见两处 view_definition。
"""

import logging

logger = logging.getLogger(__name__)

#: (code, 中文名, category, 说明)
_LINE_TYPES = [
    ('STD', '标准物料行', 'material', '常规物料销售行，参与定价与库存'),
    ('SVC', '服务行', 'service', '服务类销售行，不产生库存移动'),
    ('RET', '退货行', 'return', '退货行，方向与标准行相反'),
    ('FOC', '免费行', 'free_of_charge', '免费赠送行，不计价但扣减库存'),
    ('TXT', '文本行', 'text', '纯说明行，不定价、不影响库存'),
]

#: (code, 中文名, category, 默认行类型编码, 说明)
_DOC_TYPES = [
    ('TA', '标准销售订单', 'standard', 'STD', '标准订单，默认物料行'),
    ('RE', '退货订单', 'return', 'RET', '退货订单，默认退货行'),
]

#: (code, 中文名, domain, value_type, target_bo, default_value, 用途说明)
#: target_bo 仅 value_type='ref' 时有值；domain 决定参数归属的配置域（sales / procurement / ...）
_PARAMS = [
    ('allow_partial_delivery', '允许部分交货', 'sales', 'bool', None, 'true',
     '订单行是否允许按少于订购数量的数量交货'),
    ('allow_over_delivery', '允许超量交货', 'sales', 'bool', None, 'false',
     '订单行是否允许交货数量超过订购数量'),
    ('allow_under_delivery', '允许欠量交货', 'sales', 'bool', None, 'false',
     '订单行是否允许交货数量少于订购数量而不需审批'),
    ('pricing_relevant', '行参与定价', 'sales', 'bool', None, 'true',
     '该行是否进入定价流程；文本行等应关闭'),
    ('billing_relevant', '行参与开票', 'sales', 'bool', None, 'true',
     '该行是否进入开票流程'),
    ('inventory_effect', '行影响库存', 'sales', 'bool', None, 'true',
     '该行是否产生库存移动（服务行 / 文本行应关闭）'),
    ('cost_relevant', '行参与成本', 'sales', 'bool', None, 'true',
     '该行是否计入成本核算'),
    ('require_customer_po', '客户订单号必填', 'sales', 'bool', None, 'true',
     '单据行是否必须填写客户采购订单号'),
    ('default_payment_term', '默认付款条件', 'sales', 'ref', 'payment_term', None,
     '未在客户账户上指定付款条件时使用的默认值（引用 payment_term）'),
    # ===== 行录入约束（波次 0）=====
    ('qty_required', '行数量必录', 'sales', 'bool', None, 'true',
     '单据行是否必须录入数量；文本行按行类型置 false'),
    ('price_required', '行单价必录', 'sales', 'bool', None, 'true',
     '单据行是否必须录入单价；免费行 / 文本行按行类型置 false'),
    ('default_incoterm', '默认贸易条款', 'sales', 'string', None, None,
     '单据类型与客户账户都未给贸易条款时的兜底代码（Incoterms 2020 三字码）'),
    # ===== 税务（波次 0）=====
    ('default_tax_code', '默认税码', 'sales', 'ref', 'tax_code', None,
     '客户档案 / 物料主数据均未指定税务分类时使用的兜底税码（引用 tax_code）'),
    ('tax_included_pricing', '价格含税', 'sales', 'bool', None, 'false',
     '单据价格是否含税。含税时税额由净价倒算（tax = gross - gross/(1+rate)），'
     '不含税时按净价正算（tax = net * rate）；税额舍入取币种小数位'),
    ('tax_date_basis', '税率取用基准日', 'sales', 'enum', None, 'document_date',
     '按哪个日期选取生效税率段：document_date（单据日期）或 delivery_date（交货日期）；'
     '波次 0 只实现 document_date，delivery_date 待交货单据落地后启用'),
]


#: 类型字典的归属域（消费方 BO 的 YAML id）
_SCOPE_BO = 'sales_order'

#: 控制参数取值（波次 0 只配行类型的例外）
#: (参数编码, 行类型编码, 取值, 说明) —— 维度只用到 line_type_id，其余维度留空
_PARAM_VALUES = [
    ('qty_required', 'TXT', 'false', '文本行无数量'),
    ('price_required', 'TXT', 'false', '文本行无单价'),
    ('price_required', 'FOC', 'false', '免费行单价为 0'),
    ('pricing_relevant', 'TXT', 'false', '文本行不参与定价'),
]


def _type_id(ds, code, level):
    """按 (scope_bo, level, code) 查类型字典主键。"""
    rows = ds.query(
        "SELECT id FROM type_definitions "
        "WHERE scope_bo = ? AND level = ? AND code = ?",
        [_SCOPE_BO, level, code])
    return rows[0].get('id') if rows else None


def _upsert_line_types(ds):
    inserted = updated = 0
    for code, name, category, desc in _LINE_TYPES:
        existing_id = _type_id(ds, code, 'line')
        if existing_id:
            ds.execute(
                "UPDATE type_definitions SET name = ?, line_category = ?, "
                "description = ? WHERE id = ?",
                [name, category, desc, existing_id])
            updated += 1
        else:
            ds.execute(
                "INSERT INTO type_definitions "
                "(code, name, scope_bo, level, line_category, status, "
                " description, created_at) "
                "VALUES (?, ?, ?, 'line', ?, 'active', ?, datetime('now'))",
                [code, name, _SCOPE_BO, category, desc])
            inserted += 1
    return inserted, updated


def _upsert_doc_types(ds):
    inserted = updated = 0
    for code, name, category, default_line_code, desc in _DOC_TYPES:
        line_id = _type_id(ds, default_line_code, 'line')
        existing_id = _type_id(ds, code, 'header')
        if existing_id:
            ds.execute(
                "UPDATE type_definitions SET name = ?, document_category = ?, "
                "default_type_id = ?, description = ? WHERE id = ?",
                [name, category, line_id, desc, existing_id])
            updated += 1
        else:
            ds.execute(
                "INSERT INTO type_definitions "
                "(code, name, scope_bo, level, document_category, "
                " default_type_id, status, description, created_at) "
                "VALUES (?, ?, ?, 'header', ?, ?, 'active', ?, datetime('now'))",
                [code, name, _SCOPE_BO, category, line_id, desc])
            inserted += 1
    return inserted, updated


def _upsert_params(ds):
    inserted = updated = 0
    for code, name, domain, value_type, target_bo, default_value, desc in _PARAMS:
        existing = ds.query(
            "SELECT id FROM control_parameter_defs WHERE code = ?", [code])
        if existing:
            # 值类型与语义属不可变字段：仅刷新显示名、默认值与说明
            ds.execute(
                "UPDATE control_parameter_defs SET name = ?, "
                "default_value = ?, description = ? WHERE code = ?",
                [name, default_value, desc, code])
            updated += 1
        else:
            ds.execute(
                "INSERT INTO control_parameter_defs "
                "(code, name, domain, value_type, target_bo, default_value, "
                " status, description, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'))",
                [code, name, domain, value_type, target_bo, default_value, desc])
            inserted += 1
    return inserted, updated


def _param_id(ds, code):
    rows = ds.query(
        "SELECT id FROM control_parameter_defs WHERE code = ?", [code])
    return rows[0].get('id') if rows else None


def _upsert_param_values(ds):
    inserted = updated = 0
    for param_code, line_code, value, desc in _PARAM_VALUES:
        param_id = _param_id(ds, param_code)
        line_id = _type_id(ds, line_code, 'line')
        if not param_id or not line_id:
            logger.warning(
                '[sales config seed] 跳过取值 %s/%s：参数或行类型缺失',
                param_code, line_code)
            continue
        existing = ds.query(
            "SELECT id FROM control_parameter_values "
            "WHERE control_parameter_id = ? AND line_type_id = ? "
            "  AND org_id IS NULL AND document_type_id IS NULL "
            "  AND item_group_id IS NULL AND specificity_rank = 100",
            [param_id, line_id])
        if existing:
            ds.execute(
                "UPDATE control_parameter_values SET value = ?, description = ? "
                "WHERE id = ?",
                [value, desc, existing[0].get('id')])
            updated += 1
        else:
            ds.execute(
                "INSERT INTO control_parameter_values "
                "(control_parameter_id, line_type_id, specificity_rank, value, "
                " status, description, created_at) "
                "VALUES (?, ?, 100, ?, 'active', ?, datetime('now'))",
                [param_id, line_id, value, desc])
            inserted += 1
    return inserted, updated


def init_sales_config_seed_data(data_source):
    """幂等写入销售配置种子。返回各分组的 (inserted, updated) 计数。

    顺序固定：行类型 → 单据类型 → 控制参数 → 控制参数取值（后者引用前者的主键）。
    不重置 status：已停用的记录重跑保持 inactive。
    """
    line_types = _upsert_line_types(data_source)
    doc_types = _upsert_doc_types(data_source)
    params = _upsert_params(data_source)
    values = _upsert_param_values(data_source)
    data_source.commit()
    logger.info(
        'Sales config seeded: line_types %s, doc_types %s, params %s, values %s',
        line_types, doc_types, params, values)
    return {'line_types': line_types, 'doc_types': doc_types,
            'params': params, 'values': values}


if __name__ == '__main__':
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path

    _db_path = get_meta_db_path()
    _ds = get_data_source('sqlite', database=str(_db_path))
    _result = init_sales_config_seed_data(_ds)
    print(f'[sales config seed] db={_db_path}')
    for group, (ins, upd) in _result.items():
        print(f'[sales config seed] {group}: {ins} inserted, {upd} updated')
