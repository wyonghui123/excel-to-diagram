# -*- coding: utf-8 -*-
"""编号序列（number_sequence）取号内核测试

依据: docs/superpowers/specs/2026-10-25-number-sequence-implementation-spec.md
      docs/superpowers/specs/2026-10-24-sales-order-wave0-detailed-plan.md §2.3

钉死的行为:
- pattern 单一真源（前缀 / 分隔符 / 日期段 / 流水位数全在 pattern）
- 日期令牌取业务日期，不用系统时钟；周期隔离由日期令牌派生
- 独立短事务取号：取号即提交、允许空号、不回填
- 字段 / 业务日期 / 分段字段缺值即报错，不生成裸号
- peek 不写状态；位数耗尽由 on_exhaust 决定

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db。
"""
import os
import sys
from datetime import date

import pytest
import yaml

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')
_YAML_PATH = os.path.join(_SCHEMA_DIR, 'number_sequence.yaml')
_DOC_TYPE_YAML_PATH = os.path.join(_SCHEMA_DIR, 'document_type.yaml')
# [对象级泛化 2026-10-25] document_types 是 type_definitions 的只读切片视图，
# 建视图前必须先有底层表。
_TYPE_DEF_YAML_PATH = os.path.join(_SCHEMA_DIR, 'type_definition.yaml')

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _raw(path=_YAML_PATH):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _config(**overrides):
    base = {
        'code': 'SO_STD',
        'name': '标准订单',
        'pattern': 'SO-{DATE:yyyymm}-{SEQ:6}',
        'scope_fields': None,
        'date_field': 'order_date',
        'start_value': 1,
        'on_exhaust': 'error',
    }
    base.update(overrides)
    return base


@pytest.fixture()
def seq_ds(tmp_path):
    """临时库：number_sequences + type_definitions + document_types 视图"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    ns_obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
    td_obj = load_yaml_file(_TYPE_DEF_YAML_PATH, aspects_defs=aspects)
    dt_obj = load_yaml_file(_DOC_TYPE_YAML_PATH, aspects_defs=aspects)
    assert ns_obj is not None and td_obj is not None and dt_obj is not None

    ds = get_data_source('sqlite', database=str(tmp_path / 'number_sequence.db'))
    # 顺序固定：底层表 → 视图
    sync_schema_from_meta(ds, [ns_obj, td_obj, dt_obj])
    yield ds
    _clear_data_source_cache_for_testing()


def _engine(ds):
    from meta.core.number_sequence_engine import NumberSequenceEngine
    return NumberSequenceEngine(ds)


# ────────────────────────────────────────
# T1 YAML 结构
# ────────────────────────────────────────
class TestSchemaDeclaration:
    def test_object_identity(self):
        d = _raw()
        assert d['id'] == 'number_sequence'
        assert d['table_name'] == 'number_sequences'
        assert d['display_name_field'] == 'name'

    def test_code_unique_immutable(self):
        fields = {f['id']: f for f in _raw()['fields']}
        code = fields['code']
        assert code['required'] is True
        assert code['unique'] is True
        assert code['semantics']['business_key'] is True
        assert code['semantics']['immutable'] is True
        assert code['semantics']['data_category'] == 'code'

    def test_pattern_single_source(self):
        fields = {f['id']: f for f in _raw()['fields']}
        assert fields['pattern']['required'] is True
        assert fields['pattern']['max_length'] == 80
        # 冗余投影不得复活
        for banned in ('prefix', 'date_pattern', 'separator', 'width',
                       'reset_policy', 'current_value', 'current_period'):
            assert banned not in fields

    def test_runtime_state_not_in_schema(self):
        fields = {f['id']: f for f in _raw()['fields']}
        assert 'current_value' not in fields
        assert fields['start_value']['default'] == 1

    def test_unique_index(self):
        idx = _raw().get('indexes') or []
        hits = [i for i in idx if i.get('name') == 'idx_number_sequence_code']
        assert len(hits) == 1
        assert hits[0]['unique'] is True
        assert hits[0]['fields'] == ['code']

    def test_restrict_on_type_definition(self):
        dp = _raw()['deletion_policy']
        assert dp['mode'] == 'restrict'
        hits = [r for r in dp['restrict_on']
                if r.get('table') == 'type_definitions']
        assert len(hits) == 1
        assert hits[0]['foreign_key'] == 'number_sequence_id'

    def test_skip_auto_menu(self):
        assert _raw()['ui_view_config']['skip_auto_menu'] is True

    def test_document_type_binding_field_nullable(self):
        fields = {f['id']: f for f in _raw(_DOC_TYPE_YAML_PATH)['fields']}
        f = fields['number_sequence_id']
        assert f['type'] == 'integer'
        assert f.get('nullable') is True
        assert f.get('required') is not True
        rel_ids = {r['id'] for r in (_raw(_DOC_TYPE_YAML_PATH).get('relations') or [])}
        assert 'document_type_to_number_sequence' in rel_ids


# ────────────────────────────────────────
# T2–T5 取号与周期
# ────────────────────────────────────────
class TestAllocate:
    def test_first_code(self, seq_ds):
        code = _engine(seq_ds).allocate(
            _config(), {}, {'order_date': date(2026, 10, 24)}
        )
        assert code == 'SO-202610-000001'

    def test_second_code_increments(self, seq_ds):
        eng = _engine(seq_ds)
        dates = {'order_date': date(2026, 10, 24)}
        first = eng.allocate(_config(), {}, dates)
        second = eng.allocate(_config(), {}, dates)
        assert (first, second) == ('SO-202610-000001', 'SO-202610-000002')

    def test_business_date_switches_period(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config()
        oct_code = eng.allocate(cfg, {}, {'order_date': date(2026, 10, 31)})
        nov_code = eng.allocate(cfg, {}, {'order_date': date(2026, 11, 1)})
        assert oct_code == 'SO-202610-000001'
        assert nov_code == 'SO-202611-000001'

    def test_no_date_token_never_resets(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config(code='QT_SEQ', pattern='QT-{SEQ:4}')
        values = [eng.allocate(cfg, {}, {'order_date': date(2026, 10, 1)})
                  for _ in range(3)]
        assert values == ['QT-0001', 'QT-0002', 'QT-0003']

    def test_start_value(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config(code='OFFSET_SEQ', pattern='OF-{SEQ:4}', start_value=100)
        assert eng.allocate(cfg) == 'OF-0100'

    def test_date_accepts_iso_string(self, seq_ds):
        code = _engine(seq_ds).allocate(
            _config(), {}, {'order_date': '2026-10-24T08:00:00'}
        )
        assert code == 'SO-202610-000001'

    def test_field_reference_uppercased(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config(code='FIELD_SEQ', pattern='SO-{type_code}-{SEQ:4}')
        code = eng.allocate(cfg, {'type_code': 'zor'})
        assert code == 'SO-ZOR-0001'


# ────────────────────────────────────────
# T6–T8 分段与缺值
# ────────────────────────────────────────
class TestScopeAndMissingValues:
    def test_scope_splits_counters(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config(code='ORG_SEQ', pattern='PO-{SEQ:4}',
                      scope_fields=['company_code'])
        a1 = eng.allocate(cfg, {'company_code': 'A'})
        b1 = eng.allocate(cfg, {'company_code': 'B'})
        a2 = eng.allocate(cfg, {'company_code': 'A'})
        assert (a1, b1, a2) == ('PO-0001', 'PO-0001', 'PO-0002')

    def test_scope_accepts_json_string(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config(code='ORG_JSON_SEQ', pattern='PJ-{SEQ:4}',
                      scope_fields='["company_code"]')
        assert eng.allocate(cfg, {'company_code': 'A'}) == 'PJ-0001'

    def test_scope_missing_value_raises(self, seq_ds):
        from meta.core.number_sequence_engine import NumberSequenceError
        eng = _engine(seq_ds)
        cfg = _config(code='ORG_MISS_SEQ', pattern='PM-{SEQ:4}',
                      scope_fields=['company_code'])
        with pytest.raises(NumberSequenceError):
            eng.allocate(cfg, {})

    def test_field_missing_value_raises(self, seq_ds):
        from meta.core.number_sequence_engine import NumberSequenceError
        eng = _engine(seq_ds)
        cfg = _config(code='FIELD_MISS_SEQ', pattern='SO-{type_code}-{SEQ:4}')
        with pytest.raises(NumberSequenceError):
            eng.allocate(cfg, {})

    def test_date_missing_raises(self, seq_ds):
        from meta.core.number_sequence_engine import NumberSequenceError
        eng = _engine(seq_ds)
        with pytest.raises(NumberSequenceError):
            eng.allocate(_config(), {}, {})


# ────────────────────────────────────────
# T9–T11 peek / 空号 / 耗尽
# ────────────────────────────────────────
class TestPeekAndExhaust:
    def test_peek_does_not_consume(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config(code='PEEK_SEQ', pattern='PK-{SEQ:4}')
        assert eng.peek(cfg) == 'PK-0001'
        assert eng.peek(cfg) == 'PK-0001'
        assert eng.allocate(cfg) == 'PK-0001'

    def test_gaps_are_kept(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config(code='GAP_SEQ', pattern='GP-{SEQ:4}')
        assert eng.allocate(cfg) == 'GP-0001'
        assert eng.allocate(cfg) == 'GP-0002'
        assert eng.peek(cfg) == 'GP-0003'
        # 模拟业务失败/跳号：直接多取两个，中间号不会被回填
        assert eng.allocate(cfg) == 'GP-0003'
        assert eng.allocate(cfg) == 'GP-0004'
        assert eng.peek(cfg) == 'GP-0005'

    def test_exhaust_error(self, seq_ds):
        from meta.core.number_sequence_engine import NumberSequenceError
        eng = _engine(seq_ds)
        cfg = _config(code='EXH_ERR_SEQ', pattern='EE-{SEQ:1}', start_value=9)
        assert eng.allocate(cfg) == 'EE-9'
        with pytest.raises(NumberSequenceError):
            eng.allocate(cfg)

    def test_exhaust_extend(self, seq_ds):
        eng = _engine(seq_ds)
        cfg = _config(code='EXH_EXT_SEQ', pattern='EX-{SEQ:1}',
                      start_value=9, on_exhaust='extend')
        assert eng.allocate(cfg) == 'EX-9'
        assert eng.allocate(cfg) == 'EX-10'


# ────────────────────────────────────────
# T12 pattern 结构非法
# ────────────────────────────────────────
class TestPatternValidation:
    @pytest.mark.parametrize('pattern', [
        '',
        'SO-{DATE:yyyymm}',                 # 无 SEQ
        'SO-{SEQ:4}-{SEQ:4}',               # 多 SEQ
        'SO-{SEQ:0}',                       # padding 非正
        'SO-{DATE:yyyy-mm}-{SEQ:4}',        # 日期格式非法
        'SO-{FOO:1}-{SEQ:4}',               # 未知令牌
    ])
    def test_invalid_patterns(self, seq_ds, pattern):
        from meta.core.number_sequence_engine import NumberSequenceError
        eng = _engine(seq_ds)
        with pytest.raises(NumberSequenceError):
            eng.validate_pattern(pattern)

    def test_valid_pattern_reports_fields_and_padding(self, seq_ds):
        info = _engine(seq_ds).validate_pattern(
            'SO-{type_code}-{DATE:yyyymmdd}-{SEQ:6}'
        )
        assert info['padding'] == 6
        assert info['fields'] == ['type_code']
        assert info['has_date'] is True


# ────────────────────────────────────────
# T13 嵌套事务拒绝
# ────────────────────────────────────────
class TestTransactionContract:
    def test_reject_inside_outer_transaction(self, seq_ds):
        from meta.core.number_sequence_engine import NumberSequenceError
        eng = _engine(seq_ds)
        cfg = _config(code='TX_SEQ', pattern='TX-{SEQ:4}')
        with seq_ds.transaction():
            with pytest.raises(NumberSequenceError):
                eng.allocate(cfg)


# ────────────────────────────────────────
# T14 物理表结构
# ────────────────────────────────────────
class TestPhysicalTables:
    def test_number_sequences_columns(self, seq_ds):
        cols = [c[1] for c in seq_ds.execute(
            'PRAGMA table_info(number_sequences)').fetchall()]
        # updated_at 是 audit_aspect 的虚拟列（storage: virtual），不落物理表
        for expected in ('id', 'code', 'name', 'pattern', 'scope_fields',
                         'date_field', 'start_value', 'on_exhaust',
                         'preview', 'status', 'description', 'created_at'):
            assert expected in cols, '缺失列 %s' % expected

    def test_document_type_binding_column(self, seq_ds):
        cols = [c[1] for c in seq_ds.execute(
            'PRAGMA table_info(document_types)').fetchall()]
        assert 'number_sequence_id' in cols

    def test_sequences_state_table_created(self, seq_ds):
        _engine(seq_ds)  # 状态表由内核初始化时幂等创建
        cols = [c[1] for c in seq_ds.execute(
            'PRAGMA table_info(_sequences)').fetchall()]
        assert 'sequence_name' in cols
        assert 'current_value' in cols
