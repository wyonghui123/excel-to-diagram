# -*- coding: utf-8 -*-
"""
测试 _is_field_editable 方法
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meta.core.models import registry
from meta.services.import_export_service import ImportExportService
from meta.core.datasource import get_data_source


def test_is_field_editable():
    """测试 _is_field_editable 方法"""
    role = registry.get('role')
    if not role:
        print("Role not found")
        return

    ds = get_data_source("sqlite", database=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta', 'architecture.db'))
    from meta.services.manage_service import ManageService
    from meta.services.query_service import QueryService
    manage_service = ManageService(ds)
    query_service = QueryService(ds)
    ie_service = ImportExportService(ds, manage_service, query_service)

    fields_to_check = ['user_count', 'menu_count', 'permission_count', 'data_perm_count']

    for field in role.fields:
        if field.id in fields_to_check:
            is_editable = ie_service._is_field_editable(field)
            readonly_always = getattr(field.semantics, 'readonly_always', False)
            computed = getattr(field.semantics, 'computed', False)

            print(f"\n字段: {field.name} ({field.id})")
            print(f"  readonly_always: {readonly_always}")
            print(f"  computed: {computed}")
            print(f"  _is_field_editable(): {is_editable}")
            print(f"  结果: {'只读' if not is_editable else '可编辑'}")


if __name__ == '__main__':
    test_is_field_editable()
