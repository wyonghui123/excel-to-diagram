# -*- coding: utf-8 -*-
"""
[Plan B Task 3] OrgFunctionService 单元测试

测试 org 多职能视图的核心行为:
- add_function: 验证 function_type + is_primary
- get_functions_by_org: 列表
- get_primary_function: 单条主职能
- remove_function: 移除
"""
import os
import sqlite3
import tempfile
import pytest


@pytest.fixture
def ds():
    """创建临时 SQLite DB, 复制 org_functions + orgs 表结构"""
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    # 复制 schema (只复制需要的表)
    main = sqlite3.connect('meta/architecture.db')
    for table in ('orgs', 'org_functions'):
        schema = main.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
        ).fetchone()
        if schema and schema[0]:
            conn.execute(schema[0])
    conn.commit()
    main.close()

    # 简单 wrapper, 兼容 service 的 cursor 接口
    class DS:
        def __init__(self, c):
            self._c = c

        def execute(self, sql, params=None):
            cur = self._c.cursor()
            cur.execute(sql, params or [])
            return cur

        def commit(self):
            self._c.commit()

    yield DS(conn)

    conn.close()
    os.unlink(tmp.name)


@pytest.fixture
def svc(ds):
    from meta.services.org_function_service import OrgFunctionService
    return OrgFunctionService(ds)


@pytest.fixture
def test_org(ds):
    """插入测试 org"""
    cur = ds.execute("INSERT INTO orgs (code, name, org_type) VALUES (?, ?, ?)",
                     ['test_org_of', 'Test Org', 'administrative'])
    ds.commit()
    return cur.lastrowid


class TestOrgFunctionService:
    def test_get_functions_by_org_empty(self, svc, test_org):
        result = svc.get_functions_by_org(test_org)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_add_function_creates_row(self, svc, test_org):
        new_id = svc.add_function(test_org, 'cost_center', is_primary=False)
        assert new_id is not None

        funcs = svc.get_functions_by_org(test_org)
        types = [f['function_type'] for f in funcs]
        assert 'cost_center' in types

    def test_add_function_invalid_type_returns_none(self, svc, test_org):
        result = svc.add_function(test_org, 'invalid_type', is_primary=False)
        assert result is None

    def test_primary_demotes_existing(self, svc, test_org):
        """添加 is_primary=True 时, 已有主职能应被降级"""
        # 先添加一个主职能
        svc.add_function(test_org, 'administrative', is_primary=True)
        # 再添加另一个主职能
        svc.add_function(test_org, 'profit_center', is_primary=True)

        primary = svc.get_primary_function(test_org)
        assert primary is not None
        assert primary['function_type'] == 'profit_center'

        # 验证 administrative 已被降级
        funcs = svc.get_functions_by_org(test_org)
        admin = [f for f in funcs if f['function_type'] == 'administrative'][0]
        assert admin['is_primary'] in (0, False)

    def test_remove_function(self, svc, test_org):
        svc.add_function(test_org, 'legal_entity', is_primary=False)
        success = svc.remove_function(test_org, 'legal_entity')
        assert success is True

        funcs = svc.get_functions_by_org(test_org)
        types = [f['function_type'] for f in funcs]
        assert 'legal_entity' not in types
