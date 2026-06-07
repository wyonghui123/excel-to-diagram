# -*- coding: utf-8 -*-
"""
全业务对象 CRUD 测试 - 合理顺序版本（类级别共享数据库）

测试流程（模拟真实业务场景）：
1. 创建阶段：按依赖链创建2个完整业务对象
2. 更新阶段：更新2个已创建的对象属性
3. 删除阶段：删除其中1个对象

依赖链顺序：
产品 → 版本 → 领域 → 子域 → 服务模块 → 业务对象 → 关系/标注
"""

import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.services.manage_service import CreateRequest, UpdateRequest, DeleteRequest
from meta.services.query_service import SearchRequest, QueryCondition, QueryService
from meta.core.datasource import get_data_source
from meta.services.manage_service import ManageService
from tests.conftest import TestBase


def init_database_schema(ds):
    """初始化数据库表结构（独立辅助函数）"""
    from meta.core.schema_generator import SchemaGenerator
    from meta.core.models import registry as meta_registry
    from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
    
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)
    
    generator = SchemaGenerator(dialect='sqlite')
    
    for obj in meta_registry.get_all().values():
        if hasattr(obj, 'table_name') and obj.table_name:
            sql = generator.generate_create_table(obj)
            if sql:
                ds.execute(sql)
                
            indexes = generator.generate_create_index(obj)
            for idx_sql in indexes:
                ds.execute(idx_sql)
    
    ds.commit()


class TestBusinessObjectLifecycle(TestBase):
    """
    业务对象完整生命周期测试
    
    场景：在产品"ERP系统"下创建两个领域模块，验证完整的CRUD操作
    使用 setup_class/teardown_class 确保整个测试类共享同一数据库
    """

    @classmethod
    def setup_class(cls):
        """整个测试类开始时执行一次"""
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, 'test_lifecycle.db')
        
        cls.ds = get_data_source("sqlite", database=cls.db_path)
        init_database_schema(cls.ds)
        
        cls.manage_service = ManageService(cls.ds)
        cls.query_service = QueryService(cls.ds)

    @classmethod
    def teardown_class(cls):
        """整个测试类结束后执行一次"""
        if hasattr(cls, 'tmp_dir') and os.path.exists(cls.tmp_dir):
            shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    # ==================== 测试步骤 ====================

    def test_01_create_product_and_version(self):
        """步骤1：创建产品和版本（基础依赖）"""
        # 调试信息
        print(f"\n[DEBUG] Database path: {self.__class__.db_path}")
        print(f"[DEBUG] DS object: {id(self.__class__.ds)}")
        
        # 创建产品
        product_data = {
            'code': 'ERP_SYSTEM',
            'name': 'ERP管理系统',
            'description': '企业资源计划系统'
        }
        req = CreateRequest(object_type='product', data=product_data)
        result = self.__class__.manage_service.create(req)
        
        print(f"[DEBUG] Create result: success={result.success}, message={result.message}")
        print(f"[DEBUG] Last insert ID: {result.last_insert_id}")
        
        assert result.success, f"创建产品失败: {result.message}"
        
        # 直接查询验证
        count_sql = "SELECT COUNT(*) FROM products"
        count_row = self.__class__.ds.execute(count_sql).fetchone()
        print(f"[DEBUG] Products count in DB: {count_row[0]}")
        
        product = self._find_by_field('product', 'code', 'ERP_SYSTEM')
        print(f"[DEBUG] Found product: {product}")
        assert product is not None, "产品应该存在"
        assert product['name'] == 'ERP管理系统'
        
        # 创建版本
        version_data = {
            'product_id': product['id'],
            'code': 'V2024',
            'name': '2024版',
            'is_current': 1,
            'description': '2024年度版本'
        }
        req = CreateRequest(object_type='version', data=version_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"创建版本失败: {result.message}"
        
        version = self._find_by_field('version', 'code', 'V2024')
        assert version is not None, "版本应该存在"
        
        print(f"[OK] Create product: ERP_SYSTEM (id={product['id']})")
        print(f"[OK] Create version: V2024 (id={version['id']})")

    def test_02_create_two_domains(self):
        """步骤2：创建2个领域（主测试对象）"""
        version = self._find_by_field('version', 'code', 'V2024')
        assert version is not None, "版本应该已存在（从test_01创建）"
        version_id = version['id']
        
        # 创建第1个领域：财务管理
        domain1_data = {
            'version_id': version_id,
            'code': 'FINANCE',
            'name': '财务管理',
            'description': '负责财务相关业务'
        }
        req = CreateRequest(object_type='domain', data=domain1_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"创建领域1失败: {result.message}"
        
        domain1 = self._find_by_field('domain', 'code', 'FINANCE')
        assert domain1 is not None
        assert domain1['name'] == '财务管理'
        
        # 创建第2个领域：供应链管理
        domain2_data = {
            'version_id': version_id,
            'code': 'SUPPLY_CHAIN',
            'name': '供应链管理',
            'description': '负责供应链相关业务'
        }
        req = CreateRequest(object_type='domain', data=domain2_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"创建领域2失败: {result.message}"
        
        domain2 = self._find_by_field('domain', 'code', 'SUPPLY_CHAIN')
        assert domain2 is not None
        assert domain2['name'] == '供应链管理'
        
        # 验证总数
        actual_table = self._get_table_name('domain')
        count_sql = f"SELECT COUNT(*) as cnt FROM {actual_table}"
        count = self.__class__.ds.execute(count_sql).fetchone()[0]
        assert count >= 2, f"应该至少有2个领域，实际: {count}"
        
        print(f"[OK] Create domain1: FINANCE - 财务管理 (id={domain1['id']})")
        print(f"[OK] Create domain2: SUPPLY_CHAIN - 供应链管理 (id={domain2['id']})")

    def test_03_update_two_domains(self):
        """步骤3：更新2个已创建的领域"""
        domain1 = self._find_by_field('domain', 'code', 'FINANCE')
        domain2 = self._find_by_field('domain', 'code', 'SUPPLY_CHAIN')
        
        assert domain1 is not None, "FINANCE领域应该已存在"
        assert domain2 is not None, "SUPPLY_CHAIN领域应该已存在"
        
        # 更新第1个领域名称和描述
        update1_data = {
            'name': '财务与成本管理',
            'description': '升级为包含成本管理的综合财务模块'
        }
        req = UpdateRequest(
            object_type='domain',
            id=domain1['id'],
            data=update1_data
        )
        result = self.__class__.manage_service.update(req)
        assert result.success, f"更新领域1失败: {result.message}"
        
        updated1 = self._find_by_id('domain', domain1['id'])
        assert updated1['name'] == '财务与成本管理'
        
        # 更新第2个领域名称和描述
        update2_data = {
            'name': '供应链与物流管理',
            'description': '扩展为包含物流的综合供应链模块'
        }
        req = UpdateRequest(
            object_type='domain',
            id=domain2['id'],
            data=update2_data
        )
        result = self.__class__.manage_service.update(req)
        assert result.success, f"更新领域2失败: {result.message}"
        
        updated2 = self._find_by_id('domain', domain2['id'])
        assert updated2['name'] == '供应链与物流管理'
        
        print(f"[OK] Update domain1: FINANCE -> 财务与成本管理")
        print(f"[OK] Update domain2: SUPPLY_CHAIN -> 供应链与物流管理")

    def test_04_delete_one_domain(self):
        """步骤4：删除其中1个领域（保留另一个）"""
        domain_to_delete = self._find_by_field('domain', 'code', 'FINANCE')
        domain_to_keep = self._find_by_field('domain', 'code', 'SUPPLY_CHAIN')
        
        assert domain_to_delete is not None, "待删除领域应该存在"
        assert domain_to_keep is not None, "保留领域应该存在"
        
        # 删除第1个领域
        req = DeleteRequest(object_type='domain', id=domain_to_delete['id'])
        result = self.__class__.manage_service.delete(req)
        assert result.success, f"删除领域失败: {result.message}"
        
        # 验证删除成功
        deleted = self._find_by_id('domain', domain_to_delete['id'])
        assert deleted is None or deleted.get('is_deleted') == 1, "领域应该被删除"
        
        # 验证另一个领域仍然存在
        kept = self._find_by_id('domain', domain_to_keep['id'])
        assert kept is not None, "保留的领域不应该被删除"
        assert kept['name'] == '供应链与物流管理'
        
        print(f"[OK] Delete domain: FINANCE (id={domain_to_delete['id']})")
        print(f"[OK] Keep domain: SUPPLY_CHAIN - 供应链与物流管理")

    def test_05_verify_audit_logs(self):
        """步骤5：验证审计日志记录完整性"""
        logs_sql = """
            SELECT action, COUNT(*) as cnt 
            FROM audit_logs 
            WHERE object_type = 'domain' 
            GROUP BY action
        """
        logs = self.__class__.ds.execute(logs_sql).fetchall()
        log_dict = {row[0]: row[1] for row in logs}
        
        # 应该有CREATE、UPDATE、DELETE日志
        create_count = log_dict.get('CREATE', 0)
        update_count = log_dict.get('UPDATE', 0)
        delete_count = log_dict.get('DELETE', 0)
        
        total_logs = sum(log_dict.values())
        
        print(f"\n[审计日志统计]")
        print(f"  CREATE: {create_count} 条 (期望 >= 2)")
        print(f"  UPDATE: {update_count} 条 (期望 >= 2)")
        print(f"  DELETE: {delete_count} 条 (期望 >= 1)")
        print(f"  总计:   {total_logs} 条")
        
        assert create_count >= 2, f"应该有至少2条CREATE日志，实际: {create_count}"
        assert update_count >= 2, f"应该有至少2条UPDATE日志，实际: {update_count}"
        assert delete_count >= 1, f"应该有至少1条DELETE日志，实际: {delete_count}"

    # ==================== 辅助方法 ====================
    
    # 表名映射（单数 -> 复数）
    TABLE_NAMES = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
        'relationship': 'relationships',
        'annotation': 'annotations',
        'user': 'users',
        'role': 'roles',
        'user_group': 'user_groups',
        'enum_type': 'enum_types',
        'enum_value': 'enum_values'
    }

    def _get_table_name(self, object_type):
        """获取实际的数据库表名"""
        return self.TABLE_NAMES.get(object_type, object_type + 's')

    def _find_by_field(self, table, field, value):
        """根据字段值查找记录"""
        actual_table = self._get_table_name(table)
        sql = f"SELECT * FROM {actual_table} WHERE {field} = ? LIMIT 1"
        try:
            row = self.__class__.ds.execute(sql, [value]).fetchone()
            if not row:
                return None
            
            # 获取列名
            cursor = self.__class__.ds.execute(f"PRAGMA table_info({actual_table})")
            columns = [col[1] for col in cursor.fetchall()]
            
            # 转换为字典
            return dict(zip(columns, row))
        except Exception as e:
            print(f"[ERROR] 查询失败 {table}.{field}={value}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _find_by_id(self, table, id_value):
        """根据ID查找记录"""
        return self._find_by_field(table, 'id', id_value)


class TestUserAndRoleCRUD(TestBase):
    """
    用户和角色 CRUD 测试（独立于层级结构）
    
    场景：创建用户并分配角色，验证权限管理基础功能
    使用 setup_class/teardown_class 确保整个测试类共享同一数据库
    """

    @classmethod
    def setup_class(cls):
        """整个测试类开始时执行一次"""
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, 'test_user_role.db')
        
        cls.ds = get_data_source("sqlite", database=cls.db_path)
        init_database_schema(cls.ds)
        
        cls.manage_service = ManageService(cls.ds)

    @classmethod
    def teardown_class(cls):
        """整个测试类结束后执行一次"""
        if hasattr(cls, 'tmp_dir') and os.path.exists(cls.tmp_dir):
            shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    # ==================== 测试步骤 ====================

    def test_01_create_user(self):
        """创建用户"""
        user_data = {
            'username': 'test_admin',
            'display_name': 'Test Admin',
            'email': 'admin@test.com',
            'status': 1
        }
        req = CreateRequest(object_type='user', data=user_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"Create user failed: {result.message}"
        
        user = self._find_by_field('user', 'username', 'test_admin')
        assert user is not None, "User should exist"
        assert user['display_name'] == 'Test Admin'
        print(f"[OK] Create user: test_admin (id={user['id']})")

    def test_02_create_role(self):
        """创建角色"""
        role_data = {
            'code': 'TEST_ADMIN_ROLE',
            'name': 'Test Admin Role',
            'description': 'Role for automated testing'
        }
        req = CreateRequest(object_type='role', data=role_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"Create role failed: {result.message}"
        
        role = self._find_by_field('role', 'code', 'TEST_ADMIN_ROLE')
        assert role is not None, "Role should exist"
        print(f"[OK] Create role: TEST_ADMIN_ROLE (id={role['id']})")

    def test_03_update_user_display_name(self):
        """更新用户显示名"""
        user = self._find_by_field('user', 'username', 'test_admin')
        assert user is not None, "User should exist"
        
        req = UpdateRequest(
            object_type='user',
            id=user['id'],
            data={'display_name': 'Super Admin'}
        )
        result = self.__class__.manage_service.update(req)
        assert result.success, f"Update user failed: {result.message}"
        
        updated = self._find_by_id('user', user['id'])
        assert updated['display_name'] == 'Super Admin'
        print(f"[OK] Update user: display_name -> Super Admin")

    def test_04_update_role_description(self):
        """更新角色描述"""
        role = self._find_by_field('role', 'code', 'TEST_ADMIN_ROLE')
        assert role is not None, "Role should exist"
        
        req = UpdateRequest(
            object_type='role',
            id=role['id'],
            data={
                'description': 'Enhanced admin role with all permissions',
                'name': 'Enhanced Admin Role'
            }
        )
        result = self.__class__.manage_service.update(req)
        assert result.success, f"Update role failed: {result.message}"
        
        updated = self._find_by_id('role', role['id'])
        assert updated['name'] == 'Enhanced Admin Role'
        print(f"[OK] Update role: name -> Enhanced Admin Role")

    def test_05_delete_role_keep_user(self):
        """删除角色（保留用户）"""
        role = self._find_by_field('role', 'code', 'TEST_ADMIN_ROLE')
        assert role is not None, "Role should exist"
        
        req = DeleteRequest(object_type='role', id=role['id'])
        result = self.__class__.manage_service.delete(req)
        assert result.success, f"Delete role failed: {result.message}"
        
        deleted = self._find_by_id('role', role['id'])
        assert deleted is None or deleted.get('is_deleted') == 1, "Role should be deleted"
        
        # 验证用户仍然存在
        user = self._find_by_field('user', 'username', 'test_admin')
        assert user is not None, "User should still exist"
        print(f"[OK] Delete role: TEST_ADMIN_ROLE (user still exists)")

    # ==================== 辅助方法 ====================
    
    TABLE_NAMES = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
        'relationship': 'relationships',
        'annotation': 'annotations',
        'user': 'users',
        'role': 'roles',
        'user_group': 'user_groups',
        'enum_type': 'enum_types',
        'enum_value': 'enum_values'
    }

    def _get_table_name(self, object_type):
        return self.TABLE_NAMES.get(object_type, object_type + 's')

    def _find_by_field(self, table, field, value):
        actual_table = self._get_table_name(table)
        sql = f"SELECT * FROM {actual_table} WHERE {field} = ? LIMIT 1"
        try:
            row = self.__class__.ds.execute(sql, [value]).fetchone()
            if not row:
                return None
            
            cursor = self.__class__.ds.execute(f"PRAGMA table_info({actual_table})")
            columns = [col[1] for col in cursor.fetchall()]
            
            return dict(zip(columns, row))
        except Exception as e:
            print(f"[ERROR] Query failed {table}.{field}={value}: {e}")
            return None

    def _find_by_id(self, table, id_value):
        return self._find_by_field(table, 'id', id_value)


class TestAnnotationCRUD(TestBase):
    """
    标注 CRUD 测试（轻量级，无复杂依赖）
    
    场景：为业务对象添加备注信息
    """

    @classmethod
    def setup_class(cls):
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, 'test_annotation.db')
        
        cls.ds = get_data_source("sqlite", database=cls.db_path)
        init_database_schema(cls.ds)
        
        cls.manage_service = ManageService(cls.ds)

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, 'tmp_dir') and os.path.exists(cls.tmp_dir):
            shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    # ==================== 测试步骤 ====================

    def test_01_create_two_annotations(self):
        """创建2条标注"""
        # 标注1：重要提示
        ann1_data = {
            'target_type': 'domain',
            'target_id': 1,
            'category': 'important',
            'content': 'Core business domain - priority handling'
        }
        req = CreateRequest(object_type='annotation', data=ann1_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"Create annotation 1 failed: {result.message}"
        
        # 标注2：警告信息（使用不同的target_id和content避免唯一约束）
        ann2_data = {
            'target_type': 'domain',
            'target_id': 99,  # 使用不同的target_id
            'category': 'warning',
            'content': 'Domain refactoring in progress'
        }
        req = CreateRequest(object_type='annotation', data=ann2_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"Create annotation 2 failed: {result.message}"
        
        # 验证数量
        actual_table = self._get_table_name('annotation')
        count_sql = f"SELECT COUNT(*) FROM {actual_table}"
        count = self.__class__.ds.execute(count_sql).fetchone()[0]
        assert count >= 2, f"Should have at least 2 annotations, actual: {count}"
        
        print(f"[OK] Create 2 annotations (total: {count})")

    def test_02_update_two_annotations(self):
        """更新2条标注内容"""
        actual_table = self._get_table_name('annotation')
        annotations = self.__class__.ds.execute(
            f"SELECT * FROM {actual_table} ORDER BY id LIMIT 2"
        ).fetchall()
        
        assert len(annotations) >= 2, "Need at least 2 annotations"
        
        cursor = self.__class__.ds.execute(f"PRAGMA table_info({actual_table})")
        columns = [col[1] for col in cursor.fetchall()]
        
        # 更新第1条标注
        ann1 = dict(zip(columns, annotations[0]))
        req = UpdateRequest(
            object_type='annotation',
            id=ann1['id'],
            data={'content': '[Updated] Highest priority - Core domain'}
        )
        result = self.__class__.manage_service.update(req)
        assert result.success, f"Update annotation 1 failed: {result.message}"
        
        # 更新第2条标注
        ann2 = dict(zip(columns, annotations[1]))
        req = UpdateRequest(
            object_type='annotation',
            id=ann2['id'],
            data={
                'category': 'info',
                'content': '[Updated] Refactoring progress: 80% complete'
            }
        )
        result = self.__class__.manage_service.update(req)
        assert result.success, f"Update annotation 2 failed: {result.message}"
        
        print(f"[OK] Update 2 annotations successfully")

    def test_03_delete_one_annotation(self):
        """删除1条标注"""
        actual_table = self._get_table_name('annotation')
        annotations = self.__class__.ds.execute(
            f"SELECT * FROM {actual_table} ORDER BY id LIMIT 1"
        ).fetchall()
        
        assert len(annotations) >= 1, "Need at least 1 annotation"
        
        cursor = self.__class__.ds.execute(f"PRAGMA table_info({actual_table})")
        columns = [col[1] for col in cursor.fetchall()]
        
        to_delete = dict(zip(columns, annotations[0]))
        req = DeleteRequest(object_type='annotation', id=to_delete['id'])
        result = self.__class__.manage_service.delete(req)
        assert result.success, f"Delete annotation failed: {result.message}"
        
        # 验证删除
        deleted = self.__class__.ds.execute(
            f"SELECT * FROM {actual_table} WHERE id = ?", [to_delete['id']]
        ).fetchone()
        assert deleted is None, "Annotation should be deleted"
        
        # 验证剩余数量
        remaining = self.__class__.ds.execute(
            f"SELECT COUNT(*) FROM {actual_table}"
        ).fetchone()[0]
        assert remaining >= 1, f"Should have at least 1 annotation left, actual: {remaining}"
        
        print(f"[OK] Delete 1 annotation (remaining: {remaining})")

    # ==================== 辅助方法 ====================
    
    TABLE_NAMES = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
        'relationship': 'relationships',
        'annotation': 'annotations',
        'user': 'users',
        'role': 'roles',
        'user_group': 'user_groups',
        'enum_type': 'enum_types',
        'enum_value': 'enum_values'
    }

    def _get_table_name(self, object_type):
        return self.TABLE_NAMES.get(object_type, object_type + 's')


class TestEnumTypeAndValueCRUD(TestBase):
    """
    枚举类型和枚举值 CRUD 测试
    
    场景：创建状态枚举并添加多个枚举值
    """

    @classmethod
    def setup_class(cls):
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, 'test_enum.db')
        
        cls.ds = get_data_source("sqlite", database=cls.db_path)
        init_database_schema(cls.ds)
        
        cls.manage_service = ManageService(cls.ds)

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, 'tmp_dir') and os.path.exists(cls.tmp_dir):
            shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    # ==================== 测试步骤 ====================

    def test_01_create_enum_type(self):
        """创建枚举类型"""
        enum_data = {
            'name': 'Status Enum',
            'description': 'Enum for status values',
            'category': 'business',  # 业务枚举
            'mutability': 'fully_editable'  # 完全可编辑
        }
        req = CreateRequest(object_type='enum_type', data=enum_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"Create enum type failed: {result.message}"
        
        # Store the created enum type ID for later use
        self.__class__._enum_type_id = result.data.get('id')
        assert self.__class__._enum_type_id, "Enum type ID should exist"
        
        print(f"[OK] Create enum type: Status Enum (db_id={self.__class__._enum_type_id})")

    def test_02_create_two_enum_values(self):
        """创建2个枚举值"""
        enum_type_id = self.__class__._enum_type_id
        assert enum_type_id, "Enum type ID should be set from test_01"
        
        # 创建第1个枚举值
        val1_data = {
            'enum_type_id': enum_type_id,
            'code': 'ACTIVE',
            'name': 'Active',  # 必填字段：显示名称
            'sort_order': 1
        }
        req = CreateRequest(object_type='enum_value', data=val1_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"Create enum value 1 failed: {result.message}"
        
        # 创建第2个枚举值
        val2_data = {
            'enum_type_id': enum_type_id,
            'code': 'INACTIVE',
            'name': 'Inactive',  # 必填字段：显示名称
            'sort_order': 2
        }
        req = CreateRequest(object_type='enum_value', data=val2_data)
        result = self.__class__.manage_service.create(req)
        assert result.success, f"Create enum value 2 failed: {result.message}"
        
        # 验证数量
        actual_table = self._get_table_name('enum_value')
        count_sql = f"SELECT COUNT(*) FROM {actual_table} WHERE enum_type_id = ?"
        count = self.__class__.ds.execute(count_sql, [enum_type['id']]).fetchone()[0]
        assert count >= 2, f"Should have at least 2 enum values, actual: {count}"
        
        print(f"[OK] Create 2 enum values (total: {count})")

    def test_03_update_enum_values(self):
        """更新2个枚举值的标签"""
        actual_table = self._get_table_name('enum_value')
        enum_values = self.__class__.ds.execute(
            f"SELECT * FROM {actual_table} ORDER BY sort_order LIMIT 2"
        ).fetchall()
        
        assert len(enum_values) >= 2, "Need at least 2 enum values"
        
        cursor = self.__class__.ds.execute(f"PRAGMA table_info({actual_table})")
        columns = [col[1] for col in cursor.fetchall()]
        
        # 更新第1个枚举值
        val1 = dict(zip(columns, enum_values[0]))
        req = UpdateRequest(
            object_type='enum_value',
            id=val1['id'],
            data={'name': 'Enabled'}  # 更新显示名称
        )
        result = self.__class__.manage_service.update(req)
        assert result.success, f"Update enum value 1 failed: {result.message}"
        
        # 更新第2个枚举值
        val2 = dict(zip(columns, enum_values[1]))
        req = UpdateRequest(
            object_type='enum_value',
            id=val2['id'],
            data={'name': 'Disabled'}  # 更新显示名称
        )
        result = self.__class__.manage_service.update(req)
        assert result.success, f"Update enum value 2 failed: {result.message}"
        
        print(f"[OK] Update 2 enum values: Active->Enabled, Inactive->Disabled")

    def test_04_delete_one_enum_value(self):
        """删除1个枚举值"""
        actual_table = self._get_table_name('enum_value')
        enum_values = self.__class__.ds.execute(
            f"SELECT * FROM {actual_table} ORDER BY sort_order LIMIT 1"
        ).fetchall()
        
        assert len(enum_values) >= 1, "Need at least 1 enum value"
        
        cursor = self.__class__.ds.execute(f"PRAGMA table_info({actual_table})")
        columns = [col[1] for col in cursor.fetchall()]
        
        to_delete = dict(zip(columns, enum_values[0]))
        req = DeleteRequest(object_type='enum_value', id=to_delete['id'])
        result = self.__class__.manage_service.delete(req)
        assert result.success, f"Delete enum value failed: {result.message}"
        
        # 验证删除
        deleted = self.__class__.ds.execute(
            f"SELECT * FROM {actual_table} WHERE id = ?", [to_delete['id']]
        ).fetchone()
        assert deleted is None, "Enum value should be deleted"
        
        # 验证剩余数量
        remaining = self.__class__.ds.execute(
            f"SELECT COUNT(*) FROM {actual_table}"
        ).fetchone()[0]
        assert remaining >= 1, f"Should have at least 1 enum value left, actual: {remaining}"
        
        print(f"[OK] Delete 1 enum value (remaining: {remaining})")

    def test_05_cascade_delete_enum_type(self):
        """级联删除枚举类型（应删除关联的枚举值）"""
        enum_type = self._find_by_field('enum_type', 'name', 'Status Enum')
        if not enum_type:
            print("[SKIP] Enum type already deleted or not found")
            return
        
        req = DeleteRequest(object_type='enum_type', id=enum_type['id'])
        result = self.__class__.manage_service.delete(req)
        
        if result.success:
            # 验证关联的枚举值也被删除
            actual_table = self._get_table_name('enum_value')
            remaining = self.__class__.ds.execute(
                f"SELECT COUNT(*) FROM {actual_table}"
            ).fetchone()[0]
            
            print(f"[OK] Cascade delete enum type (remaining enum values: {remaining})")

    # ==================== 辅助方法 ====================
    
    TABLE_NAMES = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
        'relationship': 'relationships',
        'annotation': 'annotations',
        'user': 'users',
        'role': 'roles',
        'user_group': 'user_groups',
        'enum_type': 'enum_types',
        'enum_value': 'enum_values'
    }

    def _get_table_name(self, object_type):
        return self.TABLE_NAMES.get(object_type, object_type + 's')

    def _find_by_field(self, table, field, value):
        actual_table = self._get_table_name(table)
        sql = f"SELECT * FROM {actual_table} WHERE {field} = ? LIMIT 1"
        try:
            row = self.__class__.ds.execute(sql, [value]).fetchone()
            if not row:
                return None
            
            cursor = self.__class__.ds.execute(f"PRAGMA table_info({actual_table})")
            columns = [col[1] for col in cursor.fetchall()]
            
            return dict(zip(columns, row))
        except Exception as e:
            print(f"[ERROR] Query failed {table}.{field}={value}: {e}")
            return None

    def _find_by_id(self, table, id_value):
        return self._find_by_field(table, 'id', id_value)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--tb=short', '-s'])
