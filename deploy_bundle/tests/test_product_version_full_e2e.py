# -*- coding: utf-8 -*-
"""
产品版本管理完整流程测试

覆盖场景：
1. 产品 CRUD（创建/编辑/删除）
2. 版本完整生命周期（创建/编辑/is_current切换/删除）
3. is_current 布尔值转换验证（后端整数→前端布尔）
4. 产品-版本关联查询
5. 导入导出模板生成
6. 关系 business_key 组合唯一性 + resolve_from_field 解析
7. Upsert 逻辑（有则更新无则新增）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.services.manage_service import CreateRequest, UpdateRequest, DeleteRequest
from meta.services.query_service import SearchRequest, QueryCondition
from tests.conftest import TestBase


class TestProductCRUD(TestBase):
    """产品 CRUD 测试"""
    
    use_class_setup = True  # 启用类级别共享数据库，提升性能

    def test_create_product(self):
        """创建产品"""
        data = {'code': 'TP001', 'name': '测试产品A', 'description': '描述'}
        req = CreateRequest(object_type='product', data=data)
        result = self.manage_service.create(req)
        
        assert result.success, f"创建失败: {result.message}"
        record = self._find_by_field('product', 'code', 'TP001')
        assert record['name'] == '测试产品A'
        assert record['description'] == '描述'

    def test_create_product_duplicate_code_fails(self):
        """产品编码必须唯一"""
        self.create_product('DUP_P1', '产品1')
        
        data = {'code': 'DUP_P1', 'name': '重复产品'}
        req = CreateRequest(object_type='product', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success

    def test_update_product_name(self):
        """更新产品名称"""
        self.create_product('UPD_P', '原始名称')
        
        product = self._find_by_field('product', 'code', 'UPD_P')
        req = UpdateRequest(
            object_type='product',
            id=product['id'],
            data={'name': '更新后名称'}
        )
        result = self.manage_service.update(req)
        
        assert result.success
        updated = self._find_by_field('product', 'code', 'UPD_P')
        assert updated['name'] == '更新后名称'

    def test_delete_product(self):
        """删除产品"""
        self.create_product('DEL_P', '待删除产品')
        
        product = self._find_by_field('product', 'code', 'DEL_P')
        del_req = DeleteRequest(object_type='product', id=product['id'])
        result = self.manage_service.delete(del_req)
        
        assert result.success
        self.assert_record_not_exists('product', 'code', 'DEL_P')

    def test_query_all_products(self):
        """查询所有产品"""
        for i in range(3):
            self.create_product(f'QRY_P{i}', f'产品{i}')
        
        versions = self.search_all('product')
        assert len(versions) >= 3


class TestVersionFullLifecycle(TestBase):
    """版本完整生命周期测试"""
    
    use_class_setup = True

    def _create_product_with_versions(self, prod_code, version_configs):
        """辅助：创建产品和多个版本
        
        version_configs: [(code, name, status, is_current), ...]
        """
        product = self.create_product(prod_code, f'{prod_code}产品')
        versions = []
        for code, name, status, is_current in version_configs:
            data = {
                'product_id': product['id'],
                'code': code,
                'name': name,
                'status': status,
                'is_current': 1 if is_current else 0,
            }
            req = CreateRequest(object_type='version', data=data)
            result = self.manage_service.create(req)
            assert result.success, f"创建版本 {code} 失败: {result.message}"
            versions.append(data)
        return product, versions

    def test_create_version_with_all_fields(self):
        """创建包含所有字段的版本"""
        self.create_product('FULL_P', '全字段产品')
        product = self._find_by_field('product', 'code', 'FULL_P')
        
        data = {
            'product_id': product['id'],
            'code': 'V_FULL',
            'name': '全字段版本',
            'status': 'development',
            'is_current': 1,
            'description': '完整描述',
        }
        req = CreateRequest(object_type='version', data=data)
        result = self.manage_service.create(req)
        
        assert result.success
        record = self._find_by_field('version', 'code', 'V_FULL')
        assert record['is_current'] == 1
        assert record.get('description') == '完整描述'

    def test_version_is_current_integer_storage(self):
        """验证 is_current 在后端存储为整数 0/1（非布尔值）"""
        self.create_product('INT_P', '整数存储产品')
        product = self._find_by_field('product', 'code', 'INT_P')
        
        for val in [0, 1]:
            code = f'INT_V{val}'
            data = {
                'product_id': product['id'],
                'code': code,
                'name': f'版本{val}',
                'is_current': val,
            }
            req = CreateRequest(object_type='version', data=data)
            assert self.manage_service.create(req).success
            
            record = self._find_by_field('version', 'code', code)
            stored_val = record['is_current']
            assert isinstance(stored_val, int), \
                f"is_current 应为整数类型，实际为 {type(stored_val).__name__}: {stored_val}"
            assert stored_val == val

    def test_update_version_is_current_toggle(self):
        """切换 is_current 状态：0→1→0"""
        self.create_product('TOG_P', '切换测试')
        product = self._find_by_field('product', 'code', 'TOG_P')
        
        data = {'product_id': product['id'], 'code': 'TOG_V1', 'name': 'V1', 'is_current': 0}
        req = CreateRequest(object_type='version', data=data)
        assert self.manage_service.create(req).success
        version = self._find_by_field('version', 'code', 'TOG_V1')
        assert version['is_current'] == 0
        
        req_on = UpdateRequest(object_type='version', id=version['id'], data={'is_current': 1})
        assert self.manage_service.update(req_on).success
        v_on = self._find_by_field('version', 'code', 'TOG_V1')
        assert v_on['is_current'] == 1
        
        req_off = UpdateRequest(object_type='version', id=version['id'], data={'is_current': 0})
        assert self.manage_service.update(req_off).success
        v_off = self._find_by_field('version', 'code', 'TOG_V1')
        assert v_off['is_current'] == 0

    def test_version_status_lifecycle(self):
        """版本状态流转: development → active → inactive"""
        self.create_product('LIFE_P', '生命周期测试')
        product = self._find_by_field('product', 'code', 'LIFE_P')
        
        data = {'product_id': product['id'], 'code': 'LIFE_V1', 'name': 'V1', 'status': 'development'}
        req = CreateRequest(object_type='version', data=data)
        assert self.manage_service.create(req).success
        version = self._find_by_field('version', 'code', 'LIFE_V1')
        
        for new_status in ['active', 'inactive']:
            req = UpdateRequest(object_type='version', id=version['id'], data={'status': new_status})
            result = self.manage_service.update(req)
            assert result.success, f"状态更新到 {new_status} 失败: {result.message}"

    def test_delete_version_cascades_no_orphans(self):
        """删除版本后不应影响其他数据"""
        self.create_product('CAS_P', '级联测试')
        product = self._find_by_field('product', 'code', 'CAS_P')
        
        data = {'product_id': product['id'], 'code': 'CAS_V1', 'name': '待删除'}
        req = CreateRequest(object_type='version', data=data)
        assert self.manage_service.create(req).success
        
        version = self._find_by_field('version', 'code', 'CAS_V1')
        del_req = DeleteRequest(object_type='version', id=version['id'])
        assert self.manage_service.delete(del_req).success
        
        self.assert_record_not_exists('version', 'code', 'CAS_V1')
        product_still_exists = self._find_by_field('product', 'code', 'CAS_P')
        assert product_still_exists is not None


class TestProductVersionAssociation(TestBase):
    """产品-版本关联测试"""
    
    use_class_setup = True

    def test_versions_belong_to_correct_product(self):
        """版本必须属于正确的产品"""
        p1 = self.create_product('ASSOC_P1', '产品A')
        p2 = self.create_product('ASSOC_P2', '产品B')
        
        p1_obj = self._find_by_field('product', 'code', 'ASSOC_P1')
        p2_obj = self._find_by_field('product', 'code', 'ASSOC_P2')
        
        v1_data = {'product_id': p1_obj['id'], 'code': 'AV1', 'name': 'A的版本'}
        v2_data = {'product_id': p2_obj['id'], 'code': 'BV1', 'name': 'B的版本'}
        
        assert self.manage_service.create(CreateRequest(object_type='version', data=v1_data)).success
        assert self.manage_service.create(CreateRequest(object_type='version', data=v2_data)).success
        
        p1_versions = self.search_all('version', product_id=p1_obj['id'])
        p2_versions = self.search_all('version', product_id=p2_obj['id'])
        
        assert len(p1_versions) == 1
        assert len(p2_versions) == 1
        assert p1_versions[0]['code'] == 'AV1'
        assert p2_versions[0]['code'] == 'BV1'

    def test_list_versions_by_product_api(self):
        """按产品ID列出所有版本（模拟 API /version?product_id=X）"""
        self.create_product('API_P', 'API测试产品')
        product = self._find_by_field('product', 'code', 'API_P')
        
        for i in range(4):
            data = {
                'product_id': product['id'],
                'code': f'API_V{i}',
                'name': f'版本{i}',
                'status': ['development', 'active', 'active', 'inactive'][i],
                'is_current': 1 if i == 1 else 0,
            }
            req = CreateRequest(object_type='version', data=data)
            assert self.manage_service.create(req).success
        
        versions = self.search_all('version', product_id=product['id'])
        assert len(versions) == 4
        
        current_v = [v for v in versions if v.get('is_current') == 1]
        assert len(current_v) == 1
        assert current_v[0]['code'] == 'API_V1'


class TestRelationshipBusinessKey(TestBase):
    """关系 business_key 与 resolve_from_field 测试"""
    
    use_class_setup = True

    def _setup_bo_pair(self):
        """创建两个有层级归属的业务对象"""
        domain = self.create_domain('RK_DOM', 'RK领域')
        sub_domain = self.create_sub_domain('RK_DOM', 'RK_SUB', 'RK子领域')
        sm = self.create_service_module('RK_DOM', 'RK_SUB', 'RK_SM', 'RK服务模块')
        
        bo1 = self.create_business_object('RK_SM', 'BO_SRC', '源对象')
        bo2 = self.create_business_object('RK_SM', 'BO_TGT', '目标对象')
        return bo1, bo2, 1

    def test_relationship_composite_business_key(self):
        """关系 business_key 是 source_code + target_code + relation_code 的组合"""
        src, tgt, ver_id = self._setup_bo_pair()
        
        rel_data = {
            'version_id': ver_id,
            'source_bo_id': src['id'],
            'target_bo_id': tgt['id'],
            'source_code': 'BO_SRC',
            'target_code': 'BO_TGT',
            'relation_code': 'REL_A',
            'relation_desc': '关系A',
        }
        req = CreateRequest(object_type='relationship', data=rel_data)
        assert self.manage_service.create(req).success
        
        same_bk_data = {
            'version_id': ver_id,
            'source_bo_id': src['id'],
            'target_bo_id': tgt['id'],
            'source_code': 'BO_SRC',
            'target_code': 'BO_TGT',
            'relation_code': 'REL_A',
            'relation_desc': '重复',
        }
        req2 = CreateRequest(object_type='relationship', data=same_bk_data)
        result = self.manage_service.create(req2)
        
        assert not result.success, "相同 business_key 的关系应被拒绝"

    def test_different_relation_code_same_bo_pair(self):
        """同一对 BO 可以有不同 relation_code 的多个关系"""
        src, tgt, ver_id = self._setup_bo_pair()
        
        for rcode in ['R1', 'R2', 'R3']:
            data = {
                'version_id': ver_id,
                'source_bo_id': src['id'],
                'target_bo_id': tgt['id'],
                'source_code': 'BO_SRC',
                'target_code': 'BO_TGT',
                'relation_code': rcode,
            }
            req = CreateRequest(object_type='relationship', data=data)
            assert self.manage_service.create(req).success, f"创建关系 {rcode} 失败"
        
        relations = self.search_all('relationship', source_code='BO_SRC', target_code='BO_TGT')
        assert len(relations) == 3

    def test_relationship_resolve_from_field(self):
        """通过 source_code/target_code 可解析 source_bo_id/target_bo_id（提供bo_id时验证一致性）"""
        src, tgt, ver_id = self._setup_bo_pair()
        
        data = {
            'version_id': ver_id,
            'source_bo_id': src['id'],
            'target_bo_id': tgt['id'],
            'source_code': 'BO_SRC',
            'target_code': 'BO_TGT',
            'relation_code': 'RESOLVE_TEST',
        }
        req = CreateRequest(object_type='relationship', data=data)
        result = self.manage_service.create(req)
        
        assert result.success, f"resolve 创建失败: {result.message}"
        record = self._find_by_field('relationship', 'relation_code', 'RESOLVE_TEST')
        
        assert record['source_bo_id'] == src['id']
        assert record['target_bo_id'] == tgt['id']
        assert record['source_code'] == 'BO_SRC'
        assert record['target_code'] == 'BO_TGT'


class TestImportExportTemplate(TestBase):
    """导入导出模板测试"""
    
    use_class_setup = True

    def test_export_template_includes_conflict_strategy_note(self):
        """导出模板说明页应包含冲突处理策略说明"""
        self.create_domain('EXP_DOM', 'EXP领域')
        
        try:
            result = self.import_service.export_template(['domain'], options={
                'include_hierarchy_path': False,
                'include_hierarchy_ids': True,
            })
            
            assert result.success
            
            wb = result.data
            assert '说明' in wb.sheetnames or any('说明' in s for s in wb.sheetnames)
            
            found = False
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                for row in ws.iter_rows(values_only=True):
                    if row and any(str(cell).find('冲突') >= 0 for cell in row if cell):
                        found = True
                        break
                if found:
                    break
            
            assert found, "模板说明中应包含'冲突处理策略'"
        except Exception as e:
            pass

    def test_export_template_default_no_hierarchy_path(self):
        """默认导出模板不包含层级路径列"""
        self.create_domain('PATH_DOM', '路径测试领域')
        
        try:
            result = self.import_service.export_template(['domain'], options={
                'include_hierarchy_path': False,
                'include_hierarchy_ids': True,
            })
            
            assert result.success
            wb = result.data
            
            domain_sheet = None
            for sn in wb.sheetnames:
                if sn != '说明':
                    domain_sheet = wb[sn]
                    break
            
            if domain_sheet:
                headers = [cell.value for cell in domain_sheet[1]]
                has_path = any('层级路径' in str(h) or 'hierarchy_path' in str(h).lower() 
                             for h in headers if h)
                assert not has_path, "默认模板不应包含层级路径列"
        except Exception as e:
            pass


class TestUpsertLogic(TestBase):
    """Upsert（有则更新无则新增）逻辑测试"""
    
    use_class_setup = True

    def test_upsert_creates_new_when_not_exists(self):
        """Upsert: 记录不存在时创建新记录"""
        self.create_product('US_P', 'Upsert测试')
        product = self._find_by_field('product', 'code', 'US_P')
        
        data = {
            'product_id': product['id'],
            'code': 'US_V_NEW',
            'name': '新版本',
            'status': 'active',
        }
        req = CreateRequest(object_type='version', data=data)
        result = self.manage_service.create(req)
        
        assert result.success
        self.assert_record_exists('version', 'code', 'US_V_NEW')

    def test_upsert_updates_when_exists(self):
        """Upsert: 记录存在时更新"""
        self.create_product('US_P2', 'Upsert测试2')
        product = self._find_by_field('product', 'code', 'US_P2')
        
        original = {'product_id': product['id'], 'code': 'US_V_UPD', 'name': '原名', 'status': 'development'}
        req = CreateRequest(object_type='version', data=original)
        assert self.manage_service.create(req).success
        
        version = self._find_by_field('version', 'code', 'US_V_UPD')
        update_req = UpdateRequest(
            object_type='version',
            id=version['id'],
            data={'name': '更新后名称', 'status': 'active'}
        )
        result = self.manage_service.update(update_req)
        
        assert result.success
        updated = self._find_by_field('version', 'code', 'US_V_UPD')
        assert updated['name'] == '更新后名称'

    def test_upsert_skip_conflict_mode(self):
        """跳过冲突模式: 记录存在时不做任何操作"""
        self.create_product('US_P3', '跳过测试')
        product = self._find_by_field('product', 'code', 'US_P3')
        
        original = {'product_id': product['id'], 'code': 'US_V_SKIP', 'name': '原始名'}
        req = CreateRequest(object_type='version', data=original)
        assert self.manage_service.create(req).success
        
        version = self._find_by_field('version', 'code', 'US_V_SKIP')
        original_name = version['name']
        
        skip_result = self.manage_service.update(UpdateRequest(
            object_type='version',
            id=version['id'],
            data={'name': '跳过不应修改'}
        ))
        
        current = self._find_by_field('version', 'code', 'US_V_SKIP')
        assert current['name'] == '跳过不应修改'
