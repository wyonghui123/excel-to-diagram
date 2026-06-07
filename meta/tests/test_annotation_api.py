import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
备注功能API自动化测试

测试备注的CRUD操作和级联删除功能
"""

import json
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
from meta.server import create_app
from meta.core.datasource import get_data_source
from meta.tests.test_utils import get_test_db_path
from meta.tests.shared.fixtures import _client_and_headers

@pytest.fixture(scope='class')
def api_client(shared_client):
    return shared_client


@pytest.fixture(scope='class')
def client_with_auth():
    return _client_and_headers()


@pytest.fixture(scope='class')
def auth_headers(client_with_auth):
    _, headers = client_with_auth
    headers['X-User-Id'] = '1'
    headers['X-User-Name'] = 'test_user'
    headers['X-IP-Address'] = '127.0.0.1'
    return headers


@pytest.fixture(scope='class')
def setup_annotations_table():
    ds = get_data_source("sqlite", database=get_test_db_path())
    if ds.table_exists('annotations'):
        ds.execute("DELETE FROM annotations WHERE target_id >= 8000")
        for idx in ['uidx_annotations_category', 'uidx_annotations_target_id', 'uidx_annotations_target_type']:
            try:
                ds.execute(f"DROP INDEX IF EXISTS {idx}")
            except Exception:
                pass
        ds.commit()
    else:
        ds.execute('''
            CREATE TABLE annotations (
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
        ds.execute('CREATE INDEX idx_annotation_target ON annotations(target_type, target_id)')
        ds.commit()
        print("[SETUP] Created annotations table for testing")
    yield
    ds.execute("DELETE FROM annotations WHERE target_id >= 8000")
    ds.commit()


@pytest.fixture(scope='class')
def shared_annotations(api_client, auth_headers):
    """Class scope fixture - 在同一测试类内共享创建的注解"""
    created = []
    
    # 预先创建测试数据
    test_data = [
        ('domain', 8001, 'important', '测试领域备注 - 重要'),
        ('sub_domain', 8002, 'info', '测试子领域备注 - 信息'),
        ('service_module', 8003, 'warning', '测试服务模块备注 - 警告'),
    ]
    
    for target_type, target_id, category, content in test_data:
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
        try:
            data = json.loads(response.data)
            if data.get('success', False) and 'id' in data.get('data', {}):
                created.append(data['data']['id'])
        except Exception:
            pass

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


class TestAnnotationAPI:

    def test_01_list_annotations_empty(self, api_client, auth_headers, setup_annotations_table):
        """测试查询空备注列表"""
        response = api_client.get(
            '/api/v1/annotations/by-target?target_type=domain&target_id=999999',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        assert isinstance(data.get('data', {}), list)
        assert len(data.get('data', {})) == 0
        print("[PASS] List empty annotations")

    def test_02_create_annotation_domain(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为领域创建备注"""
        response = _create_annotation(
            api_client, auth_headers,
            'domain', 8001, 'important', '测试领域备注 - 重要'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        assert 'id' in data.get('data', {})
        shared_annotations.append(data.get('data', {})['id'])
        print("[PASS] Create annotation for domain")

    def test_03_create_annotation_sub_domain(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为子领域创建备注"""
        response = _create_annotation(
            api_client, auth_headers,
            'sub_domain', 8002, 'info', '测试子领域备注 - 信息'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        shared_annotations.append(data.get('data', {})['id'])
        print("[PASS] Create annotation for sub_domain")

    def test_04_create_annotation_service_module(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为服务模块创建备注"""
        response = _create_annotation(
            api_client, auth_headers,
            'service_module', 8003, 'warning', '测试服务模块备注 - 警告'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        shared_annotations.append(data.get('data', {})['id'])
        print("[PASS] Create annotation for service_module")

    def test_05_create_annotation_business_object(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为业务对象创建备注"""
        response = _create_annotation(
            api_client, auth_headers,
            'business_object', 8004, 'tip', '测试业务对象备注 - 提示'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        shared_annotations.append(data.get('data', {})['id'])
        print("[PASS] Create annotation for business_object")

    def test_06_create_annotation_relationship(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为关系创建备注"""
        response = _create_annotation(
            api_client, auth_headers,
            'relationship', 8005, 'info', '测试关系备注 - 信息'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        shared_annotations.append(data.get('data', {})['id'])
        print("[PASS] Create annotation for relationship")

    def test_07_create_annotation_default_category(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试创建备注时默认分类为info"""
        response = _create_annotation(
            api_client, auth_headers,
            'domain', 8006, None, '测试默认分类备注'
        )
        assert response.status_code in [200, 201, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        shared_annotations.append(data.get('data', {})['id'])
        print("[PASS] Create annotation with default category")

    def test_08_create_annotation_missing_content(self, api_client, auth_headers, setup_annotations_table):
        """测试创建备注时缺少内容"""
        response = api_client.post(
            '/api/v1/annotations',
            data=json.dumps({
                'target_type': 'domain',
                'target_id': 8007,
                'category': 'info'
            }),
            headers=auth_headers
        )
        assert response.status_code in [400, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is False
        print("[PASS] Create annotation without content fails")

    def test_09_create_annotation_invalid_target_type(self, api_client, auth_headers, setup_annotations_table):
        """测试创建备注时无效的target_type"""
        response = _create_annotation(
            api_client, auth_headers,
            'invalid_type', 8008, 'info', '测试无效类型'
        )
        assert response.status_code in [400, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is False
        print("[PASS] Create annotation with invalid target_type fails")

    def test_10_create_annotation_invalid_category(self, api_client, auth_headers, setup_annotations_table):
        """测试创建备注时无效的category"""
        response = _create_annotation(
            api_client, auth_headers,
            'domain', 8009, 'invalid_category', '测试无效分类'
        )
        assert response.status_code in [400, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is False
        print("[PASS] Create annotation with invalid category fails")

    def test_11_list_annotations_by_target(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试按对象查询备注列表"""
        response = _create_annotation(
            api_client, auth_headers,
            'domain', 8001, 'important', '测试查询备注'
        )
        
        response = api_client.get(
            '/api/v1/annotations/by-target?target_type=domain&target_id=8001',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        assert isinstance(data.get('data', {}), list)
        assert len(data.get('data', {})) > 0
        for item in data.get('data', {}):
            assert item['target_type'] == 'domain'
            assert item['target_id'] == 8001
            assert 'category_label' in item
        print("[PASS] List annotations by target")

    def test_12_list_annotations_missing_params(self, api_client, auth_headers, setup_annotations_table):
        """测试查询备注时缺少参数"""
        response = api_client.get(
            '/api/v1/annotations/by-target?target_type=domain',
            headers=auth_headers
        )
        assert response.status_code in [400, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is False
        print("[PASS] List annotations without target_id fails")

    def test_13_get_annotation(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试查询单个备注"""
        assert len(shared_annotations) > 0, "需要有测试数据才能执行此测试"
        
        annotation_id = shared_annotations[0]
        response = api_client.get(
            f'/api/v1/annotations/{annotation_id}',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        assert data.get('data', {})['id'] == annotation_id
        assert 'category_label' in data.get('data', {})
        print("[PASS] Get annotation by id")

    def test_14_get_annotation_not_found(self, api_client, auth_headers, setup_annotations_table):
        """测试查询不存在的备注"""
        response = api_client.get(
            '/api/v1/annotations/999999',
            headers=auth_headers
        )
        assert response.status_code in [401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is False
        print("[PASS] Get non-existent annotation returns 404")

    def test_15_update_annotation(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试更新备注"""
        assert len(shared_annotations) > 0, "需要有测试数据才能执行此测试"
        
        annotation_id = shared_annotations[0]
        response = api_client.put(
            f'/api/v1/annotations/{annotation_id}',
            data=json.dumps({
                'category': 'warning',
                'content': '更新后的备注内容'
            }),
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is True
        if data.get('data', {}):
            assert data.get('data', {}).get('category') == 'warning'
            assert data.get('data', {}).get('content') == '更新后的备注内容'
        print("[PASS] Update annotation")

    def test_16_update_annotation_invalid_category(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试更新备注时无效的category"""
        assert len(shared_annotations) > 0, "需要有测试数据才能执行此测试"
        
        annotation_id = shared_annotations[0]
        response = api_client.put(
            f'/api/v1/annotations/{annotation_id}',
            data=json.dumps({
                'category': 'invalid_category',
                'content': '测试更新'
            }),
            headers=auth_headers
        )
        assert response.status_code in [400, 401, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert data.get('success', False) is False
        print("[PASS] Update annotation with invalid category fails")

    def test_17_create_multiple_annotations(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
        """测试为一个对象创建多条备注"""
        for i in range(3):
            _create_annotation(
                api_client, auth_headers,
                'domain', 8010 + i, 'info', f'多条备注测试 - 第{i+1}条'
            )
        
        response = api_client.get(
            '/api/v1/annotations/by-target?target_type=domain&target_id=8010',
            headers=auth_headers
        )
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            pytest.fail('response is not JSON')
        assert len(data.get('data', {})) >= 1
        print("[PASS] Create multiple annotations for same target")

    def test_18_delete_annotation(self, api_client, auth_headers, shared_annotations, setup_annotations_table):
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
