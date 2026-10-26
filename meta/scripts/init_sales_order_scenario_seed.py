# -*- coding: utf-8 -*-
"""销售订单域场景种子数据（SCN- 前缀）

用途
----
为销售订单**已交付的多个波次**准备按场景划分、可重复写入的测试数据，并提供
真实库 `--verify` 自检（守卫 / 定价 / 金额 / 默认值解析服务）。

本脚本只覆盖销售订单域自身；销售区域（territory M1~M4）由
``init_territory_scenario_seed.py`` 负责，两者用不同的业务码前缀，互不覆盖。

场景清单
--------
S0  结构落点              客户 A~D（含 party / party_relation / 档案 / 地址 / 销售员）
S1  W0 标准单金额          3 行不同精度 → 行级先舍入、抬头汇总（R7 / R11）
S2  W0 退货单符号          退货单据类别 → 整行金额取负（R3）
S3  W0 守卫反例            qty≤0 / 缺单位 / 缺物料且无描述 / 行类型越界 / 组织无销售职能
S4  W0 冻结                确认后禁改 currency / exchange_rate / 禁删行（R8 / R9）
S5  W1-A 定价链            客户价优先 → 物料价兜底（W2-F 多槽位）、折扣 10% + 附加费 3% 叠乘
S6  W1-A 失败降级          NO_CANDIDATE / CURRENCY_MISMATCH / ZERO_QTY / NEGATIVE_AMOUNT
S7  W1-A 手工价保护        price_source=manual 不被覆盖，force=True 才重取
S8  W1-B 组织段覆盖        组织行逐字段覆盖 + 停用行忽略 + 无组织行回退账户级
S9  W1-C 地址带出          默认收货 / 收票地址，缺一侧留空不阻断
S10 W1-D 销售员带出        组织专属优先于通用 / 停用不带出 / 非主不带出
S11 W2-A 服务行            默认值只补空 + W2-SVC-1~5 与 W2-R5 反例
S12 W2-D 地址文本快照      确认时按地址库回填（R-ADR-3）+ 离草稿后只读（R-ADR-1/2）
E6  退货引用链            退货行引用已确认原行 + 引用草稿原单被拒（R-RET-1~9）

约定
----
· 业务编码统一 ``SCN-SO-`` 前缀（订单 ``SCN-SO-W…``），``--cleanup`` 只删该前缀。
· 幂等：按业务键 SELECT 后 UPDATE / INSERT，可重复执行。
· 直接写表、不经过 BO 层与守卫拦截，因此数据自身必须满足 W0/W1/W2 口径。
· 物料、客户、价格全部自建（``SCN-SO-`` 前缀），不依赖其他场景脚本，
  避免与 BOM / territory 种子的 ``--cleanup`` 范围重叠。

用法
----
    python -m meta.scripts.init_sales_order_scenario_seed            # 写入（幂等）
    python -m meta.scripts.init_sales_order_scenario_seed --verify   # 自检
    python -m meta.scripts.init_sales_order_scenario_seed --cleanup  # 仅清理
    python -m meta.scripts.init_sales_order_scenario_seed --reset    # 清理后重写
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------- 真实库固定值
SALES_ORG_ID = 318          # 华东销售中心（org_functions.function_type='sales'）
INTERNAL_PARTY_ID = 17      # 华东销售中心的内部 party 表示（我方侧）
LE_ORG_ID = 315             # 上海用友 YonBIP 有限公司（法人）
PARTY_GROUP_CUSTOMER = 6    # C_KEY_ACCOUNT 重点客户组
ITEM_GROUP_ID = 4           # FEIG1 前端验证物料组

CURRENCY_CNY = 8
CURRENCY_USD = 9
UOM_FEA = 2

ADDR_SH = 6                 # 上海张江
ADDR_BJ = 7                 # 北京建国门
ADDR_NJ = 8                 # 南京中山路

ORDER_TYPE_STD = 1          # TA 标准销售订单
ORDER_TYPE_RET = 2          # RE 退货订单
LINE_STD = 101              # STD
LINE_SVC = 102              # SVC
LINE_RET = 103              # RET

TAX_13 = 1                  # CN_VAT_13
TAX_6 = 3                   # CN_VAT_6
PAYMENT_TERM_NET30 = 1      # NET30

RATE_TABLE_STD = 1          # PL_STD（approved / CNY）
RT_LIST_PRICE = 1           # RT_LIST_PRICE
RT_DISC_LINE = 2            # RT_DISC_LINE
RT_SURCHARGE_LINE = 3       # RT_SURCHARGE_LINE
KS_ITEM = 1                 # KS_ITEM
KS_ITEM_CUST = 3            # KS_ITEM_CUST

ORDER_DATE = '2026-10-26'
VALID_FROM = '2026-01-01'

ORDER_PREFIX = 'SCN-SO-W'
CODE_PREFIX = 'SCN-SO-'

# 本脚本基础物料：(code, name, item_type, base_uom)
_BASE_ITEMS: List[tuple] = [
    ('SCN-SO-ITEM-CPU', '场景组件-CPU', 'goods', UOM_FEA),
    ('SCN-SO-ITEM-BIKE', '场景成品-自行车', 'goods', UOM_FEA),
    ('SCN-SO-ITEM-NUT', '场景原料-螺母', 'goods', UOM_FEA),
]

# 本脚本自有物料：(code, name, item_type, base_uom, status, service_defaults)
_OWN_ITEMS: List[Dict[str, Any]] = [
    {'code': 'SCN-SO-ITEM-SVC-STD', 'name': '场景服务-标准维保',
     'item_type': 'service', 'base_uom': UOM_FEA, 'status': 'active',
     'service': {'billing_method_default': 'fixed_price',
                 'required_resource_type': 'technician',
                 'standard_duration': 2.0, 'duration_type': 'day'}},
    {'code': 'SCN-SO-ITEM-SVC-OFF', 'name': '场景服务-已停用',
     'item_type': 'service', 'base_uom': UOM_FEA, 'status': 'inactive',
     'service': {}},
    {'code': 'SCN-SO-ITEM-SVC-NODEF', 'name': '场景服务-无默认值',
     'item_type': 'service', 'base_uom': UOM_FEA, 'status': 'active',
     'service': {}},
    {'code': 'SCN-SO-ITEM-NEG', 'name': '场景成品-折扣过深',
     'item_type': 'goods', 'base_uom': UOM_FEA, 'status': 'active',
     'service': {}},
]

# 客户：档案默认值 / 组织差异行 / 地址 / 说明
_CUSTOMERS: List[Dict[str, Any]] = [
    {'key': 'A', 'party_code': 'SCN-SO-PTY-A', 'name': 'SCN-SO-客户A',
     'account': {'default_payment_term_id': None, 'default_incoterm_code': None},
     'org_row': {'payment_term_id': PAYMENT_TERM_NET30, 'incoterm_code': 'FOB',
                 'currency_id': CURRENCY_USD, 'status': 'active'},
     'addresses': [('ship_to', ADDR_SH), ('bill_to', ADDR_BJ)],
     'note': '组织段覆盖 + 双地址 + 主销售员（通用）'},
    {'key': 'B', 'party_code': 'SCN-SO-PTY-B', 'name': 'SCN-SO-客户B',
     'account': {'default_payment_term_id': PAYMENT_TERM_NET30,
                 'default_incoterm_code': 'DAP'},
     'org_row': None,
     'addresses': [('ship_to', ADDR_NJ)],
     'note': '无组织行 → 回退账户级；只有收货地址'},
    {'key': 'C', 'party_code': 'SCN-SO-PTY-C', 'name': 'SCN-SO-客户C',
     'account': {'default_payment_term_id': PAYMENT_TERM_NET30,
                 'default_incoterm_code': 'EXW'},
     'org_row': {'payment_term_id': None, 'incoterm_code': 'CIF',
                 'currency_id': CURRENCY_USD, 'status': 'inactive'},
     'addresses': [],
     'note': '组织行已停用 → 不参与覆盖；销售员已停用 → 不带出'},
    {'key': 'D', 'party_code': 'SCN-SO-PTY-D', 'name': 'SCN-SO-客户D',
     'account': {'default_payment_term_id': None, 'default_incoterm_code': None},
     'org_row': None,
     'addresses': [],
     'note': '无任何默认值 / 地址 / 主销售员（fail-open 留空）'},
]

# (code, name, status)
_SALESPEOPLE: List[tuple] = [
    ('SCN-SO-SP-1', '场景销售员-通用', 'active'),
    ('SCN-SO-SP-2', '场景销售员-华东专属', 'active'),
    ('SCN-SO-SP-OFF', '场景销售员-已停用', 'inactive'),
]

# (客户 key, sales_org_id, 销售员 code, is_primary, status)
_ASSIGNMENTS: List[tuple] = [
    ('A', None, 'SCN-SO-SP-1', 1, 'active'),          # 通用主销售员
    ('B', SALES_ORG_ID, 'SCN-SO-SP-2', 1, 'active'),  # 组织专属优先
    ('B', None, 'SCN-SO-SP-1', 1, 'active'),          # 通用兜底
    ('C', SALES_ORG_ID, 'SCN-SO-SP-OFF', 1, 'active'),  # 销售员本身停用 → 不带出
    ('D', SALES_ORG_ID, 'SCN-SO-SP-1', 0, 'active'),    # 非主销售员 → 不带出
]

# 定价价目行：全部挂在 PL_STD（approved / CNY），valid_from 2026-01-01
_RATE_RECORDS: List[Dict[str, Any]] = [
    {'code': 'SCN-SO-RR-CPU-LIST', 'item': 'SCN-SO-ITEM-CPU',
     'key_schema': KS_ITEM, 'keys': {'item_id': 'SCN-SO-ITEM-CPU'},
     'rate_type': RT_LIST_PRICE, 'rate': '100.0'},
    {'code': 'SCN-SO-RR-CPU-CUSTA', 'item': 'SCN-SO-ITEM-CPU',
     'key_schema': KS_ITEM_CUST,
     'keys': {'customer_account_id': 'A', 'item_id': 'SCN-SO-ITEM-CPU'},
     'rate_type': RT_LIST_PRICE, 'rate': '80.0'},
    {'code': 'SCN-SO-RR-CPU-DISC', 'item': 'SCN-SO-ITEM-CPU',
     'key_schema': KS_ITEM, 'keys': {'item_id': 'SCN-SO-ITEM-CPU'},
     'rate_type': RT_DISC_LINE, 'rate': '10.0'},
    {'code': 'SCN-SO-RR-CPU-SUR', 'item': 'SCN-SO-ITEM-CPU',
     'key_schema': KS_ITEM, 'keys': {'item_id': 'SCN-SO-ITEM-CPU'},
     'rate_type': RT_SURCHARGE_LINE, 'rate': '3.0'},
    {'code': 'SCN-SO-RR-NEG-LIST', 'item': 'SCN-SO-ITEM-NEG',
     'key_schema': KS_ITEM, 'keys': {'item_id': 'SCN-SO-ITEM-NEG'},
     'rate_type': RT_LIST_PRICE, 'rate': '100.0'},
    {'code': 'SCN-SO-RR-NEG-DISC', 'item': 'SCN-SO-ITEM-NEG',
     'key_schema': KS_ITEM, 'keys': {'item_id': 'SCN-SO-ITEM-NEG'},
     'rate_type': RT_DISC_LINE, 'rate': '150.0'},
    {'code': 'SCN-SO-RR-SVC-LIST', 'item': 'SCN-SO-ITEM-SVC-STD',
     'key_schema': KS_ITEM, 'keys': {'item_id': 'SCN-SO-ITEM-SVC-STD'},
     'rate_type': RT_LIST_PRICE, 'rate': '200.0'},
]

_ORDERS: List[Dict[str, Any]] = [
    # ---- S1 / S3 / S4：W0 标准单与守卫
    {'order_no': 'SCN-SO-W0-1', 'customer': 'A', 'order_type_id': ORDER_TYPE_STD,
     'status': 'draft', 'currency_id': CURRENCY_CNY,
     'description': 'W0 标准单：行级舍入 + 抬头汇总',
     'head': {'payment_term_id': PAYMENT_TERM_NET30, 'incoterm_code': 'FOB'},
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-CPU',
          'qty': 3.0, 'unit_price': 100.0, 'tax_code_id': TAX_13},
         {'line_no': '20', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-BIKE',
          'qty': 2.0, 'unit_price': 12.5, 'tax_code_id': TAX_13},
         {'line_no': '30', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-BIKE',
          'qty': 1.0, 'unit_price': 13.335, 'tax_code_id': TAX_13},
     ]},
    # ---- S2：W0 退货单
    {'order_no': 'SCN-SO-W0-RET-1', 'customer': 'A',
     'order_type_id': ORDER_TYPE_RET, 'status': 'draft',
     'currency_id': CURRENCY_CNY,
     'description': 'W0 退货单：整行金额取负',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_RET, 'item': 'SCN-SO-ITEM-CPU',
          'qty': 1.0, 'unit_price': 100.0, 'tax_code_id': TAX_13},
     ]},
    # ---- S5 / S7：W1-A 定价链（客户价优先 + 折扣 / 附加费）
    {'order_no': 'SCN-SO-W1-PRICE-1', 'customer': 'A',
     'order_type_id': ORDER_TYPE_STD, 'status': 'draft',
     'currency_id': CURRENCY_CNY, 'price_date': ORDER_DATE,
     'head': {'payment_term_id': PAYMENT_TERM_NET30, 'incoterm_code': 'FOB',
              'ship_to_address_id': ADDR_SH, 'bill_to_address_id': ADDR_BJ,
              'salesperson': 'SCN-SO-SP-1'},
     'description': 'W1-A 客户价优先（80 覆盖 100）+ 10% 折扣 + 3% 附加费',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-CPU',
          'qty': 5.0, 'unit_price': None, 'tax_code_id': TAX_13},
     ]},
    # ---- S5：物料价兜底（客户无客户价）
    {'order_no': 'SCN-SO-W1-CUSTB-1', 'customer': 'B',
     'order_type_id': ORDER_TYPE_STD, 'status': 'draft',
     'currency_id': CURRENCY_CNY, 'price_date': ORDER_DATE,
     'description': 'W1-A 客户无客户价 → 落物料次槽（100）',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-CPU',
          'qty': 5.0, 'unit_price': None, 'tax_code_id': TAX_13},
     ]},
    # ---- S6：无候选 / 币种不符
    {'order_no': 'SCN-SO-W1-NOCAND-1', 'customer': 'A',
     'order_type_id': ORDER_TYPE_STD, 'status': 'draft',
     'currency_id': CURRENCY_CNY, 'price_date': ORDER_DATE,
     'description': 'W1-A 物料无价目行 → NO_CANDIDATE（失败不阻保存）',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-NUT',
          'qty': 2.0, 'unit_price': None, 'tax_code_id': TAX_13},
     ]},
    {'order_no': 'SCN-SO-W1-CCY-1', 'customer': 'A',
     'order_type_id': ORDER_TYPE_STD, 'status': 'draft',
     'currency_id': CURRENCY_USD, 'price_date': ORDER_DATE,
     'description': 'W1-A 订单币种与价目表不一致 → CURRENCY_MISMATCH',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-CPU',
          'qty': 1.0, 'unit_price': None, 'tax_code_id': TAX_13},
     ]},
    # ---- S7：手工价保护
    {'order_no': 'SCN-SO-W1-MANUAL-1', 'customer': 'A',
     'order_type_id': ORDER_TYPE_STD, 'status': 'draft',
     'currency_id': CURRENCY_CNY, 'price_date': ORDER_DATE,
     'description': 'W1-A 手工价不被自动覆盖（force=True 才重取）',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-CPU',
          'qty': 2.0, 'unit_price': 999.0, 'tax_code_id': TAX_13,
          'price_source': 'manual'},
     ]},
    # ---- S11：W2-A 服务行
    {'order_no': 'SCN-SO-W2-SVC-1', 'customer': 'A',
     'order_type_id': ORDER_TYPE_STD, 'status': 'draft',
     'currency_id': CURRENCY_CNY,
     'description': 'W2-A 服务行：默认值只补空',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_SVC,
          'item': 'SCN-SO-ITEM-SVC-STD', 'qty': 1.0, 'unit_price': 200.0,
          'tax_code_id': TAX_6},
     ]},
    # ---- S4 / S12：已确认单（冻结 + 地址快照）
    {'order_no': 'SCN-SO-W2-CONF-1', 'customer': 'A',
     'order_type_id': ORDER_TYPE_STD, 'status': 'confirmed',
     'currency_id': CURRENCY_CNY, 'confirmed_date': ORDER_DATE,
     'head': {'payment_term_id': PAYMENT_TERM_NET30, 'incoterm_code': 'FOB',
              'salesperson': 'SCN-SO-SP-1',
              'ship_to_address_id': ADDR_SH, 'bill_to_address_id': ADDR_BJ},
     'description': 'W2-D 确认单：地址文本快照 + 确认后冻结',
     'amounts': (100.0, 13.0, 113.0),
     'pricing_status': 'determined',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_STD, 'item': 'SCN-SO-ITEM-CPU',
          'qty': 1.0, 'unit_price': 100.0, 'tax_code_id': TAX_13,
          'amounts': (100.0, 13.0, 113.0)},
     ]},
    # ---- E6 / R-RET：退货引用链
    # 原行复用上一张已确认标准单 SCN-SO-W2-CONF-1/10（CPU，qty=1.0）；
    # 草稿原单复用 SCN-SO-W0-1/10，仅供自检的「原单未确认 → 拒绝」负向断言。
    {'order_no': 'SCN-SO-W6-RET-1', 'customer': 'A',
     'order_type_id': ORDER_TYPE_RET, 'status': 'draft',
     'currency_id': CURRENCY_CNY,
     'description': 'E6 退货引用：引用 SCN-SO-W2-CONF-1/10，数量不超原行',
     'lines': [
         {'line_no': '10', 'line_type_id': LINE_RET, 'item': 'SCN-SO-ITEM-CPU',
          'qty': 1.0, 'unit_price': 100.0, 'tax_code_id': TAX_13,
          'reference': {'order_no': 'SCN-SO-W2-CONF-1', 'line_no': '10'}},
     ]},
]


# ---------------------------------------------------------------- 通用辅助

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


def ensure_schemas_registered() -> None:
    """写表前需要把 YAML schema 注册进全局 registry（table_name 白名单依赖它）。"""
    from meta.core import table_name_validator
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    register_from_directory(get_yaml_schema_dir())
    table_name_validator.invalidate_cache()


def _item_id(ds, code: str) -> Any:
    row = _one(ds, 'SELECT id FROM items WHERE code = ?', [code])
    if not row:
        raise LookupError(f'物料不存在: {code}')
    return row['id']


def _customer_id(ds, key: str) -> Any:
    row = _one(ds, 'SELECT id FROM customer_accounts WHERE name = ?',
               ['%s%s' % (CODE_PREFIX, '客户' + key)])
    if not row:
        raise LookupError(f'客户不存在: {key}')
    return row['id']


def _salesperson_id(ds, code: str) -> Any:
    row = _one(ds, 'SELECT id FROM salespersons WHERE code = ?', [code])
    if not row:
        raise LookupError(f'销售员不存在: {code}')
    return row['id']


# ---------------------------------------------------------------- 写入

def _upsert_item(ds, code: str, name: str, item_type: str, base_uom: int,
                 status: str = 'active',
                 service: Optional[Dict[str, Any]] = None) -> Any:
    data = {
        'code': code, 'name': name, 'item_type': item_type,
        'item_group_id': ITEM_GROUP_ID, 'base_uom': base_uom,
        'structure_role': 'none', 'config_match_policy': 'no',
        'config_materialize_policy': 'off', 'status': status,
    }
    if service:
        data.update(service)
    return _upsert(ds, 'items', 'SELECT id FROM items WHERE code = ?', [code], data)


def _upsert_customer_relation(ds, party_id: Any) -> Any:
    """建立 我方 → 客户 的关系行，返回 party_relations.id。

    customer_accounts.relation_id 唯一，但其他场景种子把 party_id 直接写进该列，
    与 party_relations.id 的值域重叠。SQLite 删除后按「最大 id + 1」复用编号，
    重写场景数据时新关系行可能与既有档案撞号（UNIQUE constraint failed）。
    撞号时改用显式 id 重建关系行（两侧最大值取大 + 1），保证 --reset 可重入。
    """
    existing = _one(
        ds, 'SELECT id FROM party_relations WHERE party1_id = ? AND party2_id = ? '
        "AND role = 'customer'", [INTERNAL_PARTY_ID, party_id])
    if existing:
        return existing['id']

    data = {'party1_id': INTERNAL_PARTY_ID, 'party2_id': party_id,
            'role': 'customer', 'internal_mark': 'external',
            'le_org_id': LE_ORG_ID, 'group_id': PARTY_GROUP_CUSTOMER,
            'status': 'active'}
    new_id = ds.insert('party_relations', data)
    if not _one(ds, 'SELECT id FROM customer_accounts WHERE relation_id = ?', [new_id]):
        return new_id

    # 撞到既有档案：先删掉这条路系行，再用显式 id 重建
    ds.execute('DELETE FROM party_relations WHERE id = ?', [new_id])
    max_rel = _one(ds, 'SELECT MAX(id) AS m FROM party_relations', [])['m'] or 0
    max_acc = _one(ds, 'SELECT MAX(relation_id) AS m FROM customer_accounts', [])['m'] or 0
    explicit_id = max(max_rel, max_acc) + 1
    data['id'] = explicit_id
    ds.insert('party_relations', data)
    return explicit_id


def _upsert_customer(ds, spec: Dict[str, Any]) -> Dict[str, Any]:
    party_id = _upsert(
        ds, 'parties', 'SELECT id FROM parties WHERE code = ?',
        [spec['party_code']],
        {'code': spec['party_code'], 'name': spec['name'],
         'party_type': 'organization', 'source': 'manual', 'status': 'active'})

    # 客户档案挂在 party_relation 之上（1:1）：先建关系行，再挂档案。
    relation_id = _upsert_customer_relation(ds, party_id)

    account = dict(spec['account'])
    account.update({'relation_id': relation_id, 'customer_type': 'external',
                    'name': spec['name'], 'description': 'SCN 场景数据：' + spec['note']})
    # 按名称定位：territory 种子把 relation_id 直接存成 party_id，与真实
    # party_relations 的 id 空间重叠，用 relation_id 当键会误改他人档案。
    account_id = _upsert(ds, 'customer_accounts',
                         'SELECT id FROM customer_accounts WHERE name = ?',
                         [spec['name']], account)

    # W1-B：组织段差异行（可缺省 / 可停用）
    if spec.get('org_row'):
        row = dict(spec['org_row'])
        row.update({'customer_account_id': account_id,
                    'sales_org_id': SALES_ORG_ID,
                    'description': 'SCN 场景数据'})
        _upsert(ds, 'customer_sales_orgs',
                'SELECT id FROM customer_sales_orgs '
                'WHERE customer_account_id = ? AND sales_org_id = ?',
                [account_id, SALES_ORG_ID], row)

    # W1-C：往来单位默认地址
    for role, address_id in spec.get('addresses') or []:
        _upsert(ds, 'party_addresses',
                'SELECT id FROM party_addresses WHERE party_id = ? AND role = ?',
                [party_id, role],
                {'party_id': party_id, 'address_id': address_id, 'role': role,
                 'is_default': 1, 'status': 'active',
                 'description': 'SCN 场景数据'})

    return {'party_id': party_id, 'relation_id': relation_id,
            'account_id': account_id}


def _upsert_rate_record(ds, spec: Dict[str, Any], ids: Dict[str, Any]) -> Any:
    keys = {}
    for field, value in spec['keys'].items():
        keys[field] = ids[value] if value in ids else value
    data = {
        'code': spec['code'], 'rate_table_id': RATE_TABLE_STD,
        'key_schema_id': spec['key_schema'],
        'keys': json.dumps(keys, ensure_ascii=False, sort_keys=True),
        'rate_type_id': spec['rate_type'], 'rate': spec['rate'],
        'valid_from': VALID_FROM, 'status': 'active',
        'description': 'SCN 场景数据',
    }
    return _upsert(ds, 'rate_records', 'SELECT id FROM rate_records WHERE code = ?',
                   [spec['code']], data)


def _upsert_order(ds, spec: Dict[str, Any], ids: Dict[str, Any]) -> Any:
    customer_id = ids['customer'][spec['customer']]
    amounts = spec.get('amounts') or (0.0, 0.0, 0.0)
    data = {
        'order_no': spec['order_no'],
        'order_type_id': spec['order_type_id'],
        'order_date': ORDER_DATE,
        'status': spec['status'],
        'customer_account_id': customer_id,
        'org_id': SALES_ORG_ID,
        'sales_org_id': SALES_ORG_ID,
        'currency_id': spec['currency_id'],
        'exchange_rate': spec.get('exchange_rate', 1.0),
        'price_date': spec.get('price_date'),
        'pricing_status': spec.get('pricing_status', 'pending'),
        'confirmed_date': spec.get('confirmed_date'),
        'net_amount': amounts[0], 'tax_amount': amounts[1],
        'gross_amount': amounts[2],
        'description': spec.get('description'),
    }
    head = spec.get('head') or {}
    data.update({k: v for k, v in head.items() if k != 'salesperson'})
    if head.get('salesperson'):
        data['salesperson_id'] = _salesperson_id(ds, head['salesperson'])
    return _upsert(ds, 'sales_orders', 'SELECT id FROM sales_orders WHERE order_no = ?',
                   [spec['order_no']], data)


def _upsert_order_line(ds, order_id: Any, line: Dict[str, Any]) -> Any:
    amounts = line.get('amounts')
    data = {
        'order_id': order_id,
        'line_no': line['line_no'],
        'line_type_id': line['line_type_id'],
        'item_id': _item_id(ds, line['item']),
        'qty': line['qty'],
        'uom_id': line.get('uom_id', UOM_FEA),
        'unit_price': line.get('unit_price'),
        'tax_code_id': line.get('tax_code_id'),
        'price_source': line.get('price_source'),
        'status': 'open',
        'pricing_mode': 'standalone',
    }
    if amounts:
        data.update({'net_amount': amounts[0], 'tax_base_amount': amounts[0],
                     'tax_amount': amounts[1], 'gross_amount': amounts[2]})
    # E6：仅当行 spec 显式给出引用时才写 reference_line_id，
    # 避免给普通行写 None 而重置既有引用。
    if 'reference_line_id' in line:
        data['reference_line_id'] = line['reference_line_id']
    return _upsert(ds, 'sales_order_lines',
                   'SELECT id FROM sales_order_lines WHERE order_id = ? AND line_no = ?',
                   [order_id, line['line_no']], data)


def seed_sales_order_scenario_data(ds) -> Dict[str, Any]:
    """写入全部 SCN-SO- 场景数据；返回引用映射。"""
    ensure_schemas_registered()

    items: Dict[str, Any] = {}
    for code, name, item_type, base_uom in _BASE_ITEMS:
        items[code] = _upsert_item(ds, code, name, item_type, base_uom)
    for spec in _OWN_ITEMS:
        items[spec['code']] = _upsert_item(
            ds, spec['code'], spec['name'], spec['item_type'],
            spec['base_uom'], spec['status'], spec.get('service'))

    customers = {spec['key']: _upsert_customer(ds, spec) for spec in _CUSTOMERS}
    ids: Dict[str, Any] = {'customer': {
        key: value['account_id'] for key, value in customers.items()}}
    ids.update({
        'SCN-SO-ITEM-CPU': items['SCN-SO-ITEM-CPU'],
        'SCN-SO-ITEM-BIKE': items['SCN-SO-ITEM-BIKE'],
        'SCN-SO-ITEM-NUT': items['SCN-SO-ITEM-NUT'],
        'SCN-SO-ITEM-SVC-NODEF': items['SCN-SO-ITEM-SVC-NODEF'],
        'SCN-SO-ITEM-SVC-STD': items['SCN-SO-ITEM-SVC-STD'],
        'SCN-SO-ITEM-SVC-OFF': items['SCN-SO-ITEM-SVC-OFF'],
        'SCN-SO-ITEM-NEG': items['SCN-SO-ITEM-NEG'],
        'A': customers['A']['account_id'],
        'B': customers['B']['account_id'],
        'C': customers['C']['account_id'],
        'D': customers['D']['account_id'],
    })

    people: Dict[str, Any] = {}
    for code, name, status in _SALESPEOPLE:
        people[code] = _upsert(
            ds, 'salespersons', 'SELECT id FROM salespersons WHERE code = ?', [code],
            {'code': code, 'name': name, 'status': status,
             'description': 'SCN 场景数据'})

    for key, org_id, sp_code, is_primary, status in _ASSIGNMENTS:
        _upsert(
            ds, 'customer_salesperson_assignments',
            'SELECT id FROM customer_salesperson_assignments '
            'WHERE customer_account_id = ? AND salesperson_id = ? '
            'AND (sales_org_id = ? OR (sales_org_id IS NULL AND ? IS NULL))',
            [customers[key]['account_id'], people[sp_code], org_id, org_id],
            {'customer_account_id': customers[key]['account_id'],
             'sales_org_id': org_id, 'salesperson_id': people[sp_code],
             'is_primary': is_primary, 'status': status})

    rates: Dict[str, Any] = {}
    for spec in _RATE_RECORDS:
        rates[spec['code']] = _upsert_rate_record(ds, spec, ids)

    orders: Dict[str, Any] = {}
    for spec in _ORDERS:
        order_id = _upsert_order(ds, spec, ids)
        orders[spec['order_no']] = order_id
        for line in spec['lines']:
            reference = line.get('reference')
            if reference:
                # E6：按业务键（订单号 + 行号）解析原行主键，被引用订单须先写入
                ref_order_id = orders.get(reference['order_no'])
                if ref_order_id is None:
                    raise LookupError(
                        '被引用订单需先写入: %s' % reference['order_no'])
                ref_row = _one(ds, 'SELECT id FROM sales_order_lines '
                                   'WHERE order_id = ? AND line_no = ?',
                               [ref_order_id, reference['line_no']])
                if not ref_row:
                    raise LookupError('被引用行不存在: %s / %s'
                                      % (reference['order_no'],
                                         reference['line_no']))
                line = dict(line, reference_line_id=ref_row['id'])
            _upsert_order_line(ds, order_id, line)

    ds.commit()
    return {'items': items, 'customers': customers, 'salespeople': people,
            'rates': rates, 'orders': orders}


_CLEANUP_SQL = [
    ('calc_details',
     "DELETE FROM calc_details WHERE result_id IN ("
     "SELECT id FROM calc_results WHERE document_type = 'sales_order' "
     "AND document_id IN (SELECT id FROM sales_orders WHERE order_no LIKE 'SCN-SO-W%'))"),
    ('calc_results',
     "DELETE FROM calc_results WHERE document_type = 'sales_order' "
     "AND document_id IN (SELECT id FROM sales_orders WHERE order_no LIKE 'SCN-SO-W%')"),
    ('sales_order_lines',
     "DELETE FROM sales_order_lines WHERE order_id IN ("
     "SELECT id FROM sales_orders WHERE order_no LIKE 'SCN-SO-W%')"),
    ('sales_orders', "DELETE FROM sales_orders WHERE order_no LIKE 'SCN-SO-W%'"),
    ('rate_records', "DELETE FROM rate_records WHERE code LIKE 'SCN-SO-%'"),
    ('customer_salesperson_assignments',
     "DELETE FROM customer_salesperson_assignments WHERE customer_account_id IN ("
     "SELECT id FROM customer_accounts WHERE name LIKE 'SCN-SO-%')"),
    ('salespersons', "DELETE FROM salespersons WHERE code LIKE 'SCN-SO-%'"),
    ('customer_sales_orgs',
     "DELETE FROM customer_sales_orgs WHERE customer_account_id IN ("
     "SELECT id FROM customer_accounts WHERE name LIKE 'SCN-SO-%')"),
    ('party_addresses',
     "DELETE FROM party_addresses WHERE party_id IN ("
     "SELECT id FROM parties WHERE code LIKE 'SCN-SO-%')"),
    ('customer_accounts',
     "DELETE FROM customer_accounts WHERE name LIKE 'SCN-SO-%'"),
    ('party_relations',
     "DELETE FROM party_relations WHERE party2_id IN "
     "(SELECT id FROM parties WHERE code LIKE 'SCN-SO-%')"),
    ('parties', "DELETE FROM parties WHERE code LIKE 'SCN-SO-%'"),
    ('items', "DELETE FROM items WHERE code LIKE 'SCN-SO-%'"),
]


def cleanup_sales_order_scenario_data(ds) -> Dict[str, int]:
    """只清理 SCN-SO- 前缀范围内的数据；子表先删。"""
    ensure_schemas_registered()
    counts: Dict[str, int] = {}
    for table, sql in _CLEANUP_SQL:
        result = ds.execute(sql)
        rowcount = getattr(result, 'rowcount', None)
        counts[table] = -1 if rowcount is None or rowcount < 0 else rowcount
    ds.commit()
    return counts


def reset_sales_order_scenario_data(ds) -> Dict[str, Any]:
    cleanup_sales_order_scenario_data(ds)
    return seed_sales_order_scenario_data(ds)


# ---------------------------------------------------------------- 自检

def _round2(value: Any) -> float:
    return round(float(value), 2)


def _run_checks(ds) -> List[Tuple[str, bool, str]]:
    """返回 [(检查项, passed, detail)]；全部基于真实库当前数据。"""
    from meta.services.customer_sales_org_service import CustomerSalesOrgService
    from meta.services.party_address_service import PartyAddressService
    from meta.services.pricing_determination_service import (
        PricingDeterminationService,
    )
    from meta.services.sales_order_amount_service import SalesOrderAmountService
    from meta.services.sales_order_guard_service import (
        SalesOrderGuardError, SalesOrderGuardService,
    )
    from meta.services.sales_order_pricing_service import SalesOrderPricingService
    from meta.services.salesperson_service import SalespersonService

    ensure_schemas_registered()
    checks: List[Tuple[str, bool, str]] = []

    def check(name: str, fn: Callable[[], str]) -> None:
        try:
            checks.append((name, True, fn()))
        except AssertionError as e:
            checks.append((name, False, str(e)))
        except Exception as e:  # 非断言异常同样记失败，避免自检中断
            checks.append((name, False, '%s: %s' % (type(e).__name__, e)))

    guard = SalesOrderGuardService(ds)
    amount = SalesOrderAmountService(ds)
    pricing = SalesOrderPricingService(ds)
    det = PricingDeterminationService(ds)
    cso = CustomerSalesOrgService(ds)
    addr = PartyAddressService(ds)
    salesperson = SalespersonService(ds)

    def order_id(order_no: str) -> Any:
        row = _one(ds, 'SELECT id FROM sales_orders WHERE order_no = ?', [order_no])
        assert row, '订单不存在: %s' % order_no
        return row['id']

    def line_id(order_no: str, line_no: str) -> Any:
        row = _one(ds, 'SELECT id FROM sales_order_lines WHERE order_id = ? '
                       'AND line_no = ?', [order_id(order_no), line_no])
        assert row, '订单行不存在: %s / %s' % (order_no, line_no)
        return row['id']

    def line_row(order_no: str, line_no: str) -> Dict[str, Any]:
        row = _one(ds, 'SELECT * FROM sales_order_lines WHERE order_id = ? '
                       'AND line_no = ?', [order_id(order_no), line_no])
        assert row, '订单行不存在: %s / %s' % (order_no, line_no)
        return row

    def cust(key: str) -> Any:
        return _customer_id(ds, key)

    # ---------------- W0：金额与汇总 ----------------
    def w0_line_amounts() -> str:
        got = []
        for line_no in ('10', '20', '30'):
            values = amount.recompute_line(line_id('SCN-SO-W0-1', line_no))
            got.append((_round2(values['net_amount']),
                        _round2(values['tax_amount']),
                        _round2(values['gross_amount'])))
        expect = [(300.0, 39.0, 339.0), (25.0, 3.25, 28.25), (13.34, 1.73, 15.07)]
        assert got == expect, '行金额 %s != %s' % (got, expect)
        return '3 行金额 / 税额 / 含税额全部符合行级舍入口径'

    def w0_order_total() -> str:
        head = amount.recompute_order(order_id('SCN-SO-W0-1'))
        lines = ds.query(
            'SELECT net_amount, tax_amount, gross_amount FROM sales_order_lines '
            'WHERE order_id = ?', [order_id('SCN-SO-W0-1')])
        net = _round2(sum(float(r['net_amount'] or 0) for r in lines))
        tax = _round2(sum(float(r['tax_amount'] or 0) for r in lines))
        gross = _round2(sum(float(r['gross_amount'] or 0) for r in lines))
        assert (_round2(head['net_amount']), _round2(head['tax_amount']),
                _round2(head['gross_amount'])) == (net, tax, gross), '抬头 ≠ 行合计'
        assert (net, tax, gross) == (338.34, 43.98, 382.32), '%s' % ((net, tax, gross),)
        return '抬头 = 行合计 338.34 / 43.98 / 382.32（R7）'

    def w0_return_sign() -> str:
        values = amount.recompute_line(line_id('SCN-SO-W0-RET-1', '10'))
        got = (_round2(values['net_amount']), _round2(values['tax_amount']),
               _round2(values['gross_amount']))
        assert got == (-100.0, -13.0, -113.0), '%s' % (got,)
        return '退货单整行金额取负（R3）'

    # ---------------- W0：守卫 ----------------
    def w0_qty_guard() -> str:
        try:
            guard.validate_line_write({'order_id': order_id('SCN-SO-W0-1'),
                                       'line_type_id': LINE_STD, 'qty': 0,
                                       'uom_id': UOM_FEA})
        except SalesOrderGuardError as e:
            assert e.rule == 'qty_not_positive', e.rule
            return 'qty=0 被拒（R2）'
        raise AssertionError('qty=0 未拒绝')

    def w0_uom_guard() -> str:
        try:
            guard.validate_line_write({'order_id': order_id('SCN-SO-W0-1'),
                                       'line_type_id': LINE_STD, 'qty': 1})
        except SalesOrderGuardError as e:
            assert e.rule == 'uom_required', e.rule
            return '缺计量单位被拒（R6）'
        raise AssertionError('缺单位未拒绝')

    def w0_description_guard() -> str:
        try:
            guard.validate_line_write({'order_id': order_id('SCN-SO-W0-1'),
                                       'line_type_id': LINE_STD, 'qty': 1,
                                       'uom_id': UOM_FEA})
        except SalesOrderGuardError as e:
            assert e.rule == 'description_required', e.rule
            return '无物料且无描述被拒（R6）'
        raise AssertionError('无物料且无描述未拒绝')

    def w0_line_type_scope() -> str:
        try:
            guard.validate_line_write({'order_id': order_id('SCN-SO-W0-1'),
                                       'line_type_id': ORDER_TYPE_STD, 'qty': 1,
                                       'uom_id': UOM_FEA, 'description': 'x'})
        except SalesOrderGuardError as e:
            assert e.rule == 'line_type_scope', e.rule
            return '抬头类型当行类型被拒（R4）'
        raise AssertionError('行类型越界未拒绝')

    def w0_sales_org_guard() -> str:
        try:
            guard.validate_order_write({'sales_org_id': 1},
                                       old_data={'status': 'draft',
                                                 'sales_org_id': 1})
        except SalesOrderGuardError as e:
            assert e.rule == 'sales_org_not_sales', e.rule
            return '无 sales 职能的组织被拒（R10）'
        raise AssertionError('无销售职能组织未拒绝')

    def w0_frozen_fields() -> str:
        old = {'status': 'confirmed', 'currency_id': CURRENCY_CNY,
               'exchange_rate': 1.0, 'order_no': 'SCN-SO-W2-CONF-1'}
        try:
            guard.validate_order_write({'currency_id': CURRENCY_USD}, old_data=old)
        except SalesOrderGuardError as e:
            assert e.rule == 'field_frozen_after_draft', e.rule
        else:
            raise AssertionError('确认后改币种未拒绝')
        try:
            guard.validate_order_write({'exchange_rate': 2.0}, old_data=old)
        except SalesOrderGuardError as e2:
            assert e2.rule == 'exchange_rate_frozen', e2.rule
            return '确认后禁改币种（R8）与汇率（R9）'
        raise AssertionError('确认后改汇率未拒绝')

    def w0_line_frozen() -> str:
        try:
            guard.validate_line_delete(line_id('SCN-SO-W2-CONF-1', '10'))
        except SalesOrderGuardError as e:
            assert e.rule == 'line_delete_parent_not_draft', e.rule
            return '已确认单禁删行（R8）'
        raise AssertionError('已确认单删除行未拒绝')

    # ---------------- W1-A / W2-C / W2-F：定价 ----------------
    def w1_customer_price() -> str:
        result = pricing.price_line(line_id('SCN-SO-W1-PRICE-1', '10'))
        assert result and result['pricing_status'] == 'determined', result
        assert _round2(result['unit_price']) == 74.16, result['unit_price']
        trace = result['price_trace']
        assert trace.get('rate_table_code') == 'PL_STD', trace
        assert _round2(trace.get('discount_amount')) == 40.0, trace
        assert _round2(trace.get('surcharge_amount')) == 10.8, trace
        return '客户价 80 优先（覆盖物料价 100）→ 10% 折扣 + 3% 附加费 → 74.16'

    def w1_item_fallback() -> str:
        result = pricing.price_line(line_id('SCN-SO-W1-CUSTB-1', '10'))
        assert result and result['pricing_status'] == 'determined', result
        assert _round2(result['unit_price']) == 92.7, result['unit_price']
        return '客户无客户价 → 落物料次槽 100 → 92.7（W2-F 多槽位）'

    def w1_no_candidate() -> str:
        result = pricing.price_line(line_id('SCN-SO-W1-NOCAND-1', '10'))
        assert result and result['pricing_status'] == 'failed', result
        assert result['reason'] == 'NO_CANDIDATE', result['reason']
        row = line_row('SCN-SO-W1-NOCAND-1', '10')
        assert row['unit_price'] is None, row['unit_price']
        return '无价目行 → NO_CANDIDATE，行仍保留（失败不阻保存）'

    def w1_currency_mismatch() -> str:
        result = pricing.price_line(line_id('SCN-SO-W1-CCY-1', '10'))
        assert result and result['pricing_status'] == 'failed', result
        assert result['reason'] == 'CURRENCY_MISMATCH', result['reason']
        return '订单币种 USD ≠ 价目表 CNY → CURRENCY_MISMATCH'

    def w1_manual_protected() -> str:
        lid = line_id('SCN-SO-W1-MANUAL-1', '10')
        assert pricing.price_line(lid) is None, '手工价行不应被自动取价'
        assert _round2(line_row('SCN-SO-W1-MANUAL-1', '10')['unit_price']) == 999.0
        forced = pricing.price_line(lid, force=True)
        assert forced and forced['pricing_status'] == 'determined', forced
        assert _round2(forced['unit_price']) == 74.16, forced['unit_price']
        ds.execute('UPDATE sales_order_lines SET unit_price = 999.0, '
                   "price_source = 'manual', price_trace = NULL WHERE id = ?", [lid])
        ds.commit()
        return 'manual 不覆盖；force=True 重取为 74.16（已还原手工价）'

    def w1_negative_amount() -> str:
        result = det.determine_line(
            item_id=_item_id(ds, 'SCN-SO-ITEM-NEG'), qty=1, price_date=ORDER_DATE,
            currency='CNY', sales_org_id=SALES_ORG_ID,
            order_type_id=ORDER_TYPE_STD)
        assert result['pricing_status'] == 'failed', result
        assert result['reason'] == 'NEGATIVE_AMOUNT', result['reason']
        return '折扣 150% → 净额转负即失败（R-DSC-1）'

    def w1_zero_qty() -> str:
        result = det.determine_line(item_id=_item_id(ds, 'SCN-SO-ITEM-CPU'), qty=0,
                                    price_date=ORDER_DATE, currency='CNY',
                                    sales_org_id=SALES_ORG_ID,
                                    order_type_id=ORDER_TYPE_STD)
        assert result['reason'] == 'ZERO_QTY', result['reason']
        return 'qty=0 → ZERO_QTY'

    # ---------------- W1-B：组织段覆盖 ----------------
    def w1b_org_override() -> str:
        got = cso.resolve(cust('A'), SALES_ORG_ID)
        assert got == {'payment_term_id': PAYMENT_TERM_NET30,
                       'incoterm_code': 'FOB', 'currency_id': CURRENCY_USD}, got
        return '组织行覆盖账期 / 贸易条款 / 币种'

    def w1b_account_fallback() -> str:
        got = cso.resolve(cust('B'), SALES_ORG_ID)
        assert got == {'payment_term_id': PAYMENT_TERM_NET30,
                       'incoterm_code': 'DAP'}, got
        return '无组织行 → 逐字段回退账户级'

    def w1b_inactive_row_ignored() -> str:
        got = cso.resolve(cust('C'), SALES_ORG_ID)
        assert got == {'payment_term_id': PAYMENT_TERM_NET30,
                       'incoterm_code': 'EXW'}, got
        return '停用组织行不参与覆盖（仍取账户级 EXW）'

    # ---------------- W1-C：地址带出 ----------------
    def w1c_address_default() -> str:
        got = addr.resolve({'customer_account_id': cust('A')})
        assert got == {'ship_to_address_id': ADDR_SH,
                       'bill_to_address_id': ADDR_BJ}, got
        return '收货 / 收票默认地址均带出'

    def w1c_partial() -> str:
        got = addr.resolve({'customer_account_id': cust('B')})
        assert got.get('ship_to_address_id') == ADDR_NJ, got
        assert got.get('bill_to_address_id') is None, got
        empty = addr.resolve({'customer_account_id': cust('D')})
        assert empty == {'ship_to_address_id': None,
                         'bill_to_address_id': None}, empty
        return '缺收票地址留空、无地址客户全留空（fail-open）'

    # ---------------- W1-D：销售员 ----------------
    def w1d_salesperson() -> str:
        sp1 = _salesperson_id(ds, 'SCN-SO-SP-1')
        sp2 = _salesperson_id(ds, 'SCN-SO-SP-2')
        got_a = salesperson.resolve(cust('A'), SALES_ORG_ID, ORDER_DATE)
        got_b = salesperson.resolve(cust('B'), SALES_ORG_ID, ORDER_DATE)
        assert got_a == sp1, got_a
        assert got_b == sp2, got_b
        return '通用主销售员带出；组织专属优先于通用'

    def w1d_inactive_and_non_primary() -> str:
        assert salesperson.resolve(cust('C'), SALES_ORG_ID, ORDER_DATE) is None
        assert salesperson.resolve(cust('D'), SALES_ORG_ID, ORDER_DATE) is None
        return '停用销售员 / 非主销售员均不带出'

    # ---------------- W2-A：服务行 ----------------
    def w2a_defaults_only_blank() -> str:
        svc = _item_id(ds, 'SCN-SO-ITEM-SVC-STD')
        got = guard.service_line_defaults({'item_id': svc})
        assert got == {'uom_id': UOM_FEA,
                       'billing_method': 'fixed_price',
                       'required_resource_type': 'technician',
                       'service_duration': 2.0, 'duration_type': 'day'}, got
        partial = guard.service_line_defaults(
            {'item_id': svc, 'billing_method': 'milestone'})
        assert 'billing_method' not in partial, partial
        assert partial.get('required_resource_type') == 'technician', partial
        empty = guard.service_line_defaults(
            {'item_id': _item_id(ds, 'SCN-SO-ITEM-SVC-NODEF')})
        assert empty == {'uom_id': UOM_FEA}, empty
        return '默认单位 + 4 项服务默认值只补空；已填不覆盖；无服务默认物料仅补单位'

    def w2a_guard_rules() -> str:
        base = {'order_id': order_id('SCN-SO-W2-SVC-1'),
                'line_type_id': LINE_SVC, 'qty': 1, 'uom_id': UOM_FEA}
        cases = [
            ('service_field_non_service_item',
             dict(base, item_id=_item_id(ds, 'SCN-SO-ITEM-CPU'),
                  billing_method='fixed_price')),
            ('service_item_not_sellable',
             dict(base, item_id=_item_id(ds, 'SCN-SO-ITEM-SVC-OFF'))),
            ('service_date_range',
             dict(base, item_id=_item_id(ds, 'SCN-SO-ITEM-SVC-STD'),
                  service_start_date='2026-11-02', service_end_date='2026-11-01')),
            ('duration_type_required',
             dict(base, item_id=_item_id(ds, 'SCN-SO-ITEM-SVC-STD'),
                  service_duration=3)),
            ('service_enum_invalid',
             dict(base, item_id=_item_id(ds, 'SCN-SO-ITEM-SVC-STD'),
                  billing_method='monthly')),
            ('service_line_no_location',
             dict(base, item_id=_item_id(ds, 'SCN-SO-ITEM-SVC-STD'),
                  plant_location_id=3)),
        ]
        hit = []
        for rule, data in cases:
            try:
                guard.validate_line_write(data)
            except SalesOrderGuardError as e:
                assert e.rule == rule, '%s != %s' % (e.rule, rule)
                hit.append(rule)
            else:
                raise AssertionError('%s 未拒绝' % rule)
        return '6 条反例全部命中：' + ' / '.join(hit)

    # ---------------- W2-D：地址文本快照 ----------------
    def w2d_snapshot() -> str:
        snapshot = guard.snapshot_address_text(
            {'status': 'confirmed', 'ship_to_address_id': ADDR_SH,
             'bill_to_address_id': ADDR_BJ}, {'status': 'draft'})
        expect = {r['id']: r['formatted_address'] for r in ds.query(
            'SELECT id, formatted_address FROM addresses WHERE id IN (?, ?)',
            [ADDR_SH, ADDR_BJ])}
        assert snapshot.get('ship_to_address_text') == expect[ADDR_SH], snapshot
        assert snapshot.get('bill_to_address_text') == expect[ADDR_BJ], snapshot
        assert guard.snapshot_address_text(
            {'status': 'confirmed', 'ship_to_address_id': ADDR_SH},
            {'status': 'confirmed'}) == {}
        return '确认时按 address.formatted_address 原样回填（R-ADR-3）'

    def w2d_locked() -> str:
        try:
            guard.validate_order_write(
                {'ship_to_address_text': '改写'},
                old_data={'status': 'confirmed', 'ship_to_address_text': '原值'})
        except SalesOrderGuardError as e:
            assert e.rule == 'address_snapshot_locked', e.rule
        else:
            raise AssertionError('离草稿改快照未拒绝')
        try:
            guard.validate_order_write(
                {'status': 'confirmed', 'ship_to_address_text': None},
                old_data={'status': 'submitted', 'ship_to_address_text': '原值'})
        except SalesOrderGuardError as e2:
            assert e2.rule == 'address_snapshot_locked', e2.rule
            return '离草稿只读（R-ADR-1）+ 确认时不得清空（R-ADR-2）'
        raise AssertionError('确认清空快照未拒绝')

    def w2d_confirm_fill_allowed() -> str:
        guard.validate_order_write(
            {'status': 'confirmed', 'ship_to_address_text': '中国上海市…'},
            old_data={'status': 'submitted', 'ship_to_address_text': None})
        return '确认动作同请求内允许系统回填（R-ADR-1 例外）'

    # ---------------- E6：退货引用链 ----------------
    def e6_return_reference() -> str:
        ret_no, ret_line_no = 'SCN-SO-W6-RET-1', '10'
        draft_no, draft_line_no = 'SCN-SO-W0-1', '10'
        row = _one(
            ds,
            'SELECT rl.order_id AS ret_order_id, '
            '       rl.reference_line_id, rl.item_id AS ret_item_id, '
            '       ro.customer_account_id AS ret_customer_id, '
            '       rot.document_category AS ret_doc_category, '
            '       rlt.line_category AS ret_line_category, '
            '       ref.id AS ref_line_id, ref.order_id AS ref_order_id, '
            '       ref.line_no AS ref_line_no, ref.item_id AS ref_item_id, '
            '       ref.qty AS ref_qty, '
            '       reflt.line_category AS ref_line_category, '
            '       refo.order_no AS ref_order_no, '
            '       refo.status AS ref_order_status, '
            '       refo.customer_account_id AS ref_customer_id, '
            '       refot.document_category AS ref_doc_category '
            'FROM sales_order_lines rl '
            'JOIN sales_orders ro ON ro.id = rl.order_id '
            'JOIN type_definitions rot ON rot.id = ro.order_type_id '
            'JOIN type_definitions rlt ON rlt.id = rl.line_type_id '
            'LEFT JOIN sales_order_lines ref ON ref.id = rl.reference_line_id '
            'LEFT JOIN sales_orders refo ON refo.id = ref.order_id '
            'LEFT JOIN type_definitions reflt ON reflt.id = ref.line_type_id '
            'LEFT JOIN type_definitions refot ON refot.id = refo.order_type_id '
            'WHERE ro.order_no = ? AND rl.line_no = ?',
            [ret_no, ret_line_no])
        assert row, '退货行不存在: %s / %s' % (ret_no, ret_line_no)
        assert row['ret_doc_category'] == 'return', \
            '退货单类型类别不是 return: %s' % row['ret_doc_category']
        assert row['ret_line_category'] == 'return', \
            '退货行类型类别不是 return: %s' % row['ret_line_category']
        # R-RET-1/2：引用非空且原行存在
        assert row['reference_line_id'] is not None, '退货行 reference_line_id 为空'
        assert row['ref_line_id'] is not None, \
            '引用的原行不存在: id=%s' % row['reference_line_id']
        # R-RET-3/4：不同单，且原行 / 原单都不是退货
        assert str(row['ref_order_id']) != str(row['ret_order_id']), '引用了本单行'
        assert row['ref_line_category'] != 'return', '原行是退货行'
        assert row['ref_doc_category'] != 'return', '原单是退货单'
        # R-RET-5：原单须 confirmed / closed
        assert row['ref_order_status'] in ('confirmed', 'closed'), \
            '原单 %s 状态为 %s，不可开退货' % (row['ref_order_no'],
                                              row['ref_order_status'])
        # R-RET-6/7：客户与物料一致
        assert str(row['ret_customer_id']) == str(row['ref_customer_id']), \
            '退货单客户 %s != 原单客户 %s' % (row['ret_customer_id'],
                                            row['ref_customer_id'])
        assert str(row['ret_item_id']) == str(row['ref_item_id']), \
            '退货行物料 %s != 原行物料 %s' % (row['ret_item_id'],
                                            row['ref_item_id'])
        # R-RET-8：累计未取消退货量（含本行）不得超过原行 qty
        total = _one(
            ds,
            'SELECT COALESCE(SUM(rl.qty), 0) AS qty FROM sales_order_lines rl '
            'JOIN sales_orders ro ON ro.id = rl.order_id '
            'WHERE rl.reference_line_id = ? AND rl.status <> ? '
            'AND ro.status <> ?',
            [row['ref_line_id'], 'cancelled', 'cancelled'])['qty']
        assert float(total) <= float(row['ref_qty']) + 1e-9, \
            '累计退货量 %s > 原行数量 %s' % (total, row['ref_qty'])

        # R-RET-5 负向：退货行引用草稿原单行须被拒（不写入数据）
        try:
            guard.validate_line_write(
                {'order_id': order_id(ret_no), 'line_type_id': LINE_RET,
                 'item_id': _item_id(ds, 'SCN-SO-ITEM-CPU'), 'qty': 1.0,
                 'uom_id': UOM_FEA, 'tax_code_id': TAX_13,
                 'reference_line_id': line_id(draft_no, draft_line_no)},
                is_create=True)
        except SalesOrderGuardError as e:
            assert e.rule == 'return_ref_order_not_confirmed', e.rule
        else:
            raise AssertionError('引用草稿原单行未被拒绝')

        return ('退货 %s/%s 引用 %s/%s 通过 R-RET-1~8（累计 %s ≤ 原行 %s）；'
                '引用草稿单行被拒（return_ref_order_not_confirmed）'
                % (ret_no, ret_line_no, row['ref_order_no'], row['ref_line_no'],
                   total, row['ref_qty']))

    # ---------------- 汇总 ----------------
    check('W0-1 行金额 / 税额（R11）', w0_line_amounts)
    check('W0-2 抬头 = 行合计（R7）', w0_order_total)
    check('W0-3 退货整行取负（R3）', w0_return_sign)
    check('W0-4 qty>0（R2）', w0_qty_guard)
    check('W0-5 单位必填（R6）', w0_uom_guard)
    check('W0-6 无物料须描述（R6）', w0_description_guard)
    check('W0-7 行类型作用域（R4）', w0_line_type_scope)
    check('W0-8 销售组织职能（R10）', w0_sales_org_guard)
    check('W0-9 确认后冻结（R8 / R9）', w0_frozen_fields)
    check('W0-10 已确认禁删行（R8）', w0_line_frozen)
    check('W1-A 客户价优先 + 折扣/附加费', w1_customer_price)
    check('W1-A 物料价兜底（W2-F）', w1_item_fallback)
    check('W1-A 无候选降级', w1_no_candidate)
    check('W1-A 币种不符降级', w1_currency_mismatch)
    check('W1-A 手工价保护', w1_manual_protected)
    check('W2-C 折扣过深失败（R-DSC-1）', w1_negative_amount)
    check('W1-A qty=0 不取价', w1_zero_qty)
    check('W1-B 组织段覆盖', w1b_org_override)
    check('W1-B 账户级回退', w1b_account_fallback)
    check('W1-B 停用组织行忽略', w1b_inactive_row_ignored)
    check('W1-C 收货/收票地址带出', w1c_address_default)
    check('W1-C 缺地址留空', w1c_partial)
    check('W1-D 主销售员带出', w1d_salesperson)
    check('W1-D 停用/非主不带出', w1d_inactive_and_non_primary)
    check('W2-A 默认值只补空', w2a_defaults_only_blank)
    check('W2-A 守卫反例 6 条', w2a_guard_rules)
    check('W2-D 快照回填（R-ADR-3）', w2d_snapshot)
    check('W2-D 离草稿冻结（R-ADR-1/2）', w2d_locked)
    check('W2-D 确认回填例外', w2d_confirm_fill_allowed)
    check('E6 退货引用链（R-RET-1~8）', e6_return_reference)
    return checks


def verify_sales_order_scenario(ds) -> int:
    checks = _run_checks(ds)
    width = max(len(name) for name, _, _ in checks)
    for name, passed, detail in checks:
        print('%s %s  %s' % ('[PASS]' if passed else '[FAIL]',
                            name.ljust(width), detail))
    failed = [c for c in checks if not c[1]]
    print('\n合计 %d 项：通过 %d，失败 %d'
          % (len(checks), len(checks) - len(failed), len(failed)))
    return 1 if failed else 0


# ---------------------------------------------------------------- 入口

def _main(argv: List[str]) -> int:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    from meta.core.datasource import get_data_source  # noqa: E402
    from meta.tests.test_utils import get_meta_db_path  # noqa: E402

    ds = get_data_source('sqlite', database=str(get_meta_db_path()))
    action = argv[1] if len(argv) > 1 else ''

    if action == '--cleanup':
        print('[cleanup]', cleanup_sales_order_scenario_data(ds))
        return 0
    if action == '--reset':
        seed = reset_sales_order_scenario_data(ds)
        print('[reset] customers=%d orders=%d rates=%d'
              % (len(seed['customers']), len(seed['orders']), len(seed['rates'])))
        return 0
    if action == '--verify':
        return verify_sales_order_scenario(ds)

    seed = seed_sales_order_scenario_data(ds)
    print('[seed] customers=%d salespeople=%d orders=%d rates=%d'
          % (len(seed['customers']), len(seed['salespeople']),
             len(seed['orders']), len(seed['rates'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))
