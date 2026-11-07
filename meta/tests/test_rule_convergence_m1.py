# -*- coding: utf-8 -*-
"""规则化收敛 M1：等价性回归 + 静态守卫。

对应 Spec v1.3 FR-007 / FR-008 / FR-009 / FR-013。
断言的是「迁移后读取结果与迁移前常量逐项相等」，不是新行为。
"""

import os
import subprocess
import sys

import pytest

from meta.core import hierarchy_loader, system_field_loader
from meta.services.document_number_service import (
    DocumentNumberError,
    DocumentNumberService,
    _read_numbering,
    get_numbering_map,
)
from meta.services.field_policy_engine import FieldPolicyEngine

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXPECTED_NUMBERING = {
    'sales_order': {
        'no_field': 'order_no',
        'date_field': 'order_date',
        'type_table': 'type_definitions',
    },
    'purchase_order': {
        'no_field': 'order_no',
        'date_field': 'order_date',
        'type_table': 'type_definitions',
    },
    'receipt': {
        'no_field': 'receipt_no',
        'date_field': 'receipt_date',
        'type_table': 'type_definitions',
    },
    'transfer_order': {
        'no_field': 'transfer_order_no',
        'date_field': 'transfer_date',
        'type_table': 'type_definitions',
    },
    'transfer_shipment': {
        'no_field': 'shipment_no',
        'date_field': 'ship_date',
        'scope_bo': 'transfer_shipment',
        'fallback_sequence_code': 'TRS',
    },
}


# ---------------------------------------------------------------- 编号声明

def test_numbering_declarations_equal_legacy():
    mapping = get_numbering_map()
    for object_type, expected in EXPECTED_NUMBERING.items():
        assert object_type in mapping, '缺少 numbering 声明: %s' % object_type
        for key, value in expected.items():
            assert mapping[object_type].get(key) == value, (
                '%s.%s 期望 %r 实际 %r'
                % (object_type, key, value, mapping[object_type].get(key)))


def test_unknown_object_has_no_numbering():
    assert _read_numbering('__no_such_object__') is None


def test_external_number_unknown_object_keeps_error_rule():
    service = DocumentNumberService(object())
    with pytest.raises(DocumentNumberError) as exc_info:
        service.validate_external_number('__no_such_object__', 'X-0001')
    assert exc_info.value.rule == 'NUMBER_SEQUENCE_UNSUPPORTED'


# ---------------------------------------------------------------- 系统字段

EXPECTED_SYSTEM_FIELDS = {
    'id', '_id', 'tenant_id', 'created_at', 'updated_at',
    'created_by', 'updated_by', 'created_date', 'updated_date',
    'created_user', 'updated_user', 'is_system', 'system_flag', 'readonly',
}


def test_system_fields_declaration_equal_legacy():
    actual = system_field_loader.get_system_fields()
    assert set(actual) == EXPECTED_SYSTEM_FIELDS


def test_field_policy_engine_uses_declaration():
    engine = FieldPolicyEngine()
    assert engine._is_system_field('created_at') is True
    assert engine._is_system_field('readonly') is True
    assert engine._is_system_field('order_no') is False
    assert engine._is_system_field('amount') is False


# ---------------------------------------------------------------- 层级映射

EXPECTED_TABLE_MAP = {
    'product': 'products',
    'version': 'versions',
    'domain': 'domains',
    'sub_domain': 'sub_domains',
    'service_module': 'service_modules',
    'business_object': 'business_objects',
}

EXPECTED_DISPLAY_FIELD_MAP = {
    'product': 'name',
    'version': 'name',
    'domain': 'domain_name',
    'sub_domain': 'sub_domain_name',
    'service_module': 'name',
    'business_object': 'name',
}

EXPECTED_CODE_FIELD_MAP = {obj: 'code' for obj in EXPECTED_TABLE_MAP}

EXPECTED_PARENT_INFO_MAP = {
    'version': ('product', 'products', 'product_id', 'name'),
    'domain': ('version', 'versions', 'version_id', 'name'),
    'sub_domain': ('domain', 'domains', 'domain_id', 'name'),
    'service_module': ('sub_domain', 'sub_domains', 'sub_domain_id', 'name'),
    'business_object': ('service_module', 'service_modules',
                        'service_module_id', 'name'),
}


def test_table_map_equal_legacy():
    assert hierarchy_loader.get_table_map() == EXPECTED_TABLE_MAP


def test_display_field_map_equal_legacy():
    assert hierarchy_loader.get_display_field_map() == EXPECTED_DISPLAY_FIELD_MAP


def test_code_field_map_equal_legacy():
    assert hierarchy_loader.get_code_field_map() == EXPECTED_CODE_FIELD_MAP


def test_parent_info_map_equal_legacy():
    assert hierarchy_loader.get_parent_info_map() == EXPECTED_PARENT_INFO_MAP


def test_scope_chain_keeps_four_levels():
    """TBD-4：sub_domain 仍是授权叶子，service_module 不升第 5 锚点。"""
    assert hierarchy_loader.get_scope_chain() == [
        'product', 'version', 'domain', 'sub_domain']


# ---------------------------------------------------------------- 静态守卫

def test_static_guard_has_no_hardcoded_mapping():
    script = os.path.join(PROJECT_ROOT, 'scripts', 'check_rule_convergence.py')
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True, cwd=PROJECT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
