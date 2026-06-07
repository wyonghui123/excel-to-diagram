# -*- coding: utf-8 -*-
"""
调试角色字段的meta属性
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meta.core.models import registry


def debug_role_fields():
    """调试角色字段的meta属性"""
    role = registry.get('role')
    if not role:
        print("Role not found in registry")
        return

    print("="*60)
    print(f"Role: {role.id}")
    print(f"Total fields: {len(list(role.fields))}")
    print("="*60)

    fields_to_check = ['user_count', 'menu_count', 'permission_count', 'data_perm_count']

    for field in role.fields:
        if field.id in fields_to_check:
            print(f"\n字段: {field.name} ({field.id})")
            print(f"  data_type: {getattr(field, 'data_type', 'NOT_FOUND')}")
            print(f"  storage: {field.storage}")
            print(f"  storage.value: {field.storage.value}")

            # 检查 semantics
            semantics = field.semantics
            print(f"  readonly_always: {getattr(semantics, 'readonly_always', 'NOT_FOUND')}")
            print(f"  computed: {getattr(semantics, 'computed', 'NOT_FOUND')}")

            # 检查 computation
            has_computation = hasattr(field, 'computation')
            print(f"  has computation: {has_computation}")
            if has_computation:
                computation = field.computation
                print(f"  computation.type: {getattr(computation, 'type', 'NOT_FOUND')}")
                print(f"  computation.formula: {getattr(computation, 'formula', 'NOT_FOUND')}")

            # 检查 ui
            has_ui = hasattr(field, 'ui')
            print(f"  has ui: {has_ui}")
            if has_ui:
                ui = field.ui
                print(f"  ui.editable: {getattr(ui, 'editable', 'NOT_FOUND')}")
                print(f"  ui.visible: {getattr(ui, 'visible', 'NOT_FOUND')}")


if __name__ == '__main__':
    debug_role_fields()
