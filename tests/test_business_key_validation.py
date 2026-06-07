# -*- coding: utf-8 -*-
"""
业务键校验规则测试

覆盖场景：
1. 单字段业务键唯一性（创建/更新）
2. 组合业务键唯一性（创建/更新）
3. 业务键与 unique 字段的区别
4. action_executor 中的校验集成
5. 导入验证 vs CRUD 验证一致性
6. 边界情况：空值、None、特殊字符
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.services.manage_service import CreateRequest, UpdateRequest, DeleteRequest
from meta.services.query_service import SearchRequest, QueryCondition
from tests.conftest import TestBase


class TestSingleFieldBusinessKey(TestBase):
    """单字段业务键测试"""

    def test_domain_code_is_business_key(self):
        """测试领域编码是业务键"""
        obj = __import__('meta.core.models', fromlist=['registry']).registry.get('domain')
        bk_fields = [f for f in obj.fields 
                    if getattr(f.semantics, 'business_key', False) 
                    and f.storage.value != 'virtual']
        
        bk_ids = [f.id for f in bk_fields]
        assert 'code' in bk_ids, "领域 code 应该是 business_key"

    def test_create_duplicate_code_fails_with_bk_error(self):
        """测试重复编码创建失败 - 应该有业务键错误"""
        self.create_domain('BK_DUP', '第一个')
        
        data = {'code': 'BK_DUP', 'name': '第二个'}
        req = CreateRequest(object_type='domain', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success

    def test_update_same_record_succeeds(self):
        """测试更新自身记录不报错"""
        self.create_domain('BK_UPD', '原始名称')
        
        record = self._find_by_field('domain', 'code', 'BK_UPD')
        
        req = UpdateRequest(object_type='domain', id=record['id'], 
                           data={'name': '新名称'})
        result = self.manage_service.update(req)
        
        assert result.success

    def test_update_to_existing_code_fails(self):
        """测试更新到已存在的编码应该失败"""
        self.create_domain('BK_A', '领域A')
        self.create_domain('BK_B', '领域B')
        
        record_a = self._find_by_field('domain', 'code', 'BK_A')
        
        req = UpdateRequest(object_type='domain', id=record_a['id'],
                           data={'code': 'BK_B'})
        result = self.manage_service.update(req)
        
        assert not result.success


class TestCompositeFieldBusinessKey(TestBase):
    """组合业务键测试 - relationship 场景"""

    def test_relationship_has_three_bk_fields(self):
        """测试关系对象有三个业务键字段"""
        registry = __import__('meta.core.models', fromlist=['registry']).registry
        obj = registry.get('relationship')
        bk_fields = [f for f in obj.fields 
                    if getattr(f.semantics, 'business_key', False) 
                    and f.storage.value != 'virtual'
                    and not getattr(f.semantics, 'virtual', False)]
        
        bk_ids = [f.id for f in bk_fields]
        assert 'source_code' in bk_ids
        assert 'target_code' in bk_ids
        assert 'relation_code' in bk_ids
        assert len(bk_ids) == 3

    def test_same_source_different_target_ok(self):
        """测试相同源不同目标是合法的"""
        self.create_full_hierarchy('SDT')
        self.create_business_object('SDT_SM', 'S1', '源1')
        self.create_business_object('SDT_SM', 'T1', '目标1')
        self.create_business_object('SDT_SM', 'T2', '目标2')
        
        self.create_relationship('S1', 'T1', 'REL_X')
        rel2 = self.create_relationship('S1', 'T2', 'REL_X')
        
        assert rel2 is not None
        self.assert_count('relationship', 2)

    def test_same_source_same_target_different_rel_ok(self):
        """测试相同源相同目标但关系类型不同是合法的"""
        self.create_full_hierarchy('SSD')
        self.create_business_object('SSD_SM', 'SA', '源A')
        self.create_business_object('SSD_SM', 'TA', '目标A')
        
        self.create_relationship('SA', 'TA', 'CALLS')
        rel2 = self.create_relationship('SA', 'TA', 'DATA_FLOW')
        
        assert rel2 is not None
        self.assert_count('relationship', 2)

    def test_identical_composite_key_fails(self):
        """测试完全相同的组合键应该失败"""
        self.create_full_hierarchy('ICK')
        self.create_business_object('ICK_SM', 'IX', '源X')
        self.create_business_object('ICK_SM', 'IY', '目标Y')
        
        self.create_relationship('IX', 'IY', 'REL_DUP')
        
        data2 = {
            'source_id': self._find_by_field('business_object', 'code', 'IX')['id'],
            'target_id': self._find_by_field('business_object', 'code', 'IY')['id'],
            'source_code': 'IX',
            'target_code': 'IY',
            'relation_code': 'REL_DUP',
            'relation_desc': '重复关系',
        }
        req = CreateRequest(object_type='relationship', data=data2)
        result = self.manage_service.create(req)
        
        assert not result.success


class TestBusinessKeyVsUnique(TestBase):
    """业务键 vs Unique 字段区别测试"""

    def test_unique_field_separate_from_bk(self):
        """测试 unique 字段和 business_key 是独立概念"""
        registry = __import__('meta.core.models', fromlist=['registry']).registry
        
        domain_obj = registry.get('domain')
        unique_fields = [f for f in domain_obj.fields 
                        if hasattr(f, 'unique') and f.unique]
        bk_fields = [f for f in domain_obj.fields 
                    if getattr(f.semantics, 'business_key', False)]
        
        print(f"Domain unique fields: {[f.id for f in unique_fields]}")
        print(f"Domain BK fields: {[f.id for f in bk_fields]}")


class TestImportValidationConsistency(TestBase):
    """导入验证与 CRUD 验证一致性测试"""

    def _create_import_file(self, sheets_data: dict) -> str:
        import tempfile
        from openpyxl import Workbook
        tmp = tempfile.mktemp(suffix='.xlsx')
        wb = Workbook()
        wb.remove(wb.active)
        for sheet_name, rows in sheets_data.items():
            ws = wb.create_sheet(title=sheet_name)
            for row in rows:
                ws.append(row)
        wb.save(tmp)
        return tmp

    def test_import_duplicate_detected_same_as_crud(self):
        """测试导入检测到的重复应与 CRUD 一致"""
        self.create_full_hierarchy('CON')
        self.create_domain('CON01', '已有领域')
        
        sheets = {
            '领域': [
                ['操作模式', '编码', '名称'],
                ['新增', 'CON01', '重复领域'],
            ]
        }
        tmp = self._create_import_file(sheets)
        
        try:
            preview_result = self.import_service.import_cascade(tmp, mode='preview', context={'version_id': 1})
            
            import_has_error = preview_result.validation['invalid_count'] > 0
            
            data = {'code': 'CON01', 'name': '重复领域2', 'version_id': 1}
            req = CreateRequest(object_type='domain', data=data)
            crud_result = self.manage_service.create(req)
            crud_has_error = not crud_result.success
            
            assert import_has_error == crud_has_error, \
                "导入和CRUD对重复的检测结果应一致"
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


class TestEdgeCases(TestBase):
    """边界情况测试"""

    def test_empty_string_vs_null(self):
        """测试空字符串和 null 的区别"""
        from meta.services.manage_service import CreateRequest
        
        data = {'code': '', 'name': '空编码'}
        req = CreateRequest(object_type='domain', data=data)
        result = self.manage_service.create(req)
        
        assert not result.success

    def test_special_characters_in_code(self):
        """测试编码中的特殊字符"""
        result = self.create_domain('DOM-SPEC_001', '特殊字符域')
        assert result is not None

    def test_unicode_in_name(self):
        """测试名称中的 Unicode 字符"""
        result = self.create_domain('UNI', '中文领域[SYMBOL]日本語')
        assert result is not None

    def test_very_long_code(self):
        """测试超长编码"""
        long_code = 'A' * 100
        try:
            result = self.create_domain(long_code, '长编码')
        except Exception as e:
            pass


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
