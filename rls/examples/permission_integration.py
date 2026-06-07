"""
PermissionInterceptor 集成示例（D3）

本文件展示如何在 PermissionInterceptor.before_action 中集成 rls.check_action。
不直接修改 meta/core/interceptors/permission_interceptor.py（避免破坏现有逻辑），
而是在用户的拦截器中（或在继承类中）添加集成代码。

集成方式（推荐）：

```python
# meta/core/interceptors/permission_interceptor_v2.py
from rls import check_action

class PermissionInterceptorV2(PermissionInterceptor):
    \"\"\"V2 版本：在 V1 基础上增加 YAML 集中化\"\"\"
    def before_action(self, context):
        # V1 原有逻辑
        super().before_action(context)
        # V2 新增：YAML 集中化检查
        user = get_current_user()
        if user and context.action.startswith('crud_'):
            action_suffix = self._get_permission_suffix(context.action)
            if not check_action(user.role, context.object_type, action_suffix):
                raise PermissionDenied(
                    f'RLS: {user.role} cannot {action_suffix} {context.object_type}'
                )
```
"""
from rls import check_action
from rls.enforce import check_action as check_action_direct


# 示例 1：基础集成
def integrate_with_permission_interceptor(user_role, entity, action_suffix, rules_dir=None):
    """PermissionInterceptor 集成入口

    Args:
        user_role: 当前用户角色（来自 JWT）
        entity: 实体名（context.object_type）
        action_suffix: 'create' / 'read' / 'update' / 'delete' / 'list'
        rules_dir: rls_rules 目录（None = 默认）

    Returns:
        bool: True=允许 / False=拒绝
    """
    return check_action(user_role, entity, action_suffix, rules_dir)


# 本地 PermissionDenied 异常（避免 meta.core.interceptors 依赖问题）
class _RLSPermissionDenied(Exception):
    """M11 RLS 默认拒绝异常"""
    pass


# 示例 2：失败时抛出 PermissionDenied
def check_or_raise(user_role, entity, action_suffix, rules_dir=None, denied_class=None):
    """检查 + 失败时抛错（推荐用法）

    Args:
        user_role: 角色
        entity: 实体
        action_suffix: 操作
        rules_dir: rls_rules 目录
        denied_class: 自定义异常类（默认 _RLSPermissionDenied）

    Raises:
        Exception: 拒绝时抛 denied_class
    """
    if not check_action(user_role, entity, action_suffix, rules_dir):
        if denied_class is None:
            denied_class = _RLSPermissionDenied
        raise denied_class(
            f'RLS denied: role={user_role} action={action_suffix} entity={entity}'
        )


# 示例 3：批量检查
def check_batch(user_role, entity, action_suffixes, rules_dir=None):
    """批量检查多个操作

    Returns:
        dict: {action_suffix: bool}
    """
    return {
        action: check_action(user_role, entity, action, rules_dir)
        for action in action_suffixes
    }


if __name__ == '__main__':
    # 演示
    import os
    tmpdir = os.path.join(os.path.dirname(__file__), '..', 'tests', '_tmp_demo')
    os.makedirs(tmpdir, exist_ok=True)
    yaml_path = os.path.join(tmpdir, 'order.yaml')
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write("""
entity: order
actions:
  create: [role:admin, role:manager]
  read: [role:admin, role:manager, role:user]
  update: [role:admin, role:manager]
  delete: [role:admin]
""")
    print(check_action('admin', 'order', 'create', tmpdir))  # True
    print(check_action('user', 'order', 'create', tmpdir))   # False
    print(check_action('user', 'order', 'read', tmpdir))     # True
    print(check_batch('user', 'order', ['create', 'read', 'update', 'delete']))
    # {'create': False, 'read': True, 'update': False, 'delete': False}
