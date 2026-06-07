import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
存量对象 State 采纳验证测试

覆盖 spec-backlog:
- audit_log:   pending/written/failed + 3条转换规则
- product:     is_active true/false + 2条转换规则
- version:     is_current true/false + 2条转换规则
- change_subscription: enabled true/false + enum_values 增强
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir, registry


def setup():
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)


# ============================================================
# 1. audit_log State 采纳验证
# ============================================================

def test_audit_log_has_status_enum_values():
    """测试 audit_log status 字段有 enum_values 定义"""
    print("\n=== 测试 audit_log status enum_values ===")
    
    setup()
    meta_obj = registry.get('audit_log')
    assert meta_obj is not None, "audit_log 元对象未注册"
    
    status_field = None
    for field in meta_obj.fields:
        if field.id == 'status':
            status_field = field
            break
    
    assert status_field is not None, "audit_log 缺少 status 字段"
    assert hasattr(status_field, 'enum_values'), "status 字段缺少 enum_values"
    assert status_field.enum_values is not None
    assert len(status_field.enum_values) >= 3, f"enum_values 数量不足: {len(status_field.enum_values)}"
    
    values = {ev.get('value') if isinstance(ev, dict) else ev.value: ev for ev in status_field.enum_values}
    assert 'pending' in values, "缺少 pending 状态值"
    assert 'written' in values, "缺少 written 状态值"
    assert 'failed' in values, "缺少 failed 状态值"
    
    pending = values['pending']
    if isinstance(pending, dict):
        assert pending.get('is_initial') == True, "pending 应为初始状态"
    
    print("[OK] audit_log status enum_values 配置正确")


def test_audit_log_has_status_entered_at():
    """测试 audit_log 有 status_entered_at 字段"""
    print("\n=== 测试 audit_log status_entered_at ===")
    
    meta_obj = registry.get('audit_log')
    assert meta_obj is not None, "meta_obj not found in registry"
    
    status_entered_field = None
    for field in meta_obj.fields:
        if field.id == 'status_entered_at':
            status_entered_field = field
            break
    
    assert status_entered_field is not None, "audit_log 缺少 status_entered_at 字段"
    assert status_entered_field.field_type.value == 'datetime', f"status_entered_at 类型不正确: {status_entered_field.field_type}"
    
    print("[OK] audit_log status_entered_at 字段配置正确")


def test_audit_log_state_transition_rules():
    """测试 audit_log 有3条状态转换规则"""
    print("\n=== 测试 audit_log 状态转换规则 ===")
    
    meta_obj = registry.get('audit_log')
    assert meta_obj is not None, "meta_obj not found in registry"
    
    assert hasattr(meta_obj, 'rules'), "audit_log 缺少 rules"
    assert meta_obj.rules is not None
    
    state_rules = [r for r in meta_obj.rules if hasattr(r, 'state_field') and r.state_field == 'status']
    
    rule_ids = {r.id: r for r in state_rules}
    
    assert 'mark_written' in rule_ids, "缺少 mark_written 规则"
    assert 'mark_failed' in rule_ids, "缺少 mark_failed 规则"
    assert 'retry_write' in rule_ids, "缺少 retry_write 规则"
    
    mark_written = rule_ids['mark_written']
    assert list(mark_written.from_states) == ['pending']
    assert mark_written.to_state == 'written'
    
    mark_failed = rule_ids['mark_failed']
    assert list(mark_failed.from_states) == ['pending']
    assert mark_failed.to_state == 'failed'
    
    retry_write = rule_ids['retry_write']
    assert list(retry_write.from_states) == ['failed']
    assert retry_write.to_state == 'pending'
    
    print("[OK] audit_log 状态转换规则完整正确")


# ============================================================
# 2. product State 采纳验证
# ============================================================

def test_product_state_transition_rules():
    """测试 product 有2条状态转换规则"""
    try:
        print("\n=== 测试 product 状态转换规则 ===")
        
        meta_obj = registry.get('product')
        if meta_obj is None:
            pytest.fail("product 元对象未注册")
        assert meta_obj is not None, "product 元对象未注册"
        
        if not hasattr(meta_obj, 'rules') or meta_obj.rules is None:
            pytest.fail("Missing rules in product schema")
        assert meta_obj.rules is not None
        
        state_rules = [r for r in meta_obj.rules if hasattr(r, 'state_field') and r.state_field == 'is_active']
        
        rule_ids = {r.id: r for r in state_rules}
        
        if 'activate_product' not in rule_ids:
            pytest.fail("Missing activate_product rule in product schema")
        assert 'activate_product' in rule_ids, "缺少 activate_product 规则"
        assert 'deactivate_product' in rule_ids, "缺少 deactivate_product 规则"
        
        activate = rule_ids['activate_product']
        assert list(activate.from_states) == [False]
        assert activate.to_state == True
        
        deactivate = rule_ids['deactivate_product']
        assert list(deactivate.from_states) == [True]
        assert deactivate.to_state == False
        
        ui_hints = getattr(deactivate, 'ui_hints', None)
        if ui_hints is not None:
            assert hasattr(ui_hints, 'confirm_message')
        
        print("[OK] product 状态转换规则配置正确")
    except Exception as e:
        if "skip" in str(type(e).__name__.lower()):
            raise
        pytest.fail(f"Product state transition test failed: {e}")


# ============================================================
# 3. version State 采纳验证
# ============================================================

def test_version_state_transition_rules():
    """测试 version 有2条状态转换规则"""
    print("\n=== 测试 version 状态转换规则 ===")
    
    meta_obj = registry.get('version')
    assert meta_obj is not None, "version 元对象未注册"
    
    assert hasattr(meta_obj, 'rules'), "version 缺少 rules"
    assert meta_obj.rules is not None
    
    state_rules = [r for r in meta_obj.rules if hasattr(r, 'state_field') and r.state_field == 'is_current']
    
    rule_ids = {r.id: r for r in state_rules}
    
    assert 'set_current_version' in rule_ids, "缺少 set_current_version 规则"
    assert 'unset_current_version' in rule_ids, "缺少 unset_current_version 规则"
    
    set_current = rule_ids['set_current_version']
    assert list(set_current.from_states) == [False]
    assert set_current.to_state == True
    
    unset_current = rule_ids['unset_current_version']
    assert list(unset_current.from_states) == [True]
    assert unset_current.to_state == False
    
    print("[OK] version 状态转换规则配置正确")


# ============================================================
# 4. change_subscription State 采纳验证
# ============================================================

def test_change_subscription_has_enabled_enum_values():
    """测试 change_subscription enabled 字段有 enum_values"""
    print("\n=== 测试 change_subscription enabled enum_values ===")
    
    meta_obj = registry.get('change_subscription')
    assert meta_obj is not None, "change_subscription 元对象未注册"
    
    enabled_field = None
    for field in meta_obj.fields:
        if field.id == 'enabled':
            enabled_field = field
            break
    
    assert enabled_field is not None, "change_subscription 缺少 enabled 字段"
    assert hasattr(enabled_field, 'enum_values'), "enabled 字段缺少 enum_values"
    assert enabled_field.enum_values is not None
    assert len(enabled_field.enum_values) >= 2, f"enum_values 数量不足: {len(enabled_field.enum_values)}"
    
    values = {ev.get('value') if isinstance(ev, dict) else ev.value: ev for ev in enabled_field.enum_values}
    assert True in values or 'true' in values, "缺少已启用状态值"
    assert False in values or 'false' in values, "缺少已禁用状态值"
    
    print("[OK] change_subscription enabled enum_values 配置正确")


def test_change_subscription_state_transition_rules():
    """测试 change_subscription 状态转换规则"""
    print("\n=== 测试 change_subscription 状态转换规则 ===")
    
    meta_obj = registry.get('change_subscription')
    assert meta_obj is not None, "meta_obj not found in registry"
    
    state_rules = [r for r in meta_obj.rules if hasattr(r, 'state_field') and r.state_field == 'enabled']
    
    rule_ids = {r.id: r for r in state_rules}
    
    assert 'enable_subscription' in rule_ids, "缺少 enable_subscription 规则"
    assert 'disable_subscription' in rule_ids, "缺少 disable_subscription 规则"
    
    enable_rule = rule_ids['enable_subscription']
    assert list(enable_rule.from_states) == [False]
    assert enable_rule.to_state == True
    
    disable_rule = rule_ids['disable_subscription']
    assert list(disable_rule.from_states) == [True]
    assert disable_rule.to_state == False
    
    print("[OK] change_subscription 状态转换规则配置正确")


# ============================================================
# 5. 已验证存量对象汇总验证
# ============================================================

def test_user_state_remains_correct():
    """测试 user 状态配置未受影响"""
    print("\n=== 测试 user 状态配置 ===")
    
    meta_obj = registry.get('user')
    assert meta_obj is not None
    
    state_rules = [r for r in meta_obj.rules if hasattr(r, 'state_field') and r.state_field == 'status']
    rule_ids = {r.id for r in state_rules}
    
    assert 'activate_user' in rule_ids
    assert 'lock_user' in rule_ids
    assert 'deactivate_user' in rule_ids
    
    print("[OK] user 状态配置未受影响")


def test_change_event_state_remains_correct():
    """测试 change_event 状态配置未受影响"""
    print("\n=== 测试 change_event 状态配置 ===")
    
    meta_obj = registry.get('change_event')
    assert meta_obj is not None
    
    state_rules = [r for r in meta_obj.rules if hasattr(r, 'state_field') and r.state_field == 'status']
    rule_ids = {r.id for r in state_rules}
    
    assert 'process_event' in rule_ids
    assert 'deliver_event' in rule_ids
    assert 'fail_event' in rule_ids
    assert 'retry_event' in rule_ids
    
    print("[OK] change_event 状态配置未受影响")


# ============================================================
# 运行
# ============================================================

def run_all_tests():
    print("=" * 60)
    print("存量对象 State 采纳验证测试")
    print("=" * 60)
    
    tests = [
        test_audit_log_has_status_enum_values,
        test_audit_log_has_status_entered_at,
        test_audit_log_state_transition_rules,
        test_product_state_transition_rules,
        test_version_state_transition_rules,
        test_change_subscription_has_enabled_enum_values,
        test_change_subscription_state_transition_rules,
        test_user_state_remains_correct,
        test_change_event_state_remains_correct,
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
        print("[OK] 所有存量对象 State 采纳测试通过！")
    else:
        print("[FAIL] 存在失败的测试")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
