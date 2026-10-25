# -*- coding: utf-8 -*-
"""属性字典测试（schema 接线 + 准入 lint + 拦截器接线）

依据: meta/schemas/attribute_definition.yaml / attribute_scope.yaml / party_attribute_values.yaml
      meta/services/attribute_lint_service.py
"""

import pytest

pytestmark = pytest.mark.unit

from types import SimpleNamespace

import yaml

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.attribute_guard_interceptor import AttributeGuardInterceptor
from meta.core.models_enums import ObjectType
from meta.services.attribute_impact_service import (
    AttributeImpactError,
    AttributeImpactService,
)
from meta.services.attribute_lint_service import AttributeLintError, AttributeLintService
from meta.services.attribute_scope_service import AttributeScopeService
from meta.services.attribute_value_service import (
    AttributeValueError,
    AttributeValueService,
    ItemAttributeValueService,
)


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源（按 SQL 特征分流，覆盖 lint 用到的三类查询）
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, platform_codes=(), scopes=(), item_groups=(), raise_on_query=False):
        self.platform_codes = set(platform_codes)
        self.scopes = set(scopes)
        self.item_groups = set(item_groups)
        self.raise_on_query = raise_on_query

    def query(self, sql, params):
        if self.raise_on_query:
            raise RuntimeError('db down')
        if 'attribute_definitions' in sql:
            return [{'id': 1}] if params[0] in self.platform_codes else []
        if 'attribute_scopes' in sql:
            return [{'id': 1}] if tuple(params) in self.scopes else []
        if 'item_groups' in sql:
            return [{'id': 1}] if params[0] in self.item_groups else []
        return []


def _svc(**kw):
    return AttributeLintService(_FakeDS(**kw))


# ─────────────────────────────────────────────────────────────────────────────
# 定义 lint：L1 / L2 / L3 / L7
# ─────────────────────────────────────────────────────────────────────────────

class TestDefinitionLint:
    def test_usage_class_not_allowed_to_be_active(self):
        with pytest.raises(AttributeLintError) as e:
            _svc().check_definition({
                'tenant_id': 0, 'code': 'lead_time_calc', 'status': 'active',
                'usage_class': 'computed', 'data_type': 'number',
            })
        assert e.value.rule == 'attribute_usage_class_not_allowed'
        assert e.value.field_name == 'usage_class'

    def test_usage_class_allowed_when_not_active(self):
        # 未启用 ⇒ 不拦；停用态可作为提升前的暂存
        _svc().check_definition({
            'tenant_id': 0, 'code': 'lead_time_calc', 'status': 'inactive',
            'usage_class': 'computed', 'data_type': 'number',
        })

    def test_configurable_rejects_date_type(self):
        with pytest.raises(AttributeLintError) as e:
            _svc().check_definition({
                'tenant_id': 0, 'code': 'first_use_date', 'status': 'inactive',
                'usage_class': 'descriptive', 'data_type': 'date',
                'is_configurable': True,
            })
        assert e.value.rule == 'attribute_configurable_data_type'
        assert e.value.field_name == 'data_type'

    def test_configurable_create_active_requires_two_step(self):
        with pytest.raises(AttributeLintError) as e:
            _svc().check_definition({
                'tenant_id': 0, 'code': 'paint_color', 'status': 'active',
                'usage_class': 'descriptive', 'data_type': 'string',
                'is_configurable': True,
            })
        assert e.value.rule == 'attribute_configurable_requires_scope'

    def test_configurable_activate_requires_item_scope(self):
        with pytest.raises(AttributeLintError) as e:
            _svc().check_definition(
                {'id': 7, 'tenant_id': 0, 'code': 'paint_color', 'status': 'active',
                 'usage_class': 'descriptive', 'data_type': 'string',
                 'is_configurable': True},
                exclude_id=7,
            )
        assert e.value.rule == 'attribute_configurable_requires_scope'

    def test_configurable_activate_with_item_scope_passes(self):
        _svc(scopes={(7, 'object', 'item')}).check_definition(
            {'id': 7, 'tenant_id': 0, 'code': 'paint_color', 'status': 'active',
             'usage_class': 'descriptive', 'data_type': 'string',
             'is_configurable': True},
            exclude_id=7,
        )

    def test_tenant_code_conflicts_platform_code(self):
        with pytest.raises(AttributeLintError) as e:
            _svc(platform_codes=('paint_color',)).check_definition({
                'tenant_id': 5, 'code': 'paint_color', 'status': 'active',
                'usage_class': 'descriptive', 'data_type': 'string',
            })
        assert e.value.rule == 'attribute_code_conflict_platform'
        assert e.value.field_name == 'code'

    def test_platform_code_conflicts_object_field(self, monkeypatch):
        from meta.core.models import registry
        monkeypatch.setattr(
            registry, 'get_all',
            lambda: {'party': SimpleNamespace(fields=[SimpleNamespace(id='paint_color')])},
        )
        with pytest.raises(AttributeLintError) as e:
            _svc().check_definition({
                'tenant_id': 0, 'code': 'paint_color', 'status': 'active',
                'usage_class': 'descriptive', 'data_type': 'string',
            })
        assert e.value.rule == 'attribute_code_conflict_field'

    def test_technical_field_not_treated_as_conflict(self, monkeypatch):
        from meta.core.models import registry
        monkeypatch.setattr(
            registry, 'get_all',
            lambda: {'party': SimpleNamespace(fields=[SimpleNamespace(id='created_at')])},
        )
        # 技术列每个对象都有，不构成占名；业务字段（如 status）仍算冲突
        _svc().check_definition({
            'tenant_id': 0, 'code': 'created_at', 'status': 'active',
            'usage_class': 'descriptive', 'data_type': 'datetime',
        })

    def test_query_failure_fails_open(self):
        _svc(raise_on_query=True).check_definition({
            'tenant_id': 5, 'code': 'paint_color', 'status': 'active',
            'usage_class': 'descriptive', 'data_type': 'string',
        })


# ─────────────────────────────────────────────────────────────────────────────
# 范围 lint：L4
# ─────────────────────────────────────────────────────────────────────────────

class TestScopeLint:
    def test_object_scope_missing(self, monkeypatch):
        from meta.core.models import registry
        monkeypatch.setattr(registry, 'get', lambda _id: None)
        with pytest.raises(AttributeLintError) as e:
            _svc().check_scope({'scope_type': 'object', 'scope_ref': 'no_such'})
        assert e.value.rule == 'attribute_scope_object_missing'

    def test_object_scope_view_rejected(self, monkeypatch):
        from meta.core.models import registry
        monkeypatch.setattr(
            registry, 'get',
            lambda _id: SimpleNamespace(object_type=ObjectType.VIEW),
        )
        with pytest.raises(AttributeLintError) as e:
            _svc().check_scope({'scope_type': 'object', 'scope_ref': 'v_x'})
        assert e.value.rule == 'attribute_scope_object_not_persistent'

    def test_object_scope_entity_passes(self, monkeypatch):
        from meta.core.models import registry
        monkeypatch.setattr(
            registry, 'get',
            lambda _id: SimpleNamespace(object_type=ObjectType.ENTITY),
        )
        _svc().check_scope({'scope_type': 'object', 'scope_ref': 'party'})

    def test_item_group_scope_missing(self):
        with pytest.raises(AttributeLintError) as e:
            _svc().check_scope({'scope_type': 'item_group', 'scope_ref': 'raw'})
        assert e.value.rule == 'attribute_scope_item_group_missing'
        assert e.value.field_name == 'scope_ref'

    def test_item_group_scope_passes(self):
        _svc(item_groups={'raw'}).check_scope(
            {'scope_type': 'item_group', 'scope_ref': 'raw'})

    def test_unknown_scope_type(self):
        with pytest.raises(AttributeLintError) as e:
            _svc().check_scope({'scope_type': 'org', 'scope_ref': '1'})
        assert e.value.rule == 'attribute_scope_type_invalid'


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(object_id, action, params, old_data=None, ds=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        object_id=params.get('id'),
        data_source=ds or _FakeDS(),
    )


class TestInterceptor:
    def test_priority(self):
        assert AttributeGuardInterceptor().priority == 45

    def test_only_guards_dictionary_tables(self):
        ic = AttributeGuardInterceptor()
        assert ic.should_execute(_ctx('attribute_definition', 'crud_create', {}))
        assert ic.should_execute(_ctx('attribute_scope', 'crud_update', {}))
        assert ic.should_execute(_ctx('party_attribute_value', 'crud_create', {}))
        assert ic.should_execute(_ctx('item_attribute_value', 'crud_create', {}))
        assert not ic.should_execute(_ctx('attribute_scope', 'crud_delete', {}))
        assert not ic.should_execute(_ctx('party', 'crud_create', {}))

    def test_raises_validation_failed(self):
        ic = AttributeGuardInterceptor()
        ctx = _ctx('attribute_definition', 'crud_create', {
            'tenant_id': 0, 'code': 'cost_rate', 'status': 'active',
            'usage_class': 'computed', 'data_type': 'number',
        })
        with pytest.raises(ValidationFailedError) as e:
            ic.before_action(ctx)
        assert e.value.details[0]['rule'] == 'attribute_usage_class_not_allowed'

    def test_update_merges_old_data(self):
        ic = AttributeGuardInterceptor()
        # 只改 status，旧行里的 usage_class 仍为 computed ⇒ 合并后应被拦
        ctx = _ctx('attribute_definition', 'crud_update',
                   {'id': 9, 'status': 'active', 'name': '改名'},
                   old_data={'id': 9, 'tenant_id': 0, 'code': 'cost_rate',
                             'status': 'inactive', 'usage_class': 'computed',
                             'data_type': 'number'})
        with pytest.raises(ValidationFailedError):
            ic.before_action(ctx)

    def test_scope_write_passes_through(self):
        ic = AttributeGuardInterceptor()
        ctx = _ctx('attribute_scope', 'crud_create',
                   {'scope_type': 'item_group', 'scope_ref': 'raw'},
                   ds=_FakeDS(item_groups={'raw'}))
        ic.before_action(ctx)

    def test_delete_guarded_for_definition_only(self):
        ic = AttributeGuardInterceptor()
        assert ic.should_execute(_ctx('attribute_definition', 'crud_delete', {'id': 1}))
        assert not ic.should_execute(_ctx('attribute_scope', 'crud_delete', {'id': 1}))
        assert not ic.should_execute(
            _ctx('party_attribute_value', 'crud_delete', {'id': 1}))


# ─────────────────────────────────────────────────────────────────────────────
# 引用影响（T6）：删除定义前必须无引用
# ─────────────────────────────────────────────────────────────────────────────

class _ImpactDS:
    """按表名返回预置计数。"""

    def __init__(self, scopes=0, values=None, raise_on_query=False):
        self.scopes = scopes
        self.values = values or {}
        self.raise_on_query = raise_on_query

    def query(self, sql, params):
        if self.raise_on_query:
            raise RuntimeError('db down')
        if 'attribute_scopes' in sql:
            return [{'cnt': self.scopes}]
        for table, cnt in self.values.items():
            if table in sql:
                return [{'cnt': cnt}]
        return [{'cnt': 0}]


def _impact(ds, tables=('party_attribute_values',)):
    return AttributeImpactService(ds, value_tables=list(tables))


class TestImpactPreview:
    def test_preview_counts_scope_and_values(self):
        info = _impact(_ImpactDS(scopes=2, values={'party_attribute_values': 3})).preview(7)
        assert info == {
            'attribute_id': 7, 'scope_count': 2, 'value_count': 3,
            'value_tables': {'party_attribute_values': 3}, 'referenced': True,
        }

    def test_unreferenced_passes(self):
        _impact(_ImpactDS()).assert_not_referenced(7)

    def test_referenced_rejected_with_counts(self):
        svc = _impact(_ImpactDS(scopes=2, values={'party_attribute_values': 3}))
        with pytest.raises(AttributeImpactError) as e:
            svc.assert_not_referenced(7)
        assert e.value.rule == 'attribute_in_use'
        assert '2 条适用范围' in str(e.value)
        assert '3 条属性值' in str(e.value)
        assert '停用' in str(e.value)

    def test_query_failure_fails_open(self):
        _impact(_ImpactDS(raise_on_query=True)).assert_not_referenced(7)

    def test_interceptor_blocks_delete_when_referenced(self):
        ic = AttributeGuardInterceptor()
        ctx = _ctx('attribute_definition', 'crud_delete', {'id': 7},
                   ds=_ImpactDS(scopes=1))
        with pytest.raises(ValidationFailedError) as e:
            ic.before_action(ctx)
        assert e.value.details[0]['rule'] == 'attribute_in_use'

    def test_interceptor_allows_delete_when_clean(self):
        ic = AttributeGuardInterceptor()
        ic.before_action(_ctx('attribute_definition', 'crud_delete', {'id': 7},
                              ds=_ImpactDS()))


# ─────────────────────────────────────────────────────────────────────────────
# 范围解析（T4）：四档优先级、就近覆盖不累加
# ─────────────────────────────────────────────────────────────────────────────

class _RowDS:
    """按 SQL 关键字返回预置行。"""

    def __init__(self, rows):
        self.rows = rows

    def query(self, sql, params):
        for marker, rows in self.rows.items():
            if marker in sql:
                return rows
        return []


def _scope_row(attribute_id, tenant_id, scope_type, scope_ref, required):
    return {'id': 1, 'attribute_id': attribute_id, 'tenant_id': tenant_id,
            'scope_type': scope_type, 'scope_ref': scope_ref,
            'required_flag': 1 if required else 0, 'seq': 10}


class TestScopeResolve:
    def _svc(self, rows):
        return AttributeScopeService(_RowDS({'FROM attribute_scopes': rows}))

    def test_tenant_beats_platform(self):
        svc = self._svc([
            _scope_row(1, 0, 'object', 'party', True),
            _scope_row(1, 5, 'object', 'party', False),
        ])
        resolved = svc.resolve(5, 'party')
        assert resolved[1]['required'] is False
        assert resolved[1]['tenant_id'] == 5

    def test_item_group_beats_object_within_tenant(self):
        svc = self._svc([
            _scope_row(2, 5, 'object', 'party', False),
            _scope_row(2, 5, 'item_group', 'raw', True),
        ])
        resolved = svc.resolve(5, 'party', item_group_code='raw')
        assert resolved[2]['required'] is True
        assert resolved[2]['scope_type'] == 'item_group'

    def test_overrides_not_additive(self):
        # 平台层必填、租户层可选 ⇒ 取租户层（就近覆盖），不是「必填 ∪ 可选」
        svc = self._svc([
            _scope_row(3, 0, 'item_group', 'raw', True),
            _scope_row(3, 5, 'object', 'party', False),
        ])
        assert svc.resolve(5, 'party') == {
            3: {'required': False, 'scope_type': 'object', 'scope_ref': 'party',
                'tenant_id': 5}
        }

    def test_required_ids_only(self):
        svc = self._svc([
            _scope_row(4, 0, 'object', 'party', True),
            _scope_row(5, 0, 'object', 'party', False),
        ])
        assert svc.required_attribute_ids(1, 'party') == [4]


# ─────────────────────────────────────────────────────────────────────────────
# 值校验（T5）：互斥填充 / 类型对应 / 多值 seq / 租户与状态
# ─────────────────────────────────────────────────────────────────────────────

class _DefDS:
    def __init__(self, definition=None):
        self.definition = definition

    def query(self, sql, params):
        if 'multi_value_flag' in sql:
            return [self.definition] if self.definition else []
        return []


def _definition(**kw):
    base = {'id': 1, 'tenant_id': 0, 'code': 'paint_color', 'name': '颜色',
            'data_type': 'string', 'multi_value_flag': False, 'status': 'active'}
    base.update(kw)
    return base


def _value_svc(**kw):
    return AttributeValueService(_DefDS(_definition(**kw)))


class TestValueValidation:
    def test_type_match_passes(self):
        _value_svc().validate_write({'attribute_id': 1, 'value_text': 'red', 'seq': 1})

    def test_number_goes_to_number_column(self):
        _value_svc(data_type='number').validate_write(
            {'attribute_id': 1, 'value_number': 12.5, 'seq': 1})

    def test_type_mismatch_rejected(self):
        with pytest.raises(AttributeValueError) as e:
            _value_svc(data_type='number').validate_write(
                {'attribute_id': 1, 'value_text': '12.5', 'seq': 1})
        assert e.value.rule == 'attribute_value_type_mismatch'
        assert e.value.field_name == 'value_text'

    def test_two_columns_rejected(self):
        with pytest.raises(AttributeValueError) as e:
            _value_svc().validate_write(
                {'attribute_id': 1, 'value_text': 'red', 'value_number': 1, 'seq': 1})
        assert e.value.rule == 'attribute_value_column_count'

    def test_no_value_column_rejected(self):
        with pytest.raises(AttributeValueError) as e:
            _value_svc().validate_write({'attribute_id': 1, 'seq': 1})
        assert e.value.rule == 'attribute_value_column_count'

    def test_boolean_zero_is_not_blank(self):
        _value_svc(data_type='boolean').validate_write(
            {'attribute_id': 1, 'value_boolean': 0, 'seq': 1})

    def test_inactive_attribute_rejected(self):
        with pytest.raises(AttributeValueError) as e:
            _value_svc(status='inactive').validate_write(
                {'attribute_id': 1, 'value_text': 'red', 'seq': 1})
        assert e.value.rule == 'attribute_not_active'

    def test_tenant_private_attribute_limited(self):
        with pytest.raises(AttributeValueError) as e:
            _value_svc(tenant_id=5).validate_write(
                {'tenant_id': 0, 'attribute_id': 1, 'value_text': 'red', 'seq': 1})
        assert e.value.rule == 'attribute_tenant_mismatch'

    def test_single_value_seq_over_one_rejected(self):
        with pytest.raises(AttributeValueError) as e:
            _value_svc().validate_write(
                {'attribute_id': 1, 'value_text': 'red', 'seq': 2})
        assert e.value.rule == 'attribute_seq_not_allowed'

    def test_multi_value_seq_allowed(self):
        _value_svc(multi_value_flag=1).validate_write(
            {'attribute_id': 1, 'value_text': 'red', 'seq': 3})

    def test_missing_definition_rejected(self):
        svc = AttributeValueService(_DefDS(None))
        with pytest.raises(AttributeValueError) as e:
            svc.validate_write({'attribute_id': 99, 'value_text': 'x'})
        assert e.value.rule == 'attribute_missing'


# ─────────────────────────────────────────────────────────────────────────────
# 物料参数值（字典桥接）：平台层限定 + attr_code 与字典编码一致
# ─────────────────────────────────────────────────────────────────────────────

class TestItemAttributeValue:
    def _svc(self, **kw):
        return ItemAttributeValueService(_DefDS(_definition(**kw)))

    def test_consistent_write_passes(self):
        self._svc().validate_write(
            {'item_id': 1, 'attribute_id': 1, 'attr_code': 'paint_color',
             'value_text': 'red'})

    def test_date_type_goes_to_date_column(self):
        self._svc(data_type='date').validate_write(
            {'item_id': 1, 'attribute_id': 1, 'attr_code': 'paint_color',
             'value_date': '2026-10-25'})

    def test_attribute_id_required(self):
        with pytest.raises(AttributeValueError) as e:
            self._svc().validate_write({'item_id': 1, 'attr_code': 'paint_color',
                                        'value_text': 'red'})
        assert e.value.rule == 'attribute_id_required'

    def test_tenant_private_attribute_rejected(self):
        with pytest.raises(AttributeValueError) as e:
            self._svc(tenant_id=5).validate_write(
                {'item_id': 1, 'attribute_id': 1, 'attr_code': 'paint_color',
                 'value_text': 'red'})
        assert e.value.rule == 'attribute_platform_only'

    def test_code_must_match_definition(self):
        with pytest.raises(AttributeValueError) as e:
            self._svc().validate_write(
                {'item_id': 1, 'attribute_id': 1, 'attr_code': 'other_code',
                 'value_text': 'red'})
        assert e.value.rule == 'attribute_code_mismatch'

    def test_attr_code_required(self):
        with pytest.raises(AttributeValueError) as e:
            self._svc().validate_write(
                {'item_id': 1, 'attribute_id': 1, 'value_text': 'red'})
        assert e.value.rule == 'attr_code_required'

    def test_interceptor_guards_item_values(self):
        ic = AttributeGuardInterceptor()
        ctx = _ctx('item_attribute_value', 'crud_create',
                   {'item_id': 1, 'attr_code': 'paint_color', 'value_text': 'red'},
                   ds=_DefDS(_definition()))
        with pytest.raises(ValidationFailedError) as e:
            ic.before_action(ctx)
        assert e.value.details[0]['rule'] == 'attribute_id_required'


# ─────────────────────────────────────────────────────────────────────────────
# Schema 接线
# ─────────────────────────────────────────────────────────────────────────────

def _load(name):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'schemas' / f'{name}.yaml'
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestSchema:
    def test_attribute_definition(self):
        doc = _load('attribute_definition')
        assert doc['table_name'] == 'attribute_definitions'
        assert doc['semantics']['business_key'] == ['tenant_id', 'code']
        tenant = next(f for f in doc['fields'] if f['id'] == 'tenant_id')
        assert tenant['default'] == 0
        assert {'fields': ['tenant_id', 'code'], 'unique': True,
                'name': 'idx_attribute_definition_tenant_code'} in doc['indexes']
        assert doc['ui_view_config']['skip_auto_menu'] is True

    def test_attribute_scope(self):
        doc = _load('attribute_scope')
        assert doc['table_name'] == 'attribute_scopes'
        scope_type = next(f for f in doc['fields'] if f['id'] == 'scope_type')
        assert [v['value'] for v in scope_type['enum_values']] == ['object', 'item_group']
        assert {'fields': ['tenant_id', 'attribute_id', 'scope_type', 'scope_ref'],
                'unique': True, 'name': 'idx_attribute_scope_tenant_attr_scope'} in doc['indexes']

    def test_party_attribute_values(self):
        doc = _load('party_attribute_values')
        assert doc['parent_object'] == 'party'
        assert doc['hierarchy']['parent_field'] == 'party_id'
        value_cols = [f['id'] for f in doc['fields']
                      if f['id'].startswith('value_')]
        assert value_cols == ['value_text', 'value_number', 'value_boolean',
                              'value_date', 'value_datetime']
        assert {'fields': ['tenant_id', 'party_id', 'attribute_id', 'seq'],
                'unique': True, 'name': 'uidx_party_attr_value'} in doc['indexes']
        assert [r['target'] for r in doc['relations']] == ['party', 'attribute_definition']

    def test_item_attribute_values_bridge(self):
        doc = _load('item_attribute_values')
        fields = {f['id']: f for f in doc['fields']}
        # 桥接列可为空：存量行先有 attr_code，attribute_id 由 v111 回填
        assert fields['attribute_id'].get('nullable') is True
        value_cols = [f['id'] for f in doc['fields'] if f['id'].startswith('value_')]
        assert value_cols == ['value_text', 'value_number', 'value_boolean',
                              'value_date', 'value_datetime']
        assert 'attribute_definition' in [r['target'] for r in doc['relations']]
        # 本次不换唯一键：L0/L2 仍以 attr_code 为键
        keys = {i['name']: i['fields'] for i in doc['indexes']}
        assert keys['uidx_item_attr_l0'] == ['item_id', 'attr_code']
        assert keys['uidx_item_attr_l2'] == ['item_id', 'attr_code', 'org_id']

    def test_value_template_is_not_an_object(self):
        doc = _load('_attribute_value_template')
        # 无顶层 id ⇒ 加载器跳过（文件名 _ 前缀是第二道保险）
        assert 'id' not in doc
        assert doc['template_name'] == 'attribute_value_table'
        assert [c['column'] for c in doc['value_columns']] == [
            'value_text', 'value_number', 'value_boolean',
            'value_date', 'value_datetime',
        ]
