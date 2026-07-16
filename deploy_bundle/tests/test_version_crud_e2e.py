# -*- coding: utf-8 -*-
"""
产品版本 CRUD 自动化测试

覆盖场景：
1. 版本创建（含 status / code / is_current 字段）
2. 版本状态编辑（development ↔ active ↔ inactive）
3. 当前版本切换（is_current 互斥校验）
4. 版本编码唯一性
5. 必填字段校验
6. 版本删除
7. 产品-版本关联查询
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.services.manage_service import CreateRequest, UpdateRequest, DeleteRequest
from meta.services.query_service import SearchRequest, QueryCondition
from tests.conftest import TestBase


class TestVersionCreate(TestBase):
    """版本创建测试"""
    
    use_class_setup = True  # 启用类级别共享数据库，提升性能

    def test_create_version_with_status_development(self):
        """创建开发中状态的版本"""
        self.create_product('PROD001', '测试产品')
        data = {
            'product_id': self._find_by_field('product', 'code', 'PROD001')['id'],
            'code': 'V1.0',
            'name': '初始版本',
            'status': 'development',
            'is_current': 1,
            'description': '第一个版本',
        }
        req = CreateRequest(object_type='version', data=data)
        result = self.manage_service.create(req)
        
        assert result.success, f"创建失败: {result.message}"
        record = self._find_by_field('version', 'code', 'V1.0')
        assert record['status'] == 'development'
        assert record['is_current'] == 1
        assert record['name'] == '初始版本'

    def test_create_version_with_status_active(self):
        """创建启用状态的版本"""
        self.create_product('PROD002', '产品B')
        product = self._find_by_field('product', 'code', 'PROD002')
        data = {
            'product_id': product['id'],
            'code': 'V2.0',
            'name': '正式版',
            'status': 'active',
            'is_current': 0,
        }
        req = CreateRequest(object_type='version', data=data)
        result = self.manage_service.create(req)
        
        assert result.success
        record = self._find_by_field('version', 'code', 'V2.0')
        assert record['status'] == 'active'
        assert record['is_current'] == 0

    def test_create_version_code_unique(self):
        """版本编码必须唯一"""
        self.create_product('PROD003', '产品C')
        product = self._find_by_field('product', 'code', 'PROD003')
        
        data1 = {'product_id': product['id'], 'code': 'V3.0', 'name': '版本1'}
        req1 = CreateRequest(object_type='version', data=data1)
        assert self.manage_service.create(req1).success
        
        data2 = {'product_id': product['id'], 'code': 'V3.0', 'name': '版本2'}
        req2 = CreateRequest(object_type='version', data=data2)
        result = self.manage_service.create(req2)
        
        assert not result.success
        assert '已存在' in result.message or '重复' in result.message

    def test_create_version_missing_code_fails(self):
        """缺少编码字段应失败"""
        self.create_product('PROD004', '产品D')
        product = self._find_by_field('product', 'code', 'PROD004')
        
        data = {'product_id': product['id'], 'name': '无编码版本'}
        req = CreateRequest(object_type='version', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success

    def test_create_version_missing_product_id_fails(self):
        """缺少产品ID应失败"""
        data = {'code': 'V99', 'name': '无产品版本'}
        req = CreateRequest(object_type='version', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success


class TestVersionUpdate(TestBase):
    """版本更新测试"""
    
    use_class_setup = True

    def _setup_product_and_version(self):
        """辅助：创建产品和版本"""
        self.create_product('UPD_PROD', '更新测试产品')
        self.product = self._find_by_field('product', 'code', 'UPD_PROD')
        data = {
            'product_id': self.product['id'],
            'code': 'UPD_V1',
            'name': '待更新版本',
            'status': 'development',
            'is_current': 0,
        }
        req = CreateRequest(object_type='version', data=data)
        assert self.manage_service.create(req).success
        self.version = self._find_by_field('version', 'code', 'UPD_V1')

    def test_update_version_name(self):
        """更新版本名称"""
        self._setup_product_and_version()
        
        req = UpdateRequest(
            object_type='version',
            id=self.version['id'],
            data={'name': '已更新名称'}
        )
        result = self.manage_service.update(req)
        
        assert result.success
        updated = self._find_by_field('version', 'code', 'UPD_V1')
        assert updated['name'] == '已更新名称'

    def test_update_version_status_development_to_active(self):
        """更新版本状态: 开发中 → 启用"""
        self._setup_product_and_version()
        assert self.version['status'] == 'development'
        
        req = UpdateRequest(
            object_type='version',
            id=self.version['id'],
            data={'status': 'active'}
        )
        result = self.manage_service.update(req)
        
        assert result.success, f"状态更新失败: {result.message}"
        updated = self._find_by_field('version', 'code', 'UPD_V1')
        assert updated['status'] == 'active', \
            f"期望 status=active, 实际 status={updated.get('status')}"

    def test_update_version_status_active_to_inactive(self):
        """更新版本状态: 启用 → 停用"""
        self._setup_product_and_version()
        
        req = UpdateRequest(
            object_type='version',
            id=self.version['id'],
            data={'status': 'inactive'}
        )
        result = self.manage_service.update(req)
        
        assert result.success
        updated = self._find_by_field('version', 'code', 'UPD_V1')
        assert updated['status'] == 'inactive'

    def test_update_version_description(self):
        """更新版本描述"""
        self._setup_product_and_version()
        
        req = UpdateRequest(
            object_type='version',
            id=self.version['id'],
            data={'description': '新的描述信息'}
        )
        result = self.manage_service.update(req)
        
        assert result.success
        updated = self._find_by_field('version', 'code', 'UPD_V1')
        assert updated['description'] == '新的描述信息'

    def test_update_is_current_to_true(self):
        """将版本设为当前版本"""
        self._setup_product_and_version()
        assert self.version['is_current'] == 0
        
        req = UpdateRequest(
            object_type='version',
            id=self.version['id'],
            data={'is_current': 1}
        )
        result = self.manage_service.update(req)
        
        assert result.success
        updated = self._find_by_field('version', 'code', 'UPD_V1')
        assert updated['is_current'] == 1

    def test_update_is_current_to_false(self):
        """取消当前版本标记"""
        self._setup_product_and_version()
        
        req = UpdateRequest(
            object_type='version',
            id=self.version['id'],
            data={'is_current': 1}
        )
        assert self.manage_service.update(req).success
        
        req2 = UpdateRequest(
            object_type='version',
            id=self.version['id'],
            data={'is_current': 0}
        )
        result = self.manage_service.update(req2)
        
        assert result.success
        updated = self._find_by_field('version', 'code', 'UPD_V1')
        assert updated['is_current'] == 0


class TestVersionCurrentExclusive(TestBase):
    """当前版本互斥性测试"""
    
    use_class_setup = True

    def test_only_one_current_per_product(self):
        """每个产品只能有一个当前版本"""
        self.create_product('EXCL_PROD', '互斥测试产品')
        product = self._find_by_field('product', 'code', 'EXCL_PROD')
        
        v1_data = {
            'product_id': product['id'], 'code': 'EXCL_V1',
            'name': '版本1', 'status': 'active', 'is_current': 1,
        }
        v2_data = {
            'product_id': product['id'], 'code': 'EXCL_V2',
            'name': '版本2', 'status': 'active', 'is_current': 0,
        }
        
        req1 = CreateRequest(object_type='version', data=v1_data)
        req2 = CreateRequest(object_type='version', data=v2_data)
        assert self.manage_service.create(req1).success
        assert self.manage_service.create(req2).success
        
        v2 = self._find_by_field('version', 'code', 'EXCL_V2')
        
        req_update = UpdateRequest(
            object_type='version',
            id=v2['id'],
            data={'is_current': 1}
        )
        result = self.manage_service.update(req_update)
        
        assert not result.success
        assert '当前版本' in result.message or '只能有一个' in result.message

    def test_switch_current_version(self):
        """切换当前版本：先取消旧版本，再设置新版本"""
        self.create_product('SWITCH_PROD', '切换测试产品')
        product = self._find_by_field('product', 'code', 'SWITCH_PROD')
        
        for code, name, is_cur in [('SV1', '旧版', 1), ('SV2', '新版', 0)]:
            data = {
                'product_id': product['id'], 'code': code,
                'name': name, 'status': 'active', 'is_current': is_cur,
            }
            req = CreateRequest(object_type='version', data=data)
            assert self.manage_service.create(req).success
        
        old_v = self._find_by_field('version', 'code', 'SV1')
        new_v = self._find_by_field('version', 'code', 'SV2')
        
        Step1 = UpdateRequest(object_type='version', id=old_v['id'], data={'is_current': 0})
        assert self.manage_service.update(Step1).success
        
        Step2 = UpdateRequest(object_type='version', id=new_v['id'], data={'is_current': 1})
        assert self.manage_service.update(Step2).success
        
        old_updated = self._find_by_field('version', 'code', 'SV1')
        new_updated = self._find_by_field('version', 'code', 'SV2')
        assert old_updated['is_current'] == 0
        assert new_updated['is_current'] == 1


class TestVersionDelete(TestBase):
    """版本删除测试"""
    
    use_class_setup = True

    def test_delete_version(self):
        """删除版本"""
        self.create_product('DEL_PROD', '删除测试产品')
        product = self._find_by_field('product', 'code', 'DEL_PROD')
        
        data = {
            'product_id': product['id'], 'code': 'DEL_V1',
            'name': '待删除版本', 'status': 'active',
        }
        req = CreateRequest(object_type='version', data=data)
        assert self.manage_service.create(req).success
        
        version = self._find_by_field('version', 'code', 'DEL_V1')
        del_req = DeleteRequest(object_type='version', id=version['id'])
        result = self.manage_service.delete(del_req)
        
        assert result.success
        self.assert_record_not_exists('version', 'code', 'DEL_V1')

    def test_delete_current_version(self):
        """删除当前版本应成功"""
        self.create_product('DEL_PROD2', '删除测试2')
        product = self._find_by_field('product', 'code', 'DEL_PROD2')
        
        data = {
            'product_id': product['id'], 'code': 'DEL_V2',
            'name': '当前版本待删', 'status': 'active', 'is_current': 1,
        }
        req = CreateRequest(object_type='version', data=data)
        assert self.manage_service.create(req).success
        
        version = self._find_by_field('version', 'code', 'DEL_V2')
        del_req = DeleteRequest(object_type='version', id=version['id'])
        result = self.manage_service.delete(del_req)
        
        assert result.success


class TestVersionQuery(TestBase):
    """版本查询测试"""
    
    use_class_setup = True

    def test_query_versions_by_product(self):
        """按产品ID查询版本列表"""
        self.create_product('QRY_PROD', '查询测试产品')
        product = self._find_by_field('product', 'code', 'QRY_PROD')
        
        for i, status in enumerate(['development', 'active', 'inactive']):
            data = {
                'product_id': product['id'],
                'code': f'QV{i+1}',
                'name': f'版本{i+1}',
                'status': status,
                'is_current': 1 if i == 1 else 0,
            }
            req = CreateRequest(object_type='version', data=data)
            assert self.manage_service.create(req).success
        
        versions = self.search_all('version', product_id=product['id'])
        assert len(versions) == 3
        
        current_versions = [v for v in versions if v.get('is_current') == 1]
        assert len(current_versions) == 1
        assert current_versions[0]['status'] == 'active'

    def test_query_version_by_status(self):
        """按状态筛选版本"""
        self.create_product('QRY_PROD2', '查询测试2')
        product = self._find_by_field('product', 'code', 'QRY_PROD2')
        
        for code, status in [('QS1', 'development'), ('QS2', 'active'), ('QS3', 'active')]:
            data = {
                'product_id': product['id'], 'code': code,
                'name': code, 'status': status,
            }
            req = CreateRequest(object_type='version', data=data)
            assert self.manage_service.create(req).success
        
        active_versions = self.search_all('version', status='active')
        assert len(active_versions) == 2
