# -*- coding: utf-8 -*-
"""doc_effect 声明全量校验（D7 收口 / 规格 §7.3 V1-V6）。

覆盖：
  1. 全部已加载 schema 的 `doc_effect` 声明合法（`validate_registry()` 无错误）；
  2. 逆向对象清单确实声明了 `reversal`（防止新增对象漏声明）；
  3. 六个 `DECL_*` 错误码各有负向用例（防止校验器退化为空转）。
"""
import copy

import pytest

from meta.core.doc_effect_validator import (
    DocEffectDeclarationError, validate_object, validate_registry)
from meta.core.models import registry
from meta.core.yaml_loader import get_yaml_schema_dir

#: 规格 §12 要求具备逆向能力的对象
EXPECTED_REVERSIBLE = {
    'receipt',
    'shipment',
    'transfer_order',
    'inventory_adjustment',
}


def _load_registry():
    if not registry.all():
        registry.reload(get_yaml_schema_dir())
    return registry


def _minimal(**overrides):
    """构造最小合法声明，供负向用例逐项破坏。"""
    obj = {
        'id': 'decl_probe',
        'fields': [
            {'id': 'status', 'db_column': 'status',
             'enum_values': [{'value': 'posted'}, {'value': 'reversed'}]},
        ],
        'rules': [
            {'rule_type': 'state_transition',
             'from_states': ['posted'], 'to_state': 'reversed'},
        ],
        'doc_effect': {
            'reversal': {'to_state': 'reversed', 'from_states': ['posted']},
            'faces': [],
        },
    }
    obj = copy.deepcopy(obj)
    doc_effect = overrides.pop('doc_effect', None)
    if doc_effect:
        obj['doc_effect'].update(doc_effect)
    obj.update(overrides)
    return obj


def _expect(code, obj):
    with pytest.raises(DocEffectDeclarationError) as info:
        validate_object(obj)
    assert info.value.code == code


def test_registry_declarations_are_valid():
    _load_registry()
    assert validate_registry() == []


def test_expected_objects_declare_reversal():
    _load_registry()
    declared = set()
    for obj in registry.all():
        doc_effect = getattr(obj, 'doc_effect', None) or {}
        if isinstance(doc_effect, dict) and doc_effect.get('reversal'):
            declared.add(obj.id)
    assert EXPECTED_REVERSIBLE <= declared


def test_v1_invalid_to_state():
    _expect('DECL_INVALID_TO_STATE', _minimal(doc_effect={
        'reversal': {'to_state': 'missing', 'from_states': ['posted']}}))


def test_v2_state_mismatch():
    _expect('DECL_STATE_MISMATCH', _minimal(doc_effect={
        'reversal': {'to_state': 'reversed', 'from_states': ['draft']}}))


def test_v3_unknown_primitive():
    _expect('DECL_UNKNOWN_PRIMITIVE', _minimal(doc_effect={
        'faces': [{'id': 'face_a', 'primitive': 'no_such_primitive'}]}))


def test_v4_ref_field_required():
    _expect('DECL_REF_FIELD_REQUIRED', _minimal(doc_effect={
        'faces': [{'id': 'face_a', 'primitive': 'edge_compensate_by_source'}]}))


def test_v5_unresolved_placeholder():
    _expect('DECL_UNRESOLVED_PLACEHOLDER', _minimal(doc_effect={
        'reversal': {'to_state': 'reversed', 'from_states': ['posted'],
                     'ref_field': 'id'},
        'faces': [{'id': 'face_a', 'primitive': 'edge_compensate_by_source',
                   'args': {'ref': '{bogus_root}'}}]}))


def test_v6_duplicate_face_id():
    _expect('DECL_DUPLICATE_FACE', _minimal(doc_effect={
        'faces': [{'id': 'face_a', 'primitive': 'edge_compensate_by_source'},
                  {'id': 'face_a', 'primitive': 'edge_compensate_by_source'}]}))


def test_v6_face_without_id():
    _expect('DECL_FACE_INVALID', _minimal(doc_effect={
        'faces': [{'primitive': 'edge_compensate_by_source'}]}))
