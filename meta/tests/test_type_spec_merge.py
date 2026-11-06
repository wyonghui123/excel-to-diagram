# -*- coding: utf-8 -*-
"""S2 类型规格别名（type_spec）测试。"""

import pytest

from meta.core import yaml_loader


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
