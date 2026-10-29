import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
[B9 计划行行号友好显示] EnrichmentEngine.enrich_fk_display_names 显示格式套用测试

覆盖:
1. 前缀型模板 "行 {line_no}" + display_field=line_no → "行 10"
2. 多字段模板 "{code} - {name}" → 不套用（仍为裸 display_field 值）
3. FK 值为 None → 输出 None
4. 显示字段值取不到（占位符键缺失）→ 安全回退 None，不抛异常
5. 模板为空 / 无 presentation → 不套用
"""

from types import SimpleNamespace
from unittest.mock import patch


def _make_field(field_id='line_id', display_field='line_no', display_format='行 {line_no}'):
    source = SimpleNamespace(
        type='bo',
        target_bo='sales_order_line',
        display_field=display_field,
        code_field=display_field,
        value_field='id',
        apply_target_permissions=True,
    )
    presentation = SimpleNamespace(result_type='dropdown', display_format=display_format)
    value_help = SimpleNamespace(source=source, behavior=SimpleNamespace(multiple=False),
                                 presentation=presentation)
    return SimpleNamespace(id=field_id, value_help=value_help)


def _make_meta(*fields):
    return SimpleNamespace(id='sales_order_schedule', table_name='sales_order_schedule',
                           fields=list(fields))


class _FakeCursor:

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDataSource:

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _FakeCursor(self.rows)


def _enrich(records, field, rows, table_name='sales_order_line', ds=None):
    from meta.core.enrichment_engine import EnrichmentEngine
    from meta.core.models import registry as meta_registry

    target_meta = SimpleNamespace(table_name=table_name)
    ds = ds or _FakeDataSource(rows)
    engine = EnrichmentEngine(ds, registry=None)
    with patch.object(meta_registry, 'get', return_value=target_meta):
        return engine.enrich_fk_display_names(_make_meta(field), records)


# ============================================================
# 前置型模板套用
# ============================================================

class TestPrefixDisplayFormat:

    def test_prefix_format_applied(self):
        field = _make_field(display_format='行 {line_no}')
        record = {'line_id': 67}
        records = _enrich([record], field, [(67, '10')])
        assert records[0]['line_id_display'] == '行 10'

    def test_single_record_dict_input(self):
        field = _make_field(display_format='行 {line_no}')
        record = {'line_id': 67}
        result = _enrich(record, field, [(67, '10')])
        assert result['line_id_display'] == '行 10'

    def test_no_literal_prefix_still_applied(self):
        field = _make_field(display_format='{line_no}')
        record = {'line_id': 67}
        records = _enrich([record], field, [(67, '10')])
        assert records[0]['line_id_display'] == '10'

    def test_non_string_display_value(self):
        field = _make_field(display_format='行 {line_no}')
        record = {'line_id': 67}
        records = _enrich([record], field, [(67, 10)])
        assert records[0]['line_id_display'] == '行 10'


# ============================================================
# 不套用的场景（回归面）
# ============================================================

class TestFormatNotApplied:

    def test_multi_field_format_not_applied(self):
        field = _make_field(display_format='{code} - {name}')
        record = {'line_id': 67}
        records = _enrich([record], field, [(67, '10')])
        assert records[0]['line_id_display'] == '10'

    def test_template_referencing_other_field_not_applied(self):
        field = _make_field(display_format='{code}')
        record = {'line_id': 67}
        records = _enrich([record], field, [(67, '10')])
        assert records[0]['line_id_display'] == '10'

    def test_empty_format_not_applied(self):
        field = _make_field(display_format='')
        record = {'line_id': 67}
        records = _enrich([record], field, [(67, '10')])
        assert records[0]['line_id_display'] == '10'

    def test_missing_presentation_not_applied(self):
        field = _make_field()
        field.value_help.presentation = None
        record = {'line_id': 67}
        records = _enrich([record], field, [(67, '10')])
        assert records[0]['line_id_display'] == '10'


# ============================================================
# 空值 / 缺失键安全回退
# ============================================================

class TestNullAndMissing:

    def test_fk_value_none_yields_none(self):
        field = _make_field(display_format='行 {line_no}')
        records = [{'line_id': 67}, {'line_id': None}]
        result = _enrich(records, field, [(67, '10')])
        assert result[0]['line_id_display'] == '行 10'
        assert result[1]['line_id_display'] is None

    def test_all_fk_values_none_skips_enrichment(self):
        # 整批无 FK 值时保持原状（不注入 display 键），不新增查询
        field = _make_field(display_format='行 {line_no}')
        ds = _FakeDataSource([(67, '10')])
        record = {'line_id': None}
        _enrich([record], field, None, ds=ds)
        assert ds.calls == []
        assert 'line_id_display' not in record

    def test_fk_value_missing_in_display_map(self):
        field = _make_field(display_format='行 {line_no}')
        record = {'line_id': 999}
        records = _enrich([record], field, [(67, '10')])
        assert records[0]['line_id_display'] is None

    def test_sql_still_only_selects_id_and_display_field(self):
        field = _make_field(display_format='行 {line_no}')
        ds = _FakeDataSource([(67, '10')])
        _enrich([{'line_id': 67}], field, None, ds=ds)
        # 未新增查询、未扩展 SELECT 列（仍为 id + display_field）
        assert len(ds.calls) == 1
        sql, params = ds.calls[0]
        assert sql == 'SELECT id, line_no FROM sales_order_line WHERE id IN (?)'
        assert params == [67]


# ============================================================
# 私有格式化函数直测
# ============================================================

class TestApplySingleTokenDisplayFormat:

    def test_applies_single_token(self):
        from meta.core.enrichment_engine import _apply_single_token_display_format
        assert _apply_single_token_display_format('10', 'line_no', '行 {line_no}') == '行 10'

    def test_rejects_multi_token(self):
        from meta.core.enrichment_engine import _apply_single_token_display_format
        assert _apply_single_token_display_format('10', 'name', '{code} - {name}') == '10'

    def test_rejects_empty_format(self):
        from meta.core.enrichment_engine import _apply_single_token_display_format
        assert _apply_single_token_display_format('10', 'line_no', '') == '10'

    def test_none_value_returns_none(self):
        from meta.core.enrichment_engine import _apply_single_token_display_format
        assert _apply_single_token_display_format(None, 'line_no', '行 {line_no}') is None

    def test_format_error_falls_back_to_raw_value(self):
        from meta.core.enrichment_engine import _apply_single_token_display_format

        class _BadFormat:
            def __format__(self, spec):
                raise TypeError('unsupported format')

        sentinel = _BadFormat()  # __format__ 抛错 ⇒ 回退原值
        value = _apply_single_token_display_format(sentinel, 'line_no', '行 {line_no}')
        assert value is sentinel
