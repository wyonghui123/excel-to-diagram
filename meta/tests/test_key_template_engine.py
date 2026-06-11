import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
import pytest
import os
import tempfile
from meta.core.key_template_engine import (
    KeyTemplateParser,
    KeyTemplateConfig,
    SequenceEngine,
    KeyTemplateEngine,
)
from meta.core.datasource import get_data_source


class TestKeyTemplateParser:

    def setup_method(self):
        self.parser = KeyTemplateParser()

    def test_parse_simple_pattern(self):
        tokens = self.parser.parse("{field}_{SEQ:4}")
        assert len(tokens) == 3
        assert tokens[0] == {"type": "field", "name": "field"}
        assert tokens[1] == {"type": "separator", "value": "_"}
        assert tokens[2] == {"type": "sequence", "padding": 4}

    def test_parse_multi_field_pattern(self):
        tokens = self.parser.parse("{source_code}-{target_code}-{SEQ:2}")
        assert len(tokens) == 5
        assert tokens[0] == {"type": "field", "name": "source_code"}
        assert tokens[1] == {"type": "separator", "value": "-"}
        assert tokens[2] == {"type": "field", "name": "target_code"}
        assert tokens[3] == {"type": "separator", "value": "-"}
        assert tokens[4] == {"type": "sequence", "padding": 2}

    def test_parse_literal_text(self):
        tokens = self.parser.parse("PO_{SEQ:5}")
        assert len(tokens) == 4
        assert tokens[0] == {"type": "literal", "value": "P"}
        assert tokens[1] == {"type": "literal", "value": "O"}
        assert tokens[2] == {"type": "separator", "value": "_"}
        assert tokens[3] == {"type": "sequence", "padding": 5}

    def test_parse_no_sequence(self):
        tokens = self.parser.parse("{module}_{category}")
        assert len(tokens) == 3
        assert tokens[0] == {"type": "field", "name": "module"}
        assert tokens[1] == {"type": "separator", "value": "_"}
        assert tokens[2] == {"type": "field", "name": "category"}

    def test_parse_dot_separator(self):
        tokens = self.parser.parse("{prefix}.{SEQ:3}")
        assert tokens[1]["value"] == "."

    def test_parse_slash_separator(self):
        tokens = self.parser.parse("{prefix}/{SEQ:3}")
        assert tokens[1]["value"] == "/"

    def test_parse_colon_separator(self):
        tokens = self.parser.parse("{prefix}:{SEQ:3}")
        assert tokens[1]["value"] == ":"

    def test_parse_empty_pattern(self):
        tokens = self.parser.parse("")
        assert len(tokens) == 0

    def test_parse_no_placeholders(self):
        tokens = self.parser.parse("ABC-DEF")
        assert len(tokens) == 7

    def test_resolve_basic(self):
        tokens = self.parser.parse("{service_module_code}_{SEQ:4}")
        code = self.parser.resolve(
            tokens,
            {"service_module_code": "ORDER_SVC"},
            sequence_value=1
        )
        assert code == "ORDER_SVC_0001"

    def test_resolve_multi_field(self):
        tokens = self.parser.parse("{source_code}-{target_code}-{SEQ:2}")
        code = self.parser.resolve(
            tokens,
            {"source_code": "ORDER", "target_code": "USER"},
            sequence_value=3
        )
        assert code == "ORDER-USER-03"

    def test_resolve_field_uppercase(self):
        tokens = self.parser.parse("{code}_{SEQ:2}")
        code = self.parser.resolve(
            tokens,
            {"code": "order_svc"},
            sequence_value=5
        )
        assert code == "ORDER_SVC_05"

    def test_resolve_missing_field(self):
        tokens = self.parser.parse("{code}_{SEQ:2}")
        code = self.parser.resolve(
            tokens,
            {},
            sequence_value=1
        )
        assert code == "_01"

    def test_resolve_no_padding(self):
        tokens = self.parser.parse("{SEQ:0}")
        code = self.parser.resolve(tokens, {}, 42)
        assert code == "42"

    def test_build_scope_key_single(self):
        segments = [
            {"type": "parent_field", "source": "service_module_code"}
        ]
        scope = self.parser.build_scope_key(
            segments,
            {"service_module_code": "ORDER_SVC"},
            "default"
        )
        assert scope == "ORDER_SVC"

    def test_build_scope_key_multi(self):
        segments = [
            {"type": "parent_field", "source": "source_code"},
            {"type": "parent_field", "source": "target_code"}
        ]
        scope = self.parser.build_scope_key(
            segments,
            {"source_code": "ORDER", "target_code": "USER"},
            "default"
        )
        assert scope == "ORDER:USER"

    def test_build_scope_key_no_parent(self):
        segments = [
            {"type": "sequence", "name": "my_seq"}
        ]
        scope = self.parser.build_scope_key(segments, {}, "default")
        assert scope == "default"

    def test_build_scope_key_empty_value(self):
        segments = [
            {"type": "parent_field", "source": "non_existent"}
        ]
        scope = self.parser.build_scope_key(segments, {}, "fallback")
        assert scope == "fallback"


class TestKeyTemplateConfig:

    def test_from_dict_enabled(self):
        data = {
            "enabled": True,
            "auto_suggest": True,
            "pattern": "{code}_{SEQ:4}",
            "separator": "_",
            "segments": [],
            "preview": "CODE_0001"
        }
        config = KeyTemplateConfig.from_dict("test_obj", data)
        assert config.enabled is True
        assert config.auto_suggest is True
        assert config.pattern == "{code}_{SEQ:4}"
        assert config.object_id == "test_obj"

    def test_from_dict_disabled(self):
        config = KeyTemplateConfig.from_dict("test_obj", {"enabled": False})
        assert config.enabled is False

    def test_from_dict_empty(self):
        config = KeyTemplateConfig.from_dict("test_obj", {})
        assert config.enabled is False

    def test_from_dict_none(self):
        config = KeyTemplateConfig.from_dict("test_obj", None)
        assert config.enabled is False


class TestSequenceEngine:

    def setup_method(self):
        self.db_path = os.path.join(tempfile.gettempdir(), f"test_kt_{os.getpid()}.db")
        self.ds = get_data_source("sqlite", database=self.db_path)
        self.engine = SequenceEngine(self.ds)

    def teardown_method(self):
        try:
            self.ds.disconnect()
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_next_value_basic(self):
        val = self.engine.next_value("test_seq")
        assert val >= 1

    def test_next_value_increments(self):
        v1 = self.engine.next_value("increment_test")
        v2 = self.engine.next_value("increment_test")
        assert v2 == v1 + 1

    def test_next_value_isolated_sequences(self):
        v1 = self.engine.next_value("seq_a")
        v2 = self.engine.next_value("seq_b")
        assert v1 >= 1
        assert v2 >= 1

    def test_next_value_with_start(self):
        val = self.engine.next_value("start_test", start=100)
        assert val == 100

    def test_next_value_wraps_correctly(self):
        self.engine.next_value("wrap_test", start=5)
        v2 = self.engine.next_value("wrap_test", start=5)
        assert v2 == 6

    def test_reset_sequence(self):
        self.engine.next_value("reset_test")
        self.engine.next_value("reset_test")
        self.engine.reset_sequence("reset_test")
        val = self.engine.next_value("reset_test")
        assert val == 1

    def test_auto_detect_start_empty_table(self):
        self.ds.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, code TEXT)")
        self.ds.commit()
        start = self.engine.auto_detect_start("kt", "test_table", "code")
        assert start == 1


class TestKeyTemplateEngine:

    def setup_method(self):
        self.db_path = os.path.join(tempfile.gettempdir(), f"test_kt_engine_{os.getpid()}.db")
        self.ds = get_data_source("sqlite", database=self.db_path)
        self.engine = KeyTemplateEngine(self.ds)

    def teardown_method(self):
        try:
            self.ds.disconnect()
            os.unlink(self.db_path)
        except Exception:
            pass

    def _make_config(self, **kwargs):
        defaults = {
            "enabled": True,
            "auto_suggest": True,
            "pattern": "{service_module_code}_{SEQ:4}",
            "separator": "_",
            "segments": [
                {"type": "parent_field", "source": "service_module_code"},
                {"type": "separator", "value": "_"},
                {"type": "sequence", "name": "bo_seq", "scope": "service_module_code",
                 "auto_detect": False, "padding": 4, "start": 1}
            ]
        }
        defaults.update(kwargs)
        return KeyTemplateConfig.from_dict("test_obj", defaults)

    def test_generate_code_disabled(self):
        config = KeyTemplateConfig.from_dict("test_obj", {"enabled": False})
        code = self.engine.generate_code(config, {}, "test_obj")
        assert code is None

    def test_generate_code_empty_pattern(self):
        config = KeyTemplateConfig.from_dict("test_obj", {"enabled": True, "pattern": ""})
        code = self.engine.generate_code(config, {}, "test_obj")
        assert code is None

    def test_generate_code_basic(self):
        config = self._make_config()
        code = self.engine.generate_code(
            config,
            {"service_module_code": "ORDER_SVC"},
            "business_object"
        )
        assert code is not None
        assert code.startswith("ORDER_SVC_")
        assert len(code) == len("ORDER_SVC_0001")

    def test_generate_code_increments(self):
        config = self._make_config()
        code1 = self.engine.generate_code(
            config, {"service_module_code": "ORDER_SVC"}, "test_obj"
        )
        code2 = self.engine.generate_code(
            config, {"service_module_code": "ORDER_SVC"}, "test_obj"
        )
        assert code1 != code2
        num1 = int(code1.split("_")[-1])
        num2 = int(code2.split("_")[-1])
        assert num2 == num1 + 1

    def test_generate_code_scoped_sequences(self):
        config = self._make_config()
        code_a = self.engine.generate_code(
            config, {"service_module_code": "MODULE_A"}, "test_obj"
        )
        code_b = self.engine.generate_code(
            config, {"service_module_code": "MODULE_B"}, "test_obj"
        )
        assert code_a.startswith("MODULE_A_")
        assert code_b.startswith("MODULE_B_")
        assert code_a.endswith("0001")
        assert code_b.endswith("0001")

    def test_preview_code(self):
        config = self._make_config()
        code = self.engine.preview_code(
            config, {"service_module_code": "ORDER_SVC"}
        )
        assert code == "ORDER_SVC_0001"

    def test_preview_code_no_field(self):
        """[UPDATED 2026-06-11] parent_field 值缺失 → 返回 None（拒绝生成裸序列号）"""
        config = self._make_config()
        code = self.engine.preview_code(config, {})
        assert code is None, (
            f"parent_field 缺失时应返回 None（不生成裸序列号），实际: {code}"
        )

    def test_validate_parent_fields_all_present(self):
        """[NEW 2026-06-11] 所有 parent_field 值存在 → 返回 True"""
        config = self._make_config()
        field_values = {"service_module_code": "PUM"}
        assert self.engine._validate_parent_fields(config.segments, field_values) is True

    def test_validate_parent_fields_one_missing(self):
        """[NEW 2026-06-11] 一个 parent_field 值缺失 → 返回 False"""
        config = self._make_config()
        assert self.engine._validate_parent_fields(config.segments, {}) is False

    def test_validate_parent_fields_empty_value(self):
        """[NEW 2026-06-11] parent_field 值为空字符串 → 返回 False"""
        config = self._make_config()
        assert self.engine._validate_parent_fields(config.segments, {"service_module_code": ""}) is False

    def test_validate_parent_fields_multi_all_present(self):
        """[NEW 2026-06-11] 多个 parent_field 全部存在 → 返回 True"""
        config = KeyTemplateConfig.from_dict("rel", {
            "enabled": True,
            "pattern": "{source_code}-{target_code}-{SEQ:2}",
            "segments": [
                {"type": "parent_field", "source": "source_code"},
                {"type": "separator", "value": "-"},
                {"type": "parent_field", "source": "target_code"},
                {"type": "separator", "value": "-"},
                {"type": "sequence", "name": "rel_seq", "scope": "source_code,target_code",
                 "auto_detect": False, "padding": 2, "start": 1}
            ]
        })
        field_values = {"source_code": "ORDER", "target_code": "USER"}
        assert self.engine._validate_parent_fields(config.segments, field_values) is True

    def test_validate_parent_fields_multi_one_missing(self):
        """[NEW 2026-06-11] 多个 parent_field 中一个缺失 → 返回 False"""
        config = KeyTemplateConfig.from_dict("rel", {
            "enabled": True,
            "pattern": "{source_code}-{target_code}-{SEQ:2}",
            "segments": [
                {"type": "parent_field", "source": "source_code"},
                {"type": "separator", "value": "-"},
                {"type": "parent_field", "source": "target_code"},
                {"type": "separator", "value": "-"},
                {"type": "sequence", "name": "rel_seq", "scope": "source_code,target_code",
                 "auto_detect": False, "padding": 2, "start": 1}
            ]
        })
        field_values = {"source_code": "ORDER"}  # target_code 缺失
        assert self.engine._validate_parent_fields(config.segments, field_values) is False

    def test_generate_code_rejects_missing_parent_field(self):
        """[NEW 2026-06-11] parent_field 缺失时 generate_code 返回 None（不生成裸序列号）"""
        config = self._make_config()
        code = self.engine.generate_code(config, {}, "test_obj")
        assert code is None, (
            f"parent_field 缺失时应返回 None，实际: {code}"
        )

    def test_preview_code_rejects_missing_parent_field(self):
        """[NEW 2026-06-11] parent_field 缺失时 preview_code 返回 None"""
        config = self._make_config()
        code = self.engine.preview_code(config, {"service_module_code": ""})
        assert code is None, (
            f"parent_field 值为空时应返回 None，实际: {code}"
        )

    def test_generate_code_multi_field_pattern(self):
        config = KeyTemplateConfig.from_dict("rel", {
            "enabled": True,
            "pattern": "{source_code}-{target_code}-{SEQ:2}",
            "segments": [
                {"type": "parent_field", "source": "source_code"},
                {"type": "separator", "value": "-"},
                {"type": "parent_field", "source": "target_code"},
                {"type": "separator", "value": "-"},
                {"type": "sequence", "name": "rel_seq", "scope": "source_code",
                 "auto_detect": False, "padding": 2, "start": 1}
            ]
        })
        code = self.engine.generate_code(
            config,
            {"source_code": "ORDER", "target_code": "USER"},
            "relationship"
        )
        assert code is not None
        assert code.startswith("ORDER-USER-")
        assert code.endswith("01")

    def test_get_sequence_engine(self):
        se = self.engine.get_sequence_engine()
        assert isinstance(se, SequenceEngine)