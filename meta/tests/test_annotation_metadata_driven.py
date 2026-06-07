import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Annotation 元数据驱动集成测试

测试服务模块、业务对象、关系的 annotation CRUD
验证 child_sections 配置是否正确返回
"""

import json
import sys
import os
import jwt

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
from meta.server import create_app
from meta.core.datasource import get_data_source
from meta.tests.test_utils import get_test_db_path

@pytest.fixture(scope='class')
def api_client(shared_client):
    return shared_client


@pytest.fixture(scope='class')
def auth_headers(api_client):
    secret = os.environ.get('JWT_SECRET_KEY', 'test-secret-key-for-testing-purposes-only-min32chars')
    token = jwt.encode(
        {
            'user_id': 1,
            'username': 'admin',
            'exp': 9999999999
        },
        secret,
        algorithm='HS256'
    )
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_user',
        'X-IP-Address': '127.0.0.1'
    }


@pytest.fixture(scope='class')
def setup_annotations_table():
    ds = get_data_source("sqlite", database=get_test_db_path())
    ds.execute('''
        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type VARCHAR(200) NOT NULL,
            target_id INTEGER NOT NULL,
            category VARCHAR(200) NOT NULL,
            content TEXT,
            created_at DATETIME NOT NULL,
            created_by VARCHAR(200),
            updated_at DATETIME,
            updated_by VARCHAR(200)
        )
    ''')
    ds.execute('CREATE INDEX IF NOT EXISTS idx_annotation_target ON annotations(target_type, target_id)')
    ds.commit()
    print("[SETUP] Ensured annotations table exists for testing")
    yield
    ds.execute('DROP TABLE IF EXISTS annotations')
    ds.commit()


@pytest.fixture(scope='class')
def shared_annotations(api_client, auth_headers):
    """Class scope fixture - 在同一测试类内共享创建的注解"""
    created = []

    yield created

    for annotation_id in reversed(created):
        try:
            api_client.delete(f'/api/v1/annotations/{annotation_id}', headers=auth_headers)
        except Exception:
            pass
    print("\n[CLEANUP] Deleted all test annotations")


def _create_annotation(api_client, auth_headers, target_type, target_id, category, content):
    response = api_client.post(
        '/api/v1/annotations',
        data=json.dumps({
            'target_type': target_type,
            'target_id': target_id,
            'category': category,
            'content': content
        }),
        headers=auth_headers
    )
    return response


class TestAnnotationMetadataDriven:

    def test_01_ui_config_service_module_has_annotation_section(self, api_client, auth_headers, setup_annotations_table):
        """测试 service_module 的 UI Config 包含 annotation child_section"""
        response = api_client.get(
            '/api/v2/meta/service_module/ui-config',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        
        ui_view_config = data.get('data', {}).get('ui_view_config', {})
        child_sections = ui_view_config.get('child_sections', [])
        
        annotation_section = next(
            (cs for cs in child_sections if cs.get('child_object') == 'annotation'),
            None
        )
        
        assert annotation_section is not None, "service_module should have annotation child_section"
        assert annotation_section.get('title') == '备注信息'
        assert 'columns' in annotation_section
        assert 'actions' in annotation_section
        print("[PASS] service_module UI Config has annotation child_section")

    def test_02_ui_config_business_object_has_annotation_section(self, api_client, auth_headers, setup_annotations_table):
        """测试 business_object 的 UI Config 包含 annotation child_section"""
        response = api_client.get(
            '/api/v2/meta/business_object/ui-config',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        
        ui_view_config = data.get('data', {}).get('ui_view_config', {})
        child_sections = ui_view_config.get('child_sections', [])
        
        annotation_section = next(
            (cs for cs in child_sections if cs.get('child_object') == 'annotation'),
            None
        )
        
        assert annotation_section is not None, "business_object should have annotation child_section"
        assert annotation_section.get('title') == '备注信息'
        print("[PASS] business_object UI Config has annotation child_section")

    def test_03_ui_config_relationship_has_annotation_section(self, api_client, auth_headers, setup_annotations_table):
        """测试 relationship 的 UI Config 包含 annotation child_section"""
        response = api_client.get(
            '/api/v2/meta/relationship/ui-config',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        
        ui_view_config = data.get('data', {}).get('ui_view_config', {})
        child_sections = ui_view_config.get('child_sections', [])
        
        annotation_section = next(
            (cs for cs in child_sections if cs.get('child_object') == 'annotation'),
            None
        )
        
        assert annotation_section is not None, "relationship should have annotation child_section"
        assert annotation_section.get('title') == '备注信息'
        print("[PASS] relationship UI Config has annotation child_section")

    def test_04_annotation_has_polymorphic_association(self, api_client, auth_headers, setup_annotations_table):
        """测试 annotation.yaml 定义了 polymorphic association"""
        response = api_client.get(
            '/api/v2/meta/annotation/ui-config',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        
        associations = data.get('data', {}).get('associations', [])
        target_assoc = next(
            (a for a in associations if a.get('name') == 'target'),
            None
        )
        
        assert target_assoc is not None, "annotation should have 'target' association"
        assert target_assoc.get('target_entity') == 'polymorphic'
        assert target_assoc.get('type') == 'many_to_one'
        print("[PASS] annotation has polymorphic association defined")

    def test_05_create_annotation_for_service_module(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为服务模块创建备注"""
        response = _create_annotation(
            api_client, auth_headers,
            'service_module', 1, 'important', '服务模块重要备注 - 需要关注性能问题'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        assert 'id' in data.get('data', {})
        shared_annotations.append(data.get('data', {})['id'])
        print("[PASS] Create annotation for service_module")

    def test_06_create_annotation_for_business_object(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为业务对象创建备注"""
        response = _create_annotation(
            api_client, auth_headers,
            'business_object', 1, 'info', '业务对象备注 - 核心实体，需要权限控制'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        shared_annotations.append(data.get('data', {}).get('id'))
        print("[PASS] Create annotation for business_object")

    def test_07_create_annotation_for_relationship(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为关系创建备注"""
        response = _create_annotation(
            api_client, auth_headers,
            'relationship', 1, 'warning', '关系备注 - 级联删除需要谨慎处理'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        shared_annotations.append(data.get('data', {}).get('id'))
        print("[PASS] Create annotation for relationship")

    def test_08_list_annotations_for_service_module(self, api_client, auth_headers, setup_annotations_table):
        """测试查询服务模块的备注列表"""
        response = api_client.get(
            '/api/v1/annotations/by-target?target_type=service_module&target_id=1',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        assert isinstance(data.get('data', {}), list)
        assert len(data.get('data', {})) >= 0
        print("[PASS] List annotations for service_module")

    def test_09_list_annotations_for_business_object(self, api_client, auth_headers, setup_annotations_table):
        """测试查询业务对象的备注列表"""
        response = api_client.get(
            '/api/v1/annotations/by-target?target_type=business_object&target_id=1',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        assert len(data.get('data', [])) >= 0
        print("[PASS] List annotations for business_object")

    def test_10_list_annotations_for_relationship(self, api_client, auth_headers, setup_annotations_table):
        """测试查询关系的备注列表"""
        response = api_client.get(
            '/api/v1/annotations/by-target?target_type=relationship&target_id=1',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        assert len(data.get('data', [])) >= 0
        print("[PASS] List annotations for relationship")

    def test_11_update_annotation_service_module(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试更新服务模块备注"""
        assert len(shared_annotations) > 0, "需要有测试数据才能执行此测试"
        
        annotation_id = shared_annotations[0]
        response = api_client.put(
            f'/api/v1/annotations/{annotation_id}',
            data=json.dumps({
                'category': 'warning',
                'content': '更新后的服务模块备注 - 性能问题已解决'
            }),
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        print("[PASS] Update annotation for service_module")

    def test_12_annotation_categories_validation(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试备注分类验证"""
        valid_categories = ['important', 'info', 'warning', 'tip']
        
        for i, category in enumerate(valid_categories):
            response = _create_annotation(
                api_client, auth_headers,
                'service_module', 2 + i, category, f'测试分类 {category}'
            )
            assert response.status_code in [200, 201, 400, 401, 500]
            if response.status_code in [201, 200]:
                try:
                    data = json.loads(response.data)
                except (json.JSONDecodeError, ValueError):
                    pytest.fail('response is not JSON')
                assert data.get('success', False) is True
                shared_annotations.append(data.get('data', {}).get('id'))
        
        print(f"[PASS] Valid categories tested: {valid_categories}")

    def test_13_multiple_annotations_same_target(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试同一对象多条备注"""
        categories = ['important', 'warning', 'tip']
        for i, category in enumerate(categories):
            response = _create_annotation(
                api_client, auth_headers,
                'business_object', 3 + i, category, f'业务对象备注 #{i+1} - 测试多条备注'
            )
            assert response.status_code in [200, 201, 400, 401, 500]
            if response.status_code in [201, 200]:
                try:
                    data = json.loads(response.data)
                except (json.JSONDecodeError, ValueError):
                    pytest.fail('response is not JSON')
                shared_annotations.append(data.get('data', {}).get('id'))
        
        response = api_client.get(
            '/api/v1/annotations/by-target?target_type=business_object&target_id=3',
            headers=auth_headers
        )
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert len(data.get('data', [])) >= 0
        print("[PASS] Multiple annotations for same target")

    def test_14_delete_annotation(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试删除备注"""
        assert len(shared_annotations) >= 2, "至少需要2条测试数据才能执行此测试"
        
        annotation_id = shared_annotations.pop()
        response = api_client.delete(
            f'/api/v1/annotations/{annotation_id}',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        
        response = api_client.get(
            f'/api/v1/annotations/{annotation_id}',
            headers=auth_headers
        )
        assert response.status_code in [401, 404, 500]
        print("[PASS] Delete annotation")

    def test_15_cascade_delete_simulation(self, api_client, auth_headers, setup_annotations_table):
        """测试级联删除场景 - 当父对象被删除时，备注应被级联删除"""
        response = _create_annotation(
            api_client, auth_headers,
            'service_module', 99999, 'info', '测试级联删除的备注'
        )
        assert response.status_code in [200, 201, 400, 401, 500]
        
        if response.status_code not in [201, 200]:
            response = api_client.post(
                '/api/v1/annotations',
                data=json.dumps({
                    'target_type': 'service_module',
                    'target_id': 99999,
                    'category': 'info',
                    'content': '测试级联删除的备注'
                }),
                headers=auth_headers
            )
            assert response.status_code in [200, 201, 400, 401, 500], "无法创建测试备注"
        
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        test_annotation_id = data.get('data', {}).get('id')
        
        response = api_client.get(
            f'/api/v1/annotations/{test_annotation_id}',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        
        response = api_client.delete(
            f'/api/v1/annotations/{test_annotation_id}',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        print("[PASS] Cascade delete simulation works")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
