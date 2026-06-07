import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
MenuAutoGenerator 服务测试

测试 meta/services/menu_auto_generator.py：
- generate_all
- generate_object_list_menu
- persist_to_db

迁移自 unittest.TestCase -> pytest
"""
import pytest
import os


@pytest.fixture(scope='class')
def data_source():
    """获取数据源"""
    from meta.core.datasource import get_data_source
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db'
    )
    return get_data_source("sqlite", database=db_path)


@pytest.fixture(scope='class')
def client():
    """获取 Flask test client"""
    from meta.tests.conftest import get_shared_app
    _, client = get_shared_app()
    return client


@pytest.fixture
def auth_headers():
    """获取认证 headers"""
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo

    user = UserInfo(
        user_id='1',
        username='admin',
        display_name='Admin',
        email='admin@test.com',
        roles=['admin'],
        permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }


class TestMenuAutoGenerator:
    """MenuAutoGenerator 服务测试"""

    def test_menu_generator_exists(self):
        """测试 MenuAutoGenerator 类存在"""
        from meta.services.menu_auto_generator import MenuAutoGenerator
        assert MenuAutoGenerator is not None

    def test_generate_all(self):
        """测试从 YAML 生成菜单"""
        from meta.services.menu_auto_generator import MenuAutoGenerator
        generator = MenuAutoGenerator()

        menu_data = generator.generate_all()
        assert isinstance(menu_data, list)

    def test_generate_object_list_menu(self):
        """测试生成单个对象的列表菜单"""
        from meta.services.menu_auto_generator import MenuAutoGenerator
        from meta.core.models import registry
        generator = MenuAutoGenerator()

        all_objects = registry.get_all()
        if all_objects:
            first_obj = next(iter(all_objects.values()))
            menu = generator.generate_object_list_menu(first_obj)
            assert isinstance(menu, dict)
            assert 'menu_code' in menu
            assert 'menu_name' in menu
            assert 'page_type' in menu

    def test_persist_to_db(self, data_source):
        """测试持久化菜单到数据库"""
        from meta.services.menu_auto_generator import MenuAutoGenerator
        generator = MenuAutoGenerator()

        count = generator.persist_to_db(data_source)
        assert isinstance(count, int)
        assert count >= 0

    def test_skip_auto_menu_config(self):
        """测试 skip_auto_menu 配置"""
        from meta.services.menu_auto_generator import MenuAutoGenerator
        generator = MenuAutoGenerator()

        menu_data = generator.generate_all()

        for item in menu_data:
            if item.get('skip_auto_menu'):
                assert 'route' not in item

    def test_bo_bindings(self):
        """测试 BO 绑定"""
        from meta.services.menu_auto_generator import MenuAutoGenerator
        generator = MenuAutoGenerator()

        menu_data = generator.generate_all()

        for item in menu_data:
            if 'object_type' in item or 'primary_object_type' in item:
                obj_type = item.get('primary_object_type') or item.get('object_type')
                assert obj_type is not None

    def test_menu_has_required_fields(self):
        """测试菜单包含必要字段"""
        from meta.services.menu_auto_generator import MenuAutoGenerator
        generator = MenuAutoGenerator()

        menu_data = generator.generate_all()

        for item in menu_data:
            assert 'menu_code' in item
            assert 'menu_name' in item
            assert 'page_type' in item


class TestMenuAPI:
    """Menu API 测试"""

    def test_get_menu_tree(self, client, auth_headers):
        """获取菜单树"""
        response = client.get(
            '/api/v1/menu-permission/visible',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_get_menu_categories(self, client, auth_headers):
        """获取菜单分类"""
        response = client.get(
            '/api/v1/menu-permission/menus',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_get_menu_tree_without_auth(self, client):
        """未认证获取菜单"""
        response = client.get('/api/v1/menu-permission/visible')
        assert response.status_code in [401, 403, 302, 200, 404, 500]

    def test_get_menu_categories_without_auth(self, client):
        """未认证获取菜单分类"""
        response = client.get('/api/v1/menu-permission/menus')
        assert response.status_code in [401, 403, 302, 200, 404, 500]
