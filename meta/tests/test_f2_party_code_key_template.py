# -*- coding: utf-8 -*-
"""F2 · party 唯一识别号（code）+ key_template 编码规则测试 (2026-10-05)

依据: docs/superpowers/specs/2026-10-05-f2-party-relationship-naming-and-identifier.md
      (§9 D2/D3 拍板: 形式 PATY-{SEQ:8}; 编码统一走平台 key_template)

一手核对结论（本测试钉死）:
- 平台 key_template 的生成目标列**硬编码为 code**
  (interceptors/key_template_interceptor.py:69-98; key_template_engine.py:579-582)
  ⇒ 唯一识别号的**技术标识/物理列 = code**（界面词 = 身份主体编号）
- party **无父对象** ⇒ segments 不得含 parent_field
  (key_template_engine.py:496-524 对 parent_field 段强制非空校验)

覆盖:
1. YAML 声明 : party.yaml 含 code 字段（business_key / immutable / data_category）+ key_template 块
2. 红线     : key_template.segments 不含 parent_field；pattern 仅常量字面量 + {SEQ:n}
3. 建列     : sync_schema_from_meta 建出 parties.code 列（NOT NULL，随 required）
4. 编码生成 : KeyTemplateEngine.generate_code → PATY-00000001，且随已有记录递增为 ...0002

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db;
         DML 走 ds.insert API（本文件无裸写语句 —— conftest raw-SQL 守卫）
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

PREFIX = 'PATY-'

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_party_yaml():
    import yaml
    with open(os.path.join(_SCHEMA_DIR, 'party.yaml'), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture()
def party_ds(tmp_path):
    """临时库: 仅建 party 基表（含 code 列）"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file

    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party.yaml'))
    assert obj is not None, 'party.yaml 加载失败'

    ds = get_data_source("sqlite", database=str(tmp_path / 'f2_party_code.db'))
    sync_schema_from_meta(ds, [obj])
    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 1. YAML 声明（§9 D2）
# ────────────────────────────────────────
class TestPartyCodeField:
    def test_code_field_exists_with_semantics(self):
        fields = {f['id']: f for f in _load_party_yaml()['fields']}
        assert 'code' in fields, '唯一识别号字段（技术标识 code）缺失'
        code = fields['code']
        assert code['db_column'] == 'code'
        assert code['required'] is True
        assert code['unique'] is True
        assert code['semantics'].get('business_key') is True
        assert code['semantics'].get('immutable') is True
        assert code['semantics'].get('data_category') == 'code'

    def test_no_party_number_column(self):
        """平台 key_template 硬编码 code 列 ⇒ 不得另立 party_number 字段（否则永不被填充）"""
        fields = {f['id']: f for f in _load_party_yaml()['fields']}
        assert 'party_number' not in fields


# ────────────────────────────────────────
# 2. key_template 红线与形式（§9 D3）
# ────────────────────────────────────────
class TestKeyTemplateDeclaration:
    def test_enabled_and_form(self):
        kt = _load_party_yaml().get('key_template') or {}
        assert kt.get('enabled') is True
        assert kt.get('auto_suggest') is True
        assert kt.get('user_editable') == 'auto_or_manual'
        assert kt.get('pattern') == 'PATY-{SEQ:8}'
        assert kt.get('preview') == 'PATY-00000001'

    def test_redline_no_parent_field_segment(self):
        """party 无父对象 ⇒ 禁 parent_field 段（引擎强制非空校验）"""
        segs = (_load_party_yaml().get('key_template') or {}).get('segments', [])
        assert segs, 'segments 不应为空（需声明 sequence 段以启用 auto_detect）'
        assert all(s.get('type') != 'parent_field' for s in segs), \
            'party 无父对象，segments 不得含 parent_field'

    def test_sequence_segment_padding(self):
        segs = (_load_party_yaml().get('key_template') or {}).get('segments', [])
        seq = next(s for s in segs if s.get('type') == 'sequence')
        assert seq.get('padding') == 8
        assert seq.get('auto_detect') is True


# ────────────────────────────────────────
# 3. 建列（真实 schema）
# ────────────────────────────────────────
class TestCodeColumnCreated:
    def test_code_column_present(self, party_ds):
        cols = [c[1] for c in party_ds.execute("PRAGMA table_info(parties)").fetchall()]
        assert 'code' in cols


# ────────────────────────────────────────
# 4. 编码生成（端到端：引擎按 key_template 落 code）
# ────────────────────────────────────────
class TestCodeGeneration:
    def _engine_and_config(self, ds):
        from meta.core.key_template_engine import (
            KeyTemplateConfig, KeyTemplateEngine,
        )
        raw = _load_party_yaml()['key_template']
        cfg = KeyTemplateConfig.from_dict('party', raw)
        assert cfg.enabled and cfg.auto_suggest
        return KeyTemplateEngine(ds), cfg

    def test_first_code(self, party_ds):
        eng, cfg = self._engine_and_config(party_ds)
        code = eng.generate_code(cfg, {}, 'party',
                                 table_name='parties', prefix_filter=PREFIX)
        assert code == 'PATY-00000001'

    def test_second_code_increments(self, party_ds):
        eng, cfg = self._engine_and_config(party_ds)
        first = eng.generate_code(cfg, {}, 'party',
                                  table_name='parties', prefix_filter=PREFIX)
        party_ds.insert('parties', {
            'id': 1, 'name': '外部供应商A', 'party_type': 'organization',
            'code': first,
        })
        second = eng.generate_code(cfg, {}, 'party',
                                   table_name='parties', prefix_filter=PREFIX)
        assert second == 'PATY-00000002'