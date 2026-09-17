# -*- coding: utf-8 -*-
"""
[FILE] test_dim_scope_bizkey.py
[DESCRIPTION] Spec 20 维度范围业务键锚定 单元测试 (数据构建经 factories/ 白名单)

[覆盖场景]
  1. _resolve_bizkeys 跨版本解析 (同 code 多 ID)
  2. 锚点 0 命中检测
  3. 开关 DIM_SCOPE_BIZKEY_ENABLED
  4. expand_detail: native/anchors/failed 分离
  5. chain 链尾锚点子查询 + 单引号转义
  6. derive_data_conditions 动态 SQL (G2 铁证见 TestG2DynamicAcceptance)
  7. fail-closed: 锚点失败 → 1=0
  8. 回归: 纯数字/wildcard/all/exclude 行为不变
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ['TEST_ENTRY'] = '1'  # 绕过 conftest 硬阻断

import pytest

from meta.services.dimension_scope_engine import DimensionScopeEngine
from meta.tests.factories._dimension_scope_engine_helpers import (
    make_dim_scope_engine_ds,
)
from meta.tests.factories._spec20_bizkey_helpers import (
    seed_bizkey_data,
    add_scope,
    insert_domain,
    insert_version,
    insert_sub_domain,
    query_ids,
)


@pytest.fixture
def ds():
    for ds_obj in make_dim_scope_engine_ds():
        seed_bizkey_data(ds_obj)
        yield ds_obj


def engine(ds) -> DimensionScopeEngine:
    return DimensionScopeEngine(ds)


class TestResolveBizkeys:
    def test_cross_version_resolution(self, ds):
        result = engine(ds)._resolve_bizkeys('domain', ['SCM'])
        assert set(result['SCM']) == {64, 88, 90}  # 跨 3 版本全部命中

    def test_unresolved_code(self, ds):
        result = engine(ds)._resolve_bizkeys('domain', ['NOPE'])
        assert result['NOPE'] == set()

    def test_unknown_dim_returns_empty(self, ds):
        assert engine(ds)._resolve_bizkeys('nonexistent', ['SCM']) == {}


class TestBizkeyFlag:
    def test_default_off(self, ds, monkeypatch):
        monkeypatch.delenv('DIM_SCOPE_BIZKEY_ENABLED', raising=False)
        assert DimensionScopeEngine._bizkey_enabled() is False

    def test_enabled_via_env(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        assert DimensionScopeEngine._bizkey_enabled() is True


class TestExpandDetail:
    def test_native_and_anchors_separated(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', [70, 'SCM'])
        expanded, native, anchors, inherited, failed = engine(ds).expand_dimension_values_detail(1)
        assert native['domain'] == {70}
        assert anchors['domain'] == {'SCM'}
        # expanded 含锚点解析快照 (旧消费方兼容) + 数字
        assert expanded['domain'] == {70, 64, 88, 90}
        assert failed.get('domain') is None

    def test_unresolved_anchor_marked_failed(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', ['SCM', 'TYPO_X'])
        expanded, native, anchors, inherited, failed = engine(ds).expand_dimension_values_detail(1)
        assert failed['domain'] == {'TYPO_X'}   # 混合: 部分失败 → 整体标失败 (严格模式)
        assert 'domain' not in anchors

    def test_flag_off_fails_closed(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '0')
        add_scope(ds, 1, 'domain', ['SCM'])
        expanded, native, anchors, inherited, failed = engine(ds).expand_dimension_values_detail(1)
        assert failed['domain'] == {'SCM'}
        assert not anchors.get('domain')
        assert 'domain' not in expanded

    def test_legacy_expand_unchanged_signature(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '0')
        add_scope(ds, 1, 'domain', [70])
        assert engine(ds).expand_dimension_values(1) == {'domain': {70}}

    def test_anchor_inherit_children_snapshot(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', ['SCM'], inherit=1)
        expanded, native, anchors, inherited, failed = engine(ds).expand_dimension_values_detail(1)
        # 锚点继承产物进 expanded (旧消费方) 且记入 inherited_from_anchor (SQL 侧动态化用)
        assert expanded['sub_domain'] == {301, 302}
        assert inherited['sub_domain']['domain'] == {301, 302}

    def test_numeric_inherit_not_marked_inherited(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', [64], inherit=1)
        expanded, native, anchors, inherited, failed = engine(ds).expand_dimension_values_detail(1)
        assert expanded['sub_domain'] == {301, 302}
        assert 'sub_domain' not in inherited   # 数字继承是快照语义 (G4 不变)


class TestChainAnchor:
    def test_chain_tail_embeds_code_subquery(self, ds):
        add_scope(ds, 1, 'domain', ['SCM'], inherit=0)
        # business_object 沿链追溯到 domain (leaf=service_module_id)
        cond = engine(ds)._build_chain_condition(
            'business_object', 'domain', [], anchor_codes=['SCM'])
        assert cond is not None
        assert "code IN ('SCM')" in cond
        # 完整链: BO.service_module_id → service_modules → sub_domains → domains
        assert 'domains' in cond and 'sub_domains' in cond and 'service_modules' in cond
        # 不含任何数字快照
        assert ' 64' not in cond and ' 88' not in cond

    def test_chain_mixed_native_and_anchor(self, ds):
        cond = engine(ds)._build_chain_condition(
            'business_object', 'domain', [70], anchor_codes=['SCM'])
        assert 'id IN (70)' in cond
        assert "code IN ('SCM')" in cond

    def test_quote_escaping(self, ds):
        cond = engine(ds)._build_chain_condition(
            'business_object', 'domain', [], anchor_codes=["SCM'--"])
        assert "''" in cond          # 单引号已翻倍转义
        assert "SCM'--" not in cond  # 原始未转义串不出现

    def test_no_inputs_returns_none(self, ds):
        assert engine(ds)._build_chain_condition('business_object', 'domain', []) is None


class TestDeriveConditions:
    def test_pure_anchor_domain_self_direct(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', ['SCM'], inherit=0)
        conds = engine(ds).derive_data_conditions(1)
        c = conds.get('domain', '')
        assert "code IN ('SCM')" in c and ' 64' not in c and ' 88' not in c

    def test_anchor_inherit_subdomain_dynamic(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', ['SCM'], inherit=1)
        conds = engine(ds).derive_data_conditions(1)
        c = conds.get('sub_domain', '')
        # 动态: 沿父 FK 子查询, 不含子快照 ID
        assert 'domain_id IN' in c and "code IN ('SCM')" in c
        assert '301' not in c and '302' not in c

    def test_anchor_fail_closed(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', ['TYPO_X'], inherit=0)
        conds = engine(ds).derive_data_conditions(1)
        assert conds.get('domain') == '1 = 0'

    def test_mixed_native_anchor_or(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', [70, 'SCM'], inherit=0)
        conds = engine(ds).derive_data_conditions(1)
        c = conds.get('domain', '')
        assert 'id IN (70)' in c and "code IN ('SCM')" in c

    def test_numeric_golden_regression(self, ds, monkeypatch):
        """G4: 纯数字 scope 生成 SQL 与旧逻辑完全一致 (基准经改动前探针实测)"""
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '0')
        add_scope(ds, 1, 'domain', [64], inherit=1)
        conds = engine(ds).derive_data_conditions(1)
        # 向上展开 version={10} 经 yaml binding 生成 version_id 条件 (既有行为)
        assert conds.get('domain') == 'id = 64 AND version_id = 10'
        # 旧版: inherit 展开快照 + domain binding (实测基准, version 注入块只认 original_expanded)
        assert conds.get('sub_domain') == 'domain_id = 64 AND id IN (301,302)'

    def test_wildcard_regression(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '0')
        add_scope(ds, 1, 'domain', ['*'], inherit=1)
        conds = engine(ds).derive_data_conditions(1)
        assert '64' in conds.get('domain', '') and '88' in conds.get('domain', '')


class TestG2DynamicAcceptance:
    def test_new_version_domain_auto_covered(self, ds, monkeypatch):
        """G2 铁证: derive 的 SQL 不含新 ID, 但插入新版本 SCM 后执行命中

        模拟时序:
          t1: PS 配 domain 锚点 SCM → derive → 记录 SQL
          t2: 新建版本 v03 + domains(id=120, code='SCM')  ← 不 re-derive
          t3: 直接执行 t1 的 SQL → 命中 120  ← 动态性的证明
        """
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', ['SCM'], inherit=1)
        eng = engine(ds)
        conds = eng.derive_data_conditions(1)
        sql_at_t1 = conds['domain']

        # t2: 新版本新域 (模拟版本升级, 不调用 derive)
        insert_version(ds, 12, 'v3', 'v03', 1)
        insert_domain(ds, 120, 'SCM', '供应链云', 12)

        # t3: SQL 字符串不变, 执行结果覆盖新域
        rows = ds.execute(f"SELECT id FROM domains WHERE {sql_at_t1}").fetchall()
        ids = {r[0] for r in rows}
        assert {64, 88, 90, 120} <= ids
        assert 70 not in ids          # FIN 不误命中

    def test_subdomain_of_new_version_covered(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        add_scope(ds, 1, 'domain', ['SCM'], inherit=1)
        eng = engine(ds)
        conds = eng.derive_data_conditions(1)
        sql_sub = conds['sub_domain']
        insert_version(ds, 12, 'v3', 'v03', 1)
        insert_domain(ds, 120, 'SCM', '供应链云', 12)
        insert_sub_domain(ds, 401, 'SCM_SALE', '销售', 120)
        rows = ds.execute(f"SELECT id FROM sub_domains WHERE {sql_sub}").fetchall()
        ids = {r[0] for r in rows}
        assert 401 in ids and 301 in ids


class TestApiPreflight:
    """[Spec 20 Task 8] API 保存预检: 锚点白名单校验 + 0 命中 warning"""

    def test_reject_injection_chars(self):
        from meta.api.permission_set_dimension_scope_api import _validate_anchor_codes
        ok, err = _validate_anchor_codes(["SCM'; DROP TABLE x--"])
        assert not ok and '非法字符' in err

    def test_allow_normal_code(self):
        from meta.api.permission_set_dimension_scope_api import _validate_anchor_codes
        ok, err = _validate_anchor_codes(['SCM', 'SCM_PL-1.2'])
        assert ok and err == ''

    def test_allow_wildcard_and_numeric(self):
        from meta.api.permission_set_dimension_scope_api import _validate_anchor_codes
        ok, err = _validate_anchor_codes(['*', 13, '-1'])
        assert ok and err == ''

    def test_unresolved_warning_not_blocking(self, ds):
        from meta.api.permission_set_dimension_scope_api import _preflight_anchor_warnings
        warnings = _preflight_anchor_warnings(ds, 1, 'domain', ['TYPO_X'])
        assert warnings and '未解析到' in warnings[0]

    def test_resolved_no_warning(self, ds):
        from meta.api.permission_set_dimension_scope_api import _preflight_anchor_warnings
        warnings = _preflight_anchor_warnings(ds, 1, 'domain', ['SCM'])
        assert warnings == []


# ============================================================================
# [Spec 20 Task 9-B] Rule Builder 条件规则业务键锚点展开
#   背景: ConditionRuleBuilder 产出 "domain_id IN (64, 'SCM')" 后,
#   ConditionEvaluator per-record 求值 str(88) not in ['64','SCM'] → 锚点静默失效
#   (IN fail-closed / NOT IN fail-open)。展开必须在 rule-load 时把 code 解析为 ID。
# ============================================================================

class TestConditionAnchorExpansion:
    def test_in_mixed_expansion(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "domain_id IN (64, 'SCM')", 'domain')
        assert out == 'domain_id IN (64, 88, 90)'

    def test_not_in_expansion(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "domain_id NOT IN ('SCM')", 'domain')
        assert out == 'domain_id NOT IN (64, 88, 90)'

    def test_self_reference_id_field(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "id IN ('SCM')", 'domain')
        assert out == 'id IN (64, 88, 90)'

    def test_eq_single_anchor(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "domain_id = 'SCM'", 'domain')
        assert out == 'domain_id IN (64, 88, 90)'

    def test_neq_single_anchor(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "domain_id != 'SCM'", 'domain')
        assert out == 'domain_id NOT IN (64, 88, 90)'

    def test_bare_token_without_quotes(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, 'domain_id IN (SCM)', 'domain')
        assert out == 'domain_id IN (64, 88, 90)'

    def test_zero_hit_anchor_dropped_keep_numeric(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "domain_id IN (64, 'TYPO')", 'domain')
        assert out == 'domain_id IN (64)'

    def test_all_zero_hit_in_becomes_false(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "domain_id IN ('TYPO')", 'domain')
        assert out == '1=0'

    def test_all_zero_hit_not_in_drops_predicate(self, ds, monkeypatch):
        # NOT IN (0命中) = 恒真 → 谓词删除; 全条件删空 → 1=1
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "domain_id NOT IN ('TYPO')", 'domain')
        assert out == '1=1'

    def test_and_composite(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(
            ds, "domain_id IN ('SCM') AND status = 'active'", 'domain')
        assert out == "domain_id IN (64, 88, 90) AND status = 'active'"

    def test_code_field_native_no_expansion(self, ds, monkeypatch):
        # field=code 自引用: resource.code 字符串原生匹配, 无需展开 (保持动态)
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "code IN ('SCM')", 'business_object')
        assert out == "code IN ('SCM')"

    def test_non_dimension_field_untouched(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "owner_id IN ('X')", 'domain')
        assert out == "owner_id IN ('X')"

    def test_top_level_or_skipped(self, ds, monkeypatch):
        # OR 组合不展开 (保守: 保持现状, 不引入语义漂移)
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        cond = "domain_id IN ('SCM') OR status = 'active'"
        assert _expand_condition_anchors(ds, cond, 'domain') == cond

    def test_flag_off_with_anchors_fail_closed(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '0')
        from meta.services.condition_permission_service import _expand_condition_anchors
        assert _expand_condition_anchors(ds, "domain_id IN ('SCM')", 'domain') == '1=0'

    def test_flag_off_without_anchors_unchanged(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '0')
        from meta.services.condition_permission_service import _expand_condition_anchors
        cond = 'domain_id IN (64, 88)'
        assert _expand_condition_anchors(ds, cond, 'domain') == cond

    def test_no_anchor_numeric_only_unchanged(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        cond = 'domain_id IN (64, 88)'
        assert _expand_condition_anchors(ds, cond, 'domain') == cond


class TestDimensionCodesQuery:
    """[Spec 20 Task 9-B] picker 业务键列表纯查询函数"""

    def test_codes_with_hit_counts(self, ds):
        from meta.api.permission_dimension_api import _query_dimension_codes
        data = _query_dimension_codes(ds, 'domain', search='', page=1, page_size=20)
        assert data['pagination']['total_count'] == 2  # SCM / FIN
        by_code = {c['code']: c for c in data['codes']}
        assert by_code['SCM']['resolved_count'] == 3
        assert by_code['SCM']['sample_name'] == '供应链云'
        assert by_code['FIN']['resolved_count'] == 1

    def test_parent_label_dynamic(self, ds):
        # [Spec 20 v3] parent_label 驱动动态「跨{父对象}·业务键」标签:
        #   domain 父=version→版本; version 父=product→产品; product 根对象→None
        from meta.api.permission_dimension_api import _query_dimension_codes
        assert _query_dimension_codes(ds, 'domain', '', 1, 20)['parent_label'] == '版本'
        assert _query_dimension_codes(ds, 'version', '', 1, 20)['parent_label'] == '产品'
        assert _query_dimension_codes(ds, 'product', '', 1, 20)['parent_label'] is None

    def test_search_filter(self, ds):
        from meta.api.permission_dimension_api import _query_dimension_codes
        data = _query_dimension_codes(ds, 'domain', search='SC', page=1, page_size=20)
        assert [c['code'] for c in data['codes']] == ['SCM']

    def test_scoped_ids_narrow_counts(self, ds):
        from meta.api.permission_dimension_api import _query_dimension_codes
        data = _query_dimension_codes(ds, 'domain', search='', page=1, page_size=20,
                                      scoped_ids={64})
        by_code = {c['code']: c for c in data['codes']}
        assert by_code['SCM']['resolved_count'] == 1
        assert 'FIN' not in by_code

    def test_unknown_dim_returns_none(self, ds):
        from meta.api.permission_dimension_api import _query_dimension_codes
        assert _query_dimension_codes(ds, 'nonexistent', '', 1, 20) is None

    def test_version_cross_parent_counts(self, ds):
        # version.code='v01' 跨产品 2 份 (跨父对象多份)
        from meta.api.permission_dimension_api import _query_dimension_codes
        data = _query_dimension_codes(ds, 'version', search='', page=1, page_size=20)
        by_code = {c['code']: c for c in data['codes']}
        assert by_code['v01']['resolved_count'] == 2


# ============================================================================
# [Spec 20 v5 字段即模式] FK code 虚拟字段 (version_code) 白名单 + 谓词左值改写
#   背景: domain.version_code 是 virtual resolution 解析字段 (semantics.redundancy
#   声明 source_field=version_id), 此前被 field-metadata 的 virtual 过滤拦截,
#   导致 FK 业务键锚定只能内联在 version_id 的双 Tab 里 (宽写回例外)。
#   白名单放行后: field=version_code → bizkey_only 直出 version 业务键列表,
#   展开时左值改写 version_code IN (...) → version_id IN (...)。
#   通用性: 判据全部来自 YAML semantics.redundancy, 零命名约定/维度硬编码。
# ============================================================================

class TestFkCodeFieldMap:
    def test_domain_map(self, ds):
        from meta.services.condition_permission_service import _fk_code_field_map
        assert _fk_code_field_map('domain') == {'version_code': ('version', 'version_id')}

    def test_bad_dim_excluded(self, ds):
        # relationship.source_bo_code: source_field=source_bo_id → dim='source_bo'
        # 不在维度注册表 (解析无引擎) → 白名单排除
        from meta.services.condition_permission_service import _fk_code_field_map
        assert 'source_bo_code' not in _fk_code_field_map('relationship')

    def test_non_code_virtual_excluded(self, ds):
        # 非 *_code 虚拟字段 (如 version_name 显示名) 不放行
        from meta.services.condition_permission_service import _fk_code_field_map
        for k in _fk_code_field_map('domain'):
            assert k.endswith('_code')


class TestFkCodeExpansion:
    """version_code 谓词: 值域纯业务键 → 数字 token 也按 code 解析 + 左值改写"""

    def test_in_left_value_rewritten(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "version_code IN ('v01')", 'domain')
        assert out == 'version_id IN (10, 20)'

    def test_in_multi_code(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        out = _expand_condition_anchors(ds, "version_code IN ('v01', 'v02')", 'domain')
        assert out == 'version_id IN (10, 11, 20)'

    def test_numeric_token_parsed_as_code(self, ds, monkeypatch):
        # 数字 code ('123' 是合法 version.code) + 数字字面 token 都按业务键解析
        # [helper 参数语义实证] insert_version 第2位置参→code 列, 第3位置参→name 列
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        insert_version(ds, 13, '123', 'V1.3', 1)  # code='123', name='V1.3'
        from meta.services.condition_permission_service import _expand_condition_anchors
        assert _expand_condition_anchors(ds, "version_code IN ('123')", 'domain') == 'version_id IN (13)'
        assert _expand_condition_anchors(ds, 'version_code IN (123)', 'domain') == 'version_id IN (13)'

    def test_zero_hit_fail_closed(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        assert _expand_condition_anchors(ds, "version_code IN ('TYPO')", 'domain') == '1=0'

    def test_flag_off_fail_closed(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '0')
        from meta.services.condition_permission_service import _expand_condition_anchors
        assert _expand_condition_anchors(ds, "version_code IN ('v01')", 'domain') == '1=0'

    def test_cmp_left_value_rewritten(self, ds, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        assert _expand_condition_anchors(ds, "version_code = 'v01'", 'domain') == 'version_id IN (10, 20)'

    def test_fk_id_regression_unchanged(self, ds, monkeypatch):
        # FK id 字段 (version_id) 旧语义不变: 非数字解析 + 数字保留
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '1')
        from meta.services.condition_permission_service import _expand_condition_anchors
        assert _expand_condition_anchors(ds, "version_id IN ('v01')", 'domain') == 'version_id IN (10, 20)'


class TestFkCodeFieldMetadata:
    """field-metadata 白名单放行 + anchor_semantics 通用语义信号"""

    def test_fk_code_whitelisted(self, ds):
        from meta.services.condition_permission_service import ConditionPermissionService
        items = {f['db_column']: f for f in ConditionPermissionService(ds).get_resource_field_metadata('domain')}
        vc = items.get('version_code')
        assert vc is not None, 'version_code 应被白名单放行'
        assert vc['is_business_key'] is True
        assert vc['is_foreign_key'] is True
        assert vc['relation_object'] == 'version'
        assert vc['anchor_semantics'] == 'bizkey'

    def test_anchor_semantics_signals(self, ds):
        # 通用信号矩阵: 前端分组/hint/契约全部由 anchor_semantics 派生, 零硬编码
        from meta.services.condition_permission_service import ConditionPermissionService
        items = {f['db_column']: f for f in ConditionPermissionService(ds).get_resource_field_metadata('domain')}
        assert items['id']['anchor_semantics'] == 'instance'       # 技术主键 → 快照
        assert items['version_id']['anchor_semantics'] == 'instance'  # FK id → 快照
        assert items['code']['anchor_semantics'] == 'bizkey'       # self-ref 业务键 → 动态
        assert items['version_code']['anchor_semantics'] == 'bizkey'  # FK code → 动态
        assert items['name']['anchor_semantics'] is None           # 普通属性

    def test_other_virtual_still_excluded(self, ds):
        # computed/显示名等虚拟字段不被误放行
        from meta.services.condition_permission_service import ConditionPermissionService
        cols = {f['db_column'] for f in ConditionPermissionService(ds).get_resource_field_metadata('domain')}
        assert 'version_name' not in cols
