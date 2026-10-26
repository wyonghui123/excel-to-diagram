# -*- coding: utf-8 -*-
"""销售区域域场景种子数据（SCN- 前缀）

用途
----
为销售区域 M1~M4 四条已完成波次准备按场景划分的可重复数据，并提供真实库
`--verify` 自检（引擎 / 守卫 / 数据库约束 / 菜单形态）。

场景清单
--------
S1 区域树与层级派生      SCN-TER-CN → SCN-TER-CN-EAST → SH / JS；NORTH 为兄弟
S2 区域类型              geographic 与 industry 各一，验证 M1 的 territory_type
S3 停用区域              SCN-TER-OFF（status=inactive），验证 R-TER-6
S4 客户主 / 次区域分配   SCN-CA-A：主区域 SH + 次区域 JS（priority=2）
                         SCN-CA-B：主区域 EAST（父区域）
                         SCN-CA-A：一条已过期分配 → NORTH（应被带出逻辑忽略）
S5 无分配客户            SCN-CA-C，验证带出 fail-open（留空不阻断）
S6 订单区域快照          draft×3（SH / JS / NORTH）+ 无区域×1 + confirmed×1
S7 数据范围角色          SCN-PS-TERRITORY，territory=[EAST]，inherit_children=1
S8 守卫反例              成环 / 自引用 / 停用区域分配 / 有效期倒置 / 第二主区域

约定
----
· 业务编码统一 ``SCN-`` 前缀，``--cleanup`` 只删该前缀范围内的数据。
· 幂等：按业务键 SELECT 后 UPDATE / INSERT，可重复执行。
· 直接写表、不经过 BO 层与守卫拦截，因此数据自身必须满足 R-TER-1~8 口径。
· 订单只写抬头（区域场景不消费行），金额固定 100 便于人工核对。

用法
----
    python -m meta.scripts.init_territory_scenario_seed            # 写入（幂等）
    python -m meta.scripts.init_territory_scenario_seed --verify   # 自检
    python -m meta.scripts.init_territory_scenario_seed --cleanup  # 仅清理
    python -m meta.scripts.init_territory_scenario_seed --reset    # 清理后重写
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

SCN = 'SCN-'

PS_CODE = 'SCN-PS-TERRITORY'
PS_NAME = '场景-华东区域角色'

# (code, name, parent_code, territory_type, status)
_TERRITORIES: List[tuple] = [
    ('SCN-TER-CN', '场景-中国区', None, 'geographic', 'active'),
    ('SCN-TER-CN-EAST', '场景-华东', 'SCN-TER-CN', 'geographic', 'active'),
    ('SCN-TER-CN-EAST-SH', '场景-上海', 'SCN-TER-CN-EAST', 'geographic', 'active'),
    ('SCN-TER-CN-EAST-JS', '场景-江苏', 'SCN-TER-CN-EAST', 'geographic', 'active'),
    ('SCN-TER-CN-NORTH', '场景-华北', 'SCN-TER-CN', 'geographic', 'active'),
    ('SCN-TER-IND', '场景-制造业', None, 'industry', 'active'),
    ('SCN-TER-OFF', '场景-停用区域', None, 'geographic', 'inactive'),
]

# (party_code, party_name, customer_name)
_CUSTOMERS: List[tuple] = [
    ('SCN-PTY-A', '场景客户A', '场景客户A'),
    ('SCN-PTY-B', '场景客户B', '场景客户B'),
    ('SCN-PTY-C', '场景客户C', '场景客户C'),
]

# (customer_name, territory_code, is_primary, priority, effective_from, effective_to)
_ASSIGNMENTS: List[tuple] = [
    ('场景客户A', 'SCN-TER-CN-EAST-SH', 1, None, '2026-01-01', None),
    ('场景客户A', 'SCN-TER-CN-EAST-JS', 0, 2, '2026-01-01', None),
    ('场景客户A', 'SCN-TER-CN-NORTH', 0, 1, '2025-01-01', '2025-12-31'),
    ('场景客户B', 'SCN-TER-CN-EAST', 1, None, '2026-01-01', None),
]

# (order_no, customer_name, territory_code, status)
_ORDERS: List[tuple] = [
    ('SCN-SO-SH-1', '场景客户A', 'SCN-TER-CN-EAST-SH', 'draft'),
    ('SCN-SO-JS-1', '场景客户A', 'SCN-TER-CN-EAST-JS', 'draft'),
    ('SCN-SO-NORTH-1', '场景客户B', 'SCN-TER-CN-NORTH', 'draft'),
    ('SCN-SO-NOTERR-1', '场景客户C', None, 'draft'),
    ('SCN-SO-CONF-1', '场景客户A', 'SCN-TER-CN-EAST-SH', 'confirmed'),
]

SALES_ORG_ID = 318       # 华东销售中心（org_functions 具备 sales 职能）
CURRENCY_CNY = 8
ORDER_TYPE_STD = 1
ORDER_DATE = '2026-10-26'


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
    """写表前把 YAML schema 注册进全局 registry（table_name 白名单 / 引擎依赖）。"""
    from meta.core import table_name_validator
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    register_from_directory(get_yaml_schema_dir())
    table_name_validator.invalidate_cache()


def _territory_id(ds, code: str) -> Any:
    row = _one(ds, 'SELECT id FROM territories WHERE code = ?', [code])
    if not row:
        raise LookupError(f'销售区域不存在: {code}')
    return row['id']


def _customer_id(ds, name: str) -> Any:
    row = _one(ds, 'SELECT id FROM customer_accounts WHERE name = ?', [name])
    if not row:
        raise LookupError(f'客户不存在: {name}')
    return row['id']


# ---------------------------------------------------------------- 写入

def seed_territory_scenario_data(ds) -> Dict[str, Any]:
    """写入全部 SCN 场景数据；返回引用映射（territories / customers / orders / ps）。"""
    ensure_schemas_registered()
    tids: Dict[str, Any] = {}

    # S1 / S2 / S3：区域树（level 按父链派生，与 R-TER-4 同口径）
    for code, name, parent_code, ttype, status in _TERRITORIES:
        parent_id = tids.get(parent_code) if parent_code else None
        level = 1 if parent_id is None else _one(
            ds, 'SELECT level FROM territories WHERE id = ?', [parent_id])['level'] + 1
        tids[code] = _upsert(
            ds, 'territories', 'SELECT id FROM territories WHERE code = ?', [code],
            {
                'code': code, 'name': name, 'parent_id': parent_id,
                'level': level, 'territory_type': ttype, 'status': status,
                'description': 'SCN 场景数据',
            })

    # S4 / S5：客户档案（party + customer_account 两层）
    cids: Dict[str, Any] = {}
    for party_code, party_name, customer_name in _CUSTOMERS:
        party_id = _upsert(
            ds, 'parties', 'SELECT id FROM parties WHERE code = ?', [party_code],
            {'code': party_code, 'name': party_name,
             'party_type': 'organization', 'source': 'manual', 'status': 'active'})
        # 按名称定位：relation_id 直接存 party_id 会与其他脚本的真实关系行 id 冲突。
        cids[customer_name] = _upsert(
            ds, 'customer_accounts', 'SELECT id FROM customer_accounts WHERE name = ?',
            [customer_name],
            {'relation_id': party_id, 'customer_type': 'external',
             'name': customer_name, 'description': 'SCN 场景数据'})

    # S4：客户区域分配（主 / 次 / 过期）
    for customer_name, tcode, is_primary, priority, eff_from, eff_to in _ASSIGNMENTS:
        cid = cids[customer_name]
        tid = tids[tcode]
        _upsert(
            ds, 'territory_account_assignments',
            'SELECT id FROM territory_account_assignments '
            'WHERE customer_account_id = ? AND territory_id = ? AND effective_from = ?',
            [cid, tid, eff_from],
            {'customer_account_id': cid, 'territory_id': tid,
             'is_primary': is_primary, 'priority': priority,
             'effective_from': eff_from, 'effective_to': eff_to,
             'assignment_source': 'manual'})

    # S6：订单区域快照
    for order_no, customer_name, tcode, status in _ORDERS:
        _upsert(
            ds, 'sales_orders', 'SELECT id FROM sales_orders WHERE order_no = ?',
            [order_no],
            {'order_no': order_no, 'order_type_id': ORDER_TYPE_STD,
             'order_date': ORDER_DATE, 'status': status,
             'customer_account_id': cids[customer_name],
             'org_id': SALES_ORG_ID, 'sales_org_id': SALES_ORG_ID,
             'currency_id': CURRENCY_CNY, 'exchange_rate': 1.0,
             'net_amount': 100.0, 'tax_amount': 0.0, 'gross_amount': 100.0,
             'pricing_status': 'determined',
             'territory_id': tids[tcode] if tcode else None,
             'confirmed_date': '2026-10-26' if status == 'confirmed' else None})

    # S7：数据范围角色（permission_set + territory 维度范围）
    ps_id = _upsert(
        ds, 'permission_sets', 'SELECT id FROM permission_sets WHERE code = ?',
        [PS_CODE],
        {'code': PS_CODE, 'name': PS_NAME, 'description': 'SCN 场景数据',
         'is_active': 1, 'is_system': 0})
    _upsert(
        ds, 'permission_set_dimension_scopes',
        'SELECT id FROM permission_set_dimension_scopes '
        'WHERE permission_set_id = ? AND dimension_code = ?',
        [ps_id, 'territory'],
        {'permission_set_id': ps_id, 'dimension_code': 'territory',
         'dimension_values': json.dumps([tids['SCN-TER-CN-EAST']]),
         'inherit_children': 1, 'scope_mode': 'include'})

    return {'territories': tids, 'customers': cids, 'ps_id': ps_id}


def cleanup_territory_scenario_data(ds) -> Dict[str, int]:
    """只清理 SCN- 前缀范围内的数据；子表先删，区域按 level 倒序删。"""
    counts: Dict[str, int] = {}
    order_nos = "','".join(o[0] for o in _ORDERS)
    customer_names = "','".join(c[2] for c in _CUSTOMERS)
    party_codes = "','".join(c[0] for c in _CUSTOMERS)
    statements = [
        ('sales_orders',
         f"DELETE FROM sales_orders WHERE order_no IN ('{order_nos}')"),
        ('territory_account_assignments',
         "DELETE FROM territory_account_assignments WHERE territory_id IN "
         "(SELECT id FROM territories WHERE code LIKE 'SCN-TER-%') "
         "OR customer_account_id IN (SELECT id FROM customer_accounts "
         f"WHERE name IN ('{customer_names}'))"),
        ('customer_accounts',
         f"DELETE FROM customer_accounts WHERE name IN ('{customer_names}')"),
        ('parties',
         f"DELETE FROM parties WHERE code IN ('{party_codes}')"),
        ('permission_set_dimension_scopes',
         "DELETE FROM permission_set_dimension_scopes WHERE permission_set_id IN "
         "(SELECT id FROM permission_sets WHERE code = ?)"),
        ('permission_sets',
         "DELETE FROM permission_sets WHERE code = ?"),
        ('territories',
         "DELETE FROM territories WHERE code LIKE 'SCN-TER-%'"),
    ]
    for table, sql in statements:
        params = [PS_CODE] if '?' in sql else None
        result = ds.execute(sql, params)
        rowcount = getattr(result, 'rowcount', None)
        counts[table] = -1 if rowcount is None or rowcount < 0 else rowcount
    ds.commit()
    return counts


def reset_territory_scenario_data(ds) -> Dict[str, Any]:
    cleanup_territory_scenario_data(ds)
    return seed_territory_scenario_data(ds)


# ---------------------------------------------------------------- 自检

def _run_checks(ds) -> List[tuple]:
    """返回 [(检查项, passed, detail)]；全部基于真实库当前数据。"""
    from meta.services.dimension_scope_engine import DimensionScopeEngine
    from meta.services.sales_order_guard_service import (
        SalesOrderGuardError, SalesOrderGuardService,
    )
    from meta.services.territory_guard_service import (
        TerritoryGuardError, TerritoryGuardService,
    )

    ensure_schemas_registered()
    checks: List[tuple] = []

    def check(name: str, fn: Callable[[], str]) -> None:
        try:
            checks.append((name, True, fn()))
        except AssertionError as e:
            checks.append((name, False, str(e)))
        except Exception as e:  # 非断言异常同样记失败，避免自检中断
            checks.append((name, False, f'{type(e).__name__}: {e}'))

    t = TerritoryGuardService(ds)
    so = SalesOrderGuardService(ds)
    engine = DimensionScopeEngine(ds)
    tids = {row['code']: row['id'] for row in ds.query(
        "SELECT id, code FROM territories WHERE code LIKE 'SCN-TER-%'")}

    def tree_levels() -> str:
        rows = ds.query(
            "SELECT code, parent_id, level FROM territories "
            "WHERE code LIKE 'SCN-TER-%'")
        levels = {r['code']: r['level'] for r in rows}
        expect = {'SCN-TER-CN': 1, 'SCN-TER-CN-EAST': 2,
                  'SCN-TER-CN-EAST-SH': 3, 'SCN-TER-CN-EAST-JS': 3,
                  'SCN-TER-CN-NORTH': 2, 'SCN-TER-IND': 1, 'SCN-TER-OFF': 1}
        assert levels == expect, f'level 不符: {levels}'
        return '7 个区域 level 全部按父链派生'

    def territory_type() -> str:
        row = _one(ds, 'SELECT territory_type FROM territories WHERE code = ?',
                   ['SCN-TER-IND'])
        assert row and row['territory_type'] == 'industry', f'territory_type={row}'
        return 'industry / geographic 两值可用'

    def level_derivation() -> str:
        assert t.validate_territory_write({'parent_id': tids['SCN-TER-CN-EAST']}) == 3
        return '挂到华东下派生出 level=3'

    def cycle_rejected() -> str:
        try:
            t.validate_territory_write(
                {'parent_id': tids['SCN-TER-CN-EAST-SH']},
                exclude_id=tids['SCN-TER-CN-EAST'])
        except TerritoryGuardError as e:
            return f'环被拒（rule={e.rule}）'
        raise AssertionError('成环未拒绝')

    def self_parent_rejected() -> str:
        try:
            t.validate_territory_write(
                {'parent_id': tids['SCN-TER-CN-EAST']},
                exclude_id=tids['SCN-TER-CN-EAST'])
        except TerritoryGuardError as e:
            return f'自引用被拒（rule={e.rule}）'
        raise AssertionError('自引用未拒绝')

    def inactive_assignment_rejected() -> str:
        try:
            t.validate_assignment_write(
                {'territory_id': tids['SCN-TER-OFF'],
                 'effective_from': '2026-01-01'}, assignee_label='客户')
        except TerritoryGuardError as e:
            assert e.rule == 'territory_inactive', e.rule
            return '停用区域分配被拒（R-TER-6）'
        raise AssertionError('停用区域分配未拒绝')

    def date_range_rejected() -> str:
        try:
            t.validate_assignment_write(
                {'territory_id': tids['SCN-TER-CN-EAST'],
                 'effective_from': '2026-02-01', 'effective_to': '2026-02-01'},
                assignee_label='客户')
        except TerritoryGuardError as e:
            assert e.rule == 'assignment_date_range', e.rule
            return '有效期倒置被拒（R-TER-3）'
        raise AssertionError('有效期倒置未拒绝')

    def second_primary_rejected() -> str:
        cid = _customer_id(ds, '场景客户A')
        try:
            ds.execute(
                'INSERT INTO territory_account_assignments '
                '(customer_account_id, territory_id, effective_from, is_primary, '
                ' assignment_source) VALUES (?, ?, ?, 1, ?)',
                [cid, tids['SCN-TER-CN-NORTH'], '2026-01-01', 'manual'])
        except Exception as e:
            assert 'UNIQUE' in str(e).upper() or 'unique' in str(e), str(e)
            return '同日第二主区域被唯一索引拒绝（R-TER-7）'
        raise AssertionError('第二主区域未拒绝')

    def default_selection() -> str:
        a = so.territory_default({'customer_account_id': _customer_id(ds, '场景客户A')})
        b = so.territory_default({'customer_account_id': _customer_id(ds, '场景客户B')})
        c = so.territory_default({'customer_account_id': _customer_id(ds, '场景客户C')})
        assert a == {'territory_id': tids['SCN-TER-CN-EAST-SH']}, a
        assert b == {'territory_id': tids['SCN-TER-CN-EAST']}, b
        assert c == {}, c
        return '主区域优先 / 父区域可用 / 无分配留空（§6.1）'

    def condition_scope() -> str:
        ps = _one(ds, 'SELECT id FROM permission_sets WHERE code = ?', [PS_CODE])
        conds = engine.derive_data_conditions(ps['id'])
        cond = conds.get('sales_order', '')
        expect = {tids['SCN-TER-CN-EAST'], tids['SCN-TER-CN-EAST-SH'],
                  tids['SCN-TER-CN-EAST-JS']}
        assert cond.startswith('territory_id IN ('), cond
        got = {int(x) for x in cond.split('(')[1].split(')')[0].split(',')}
        assert got == expect, f'{got} != {expect}'
        return f'{cond}'

    def visibility() -> str:
        ps = _one(ds, 'SELECT id FROM permission_sets WHERE code = ?', [PS_CODE])
        cond = engine.derive_data_conditions(ps['id'])['sales_order']
        rows = ds.query(
            f"SELECT order_no FROM sales_orders WHERE {cond}")
        got = {r['order_no'] for r in rows}
        expect = {'SCN-SO-SH-1', 'SCN-SO-JS-1', 'SCN-SO-CONF-1'}
        assert got == expect, f'可见={sorted(got)}'
        return '华东子树 3 单可见；华北 / 无区域不可见'

    def confirmed_frozen() -> str:
        try:
            so.validate_order_write(
                {'territory_id': tids['SCN-TER-CN-EAST-JS']},
                old_data={'status': 'confirmed',
                          'territory_id': tids['SCN-TER-CN-EAST-SH']})
        except SalesOrderGuardError as e:
            assert e.rule == 'order_territory_locked', e.rule
            return '确认后改区域被拒（R-TER-8）'
        raise AssertionError('确认后修改未拒绝')

    def draft_mutable() -> str:
        so.validate_order_write(
            {'territory_id': tids['SCN-TER-CN-EAST-JS']},
            old_data={'status': 'draft',
                      'territory_id': tids['SCN-TER-CN-EAST-SH']})
        return '草稿可改区域'

    def hub_menu() -> str:
        row = _one(ds, "SELECT page_type FROM menus WHERE menu_code = 'territory-list'", [])
        assert row and row['page_type'] == 'multi_object_hub', f'menu={row}'
        return '菜单形态 = multi_object_hub（M4）'

    check('S1 区域树 level 派生', tree_levels)
    check('S2 territory_type 两值', territory_type)
    check('S1b 新增节点 level 派生', level_derivation)
    check('S8a 成环拒绝（R-TER-1）', cycle_rejected)
    check('S8b 自引用拒绝（R-TER-1）', self_parent_rejected)
    check('S8c 停用区域分配拒绝（R-TER-6）', inactive_assignment_rejected)
    check('S8d 有效期倒置拒绝（R-TER-3）', date_range_rejected)
    check('S8e 第二主区域拒绝（R-TER-7）', second_primary_rejected)
    check('S4/S5 主区域带出（§6.1）', default_selection)
    check('S7 数据条件（M4）', condition_scope)
    check('S6 订单可见性（M4）', visibility)
    check('S6b 确认后区域冻结（R-TER-8）', confirmed_frozen)
    check('S6c 草稿可改区域', draft_mutable)
    check('S1c 菜单形态（M4）', hub_menu)
    return checks


def verify_territory_scenario(ds) -> int:
    checks = _run_checks(ds)
    width = max(len(name) for name, _, _ in checks)
    for name, passed, detail in checks:
        flag = '[PASS]' if passed else '[FAIL]'
        print(f'{flag} {name.ljust(width)}  {detail}')
    failed = [c for c in checks if not c[1]]
    print(f'\n合计 {len(checks)} 项：通过 {len(checks) - len(failed)}，失败 {len(failed)}')
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
        print('[cleanup]', cleanup_territory_scenario_data(ds))
        return 0
    if action == '--reset':
        seed = reset_territory_scenario_data(ds)
        print('[reset] territories=%d customers=%d ps=%s'
              % (len(seed['territories']), len(seed['customers']), seed['ps_id']))
        return 0
    if action == '--verify':
        return verify_territory_scenario(ds)

    seed = seed_territory_scenario_data(ds)
    print('[seed] territories=%d customers=%d ps=%s'
          % (len(seed['territories']), len(seed['customers']), seed['ps_id']))
    return 0


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))
