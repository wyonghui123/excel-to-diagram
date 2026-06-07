"""
FieldPolicyInterceptor 集成示例（D3）

本文件展示如何在 FieldPolicyInterceptor.after_action 中集成 rls.apply_field_masks。
不直接修改现有拦截器，而是在用户代码中集成。

关键点：
- FieldPolicyInterceptor 已有 mask 规则（FieldPolicyValidationInterceptor）
- rls.apply_field_masks 提供 YAML 化版本
- 集成时需要放在 after_action 阶段（对返回结果脱敏）
"""
from rls import apply_field_masks, apply_field_masks_to_list


# 示例 1：在 after_action 集成
def integrate_with_field_policy_interceptor_after_action(user_role, entity, result, rules_dir=None):
    """FieldPolicyInterceptor.after_action 集成入口

    Args:
        user_role: 角色
        entity: 实体
        result: 查询结果（dict 或 list of dict）
        rules_dir: rls_rules 目录

    Returns:
        脱敏后的 result

    行为：
    1. 检查 result 类型
    2. dict → apply_field_masks
    3. list → apply_field_masks_to_list
    4. 其他 → 原样返回
    """
    if isinstance(result, list):
        return apply_field_masks_to_list(user_role, entity, result, rules_dir)
    elif isinstance(result, dict):
        return apply_field_masks(user_role, entity, result, rules_dir)
    return result


# 示例 2：单字段脱敏（高级用法）
def mask_single_field(user_role, entity, field, value, rules_dir=None):
    """对单个字段应用 mask

    用法：result = mask_single_field(user.role, 'order', 'phone', '13800001234')
    """
    data = {field: value}
    masked = apply_field_masks(user_role, entity, data, rules_dir)
    return masked.get(field, value)


# 示例 3：条件脱敏（不同角色不同 mask）
def conditional_mask(user_role, entity, data):
    """根据角色应用不同脱敏策略

    注意：apply_field_masks 已经按 role 过滤，
    业务方无需再判断 user_role。
    """
    return apply_field_masks(user_role, entity, data)


if __name__ == '__main__':
    import os
    tmpdir = os.path.join(os.path.dirname(__file__), '..', 'tests', '_tmp_demo')
    os.makedirs(tmpdir, exist_ok=True)
    yaml_path = os.path.join(tmpdir, 'order.yaml')
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write("""
entity: order
field_masks:
  - field: phone
    mask: "***-****-{}"
    applies_to: [role:user, role:viewer]
  - field: amount
    mask: "***"
    applies_to: [role:viewer]
""")
    # 测试单条
    data = {'id': 1, 'phone': '13800001234', 'amount': 1000}
    print(apply_field_masks('user', 'order', data, tmpdir))
    # {'id': 1, 'phone': '***-****-1234', 'amount': 1000}
    # 测试 list
    data_list = [
        {'id': 1, 'phone': '13800001234'},
        {'id': 2, 'phone': '13800005678'},
    ]
    print(apply_field_masks_to_list('user', 'order', data_list, tmpdir))
    # [{'id': 1, 'phone': '***-****-1234'}, {'id': 2, 'phone': '***-****-5678'}]
