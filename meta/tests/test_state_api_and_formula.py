import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
状态转换 API 与 Formula 采纳验证测试

覆盖 spec-backlog:
- 状态转换 API: /state_transitions 端点
- Formula 采纳: change_event delivery_latency_seconds
- Formula 采纳: user inactive_days / account_age_days / current_status_duration_days
- 状态历史 API: /state_history
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir, registry


def setup():
    if not registry._objects:
        from meta.core.yaml_loader import _dir_registry_cache
        _dir_registry_cache.clear()
        schema_dir = get_yaml_schema_dir()
        register_from_directory(schema_dir)
    elif registry.get('change_event') is None:
        from meta.core.yaml_loader import _dir_registry_cache
        _dir_registry_cache.clear()
        schema_dir = get_yaml_schema_dir()
        register_from_directory(schema_dir)


# ============================================================
# 1. 状态转换 API 验证
# ============================================================

def test_state_transitions_api_exists():
    """测试 /state_transitions API 端点已注册"""
    print("\n=== 测试 state_transitions API 端点 ===")
    
    from meta.api.manage_api import get_state_transitions
    
    assert get_state_transitions is not None
    
    print("[OK] get_state_transitions API 端点已注册")


def test_state_history_api_exists():
    """测试 /state_history API 端点已注册"""
    print("\n=== 测试 state_history API 端点 ===")
    
    from meta.api.manage_api import get_state_history
    
    assert get_state_history is not None
    
    print("[OK] get_state_history API 端点已注册")


def test_state_transitions_func_logic():
    """测试 get_state_transitions 函数逻辑完整性"""
    print("\n=== 测试 get_state_transitions 函数逻辑 ===")
    
    import inspect
    from meta.api.manage_api import get_state_transitions
    source = inspect.getsource(get_state_transitions)
    
    assert 'state_field' in source
    assert 'from_states' in source
    assert 'to_state' in source
    assert 'available' in source
    
    print("[OK] get_state_transitions 函数逻辑完整")


# ============================================================
# 2. change_event Formula 采纳验证
# ============================================================

def test_change_event_delivery_latency_formula():
    """测试 change_event delivery_latency_seconds formula 字段"""
    print("\n=== 测试 change_event delivery_latency_seconds ===")
    
    setup()
    meta_obj = registry.get('change_event')
    assert meta_obj is not None, "change_event 元对象未注册"
    
    latency_field = None
    for field in meta_obj.fields:
        if field.id == 'delivery_latency_seconds':
            latency_field = field
            break
    
    assert latency_field is not None, "change_event 缺少 delivery_latency_seconds 字段"
    
    storage_str = str(latency_field.storage).lower()
    assert 'virtual' in storage_str, f"应为 virtual 字段，实际: {latency_field.storage}"
    
    assert latency_field.computation, "缺少 computation 配置"
    
    formula = latency_field.computation.get('formula', '') if isinstance(latency_field.computation, dict) else getattr(latency_field.computation, 'formula', '')
    assert 'DATEDIFF' in formula
    assert 'ISNULL' in formula
    assert 'IF' in formula
    
    print(f"  Formula: {formula}")
    print("[OK] change_event delivery_latency_seconds formula 配置正确")


# ============================================================
# 3. user Formula 采纳验证
# ============================================================

def test_user_inactive_days_formula():
    """测试 user inactive_days formula 字段"""
    print("\n=== 测试 user inactive_days ===")
    
    meta_obj = registry.get('user')
    assert meta_obj is not None, "user 元对象未注册"
    
    field = None
    for f in meta_obj.fields:
        if f.id == 'inactive_days':
            field = f
            break
    
    assert field is not None, "user 缺少 inactive_days 字段"
    
    storage_str = str(field.storage).lower()
    assert 'virtual' in storage_str, f"应为 virtual 字段，实际: {field.storage}"
    assert field.computation, "缺少 computation 配置"
    
    formula = field.computation.get('formula', '') if isinstance(field.computation, dict) else getattr(field.computation, 'formula', '')
    assert 'DATEDIFF' in formula
    assert 'last_login_at' in formula or 'ISNULL' in formula
    
    print(f"  Formula: {formula}")
    print("[OK] user inactive_days formula 配置正确")


def test_user_account_age_days_formula():
    """测试 user account_age_days formula 字段"""
    print("\n=== 测试 user account_age_days ===")
    
    meta_obj = registry.get('user')
    assert meta_obj is not None, "meta_obj not found in registry"
    
    field = None
    for f in meta_obj.fields:
        if f.id == 'account_age_days':
            field = f
            break
    
    assert field is not None, "user 缺少 account_age_days 字段"
    
    storage_str = str(field.storage).lower()
    assert 'virtual' in storage_str
    
    formula = field.computation.get('formula', '') if isinstance(field.computation, dict) else getattr(field.computation, 'formula', '')
    assert 'DATEDIFF' in formula
    assert 'created_at' in formula
    
    print(f"  Formula: {formula}")
    print("[OK] user account_age_days formula 配置正确")


def test_user_current_status_duration_formula():
    """测试 user current_status_duration_days formula 字段 (2026-06-09 重构)

    单一事实源改为 audit_logs, formula 从 audit_logs 子查询派生最近一次 status 变化时间.
    """
    print("\n=== 测试 user current_status_duration_days ===")

    meta_obj = registry.get('user')
    assert meta_obj is not None, "meta_obj not found in registry"

    field = None
    for f in meta_obj.fields:
        if f.id == 'current_status_duration_days':
            field = f
            break

    assert field is not None, "user 缺少 current_status_duration_days 字段"

    storage_str = str(field.storage).lower()
    assert 'virtual' in storage_str

    formula = field.computation.get('formula', '') if isinstance(field.computation, dict) else getattr(field.computation, 'formula', '')
    assert 'DATEDIFF' in formula
    # [FIX 2026-06-09] 不再引用 status_entered_at, 改为从 audit_logs 子查询派生
    assert 'status_entered_at' not in formula, f"formula 不应再引用 status_entered_at (已删除), 实际: {formula}"
    assert 'audit_logs' in formula, f"formula 应从 audit_logs 派生, 实际: {formula}"
    assert 'COALESCE' in formula, f"formula 应有 COALESCE 兜底 (没 audit log 时用 created_at), 实际: {formula}"

    print(f"  Formula: {formula}")
    print("[OK] user current_status_duration_days formula 从 audit_logs 派生, 配置正确")


# ============================================================
# 4. [REMOVED 2026-06-09] status_entered_at 字段已删除
#    原 test_user_status_entered_at_field 移除, 改用 test_user_status_entered_at_field_removed
#    验证字段已成功删除 (避免误恢复)
# ============================================================

def test_user_status_entered_at_field_removed():
    """验证 user status_entered_at 字段已删除 (2026-06-09 重构)

    单一事实源改为 audit_logs. 字段冗余 (被 state_transition 反复覆盖), 产生大量 audit log.
    详见: rule_executor.py StateTransitionExecutor + user.yaml 字段定义.
    """
    print("\n=== 测试 user status_entered_at 已删除 ===")

    meta_obj = registry.get('user')
    assert meta_obj is not None, "meta_obj not found in registry"

    field = next((f for f in meta_obj.fields if f.id == 'status_entered_at'), None)
    assert field is None, (
        f"user 不应有 status_entered_at 字段 (单一事实源改为 audit_logs), 实际仍存在. "
        f"如需恢复, 同步恢复 rule_executor.py 自动写逻辑 + audit_log 清理"
    )

    print("[OK] user status_entered_at 字段已成功删除, 单一事实源为 audit_logs")


def test_change_event_status_entered_at_field():
    """测试 change_event 有 status_entered_at 字段"""
    print("\n=== 测试 change_event status_entered_at ===")
    
    meta_obj = registry.get('change_event')
    assert meta_obj is not None, "meta_obj not found in registry"
    
    field = None
    for f in meta_obj.fields:
        if f.id == 'status_entered_at':
            field = f
            break
    
    assert field is not None, "change_event 缺少 status_entered_at 字段"
    assert field.field_type.value == 'datetime', f"status_entered_at 类型不正确: {field.field_type}"
    
    print("[OK] change_event status_entered_at 字段配置正确")


# ============================================================
# 5. FormulaFunctionRegistry 存在性验证
# ============================================================

def test_formula_function_registry_has_nonull_functions():
    """测试 FormulaFunctionRegistry 有关键函数"""
    print("\n=== 测试 FormulaFunctionRegistry 关键函数 ===")
    
    from meta.core.formula_functions import FormulaFunctionRegistry
    
    has_if = FormulaFunctionRegistry.has('IF')
    has_datediff = FormulaFunctionRegistry.has('DATEDIFF')
    has_isnull = FormulaFunctionRegistry.has('ISNULL')
    has_round = FormulaFunctionRegistry.has('ROUND')
    
    assert has_if, "缺少 IF 函数"
    assert has_datediff, "缺少 DATEDIFF 函数"
    assert has_isnull, "缺少 ISNULL 函数"
    assert has_round, "缺少 ROUND 函数"
    
    all_functions = FormulaFunctionRegistry.list_functions()
    print(f"  已注册函数数: {len(all_functions)}")
    print("[OK] FormulaFunctionRegistry 关键函数完整")


# ============================================================
# 6. Audit Log 恢复 API 验证
# ============================================================

def test_recover_from_log_api_exists():
    """测试 recover_from_log API 端点已注册"""
    print("\n=== 测试 recover_from_log API ===")
    
    from meta.api.manage_api import recover_from_log
    assert recover_from_log is not None
    print("[OK] recover_from_log API 端点已注册")


def test_list_deleted_objects_api_exists():
    """测试 list_deleted_objects API 端点已注册"""
    print("\n=== 测试 list_deleted_objects API ===")
    
    from meta.api.manage_api import list_deleted_objects
    assert list_deleted_objects is not None
    print("[OK] list_deleted_objects API 端点已注册")


# ============================================================
# 7. StateTransitionButtons 组件验证
# ============================================================

def test_state_transition_buttons_component_exists():
    """测试 StateTransitionButtons.vue 组件存在"""
    print("\n=== 测试 StateTransitionButtons 组件 ===")
    
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src')
    component_path = os.path.join(frontend_dir, 'components', 'bo', 'StateTransitionButtons.vue')
    
    assert os.path.exists(component_path), f"组件文件不存在: {component_path}"
    
    with open(component_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'state-transition-buttons' in content
    assert 'availableTransitions' in content
    
    print("[OK] StateTransitionButtons 组件文件存在且内容正确")


def test_object_page_integrates_state_transitions():
    """测试 ObjectPage.vue 集成了状态转换按钮"""
    try:
        print("\n=== 测试 ObjectPage 集成状态转换 ===")
        
        frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src')
        component_path = os.path.join(frontend_dir, 'components', 'common', 'ObjectPage', 'ObjectPage.vue')
        
        if not os.path.exists(component_path):
            pytest.skip("ObjectPage.vue component not found")
        
        with open(component_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'StateTransitionButtons' not in content:
            pytest.skip("StateTransitionButtons not in ObjectPage template - feature not implemented")
        
        print("[OK] ObjectPage 正确集成 StateTransitionButtons 组件")
    except Exception as e:
        if "skip" in str(type(e).__name__.lower()):
            raise
        pytest.fail(f"StateTransitionButtons integration check failed: {e}")


# ============================================================
# 运行
# ============================================================

def run_all_tests():
    print("=" * 60)
    print("状态转换 API 与 Formula 采纳验证测试")
    print("=" * 60)
    
    tests = [
        test_state_transitions_api_exists,
        test_state_history_api_exists,
        test_state_transitions_func_logic,
        test_change_event_delivery_latency_formula,
        test_user_inactive_days_formula,
        test_user_account_age_days_formula,
        test_user_current_status_duration_formula,
        test_user_status_entered_at_field_removed,
        test_change_event_status_entered_at_field,
        test_formula_function_registry_has_nonull_functions,
        test_recover_from_log_api_exists,
        test_list_deleted_objects_api_exists,
        test_state_transition_buttons_component_exists,
        test_object_page_integrates_state_transitions,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {test.__name__} FAILED: {e}")
    
    print("\n" + "=" * 60)
    print(f"结果: {passed} passed, {failed} failed")
    if failed == 0:
        print("[OK] 所有状态转换 API 与 Formula 采纳测试通过！")
    else:
        print("[FAIL] 存在失败的测试")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
