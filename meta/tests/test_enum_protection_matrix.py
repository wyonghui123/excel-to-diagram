# -*- coding: utf-8 -*-
"""
mutability 矩阵 9-case 测试 (v3.18 enum-mgmt-spec)

[NEW] 2026-06-13 批次: 枚举保护拦截器的 9-case 完整覆盖

mutability 矩阵定义 (DEC-1):
  - fullEditable: CRUD 全部允许 (除 is_system=true 仍不可 update/delete)
  - extensible:   可加新值, 可改/删非预置值, 不可改/删预置值
  - locked:       全部禁止

is_system 矩阵 (DEC-2 AND 严格):
  - is_system=true 永远不可 update/delete (无论 mutability 是什么)
  - is_system=true 不影响 "可创建新值"

9-case 矩阵 (针对 enum_value, is_system=false):

| case | mutability    | create | update | delete | 期望 error_code         |
|------|---------------|--------|--------|--------|-------------------------|
| 1    | fullEditable  | OK     | OK     | OK     | -                       |
| 2    | fullEditable  | OK     | OK     | OK     | -                       |
| 3    | fullEditable  | OK     | OK     | OK     | -                       |
| 4    | extensible    | OK     | OK     | OK     | -                       |
| 5    | extensible    | OK     | OK     | OK     | -                       |
| 6    | extensible    | OK     | OK     | OK     | -                       |
| 7    | locked        | BLOCK  | BLOCK  | BLOCK  | enum_value_locked       |
| 8    | locked        | BLOCK  | BLOCK  | BLOCK  | enum_value_locked       |
| 9    | locked        | BLOCK  | BLOCK  | BLOCK  | enum_value_locked       |

补充 case (验证 is_system=true 的 AND 严格):
  - is_system=true 永远 BLOCK update/delete, 任何 mutability

注: ErrorCode 的 .value 是小写 snake_case, 如 ErrorCode.ENUM_VALUE_LOCKED.value == 'enum_value_locked'
"""
import pytest
from unittest.mock import Mock, MagicMock

from meta.core.interceptors.enum_protection_interceptor import (
    EnumProtectionInterceptor,
    ALLOWED_MUTABILITY,
    CODE_PATTERN,
)
from meta.core.action_context import ActionContext, ActionResult
from meta.core.error_codes import ErrorCode

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def _make_meta_object(object_type: str):
    meta = Mock()
    meta.id = object_type
    return meta


def _make_context(
    object_type: str,
    action: str,
    params=None,
    old_data=None,
    data_source=None,
):
    return ActionContext(
        meta_object=_make_meta_object(object_type),
        action=action,
        params=params or {},
        data_source=data_source or Mock(),
        old_data=old_data,
    )


def _make_ds_with_enum_type(enum_type_row: dict):
    """构造返回 enum_type 行的 mock data_source"""
    ds = Mock()
    cursor = Mock()
    if enum_type_row:
        cols = list(enum_type_row.keys())
        cursor.fetchone.return_value = tuple(enum_type_row.values())
        cursor.description = [(c, None, None, None, None, None, None) for c in cols]
    else:
        cursor.fetchone.return_value = None
    ds.execute.return_value = cursor
    return ds


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

MUTABILITY_VALUES = ['fullEditable', 'extensible', 'locked']
ACTIONS = ['crud_create', 'crud_update', 'crud_delete']


# ─────────────────────────────────────────────
# 9-Case 主矩阵
# ─────────────────────────────────────────────

class TestEnumProtectionMatrix9Case:
    """
    9-case 主矩阵：3 mutability × 3 actions (针对 enum_value, is_system=false)

    fullEditable + extensible 在 create/update/delete 时全部 OK
    locked 在 create/update/delete 时全部 BLOCK (ENUM_VALUE_LOCKED)
    """

    # ── 1~3: fullEditable × {create, update, delete} ──

    def test_case_01_fullEditable_create_ok(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'fullEditable', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': 'NEW_VAL', 'name': 'New Val'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None, f"fullEditable create 应通过, 实际: {ctx.result}"

    def test_case_02_fullEditable_update_ok(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'fullEditable', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 100, 'name': 'updated'},
            old_data={'id': 100, 'enum_type_id': 1, 'code': 'VAL', 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None, f"fullEditable update 应通过, 实际: {ctx.result}"

    def test_case_03_fullEditable_delete_ok(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'fullEditable', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 100},
            old_data={'id': 100, 'enum_type_id': 1, 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None, f"fullEditable delete 应通过, 实际: {ctx.result}"

    # ── 4~6: extensible × {create, update, delete} ──

    def test_case_04_extensible_create_ok(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'extensible', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': 'NEW_VAL', 'name': 'New Val'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None, f"extensible create 应通过, 实际: {ctx.result}"

    def test_case_05_extensible_update_ok(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'extensible', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 100, 'name': 'updated'},
            old_data={'id': 100, 'enum_type_id': 1, 'code': 'VAL', 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None, f"extensible update 应通过, 实际: {ctx.result}"

    def test_case_06_extensible_delete_ok(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'extensible', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 100},
            old_data={'id': 100, 'enum_type_id': 1, 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None, f"extensible delete 应通过, 实际: {ctx.result}"

    # ── 7~9: locked × {create, update, delete} ──

    def test_case_07_locked_create_block(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'locked', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': 'NEW_VAL', 'name': 'New Val'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert ErrorCode.ENUM_VALUE_LOCKED.value in ctx.result.errors

    def test_case_08_locked_update_block(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'locked', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 100, 'name': 'updated'},
            old_data={'id': 100, 'enum_type_id': 1, 'code': 'VAL', 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert ErrorCode.ENUM_VALUE_LOCKED.value in ctx.result.errors

    def test_case_09_locked_delete_block(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'locked', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 100},
            old_data={'id': 100, 'enum_type_id': 1, 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert ErrorCode.ENUM_VALUE_LOCKED.value in ctx.result.errors


# ─────────────────────────────────────────────
# 9-Case 参数化版本 (更紧凑, 同样的 9 测)
# ─────────────────────────────────────────────

class TestEnumProtectionMatrixParameterized:
    """参数化 9-case: 3 mutability × 3 actions"""

    @pytest.mark.parametrize('mutability,action,should_block', [
        # fullEditable × 3 (全 OK)
        ('fullEditable', 'crud_create', False),
        ('fullEditable', 'crud_update', False),
        ('fullEditable', 'crud_delete', False),
        # extensible × 3 (全 OK)
        ('extensible', 'crud_create', False),
        ('extensible', 'crud_update', False),
        ('extensible', 'crud_delete', False),
        # locked × 3 (全 BLOCK)
        ('locked', 'crud_create', True),
        ('locked', 'crud_update', True),
        ('locked', 'crud_delete', True),
    ])
    def test_matrix_9_cases(self, mutability, action, should_block):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({
            'id': 1, 'mutability': mutability, 'category': 'business',
        })

        if action == 'crud_create':
            ctx = _make_context(
                'enum_value', action,
                params={'enum_type_id': 1, 'code': 'NEW_VAL', 'name': 'New Val'},
                data_source=ds,
            )
        elif action == 'crud_update':
            ctx = _make_context(
                'enum_value', action,
                params={'id': 100, 'name': 'updated'},
                old_data={'id': 100, 'enum_type_id': 1, 'code': 'VAL', 'is_system': 0},
                data_source=ds,
            )
        else:  # crud_delete
            ctx = _make_context(
                'enum_value', action,
                params={'id': 100},
                old_data={'id': 100, 'enum_type_id': 1, 'is_system': 0},
                data_source=ds,
            )

        interceptor.before_action(ctx)

        if should_block:
            assert ctx.result is not None
            assert ctx.result.success is False
            assert ErrorCode.ENUM_VALUE_LOCKED.value in ctx.result.errors
        else:
            assert ctx.result is None, (
                f"mutability={mutability} action={action} 不应被拦截, 实际: {ctx.result}"
            )


# ─────────────────────────────────────────────
# AND 严格: is_system=true 时无论 mutability 都不允许 update/delete
# ─────────────────────────────────────────────

class TestIsSystemAndStrict:
    """
    DEC-2: is_system=true 时, 任何 mutability 都不可 update/delete
    这与 mutability 是 AND 关系: 任何一个触发就 BLOCK
    """

    @pytest.mark.parametrize('mutability', ['fullEditable', 'extensible', 'locked'])
    def test_is_system_true_blocks_update(self, mutability):
        """is_system=true + 任意 mutability → update BLOCK (SYSTEM_VALUE_IMMUTABLE)"""
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({
            'id': 1, 'mutability': mutability, 'category': 'business',
        })
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 100, 'name': 'updated'},
            old_data={'id': 100, 'enum_type_id': 1, 'code': 'VAL', 'is_system': 1},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        # is_system 比 mutability 优先级更高 (先检查 is_system)
        assert ErrorCode.SYSTEM_VALUE_IMMUTABLE.value in ctx.result.errors

    @pytest.mark.parametrize('mutability', ['fullEditable', 'extensible', 'locked'])
    def test_is_system_true_blocks_delete(self, mutability):
        """is_system=true + 任意 mutability → delete BLOCK (SYSTEM_VALUE_IMMUTABLE)"""
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({
            'id': 1, 'mutability': mutability, 'category': 'business',
        })
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 100},
            old_data={'id': 100, 'enum_type_id': 1, 'is_system': 1},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert ErrorCode.SYSTEM_VALUE_IMMUTABLE.value in ctx.result.errors

    @pytest.mark.parametrize('mutability', ['fullEditable', 'extensible'])
    def test_is_system_true_still_creates(self, mutability):
        """is_system=true + 非 locked → 仍可创建 (不影响新增)"""
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({
            'id': 1, 'mutability': mutability, 'category': 'business',
        })
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': 'NEW_VAL', 'name': 'New Val', 'is_system': 1},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        # is_system 在 create 时不阻止
        assert ctx.result is None

    def test_is_system_true_with_locked_create_blocked_by_locked(self):
        """is_system=true + locked → create 仍 BLOCK (由 locked 触发)"""
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({
            'id': 1, 'mutability': 'locked', 'category': 'business',
        })
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': 'NEW_VAL', 'name': 'New Val', 'is_system': 1},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.ENUM_VALUE_LOCKED.value in ctx.result.errors


# ─────────────────────────────────────────────
# FR-001: mutability 值空间校验
# ─────────────────────────────────────────────

class TestMutabilityValueSpace:
    """FR-001: mutability 必须是 3 档之一, 其他值被拒绝 (INVALID_MUTABILITY)"""

    def test_allowed_values_constant(self):
        """ALLOWED_MUTABILITY 应是 3 档"""
        assert ALLOWED_MUTABILITY == {'fullEditable', 'extensible', 'locked'}

    @pytest.mark.parametrize('invalid_mut', ['mutable', 'immutable', 'frozen', 'fully_editable', 'FULL_EDITABLE', 'Extensible'])
    def test_invalid_mutability_on_create_enum_type(self, invalid_mut):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_create',
            params={'id': 'X', 'name': 'X', 'mutability': invalid_mut},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert ErrorCode.INVALID_MUTABILITY.value in ctx.result.errors

    @pytest.mark.parametrize('invalid_mut', ['mutable', 'immutable', 'frozen'])
    def test_invalid_mutability_on_update_enum_type(self, invalid_mut):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_update',
            params={'id': 1, 'mutability': invalid_mut},
            old_data={'id': 1, 'category': 'business', 'mutability': 'extensible'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.INVALID_MUTABILITY.value in ctx.result.errors

    def test_valid_mutability_does_not_trigger_invalid(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_create',
            params={'id': 'X', 'name': 'X', 'mutability': 'fullEditable'},
        )
        interceptor.before_action(ctx)
        # INVALID_MUTABILITY 不应触发
        if ctx.result:
            assert ErrorCode.INVALID_MUTABILITY.value not in ctx.result.errors


# ─────────────────────────────────────────────
# FR-006 ~ FR-010: 字段校验
# ─────────────────────────────────────────────

class TestFieldValidation:
    """FR-006~010: 必填/code 格式/code&id 不可改/(enum_type_id, name) 唯一"""

    # FR-006: 必填校验
    def test_create_value_missing_code(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'name': 'X'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.ACTION_PARAMS_MISSING.value in ctx.result.errors

    def test_create_value_missing_name(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': 'X'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.ACTION_PARAMS_MISSING.value in ctx.result.errors

    def test_create_value_missing_enum_type_id(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'code': 'X', 'name': 'X'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.ACTION_PARAMS_MISSING.value in ctx.result.errors

    # FR-007: code 格式校验
    @pytest.mark.parametrize('bad_code', [
        'lowercase', '1NUMBER', '_UNDER', 'has-dash', 'has space', 'with.dot',
    ])
    def test_invalid_code_format(self, bad_code):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': bad_code, 'name': 'X'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.INVALID_CODE_FORMAT.value in ctx.result.errors

    @pytest.mark.parametrize('good_code', ['A', 'ABC', 'A_B_C', 'A1B2', 'X1_Y2_Z3', 'A_'])
    def test_valid_code_format(self, good_code):
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'extensible', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': good_code, 'name': 'X'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        # 不应触发 INVALID_CODE_FORMAT
        if ctx.result:
            assert ErrorCode.INVALID_CODE_FORMAT.value not in ctx.result.errors

    def test_code_pattern_constant(self):
        """CODE_PATTERN 编译正确, 符合 ^[A-Z][A-Z0-9_]*$"""
        assert CODE_PATTERN.pattern == r'^[A-Z][A-Z0-9_]*$'

    # FR-008: code 不可改
    def test_code_immutable_on_update(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 100, 'code': 'NEW_CODE'},
            old_data={'id': 100, 'enum_type_id': 1, 'code': 'OLD_CODE', 'is_system': 0},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.CODE_IMMUTABLE.value in ctx.result.errors

    def test_code_same_value_allowed(self):
        """code 传相同值不算修改"""
        interceptor = EnumProtectionInterceptor()
        ds = _make_ds_with_enum_type({'id': 1, 'mutability': 'extensible', 'category': 'business'})
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 100, 'code': 'SAME_CODE'},
            old_data={'id': 100, 'enum_type_id': 1, 'code': 'SAME_CODE', 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        # 不应触发 CODE_IMMUTABLE
        if ctx.result:
            assert ErrorCode.CODE_IMMUTABLE.value not in ctx.result.errors

    # FR-010: id 不可改 (enum_type)
    def test_id_immutable_on_update_enum_type(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_update',
            params={'id': 'NEW_ID', 'name': 'X'},
            old_data={'id': 'OLD_ID', 'category': 'business', 'name': 'X'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.ID_IMMUTABLE.value in ctx.result.errors

    def test_id_same_value_allowed(self):
        """id 传相同值不算修改"""
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_update',
            params={'id': 'SAME', 'name': 'X'},
            old_data={'id': 'SAME', 'category': 'business', 'name': 'X'},
        )
        interceptor.before_action(ctx)
        if ctx.result:
            assert ErrorCode.ID_IMMUTABLE.value not in ctx.result.errors


# ─────────────────────────────────────────────
# 枚举类型自身保护: category=system
# ─────────────────────────────────────────────

class TestEnumTypeSystemCategory:
    """category=system 的 enum_type 不可 update/delete (SYSTEM_ENUM_IMMUTABLE)"""

    def test_system_enum_type_update_blocked(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_update',
            params={'id': 1, 'name': 'new'},
            old_data={'id': 1, 'category': 'system'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.SYSTEM_ENUM_IMMUTABLE.value in ctx.result.errors

    def test_system_enum_type_delete_blocked(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_delete',
            params={'id': 1},
            old_data={'id': 1, 'category': 'system'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.SYSTEM_ENUM_IMMUTABLE.value in ctx.result.errors

    def test_business_enum_type_update_allowed(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_update',
            params={'id': 1, 'name': 'new'},
            old_data={'id': 1, 'category': 'business', 'name': 'old'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_system_enum_type_create_blocked(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_create',
            params={'id': 'X', 'name': 'X', 'category': 'system', 'mutability': 'extensible'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ErrorCode.SYSTEM_ENUM_IMMUTABLE.value in ctx.result.errors


# ─────────────────────────────────────────────
# 边界场景
# ─────────────────────────────────────────────

class TestEdgeCases:

    def test_non_enum_object_passes(self):
        interceptor = EnumProtectionInterceptor()
        for obj in ('user', 'role', 'product', 'permission'):
            ctx = _make_context(obj, 'crud_create', params={'name': 'x'})
            interceptor.before_action(ctx)
            assert ctx.result is None, f"{obj} 应被跳过"

    def test_non_crud_action_passes(self):
        interceptor = EnumProtectionInterceptor()
        for action in ('crud_read', 'crud_query', 'query', 'list'):
            ctx = _make_context('enum_value', action)
            interceptor.before_action(ctx)
            assert ctx.result is None, f"{action} 应被跳过"

    def test_db_exception_during_lock_check_does_not_block(self):
        """DB 异常时, 拦截器应 fail-open (放行), 由业务层处理"""
        interceptor = EnumProtectionInterceptor()
        ds = Mock()
        ds.execute.side_effect = Exception('DB connection lost')
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'code': 'NEW', 'name': 'New'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        # 异常被吞掉, 不应 block (fail-open)
        assert ctx.result is None

    def test_enum_type_not_found_does_not_block_create(self):
        """找不到 enum_type 时 (罕见), 放行让业务层处理"""
        interceptor = EnumProtectionInterceptor()
        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = None
        ds.execute.return_value = cursor
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 999, 'code': 'NEW', 'name': 'New'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        # 找不到 enum_type, fail-open
        assert ctx.result is None
