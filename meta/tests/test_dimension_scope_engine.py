import pytest

pytestmark = pytest.mark.unit

import sys
import os
import sqlite3
import tempfile
import json

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
from meta.services.dimension_scope_engine import DimensionScopeEngine, HIERARCHY_CHAIN


@pytest.fixture
def ds():
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS role_dimension_scopes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            dimension_code TEXT NOT NULL,
            dimension_values TEXT,
            inherit_children INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_code TEXT UNIQUE NOT NULL,
            menu_name TEXT,
            parent_menu TEXT,
            primary_object_type TEXT,
            object_types TEXT,
            auto_generated INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            show_in_sidebar INTEGER DEFAULT 1,
            required_permissions TEXT
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT
        );
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            product_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            version_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            domain_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            sub_domain_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            service_module_id INTEGER
        );
    """)
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection

        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor

        def commit(self):
            self._conn.commit()

    yield MockDS(conn)
    conn.close()
    os.unlink(db_path)


def _seed_scope_data(ds):
    ds.execute(
        "INSERT INTO role_dimension_scopes (role_id, dimension_code, dimension_values, inherit_children) VALUES (?, ?, ?, ?)",
        [1, 'product', json.dumps([1]), 1]
    )
    ds.execute(
        "INSERT INTO products (name, code) VALUES (?, ?)",
        ['Product1', 'P1']
    )


def test_expand_dimension_values(ds):
    _seed_scope_data(ds)
    engine = DimensionScopeEngine(ds)
    result = engine.expand_dimension_values(1)
    assert isinstance(result, dict)
    assert 'product' in result
    assert 1 in result['product']


def test_derive_data_conditions(ds):
    _seed_scope_data(ds)
    engine = DimensionScopeEngine(ds)
    result = engine.derive_data_conditions(1)
    assert isinstance(result, dict)


def test_derive_recommended_menus(ds):
    _seed_scope_data(ds)
    ds.execute(
        "INSERT INTO menus (menu_code, menu_name, primary_object_type, object_types, auto_generated, is_active) VALUES (?, ?, ?, ?, ?, ?)",
        ['menu_domain', 'Domain Menu', 'domain', json.dumps(['domain']), 1, 1]
    )
    engine = DimensionScopeEngine(ds)
    result = engine.derive_recommended_menus(1)
    assert isinstance(result, list)


def test_derive_permissions(ds):
    _seed_scope_data(ds)
    ds.execute(
        "INSERT INTO menus (menu_code, menu_name, primary_object_type, object_types, auto_generated, is_active, required_permissions) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ['menu_domain', 'Domain Menu', 'domain', json.dumps(['domain']), 1, 1, json.dumps(['domain:read'])]
    )
    engine = DimensionScopeEngine(ds)
    result = engine.derive_permissions(1)
    assert isinstance(result, list)


def test_auto_sync_all(ds):
    _seed_scope_data(ds)
    engine = DimensionScopeEngine(ds)
    result = engine.auto_sync_all(1)
    assert isinstance(result, dict)
    assert 'dimension_scopes' in result
    assert 'recommended_menus' in result
    assert 'derived_permissions' in result
    assert 'data_conditions' in result


def test_hierarchy_chain_constant():
    # [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
    # 新的层级链: product → version → domain → sub_domain (4层)
    assert HIERARCHY_CHAIN == ['product', 'version', 'domain', 'sub_domain']


def test_load_scopes_empty(ds):
    engine = DimensionScopeEngine(ds)
    scopes = engine._load_scopes(999)
    assert isinstance(scopes, list)
    assert len(scopes) == 0
