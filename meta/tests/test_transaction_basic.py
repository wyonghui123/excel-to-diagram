import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
事务系统基础测试

测试 SQLiteAdapter 的事务核心功能：
- begin_transaction / commit / rollback
- 条件化 commit（事务内不自动 commit，事务外自动 commit）
- Savepoint 支持
- 外键约束启用
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
import pytest
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.datasource import DataSourceType
from meta.core.table_name_validator import register_table_name

register_table_name('parent_table')
register_table_name('child_table')

class TestTransactionBasic:
    
    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test.db"
        self.ds.connect(database=str(db_path))
        self.ds.execute(
            "CREATE TABLE test_table "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, value INTEGER)"
        )
        self.ds.execute("INSERT INTO test_table (name, value) VALUES ('init', 0)")
        self.ds._connection.commit()
        
        yield
        
        self.ds.disconnect()
    
    def test_begin_transaction_enters_explicit_mode(self):
        assert not self.ds.in_transaction
        self.ds.begin_transaction()
        assert self.ds.in_transaction
        self.ds.rollback()
    
    def test_commit_exits_transaction(self):
        self.ds.begin_transaction()
        assert self.ds.in_transaction
        self.ds.commit()
        assert not self.ds.in_transaction
    
    def test_rollback_exits_transaction(self):
        self.ds.begin_transaction()
        assert self.ds.in_transaction
        self.ds.rollback()
        assert not self.ds.in_transaction
    
    def test_insert_no_auto_commit_in_transaction(self):
        self.ds.begin_transaction()
        self.ds.insert("test_table", {"name": "tx_test", "value": 1})
        rows = self.ds.find("test_table", {"name": "tx_test"})
        assert len(rows) == 1, "事务内应能读到未提交的数据"
        self.ds.rollback()
        rows = self.ds.find("test_table", {"name": "tx_test"})
        assert len(rows) == 0, "回滚后数据应不存在"
    
    def test_insert_auto_commit_outside_transaction(self):
        assert not self.ds.in_transaction
        self.ds.insert("test_table", {"name": "auto_test", "value": 2})
        rows = self.ds.find("test_table", {"name": "auto_test"})
        assert len(rows) == 1, "非事务模式应自动提交"
    
    def test_update_no_auto_commit_in_transaction(self):
        self.ds.begin_transaction()
        self.ds.update("test_table", 1, {"value": 99})
        row = self.ds.find_by_id("test_table", 1)
        assert row["value"] == 99, "事务内应能读到更新"
        self.ds.rollback()
        row = self.ds.find_by_id("test_table", 1)
        assert row["value"] == 0, "回滚后应恢复原值"
    
    def test_update_auto_commit_outside_transaction(self):
        self.ds.update("test_table", 1, {"value": 50})
        row = self.ds.find_by_id("test_table", 1)
        assert row["value"] == 50, "非事务模式应自动提交更新"
    
    def test_delete_no_auto_commit_in_transaction(self):
        self.ds.begin_transaction()
        self.ds.delete("test_table", 1)
        row = self.ds.find_by_id("test_table", 1)
        assert row is None, "事务内删除后应读不到"
        self.ds.rollback()
        row = self.ds.find_by_id("test_table", 1)
        assert row is not None, "回滚后数据应恢复"
    
    def test_delete_auto_commit_outside_transaction(self):
        self.ds.delete("test_table", 1)
        row = self.ds.find_by_id("test_table", 1)
        assert row is None, "非事务模式应自动提交删除"
    
    def test_transaction_context_manager_commit(self):
        with self.ds.transaction():
            assert self.ds.in_transaction
            self.ds.insert("test_table", {"name": "ctx_test", "value": 3})
        assert not self.ds.in_transaction
        rows = self.ds.find("test_table", {"name": "ctx_test"})
        assert len(rows) == 1, "上下文管理器正常退出应提交"
    
    def test_transaction_context_manager_rollback_on_exception(self):
        try:
            with self.ds.transaction():
                self.ds.insert("test_table", {"name": "rollback_test", "value": 4})
                raise ValueError("模拟异常")
        except ValueError:
            pass
        assert not self.ds.in_transaction
        rows = self.ds.find("test_table", {"name": "rollback_test"})
        assert len(rows) == 0, "异常时应回滚"
    
    def test_savepoint_create_and_rollback(self):
        with self.ds.transaction():
            self.ds.insert("test_table", {"name": "sp_before", "value": 10})
            sp = self.ds.set_savepoint("sp1")
            self.ds.insert("test_table", {"name": "sp_after", "value": 11})
            self.ds.rollback_to(sp)
            self.ds.insert("test_table", {"name": "sp_final", "value": 12})
        rows_before = self.ds.find("test_table", {"name": "sp_before"})
        rows_after = self.ds.find("test_table", {"name": "sp_after"})
        rows_final = self.ds.find("test_table", {"name": "sp_final"})
        assert len(rows_before) == 1, "savepoint前的数据应保留"
        assert len(rows_after) == 0, "savepoint回滚后数据应不存在"
        assert len(rows_final) == 1, "回滚后新插入的数据应存在"
    
    def test_savepoint_nested(self):
        with self.ds.transaction():
            self.ds.insert("test_table", {"name": "outer", "value": 20})
            sp1 = self.ds.set_savepoint("sp_outer")
            self.ds.insert("test_table", {"name": "inner1", "value": 21})
            sp2 = self.ds.set_savepoint("sp_inner")
            self.ds.insert("test_table", {"name": "inner2", "value": 22})
            self.ds.rollback_to(sp2)
        rows_outer = self.ds.find("test_table", {"name": "outer"})
        rows_inner1 = self.ds.find("test_table", {"name": "inner1"})
        rows_inner2 = self.ds.find("test_table", {"name": "inner2"})
        assert len(rows_outer) == 1
        assert len(rows_inner1) == 1
        assert len(rows_inner2) == 0, "内层savepoint回滚应只影响内层"
    
    def test_foreign_keys_enabled(self, tmp_path):
        try:
            ds = SQLiteAdapter()
            # v3.13+ :memory: 不支持，改用临时文件
            db_path = tmp_path / "fk_test.db"
            ds.connect(database=str(db_path))
            ds.execute("PRAGMA foreign_keys = ON")
            ds.execute(
                "CREATE TABLE parent_table (id INTEGER PRIMARY KEY, name TEXT)"
            )
            ds.execute(
                "CREATE TABLE child_table (id INTEGER PRIMARY KEY, "
                "parent_id INTEGER REFERENCES parent_table(id) ON DELETE CASCADE)"
            )
            ds._connection.commit()
            ds.insert("parent_table", {"id": 1, "name": "p1"})
            ds._connection.commit()
            with pytest.raises(Exception):
                with ds.transaction():
                    ds.insert("child_table", {"id": 1, "parent_id": 999})
            ds.disconnect()
        except Exception as e:
            pytest.fail(f"Foreign key test issue: {e}")
    
    def test_in_transaction_property(self):
        assert not self.ds.in_transaction
        self.ds.begin_transaction()
        assert self.ds.in_transaction
        self.ds.commit()
        assert not self.ds.in_transaction
        self.ds.begin_transaction()
        assert self.ds.in_transaction
        self.ds.rollback()
        assert not self.ds.in_transaction
    
    def test_batch_insert_no_auto_commit_in_transaction(self):
        self.ds.begin_transaction()
        self.ds.batch_insert("test_table", [
            {"name": "batch1", "value": 100},
            {"name": "batch2", "value": 101},
        ])
        rows = self.ds.find("test_table")
        assert any(r["name"] == "batch1" for r in rows)
        self.ds.rollback()
        rows = self.ds.find("test_table", {"name": "batch1"})
        assert len(rows) == 0, "回滚后批量插入应不存在"
    
    def test_double_begin_transaction_is_noop(self):
        self.ds.begin_transaction()
        assert self.ds.in_transaction
        self.ds.begin_transaction()
        assert self.ds.in_transaction
        self.ds.rollback()
        assert not self.ds.in_transaction

