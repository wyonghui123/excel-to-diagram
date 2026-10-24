import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""单位换算守卫测试（V1 / V2 / V4 / V5 / V7 / V8）

依据: docs/superpowers/specs/2026-10-24-uom-conversion-model-design.md §6
"""

from types import SimpleNamespace

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.uom_conversion_guard_interceptor import (
    UomConversionGuardInterceptor,
)
from meta.core.metadata_driven_validator import MetadataDrivenValidator
from meta.core.models import FieldType, MetaField
from meta.services.uom_conversion_guard_service import (
    UomConversionGuardError,
    UomConversionGuardService,
)


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源（只实现守卫用到的两条 SQL 形态）
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, items=None, uoms=None, conv_by_item=None, conv_by_uom=None,
                 groups=None, group_conv_by_uom=None, group_conv_by_group=None,
                 groups_by_base=None):
        self.items = items or {}
        self.uoms = uoms or {}
        self.conv_by_item = conv_by_item or {}
        self.conv_by_uom = conv_by_uom or {}
        self.groups = groups or {}
        self.group_conv_by_uom = group_conv_by_uom or {}
        self.group_conv_by_group = group_conv_by_group or {}
        self.groups_by_base = groups_by_base or {}

    def query(self, sql, params):
        if 'FROM items' in sql:
            row = self.items.get(params[0])
            return [row] if row else []
        if 'FROM uoms' in sql:
            row = self.uoms.get(params[0])
            return [row] if row else []
        if 'FROM uom_groups' in sql and 'COUNT(*)' not in sql:
            row = self.groups.get(params[0])
            return [row] if row else []
        if 'COUNT(*)' in sql:
            if 'FROM item_uom_conversions' in sql:
                table = self.conv_by_item if 'WHERE item_id' in sql else self.conv_by_uom
            elif 'FROM uom_conversions' in sql:
                table = self.group_conv_by_group if 'WHERE uom_group_id' in sql \
                    else self.group_conv_by_uom
            elif 'FROM uom_groups' in sql:
                table = self.groups_by_base
            else:
                raise AssertionError(f'未预期的 SQL: {sql}')
            return [{'cnt': table.get(params[0], 0)}]
        raise AssertionError(f'未预期的 SQL: {sql}')


ITEM_ACTIVE = {'id': 1, 'base_uom': 10, 'status': 'active'}
UOM_ACTIVE = {'id': 20, 'name': '箱', 'status': 'active', 'uom_group_id': 1}
GROUP_ACTIVE = {'id': 1, 'name': '数量', 'base_uom_id': 10, 'status': 'active'}


def _ctx(object_id, action, params, old_data=None, ds=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        object_id=params.get('id'),
        data_source=ds or _FakeDS(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# V1 —— 字段级数值范围 / 小数位
# ─────────────────────────────────────────────────────────────────────────────

class TestNumericRange:
    """V1：factor > 0 且最多 10 位小数（YAML constraints 驱动）。"""

    @staticmethod
    def _factor_field():
        return MetaField(
            id='factor', name='换算率', field_type=FieldType.FLOAT,
            db_column='factor', required=True,
            constraints=[{'type': 'numeric_range', 'gt': 0, 'decimal_places': 10}],
        )

    def test_accepts_positive_factor(self):
        errors = MetadataDrivenValidator(None)._check_numeric_range(
            self._factor_field(), 12.5, '换算率')
        assert errors == []

    def test_rejects_zero(self):
        errors = MetadataDrivenValidator(None)._check_numeric_range(
            self._factor_field(), 0, '换算率')
        assert len(errors) == 1
        assert errors[0].rule == 'numeric_range.gt'

    def test_rejects_negative(self):
        errors = MetadataDrivenValidator(None)._check_numeric_range(
            self._factor_field(), -1, '换算率')
        assert len(errors) == 1
        assert errors[0].rule == 'numeric_range.gt'

    def test_rejects_more_than_ten_decimal_places(self):
        errors = MetadataDrivenValidator(None)._check_numeric_range(
            self._factor_field(), 0.3333333333333, '换算率')
        assert len(errors) == 1
        assert errors[0].rule == 'numeric_range.decimal_places'

    def test_accepts_exactly_ten_decimal_places(self):
        errors = MetadataDrivenValidator(None)._check_numeric_range(
            self._factor_field(), 0.3333333333, '换算率')
        assert errors == []

    def test_field_without_constraints_is_untouched(self):
        plain = MetaField(id='x', name='X', field_type=FieldType.FLOAT, db_column='x')
        assert MetadataDrivenValidator(None)._check_numeric_range(plain, -5, 'X') == []


# ─────────────────────────────────────────────────────────────────────────────
# V2 / V4 / V5 —— 换算行写入
# ─────────────────────────────────────────────────────────────────────────────

class TestConversionWrite:
    def _service(self, **kwargs):
        return UomConversionGuardService(_FakeDS(**kwargs))

    def test_v2_rejects_uom_equals_base(self):
        svc = self._service(items={1: ITEM_ACTIVE}, uoms={10: UOM_ACTIVE})
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_conversion_write({'item_id': 1, 'uom_id': 10})
        assert e.value.rule == 'uom_equals_base'

    def test_v2_allows_other_uom(self):
        svc = self._service(items={1: ITEM_ACTIVE}, uoms={20: UOM_ACTIVE})
        svc.validate_conversion_write({'item_id': 1, 'uom_id': 20})

    def test_v4_rejects_inactive_uom(self):
        svc = self._service(
            items={1: ITEM_ACTIVE},
            uoms={20: {'id': 20, 'name': '箱', 'status': 'inactive'}})
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_conversion_write({'item_id': 1, 'uom_id': 20})
        assert e.value.rule == 'uom_inactive'
        assert '箱' in str(e.value)

    def test_v5_rejects_draft_item(self):
        svc = self._service(
            items={1: {'id': 1, 'base_uom': 10, 'status': 'draft'}},
            uoms={20: UOM_ACTIVE})
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_conversion_write({'item_id': 1, 'uom_id': 20})
        assert e.value.rule == 'item_not_issued'

    def test_v5_allows_active_item(self):
        svc = self._service(items={1: ITEM_ACTIVE}, uoms={20: UOM_ACTIVE})
        svc.validate_conversion_write({'item_id': 1, 'uom_id': 20})

    def test_missing_item_row_falls_through_to_fk_check(self):
        """物料行取不到时不在这里拦（由 FK 存在性校验兜底）。"""
        svc = self._service(uoms={20: UOM_ACTIVE})
        svc.validate_conversion_write({'item_id': 999, 'uom_id': 20})


# ─────────────────────────────────────────────────────────────────────────────
# V7 / V8 —— 物料改基本单位 / 单位停用
# ─────────────────────────────────────────────────────────────────────────────

class TestItemAndUomUpdate:
    def test_v7_rejects_base_uom_change_with_conversions(self):
        svc = UomConversionGuardService(
            _FakeDS(items={1: ITEM_ACTIVE}, conv_by_item={1: 2}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_item_update(1, 11)
        assert e.value.rule == 'base_uom_locked'
        assert '2' in str(e.value)

    def test_v7_allows_when_no_conversions(self):
        svc = UomConversionGuardService(_FakeDS(items={1: ITEM_ACTIVE}))
        svc.validate_item_update(1, 11)

    def test_v7_ignores_unchanged_base_uom(self):
        svc = UomConversionGuardService(
            _FakeDS(items={1: ITEM_ACTIVE}, conv_by_item={1: 2}))
        svc.validate_item_update(1, 10)

    def test_v8_rejects_deactivate_when_referenced(self):
        svc = UomConversionGuardService(
            _FakeDS(uoms={20: UOM_ACTIVE}, conv_by_uom={20: 3}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_uom_update(20, 'inactive')
        assert e.value.rule == 'uom_referenced'
        assert '3' in str(e.value)

    def test_v8_allows_deactivate_when_unreferenced(self):
        svc = UomConversionGuardService(_FakeDS(uoms={20: UOM_ACTIVE}))
        svc.validate_uom_update(20, 'inactive')

    def test_v8_ignores_non_deactivate_update(self):
        svc = UomConversionGuardService(
            _FakeDS(uoms={20: UOM_ACTIVE}, conv_by_uom={20: 3}))
        svc.validate_uom_update(20, 'active')


# ─────────────────────────────────────────────────────────────────────────────
# V9 / V10 —— 组内换算行写入
# ─────────────────────────────────────────────────────────────────────────────

class TestGroupConversionWrite:
    def _service(self, **kwargs):
        return UomConversionGuardService(_FakeDS(**kwargs))

    def test_v9_rejects_uom_from_other_group(self):
        svc = self._service(
            groups={1: GROUP_ACTIVE},
            uoms={20: {**UOM_ACTIVE, 'uom_group_id': 2}})
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_conversion_write({'uom_group_id': 1, 'uom_id': 20})
        assert e.value.rule == 'uom_group_mismatch'

    def test_v10_rejects_group_base_uom(self):
        svc = self._service(
            groups={1: GROUP_ACTIVE},
            uoms={10: {**UOM_ACTIVE, 'id': 10}})
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_conversion_write({'uom_group_id': 1, 'uom_id': 10})
        assert e.value.rule == 'uom_equals_group_base'

    def test_v10_rejects_when_group_has_no_base(self):
        svc = self._service(
            groups={1: {**GROUP_ACTIVE, 'base_uom_id': None}},
            uoms={20: UOM_ACTIVE})
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_conversion_write({'uom_group_id': 1, 'uom_id': 20})
        assert e.value.rule == 'group_base_uom_unset'

    def test_rejects_inactive_uom(self):
        svc = self._service(
            groups={1: GROUP_ACTIVE},
            uoms={20: {**UOM_ACTIVE, 'status': 'inactive'}})
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_conversion_write({'uom_group_id': 1, 'uom_id': 20})
        assert e.value.rule == 'uom_inactive'

    def test_rejects_inactive_group(self):
        svc = self._service(
            groups={1: {**GROUP_ACTIVE, 'status': 'inactive'}},
            uoms={20: UOM_ACTIVE})
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_conversion_write({'uom_group_id': 1, 'uom_id': 20})
        assert e.value.rule == 'group_inactive'

    def test_allows_valid_group_conversion(self):
        svc = self._service(groups={1: GROUP_ACTIVE}, uoms={20: UOM_ACTIVE})
        svc.validate_group_conversion_write({'uom_group_id': 1, 'uom_id': 20})

    def test_missing_uom_row_falls_through_to_fk_check(self):
        svc = self._service(groups={1: GROUP_ACTIVE})
        svc.validate_group_conversion_write({'uom_group_id': 1, 'uom_id': 999})


# ─────────────────────────────────────────────────────────────────────────────
# V11 / V12 —— 组改基本单位
# ─────────────────────────────────────────────────────────────────────────────

class TestGroupUpdate:
    def test_v11_rejects_base_change_with_conversions(self):
        svc = UomConversionGuardService(
            _FakeDS(groups={1: GROUP_ACTIVE}, group_conv_by_group={1: 4}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_update(1, 11)
        assert e.value.rule == 'base_uom_locked'
        assert '4' in str(e.value)

    def test_v11_rejects_clearing_base_with_conversions(self):
        svc = UomConversionGuardService(
            _FakeDS(groups={1: GROUP_ACTIVE}, group_conv_by_group={1: 1}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_update(1, None)
        assert e.value.rule == 'base_uom_locked'

    def test_v12_rejects_base_from_other_group(self):
        svc = UomConversionGuardService(
            _FakeDS(groups={1: GROUP_ACTIVE},
                    uoms={11: {**UOM_ACTIVE, 'id': 11, 'uom_group_id': 2}}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_update(1, 11)
        assert e.value.rule == 'base_uom_group_mismatch'

    def test_v12_rejects_inactive_base(self):
        svc = UomConversionGuardService(
            _FakeDS(groups={1: GROUP_ACTIVE},
                    uoms={11: {**UOM_ACTIVE, 'id': 11, 'status': 'inactive'}}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_group_update(1, 11)
        assert e.value.rule == 'base_uom_inactive'

    def test_allows_base_change_without_conversions(self):
        svc = UomConversionGuardService(
            _FakeDS(groups={1: GROUP_ACTIVE},
                    uoms={11: {**UOM_ACTIVE, 'id': 11}}))
        svc.validate_group_update(1, 11)

    def test_ignores_unchanged_base(self):
        svc = UomConversionGuardService(
            _FakeDS(groups={1: GROUP_ACTIVE}, group_conv_by_group={1: 2}))
        svc.validate_group_update(1, 10)


# ─────────────────────────────────────────────────────────────────────────────
# V13 / V14 —— 单位改组 / 停用
# ─────────────────────────────────────────────────────────────────────────────

class TestUomGroupChangeAndDeactivate:
    def test_v13_rejects_group_change_with_group_conversions(self):
        svc = UomConversionGuardService(
            _FakeDS(uoms={20: UOM_ACTIVE}, group_conv_by_uom={20: 2}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_uom_group_change(20, 2)
        assert e.value.rule == 'uom_group_locked'
        assert '2' in str(e.value)

    def test_v13_allows_group_change_without_conversions(self):
        svc = UomConversionGuardService(_FakeDS(uoms={20: UOM_ACTIVE}))
        svc.validate_uom_group_change(20, 2)

    def test_v13_ignores_unchanged_group(self):
        svc = UomConversionGuardService(
            _FakeDS(uoms={20: UOM_ACTIVE}, group_conv_by_uom={20: 2}))
        svc.validate_uom_group_change(20, 1)

    def test_v14_rejects_deactivate_when_referenced_by_group_conversion(self):
        svc = UomConversionGuardService(
            _FakeDS(uoms={20: UOM_ACTIVE}, group_conv_by_uom={20: 3}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_uom_update(20, 'inactive')
        assert e.value.rule == 'uom_referenced'
        assert '3' in str(e.value)

    def test_v14_rejects_deactivate_when_used_as_group_base(self):
        svc = UomConversionGuardService(
            _FakeDS(uoms={20: UOM_ACTIVE}, groups_by_base={20: 1}))
        with pytest.raises(UomConversionGuardError) as e:
            svc.validate_uom_update(20, 'inactive')
        assert e.value.rule == 'uom_is_group_base'


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线（对象 / 动作门控 + 异常转换）
# ─────────────────────────────────────────────────────────────────────────────

class TestInterceptorWiring:
    def setup_method(self):
        self.itc = UomConversionGuardInterceptor()

    def test_only_guarded_objects_pass(self):
        ds = _FakeDS()
        assert self.itc.should_execute(_ctx('item_uom_conversion', 'crud_create', {}, ds=ds))
        assert self.itc.should_execute(_ctx('uom_conversion', 'crud_create', {}, ds=ds))
        assert self.itc.should_execute(_ctx('item', 'crud_update', {}, ds=ds))
        assert self.itc.should_execute(_ctx('uom', 'crud_update', {}, ds=ds))
        assert self.itc.should_execute(_ctx('uom_group', 'crud_update', {}, ds=ds))

    def test_other_objects_and_reads_short_circuit(self):
        ds = _FakeDS()
        assert not self.itc.should_execute(_ctx('party', 'crud_create', {}, ds=ds))
        assert not self.itc.should_execute(_ctx('item', 'crud_create', {}, ds=ds))
        assert not self.itc.should_execute(_ctx('uom', 'crud_read', {}, ds=ds))
        assert not self.itc.should_execute(_ctx('uom_group', 'crud_create', {}, ds=ds))

    def test_conversion_create_raises_validation_failed(self):
        ds = _FakeDS(items={1: ITEM_ACTIVE}, uoms={10: UOM_ACTIVE})
        with pytest.raises(ValidationFailedError) as e:
            self.itc.before_action(
                _ctx('item_uom_conversion', 'crud_create',
                     {'item_id': 1, 'uom_id': 10}, ds=ds))
        assert '基本单位' in str(e.value)

    def test_conversion_update_merges_old_data(self):
        """更新只传 uom_id 时，item_id 由旧行补齐后仍能判定。"""
        ds = _FakeDS(items={1: ITEM_ACTIVE}, uoms={10: UOM_ACTIVE})
        with pytest.raises(ValidationFailedError):
            self.itc.before_action(
                _ctx('item_uom_conversion', 'crud_update',
                     {'id': 5, 'uom_id': 10},
                     old_data={'id': 5, 'item_id': 1, 'uom_id': 20}, ds=ds))

    def test_item_base_uom_change_raises(self):
        ds = _FakeDS(items={1: ITEM_ACTIVE}, conv_by_item={1: 1})
        with pytest.raises(ValidationFailedError):
            self.itc.before_action(
                _ctx('item', 'crud_update', {'id': 1, 'base_uom': 11}, ds=ds))

    def test_item_update_without_base_uom_is_noop(self):
        ds = _FakeDS(items={1: ITEM_ACTIVE}, conv_by_item={1: 1})
        self.itc.before_action(_ctx('item', 'crud_update', {'id': 1, 'name': '新名'}, ds=ds))

    def test_uom_deactivate_raises(self):
        ds = _FakeDS(uoms={20: UOM_ACTIVE}, conv_by_uom={20: 2})
        with pytest.raises(ValidationFailedError):
            self.itc.before_action(
                _ctx('uom', 'crud_update', {'id': 20, 'status': 'inactive'}, ds=ds))

    def test_group_conversion_create_raises(self):
        ds = _FakeDS(groups={1: GROUP_ACTIVE},
                     uoms={20: {**UOM_ACTIVE, 'uom_group_id': 2}})
        with pytest.raises(ValidationFailedError) as e:
            self.itc.before_action(
                _ctx('uom_conversion', 'crud_create',
                     {'uom_group_id': 1, 'uom_id': 20}, ds=ds))
        assert '计量单位组' in str(e.value)

    def test_group_conversion_update_merges_old_data(self):
        """更新只传 uom_id 时，uom_group_id 由旧行补齐后仍能判定。"""
        ds = _FakeDS(groups={1: GROUP_ACTIVE},
                     uoms={20: {**UOM_ACTIVE, 'uom_group_id': 2}})
        with pytest.raises(ValidationFailedError):
            self.itc.before_action(
                _ctx('uom_conversion', 'crud_update',
                     {'id': 7, 'uom_id': 20},
                     old_data={'id': 7, 'uom_group_id': 1, 'uom_id': 10}, ds=ds))

    def test_uom_group_base_change_raises(self):
        ds = _FakeDS(groups={1: GROUP_ACTIVE}, group_conv_by_group={1: 1})
        with pytest.raises(ValidationFailedError):
            self.itc.before_action(
                _ctx('uom_group', 'crud_update', {'id': 1, 'base_uom_id': 11}, ds=ds))

    def test_uom_group_update_without_base_is_noop(self):
        ds = _FakeDS(groups={1: GROUP_ACTIVE}, group_conv_by_group={1: 1})
        self.itc.before_action(
            _ctx('uom_group', 'crud_update', {'id': 1, 'name': '新组名'}, ds=ds))
