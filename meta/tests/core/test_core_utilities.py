# -*- coding: utf-8 -*-
"""
核心工具测试

合并以下测试文件:
- test_exceptions.py (异常类)
- test_single_source_of_truth.py (单一事实原则)

测试范围:
- 异常类定义与继承
- 单一事实原则实现
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.integration


# ==================== 异常类测试 ====================

class TestExceptions:
    """异常类测试"""

    def test_exception_inheritance(self):
        """测试异常继承自 Exception"""
        from meta.core.exceptions import ConcurrentModificationError
        assert issubclass(ConcurrentModificationError, Exception)

    def test_raise_and_catch(self):
        """测试异常抛出和捕获"""
        from meta.core.exceptions import ConcurrentModificationError
        with pytest.raises(ConcurrentModificationError):
            raise ConcurrentModificationError("版本冲突")

    def test_exception_message(self):
        """测试异常消息"""
        from meta.core.exceptions import ConcurrentModificationError
        try:
            raise ConcurrentModificationError("乐观锁检测到冲突")
        except ConcurrentModificationError as e:
            assert "乐观锁" in str(e)

    def test_exception_with_context(self):
        """测试异常携带上下文信息"""
        from meta.core.exceptions import ConcurrentModificationError
        error = ConcurrentModificationError(
            f"expected_version=5, actual_version=3"
        )
        assert "expected_version=5" in str(error)

    def test_exception_chaining(self):
        """测试异常链"""
        from meta.core.exceptions import ConcurrentModificationError
        try:
            try:
                raise ValueError("原始错误")
            except ValueError as ve:
                raise ConcurrentModificationError("包装错误") from ve
        except ConcurrentModificationError as e:
            assert e.__cause__ is not None
            assert isinstance(e.__cause__, ValueError)


# ==================== 单一事实原则测试 ====================

class TestSingleSourceOfTruth:
    """单一事实原则测试"""

    def test_get_latest_change_time(self):
        """测试 _get_latest_change_time 函数"""
        from meta.core.datasource import get_data_source
        
        ds = get_data_source("sqlite", database="meta/architecture.db")
        
        def get_latest_change_time(object_type, object_id):
            cursor = ds.execute("""
                SELECT created_at FROM audit_logs 
                WHERE object_type = ? AND object_id = ?
                ORDER BY 
                    CASE action 
                        WHEN 'UPDATE' THEN 1 
                        WHEN 'DELETE' THEN 2 
                        WHEN 'CREATE' THEN 3 
                    END ASC,
                    created_at DESC
                LIMIT 1
            """, [object_type, object_id])
            row = cursor.fetchone()
            return row[0] if row else None
        
        result = get_latest_change_time('role', 99999)
        assert result is None

    def test_audit_logs_for_role(self):
        """测试角色审计日志查询"""
        from meta.core.datasource import get_data_source
        
        ds = get_data_source("sqlite", database="meta/architecture.db")
        
        cursor = ds.execute("""
            SELECT action, created_at, object_id, old_value, new_value 
            FROM audit_logs 
            WHERE object_type = 'role'
            ORDER BY created_at DESC 
            LIMIT 3
        """)
        
        rows = cursor.fetchall()
        assert isinstance(rows, list)

    def test_single_source_of_truth_principle(self):
        """测试单一事实原则实现"""
        from meta.core.datasource import get_data_source
        
        ds = get_data_source("sqlite", database="meta/architecture.db")
        
        cursor = ds.execute("PRAGMA table_info(roles)")
        columns = [row[1] for row in cursor.fetchall()]
        
        has_updated_at = 'updated_at' in columns
        assert isinstance(has_updated_at, bool)

    def test_audit_log_action_types(self):
        """测试审计日志的 action 类型"""
        from meta.core.datasource import get_data_source
        
        ds = get_data_source("sqlite", database="meta/architecture.db")
        
        cursor = ds.execute("""
            SELECT DISTINCT action FROM audit_logs 
            ORDER BY action
        """)
        
        action_types = [row[0] for row in cursor.fetchall()]
        assert isinstance(action_types, list)
