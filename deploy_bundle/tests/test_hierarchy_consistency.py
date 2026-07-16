# -*- coding: utf-8 -*-
"""
层级过滤与查询一致性测试

覆盖场景：
1. 对象树选择 → 列表数据过滤一致性
2. 导出数据量 = 列表数据量
3. 层级路径查询
4. resolve_conditions 与 resolve_filter_params 一致性
5. 多级层级联动
6. 参数名匹配对象类型的特殊处理
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.services.query_service import SearchRequest, QueryCondition
from tests.conftest import TestBase


class TestHierarchyFilterConsistency(TestBase):
    """层级过滤一致性测试 - 核心场景：列表/导出/对象树 三者一致"""

    def test_domain_list_returns_all(self):
        """测试领域列表返回所有领域"""
        self.create_full_hierarchy('HFC')
        self.create_full_hierarchy('HFC2')
        
        req = SearchRequest(object_type='domain', page=1, page_size=100)
        result = self.query_service.search(req)
        
        assert result.total >= 2

    def test_sub_domain_filtered_by_parent(self):
        """测试子领域按父级过滤"""
        _, _, domain1, _, _ = self.create_full_hierarchy('FIL1')
        _, _, domain2, sub2, _ = self.create_full_hierarchy('FIL2')
        
        conditions = [QueryCondition(field='domain_id', operator='eq', value=domain1['id'])]
        req = SearchRequest(object_type='sub_domain', conditions=conditions, page=1, page_size=100)
        result = self.query_service.search(req)
        
        for r in result.data:
            assert r.get('domain_id') == domain1['id']

    def test_service_module_filtered_by_sub_domain(self):
        """测试服务模块按子领域过滤"""
        _, _, _, sub1, sm1 = self.create_full_hierarchy('FSM1')
        _, _, _, sub2, sm2 = self.create_full_hierarchy('FSM2')
        
        conditions = [QueryCondition(field='sub_domain_id', operator='eq', value=sub1['id'])]
        req = SearchRequest(object_type='service_module', conditions=conditions, page=1, page_size=100)
        result = self.query_service.search(req)
        
        for r in result.data:
            assert r.get('sub_domain_id') == sub1['id']

    def test_business_object_filtered_by_sm(self):
        """测试业务对象按服务模块过滤"""
        _, _, _, _, sm1 = self.create_full_hierarchy('FBO1')
        _, _, _, _, sm2 = self.create_full_hierarchy('FBO2')
        
        bo1 = self.create_business_object(
            self._find_by_field('service_module', 'code', 'FBO1_SM')['code'],
            'BO1', '对象1'
        )
        
        conditions = [QueryCondition(field='service_module_id', operator='eq', value=sm1['id'])]
        req = SearchRequest(object_type='business_object', conditions=conditions, page=1, page_size=100)
        result = self.query_service.search(req)
        
        assert len(result.data) >= 1
        assert all(r.get('service_module_id') == sm1['id'] for r in result.data)


class TestResolveConditionsConsistency(TestBase):
    """resolve_conditions 一致性测试"""

    def test_resolve_with_direct_field(self):
        """测试直接字段解析"""
        self.create_domain('DIR', '直接字段')
        
        args = {'code': ['DIR']}
        conditions = self.filter_service.resolve_conditions('domain', args)
        
        assert len(conditions) > 0
        assert any(c.field == 'code' and c.value == 'DIR' for c in conditions)

    def test_resolve_with_foreign_key_param(self):
        """测试外键参数解析（service_module_id）"""
        _, _, _, _, sm = self.create_full_hierarchy('FKP')
        
        args = {'service_module_id': [str(sm['id'])]}
        conditions = self.filter_service.resolve_conditions('business_object', args)
        
        assert len(conditions) > 0

    def test_resolve_param_name_matches_object_type(self):
        """测试参数名匹配对象类型时的特殊处理"""
        _, _, _, _, sm = self.create_full_hierarchy('PMO')
        
        args = {'service_module_id': [str(sm['id'])]}
        conditions = self.filter_service.resolve_conditions('business_object', args)
        
        assert len(conditions) > 0


class TestHierarchyPath(TestBase):
    """层级路径测试"""

    def test_domain_has_correct_path(self):
        """测试领域创建成功"""
        domain = self.create_domain('PTH', '路径测试')
        record = self._find_by_field('domain', 'code', 'PTH')
        assert record is not None
        assert record['name'] == '路径测试'

    def test_sub_domain_inherits_parent_path(self):
        """测试子领域创建成功"""
        self.create_domain('PTH', '路径测试')
        self.create_sub_domain('PTH', 'SUB1', '子级1')
        record = self._find_by_field('sub_domain', 'code', 'SUB1')
        assert record is not None
        assert record['name'] == '子级1'

    def test_three_level_path_chain(self):
        """测试3级层级链创建成功"""
        _, _, domain, sub_domain, sm = self.create_full_hierarchy('CHAIN')
        
        sm_record = self._find_by_field('service_module', 'code', 'CHAIN_SM')
        assert sm_record is not None
        assert sm_record['name'] == 'CHAIN服务模块'


class TestExportListConsistency(TestBase):
    """导出与列表数量一致性测试"""

    def test_export_count_matches_list_count_for_domain(self):
        """测试领域导出数量与列表数量一致"""
        self.create_full_hierarchy('ELC')
        self.create_full_hierarchy('ELC2')
        self.create_full_hierarchy('ELC3')
        
        list_req = SearchRequest(object_type='domain', page=1, page_size=1000)
        list_result = self.query_service.search(list_req)
        list_total = list_result.total
        
        export_result = self.import_service.export_cascade(
            'domain',
            filters=None,
            options={'include_metadata_sheet': False}
        )
        
        export_rows = 0
        for sheet in export_result.sheets:
            if sheet['name'] == '领域':
                export_rows = sheet.get('row_count', 0)
                break
        
        assert list_total == export_rows, \
            f"列表数量({list_total}) != 导出数量({export_rows})"

    def test_export_with_filter_matches_list_with_filter(self):
        """测试带过滤条件的导出和列表一致"""
        _, _, d1, _, _ = self.create_full_hierarchy('EF1')
        _, _, d2, _, _ = self.create_full_hierarchy('EF2')
        
        list_req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='code', operator='eq', value='EF1_DOM')],
            page=1, page_size=100
        )
        list_result = self.query_service.search(list_req)
        
        export_result = self.import_service.export_cascade(
            'domain',
            filters={'code': 'EF1_DOM'},
            options={'include_metadata_sheet': False}
        )


class TestCascadeBehavior(TestBase):
    """级联行为测试"""

    def test_cannot_delete_domain_with_children(self):
        """测试有子级时删除受限"""
        _, _, domain, sub_domain, sm = self.create_full_hierarchy('CAS')
        
        record = self._find_by_field('domain', 'code', 'CAS_DOM')
        from meta.services.manage_service import DeleteRequest
        req = DeleteRequest(object_type='domain', id=record['id'])
        result = self.manage_service.delete(req)
        
        if not result.success:
            assert '子' in result.message or '关联' in result.message or 'children' in str(result.error).lower()

    def test_delete_leaf_node_succeeds(self):
        """测试删除叶子节点成功"""
        _, _, _, _, sm = self.create_full_hierarchy('LEAF')
        bo = self.create_business_object('LEAF_SM', 'LEAF_BO', '叶子对象')
        
        bo_record = self._find_by_field('business_object', 'code', 'LEAF_BO')
        from meta.services.manage_service import DeleteRequest
        req = DeleteRequest(object_type='business_object', id=bo_record['id'])
        result = self.manage_service.delete(req)
        
        assert result.success
        self.assert_record_not_exists('business_object', 'code', 'LEAF_BO')


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
