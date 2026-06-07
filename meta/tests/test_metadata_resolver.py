import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
MetadataResolver 单元测试

测试 §7.13 (FR-P1-008) 元数据驱动推导模式的统一入口。
MetadataResolver 从 YAML 元模型推导表名、字段名、图标等元数据，
遵循 SSOT（Single Source of Truth）原则，消除硬编码映射。
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.metadata_resolver import MetadataResolver
from meta.core.models import MetaObject, MetaField, FieldType
from meta.core.models import registry as meta_registry


@pytest.fixture(autouse=True)
def reset_cache():
    MetadataResolver._cache.clear()
    yield
    MetadataResolver._cache.clear()


class TestGetEntityIcon:

    def test_returns_icon_from_ui_config(self):
        obj = MetaObject(
            id='user', name='User', table_name='users',
            fields=[],
        )
        obj.ui = type('UI', (), {'icon': 'UserIcon'})()
        meta_registry._objects['user'] = obj

        icon = MetadataResolver.get_entity_icon('user')
        assert icon == 'UserIcon'

        del meta_registry._objects['user']

    def test_returns_default_icon_by_category(self):
        obj = MetaObject(
            id='product', name='Product', table_name='products',
            fields=[],
        )
        obj.ui = type('UI', (), {'icon': None, 'category': 'master_data'})()
        meta_registry._objects['product'] = obj

        icon = MetadataResolver.get_entity_icon('product')
        assert icon == 'Database'

        del meta_registry._objects['product']

    def test_returns_link_for_unknown_entity(self):
        icon = MetadataResolver.get_entity_icon('nonexistent_entity')
        assert icon == 'Link'

    def test_returns_link_for_empty_input(self):
        icon = MetadataResolver.get_entity_icon('')
        assert icon == 'Link'
        icon = MetadataResolver.get_entity_icon(None)
        assert icon == 'Link'

    def test_cache_returns_same_result(self):
        obj = MetaObject(
            id='order', name='Order', table_name='orders',
            fields=[],
        )
        obj.ui = type('UI', (), {'icon': 'OrderIcon'})()
        meta_registry._objects['order'] = obj

        icon1 = MetadataResolver.get_entity_icon('order')
        icon2 = MetadataResolver.get_entity_icon('order')
        assert icon1 == icon2
        assert MetadataResolver._cache.get('icon:order') == 'OrderIcon'

        del meta_registry._objects['order']


class TestGetFkColumn:

    def test_returns_from_association_through(self):
        assoc = type('Assoc', (), {
            'through': 'user_roles',
            'source_key': 'user_id',
        })()
        obj = MetaObject(
            id='user', name='User', table_name='users',
            fields=[],
        )
        obj.associations = {'roles': assoc}
        meta_registry._objects['user'] = obj

        result = MetadataResolver.get_fk_column('user_roles', 'user')
        assert result == ('user_roles', 'user_id')

        del meta_registry._objects['user']

    def test_fallback_uses_entity_id_suffix(self):
        result = MetadataResolver.get_fk_column('user_roles', 'unknown_entity')
        assert result == ('user_roles', 'unknown_entity_id')

    def test_returns_none_for_empty_input(self):
        assert MetadataResolver.get_fk_column(None, 'user') is None
        assert MetadataResolver.get_fk_column('user_roles', None) is None

    def test_cache_works(self):
        assoc = type('Assoc', (), {
            'through': 'role_permissions',
            'source_key': 'role_id',
        })()
        obj = MetaObject(
            id='role', name='Role', table_name='roles',
            fields=[],
        )
        obj.associations = {'users': assoc}
        meta_registry._objects['role'] = obj

        result1 = MetadataResolver.get_fk_column('role_permissions', 'role')
        result2 = MetadataResolver.get_fk_column('role_permissions', 'role')
        assert result1 == result2

        del meta_registry._objects['role']


class TestGetAssociationTarget:

    def test_returns_target_entity_from_association(self):
        assoc = type('Assoc', (), {
            'target_entity': 'role',
        })()
        obj = MetaObject(
            id='user', name='User', table_name='users',
            fields=[],
        )
        obj.associations = {'roles': assoc}
        meta_registry._objects['user'] = obj

        target = MetadataResolver.get_association_target('user', 'roles')
        assert target == 'role'

        del meta_registry._objects['user']

    def test_returns_empty_for_unknown(self):
        target = MetadataResolver.get_association_target('unknown', 'roles')
        assert target == ''

    def test_returns_empty_for_empty_input(self):
        assert MetadataResolver.get_association_target('', 'roles') == ''
        assert MetadataResolver.get_association_target('user', '') == ''


class TestGetM2mThroughInfo:

    def test_returns_through_info_from_association(self):
        assoc = type('Assoc', (), {
            'through': 'user_roles',
            'source_key': 'user_id',
            'target_key': 'role_id',
        })()
        obj = MetaObject(
            id='user', name='User', table_name='users',
            fields=[],
        )
        obj.associations = {'roles': assoc}
        meta_registry._objects['user'] = obj

        result = MetadataResolver.get_m2m_through_info('user', 'role', 'roles')
        assert result == ('user_roles', 'user_id', 'role_id')

        del meta_registry._objects['user']

    def test_returns_none_for_unknown(self):
        result = MetadataResolver.get_m2m_through_info('unknown', 'role', 'roles')
        assert result is None

    def test_returns_none_for_partial_input(self):
        assert MetadataResolver.get_m2m_through_info(None, 'role', 'roles') is None


class TestGetDisplayField:

    def test_returns_display_field_from_object(self):
        obj = MetaObject(
            id='product', name='Product', table_name='products',
            fields=[],
        )
        obj.display_field = 'product_name'
        meta_registry._objects['product'] = obj

        field = MetadataResolver.get_display_field('product')
        assert field == 'product_name'

        del meta_registry._objects['product']

    def test_returns_name_as_default(self):
        field = MetadataResolver.get_display_field('nonexistent')
        assert field == 'name'

    def test_returns_name_for_empty_input(self):
        assert MetadataResolver.get_display_field('') == 'name'
        assert MetadataResolver.get_display_field(None) == 'name'


class TestGetTableName:

    def test_returns_table_name_from_object(self):
        obj = MetaObject(
            id='customer', name='Customer', table_name='customers',
            fields=[],
        )
        meta_registry._objects['customer'] = obj

        table = MetadataResolver.get_table_name('customer')
        assert table == 'customers'

        del meta_registry._objects['customer']

    def test_fallback_to_entity_name(self):
        table = MetadataResolver.get_table_name('unknown_entity')
        assert table == 'unknown_entity'


class TestIsNavigationEnabled:

    def test_enables_for_m2m(self):
        assert MetadataResolver.is_navigation_enabled('many_to_many') is True

    def test_enables_for_composition(self):
        assert MetadataResolver.is_navigation_enabled('composition') is True

    def test_enables_for_reverse_m2m(self):
        assert MetadataResolver.is_navigation_enabled('reverse_many_to_many') is True

    def test_disables_for_reference(self):
        assert MetadataResolver.is_navigation_enabled('reference') is False

    def test_disables_for_unknown(self):
        assert MetadataResolver.is_navigation_enabled('unknown_type') is False


class TestClearCache:

    def test_clears_all_cache(self):
        obj = MetaObject(
            id='session', name='Session', table_name='sessions',
            fields=[],
        )
        obj.ui = type('UI', (), {'icon': 'SessionIcon'})()
        meta_registry._objects['session'] = obj

        MetadataResolver.get_entity_icon('session')
        assert len(MetadataResolver._cache) > 0

        MetadataResolver.clear_cache()
        assert len(MetadataResolver._cache) == 0

        del meta_registry._objects['session']

    def test_cache_persists_across_calls(self):
        obj = MetaObject(
            id='item', name='Item', table_name='items',
            fields=[],
        )
        obj.display_field = 'item_name'
        meta_registry._objects['item'] = obj

        MetadataResolver.get_display_field('item')
        MetadataResolver.get_table_name('item')

        assert 'display:item' in MetadataResolver._cache
        assert 'table:item' in MetadataResolver._cache

        del meta_registry._objects['item']


class TestSingletonBehavior:

    def test_returns_same_instance(self):
        r1 = MetadataResolver()
        r2 = MetadataResolver()
        assert r1 is r2


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
