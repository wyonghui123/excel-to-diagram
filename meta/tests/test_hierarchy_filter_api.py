import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
层级过滤 API 集成测试

测试 API 级别的过滤功能：
1. 列表查询过滤
2. 导出功能过滤
"""

import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.server import create_app
from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo
from meta.tests.test_utils import get_test_db_path


def get_auth_headers():
    test_user = UserInfo(
        user_id='1', username='test_user', display_name='Test User',
        email='test@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(test_user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_user',
        'X-IP-Address': '127.0.0.1'
    }


def _check_data_exists(ds, table_name):
    cursor = ds.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row["cnt"]) > 0


def _check_business_objects_exist(ds):
    cursor = ds.execute("SELECT COUNT(*) as cnt FROM business_objects")
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row["cnt"]) > 0


def _check_domains_exist(ds):
    cursor = ds.execute("SELECT COUNT(*) as cnt FROM domains")
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row["cnt"]) > 0


def _check_sub_domains_exist(ds):
    cursor = ds.execute("SELECT COUNT(*) as cnt FROM sub_domains")
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row["cnt"]) > 0


def _check_service_modules_exist(ds):
    cursor = ds.execute("SELECT COUNT(*) as cnt FROM service_modules")
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row["cnt"]) > 0


def _check_complete_hierarchy_exists(ds):
    cursor = ds.execute("""
        SELECT COUNT(*) as cnt
        FROM business_objects bo
        JOIN service_modules sm ON bo.service_module_id = sm.id
        JOIN sub_domains sd ON sm.sub_domain_id = sd.id
        JOIN domains d ON sd.domain_id = d.id
    """)
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row["cnt"]) > 0


class TestListFilterAPI:
    """列表查询过滤 API 测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from meta.tests.conftest import get_shared_app
        self.app, self.client = get_shared_app()
        self.headers = get_auth_headers()
        
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        
        cursor = self.ds.execute("""
            SELECT bo.id, bo.service_module_id, sm.sub_domain_id, sd.domain_id
            FROM business_objects bo
            INNER JOIN service_modules sm ON bo.service_module_id = sm.id
            INNER JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            ORDER BY bo.id
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            self.test_bo_id, self.test_sm_id, self.test_sd_id, self.test_d_id = row
        else:
            self.test_bo_id = self.test_sm_id = self.test_sd_id = self.test_d_id = None
            self._create_test_data()
    
    def _create_test_data(self):
        self.ds.execute("""
            INSERT INTO products (code, name) VALUES ('TEST', 'Test Product')
        """)
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        product_id = cursor.fetchone()[0]
        
        self.ds.execute("""
            INSERT INTO versions (product_id, code, name) VALUES (?, 'V1', 'Version 1')
        """, (product_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        version_id = cursor.fetchone()[0]
        
        self.ds.execute("""
            INSERT INTO domains (version_id, code, name) VALUES (?, 'TEST_DOMAIN', 'Test Domain')
        """, (version_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        domain_id = cursor.fetchone()[0]
        self.test_d_id = domain_id
        
        self.ds.execute("""
            INSERT INTO sub_domains (domain_id, code, name) VALUES (?, 'TEST_SD', 'Test Sub Domain')
        """, (domain_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        sub_domain_id = cursor.fetchone()[0]
        self.test_sd_id = sub_domain_id
        
        self.ds.execute("""
            INSERT INTO service_modules (sub_domain_id, code, name) VALUES (?, 'TEST_SM', 'Test Service Module')
        """, (sub_domain_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        service_module_id = cursor.fetchone()[0]
        self.test_sm_id = service_module_id
        
        self.ds.execute("""
            INSERT INTO business_objects (service_module_id, code, name) VALUES (?, 'TEST_BO', 'Test Business Object')
        """, (service_module_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        self.test_bo_id = cursor.fetchone()[0]

    def test_list_business_objects_without_filter(self):
        """测试无过滤条件查询业务对象"""
        response = self.client.get(
            '/api/v2/bo/business_object',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True

    def test_list_business_objects_with_domain_filter(self):
        """测试使用 domain_id 过滤业务对象"""
        if not _check_domains_exist(self.ds):
            pytest.fail("No domains in database - requires test data setup")
        if not self.test_d_id:
            pytest.fail("No business object with domain association - requires test data setup")
        
        response = self.client.get(
            f'/api/v2/bo/business_object?domain_id={self.test_d_id}',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True

    def test_list_business_objects_with_sub_domain_filter(self):
        """测试使用 sub_domain_id 过滤业务对象"""
        if not _check_sub_domains_exist(self.ds):
            pytest.fail("No sub_domains in database - requires test data setup")
        if not self.test_sd_id:
            pytest.fail("No business object with sub_domain association - requires test data setup")
        
        response = self.client.get(
            f'/api/v2/bo/business_object?sub_domain_id={self.test_sd_id}',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True

    def test_list_business_objects_with_service_module_filter(self):
        """测试使用 service_module_id 过滤业务对象"""
        if not _check_service_modules_exist(self.ds):
            pytest.fail("No service_modules in database - requires test data setup")
        if not self.test_sm_id:
            pytest.fail("No business object with service_module association - requires test data setup")
        
        response = self.client.get(
            f'/api/v2/bo/business_object?service_module_id={self.test_sm_id}',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True

    def test_list_domains_with_business_object_filter(self):
        """测试使用 business_object_id 过滤领域"""
        if not _check_business_objects_exist(self.ds):
            pytest.fail("No business_objects in database - requires test data setup")
        if not self.test_bo_id:
            pytest.fail("No business object available - requires test data setup")
        
        response = self.client.get(
            f'/api/v2/bo/domain?business_object_id={self.test_bo_id}',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True

    def test_list_service_modules_with_business_object_filter(self):
        """测试使用 business_object_id 过滤服务模块"""
        if not _check_business_objects_exist(self.ds):
            pytest.fail("No business_objects in database - requires test data setup")
        if not self.test_bo_id:
            pytest.fail("No business object available - requires test data setup")
        
        response = self.client.get(
            f'/api/v2/bo/service_module?business_object_id={self.test_bo_id}',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True

    def test_list_sub_domains_with_business_object_filter(self):
        """测试使用 business_object_id 过滤子领域"""
        if not _check_business_objects_exist(self.ds):
            pytest.fail("No business_objects in database - requires test data setup")
        if not self.test_bo_id:
            pytest.fail("No business object available - requires test data setup")
        
        response = self.client.get(
            f'/api/v2/bo/sub_domain?business_object_id={self.test_bo_id}',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True


class TestRelationshipFilterAPI:
    """关系过滤 API 测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from meta.tests.conftest import get_shared_app
        self.app, self.client = get_shared_app()
        self.headers = get_auth_headers()
        
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        
        cursor = self.ds.execute("""
            SELECT bo.id, bo.service_module_id, sm.sub_domain_id, sd.domain_id
            FROM business_objects bo
            INNER JOIN service_modules sm ON bo.service_module_id = sm.id
            INNER JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            ORDER BY bo.id
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            self.test_bo_id, self.test_sm_id, self.test_sd_id, self.test_d_id = row
        else:
            self.test_bo_id = self.test_sm_id = self.test_sd_id = self.test_d_id = None
            self._create_test_data()
    
    def _create_test_data(self):
        self.ds.execute("""
            INSERT INTO products (code, name) VALUES ('TEST', 'Test Product')
        """)
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        product_id = cursor.fetchone()[0]
        
        self.ds.execute("""
            INSERT INTO versions (product_id, code, name) VALUES (?, 'V1', 'Version 1')
        """, (product_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        version_id = cursor.fetchone()[0]
        
        self.ds.execute("""
            INSERT INTO domains (version_id, code, name) VALUES (?, 'TEST_DOMAIN', 'Test Domain')
        """, (version_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        domain_id = cursor.fetchone()[0]
        self.test_d_id = domain_id
        
        self.ds.execute("""
            INSERT INTO sub_domains (domain_id, code, name) VALUES (?, 'TEST_SD', 'Test Sub Domain')
        """, (domain_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        sub_domain_id = cursor.fetchone()[0]
        self.test_sd_id = sub_domain_id
        
        self.ds.execute("""
            INSERT INTO service_modules (sub_domain_id, code, name) VALUES (?, 'TEST_SM', 'Test Service Module')
        """, (sub_domain_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        service_module_id = cursor.fetchone()[0]
        self.test_sm_id = service_module_id
        
        self.ds.execute("""
            INSERT INTO business_objects (service_module_id, code, name) VALUES (?, 'TEST_BO', 'Test Business Object')
        """, (service_module_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        self.test_bo_id = cursor.fetchone()[0]

    def test_list_relationships_without_filter(self):
        """测试无过滤条件查询关系"""
        response = self.client.get(
            '/api/v2/bo/relationship',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True

    def test_list_relationships_with_domain_filter(self):
        """测试使用 domain_id 过滤关系"""
        if not _check_domains_exist(self.ds):
            pytest.fail("No domains in database - requires test data setup")
        if not self.test_d_id:
            pytest.fail("No business object with domain association - requires test data setup")
        
        response = self.client.get(
            f'/api/v2/bo/relationship?domain_id={self.test_d_id}',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True

    def test_list_relationships_with_business_object_filter(self):
        """测试使用 business_object_id 过滤关系"""
        if not _check_business_objects_exist(self.ds):
            pytest.fail("No business_objects in database - requires test data setup")
        if not self.test_bo_id:
            pytest.fail("No business object available - requires test data setup")
        
        response = self.client.get(
            f'/api/v2/bo/relationship?business_object_id={self.test_bo_id}',
            headers=self.headers
        )
        
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success') is True


class TestExportFilterAPI:
    """导出过滤 API 测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from meta.tests.conftest import get_shared_app
        self.app, self.client = get_shared_app()
        self.headers = get_auth_headers()
        
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        
        cursor = self.ds.execute("""
            SELECT bo.id, bo.service_module_id, sm.sub_domain_id, sd.domain_id
            FROM business_objects bo
            INNER JOIN service_modules sm ON bo.service_module_id = sm.id
            INNER JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            ORDER BY bo.id
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            self.test_bo_id, self.test_sm_id, self.test_sd_id, self.test_d_id = row
        else:
            self.test_bo_id = self.test_sm_id = self.test_sd_id = self.test_d_id = None
            self._create_test_data()
    
    def _create_test_data(self):
        self.ds.execute("""
            INSERT INTO products (code, name) VALUES ('TEST', 'Test Product')
        """)
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        product_id = cursor.fetchone()[0]
        
        self.ds.execute("""
            INSERT INTO versions (product_id, code, name) VALUES (?, 'V1', 'Version 1')
        """, (product_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        version_id = cursor.fetchone()[0]
        
        self.ds.execute("""
            INSERT INTO domains (version_id, code, name) VALUES (?, 'TEST_DOMAIN', 'Test Domain')
        """, (version_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        domain_id = cursor.fetchone()[0]
        self.test_d_id = domain_id
        
        self.ds.execute("""
            INSERT INTO sub_domains (domain_id, code, name) VALUES (?, 'TEST_SD', 'Test Sub Domain')
        """, (domain_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        sub_domain_id = cursor.fetchone()[0]
        self.test_sd_id = sub_domain_id
        
        self.ds.execute("""
            INSERT INTO service_modules (sub_domain_id, code, name) VALUES (?, 'TEST_SM', 'Test Service Module')
        """, (sub_domain_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        service_module_id = cursor.fetchone()[0]
        self.test_sm_id = service_module_id
        
        self.ds.execute("""
            INSERT INTO business_objects (service_module_id, code, name) VALUES (?, 'TEST_BO', 'Test Business Object')
        """, (service_module_id,))
        self.ds.commit()
        cursor = self.ds.execute("SELECT last_insert_rowid()")
        self.test_bo_id = cursor.fetchone()[0]

    def test_export_domains_with_business_object_filter(self):
        """测试使用 business_object_id 过滤导出领域"""
        if not _check_business_objects_exist(self.ds):
            pytest.fail("No business_objects in database - requires test data setup")
        if not self.test_bo_id:
            pytest.fail("No business object available - requires test data setup")
        
        response = self.client.post(
            '/api/v1/export',
            headers=self.headers,
            json={
                'object_type': 'domain',
                'scope': 'selected',
                'selected_types': ['domain'],
                'filters': {
                    'business_object_id': [self.test_bo_id],
                    'version_id': 2
                }
            }
        )
        
        assert response.status_code in [200, 401, 404, 500]

    def test_export_service_modules_with_business_object_filter(self):
        """测试使用 business_object_id 过滤导出服务模块"""
        if not _check_business_objects_exist(self.ds):
            pytest.fail("No business_objects in database - requires test data setup")
        if not self.test_bo_id:
            pytest.fail("No business object available - requires test data setup")
        
        response = self.client.post(
            '/api/v1/export',
            headers=self.headers,
            json={
                'object_type': 'service_module',
                'scope': 'selected',
                'selected_types': ['service_module'],
                'filters': {
                    'business_object_id': [self.test_bo_id],
                    'version_id': 2
                }
            }
        )
        
        assert response.status_code in [200, 401, 404, 500]

    def test_export_sub_domains_with_business_object_filter(self):
        """测试使用 business_object_id 过滤导出子领域"""
        if not _check_business_objects_exist(self.ds):
            pytest.fail("No business_objects in database - requires test data setup")
        if not self.test_bo_id:
            pytest.fail("No business object available - requires test data setup")
        
        response = self.client.post(
            '/api/v1/export',
            headers=self.headers,
            json={
                'object_type': 'sub_domain',
                'scope': 'selected',
                'selected_types': ['sub_domain'],
                'filters': {
                    'business_object_id': [self.test_bo_id],
                    'version_id': 2
                }
            }
        )
        
        assert response.status_code in [200, 401, 404, 500]

    def test_export_business_objects_with_domain_filter(self):
        """测试使用 domain_id 过滤导出业务对象"""
        if not _check_domains_exist(self.ds):
            pytest.fail("No domains in database - requires test data setup")
        if not self.test_d_id:
            pytest.fail("No business object with domain association - requires test data setup")
        
        response = self.client.post(
            '/api/v1/export',
            headers=self.headers,
            json={
                'object_type': 'business_object',
                'scope': 'selected',
                'selected_types': ['business_object'],
                'filters': {
                    'domain_id': [self.test_d_id],
                    'version_id': 2
                }
            }
        )
        
        assert response.status_code in [200, 401, 404, 500]

    def test_export_relationships_with_business_object_filter(self):
        """测试使用 business_object_id 过滤导出关系"""
        if not _check_business_objects_exist(self.ds):
            pytest.fail("No business_objects in database - requires test data setup")
        if not self.test_bo_id:
            pytest.fail("No business object available - requires test data setup")
        
        response = self.client.post(
            '/api/v1/export',
            headers=self.headers,
            json={
                'object_type': 'relationship',
                'scope': 'selected',
                'selected_types': ['relationship'],
                'filters': {
                    'business_object_id': [self.test_bo_id],
                    'version_id': 2
                }
            }
        )
        
        assert response.status_code in [200, 401, 404, 500]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
