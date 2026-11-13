# -*- coding: utf-8 -*-
"""T13-5 视图配置：col_span / tabs / schema_version 测试

覆盖：
- col_span 越界或非整数被忽略（降级为 None / 不进 col_span_map）
- tabs 引用不存在的 section key 被丢弃
- schema_version 随配置变化、同输入稳定；聚合端点装配版本号
"""

import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration


class TestColSpan:
    @pytest.mark.parametrize("raw,expected", [
        (2, 2), (4, 4), ("3", 3),
        (0, None), (5, None), (-1, None),
        ("abc", None), (None, None), (True, None),
    ])
    def test_parse_col_span_validates_range(self, raw, expected):
        from meta.core.yaml_loader import _parse_col_span

        assert _parse_col_span(raw) == expected

    def test_col_span_map_drops_illegal_values(self):
        from meta.core.yaml_loader import _parse_col_span_map

        assert _parse_col_span_map({"a": 2, "b": 9, "c": "x", "d": "3"}) == {"a": 2, "d": 3}

    def test_builder_ignores_out_of_range_col_span(self):
        from meta.core.models import registry
        from meta.services import view_config_service as view_config_service_module

        meta_object = registry.get("enum_type")
        assert meta_object and meta_object.fields
        field = meta_object.fields[0]
        original = field.ui.col_span
        try:
            field.ui.col_span = 9
            config = view_config_service_module.view_config_service.build_detail_view_from_fields("enum_type")
            spans = {
                fid: span
                for facet in config.facets
                for fid, span in facet.col_span_map.items()
            }
            assert field.id not in spans

            field.ui.col_span = 2
            config = view_config_service_module.view_config_service.build_detail_view_from_fields("enum_type")
            spans = {
                fid: span
                for facet in config.facets
                for fid, span in facet.col_span_map.items()
            }
            assert spans.get(field.id) == 2
        finally:
            field.ui.col_span = original

    def test_form_section_gets_key_and_span_map(self):
        from meta.core.models import registry
        from meta.services import view_config_service as view_config_service_module

        meta_object = registry.get("enum_type")
        field = next(f for f in meta_object.fields if f.ui.editable)
        original = field.ui.col_span
        try:
            field.ui.col_span = 2
            config = view_config_service_module.view_config_service.build_form_view_from_fields("enum_type")
            assert all(section.key for section in config.sections)
            assert any(
                field.id in section.col_span_map for section in config.sections
            )
        finally:
            field.ui.col_span = original


class TestTabs:
    def test_tab_referencing_missing_section_dropped(self):
        from meta.core.yaml_loader import parse_ui_form_view_config

        config = parse_ui_form_view_config({
            "sections": [{"key": "basic", "title": "基本信息", "fields": ["a"]}],
            "tabs": [
                {"key": "ok", "label": "正常", "section_keys": ["basic"]},
                {"key": "bad", "label": "缺失", "section_keys": ["basic", "nope"]},
            ],
        })
        assert [tab.key for tab in config.tabs] == ["ok"]

    def test_section_without_key_is_none(self):
        from meta.core.yaml_loader import parse_ui_form_view_config

        config = parse_ui_form_view_config({"sections": [{"title": "基本信息", "fields": ["a"]}]})
        assert config.sections[0].key is None


class TestSchemaVersion:
    def test_fallback_is_stable_and_config_sensitive(self):
        from meta.core.models import UIFormSection, UIFormViewConfig, UIViewConfig
        from meta.services.view_config_service import _build_fallback_schema_version

        cfg_a = UIViewConfig(form=UIFormViewConfig(
            sections=[UIFormSection(title="A", fields=["f1"])],
        ))
        cfg_b = UIViewConfig(form=UIFormViewConfig(
            sections=[UIFormSection(title="A", fields=["f1", "f2"])],
        ))

        version_a1 = _build_fallback_schema_version("enum_type", cfg_a)
        version_a2 = _build_fallback_schema_version("enum_type", cfg_a)
        version_b = _build_fallback_schema_version("enum_type", cfg_b)

        assert len(version_a1) == 12
        assert version_a1 == version_a2
        assert version_a1 != version_b

    def test_get_or_build_view_config_sets_schema_version(self):
        from meta.services import view_config_service as view_config_service_module

        service = view_config_service_module.view_config_service
        config = service.get_or_build_view_config("enum_type")
        assert config.schema_version

        global_hash = view_config_service_module._compute_schema_dir_hash()
        if global_hash:
            assert config.schema_version == global_hash

    def test_schema_version_changes_after_schema_reload(self, monkeypatch):
        from meta.services import view_config_service as view_config_service_module

        service = view_config_service_module.view_config_service
        original = view_config_service_module._compute_schema_dir_hash
        try:
            monkeypatch.setattr(
                view_config_service_module, "_compute_schema_dir_hash", lambda: "aaaaaaaaaaaa"
            )
            first = service.get_or_build_view_config("enum_type").schema_version
            assert first == "aaaaaaaaaaaa"

            monkeypatch.setattr(
                view_config_service_module, "_compute_schema_dir_hash", lambda: "bbbbbbbbbbbb"
            )
            second = service.get_or_build_view_config("enum_type").schema_version
            assert second == "bbbbbbbbbbbb"
        finally:
            monkeypatch.setattr(
                view_config_service_module, "_compute_schema_dir_hash", original
            )