# -*- coding: utf-8 -*-
"""类型规格别名与扩展属性值服务派生的契约测试。

[TEST-EFF P2-1] 由两个小文件合并而来，减少逐文件启动开销：
- test_type_spec_merge.py
- test_attribute_value_service_factory.py
"""

import pytest

from meta.core import yaml_loader
from meta.services.attribute_value_service import (
    AttributeValueService,
    ItemAttributeValueService,
)
from meta.services.batch_attribute_value_service import BatchAttributeValueService


def _load_specs(tmp_path, body):
    (tmp_path / "_type_specs.yaml").write_text(body, encoding="utf-8")
    yaml_loader.load_type_specs(str(tmp_path))


def test_type_spec_inherits(tmp_path):
    _load_specs(tmp_path, (
        "type_specs:\n"
        "  code_32:\n"
        "    type: string\n"
        "    max_length: 32\n"
        "    pattern: '^[A-Z]+$'\n"
    ))
    field = yaml_loader.parse_field({"id": "c", "name": "编码", "type_spec": "code_32"})
    assert field.max_length == 32
    assert field.pattern == "^[A-Z]+$"


def test_field_explicit_value_wins(tmp_path):
    _load_specs(tmp_path, (
        "type_specs:\n"
        "  name_64:\n"
        "    type: string\n"
        "    max_length: 64\n"
    ))
    field = yaml_loader.parse_field({"id": "n", "name": "名称", "type_spec": "name_64", "max_length": 8})
    assert field.max_length == 8


def test_unknown_spec_raises(tmp_path):
    _load_specs(tmp_path, "type_specs: {}\n")
    with pytest.raises(ValueError, match="unknown type_spec"):
        yaml_loader.parse_field({"id": "x", "name": "X", "type_spec": "nope"})


def test_repo_type_specs_load():
    """仓库自带 _type_specs.yaml 可被加载，且四类规格齐全。"""
    specs = yaml_loader.load_type_specs("meta/schemas")
    assert set(specs) >= {"code_32", "code_64", "name_64", "description_1024"}


def test_party_keeps_existing_names():
    svc = AttributeValueService.for_object('party', data_source=object())
    assert svc.VALUE_TABLE == 'party_attribute_values'
    assert svc.OWNER_FIELD == 'party_id'


def test_new_object_follows_naming_convention():
    svc = AttributeValueService.for_object('purchase_order', data_source=object())
    assert svc.VALUE_TABLE == 'purchase_order_attribute_values'
    assert svc.OWNER_FIELD == 'purchase_order_id'


def test_specialized_subclasses_are_resolved():
    assert isinstance(
        AttributeValueService.for_object('item', data_source=object()),
        ItemAttributeValueService)
    assert isinstance(
        AttributeValueService.for_object('batch', data_source=object()),
        BatchAttributeValueService)


def test_derived_service_keeps_base_behaviour():
    svc = AttributeValueService.for_object('purchase_order', data_source=object())
    assert isinstance(svc, AttributeValueService)
    assert svc.DEFINITION_TABLE == 'attribute_definitions'
