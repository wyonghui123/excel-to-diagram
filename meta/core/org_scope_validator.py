# -*- coding: utf-8 -*-
"""业务对象组织边界声明校验（规格 24 §3.1 V1-V6）

声明真源 = 各 BO YAML 的顶层 ``org_scope`` 块。
本模块只做加载期/测试期校验，不参与请求链路。
"""

import os
import re
from typing import Dict, List, Optional, Set

import yaml

ORG_SCOPE_MODES = ('direct', 'chain', 'dual', 'global')

# 错误码（规格 24 §6）
ORG_SCOPE_UNDECLARED = 'ORG_SCOPE_UNDECLARED'
ORG_SCOPE_AMBIGUOUS = 'ORG_SCOPE_AMBIGUOUS'
ORG_SCOPE_FIELD_MISSING = 'ORG_SCOPE_FIELD_MISSING'
ORG_SCOPE_CHAIN_INVALID = 'ORG_SCOPE_CHAIN_INVALID'
ORG_SCOPE_DUAL_INCOMPLETE = 'ORG_SCOPE_DUAL_INCOMPLETE'
ORG_SCOPE_EXEMPTION_REASON_MISSING = 'ORG_SCOPE_EXEMPTION_REASON_MISSING'

# 组织字段命名（用于推导「可能承载 owning org」的候选对象）
_ORG_COLUMN_PATTERN = re.compile(r'(^|_)org_id$')

EXEMPTIONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'schemas',
    'org_scope_exemptions.yaml',
)


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


def org_columns(meta_obj) -> Set[str]:
    """返回对象中形如 org_id / *_org_id 的字段名集合。"""
    return {
        column for column in _declared_columns(meta_obj)
        if _ORG_COLUMN_PATTERN.search(column)
    }


def load_exemptions() -> Dict[str, str]:
    """读取豁免清单；理由为空直接抛错（FR-003：豁免必须带理由）。"""
    if not os.path.exists(EXEMPTIONS_PATH):
        return {}
    with open(EXEMPTIONS_PATH, 'r', encoding='utf-8') as handle:
        data = yaml.safe_load(handle) or {}

    result: Dict[str, str] = {}
    for item in data.get('exemptions') or []:
        bo_id = str(item.get('object') or '').strip()
        reason = str(item.get('reason') or '').strip()
        if not bo_id:
            continue
        if not reason:
            raise OrgScopeDeclarationError(
                ORG_SCOPE_EXEMPTION_REASON_MISSING, '豁免必须填写 reason', bo_id)
        result[bo_id] = reason
    return result


def candidate_org_scope_bos(registry_obj=None) -> Set[str]:
    """推导候选对象：已声明 org_scope ∪ 含组织字段的 BO。"""
    if registry_obj is None:
        from meta.core.models import registry as registry_obj

    candidates: Set[str] = set()
    for obj in registry_obj.all():
        if _get(obj, 'org_scope', None) or org_columns(obj):
            candidates.add(_get(obj, 'id', '') or '')
    return {bo_id for bo_id in candidates if bo_id}


def required_org_scope_bos(registry_obj=None, exemptions=None) -> Set[str]:
    """候选 - 显式豁免 = 必须声明 org_scope 的集合。"""
    if exemptions is None:
        exemptions = load_exemptions()
    return candidate_org_scope_bos(registry_obj) - set(exemptions)


def validate_registry(registry_obj=None) -> List[OrgScopeDeclarationError]:
    """全量校验：已声明对象的 V1-V5 + 候选对象必须声明（V6）。"""
    if registry_obj is None:
        from meta.core.models import registry as registry_obj

    errors: List[OrgScopeDeclarationError] = []
    for obj in registry_obj.all():
        errors.extend(validate_object(obj, registry_obj))

    # V6: 候选对象（含组织字段或已显式登记）必须声明；豁免只能来自 YAML
    try:
        exemptions = load_exemptions()
    except OrgScopeDeclarationError as exc:
        errors.append(exc)
        exemptions = {}

    for bo_id in sorted(required_org_scope_bos(registry_obj, exemptions)):
        obj = registry_obj.get(bo_id)
        if obj is None:
            continue
        if not (_get(obj, 'org_scope', None) or {}):
            errors.append(OrgScopeDeclarationError(
                ORG_SCOPE_UNDECLARED,
                '存在组织字段但未声明 org_scope（如为执行组织字段，请登记到 '
                'org_scope_exemptions.yaml 并填写理由）', bo_id,
            ))
    return errors
