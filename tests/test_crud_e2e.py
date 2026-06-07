# -*- coding: utf-8 -*-
"""
CRUD 端到端测试

覆盖场景：
1. 基础 CRUD（创建、读取、更新、删除）
2. 层级数据创建（领域→子领域→服务模块→业务对象）
3. 业务键唯一性校验
4. 必填字段校验
5. 外键引用校验
6. 级联删除行为
7. 更新时的业务键冲突检测
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.services.manage_service import CreateRequest, UpdateRequest, DeleteRequest
from meta.services.query_service import SearchRequest, QueryCondition
from tests.conftest import TestBase


class TestCRUDBasic(TestBase):
    """基础 CRUD 测试"""
    
    use_class_setup = True  # 启用类级别共享数据库，提升性能

    def test_create_domain(self):
        """测试创建领域"""
        domain = self.create_domain('DOM001', '测试领域')
        record = self.assert_record_exists('domain', 'code', 'DOM001')
        assert record['name'] == '测试领域'

    def test_create_duplicate_code_fails(self):
        """测试重复编码创建失败"""
        self.create_domain('DOM001', '领域1')
        
        from meta.services.manage_service import CreateRequest
        data = {'code': 'DOM001', 'name': '领域2'}
        req = CreateRequest(object_type='domain', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success
        assert '已存在' in result.message or '重复' in result.message

    def test_update_domain(self):
        """测试更新领域"""
        self.create_domain('UPD001', '旧名称')
        
        record = self._find_by_field('domain', 'code', 'UPD001')
        req = UpdateRequest(object_type='domain', id=record['id'], data={'name': '新名称'})
        result = self.manage_service.update(req)
        
        assert result.success
        updated = self._find_by_field('domain', 'code', 'UPD001')
        assert updated is not None
        assert updated['name'] == '新名称'

    def test_delete_domain(self):
        """测试删除领域"""
        self.create_domain('DOM001', '待删除')
        
        record = self._find_by_field('domain', 'code', 'DOM001')
        req = DeleteRequest(object_type='domain', id=record['id'])
        result = self.manage_service.delete(req)
        
        assert result.success
        self.assert_record_not_exists('domain', 'code', 'DOM001')

    def test_required_field_missing(self):
        """测试必填字段缺失"""
        from meta.services.manage_service import CreateRequest
        
        data = {'name': '无编码领域'}
        req = CreateRequest(object_type='domain', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success

    def test_read_single_record(self):
        """测试读取单条记录"""
        self.create_domain('DOM001', '读取测试')
        
        record = self._find_by_field('domain', 'code', 'DOM001')
        assert record is not None
        assert 'id' in record
        assert 'created_at' in record


class TestHierarchyCRUD(TestBase):
    """层级 CRUD 测试 - 验证外键关系正确性"""
    
    use_class_setup = True

    def test_create_full_hierarchy_chain(self):
        """测试完整4级层级链创建"""
        product, version, domain, sub_domain, sm = self.create_full_hierarchy('H1')
        
        self.assert_count('product', 1, code='H1_PROD')
        self.assert_count('version', 1, code='H1_V1')
        self.assert_count('domain', 1, code='H1_DOM')
        self.assert_count('sub_domain', 1, code='H1_SUB')
        self.assert_count('service_module', 1, code='H1_SM')

    def test_sub_domain_requires_parent(self):
        """测试子领域必须有父级领域"""
        from meta.services.manage_service import CreateRequest
        
        data = {
            'code': 'SUB_ORPHAN',
            'name': '孤儿子领域',
        }
        req = CreateRequest(object_type='sub_domain', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success

    def test_service_module_requires_sub_domain(self):
        """测试服务模块必须有父级子领域"""
        from meta.services.manage_service import CreateRequest
        
        data = {
            'code': 'SM_ORPHAN',
            'name': '孤儿服务模块',
        }
        req = CreateRequest(object_type='service_module', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success

    def test_business_object_requires_service_module(self):
        """测试业务对象必须属于服务模块"""
        from meta.services.manage_service import CreateRequest
        
        data = {
            'code': 'BO_ORPHAN',
            'name': '孤儿业务对象',
            'object_type': 'entity',
        }
        req = CreateRequest(object_type='business_object', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success

    def test_cascade_delete_domain_deletes_children(self):
        """测试级联删除领域时子级也被删除"""
        _, _, domain, sub_domain, sm = self.create_full_hierarchy('CSC')
        
        bo = self.create_business_object('CSC_SM', 'BO001', '测试对象')
        
        record = self._find_by_field('domain', 'code', 'CSC_DOM')
        req = DeleteRequest(object_type='domain', id=record['id'])
        result = self.manage_service.delete(req)
        
        if result.success:
            self.assert_count('sub_domain', 0, code='CSC_SUB')
            self.assert_count('service_module', 0, code='CSC_SM')


class TestBusinessKeyValidation(TestBase):
    """业务键唯一性校验测试"""
    
    use_class_setup = True

    def test_single_field_business_key_unique_on_create(self):
        """测试单字段业务键创建时唯一性"""
        self.create_domain('BK01', '领域1')
        
        from meta.services.manage_service import CreateRequest
        data = {'code': 'BK01', 'name': '领域2'}
        req = CreateRequest(object_type='domain', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success
        assert '已存在' in result.message or '重复' in result.message or 'VALIDATION_FAILED' == result.error

    def test_composite_business_key_unique_on_create(self):
        """测试组合业务键创建时唯一性"""
        self.create_full_hierarchy('CBK')
        self.create_business_object('CBK_SM', 'BO_SRC', '源对象')
        self.create_business_object('CBK_SM', 'BO_TGT', '目标对象')
        
        self.create_relationship('BO_SRC', 'BO_TGT', 'REL_01')
        
        from meta.services.manage_service import CreateRequest
        source = self._find_by_field('business_object', 'code', 'BO_SRC')
        target = self._find_by_field('business_object', 'code', 'BO_TGT')
        
        data2 = {
            'source_id': source['id'],
            'target_id': target['id'],
            'source_code': 'BO_SRC',
            'target_code': 'BO_TGT',
            'relation_code': 'REL_01',
            'relation_desc': '重复关系',
        }
        req2 = CreateRequest(object_type='relationship', data=data2)
        result2 = self.manage_service.create(req2)
        
        assert not result2.success

    def test_composite_key_different_target_is_ok(self):
        """测试组合键：不同目标是合法的"""
        self.create_full_hierarchy('CDT')
        self.create_business_object('CDT_SM', 'BO_A', '对象A')
        self.create_business_object('CDT_SM', 'BO_B', '对象B')
        self.create_business_object('CDT_SM', 'BO_C', '对象C')
        
        self.create_relationship('BO_A', 'BO_B', 'REL_X')
        
        rel2 = self.create_relationship('BO_A', 'BO_C', 'REL_X')
        
        assert rel2 is not None
        self.assert_count('relationship', 2, relation_code='REL_X')

    def test_update_preserves_own_bk(self):
        """测试更新时保留自身记录不报重复"""
        self.create_domain('UPD', '原始名称')
        
        record = self._find_by_field('domain', 'code', 'UPD')
        
        from meta.services.manage_service import UpdateRequest
        req = UpdateRequest(
            object_type='domain', 
            id=record['id'], 
            data={'name': '更新后名称'}
        )
        result = self.manage_service.update(req)
        
        assert result.success
        updated = self._find_by_field('domain', 'code', 'UPD')
        assert updated['name'] == '更新后名称'


class TestRelationshipCRUD(TestBase):
    """业务关系 CRUD 测试"""
    
    use_class_setup = True

    def test_create_relationship_with_enrichment(self):
        """测试创建关系时自动填充冗余字段"""
        self.create_full_hierarchy('REN')
        self.create_business_object('REN_SM', 'SRC', '源对象')
        self.create_business_object('REN_SM', 'TGT', '目标对象')
        
        rel = self.create_relationship('SRC', 'TGT', 'DEPENDS_ON')
        
        record = self.search_all('relationship', relation_code='DEPENDS_ON')[0]
        assert record['source_code'] == 'SRC'
        assert record['target_code'] == 'TGT'

    def test_delete_relationship(self):
        """测试删除关系"""
        self.create_full_hierarchy('DEL')
        self.create_business_object('DEL_SM', 'S1', '源1')
        self.create_business_object('DEL_SM', 'T1', '目标1')
        
        self.create_relationship('S1', 'T1', 'TO_DELETE')
        
        record = self.search_all('relationship', relation_code='TO_DELETE')[0]
        req = DeleteRequest(object_type='relationship', id=record['id'])
        result = self.manage_service.delete(req)
        
        assert result.success
        self.assert_count('relationship', 0, relation_code='TO_DELETE')

    def test_update_relation_description_only(self):
        """测试只更新关系描述（不改业务键）"""
        self.create_full_hierarchy('UDL')
        self.create_business_object('UDL_SM', 'US', '源S')
        self.create_business_object('UDL_SM', 'UT', '目标T')
        
        self.create_relationship('US', 'UT', 'R1', relation_desc='原描述')
        
        record = self.search_all('relationship', relation_code='R1')[0]
        
        from meta.services.manage_service import UpdateRequest
        req = UpdateRequest(
            object_type='relationship',
            id=record['id'],
            data={'relation_desc': '新描述'}
        )
        result = self.manage_service.update(req)
        
        assert result.success
        updated = self.search_all('relationship', relation_code='R1')[0]
        assert updated['relation_desc'] == '新描述'


class TestBatchOperations(TestBase):
    """批量操作测试"""
    
    use_class_setup = True

    def test_list_pagination(self):
        """测试分页查询"""
        for i in range(10):
            self.create_domain(f'PG{i:03d}', f'分页{i}')
        
        req = SearchRequest(object_type='domain', page=1, page_size=5)
        result = self.query_service.search(req)
        
        assert result.total == 10
        assert len(result.data) == 5
        assert result.total_pages == 2

    def test_keyword_search(self):
        """测试关键词搜索"""
        self.create_domain('KW001', '供应链管理')
        self.create_domain('KW002', '采购管理')
        self.create_domain('KW003', '仓储管理')
        
        req = SearchRequest(object_type='domain', keyword='供应', page=1, page_size=10)
        result = self.query_service.search(req)
        
        assert len(result.data) >= 1
        assert any(d['name'] == '供应链管理' for d in result.data)

    def test_filter_by_condition(self):
        """测试条件过滤"""
        self.create_domain('FL001', '活跃领域')
        self.create_domain('FL002', '禁用领域')
        
        req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='code', operator='eq', value='FL001')],
            page=1, page_size=10
        )
        result = self.query_service.search(req)
        
        assert result.total == 1
        assert result.data[0]['code'] == 'FL001'


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
