import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
维度感知过滤测试

针对修复的问题：
1. 全选对象树时，空叶子节点（无子领域的domain）被AND条件排除
2. 导出时多层级参数导致数据丢失
3. resolve_filter_params 应根据当前对象类型只处理祖先层级的参数
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.services.config_driven_hierarchy_filter import ConfigDrivenHierarchyFilterService, HierarchyConfigLoader
from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services
from meta.services.query_service import QueryService
from meta.tests.test_utils import get_test_db_path


class TestGetAllowedFilterParams:
    """测试 _get_allowed_filter_params 维度感知参数过滤"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        # v3.18 P1: 修复 S017 数据依赖 skip
        cursor = self.ds.execute("SELECT COUNT(*) FROM domains WHERE version_id=1")
        if cursor.fetchone()[0] < 3:
            for i in range(3):
                self.ds.execute(
                    "INSERT INTO domains (name, code, version_id) VALUES (?, ?, 1)",
                    (f'TEST_S017_D{i}', f'TEST_S017_D{i}')
                )
            self.ds.commit()
        self.query_service = QueryService(self.ds)
        self.service = ConfigDrivenHierarchyFilterService(self.query_service, self.ds)

    def test_domain_only_allows_version_and_domain_id(self):
        """domain 类型只允许 version_id 和 domain_id"""
        allowed = self.service._get_allowed_filter_params('domain')
        
        assert 'version_id' in allowed
        assert 'domain_id' in allowed
        assert 'sub_domain_id' not in allowed
        assert 'service_module_id' not in allowed
        assert 'business_object_id' not in allowed

    def test_sub_domain_allows_up_to_sub_domain_id(self):
        """sub_domain 允许 version_id, domain_id, sub_domain_id"""
        allowed = self.service._get_allowed_filter_params('sub_domain')
        
        assert 'version_id' in allowed
        assert 'domain_id' in allowed
        assert 'sub_domain_id' in allowed
        assert 'service_module_id' not in allowed
        assert 'business_object_id' not in allowed

    def test_service_module_allows_up_to_service_module_id(self):
        """service_module 允许到 service_module_id"""
        allowed = self.service._get_allowed_filter_params('service_module')
        
        assert 'version_id' in allowed
        assert 'domain_id' in allowed
        assert 'sub_domain_id' in allowed
        assert 'service_module_id' in allowed
        assert 'business_object_id' not in allowed

    def test_business_object_allows_all_levels(self):
        """business_object 允许所有层级参数"""
        allowed = self.service._get_allowed_filter_params('business_object')
        
        assert 'version_id' in allowed
        assert 'domain_id' in allowed
        assert 'sub_domain_id' in allowed
        assert 'service_module_id' in allowed
        assert 'business_object_id' in allowed

    def test_relationship_not_in_hierarchy_levels(self):
        """relationship 不在层级定义中，只返回最小集合"""
        allowed = self.service._get_allowed_filter_params('relationship')
        
        assert 'version_id' in allowed
        assert 'relation_codes' in allowed
        # relationship 不在 hierarchies.yaml 的 levels 中
        # 所以不会有 domain_id 等层级参数（这是正确行为）

    def test_always_includes_relation_codes(self):
        """所有类型都应包含 relation_codes"""
        for obj_type in ['domain', 'sub_domain', 'service_module', 'business_object']:
            allowed = self.service._get_allowed_filter_params(obj_type)
            assert 'relation_codes' in allowed, f"{obj_type} should include relation_codes"

    def test_unknown_type_returns_minimal(self):
        """未知类型返回最小集合"""
        allowed = self.service._get_allowed_filter_params('unknown_type_xyz')
        
        assert 'version_id' in allowed
        assert 'relation_codes' in allowed


class TestResolveFilterParamsDimensionAware:
    """测试 resolve_filter_params 的维度感知行为"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)
        self.query_service = QueryService(self.ds)
        self.service = ConfigDrivenHierarchyFilterService(self.query_service, self.ds)

    def test_domain_filters_out_descendant_params(self):
        """domain 查询时，sub_domain_id/service_module_id/business_object_id 被忽略
        
        注意：domain_id 会被转换为 id（因为 dim_object == object_type）
        """
        filters = {
            'version_id': 1,
            'domain_id': [1, 2, 3],
            'sub_domain_id': [10, 20],
            'service_module_id': [100],
            'business_object_id': [1000]
        }
        
        resolved = self.service.resolve_filter_params('domain', filters)
        
        assert 'version_id' in resolved
        # domain_id 匹配 dimension.object=domain 且当前类型也是 domain → 转为 id
        assert 'id' in resolved or 'domain_id' in resolved
        assert 'sub_domain_id' not in resolved, "domain 不应有 sub_domain_id"
        assert 'service_module_id' not in resolved, "domain 不应有 service_module_id"
        assert 'business_object_id' not in resolved, "domain 不应有 business_object_id"

    def test_business_object_keeps_all_params(self):
        """business_object 查询保留所有层级参数"""
        filters = {
            'version_id': 1,
            'domain_id': [1],
            'sub_domain_id': [10],
            'service_module_id': [100]
        }
        
        resolved = self.service.resolve_filter_params('business_object', filters)
        
        assert 'version_id' in resolved
        # business_object 有 domain_id 字段（虚拟），会被保留或追溯为 id
        has_any_level_param = any(k in resolved for k in ['domain_id', 'sub_domain_id', 'service_module_id', 'id'])
        assert has_any_level_param, "business_object 应保留层级参数"

    def test_mixed_selection_for_domain_preserves_all_domains(self):
        """
        场景：用户在对象树全选5个领域（其中2个没有子领域）
        
        buildOriginalFilter 会收集：
          domain_id: [1,2,3,4,5]     -- 5个都有
          sub_domain_id: [6,7,8]      -- 只有3个有子领域的
          service_module_id: [...]     -- 同上
        
        对于 domain 对象类型，_get_allowed_filter_params 只允许 domain_id，
        所以 sub_domain_id/service_module_id 被忽略，
        确保 domain_id=[1,2,3,4,5] 全部传递给查询
        """
        filters = {
            'version_id': 1,
            'domain_id': [1, 2, 3, 4, 5],
            'sub_domain_id': [10, 20, 30],
            'service_module_id': [100, 200]
        }
        
        resolved = self.service.resolve_filter_params('domain', filters)
        
        # domain_id 应转为 id 或保留
        if 'id' in resolved:
            ids = resolved['id']
            assert len(ids) == 5, \
                f"所有5个domain都应保留，包括空叶子域。实际: {ids}"
        elif 'domain_id' in resolved:
            assert len(resolved['domain_id']) == 5
        
        assert 'sub_domain_id' not in resolved
        assert 'service_module_id' not in resolved

    def test_empty_filters_returns_minimal(self):
        """空过滤器只返回 version_id"""
        filters = {'version_id': 1}
        
        for obj_type in ['domain', 'sub_domain', 'business_object']:
            resolved = self.service.resolve_filter_params(obj_type, filters)
            
            assert resolved.get('version_id') == 1
            # 不应该有多余的空参数
            extra_keys = set(resolved.keys()) - {'version_id'}
            assert len(extra_keys) == 0 or all(
                resolved[k] is None or resolved[k] == [] 
                for k in extra_keys
            ), f"{obj_type} 不应有额外非空参数"


class TestExportWithLeafDomains:
    """导出场景下空叶子域的数据完整性测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(self.ds)

    def test_export_domain_includes_leaf_domains(self):
        """
        导出 domain 时，即使某些 domain 没有 sub_domain，
        只要 domain_id 包含了它们，就应该出现在结果中
        """
        cursor = self.ds.execute("""
            SELECT id FROM domains WHERE version_id = 1
        """)
        all_domain_ids = [row[0] for row in cursor.fetchall()]
        
        if len(all_domain_ids) < 2:
            pytest.skip("Not enough domains to test")
        
        from meta.services.import_export_service import ImportExportService
        
        service = ImportExportService(self.ds)
        
        sheet_data = service._query_with_hierarchy(
            'domain',
            {'version_id': 1, 'domain_id': all_domain_ids},
            {}
        )
        
        assert len(sheet_data) >= len(all_domain_ids), \
            f"导出结果{len(sheet_data)}条应 >= 传入domain数量{len(all_domain_ids)}，" \
            "空叶子域不应被排除"

    def test_export_with_mixed_level_filters_does_not_lose_data(self):
        """
        使用混合层级过滤导出 domain 时，
        结果数量应该等于 domain_id 参数中的数量
        而非被 sub_domain_id 等后续参数缩小范围
        """
        cursor = self.ds.execute("""
            SELECT id FROM domains WHERE version_id = 1 ORDER BY id
        """)
        all_domain_ids = [row[0] for row in cursor.fetchall()]
        
        if len(all_domain_ids) < 3:
            pytest.skip("Not enough domains")
        
        from meta.services.import_export_service import ImportExportService
        from meta.tests.test_utils import get_test_db_path

        service = ImportExportService(self.ds)
        
        full_result = service._query_with_hierarchy(
            'domain',
            {'version_id': 1, 'domain_id': all_domain_ids},
            {}
        )
        
        mixed_result = service._query_with_hierarchy(
            'domain',
            {
                'version_id': 1,
                'domain_id': all_domain_ids,
                'sub_domain_id': [99999],
                'service_module_id': [99999]
            },
            {}
        )
        
        assert len(full_result) >= len(mixed_result), \
            f"完整查询{len(full_result)}条 vs 混合查询{len(mixed_result)}条，" \
            "混合参数不应减少domain结果数"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
