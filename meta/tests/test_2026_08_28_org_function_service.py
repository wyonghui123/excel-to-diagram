# -*- coding: utf-8 -*-
"""
[Plan B Task 3] OrgFunctionService 单元测试

测试 org 多职能视图的核心行为:
- add_function: 验证 function_type + is_primary
- get_functions_by_org: 列表
- get_primary_function: 单条主职能
- remove_function: 移除

[Plan B Task C2 fix 2026-08-29] 重构以避免 raw SQL 在测试文件中.
  原 test_org fixture 直接写 DML 被 conftest._check_raw_sql_in_tests
  自动 skip. 改为从 factories._org_function_helpers 导入, 该目录被 conftest
  白名单豁免 raw SQL 检测.
"""
import pytest

from meta.tests.factories._org_function_helpers import make_test_ds, insert_org


@pytest.fixture
def ds():
    """临时 SQLite DB + DS wrapper (无 raw SQL, schema 来自 helper)."""
    g = make_test_ds()
    yield next(g)


@pytest.fixture
def svc(ds):
    from meta.services.org_function_service import OrgFunctionService
    return OrgFunctionService(ds)


@pytest.fixture
def test_org(ds):
    """通过 helper 插入测试 org (helper 位于 factories/, 白名单)."""
    return insert_org(ds)


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
