import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
服务层集成测试

测试 DeletionService 和 AssociationService 与数据库的交互
需要创建测试数据库和表结构
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class MockDataSource:
    """模拟数据源"""
    
    def __init__(self):
        self.data = {}
        self.transaction_active = False
    
    def execute(self, sql, params=None):
        """执行 SQL 并返回模拟结果"""
        params = params or []
        
        if "CREATE TABLE" in sql.upper():
            table_name = self._extract_table_name(sql)
            self.data[table_name] = []
            return MockCursor()
        
        if "INSERT INTO" in sql.upper():
            table_name = self._extract_table_name(sql)
            if table_name not in self.data:
                self.data[table_name] = []
            record = {}
            for i, param in enumerate(params):
                record[f"field_{i}"] = param
            self.data[table_name].append(record)
            return MockCursor()
        
        if "SELECT" in sql.upper() and "COUNT" in sql.upper():
            table_name = self._extract_select_table(sql)
            if table_name and table_name in self.data:
                count = len(self.data[table_name])
                return MockCursor([{"cnt": count}])
            return MockCursor([{"cnt": 0}])
        
        if "DELETE FROM" in sql.upper():
            table_name = self._extract_delete_table(sql)
            if table_name in self.data:
                self.data[table_name] = []
            return MockCursor()
        
        if "UPDATE" in sql.upper():
            return MockCursor()
        
        return MockCursor()
    
    def _extract_table_name(self, sql):
        """从 INSERT SQL 中提取表名"""
        parts = sql.upper().split()
        idx = parts.index("INTO") + 1
        return parts[idx].strip('`').strip('"')
    
    def _extract_select_table(self, sql):
        """从 SELECT SQL 中提取表名"""
        parts = sql.upper().split()
        if "FROM" in parts:
            idx = parts.index("FROM") + 1
            return parts[idx].split()[0].strip('`').strip('"').split('.')[-1]
        return None
    
    def _extract_delete_table(self, sql):
        """从 DELETE SQL 中提取表名"""
        parts = sql.upper().split()
        idx = parts.index("FROM") + 1
        return parts[idx].split()[0].strip('`').strip('"')
    
    def transaction(self):
        """返回事务上下文"""
        return TransactionContext(self)


class MockCursor:
    """模拟数据库游标"""
    
    def __init__(self, rows=None):
        self.rows = rows or []
        self._index = 0
    
    def fetchone(self):
        if self._index < len(self.rows):
            result = self.rows[self._index]
            self._index += 1
            return result
        return None
    
    def fetchall(self):
        return self.rows


class TransactionContext:
    """模拟事务上下文"""
    
    def __init__(self, ds):
        self.ds = ds
        self.committed = False
    
    def __enter__(self):
        self.ds.transaction_active = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ds.transaction_active = False
        self.committed = True
        return False


class TestDeletionService:
    """DeletionService 测试"""
    
    def test_get_table_name_default(self):
        """测试默认表名获取"""
        from meta.services.deletion_service import DeletionService
        
        mock_ds = MockDataSource()
        service = DeletionService(data_source=mock_ds, schema_registry=None)
        
        table_name = service.get_table_name("user")
        assert table_name == "users"
        print("[OK] get_table_name('user') = 'users'")
    
    def test_get_table_name_custom(self):
        """测试自定义表名"""
        from meta.services.deletion_service import DeletionService
        
        mock_registry = MockRegistry()
        service = DeletionService(data_source=None, schema_registry=mock_registry)
        
        table_name = service.get_table_name("user")
        assert table_name == "custom_users"
        print("[OK] custom table name works")


class MockRegistry:
    """模拟 Schema Registry"""
    
    def get(self, entity_type):
        obj = type('MockMetaObj', (), {'table_name': 'custom_users'})()
        return obj


class TestAssociationService:
    """AssociationService 测试"""
    
    def test_get_table_name(self):
        """测试获取表名"""
        from meta.services.association_service import AssociationService
        
        mock_ds = MockDataSource()
        service = AssociationService(mock_ds, None)
        
        table_name = service.get_table_name("user")
        assert table_name == "users"
        print("[OK] get_table_name('user') = 'users'")
    
    def test_association_definition_parse(self):
        """测试关联定义解析"""
        from meta.core.yaml_loader import AssociationDefinition
        
        assoc = AssociationDefinition(
            name="users",
            type="many_to_many",
            through="user_roles",
            source_key="role_id",
            target_entity="user",
            target_key="user_id"
        )
        
        assert assoc.type == "many_to_many"
        assert assoc.through == "user_roles"
        print("[OK] AssociationDefinition parse works")


def run_mock_tests():
    """运行模拟测试"""
    print("=" * 60)
    print("Service Layer Mock Tests")
    print("=" * 60)
    
    from meta.services.deletion_service import DeletionService
    from meta.services.association_service import AssociationService
    from meta.core.yaml_loader import AssociationDefinition
    
    # Test DeletionService
    print("\n--- DeletionService Tests ---")
    
    mock_ds = MockDataSource()
    service = DeletionService(data_source=mock_ds, schema_registry=None)
    
    table_name = service.get_table_name("user")
    print(f"[OK] get_table_name('user') = '{table_name}'")
    assert table_name == "users"
    
    # Test AssociationService
    print("\n--- AssociationService Tests ---")
    assoc_service = AssociationService(mock_ds, None)
    
    assoc_table_name = assoc_service.get_table_name("user")
    print(f"[OK] AssociationService.get_table_name('user') = '{assoc_table_name}'")
    assert assoc_table_name == "users"
    
    # Test AssociationDefinition
    assoc = AssociationDefinition(
        name="users",
        type="many_to_many",
        through="user_roles",
        source_key="role_id",
        target_entity="user",
        target_key="user_id"
    )
    print(f"[OK] AssociationDefinition created: type={assoc.type}, through={assoc.through}")
    assert assoc.type == "many_to_many"
    assert assoc.through == "user_roles"
    
    print("\n" + "=" * 60)
    print("OK: All service mock tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_mock_tests()
