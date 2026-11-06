# -*- coding: utf-8 -*-
"""业务对象组织边界声明校验（规格 24 §3.1 V1-V6）

声明真源 = 各 BO YAML 的顶层 ``org_scope`` 块。
本模块只做加载期/测试期校验，不参与请求链路。
"""

from typing import Dict, List, Optional, Set

ORG_SCOPE_MODES = ('direct', 'chain', 'dual', 'global')

# 错误码（规格 24 §6）
ORG_SCOPE_UNDECLARED = 'ORG_SCOPE_UNDECLARED'
ORG_SCOPE_AMBIGUOUS = 'ORG_SCOPE_AMBIGUOUS'
ORG_SCOPE_FIELD_MISSING = 'ORG_SCOPE_FIELD_MISSING'
ORG_SCOPE_CHAIN_INVALID = 'ORG_SCOPE_CHAIN_INVALID'
ORG_SCOPE_DUAL_INCOMPLETE = 'ORG_SCOPE_DUAL_INCOMPLETE'

# 规格 24 §4 登记清单（一致性测试期望集合，mode 为期望值）
#   声明真源仍在各 BO YAML；此常量用于拦截"漏登记 / 模式漂移"。
REQUIRED_ORG_SCOPE_BOS: Dict[str, str] = {
    # ── A 类：直接归属 ──
    'purchase_order': 'direct',
    'receipt': 'direct',
    'sales_order': 'direct',
    'inventory_transaction': 'direct',
    'inventory_balance': 'direct',
    'inventory_adjustment': 'direct',
    'inventory_count': 'direct',
    'inventory_reservation': 'direct',
    'serial_number': 'direct',
    'party_internal': 'direct',
    'project': 'direct',
    'location': 'direct',
    'batch': 'direct',
    'employee': 'direct',
    'shift': 'direct',
    'resource': 'direct',
    'resource_group': 'direct',
    'resource_availability': 'direct',
    'resource_rate': 'direct',
    'handling_unit': 'direct',
    'production_version': 'direct',
    'work_definition': 'direct',
    # ── B 类：派生成 ──
    'receipt_line': 'chain',
    'purchase_order_line': 'chain',
    'purchase_order_schedule': 'chain',
    'shipment': 'chain',
    'shipment_line': 'chain',
    'sales_order_line': 'chain',
    'transfer_order_line': 'chain',
    'inventory_adjustment_line': 'chain',
    'inventory_count_line': 'chain',
    'work_order': 'chain',
    # ── C 类：双端 ──
    'transfer_order': 'dual',
    # ── D 类：全局共享（RDS 等价） ──
    'item': 'global',
    'item_group': 'global',
    'item_structure': 'global',
    'item_uom_conversion': 'global',
    'item_xref': 'global',
    'item_attribute_value': 'global',
    'party': 'global',
    'party_archive': 'global',
    'control_parameter_value': 'global',
    'pricing_determination': 'global',
}


class OrgScopeDeclarationError(ValueError):
    """org_scope 声明非法（V1-V6）"""

    def __init__(self, code: str, message: str, bo_id: str = ''):
        self.code = code
        self.bo_id = bo_id
        self.message = message
        super().__init__(f'[{code}] {bo_id}: {message}' if bo_id else f'[{code}] {message}')


def _get(obj, key, default=None):
    """兼容 dict / MetaObject 两种输入"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _declared_columns(meta_obj) -> Set[str]:
    """对象可用于声明的列集合（id 与 db_column 都算）"""
    columns: Set[str] = set()
    for fld in _get(meta_obj, 'fields', None) or []:
        for attr in ('id', 'db_column'):
            if isinstance(fld, dict):
                value = fld.get(attr)
            else:
                value = getattr(fld, attr, None)
            if value:
                columns.add(str(value))
    return columns


def _check_reference_field(meta_obj, field: str, label: str, errors: List[OrgScopeDeclarationError]) -> None:
    if field not in _declared_columns(meta_obj):
        errors.append(OrgScopeDeclarationError(
            ORG_SCOPE_FIELD_MISSING, f'{label} 字段 {field!r} 不存在于对象字段',
            _get(meta_obj, 'id', ''),
        ))


def validate_object(meta_obj, registry_obj=None) -> List[OrgScopeDeclarationError]:
    """校验单个 BO 的 org_scope 声明（V1-V5）"""
    decl = _get(meta_obj, 'org_scope', None) or {}
    if not decl:
        return []

    bo_id = _get(meta_obj, 'id', '')
    errors: List[OrgScopeDeclarationError] = []
    mode = decl.get('mode')

    # V1: mode 合法
    if mode not in ORG_SCOPE_MODES:
        errors.append(OrgScopeDeclarationError(
            ORG_SCOPE_UNDECLARED,
            f'mode={mode!r} 非法，取值应为 {"/".join(ORG_SCOPE_MODES)}', bo_id,
        ))
        return errors

    # V5: 不得同时声明两套组织字段
    if mode == 'dual' and decl.get('field'):
        errors.append(OrgScopeDeclarationError(
            ORG_SCOPE_AMBIGUOUS, 'dual 模式不得同时声明 field', bo_id))
    if mode != 'dual' and (decl.get('from_field') or decl.get('to_field')):
        errors.append(OrgScopeDeclarationError(
            ORG_SCOPE_AMBIGUOUS, f'{mode} 模式不得声明 from_field/to_field', bo_id))

    if mode in ('direct', 'dual'):
        # V2: direct/dual 的 field 必须存在于本 BO
        if mode == 'direct':
            field = decl.get('field')
            if not field:
                errors.append(OrgScopeDeclarationError(
                    ORG_SCOPE_FIELD_MISSING, 'direct 模式必须声明 field', bo_id))
            else:
                _check_reference_field(meta_obj, field, 'owning org', errors)

        # V4: dual 必须同时声明 from_field / to_field
        if mode == 'dual':
            from_field = decl.get('from_field')
            to_field = decl.get('to_field')
            if not from_field or not to_field:
                errors.append(OrgScopeDeclarationError(
                    ORG_SCOPE_DUAL_INCOMPLETE,
                    'dual 模式必须同时声明 from_field 与 to_field', bo_id))
            for label, field in (('from_field', from_field), ('to_field', to_field)):
                if field:
                    _check_reference_field(meta_obj, field, label, errors)

    if mode == 'chain':
        # V3: chain 必须声明 via + host，且 via 属于本 BO
        via = decl.get('via')
        host_id = decl.get('host')
        if not via or not host_id:
            errors.append(OrgScopeDeclarationError(
                ORG_SCOPE_CHAIN_INVALID, 'chain 模式必须声明 via 与 host', bo_id))
            return errors
        _check_reference_field(meta_obj, via, 'via', errors)

        if registry_obj is None:
            try:
                from meta.core.models import registry as registry_obj
            except Exception:
                registry_obj = None

        host_obj = registry_obj.get(host_id) if registry_obj is not None else None
        if host_obj is None:
            errors.append(OrgScopeDeclarationError(
                ORG_SCOPE_CHAIN_INVALID, f'host={host_id!r} 未注册', bo_id))
            return errors

        host_field = decl.get('field')
        if host_field:
            _check_reference_field(host_obj, host_field, f'host({host_id})', errors)
        elif not (getattr(host_obj, 'org_scope', None) or {}):
            errors.append(OrgScopeDeclarationError(
                ORG_SCOPE_CHAIN_INVALID,
                f'host={host_id!r} 既无 field 也未声明 org_scope（无法派生归属组织）', bo_id,
            ))

    return errors


def validate_registry(registry_obj=None) -> List[OrgScopeDeclarationError]:
    """全量校验：已声明对象的 V1-V5 + 规格 §4 登记清单（V6）"""
    if registry_obj is None:
        from meta.core.models import registry as registry_obj

    errors: List[OrgScopeDeclarationError] = []
    for obj in registry_obj.all():
        errors.extend(validate_object(obj, registry_obj))

    # V6: 规格 §4 登记清单必须声明，且模式与期望一致
    for bo_id, expected_mode in REQUIRED_ORG_SCOPE_BOS.items():
        obj = registry_obj.get(bo_id)
        if obj is None:
            continue  # 视图依赖缺失时对象可能未注册
        decl = getattr(obj, 'org_scope', None) or {}
        if not decl:
            errors.append(OrgScopeDeclarationError(
                ORG_SCOPE_UNDECLARED, '规格 §4 要求声明 org_scope 但未声明', bo_id))
        elif decl.get('mode') != expected_mode:
            errors.append(OrgScopeDeclarationError(
                ORG_SCOPE_UNDECLARED,
                f'org_scope.mode={decl.get("mode")!r} 与规格期望 {expected_mode!r} 不一致', bo_id,
            ))
    return errors
