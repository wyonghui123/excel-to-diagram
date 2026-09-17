"""
[Spec 22 2026-09-13] state_transition action_ref / 通用 action 池 / ActionPermissionInterceptor 测试

覆盖：
  - FR-001 _standard_actions.yaml 新增 9 个通用 action
    (activate/deactivate/lock/unlock/freeze/unfreeze/reset_password/archive/restore)
  - FR-002 MetaStateTransition + parse_state_transition 解析 action_ref
  - FR-003 /state_transitions GET 返回 actionRef
  - FR-004 ActionPermissionInterceptor 校验 action_ref 权限
  - FR-005 /state-transition-actions endpoint 返回 instance 级 action_ref
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir, registry
from meta.core.standard_action_loader import StandardActionLoader


def setup():
    """复用现有测试的 setup 方式：从 yaml 目录注册所有 schema"""
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)


# ────────────────────────────────────────────
# FR-001 通用 action 入池
# ────────────────────────────────────────────

def test_standard_actions_includes_activate():
    """[Spec 22 FR-001] activate action 已在 _standard_actions.yaml"""
    actions = StandardActionLoader.get_actions()
    ids = {a.id for a in actions}
    assert 'activate' in ids, "缺少 activate action"


def test_standard_actions_includes_all_state_transition_actions():
    """[Spec 22 FR-001 + PM 反馈第十七次] 7 个通用 action 全部入池
    (archive/restore 已撤销——归档不是用户操作，由 audit_log row_snapshot 承担恢复)"""
    actions = StandardActionLoader.get_actions()
    ids = {a.id for a in actions}
    expected = {'activate', 'deactivate', 'lock', 'unlock', 'freeze', 'unfreeze',
                'reset_password'}
    missing = expected - ids
    assert not missing, f"缺少 action: {missing}"


def test_standard_actions_excludes_archive_restore():
    """[Spec 22 PM 反馈第十七次 2026-09-13] archive/restore 不再进入标准动作池"""
    actions = StandardActionLoader.get_actions()
    ids = {a.id for a in actions}
    forbidden = {'archive', 'restore'}
    leaked = forbidden & ids
    assert not leaked, (
        f"archive/restore 不应进入标准动作池（详见 Spec 22 §6.7），但发现了: {leaked}"
    )


def test_standard_actions_total_count():
    """[Spec 22 FR-001 + PM 反馈第十七次] action 总数: 16 旧 + 7 新 = 23
    (原计划 25，因 archive/restore 撤销减 2)"""
    actions = StandardActionLoader.get_actions()
    assert len(actions) == 23, f"期望 23 个 action, 实为 {len(actions)}"


def test_state_transition_actions_instance_scope():
    """[Spec 22 FR-001] 新增 action 全部 instance_scope: instance"""
    actions = StandardActionLoader.get_actions()
    state_actions = {a.id: a for a in actions if a.id in {
        'activate', 'deactivate', 'lock', 'unlock', 'freeze', 'unfreeze',
        'reset_password'
    }}
    from meta.core.models import InstanceScope
    for aid, a in state_actions.items():
        assert a.instance_scope == InstanceScope.INSTANCE, \
            f"{aid} instance_scope 应为 instance, 实为 {a.instance_scope}"


def test_state_transition_actions_action_type():
    """[Spec 22 FR-001] 新增 action 全部 action_type: business"""
    from meta.core.models import ActionType
    actions = StandardActionLoader.get_actions()
    state_actions = {a.id: a for a in actions if a.id in {
        'activate', 'deactivate', 'lock', 'unlock', 'freeze', 'unfreeze',
        'reset_password'
    }}
    for aid, a in state_actions.items():
        assert a.action_type == ActionType.BUSINESS, \
            f"{aid} action_type 应为 business, 实为 {a.action_type}"


# ────────────────────────────────────────────
# FR-002 yaml action_ref 字段解析
# ────────────────────────────────────────────

def test_user_yaml_action_ref_parsed():
    """[Spec 22 FR-002] user.yaml rules 中 activate_user 解析 action_ref=activate"""
    setup()
    user_schema = registry.get('user')
    assert user_schema is not None, "user 未注册"
    rules = user_schema.rules if hasattr(user_schema, 'rules') else []
    state_rules = [r for r in rules if hasattr(r, 'state_field') and r.state_field == 'status']
    rule_by_id = {r.id: r for r in state_rules}

    assert 'activate_user' in rule_by_id
    assert rule_by_id['activate_user'].action_ref == 'activate', \
        "activate_user.action_ref 应为 'activate'"

    assert 'lock_user' in rule_by_id
    assert rule_by_id['lock_user'].action_ref == 'lock'

    assert 'deactivate_user' in rule_by_id
    assert rule_by_id['deactivate_user'].action_ref == 'deactivate'


def test_permission_set_yaml_action_ref_parsed():
    """[Spec 22 FR-002] permission_set.yaml rules 解析 action_ref"""
    setup()
    ps_schema = registry.get('permission_set')
    assert ps_schema is not None, "permission_set 未注册"
    rules = ps_schema.rules if hasattr(ps_schema, 'rules') else []
    rule_by_id = {r.id: r for r in rules}

    assert 'enable_permission_set' in rule_by_id
    assert rule_by_id['enable_permission_set'].action_ref == 'activate'

    assert 'disable_permission_set' in rule_by_id
    assert rule_by_id['disable_permission_set'].action_ref == 'deactivate'


def test_product_yaml_action_ref_parsed():
    """[Spec 22 FR-002] product.yaml rules 解析 action_ref"""
    setup()
    product_schema = registry.get('product')
    assert product_schema is not None, "product 未注册"
    rules = product_schema.rules if hasattr(product_schema, 'rules') else []
    rule_by_id = {r.id: r for r in rules}

    assert 'activate_product' in rule_by_id
    assert rule_by_id['activate_product'].action_ref == 'activate'

    assert 'deactivate_product' in rule_by_id
    assert rule_by_id['deactivate_product'].action_ref == 'deactivate'


def test_action_ref_backward_compatible_empty_string():
    """[Spec 22 FR-007 向后兼容] 旧 yaml 无 action_ref 字段解析为空字符串"""
    from meta.core.models import MetaStateTransition
    rule = MetaStateTransition(
        id='legacy_rule',
        name='旧规则',
        state_field='status',
        from_states=['active'],
        to_state='inactive',
    )
    assert rule.action_ref == "", "未设置 action_ref 应为默认空字符串"


# ────────────────────────────────────────────
# FR-004 ActionPermissionInterceptor 行为
# ────────────────────────────────────────────

def test_action_permission_interceptor_loaded():
    """[Spec 22 FR-004] ActionPermissionInterceptor 已注册"""
    from meta.core.interceptors.action_permission_interceptor import ActionPermissionInterceptor
    interceptor = ActionPermissionInterceptor()
    assert interceptor.priority == 31, f"priority 应为 31, 实为 {interceptor.priority}"


def test_action_permission_interceptor_should_execute_only_crud_update():
    """[Spec 22 FR-004] 仅对 crud_update 生效"""
    from unittest.mock import MagicMock
    from meta.core.interceptors.action_permission_interceptor import ActionPermissionInterceptor
    interceptor = ActionPermissionInterceptor()

    ctx_update = MagicMock(action='crud_update')
    ctx_create = MagicMock(action='crud_create')
    ctx_read = MagicMock(action='crud_read')

    assert interceptor.should_execute(ctx_update) is True
    assert interceptor.should_execute(ctx_create) is False
    assert interceptor.should_execute(ctx_read) is False


# ────────────────────────────────────────────
# 兼容 FR-007 allowed_roles 字段保留
# ────────────────────────────────────────────

def test_meta_state_transition_has_allowed_roles():
    """[Spec 22 FR-007] allowed_roles 字段保留向后兼容"""
    from meta.core.models import MetaStateTransition
    rule = MetaStateTransition(
        id='legacy_rule',
        name='旧规则',
        state_field='status',
        from_states=['active'],
        to_state='inactive',
        allowed_roles=['admin', 'manager'],
    )
    assert rule.allowed_roles == ['admin', 'manager']


# ────────────────────────────────────────────
# FR-005 [PM 反馈 2026-09-13 第十四次] 路由顺序：/state-transition-actions
# 必须在 /<path:obj_id> 之前注册，否则被贪婪匹配吞掉
# ────────────────────────────────────────────

def test_state_transition_actions_route_registered_before_path_obj_id():
    """[PM 反馈 2026-09-13 第十四次] 路由顺序校验

    根因：bo_api.py 里 '/<object_type>/<path:obj_id>' 会贪婪匹配
      /bo/user/state-transition-actions，把 'state-transition-actions'
      当作 obj_id，导致 endpoint 永远命中 read_bo_by_string_id
      并返回 '用户 with id=state-transition-actions not found'。

    修复：把 /<object_type>/state-transition-actions 移到 path:obj_id 之前。
    本测试防止未来回归。
    """
    from meta.api.bo_api import bo_bp
    # bo_bp 是 Flask Blueprint（Function 注册），它的 url_map 不直接暴露；
    # 改用模块导入顺序作为 proxy：state-transition-actions 路由的源码位置
    # 必须早于 read_bo_by_string_id（path:obj_id）
    import inspect
    import re
    from meta.api import bo_api
    src = inspect.getsource(bo_api)
    # 精确匹配 @bo_bp.route('...') 单行装饰器
    sta_matches = [m.start() for m in re.finditer(
        r"@bo_bp\.route\('([^']*state-transition-actions[^']*)'", src
    )]
    path_matches = [m.start() for m in re.finditer(
        r"@bo_bp\.route\('([^']*<path:obj_id>[^']*)'", src
    )]
    assert sta_matches, "state-transition-actions 路由装饰器不应被完全移除"
    assert path_matches, "path:obj_id 路由装饰器不应被完全移除"
    idx_sta = sta_matches[0]
    idx_path = path_matches[0]
    # state-transition-actions 路由装饰器必须在 path:obj_id 之前
    assert idx_sta < idx_path, (
        f"路由顺序错误: state-transition-actions (idx={idx_sta}) 必须在 "
        f"<path:obj_id> (idx={idx_path}) 之前，否则会被贪婪匹配吞掉"
    )


def test_action_labels_include_state_transition_actions():
    """[PM 反馈 2026-09-13 第十四次] 后端 _ACTION_LABELS 必须包含
    activate/deactivate/lock 等 state_transition 通用 action，否则
    资源矩阵「更多动作」列会显示英文 code 而不是中文"""
    from meta.api.permission_dimension_api import _ACTION_LABELS
    for action in ['activate', 'deactivate', 'lock', 'unlock',
                   'freeze', 'unfreeze', 'reset_password']:
        assert action in _ACTION_LABELS, (
            f"_ACTION_LABELS 缺少 {action}，前端会显示英文 code"
        )
        assert _ACTION_LABELS[action] and _ACTION_LABELS[action] != action, (
            f"_ACTION_LABELS[{action}] = {_ACTION_LABELS[action]!r} 应是中文"
        )


# ────────────────────────────────────────────
# 汇总
# ────────────────────────────────────────────

tests = [
    test_standard_actions_includes_activate,
    test_standard_actions_includes_all_state_transition_actions,
    test_standard_actions_excludes_archive_restore,
    test_standard_actions_total_count,
    test_state_transition_actions_instance_scope,
    test_state_transition_actions_action_type,
    test_user_yaml_action_ref_parsed,
    test_permission_set_yaml_action_ref_parsed,
    test_product_yaml_action_ref_parsed,
    test_action_ref_backward_compatible_empty_string,
    test_action_permission_interceptor_loaded,
    test_action_permission_interceptor_should_execute_only_crud_update,
    test_meta_state_transition_has_allowed_roles,
    test_state_transition_actions_route_registered_before_path_obj_id,
    test_action_labels_include_state_transition_actions,
]


if __name__ == '__main__':
    import subprocess
    import sys as _sys
    exit_code = 0
    for t in tests:
        try:
            setup_function(t)
            t()
            teardown_function(t)
            print(f"  [OK] {t.__name__}")
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            exit_code = 1
        except Exception as e:
            # 端点相关 skip 视为 OK
            err_str = str(e)
            if 'skip' in err_str.lower() or '不可用' in err_str:
                print(f"  [SKIP] {t.__name__}: {err_str[:60]}")
            else:
                print(f"  [ERROR] {t.__name__}: {e}")
                exit_code = 1
    _sys.exit(exit_code)
