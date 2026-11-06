# -*- coding: utf-8 -*-
"""业务对象组织边界（Spec 24）声明与服务校验

覆盖：
  1. 全量 org_scope 声明合法（V1-V5）；
  2. 规格 §4 登记清单完整且模式一致（V6）；
  3. V1-V5 负向用例（防止校验器空转）；
  4. visible_org_ids：权限集子树 / 排除 / 管理员豁免 / 三态开关（主组织不授权）；
  5. 读条件 direct / dual / chain（含嵌套 chain）；
  6. 写判定：direct / dual / chain 与组织职能校验。
"""
import pytest

from meta.core.action_context import ActionContext
from meta.core.interceptors.org_scope_interceptor import OrgScopeDenied, OrgScopeInterceptor
from meta.core.models import registry
from meta.core.org_scope_validator import (
    ORG_SCOPE_AMBIGUOUS,
    ORG_SCOPE_CHAIN_INVALID,
    ORG_SCOPE_DUAL_INCOMPLETE,
    ORG_SCOPE_FIELD_MISSING,
    ORG_SCOPE_UNDECLARED,
    REQUIRED_ORG_SCOPE_BOS,
    validate_object,
    validate_registry,
)
from meta.core.yaml_loader import get_yaml_schema_dir
from meta.services.org_scope_service import (
    ORG_SCOPE_ENFORCE,
    OrgScopeService,
    clear_org_scope_cache,
)
from meta.tests.factories._org_scope_helpers import (
    insert_location,
    insert_user,
    make_test_ds,
    set_control_parameter,
)


def _load_registry():
    if not registry.all():
        registry.reload(get_yaml_schema_dir())
    return registry


def _obj(**overrides):
    obj = {
        'id': 'scope_probe',
        'fields': [
            {'id': 'id', 'db_column': 'id'},
            {'id': 'org_id', 'db_column': 'org_id'},
            {'id': 'from_org_id', 'db_column': 'from_org_id'},
            {'id': 'to_org_id', 'db_column': 'to_org_id'},
            {'id': 'parent_id', 'db_column': 'parent_id'},
        ],
        'org_scope': {'mode': 'direct', 'field': 'org_id'},
    }
    obj.update(overrides)
    return obj


def _codes(errors):
    return [e.code for e in errors]


# ---------------------------------------------------------------------------
# T1: 声明校验
# ---------------------------------------------------------------------------

def test_registry_declarations_are_valid():
    _load_registry()
    errors = validate_registry()
    assert errors == [], '\n'.join(str(e) for e in errors)


def test_required_objects_are_registered():
    _load_registry()
    missing = [bo for bo in REQUIRED_ORG_SCOPE_BOS if registry.get(bo) is None]
    assert missing == []


def test_v1_invalid_mode():
    assert _codes(validate_object(_obj(org_scope={'mode': 'bogus'}))) == [ORG_SCOPE_UNDECLARED]


def test_v2_direct_field_missing():
    assert _codes(validate_object(_obj(org_scope={'mode': 'direct', 'field': 'nope_id'}))) == [
        ORG_SCOPE_FIELD_MISSING
    ]


def test_v2_direct_field_required():
    assert _codes(validate_object(_obj(org_scope={'mode': 'direct'}))) == [ORG_SCOPE_FIELD_MISSING]


def test_v3_chain_incomplete():
    assert _codes(validate_object(_obj(org_scope={'mode': 'chain'}))) == [ORG_SCOPE_CHAIN_INVALID]


def test_v3_chain_host_unregistered():
    errors = validate_object(_obj(org_scope={
        'mode': 'chain', 'via': 'parent_id', 'host': 'not_exists_bo', 'field': 'org_id',
    }))
    assert _codes(errors) == [ORG_SCOPE_CHAIN_INVALID]


def test_v4_dual_incomplete():
    errors = validate_object(_obj(org_scope={
        'mode': 'dual', 'from_field': 'from_org_id',
    }))
    assert _codes(errors) == [ORG_SCOPE_DUAL_INCOMPLETE]


def test_v5_dual_with_field_is_ambiguous():
    errors = validate_object(_obj(org_scope={
        'mode': 'dual', 'field': 'org_id',
        'from_field': 'from_org_id', 'to_field': 'to_org_id',
    }))
    assert ORG_SCOPE_AMBIGUOUS in _codes(errors)


def test_v5_direct_with_dual_fields_is_ambiguous():
    errors = validate_object(_obj(org_scope={
        'mode': 'direct', 'field': 'org_id',
        'from_field': 'from_org_id',
    }))
    assert ORG_SCOPE_AMBIGUOUS in _codes(errors)


# ---------------------------------------------------------------------------
# T2: visible_org_ids
# ---------------------------------------------------------------------------

@pytest.fixture()
def ds():
    clear_org_scope_cache()
    generator = make_test_ds()
    data_source, _path = next(generator)
    yield data_source
    try:
        next(generator)
    except StopIteration:
        pass
    clear_org_scope_cache()


def test_visible_orgs_include_subtree_and_exclude(ds):
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    # include [2] 展开为 {2,3}；exclude [3]（inherit_children=0）剔除 3
    assert service.visible_org_ids(100) == {2}


def test_primary_org_does_not_grant_access(ds):
    insert_user(ds, 100, 5)
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    # 规格 24 §5.1：主组织只作默认上下文，不进入可见集
    assert service.visible_org_ids(100) == {2}


def test_primary_org_alone_yields_empty(ds):
    insert_user(ds, 300, 5)
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    # 无任何权限集组织范围时，仅有主组织不授予数据访问
    assert service.visible_org_ids(300) == set()


def test_visible_orgs_admin_is_all(ds):
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    assert service.visible_org_ids(100, is_admin=True) is None


def test_visible_orgs_empty_without_scope(ds):
    insert_user(ds, 200, None)
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    assert service.visible_org_ids(200) == set()


def test_mode_from_control_parameter(ds):
    set_control_parameter(ds, 'compat')
    assert OrgScopeService(ds).mode() == 'compat'


def test_mode_defaults_off(ds):
    assert OrgScopeService(ds).mode() == 'off'


def test_reference_function_filter(ds):
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    assert service.visible_org_ids_for_function(100, 'inventory') == {2}


# ---------------------------------------------------------------------------
# T3: 读条件
# ---------------------------------------------------------------------------

def test_read_condition_direct():
    _load_registry()
    service = OrgScopeService(None, mode=ORG_SCOPE_ENFORCE)
    conds = service.build_read_conditions(registry.get('receipt'), {2, 3})
    assert conds == [{'type': 'raw', 'expr': 'inventory_org_id IN (2,3)', 'params': []}]


def test_read_condition_dual():
    _load_registry()
    service = OrgScopeService(None, mode=ORG_SCOPE_ENFORCE)
    conds = service.build_read_conditions(registry.get('transfer_order'), {2})
    assert conds == [{
        'type': 'raw',
        'expr': '(from_org_id IN (2) OR to_org_id IN (2))',
        'params': [],
    }]


def test_read_condition_chain():
    _load_registry()
    service = OrgScopeService(None, mode=ORG_SCOPE_ENFORCE)
    conds = service.build_read_conditions(registry.get('shipment'), {2})
    assert conds[0]['expr'] == (
        'EXISTS (SELECT 1 FROM locations h0 '
        'WHERE h0.id = ship_from_location_id AND h0.org_id IN (2))'
    )


def test_read_condition_nested_chain():
    _load_registry()
    service = OrgScopeService(None, mode=ORG_SCOPE_ENFORCE)
    conds = service.build_read_conditions(registry.get('shipment_line'), {2})
    expr = conds[0]['expr']
    assert 'FROM shipment_lines' not in expr
    assert 'FROM shipments h0' in expr
    assert 'FROM locations h1' in expr


def test_read_condition_empty_visible_is_deny():
    _load_registry()
    service = OrgScopeService(None, mode=ORG_SCOPE_ENFORCE)
    assert service.build_read_conditions(registry.get('receipt'), set()) == [
        {'type': 'raw', 'expr': '1=0', 'params': []}
    ]


def test_read_condition_global_is_noop():
    _load_registry()
    service = OrgScopeService(None, mode=ORG_SCOPE_ENFORCE)
    assert service.build_read_conditions(registry.get('items'), set()) == []


# ---------------------------------------------------------------------------
# T4/T7: 写判定 + 职能
# ---------------------------------------------------------------------------

def test_write_direct(ds):
    _load_registry()
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    receipt = registry.get('receipt')
    assert service.is_writable(receipt, {'inventory_org_id': 2}, {2, 3})
    assert not service.is_writable(receipt, {'inventory_org_id': 4}, {2, 3})


def test_write_dual_requires_both_ends(ds):
    _load_registry()
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    transfer = registry.get('transfer_order')
    assert service.is_writable(transfer, {'from_org_id': 2, 'to_org_id': 3}, {2, 3})
    assert not service.is_writable(transfer, {'from_org_id': 2, 'to_org_id': 4}, {2, 3})


def test_write_chain_and_function(ds):
    _load_registry()
    insert_location(ds, 2)
    service = OrgScopeService(ds, mode=ORG_SCOPE_ENFORCE)
    shipment = registry.get('shipment')
    assert service.is_writable(shipment, {'ship_from_location_id': 9}, {2})
    assert not service.is_writable(shipment, {'ship_from_location_id': 9}, {4})

    assert service.check_function({2}, 'inventory') is None
    assert service.check_function({4}, 'inventory') == 4


# ---------------------------------------------------------------------------
# T3/T4: 拦截器接线（读注入 / 写拒绝 / compat 不拦截）
# ---------------------------------------------------------------------------

def _ctx(ds, action, params=None, user_id=100):
    return ActionContext(
        meta_object=registry.get('receipt'),
        action=action,
        params=params or {},
        data_source=ds,
        user_id=user_id,
    )


def test_interceptor_injects_read_filter(ds):
    _load_registry()
    set_control_parameter(ds, 'enforce')
    context = _ctx(ds, 'crud_query')
    OrgScopeInterceptor().before_action(context)
    assert context.extra['query_conditions'] == [
        {'type': 'raw', 'expr': 'inventory_org_id IN (2)', 'params': []}
    ]


def test_interceptor_compat_does_not_filter(ds):
    _load_registry()
    set_control_parameter(ds, 'compat')
    context = _ctx(ds, 'crud_query')
    OrgScopeInterceptor().before_action(context)
    assert 'query_conditions' not in context.extra


def test_interceptor_denies_invisible_org_on_create(ds):
    _load_registry()
    set_control_parameter(ds, 'enforce')
    context = _ctx(ds, 'crud_create', {'inventory_org_id': 4})
    with pytest.raises(OrgScopeDenied):
        OrgScopeInterceptor().before_action(context)


def test_interceptor_allows_visible_org_on_create(ds):
    _load_registry()
    set_control_parameter(ds, 'enforce')
    context = _ctx(ds, 'crud_create', {'inventory_org_id': 2})
    OrgScopeInterceptor().before_action(context)


def test_interceptor_denies_moving_record_to_invisible_org(ds):
    _load_registry()
    set_control_parameter(ds, 'enforce')
    context = _ctx(ds, 'crud_update', {'inventory_org_id': 4})
    context.old_data = {'id': 1, 'inventory_org_id': 2}
    with pytest.raises(OrgScopeDenied):
        OrgScopeInterceptor().before_action(context)
