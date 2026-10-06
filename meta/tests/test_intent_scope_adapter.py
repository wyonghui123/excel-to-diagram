# -*- coding: utf-8 -*-
"""
IntentScopeAdapter TDD 测试

[覆盖范围]
  1. 单个 role 的过滤条件生成 (include/exclude)
  2. 多 role 合并 (OR 关系)
  3. 空 include = all (1=1 占位)
  4. 写拦截器: check_record_allowed (owner_id 运行时变量)
  5. Feature flag 控制
"""
import os
import sys
import json
import sqlite3
import tempfile

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ['TEST_ENTRY'] = '1'
os.environ['ALLOW_RAW_SQL'] = '1'


@pytest.fixture(scope="class")
def adapter_db():
    """创建测试 DB: 含 role_effective_intents + 业务表"""
    tmp_dir = tempfile.mkdtemp(prefix='adapter_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE permission_set_effective_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            data_scope TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'derived',
            is_stale INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (permission_set_id, bo_id, action_name)
        );

        -- 业务表
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            code TEXT, name TEXT, owner_id INTEGER, created_by INTEGER,
            status TEXT, risk_level INTEGER
        );

        INSERT INTO products VALUES
            (1, 'P1', 'Product 1', 100, 100, 'active', 2),
            (2, 'P2', 'Product 2', 200, 200, 'archived', 5),
            (3, 'P3', 'Product 3', 100, 100, 'active', 1),
            -- [A1 2026-10-06] owner_id ≠ created_by：用于验证 include 分支的
            --   ${user.id} 运行时变量（_is_owner 只看 owner_id，故该记录非 owner）
            (4, 'P4', 'Product 4', 900, 100, 'active', 1);
    ''')
    conn.commit()
    conn.close()
    return db_path


class TestIntentScopeAdapter:
    """IntentScopeAdapter 单元测试"""

    @pytest.fixture(autouse=True)
    def setup_adapter(self, adapter_db):
        from meta.core.intent_scope_adapter import IntentScopeAdapter
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        self.db_path = adapter_db
        self.dao = EffectiveIntentDAO(adapter_db)
        self.adapter = IntentScopeAdapter(
            db_path=adapter_db,
            dao=self.dao,
        )

    def _insert_intent(self, role_id, bo_id, action, data_scope):
        """辅助: 插入 Intent"""
        self.dao.upsert(
            permission_set_id=role_id,
            bo_id=bo_id,
            action_name=action,
            data_scope=data_scope,
        )

    def test_empty_role_ids_returns_none(self):
        """空 role_ids → None (默认拒绝)"""
        result = self.adapter.get_filter_for_roles([], 'product', 'read')
        assert result is None

    def test_no_intent_returns_none(self):
        """无 Intent → None (默认拒绝)"""
        result = self.adapter.get_filter_for_roles([999], 'product', 'read')
        assert result is None

    def test_empty_include_means_all(self):
        """空 include → cond_expr 含 1=1 (允许所有)"""
        self._insert_intent(1, 'product', 'read', {'include': [], 'exclude': []})

        result = self.adapter.get_filter_for_roles([1], 'product', 'read')
        assert result is not None
        assert '1=1' in result['cond_expr']
        # sources 是 list, 空 include 的 role 贡献 'include_all'
        # [A1 2026-10-06] 实现侧该 token 为 'include_all'（见 intent_scope_adapter:149），
        #   旧断言 'all' 已随 P4/P5 语义细化而失效
        assert 'include_all' in result['sources']

    def test_include_in_clause(self):
        """include IN 条件正确生成"""
        self._insert_intent(2, 'product', 'read', {
            'include': [{'field': 'owner_id', 'op': 'IN', 'value': [100, 200]}],
            'exclude': [],
        })

        result = self.adapter.get_filter_for_roles([2], 'product', 'read')
        assert result is not None
        assert 'owner_id IN' in result['cond_expr']
        # params 应包含 100 和 200
        assert 100 in result['params']
        assert 200 in result['params']

    def test_exclude_becomes_not_clause(self):
        """exclude 条件变为 NOT (...)"""
        self._insert_intent(3, 'product', 'read', {
            'include': [],
            'exclude': [{'field': 'status', 'op': '=', 'value': 'archived'}],
        })

        result = self.adapter.get_filter_for_roles([3], 'product', 'read')
        assert result is not None
        assert 'NOT' in result['cond_expr'].upper()
        assert 'archived' in result['params']

    def test_multiple_roles_or_merged(self):
        """多个 role 的条件用 OR 合并"""
        self._insert_intent(10, 'product', 'read', {
            'include': [{'field': 'owner_id', 'op': '=', 'value': 100}],
            'exclude': [],
        })
        self._insert_intent(11, 'product', 'read', {
            'include': [{'field': 'owner_id', 'op': '=', 'value': 200}],
            'exclude': [],
        })

        result = self.adapter.get_filter_for_roles([10, 11], 'product', 'read')
        assert result is not None
        assert 'OR' in result['cond_expr'].upper()

    def test_role_with_no_intent_skipped(self):
        """无 Intent 的 role 被跳过, 不影响其他 role"""
        self._insert_intent(20, 'product', 'read', {
            'include': [{'field': 'owner_id', 'op': '=', 'value': 100}],
            'exclude': [],
        })
        # role 21 无 Intent

        result = self.adapter.get_filter_for_roles([20, 21], 'product', 'read')
        assert result is not None
        assert 'default_deny' in result['sources']

    def test_check_record_allowed_no_role(self):
        """check_record_allowed: 无 role → 拒绝"""
        result = self.adapter.check_record_allowed(
            role_ids=[],
            bo_id='product',
            action_name='read',
            record_id=1,
            user_id=100,
        )
        assert result['allowed'] is False
        assert result['source'] == 'no_role'

    def test_check_record_allowed_no_intent_falls_back(self):
        """check_record_allowed: 无 Intent → 拒绝 + 回退 legacy

        [A1 2026-10-06] 原用例名 test_check_record_allowed_default_deny，
        但它实际测的是「该 role 无 Intent」场景。实现侧 P5 修复后该场景
        返回 source='no_intent_allows_all'（allowed 仍为 False，交调用方回退
        legacy 5 步检查），而非 'default_deny'（那是「有意图但不匹配」的落点）。
        另 user_id 原取 100，恰为 record 1 的 owner，会被 Owner 优先检查短路。
        """
        result = self.adapter.check_record_allowed(
            role_ids=[999],
            bo_id='product',
            action_name='read',
            record_id=1,
            user_id=999,
        )
        assert result['allowed'] is False
        assert result['source'] == 'no_intent_allows_all'

    def test_check_record_allowed_default_deny(self):
        """check_record_allowed: 有 Intent 但不匹配 → default_deny"""
        self._insert_intent(31, 'product', 'read', {
            'include': [{'field': 'owner_id', 'op': '=', 'value': 100}],
            'exclude': [],
        })

        # user_id=999 非 owner，且 record 2 的 owner_id=200 ≠ 100 → 不匹配
        result = self.adapter.check_record_allowed(
            role_ids=[31],
            bo_id='product',
            action_name='read',
            record_id=2,
            user_id=999,
        )
        assert result['allowed'] is False
        assert result['source'] == 'default_deny'

    def test_check_record_allowed_empty_include(self):
        """check_record_allowed: 空 include = 允许所有"""
        self._insert_intent(30, 'product', 'read', {'include': [], 'exclude': []})

        # [A1 2026-10-06] user_id 由 100 改为 999：原值恰为 record 1 的 owner_id，
        #   会被 Owner 优先检查短路（返回 'owner'），到不了空 include 分支。
        result = self.adapter.check_record_allowed(
            role_ids=[30],
            bo_id='product',
            action_name='read',
            record_id=1,
            user_id=999,
        )
        assert result['allowed'] is True
        assert result['source'] == 'include_all'

    def test_check_record_allowed_owner_runtime_variable(self):
        """check_record_allowed: 运行时变量 ${user.id} 参与 include 匹配

        [A1 2026-10-06] 原用例用 record 1 + user_id=100 断言 source='include'，
        但 100 即 record 1 的 owner_id，Owner 优先检查先命中并返回 'owner'，
        include 分支不可达。改用 record 4（owner_id=900 ≠ created_by=100），
        以 created_by 作为 include 字段——_is_owner 只看 owner_id，
        故该记录能真正进入 include 匹配并验证 ${user.id} 解析。
        """
        self._insert_intent(40, 'product', 'read', {
            'include': [{'field': 'created_by', 'op': '=', 'value': '${user.id}'}],
            'exclude': [],
        })

        # user_id=100 = record 4 的 created_by → include 命中
        result = self.adapter.check_record_allowed(
            role_ids=[40],
            bo_id='product',
            action_name='read',
            record_id=4,
            user_id=100,
        )
        assert result['allowed'] is True
        assert result['source'] == 'include'

        # user_id=999 ≠ created_by 100 → include 不命中 → default_deny
        result = self.adapter.check_record_allowed(
            role_ids=[40],
            bo_id='product',
            action_name='read',
            record_id=4,
            user_id=999,
        )
        assert result['allowed'] is False
        assert result['source'] == 'default_deny'

    def test_check_record_allowed_exclude_denies(self):
        """check_record_allowed: exclude 命中 → 拒绝"""
        self._insert_intent(50, 'product', 'read', {
            'include': [],  # 空 = 全部允许
            'exclude': [{'field': 'owner_id', 'op': '=', 'value': 200}],
        })

        # product 2 owner_id=200 → exclude 命中 → 拒绝
        result = self.adapter.check_record_allowed(
            role_ids=[50],
            bo_id='product',
            action_name='read',
            record_id=2,
            user_id=999,
        )
        assert result['allowed'] is False

        # product 1 owner_id=100 ≠ 200 → exclude 不命中 → 允许
        result = self.adapter.check_record_allowed(
            role_ids=[50],
            bo_id='product',
            action_name='read',
            record_id=1,
            user_id=999,
        )
        assert result['allowed'] is True

    def test_check_record_allowed_any_role_allows(self):
        """check_record_allowed: 任一 role 允许即允许"""
        self._insert_intent(60, 'product', 'read', {
            'include': [{'field': 'owner_id', 'op': '=', 'value': 100}],
            'exclude': [],
        })
        self._insert_intent(61, 'product', 'read', {
            'include': [{'field': 'owner_id', 'op': '=', 'value': 200}],
            'exclude': [],
        })

        # product 1 owner_id=100 → role 60 允许
        result = self.adapter.check_record_allowed(
            role_ids=[60, 61],
            bo_id='product',
            action_name='read',
            record_id=1,
            user_id=999,
        )
        assert result['allowed'] is True
