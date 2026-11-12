# -*- coding: utf-8 -*-
"""[T2] 权限自动入库覆盖测试。

旧实现 `_derive_from_object` 只遍历 `obj.actions`（228 个对象中仅 46 个声明
顶层 actions），其余 182 个对象从未被自动播种 → strict 模式下大量 403。

新口径：所有对象始终补齐标准 CRUD 单段码 `{bo}:create|read|update|delete`。
"""
import unittest

from meta.core.models import MetaAction, MetaObject, registry
from meta.services.permission_sync_service import (
    PermissionSyncService,
    _STANDARD_CRUD_SUFFIXES,
)


def _action(action_id: str) -> MetaAction:
    return MetaAction(
        id=action_id,
        name=action_id,
        action_type=None,
        method='GET',
        path='/',
    )


def _object(object_id: str, **kwargs) -> MetaObject:
    return MetaObject(id=object_id, name=object_id, table_name=object_id, **kwargs)


class TestDeriveFromObject(unittest.TestCase):
    def setUp(self):
        self.svc = PermissionSyncService(None)

    def test_no_actions_gets_standard_crud(self):
        """无 actions / 无 authorization 的对象 → 标准 CRUD 四码"""
        codes = self.svc._derive_from_object(_object('customer_invoice'))
        self.assertEqual(
            set(codes),
            {f'customer_invoice:{s}' for s in _STANDARD_CRUD_SUFFIXES},
        )

    def test_actions_plus_standard_crud(self):
        """声明了 actions 的对象仍需补齐标准 CRUD"""
        obj = _object('sales_order', actions=[_action('crud_create')])
        codes = self.svc._derive_from_object(obj)
        self.assertIn('sales_order:create', codes)
        self.assertIn('sales_order:read', codes)
        self.assertIn('sales_order:delete', codes)

    def test_authorization_declared_codes_included(self):
        """authorization.permissions 声明的码必须入库，且去重"""
        obj = _object(
            'sales_order',
            authorization={
                'check': True,
                'permissions': {'create': 'sales_order:create', 'read': 'sales_order:view'},
            },
        )
        codes = self.svc._derive_from_object(obj)
        self.assertIn('sales_order:view', codes)
        self.assertEqual(len(codes), len(set(codes)))

    def test_authorization_without_check_is_ignored(self):
        """check != true 时不引入声明码"""
        obj = _object(
            'sales_order',
            authorization={'check': False, 'permissions': {'read': 'sales_order:view'}},
        )
        codes = self.svc._derive_from_object(obj)
        self.assertNotIn('sales_order:view', codes)

    def test_all_registry_objects_covered(self):
        """228/228：每个非下划线对象都产出四个标准 CRUD 码"""
        if not registry.get_all():
            from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
            register_from_directory(get_yaml_schema_dir())

        objects = registry.get_all()
        self.assertTrue(objects, 'registry 为空，无法校验覆盖率')

        missing = []
        for obj_id, obj in objects.items():
            if obj_id.startswith('_'):
                continue
            codes = set(self.svc._derive_from_object(obj))
            for suffix in _STANDARD_CRUD_SUFFIXES:
                if f'{obj_id}:{suffix}' not in codes:
                    missing.append(f'{obj_id}:{suffix}')

        self.assertEqual(missing, [], f'未被权限同步覆盖的码: {missing[:10]}')


if __name__ == '__main__':
    unittest.main()