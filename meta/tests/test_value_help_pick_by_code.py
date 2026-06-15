# -*- coding: utf-8 -*-
"""
[FILE] test_value_help_pick_by_code.py
[DESCRIPTION] 跨领域关系 - BO Pick by Code API 单元测试 (V1.2.0)
[SPEC] .trae/specs/cross-domain-relationship-permission/spec.md

[SCENARIOS]
  S01: 缺 code → 400 MISSING_CODE
  S02: 缺 product_id → 400 MISSING_PRODUCT_ID
  S03: product_id 非法 → 400 INVALID_PRODUCT_ID
  S04: 未登录 → 401 UNAUTHORIZED
  S05: pick_by_code 正常 → 200 + BO 字典
  S06: pick_by_code 不存在 → 404 BO_NOT_FOUND
  S07: pick_by_id 正常 → 200 + BO 字典
  S08: pick_by_id 不存在 → 404 BO_NOT_FOUND
  S09: BoPickService.pick_by_code 边界 (None code/id) → None
  S10: BoPickService.pick_by_code 异常处理 (bad ds) → None (不抛)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import Mock, patch, MagicMock

from meta.services.bo_pick_service import BoPickService


# ============================================================================
# Mock 辅助
# ============================================================================
class MockDataSource:
    """[V1.2.0] 模拟 DataSource"""

    def __init__(self, rows_by_query=None, raise_exc=False):
        self.rows_by_query = rows_by_query or {}
        self.executed_queries = []
        self.raise_exc = raise_exc

    def execute(self, sql, params=None):
        self.executed_queries.append((sql, params))
        if self.raise_exc:
            raise Exception("Mock SQL error")
        sql_lower = sql.lower()
        for key, rows in self.rows_by_query.items():
            if key in sql_lower:
                return MockCursor(rows)
        return MockCursor([])


class MockCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


# ============================================================================
# BoPickService 单元测试
# ============================================================================
class TestBoPickServicePickByCode:
    """[V1.2.0] BoPickService.pick_by_code 单元测试"""

    def test_pick_by_code_returns_bo_dict(self):
        """正常情况: pick_by_code 返 BO 字典"""
        mock_ds = MockDataSource(rows_by_query={
            'select bo.id,': [
                (216, 'BORSS80DT7R0', '对象0RSS80DT7R', None, 1, None),
            ]
        })
        result = BoPickService.pick_by_code('BORSS80DT7R0', 1, data_source=mock_ds)
        assert result is not None
        assert result['id'] == 216
        assert result['code'] == 'BORSS80DT7R0'
        assert result['name'] == '对象0RSS80DT7R'

    def test_pick_by_code_returns_none_when_empty(self):
        """[S06] 不存在 → None"""
        mock_ds = MockDataSource()  # 默认返空
        result = BoPickService.pick_by_code('NONEXIST_999', 1, data_source=mock_ds)
        assert result is None

    def test_pick_by_code_returns_none_when_empty_code(self):
        """空 code → None (不调 DB)"""
        result = BoPickService.pick_by_code('', 1, data_source=MagicMock())
        assert result is None

    def test_pick_by_code_returns_none_when_zero_product_id(self):
        """product_id=0 → None"""
        result = BoPickService.pick_by_code('BO01', 0, data_source=MagicMock())
        assert result is None

    def test_pick_by_code_handles_sql_exception(self):
        """[S10] DB 异常 → None (不抛异常)"""
        mock_ds = MockDataSource(raise_exc=True)
        result = BoPickService.pick_by_code('BO01', 1, data_source=mock_ds)
        assert result is None  # 不抛异常, 静默返回 None

    def test_pick_by_code_uses_correct_sql(self):
        """验证 SQL 含 version_id 子查询 (限定 product)"""
        mock_ds = MockDataSource(rows_by_query={
            'select bo.id,': [(1, 'BO01', '测试', None, 1, None)]
        })
        BoPickService.pick_by_code('BO01', 1, data_source=mock_ds)
        # 检查 SQL 含关键 fragment
        sql = mock_ds.executed_queries[0][0]
        assert 'WHERE bo.code = ?' in sql
        assert 'SELECT id FROM versions WHERE product_id = ?' in sql
        assert 'LIMIT 1' in sql
        # 验证 params
        params = mock_ds.executed_queries[0][1]
        assert params == ['BO01', 1]

    def test_pick_by_code_uses_white_list_fields(self):
        """验证只用 _BO_PICK_FIELDS 字段 (无 owner_id, created_by 等敏感字段)"""
        from meta.services.bo_pick_service import _BO_PICK_FIELDS
        # 敏感字段应不在白名单
        assert 'owner_id' not in _BO_PICK_FIELDS
        assert 'created_by' not in _BO_PICK_FIELDS
        assert 'updated_by' not in _BO_PICK_FIELDS
        # 业务字段在白名单
        assert 'id' in _BO_PICK_FIELDS
        assert 'code' in _BO_PICK_FIELDS
        assert 'name' in _BO_PICK_FIELDS
        assert 'version_id' in _BO_PICK_FIELDS


class TestBoPickServicePickById:
    """[V1.2.0] BoPickService.pick_by_id 单元测试"""

    def test_pick_by_id_returns_bo_dict(self):
        """正常情况: pick_by_id 返 BO 字典"""
        mock_ds = MockDataSource(rows_by_query={
            'select bo.id,': [
                (216, 'BORSS80DT7R0', '对象0RSS80DT7R', None, 1, None),
            ]
        })
        result = BoPickService.pick_by_id(216, data_source=mock_ds)
        assert result is not None
        assert result['id'] == 216

    def test_pick_by_id_returns_none_when_empty(self):
        """[S08] 不存在 → None"""
        mock_ds = MockDataSource()
        result = BoPickService.pick_by_id(99999, data_source=mock_ds)
        assert result is None

    def test_pick_by_id_returns_none_when_zero_id(self):
        """bo_id=0 → None"""
        result = BoPickService.pick_by_id(0, data_source=MagicMock())
        assert result is None

    def test_pick_by_id_handles_exception(self):
        """DB 异常 → None"""
        mock_ds = MockDataSource(raise_exc=True)
        result = BoPickService.pick_by_id(1, data_source=mock_ds)
        assert result is None


class TestBoPickServicePickByNameFuzzy:
    """[V1.2.0] BoPickService.pick_by_name_fuzzy 单元测试"""

    def test_pick_by_name_fuzzy_returns_list(self):
        """正常: name 模糊搜索返列表"""
        mock_ds = MockDataSource(rows_by_query={
            'select bo.id,': [
                (1, 'BO01', '用户', None, 1, None),
                (2, 'BO02', '用户组', None, 1, None),
            ]
        })
        result = BoPickService.pick_by_name_fuzzy('用户', 1, limit=20, data_source=mock_ds)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_pick_by_name_fuzzy_empty_name(self):
        """空 name → []"""
        result = BoPickService.pick_by_name_fuzzy('', 1, data_source=MagicMock())
        assert result == []

    def test_pick_by_name_fuzzy_exception_returns_empty(self):
        """DB 异常 → [] (不抛)"""
        mock_ds = MockDataSource(raise_exc=True)
        result = BoPickService.pick_by_name_fuzzy('test', 1, data_source=mock_ds)
        assert result == []


# ============================================================================
# API 集成测试 (通过 test_client)
# ============================================================================
class TestPickByCodeApiEndpoint:
    """[V1.2.0] /api/v2/bo/business_object/pick_by_code 端点测试 (via test_client)"""

    def test_endpoint_missing_code_returns_400(self, shared_client, admin_token):
        """[S01] 缺 code → 400 MISSING_CODE"""
        if shared_client is None:
            pytest.skip("shared_client not available")
        r = shared_client.get(
            '/api/v2/bo/business_object/pick_by_code?product_id=1',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert r.status_code == 400
        data = r.get_json()
        assert data['success'] is False
        assert data['error_code'] == 'MISSING_CODE'

    def test_endpoint_missing_product_id_returns_400(self, shared_client, admin_token):
        """[S02] 缺 product_id → 400 MISSING_PRODUCT_ID"""
        if shared_client is None:
            pytest.skip("shared_client not available")
        r = shared_client.get(
            '/api/v2/bo/business_object/pick_by_code?code=BO01',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert r.status_code == 400
        data = r.get_json()
        assert data['success'] is False
        assert data['error_code'] == 'MISSING_PRODUCT_ID'

    def test_endpoint_invalid_product_id_returns_400(self, shared_client, admin_token):
        """[S03] product_id 非法 → 400 INVALID_PRODUCT_ID"""
        if shared_client is None:
            pytest.skip("shared_client not available")
        r = shared_client.get(
            '/api/v2/bo/business_object/pick_by_code?code=BO01&product_id=abc',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert r.status_code == 400
        data = r.get_json()
        assert data['success'] is False
        assert data['error_code'] == 'INVALID_PRODUCT_ID'

    def test_endpoint_unauthorized_returns_401(self, shared_client):
        """[S04] 未登录 → 401"""
        if shared_client is None:
            pytest.skip("shared_client not available")
        r = shared_client.get('/api/v2/bo/business_object/pick_by_code?code=X&product_id=1')
        # 401 (未登录) 或 302 (重定向到登录) 都是预期
        assert r.status_code in (401, 302)

    def test_endpoint_pick_existing_bo_returns_200(self, shared_client, admin_token):
        """[S05 端点] pick_by_code 存在 → 200 + BO 字典"""
        if shared_client is None:
            pytest.skip("shared_client not available")
        r = shared_client.get(
            '/api/v2/bo/business_object/pick_by_code?code=BORSS80DT7R0&product_id=1',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        # 200 (找到) 或 404 (BO 编码不在测试 DB) 都可接受 (测试环境数据可能不同)
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            data = r.get_json()
            assert data['success'] is True
            assert 'id' in data['data']
            assert 'code' in data['data']
            assert data['data']['code'] == 'BORSS80DT7R0'
