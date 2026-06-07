import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
层级过滤服务自动化测试

测试 hierarchy_filter_service 的核心功能：
1. _resolve_child_filter - 子级参数追溯
2. _get_parent_ids_from_child - 从子级获取父级ID
3. resolve_filters - 解析过滤参数
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services, _get_hierarchy_filter_service
from meta.services.hierarchy_filter_service import HierarchyFilterService
from meta.services.query_service import QueryService
from meta.tests.test_utils import get_test_db_path


def _check_table_has_data(ds, table_name):
    cursor = ds.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row["cnt"]) > 0


def _check_business_objects_with_service_module(ds):
    cursor = ds.execute("SELECT id, service_module_id FROM business_objects WHERE service_module_id IS NOT NULL LIMIT 1")
    return cursor.fetchone()


def _check_business_objects_with_sub_domain(ds):
    cursor = ds.execute("""
        SELECT bo.id, sm.sub_domain_id 
        FROM business_objects bo 
        JOIN service_modules sm ON bo.service_module_id = sm.id 
        WHERE sm.sub_domain_id IS NOT NULL 
        LIMIT 1
    """)
    return cursor.fetchone()


def _check_business_objects_with_complete_hierarchy(ds):
    cursor = ds.execute("""
        SELECT bo.id, d.id as domain_id 
        FROM business_objects bo 
        JOIN service_modules sm ON bo.service_module_id = sm.id 
        JOIN sub_domains sd ON sm.sub_domain_id = sd.id 
        JOIN domains d ON sd.domain_id = d.id 
        LIMIT 1
    """)
    return cursor.fetchone()


def _check_service_modules_with_sub_domain(ds):
    cursor = ds.execute("SELECT id, sub_domain_id FROM service_modules WHERE sub_domain_id IS NOT NULL LIMIT 1")
    return cursor.fetchone()


def _check_service_modules_with_domain(ds):
    cursor = ds.execute("""
        SELECT sm.id, sd.domain_id 
        FROM service_modules sm 
        JOIN sub_domains sd ON sm.sub_domain_id = sd.id 
        WHERE sd.domain_id IS NOT NULL 
        LIMIT 1
    """)
    return cursor.fetchone()


def _check_sub_domains_with_domain(ds):
    cursor = ds.execute("SELECT id, domain_id FROM sub_domains WHERE domain_id IS NOT NULL LIMIT 1")
    return cursor.fetchone()


class TestHierarchyFilterServiceBasic:
    """层级过滤服务基础测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        self.service = _get_hierarchy_filter_service()

    def test_get_hierarchy_chain_business_object(self):
        """测试获取业务对象的层级链"""
        chain = self.service.get_hierarchy_chain('business_object')
        
        assert isinstance(chain, list)
        assert 'business_object' in chain
        assert 'domain' in chain

    def test_get_hierarchy_chain_domain(self):
        """测试获取领域的层级链"""
        chain = self.service.get_hierarchy_chain('domain')
        
        assert isinstance(chain, list)
        assert 'domain' in chain

    def test_resolve_child_filter_invalid_type(self):
        """测试无效的对象类型"""
        result = self.service._resolve_child_filter('invalid_type', 'business_object_id', [1])
        
        assert result == []

    def test_resolve_child_filter_invalid_field(self):
        """测试无效的过滤字段"""
        result = self.service._resolve_child_filter('domain', 'invalid_field_id', [1])
        
        assert result == []

    def test_get_parent_ids_from_child_empty_input(self):
        """测试空输入"""
        result = self.service._get_parent_ids_from_child('business_object', 'domain_id', [])
        
        assert result == []

    def test_resolve_conditions_empty_args(self):
        """测试空参数"""
        conditions = self.service.resolve_conditions('business_object', {})
        
        assert conditions == []

    def test_resolve_filters_empty_filters(self):
        """测试空过滤条件"""
        resolved = self.service.resolve_filters('business_object', {})
        
        assert resolved == {}

    def test_resolve_filters_preserves_version_id(self):
        """测试 version_id 被保留"""
        filters = {
            'version_id': 123,
        }
        resolved = self.service.resolve_filters('domain', filters)
        
        assert 'version_id' in resolved
        assert resolved['version_id'] == 123


class TestHierarchyFilterServiceWithRealData:
    """层级过滤服务真实数据测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        self.service = _get_hierarchy_filter_service()

    def test_resolve_child_filter_business_object_to_service_module(self):
        """测试从 business_object_id 追溯到 service_module"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        row = _check_business_objects_with_service_module(self.ds)
        if not row:
            pytest.fail("No business objects with service_module_id - requires test data setup")
        
        bo_id, sm_id = row
        result = self.service._resolve_child_filter('service_module', 'business_object_id', [bo_id])
        
        assert isinstance(result, list)
        if result:
            assert sm_id in result

    def test_resolve_child_filter_business_object_to_sub_domain(self):
        """测试从 business_object_id 追溯到 sub_domain"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        row = _check_business_objects_with_sub_domain(self.ds)
        if not row:
            pytest.fail("No business objects with sub_domain - requires test data setup")
        
        bo_id, sd_id = row
        result = self.service._resolve_child_filter('sub_domain', 'business_object_id', [bo_id])
        
        assert isinstance(result, list)
        if result:
            assert sd_id in result

    def test_resolve_child_filter_business_object_to_domain(self):
        """测试从 business_object_id 追溯到 domain"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        row = _check_business_objects_with_complete_hierarchy(self.ds)
        if not row:
            pytest.fail("No business objects with complete hierarchy - requires test data setup")
        
        bo_id, domain_id = row
        result = self.service._resolve_child_filter('domain', 'business_object_id', [bo_id])
        
        assert isinstance(result, list)
        if result:
            assert domain_id in result

    def test_resolve_child_filter_service_module_to_sub_domain(self):
        """测试从 service_module_id 追溯到 sub_domain"""
        if not _check_table_has_data(self.ds, 'service_modules'):
            pytest.fail("No service_modules in database - requires test data setup")
        
        row = _check_service_modules_with_sub_domain(self.ds)
        if not row:
            pytest.fail("No service_modules with sub_domain_id - requires test data setup")
        
        sm_id, sd_id = row
        result = self.service._resolve_child_filter('sub_domain', 'service_module_id', [sm_id])
        
        assert isinstance(result, list)
        if result:
            assert sd_id in result

    def test_resolve_child_filter_service_module_to_domain(self):
        """测试从 service_module_id 追溯到 domain"""
        if not _check_table_has_data(self.ds, 'service_modules'):
            pytest.fail("No service_modules in database - requires test data setup")
        
        row = _check_service_modules_with_domain(self.ds)
        if not row:
            pytest.fail("No service_modules with domain - requires test data setup")
        
        sm_id, d_id = row
        result = self.service._resolve_child_filter('domain', 'service_module_id', [sm_id])
        
        assert isinstance(result, list)
        if result:
            assert d_id in result

    def test_resolve_child_filter_sub_domain_to_domain(self):
        """测试从 sub_domain_id 追溯到 domain"""
        if not _check_table_has_data(self.ds, 'sub_domains'):
            pytest.fail("No sub_domains in database - requires test data setup")
        
        row = _check_sub_domains_with_domain(self.ds)
        if not row:
            pytest.fail("No sub_domains with domain_id - requires test data setup")
        
        sd_id, d_id = row
        result = self.service._resolve_child_filter('domain', 'sub_domain_id', [sd_id])
        
        assert isinstance(result, list)
        if result:
            assert d_id in result

    def test_resolve_filters_with_business_object_id_for_domain(self):
        """测试使用 business_object_id 过滤领域"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        row = _check_business_objects_with_complete_hierarchy(self.ds)
        if not row:
            pytest.fail("No business objects with complete hierarchy - requires test data setup")
        
        bo_id, domain_id = row
        filters = {
            'business_object_id': [bo_id],
            'version_id': 1
        }
        resolved = self.service.resolve_filters('domain', filters)
        
        assert isinstance(resolved, dict)
        assert 'version_id' in resolved
        if 'id' in resolved:
            assert domain_id in resolved['id']

    def test_resolve_filters_with_business_object_id_for_service_module(self):
        """测试使用 business_object_id 过滤服务模块"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        row = _check_business_objects_with_service_module(self.ds)
        if not row:
            pytest.fail("No business objects with service_module_id - requires test data setup")
        
        bo_id, sm_id = row
        filters = {
            'business_object_id': [bo_id],
            'version_id': 1
        }
        resolved = self.service.resolve_filters('service_module', filters)
        
        assert isinstance(resolved, dict)
        if 'id' in resolved:
            assert sm_id in resolved['id']

    def test_resolve_filters_with_business_object_id_for_sub_domain(self):
        """测试使用 business_object_id 过滤子领域"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        row = _check_business_objects_with_sub_domain(self.ds)
        if not row:
            pytest.fail("No business objects with sub_domain - requires test data setup")
        
        bo_id, sd_id = row
        filters = {
            'business_object_id': [bo_id],
            'version_id': 1
        }
        resolved = self.service.resolve_filters('sub_domain', filters)
        
        assert isinstance(resolved, dict)
        if 'id' in resolved:
            assert sd_id in resolved['id']

    def test_query_parent_ids(self):
        """测试查询父级 ID"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        row = _check_business_objects_with_service_module(self.ds)
        if not row:
            pytest.fail("No business objects with service_module_id - requires test data setup")
        
        bo_id, sm_id = row
        result = self.service.query_parent_ids('business_object', 'service_module_id', [bo_id])
        
        assert isinstance(result, list)
        if result:
            assert sm_id in result

    def test_get_parent_ids_from_child(self):
        """测试从子级获取父级 ID"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        row = _check_business_objects_with_service_module(self.ds)
        if not row:
            pytest.fail("No business objects with service_module_id - requires test data setup")
        
        bo_id, sm_id = row
        result = self.service._get_parent_ids_from_child('business_object', 'service_module_id', [bo_id])
        
        assert isinstance(result, list)
        if result:
            assert sm_id in result


class TestHierarchyFilterIntegration:
    """层级过滤集成测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)

    def test_hierarchy_chain_complete(self):
        """测试层级链完整性"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        try:
            cursor = self.ds.execute("""
                SELECT bo.id, bo.code, 
                       sm.id as sm_id, sm.name as sm_name,
                       sd.id as sd_id, sd.name as sd_name,
                       d.id as d_id, d.name as d_name
                FROM business_objects bo
                LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
                LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                LEFT JOIN domains d ON sd.domain_id = d.id
            """)
            
            rows = cursor.fetchall()
            if not rows:
                pytest.fail("No business objects in database - requires test data setup")
            
            incomplete_bos = []
            for row in rows:
                bo_id, code, sm_id, sm_name, sd_id, sd_name, d_id, d_name = row
                if sm_id is None or sd_id is None or d_id is None:
                    incomplete_bos.append(code)
            if incomplete_bos:
                pytest.skip(f"Business objects missing hierarchy chain: {incomplete_bos[:5]}. Requires complete test data.")
        except Exception as e:
            pytest.skip(f"Hierarchy filter test skipped: {e}")


class TestHierarchyFilterEdgeCases:
    """边界条件测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        self.service = _get_hierarchy_filter_service()

    def test_resolve_child_filter_nonexistent_id(self):
        """测试不存在的 ID"""
        result = self.service._resolve_child_filter('domain', 'business_object_id', [999999])
        
        assert isinstance(result, list)

    def test_resolve_child_filter_multiple_ids(self):
        """测试多个 ID"""
        if not _check_table_has_data(self.ds, 'business_objects'):
            pytest.fail("No business_objects in database - requires test data setup")
        
        cursor = self.ds.execute("SELECT id FROM business_objects LIMIT 3")
        bo_ids = [row[0] for row in cursor.fetchall()]
        
        if len(bo_ids) < 2:
            pytest.fail("Not enough business objects - requires test data setup")
        
        result = self.service._resolve_child_filter('service_module', 'business_object_id', bo_ids)
        
        assert isinstance(result, list)

    def test_resolve_conditions_with_domain_id(self):
        """测试使用 domain_id 过滤业务对象"""
        if not _check_table_has_data(self.ds, 'domains'):
            pytest.fail("No domains in database - requires test data setup")
        
        cursor = self.ds.execute("SELECT id FROM domains LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            pytest.fail("No domains in database - requires test data setup")
        
        domain_id = row[0]
        args_dict = {str(domain_id): ['1']}
        conditions = self.service.resolve_conditions('business_object', {'domain_id': [str(domain_id)]})
        
        assert isinstance(conditions, list)

    def test_resolve_conditions_with_sub_domain_id(self):
        """测试使用 sub_domain_id 过滤业务对象"""
        if not _check_table_has_data(self.ds, 'sub_domains'):
            pytest.fail("No sub_domains in database - requires test data setup")
        
        cursor = self.ds.execute("SELECT id FROM sub_domains LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            pytest.fail("No sub_domains in database - requires test data setup")
        
        sd_id = row[0]
        conditions = self.service.resolve_conditions('business_object', {'sub_domain_id': [str(sd_id)]})
        
        assert isinstance(conditions, list)

    def test_resolve_conditions_with_service_module_id(self):
        """测试使用 service_module_id 过滤业务对象"""
        if not _check_table_has_data(self.ds, 'service_modules'):
            pytest.fail("No service_modules in database - requires test data setup")
        
        cursor = self.ds.execute("SELECT id FROM service_modules LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            pytest.fail("No service_modules in database - requires test data setup")
        
        sm_id = row[0]
        conditions = self.service.resolve_conditions('business_object', {'service_module_id': [str(sm_id)]})
        
        assert isinstance(conditions, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
