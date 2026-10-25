# -*- coding: utf-8 -*-
"""销售配置守卫测试（D1-D4 / V1-V2 / A1 / X1 + 拦截器接线）

依据: meta/schemas/control_parameter_def.yaml / control_parameter_value.yaml /
      line_type_assignment.yaml 头注释
"""

import pytest

pytestmark = pytest.mark.unit

from types import SimpleNamespace

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.sales_config_guard_interceptor import (
    SalesConfigGuardInterceptor,
)
from meta.services.sales_config_guard_service import (
    SalesConfigGuardError,
    SalesConfigGuardService,
)


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    """只实现守卫用到的 SQL 形态；查询语义按 SQL 的特征片段分流。"""

    def __init__(self, defs=None, values=None, assignments=None, ref_ids=None,
                 enum_codes=None, raise_on_query=False):
        self.defs = defs or {}            # id -> 定义行
        self.values = values or []        # 取值行
        self.assignments = assignments or []
        self.ref_ids = ref_ids or {}      # target_bo -> set(可引用主键)
        self.enum_codes = enum_codes or {}  # (enum_type_id, code)
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError('db down')
        p = list(params or [])

        if 'SELECT id, code FROM control_parameter_defs' in sql:
            bo = p[0]
            return [{'id': d['id'], 'code': d.get('code')}
                    for d in self.defs.values()
                    if d.get('value_type') == 'ref' and d.get('target_bo') == bo]

        if 'SELECT DISTINCT control_parameter_id' in sql:
            ids, target = p[:-1], str(p[-1]).strip()
            return [{'control_parameter_id': v['control_parameter_id']}
                    for v in self.values
                    if v['control_parameter_id'] in ids
                    and str(v.get('value')).strip() == target]

        if 'SELECT * FROM control_parameter_defs WHERE id' in sql:
            row = self.defs.get(p[0])
            return [row] if row else []

        if 'COALESCE(org_id, 0)' in sql:
            param_id, org, doc, line, grp, fallback, rank, exclude = p
            return [{'cnt': sum(
                1 for v in self.values
                if v['control_parameter_id'] == param_id
                and str(v.get('id')) != str(exclude)
                and (v.get('org_id') or 0) == (org or 0)
                and (v.get('document_type_id') or 0) == (doc or 0)
                and (v.get('line_type_id') or 0) == (line or 0)
                and (v.get('item_group_id') or 0) == (grp or 0)
                and (v.get('specificity_rank') or fallback) == rank)}]

        if 'line_type_assignments' in sql:
            doc, grp, fallback, rank, exclude = p
            return [{'cnt': sum(
                1 for a in self.assignments
                if a['document_type_id'] == doc
                and str(a.get('id')) != str(exclude)
                and (a.get('item_group_id') or 0) == (grp or 0)
                and (a.get('specificity_rank') or fallback) == rank)}]

        if 'FROM enum_values' in sql:
            key = (p[0], str(p[1]).strip())
            return [{'cnt': 1 if key in self.enum_codes else 0}]

        if 'COUNT(*) AS cnt FROM control_parameter_values' in sql:
            return [{'cnt': sum(1 for v in self.values
                                if v['control_parameter_id'] == p[0])}]

        if 'FROM payment_terms' in sql:
            return [{'cnt': 1 if p[0] in self.ref_ids.get('payment_term', set()) else 0}]

        raise AssertionError(f'未预期的 SQL: {sql}')


class _Svc(SalesConfigGuardService):
    """复用真实逻辑，只把「对象 → 表名」映射固定下来，避免依赖 registry。"""

    def _resolve_table(self, target_bo):
        return {'payment_term': 'payment_terms',
                'line_type': 'line_types'}.get(target_bo)


def _def_row(**kw):
    row = {'id': 1, 'code': 'allow_partial_delivery', 'value_type': 'bool',
           'enum_type_id': None, 'target_bo': None, 'default_value': 'true'}
    row.update(kw)
    return row


def _svc(**kw):
    return _Svc(_FakeDS(**kw))


# ─────────────────────────────────────────────────────────────────────────────
# D1 / D2 —— 值类型与值集 / 目标对象一致性
# ─────────────────────────────────────────────────────────────────────────────

class TestDefTypeConsistency:
    def test_enum_requires_enum_type(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'enum', 'default_value': 'A'})
        assert e.value.rule == 'enum_type_required'
        assert e.value.field_name == 'enum_type_id'

    def test_enum_rejects_target_bo(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'enum', 'enum_type_id': 1,
                 'target_bo': 'payment_term', 'default_value': 'A'})
        assert e.value.rule == 'target_bo_not_allowed'

    def test_ref_requires_target_bo(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'ref'})
        assert e.value.rule == 'target_bo_required'

    def test_ref_rejects_enum_type(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'ref', 'target_bo': 'payment_term',
                 'enum_type_id': 1})
        assert e.value.rule == 'enum_type_not_allowed'

    def test_ref_target_must_be_registered_object(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'ref', 'target_bo': 'no_such_bo'})
        assert e.value.rule == 'unknown_target_bo'

    def test_scalar_type_rejects_enum_type(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'string', 'enum_type_id': 1})
        assert e.value.rule == 'enum_type_not_allowed'

    def test_scalar_type_rejects_target_bo(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'bool', 'target_bo': 'payment_term'})
        assert e.value.rule == 'target_bo_not_allowed'

    def test_valid_enum_passes(self):
        _svc(enum_codes={(1, 'NET30')}).validate_parameter_def_write(
            {'code': 'x', 'value_type': 'enum', 'enum_type_id': 1,
             'default_value': 'NET30'})


# ─────────────────────────────────────────────────────────────────────────────
# D3 —— 默认值可解释
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultValue:
    def test_invalid_bool_default(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'bool', 'default_value': 'maybe'})
        assert e.value.rule == 'invalid_value'
        assert e.value.field_name == 'default_value'

    def test_invalid_int_default(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc().validate_parameter_def_write(
                {'code': 'x', 'value_type': 'int', 'default_value': '1.5'})
        assert e.value.rule == 'invalid_value'

    def test_ref_default_must_exist(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc(ref_ids={'payment_term': {3}}).validate_parameter_def_write(
                {'code': 'x', 'value_type': 'ref', 'target_bo': 'payment_term',
                 'default_value': '99'})
        assert e.value.rule == 'ref_not_found'

    def test_enum_default_must_be_in_value_set(self):
        with pytest.raises(SalesConfigGuardError) as e:
            _svc(enum_codes={(1, 'NET30')}).validate_parameter_def_write(
                {'code': 'x', 'value_type': 'enum', 'enum_type_id': 1,
                 'default_value': 'NET99'})
        assert e.value.rule == 'enum_value_not_found'

    def test_blank_default_is_allowed(self):
        _svc().validate_parameter_def_write({'code': 'x', 'value_type': 'bool'})

    def test_failed_lookup_is_fail_open(self):
        # 查询失败 → 无法判定 → 不阻断写入
        _svc(raise_on_query=True).validate_parameter_def_write(
            {'code': 'x', 'value_type': 'ref', 'target_bo': 'payment_term',
             'default_value': '99'})


# ─────────────────────────────────────────────────────────────────────────────
# D4 —— 已有取值后语义不可改
# ─────────────────────────────────────────────────────────────────────────────

class TestImmutability:
    def test_code_change_rejected_when_values_exist(self):
        svc = _svc(defs={1: _def_row()},
                   values=[{'id': 1, 'control_parameter_id': 1, 'value': 'true'}])
        with pytest.raises(SalesConfigGuardError) as e:
            svc.validate_parameter_def_write(
                _def_row(code='renamed'), exclude_id=1)
        assert e.value.rule == 'immutable_after_values'
        assert e.value.field_name == 'code'

    def test_value_type_change_rejected_when_values_exist(self):
        svc = _svc(defs={1: _def_row()},
                   values=[{'id': 1, 'control_parameter_id': 1, 'value': 'true'}])
        with pytest.raises(SalesConfigGuardError) as e:
            svc.validate_parameter_def_write(
                _def_row(value_type='string', default_value='true'), exclude_id=1)
        assert e.value.field_name == 'value_type'

    def test_rename_allowed_when_no_values(self):
        svc = _svc(defs={1: _def_row()}, values=[])
        svc.validate_parameter_def_write(_def_row(code='renamed'), exclude_id=1)

    def test_code_change_allowed_on_create(self):
        _svc().validate_parameter_def_write(_def_row(code='brand_new'))


# ─────────────────────────────────────────────────────────────────────────────
# V1 —— 取值按值类型校验
# ─────────────────────────────────────────────────────────────────────────────

class TestValueTypeCheck:
    def test_invalid_bool_value(self):
        svc = _svc(defs={1: _def_row()})
        with pytest.raises(SalesConfigGuardError) as e:
            svc.validate_parameter_value_write(
                {'control_parameter_id': 1, 'value': 'yes_please'})
        assert e.value.rule == 'invalid_value'
        assert e.value.field_name == 'value'

    def test_int_value_ok(self):
        svc = _svc(defs={1: _def_row(value_type='int')})
        svc.validate_parameter_value_write({'control_parameter_id': 1, 'value': '10'})

    def test_decimal_value_ok(self):
        svc = _svc(defs={1: _def_row(value_type='decimal')})
        svc.validate_parameter_value_write({'control_parameter_id': 1, 'value': '0.15'})

    def test_decimal_rejects_nan(self):
        svc = _svc(defs={1: _def_row(value_type='decimal')})
        with pytest.raises(SalesConfigGuardError):
            svc.validate_parameter_value_write(
                {'control_parameter_id': 1, 'value': 'NaN'})

    def test_ref_value_must_exist(self):
        svc = _svc(defs={1: _def_row(value_type='ref', target_bo='payment_term')},
                   ref_ids={'payment_term': {3}})
        with pytest.raises(SalesConfigGuardError) as e:
            svc.validate_parameter_value_write(
                {'control_parameter_id': 1, 'value': '99'})
        assert e.value.rule == 'ref_not_found'
        svc.validate_parameter_value_write(
            {'control_parameter_id': 1, 'value': '3'})

    def test_ref_value_must_be_numeric(self):
        svc = _svc(defs={1: _def_row(value_type='ref', target_bo='payment_term')})
        with pytest.raises(SalesConfigGuardError) as e:
            svc.validate_parameter_value_write(
                {'control_parameter_id': 1, 'value': 'NET30'})
        assert e.value.rule == 'invalid_value'

    def test_enum_value_must_be_in_set(self):
        svc = _svc(defs={1: _def_row(value_type='enum', enum_type_id=1)},
                   enum_codes={(1, 'NET30')})
        with pytest.raises(SalesConfigGuardError) as e:
            svc.validate_parameter_value_write(
                {'control_parameter_id': 1, 'value': 'NET99'})
        assert e.value.rule == 'enum_value_not_found'

    def test_unknown_parameter_is_pass_through(self):
        # 参数不存在 → 交给外键 / 层级校验，不在守卫里重复报错
        _svc().validate_parameter_value_write(
            {'control_parameter_id': 999, 'value': 'anything'})


# ─────────────────────────────────────────────────────────────────────────────
# V2 —— 维度组合 + specificity_rank 唯一（NULL 归一化）
# ─────────────────────────────────────────────────────────────────────────────

class TestValueUniqueness:
    def _svc_with_row(self, row):
        return _svc(defs={1: _def_row()},
                    values=[dict({'id': 5, 'control_parameter_id': 1,
                                  'value': 'false'}, **row)])

    def test_all_wildcard_null_rank_conflicts(self):
        svc = self._svc_with_row({})
        with pytest.raises(SalesConfigGuardError) as e:
            svc.validate_parameter_value_write(
                {'control_parameter_id': 1, 'value': 'true'})
        assert e.value.rule == 'dimension_conflict'
        assert e.value.field_name == 'specificity_rank'

    def test_same_dims_different_rank_passes(self):
        svc = self._svc_with_row({'specificity_rank': 900})
        svc.validate_parameter_value_write(
            {'control_parameter_id': 1, 'value': 'true', 'specificity_rank': 100})

    def test_same_rank_different_org_passes(self):
        svc = self._svc_with_row({'org_id': 1})
        svc.validate_parameter_value_write(
            {'control_parameter_id': 1, 'value': 'true', 'org_id': 2})

    def test_update_self_does_not_conflict(self):
        svc = self._svc_with_row({})
        svc.validate_parameter_value_write(
            {'control_parameter_id': 1, 'value': 'true'}, exclude_id=5)


# ─────────────────────────────────────────────────────────────────────────────
# A1 —— 单据类型下「物料组 + 具体度」唯一
# ─────────────────────────────────────────────────────────────────────────────

class TestAssignmentUniqueness:
    def test_duplicate_rejected(self):
        svc = _svc(assignments=[{'id': 1, 'document_type_id': 2,
                                 'item_group_id': None, 'specificity_rank': None}])
        with pytest.raises(SalesConfigGuardError) as e:
            svc.validate_assignment_write(
                {'document_type_id': 2, 'line_type_id': 1})
        assert e.value.rule == 'assignment_conflict'

    def test_distinct_item_group_passes(self):
        svc = _svc(assignments=[{'id': 1, 'document_type_id': 2,
                                 'item_group_id': 7, 'specificity_rank': 100}])
        svc.validate_assignment_write(
            {'document_type_id': 2, 'item_group_id': 8,
             'specificity_rank': 100, 'line_type_id': 1})

    def test_update_self_does_not_conflict(self):
        svc = _svc(assignments=[{'id': 1, 'document_type_id': 2,
                                 'item_group_id': 7, 'specificity_rank': 100}])
        svc.validate_assignment_write(
            {'document_type_id': 2, 'item_group_id': 7,
             'specificity_rank': 100, 'line_type_id': 1}, exclude_id=1)


# ─────────────────────────────────────────────────────────────────────────────
# X1 —— 删除前扫 ref 型参数的悬空引用
# ─────────────────────────────────────────────────────────────────────────────

class TestRefTargetDelete:
    def test_blocks_when_parameter_value_references_record(self):
        svc = _svc(
            defs={1: _def_row(code='default_payment_term', value_type='ref',
                              target_bo='payment_term')},
            values=[{'id': 1, 'control_parameter_id': 1, 'value': '7'}],
        )
        with pytest.raises(SalesConfigGuardError) as e:
            svc.assert_no_ref_values('payment_term', 7)
        assert e.value.rule == 'ref_target_in_use'
        assert 'default_payment_term' in str(e.value)

    def test_passes_when_no_parameter_references_record(self):
        svc = _svc(
            defs={1: _def_row(code='default_payment_term', value_type='ref',
                              target_bo='payment_term')},
            values=[{'id': 1, 'control_parameter_id': 1, 'value': '8'}],
        )
        svc.assert_no_ref_values('payment_term', 7)

    def test_passes_when_no_ref_parameter_defined(self):
        _svc().assert_no_ref_values('payment_term', 7)

    def test_failed_lookup_is_fail_open(self):
        _svc(raise_on_query=True).assert_no_ref_values('payment_term', 7)


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(object_id, action, params=None, old_data=None, ds=None):
    params = params or {}
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        object_id=params.get('id'),
        data_source=ds or _FakeDS(),
    )


class TestInterceptor:
    def test_priority_is_after_hierarchy_validation(self):
        assert SalesConfigGuardInterceptor().priority == 46

    @pytest.mark.parametrize('object_id,action,expected', [
        ('control_parameter_def', 'crud_create', True),
        ('control_parameter_def', 'crud_update', True),
        ('control_parameter_value', 'crud_create', True),
        ('line_type_assignment', 'crud_update', True),
        # 配置对象本身的删除由 deletion_policy 的列级外键兜底，不需扫 ref 参数
        ('control_parameter_def', 'crud_delete', False),
        ('payment_term', 'crud_delete', True),
        ('item', 'crud_create', False),
        ('control_parameter_def', 'activate', False),
    ])
    def test_should_execute(self, object_id, action, expected):
        assert SalesConfigGuardInterceptor().should_execute(
            _ctx(object_id, action)) is expected

    def test_update_merges_old_data(self):
        ds = _FakeDS(defs={1: _def_row()},
                     values=[{'id': 1, 'control_parameter_id': 1, 'value': 'true'}])
        ic = SalesConfigGuardInterceptor()
        old = dict(_def_row(), id=1)
        # 只改 name，不触碰不可变字段 → 不应报错
        ic.before_action(_ctx('control_parameter_def', 'crud_update',
                              params={'id': 1, 'name': '新名字'},
                              old_data=old, ds=ds))
        # old_data 补齐了 code / 值类型，故只有「改值类型」会被拦
        with pytest.raises(ValidationFailedError):
            ic.before_action(_ctx('control_parameter_def', 'crud_update',
                                  params={'id': 1, 'value_type': 'string'},
                                  old_data=old, ds=ds))

    def test_guard_error_becomes_validation_failed(self):
        ic = SalesConfigGuardInterceptor()
        with pytest.raises(ValidationFailedError) as e:
            ic.before_action(_ctx('control_parameter_def', 'crud_create',
                                  params={'code': 'x', 'value_type': 'enum'}))
        assert e.value.details[0]['rule'] == 'enum_type_required'

    def test_delete_path_blocks_dangling_ref(self):
        ds = _FakeDS(
            defs={1: _def_row(code='default_payment_term', value_type='ref',
                              target_bo='payment_term')},
            values=[{'id': 1, 'control_parameter_id': 1, 'value': '7'}],
        )
        ic = SalesConfigGuardInterceptor()
        with pytest.raises(ValidationFailedError) as e:
            ic.before_action(_ctx('payment_term', 'crud_delete',
                                  params={'id': 7}, ds=ds))
        assert e.value.details[0]['rule'] == 'ref_target_in_use'

    def test_after_action_invalidates_resolver_cache(self):
        SalesConfigGuardInterceptor().after_action(
            _ctx('control_parameter_def', 'crud_create'))
