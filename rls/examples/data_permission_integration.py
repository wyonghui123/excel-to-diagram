"""
DataPermissionInterceptor 集成示例（D3）

本文件展示如何在 DataPermissionInterceptor._apply_scope_filter 中集成 rls.get_active_row_filter。
不直接修改现有拦截器，而是在用户的代码中集成。

关键点：
- DataPermissionInterceptor 已有 scope 表达式处理
- rls.get_active_row_filter 提供 YAML 化版本
- 业务方可以选择：YAML 优先 或 YAML fallback
"""
from rls import get_active_row_filter


# 示例 1：YAML 优先（无 YAML 时回退到现有 scope）
def integrate_with_data_permission_interceptor(user_role, entity, current_scope_expr, user_id, rules_dir=None):
    """DataPermissionInterceptor 集成入口

    Args:
        user_role: 角色
        entity: 实体
        current_scope_expr: 现有 scope 表达式（meta_object.authorization.scope）
        user_id: 用户 ID
        rules_dir: rls_rules 目录

    Returns:
        str: 解析后的 scope 表达式

    行为：
    1. 尝试从 YAML 读规则
    2. 有 → 用 YAML 的 condition（替换 $user.id 变量）
    3. 无 → 用现有 scope_expr（同样替换 $user.id 变量）
    """
    rls_filter = get_active_row_filter(user_role, entity, rules_dir)
    if rls_filter:
        # YAML 优先
        return rls_filter.replace('$user.id', str(user_id))
    # 回退到现有 scope 表达式（同样替换 $user.id）
    return current_scope_expr.replace('$user.id', str(user_id))


# 示例 2：直接调用（无回退）
def get_rls_filter_only(user_role, entity, user_id):
    """仅从 YAML 读（无回退）

    返回 None 时表示无规则（业务方需自己处理）
    """
    rls_filter = get_active_row_filter(user_role, entity)
    if rls_filter:
        return rls_filter.replace('$user.id', str(user_id))
    return None


# 示例 3：DSL 解析占位（实际需要 DSL 引擎）
def parse_condition_to_sql_filter(condition, user_id, current_user_company_id):
    """将 YAML condition 字符串解析为 SQL where 子句

    注意：此函数为占位示例，实际需要 DSL 引擎。
    当前 YAML 规则的 condition 是简化的字符串，应用时需要：
    1. 提取变量（$user.id / user.company_id / ...）
    2. 替换为实际值
    3. 生成对应的 SQL where 条件
    """
    # 占位实现：简单变量替换
    resolved = condition
    resolved = resolved.replace('$user.id', str(user_id))
    if 'user.company_id' in resolved:
        resolved = resolved.replace('user.company_id', str(current_user_company_id))
    return resolved


if __name__ == '__main__':
    import os
    tmpdir = os.path.join(os.path.dirname(__file__), '..', 'tests', '_tmp_demo')
    os.makedirs(tmpdir, exist_ok=True)
    yaml_path = os.path.join(tmpdir, 'order.yaml')
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write("""
entity: order
row_filters:
  - applies_to: [role:user]
    condition: "user.company_id == order.company_id"
  - applies_to: [role:admin]
    condition: "true"
""")
    print(integrate_with_data_permission_interceptor(
        'user', 'order', 'order.user_id = $user.id', user_id=5
    ))
    # 'user.company_id == order.company_id'
    print(integrate_with_data_permission_interceptor(
        'admin', 'order', 'order.user_id = $user.id', user_id=5
    ))
    # 'true'
    print(integrate_with_data_permission_interceptor(
        'viewer', 'order', 'order.user_id = $user.id', user_id=5
    ))
    # 'order.user_id = 5' (回退)
