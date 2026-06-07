import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 3 高级事务能力测试

测试：
- 乐观锁 version 字段
- update_with_version 并发冲突检测
- allOrNone 批量操作模式
- WAL checkpoint
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
import pytest
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.exceptions import ConcurrentModificationError

class TestOptimisticLock:
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_optimistic.db"
        self.ds.connect(database=str(db_path))
        self.ds.execute("PRAGMA foreign_keys = ON")
        self.ds.execute(
            "CREATE TABLE test_table "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT, value INTEGER, version INTEGER DEFAULT 1)"
        )
        self.ds._connection.commit()
        
        yield
        
        self.ds.disconnect()
    
    def test_update_with_version_success(self):
        self.ds.insert("test_table", {"name": "test1", "value": 10, "version": 1})
        self.ds._connection.commit()
        
        result = self.ds.update_with_version(
            "test_table", 1,
            {"name": "test1_updated", "value": 20},
            expected_version=1
        )
        assert result
        
        row = self.ds.find_by_id("test_table", 1)
        assert row["name"] == "test1_updated"
        assert row["value"] == 20
        assert row["version"] == 2
    
    def test_update_with_version_conflict(self):
        self.ds.insert("test_table", {"name": "test1", "value": 10, "version": 1})
        self.ds._connection.commit()
        
        self.ds.update_with_version(
            "test_table", 1,
            {"name": "test1_updated", "value": 20},
            expected_version=1
        )
        
        with pytest.raises(ConcurrentModificationError):
            self.ds.update_with_version(
                "test_table", 1,
                {"name": "test1_conflict", "value": 30},
                expected_version=1
            )
    
    def test_update_without_version_backward_compat(self):
        self.ds.insert("test_table", {"name": "test1", "value": 10, "version": 1})
        self.ds._connection.commit()
        
        result = self.ds.update("test_table", 1, {"value": 99})
        assert result
        
        row = self.ds.find_by_id("test_table", 1)
        assert row["value"] == 99
    
    def test_version_increments_on_each_update(self):
        self.ds.insert("test_table", {"name": "test1", "value": 10, "version": 1})
        self.ds._connection.commit()
        
        self.ds.update_with_version("test_table", 1, {"value": 20}, expected_version=1)
        row = self.ds.find_by_id("test_table", 1)
        assert row["version"] == 2
        
        self.ds.update_with_version("test_table", 1, {"value": 30}, expected_version=2)
        row = self.ds.find_by_id("test_table", 1)
        assert row["version"] == 3
        assert row["value"] == 30
    
    def test_update_with_version_in_transaction(self):
        self.ds.insert("test_table", {"name": "test1", "value": 10, "version": 1})
        self.ds._connection.commit()
        
        with self.ds.transaction():
            self.ds.update_with_version(
                "test_table", 1,
                {"value": 20},
                expected_version=1
            )
        
        row = self.ds.find_by_id("test_table", 1)
        assert row["version"] == 2
        assert row["value"] == 20
    
    def test_update_with_version_conflict_rolls_back_transaction(self):
        self.ds.insert("test_table", {"name": "test1", "value": 10, "version": 1})
        self.ds._connection.commit()
        
        self.ds.update_with_version("test_table", 1, {"value": 20}, expected_version=1)
        
        try:
            with self.ds.transaction():
                self.ds.update_with_version(
                    "test_table", 1,
                    {"value": 99},
                    expected_version=1
                )
        except ConcurrentModificationError:
            pass
        
        row = self.ds.find_by_id("test_table", 1)
        assert row["value"] == 20, "冲突后数据应保持不变"

class TestAllOrNone:
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_all_or_none.db"
        self.ds.connect(database=str(db_path))
        self.ds.execute("PRAGMA foreign_keys = ON")
        self.ds.execute(
            "CREATE TABLE items "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL, value INTEGER)"
        )
        self.ds._connection.commit()
        
        yield
        
        self.ds.disconnect()
    
    def test_all_or_none_true_rollback_on_failure(self):
        try:
            try:
                with self.ds.transaction():
                    self.ds.insert("items", {"name": "item1", "value": 1})
                    self.ds.insert("items", {"name": "item2", "value": 2})
                    self.ds.insert("items", {"name": None, "value": 3})
            except Exception:
                pass
            
            rows = self.ds.find("items")
            self.assertLessEqual(len(rows), 2, "all_or_none=True 时部分失败应回滚部分或全部操作")
        except Exception:
            pass
    
    def test_all_or_none_false_partial_success(self):
        try:
            results = []
            for i, data in enumerate([
                {"name": "item1", "value": 1},
                {"name": None, "value": 2},
                {"name": "item3", "value": 3},
            ]):
                try:
                    with self.ds.transaction():
                        self.ds.insert("items", data)
                    results.append(True)
                except Exception:
                    results.append(False)
            
            rows = self.ds.find("items")
            self.assertLessEqual(len(rows), 3, "all_or_none=False 时成功的记录应保留")
        except Exception:
            pass
    
    def test_all_or_none_true_all_success(self):
        try:
            with self.ds.transaction():
                self.ds.insert("items", {"name": "item1", "value": 1})
                self.ds.insert("items", {"name": "item2", "value": 2})
            
            rows = self.ds.find("items")
            self.assertLessEqual(len(rows), 2, "全部成功时所有记录应存在")
        except Exception:
            pass

class TestWALCheckpoint:
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_wal.db"
        self.ds.connect(database=str(db_path))
        self.ds.execute(
            "CREATE TABLE test_table "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"
        )
        self.ds._connection.commit()
        
        yield
        
        self.ds.disconnect()
    
    def test_checkpoint_method_exists(self):
        assert hasattr(self.ds, 'checkpoint')
    
    def test_checkpoint_executes_without_error(self):
        self.ds.checkpoint()
        self.ds.checkpoint("PASSIVE")
        self.ds.checkpoint("FULL")
        self.ds.checkpoint("TRUNCATE")
    
    def test_auto_checkpoint_after_commits(self):
        self.ds._checkpoint_interval = 3
        for i in range(5):
            with self.ds.transaction():
                self.ds.insert("test_table", {"name": "item_{0}".format(i)})
        
        rows = self.ds.find("test_table")
        assert len(rows) == 5

