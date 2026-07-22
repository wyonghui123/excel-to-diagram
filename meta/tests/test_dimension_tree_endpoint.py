# -*- coding: utf-8 -*-
"""
Tests for GET /api/v2/bo/management_dimension/<dim>/tree endpoint
[FIX 2026-07-22] 层级值帮助 picker 后端
"""
import json
import os
import sys
import tempfile
import sqlite3

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask, g

from meta.api.management_dimension_api import register_management_dimension_apis

pytestmark = pytest.mark.integration


class MockDataSource:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=None):
        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        self.conn.commit()
        return cursor

    def close(self):
        self.conn.close()


def _init_test_database(ds):
    ds.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT
        )
    """)
    ds.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)
    ds.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            domain_name TEXT NOT NULL,
            code TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES versions(id)
        )
    """)
    ds.execute("""
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER NOT NULL,
            sub_domain_name TEXT NOT NULL,
            code TEXT NOT NULL,
            FOREIGN KEY (domain_id) REFERENCES domains(id)
        )
    """)

    ds.execute("INSERT INTO products (id, name, code) VALUES (100, '产品A', 'PROD_A')")
    ds.execute("INSERT INTO products (id, name, code) VALUES (200, '产品B', 'PROD_B')")
    ds.execute("INSERT INTO versions (id, product_id, name, code) VALUES (110, 100, 'V1.0', 'V1')")
    ds.execute("INSERT INTO versions (id, product_id, name, code) VALUES (120, 100, 'V2.0', 'V2')")
    ds.execute("INSERT INTO domains (id, version_id, domain_name, code) VALUES (210, 110, '采购域', 'PROC')")
    ds.execute("INSERT INTO domains (id, version_id, domain_name, code) VALUES (220, 110, '销售域', 'SALES')")
    ds.execute("INSERT INTO sub_domains (id, domain_id, sub_domain_name, code) VALUES (310, 210, '询价单', 'INQ')")
    ds.execute("INSERT INTO sub_domains (id, domain_id, sub_domain_name, code) VALUES (320, 210, '采购订单', 'PO')")
    ds.execute("INSERT INTO sub_domains (id, domain_id, sub_domain_name, code) VALUES (330, 220, '销售报价', 'SQ')")


@pytest.fixture
def app_with_data():
    tmpfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmpfile.close()
    ds = MockDataSource(tmpfile.name)
    _init_test_database(ds)

    # Monkey-patch module-level _data_source AND _engine 让 _build_dimension_tree
    # 直接用我们的临时 DB (跳过 _get_engine 内的 production DB 初始化)
    import meta.api.management_dimension_api as api_mod
    original_ds = api_mod._data_source
    original_engine = api_mod._engine
    api_mod._data_source = ds
    api_mod._engine = object()  # 非 None, 让 _get_engine 不再初始化

    try:
        from meta.api.management_dimension_api import _build_dimension_tree
        yield {
            'ds': ds,
            'tmpfile': tmpfile.name,
            'build_dimension_tree': _build_dimension_tree,
        }
    finally:
        api_mod._data_source = original_ds
        api_mod._engine = original_engine
        ds.close()
        try:
            os.unlink(tmpfile.name)
        except OSError:
            pass


class TestDimensionTreeEndpoint:
    def test_returns_flat_array_with_parent_id(self, app_with_data):
        """返回扁平数组，每节点含 parent_id / level / type / child_count"""
        build = app_with_data['build_dimension_tree']
        result = build('sub_domain')
        assert 'data' in result
        assert 'total' in result
        assert len(result['data']) > 0

        # 至少有一个根节点 (product)
        root_nodes = [n for n in result['data'] if n['parent_id'] is None]
        assert len(root_nodes) >= 1
        assert root_nodes[0]['level'] == 0
        assert root_nodes[0]['type'] == 'product'

        # 必要字段
        for node in result['data']:
            assert 'id' in node
            assert 'parent_id' in node
            assert 'level' in node
            assert 'type' in node
            assert 'name' in node
            assert 'code' in node
            assert 'has_children' in node
            assert 'child_count' in node

    def test_levels_chain_correct(self, app_with_data):
        """dim=sub_domain 时, 包含 product/version/domain/sub_domain 4 层"""
        build = app_with_data['build_dimension_tree']
        result = build('sub_domain')
        types = sorted({n['type'] for n in result['data']})
        assert types == ['domain', 'product', 'sub_domain', 'version']

    def test_search_returns_matched_with_parent_chain(self, app_with_data):
        """搜索返回命中节点 + 完整父链"""
        build = app_with_data['build_dimension_tree']
        result = build('sub_domain', search='询价')
        data = result['data']

        # 至少有一个匹配节点
        matched = [n for n in data if '询价' in n['name']]
        assert len(matched) > 0

        # 每个匹配节点都有父链节点
        for m in matched:
            parent_id = m['parent_id']
            if parent_id is not None:
                parents = [n for n in data if n['id'] == parent_id]
                assert len(parents) == 1, f"missing parent {parent_id}"

    def test_dim_only_returns_levels_up_to_target(self, app_with_data):
        """dim=product 只返回 product 层 (1 层)"""
        build = app_with_data['build_dimension_tree']
        result = build('product')
        types = sorted({n['type'] for n in result['data']})
        assert types == ['product']

    def test_version_id_filter(self, app_with_data):
        """version_id 过滤对 sub_domain 起作用"""
        build = app_with_data['build_dimension_tree']
        # version_id=999 不存在, 所以 sub_domain 应为空
        result = build('sub_domain', version_id=999)
        sd_nodes = [n for n in result['data'] if n['type'] == 'sub_domain']
        assert len(sd_nodes) == 0