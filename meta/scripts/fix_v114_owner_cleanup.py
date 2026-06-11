"""V1.1.4: 彻底清理子对象的 owner 字段定义和 list column

清理路径 (类似 V1.1.2 visibility):
- 所有子对象 (version/domain/sub_domain/service_module/business_object/relationship)
  删 effective_owner_id_display / owner_id_display list column
- version.yaml 删 owner_id 字段定义 (DB 列已删, 字段定义无意义)
- business_object.yaml 删 aspects 中 owner_id 引用

保留:
- product.yaml 的 owner_id (顶层 owner)
- scope 里的 owner_id 引用 (用于权限判断)
- aspects.yaml / shared_properties.yaml 的共享定义
- 注释掉的 - id: owner_id (历史记录)
"""
import io
import os
import sys

CHANGES = [
    # (file, old_str, new_str)
    # 1. version.yaml L165-175: 删 owner_id_display list column
    (
        'meta/schemas/version.yaml',
        """      - key: owner_id_display
        title: 负责人
        width: 100
        position: 5
        importance: low
        editable: false          # [FIX v1.0.9 2026-06-10] 列表中不可编辑
        hidden_in_form: true     # [FIX v1.0.9 2026-06-10] inline 新增/编辑时不显示
        # [V1.1.1 2026-06-10] UI 隐藏 - version.owner_id 已删除, 此字段无意义
        visible: false
        hidden_in_list: true
        # 防止用户绕过 visibility 限制改 owner（应使用 transfer action）
""",
        """      # [V1.1.4 2026-06-11] 删 owner_id_display 列 - 顶层 owner 已在 product
"""
    ),

    # 2. version.yaml L417-468: 删 owner_id 字段定义整段
    (
        'meta/schemas/version.yaml',
        """  - id: owner_id
    name: 负责人
    type: integer
    db_column: owner_id
    description: 版本负责人ID (V1.1 已删除 DB 列, 仅保留 schema 兼容)
    ui:
      visible: false           # [V1.1.1 2026-06-10] UI 全部隐藏 - version.owner_id DB 列已删除
      editable: false          # [FIX 2026-06-10 v1.0.9] 不可编辑, 防止绕过 visibility
      hidden_in_form: true     # [FIX 2026-06-10 v1.0.9] 表单中隐藏（auto_owner 后端注入）
      hidden_in_list: true     # [V1.1.1 2026-06-10] 列表中也隐藏
      widget: select
      relation: user
      display_field: display_name
      fieldGroup: 系统信息
      i18n_key: common.field.owner_id
    semantics:
      meaning: 版本的负责人，关联用户表
      immutable: true          # [FIX 2026-06-10 v1.0.9] update 时由 _filter_immutable_fields 过滤
      export_visible: false
      import_visible: false
      analytics:
        category: dimension
        type: foreign_key
        display_name: 负责人
      # [FIX 2026-06-10 v1.0.9] 创建时由 OwnerAutoPermissionInterceptor 自动注入 current_user
      # 任何前端/API 直接传 owner_id 都会被覆盖
      # 修改 owner 必须使用专门的 transfer action（待实施）
    value_help:
      source:
        type: bo
        target_bo: user
        value_field: id
        display_field: display_name
        code_field: username
        apply_target_permissions: false
      behavior:
        validation: true
        binding_strength: strict
        search_fields: [username, display_name]
      presentation:
        result_type: dialog
        display_format: "{display_name} ({username})"
        columns:
          - field: username
            label: 用户名
            width: 120
          - field: display_name
            label: 显示名称
            width: 150
          - field: email
            label: 邮箱
            width: 200

""",
        """  # [V1.1.4 2026-06-11] 删 owner_id 字段定义 - DB 列 V1.1.1 已删, 顶层 owner 在 product
"""
    ),

    # 3. domain.yaml L227-236: 删 effective_owner_id_display list column
    (
        'meta/schemas/domain.yaml',
        """      # 🆕 v1.1: 负责人从 product 派生 (FR-006)
      # [V1.1.1 2026-06-10] UI 隐藏 - 领域是产品内部结构, 负责人由 product 决定
      - key: effective_owner_id_display
        title: 负责人
        width: 100
        position: 5
        importance: low
        visible: false
        hidden_in_list: true
        hidden_in_form: true
""",
        """      # [V1.1.4 2026-06-11] 删 effective_owner_id_display - 顶层 owner 已在 product
"""
    ),

    # 4. sub_domain.yaml L229-238: 删 effective_owner_id_display list column
    (
        'meta/schemas/sub_domain.yaml',
        """      # 🆕 v1.1: 负责人从 product 派生
      # [V1.1.1 2026-06-10] UI 隐藏 - 子领域跟随 product
      - key: effective_owner_id_display
        title: 负责人
        width: 100
        position: 5
        importance: low
        visible: false
        hidden_in_list: true
        hidden_in_form: true
""",
        """      # [V1.1.4 2026-06-11] 删 effective_owner_id_display - 顶层 owner 已在 product
"""
    ),

    # 5. service_module.yaml L233-242: 删 effective_owner_id_display list column
    (
        'meta/schemas/service_module.yaml',
        """      # 🆕 v1.1: 负责人从 product 派生
      # [V1.1.1 2026-06-10] UI 隐藏 - 服务模块跟随 product
      - key: effective_owner_id_display
        title: 负责人
        width: 100
        position: 5
        importance: low
        visible: false
        hidden_in_list: true
        hidden_in_form: true
""",
        """      # [V1.1.4 2026-06-11] 删 effective_owner_id_display - 顶层 owner 已在 product
"""
    ),

    # 6. business_object.yaml L338-347: 删 effective_owner_id_display list column
    (
        'meta/schemas/business_object.yaml',
        """      # 🆕 v1.1: 负责人从 product 派生
      # [V1.1.1 2026-06-10] UI 隐藏 - 业务对象跟随 product
      - key: effective_owner_id_display
        title: 负责人
        width: 100
        position: 5
        importance: low
        visible: false
        hidden_in_list: true
        hidden_in_form: true
""",
        """      # [V1.1.4 2026-06-11] 删 effective_owner_id_display - 顶层 owner 已在 product
"""
    ),

    # 7. business_object.yaml L210-213: 删 aspects 中 owner_id 引用
    (
        'meta/schemas/business_object.yaml',
        """    - id: owner_id
      field: bo.owner_id
      display_name: 负责人
  
""",
        """  # [V1.1.4 2026-06-11] 删 aspects 中 owner_id 引用 - 顶层 owner 已在 product
"""
    ),

    # 8. relationship.yaml L1590-1599: 删 effective_owner_id_display list column
    (
        'meta/schemas/relationship.yaml',
        """      # 🆕 v1.1: 负责人从 product 派生 (FR-006)
      # [V1.1.1 2026-06-10] UI 隐藏 - 关系表只看关系本身, 负责人请去 product 看
      - key: effective_owner_id_display
        title: 负责人
        width: 100
        position: 5
        importance: low
        visible: false
        hidden_in_list: true
        hidden_in_form: true
""",
        """      # [V1.1.4 2026-06-11] 删 effective_owner_id_display - 顶层 owner 已在 product
"""
    ),
]


def main():
    base = r'd:\filework\excel-to-diagram'
    results = []
    for rel_path, old_str, new_str in CHANGES:
        path = os.path.join(base, rel_path)
        with io.open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_str in content:
            content = content.replace(old_str, new_str, 1)
            with io.open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            results.append((rel_path, 'OK'))
            print(f'[OK] {rel_path}: replaced')
        else:
            results.append((rel_path, 'NOT FOUND'))
            print(f'[!!] {rel_path}: pattern NOT FOUND')

    print()
    print('=== Summary ===')
    ok = sum(1 for _, s in results if s == 'OK')
    fail = sum(1 for _, s in results if s == 'NOT FOUND')
    print(f'OK: {ok}, NOT FOUND: {fail}')


if __name__ == '__main__':
    main()
