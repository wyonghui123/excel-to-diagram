# -*- coding: utf-8 -*-
"""
Phase 2 集成测试 — 补充测试覆盖缺口

[覆盖范围]
  1. 端到端集成: 推导管道 → role_effective_intents → IntentScopeAdapter → 拦截器
  2. CHILDREN_OF 操作符在 IntentScopeAdapter 中的处理
  3. data_scope 边界情况 (null / 空 JSON / 无效 JSON)
  4. 多 role + 跨 role exclude 语义 (当前实现: 每个 role 独立评估)
  5. stale 标记不影响拦截器读取 (设计选择: stale 仍可用, 仅提示重推导)
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


@pytest.fixture(scope="module")
def integration_db():
    """创建完整集成测试 DB: 含推导管道所需的所有表"""
    tmp_dir = tempfile.mkdtemp(prefix='p2_integ_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        -- Layer 2: 统一规则表
        CREATE TABLE permission_rules_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            resource_type VARCHAR(200) NOT NULL,
            permission_level VARCHAR(50) DEFAULT 'read',
            include_conditions TEXT,
            exclude_conditions TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'manual',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Layer 1: 事实表
        CREATE TABLE role_effective_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            data_scope TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'derived',
            is_stale INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role_id, bo_id, action_name)
        );

        -- 层级表
        CREATE TABLE products (id INTEGER PRIMARY KEY, code TEXT, owner_id INTEGER);
        CREATE TABLE versions (id INTEGER PRIMARY KEY, product_id INTEGER, code TEXT, owner_id INTEGER);
        CREATE TABLE domains (id INTEGER PRIMARY KEY, code TEXT, owner_id INTEGER);
        CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, domain_id INTEGER, code TEXT, owner_id INTEGER);
        CREATE TABLE service_modules (id INTEGER PRIMARY KEY, sub_domain_id INTEGER, code TEXT, owner_id INTEGER);

        INSERT INTO products VALUES (1, 'P1', 999), (2, 'P2', 888), (3, 'P3', 777);
        INSERT INTO domains VALUES (1, 'D1', 999), (2, 'D2', 888), (3, 'D3', 777);
        INSERT INTO sub_domains VALUES (101, 1, 'SD11', 999), (102, 1, 'SD12', 888);

        -- RBAC 表
        CREATE TABLE group_roles (group_id INTEGER, role_id INTEGER);
        CREATE TABLE user_group_members (user_id INTEGER, group_id INTEGER);
        INSERT INTO group_roles VALUES (1, 100), (1, 101);
        INSERT INTO user_group_members VALUES (999, 1);
    ''')
    conn.commit()
    conn.close()
    return db_path


# ============================================================================
# 1. 端到端集成: 推导管道 → adapter
# ============================================================================
class TestPipelineToAdapterIntegration:
    """端到端: 推导管道输出 → IntentScopeAdapter 读取"""

    def test_pipeline_output_is_usable_by_adapter(self, integration_db):
        """推导管道写入的 Intent 可被 IntentScopeAdapter 正确读取"""
        from meta.core.derivation_pipeline import PermissionDerivationPipeline
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        # Step 1: 插入 permission_rules_v2 规则
        conn = sqlite3.connect(integration_db)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps([{'field': 'owner_id', 'op': '=', 'value': 999}])]
        )
        conn.commit()
        conn.close()

        # Step 2: 执行推导
        dao = EffectiveIntentDAO(integration_db)
        pipeline = PermissionDerivationPipeline(db_path=integration_db, dao=dao)
        result = pipeline.derive(role_id=100)

        # 验证推导结果
        assert result['intent_count'] > 0
        intents = dao.list_for_role(100)
        action_names = {i['action_name'] for i in intents}
        assert 'read' in action_names
        assert 'list' in action_names

        # Step 3: 用 IntentScopeAdapter 读取
        adapter = IntentScopeAdapter(integration_db, dao=dao)
        filter_result = adapter.get_filter_for_roles(
            role_ids=[100], bo_id='product', action_name='read'
        )

        # 验证 adapter 输出可被拦截器使用
        assert filter_result is not None
        assert 'owner_id' in filter_result['cond_expr']
        assert 999 in filter_result['params']

    def test_pipeline_write_level_derives_update_action(self, integration_db):
        """推导管道对 write 级别正确派生 create/update Intent"""
        from meta.core.derivation_pipeline import PermissionDerivationPipeline
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        # 插入 write 级别规则
        conn = sqlite3.connect(integration_db)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (101, 'product', 'write', ?)",
            [json.dumps([{'field': 'owner_id', 'op': '=', 'value': 999}])]
        )
        conn.commit()
        conn.close()

        # 推导
        dao = EffectiveIntentDAO(integration_db)
        pipeline = PermissionDerivationPipeline(db_path=integration_db, dao=dao)
        pipeline.derive(role_id=101)

        # 验证 update Intent 存在且可被 adapter 读取
        adapter = IntentScopeAdapter(integration_db, dao=dao)
        update_filter = adapter.get_filter_for_roles(
            role_ids=[101], bo_id='product', action_name='update'
        )
        assert update_filter is not None
        assert 'owner_id' in update_filter['cond_expr']


# ============================================================================
# 2. CHILDREN_OF 操作符
# ============================================================================
class TestChildrenOfInAdapter:
    """IntentScopeAdapter 处理 CHILDREN_OF 操作符"""

    def test_children_of_generates_subquery(self, integration_db):
        """CHILDREN_OF 在 adapter 中生成子查询条件"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        # 插入含 CHILDREN_OF 的 Intent
        dao = EffectiveIntentDAO(integration_db)
        dao.upsert(
            role_id=200, bo_id='sub_domain', action_name='read',
            data_scope={
                'include': [{
                    'field': 'sub_domain_id',
                    'op': 'CHILDREN_OF',
                    'value': {'parent_field': 'domain_id', 'parent_value': 1}
                }],
                'exclude': [],
            },
        )

        adapter = IntentScopeAdapter(integration_db, dao=dao)
        result = adapter.get_filter_for_roles(
            role_ids=[200], bo_id='sub_domain', action_name='read'
        )

        assert result is not None
        # 应该生成 IN (SELECT ...) 子查询
        assert 'IN' in result['cond_expr'].upper()
        assert 'SELECT' in result['cond_expr'].upper()
        # 参数应包含 parent_value=1
        assert 1 in result['params']


# ============================================================================
# 3. data_scope 边界情况
# ============================================================================
class TestDataScopeBoundaries:
    """data_scope 边界情况测试"""

    def test_null_data_scope(self, integration_db):
        """data_scope = NULL → 当作空 scope 处理 (空 include = all)"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        # 直接 SQL 插入 NULL data_scope
        conn = sqlite3.connect(integration_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (300, 'product', 'read', NULL)"
        )
        conn.commit()
        conn.close()

        dao = EffectiveIntentDAO(integration_db)
        adapter = IntentScopeAdapter(integration_db, dao=dao)

        # NULL data_scope → data_scope = {} → 空 include = all
        result = adapter.get_filter_for_roles(
            role_ids=[300], bo_id='product', action_name='read'
        )
        # 空 include = all → 应该返回 1=1 而不是 None
        assert result is not None
        assert '1=1' in result['cond_expr']

    def test_empty_json_data_scope(self, integration_db):
        """data_scope = '{}' → 空 scope (include=[], exclude=[] = all)"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        conn = sqlite3.connect(integration_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (301, 'product', 'read', '{}')"
        )
        conn.commit()
        conn.close()

        dao = EffectiveIntentDAO(integration_db)
        adapter = IntentScopeAdapter(integration_db, dao=dao)

        result = adapter.get_filter_for_roles(
            role_ids=[301], bo_id='product', action_name='read'
        )
        # 空 JSON → data_scope = {} → include=[] → 1=1 (all)
        assert result is not None
        assert '1=1' in result['cond_expr']

    def test_adapter_skips_invalid_json(self, integration_db):
        """data_scope 是无效 JSON → adapter 应安全处理 (返回 None, 默认拒绝)"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        conn = sqlite3.connect(integration_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (302, 'product', 'read', 'invalid json {{{')"
        )
        conn.commit()
        conn.close()

        dao = EffectiveIntentDAO(integration_db)
        adapter = IntentScopeAdapter(integration_db, dao=dao)

        # 无效 JSON → json.loads 抛异常 → _get_filter_for_single_role 应抛异常
        # adapter 没有显式 catch, 这里期望抛 JSONDecodeError
        # (实际生产中应由推导管道保证 data_scope 一定是合法 JSON)
        with pytest.raises(json.JSONDecodeError):
            adapter.get_filter_for_roles(
                role_ids=[302], bo_id='product', action_name='read'
            )


# ============================================================================
# 4. 多 role + 跨 role exclude 语义
# ============================================================================
class TestMultiRoleExcludeSemantics:
    """多 role 场景下 exclude 的语义 (当前实现: 每个 role 独立评估)"""

    def test_role_a_exclude_does_not_block_role_b(self, integration_db):
        """role A 的 exclude 不影响 role B (当前实现: 独立评估)"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        dao = EffectiveIntentDAO(integration_db)

        # role A: include owner_id=999, exclude owner_id=999 (自相矛盾, 但用于测试)
        dao.upsert(
            role_id=400, bo_id='product', action_name='read',
            data_scope={
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [{'field': 'owner_id', 'op': '=', 'value': 999}],
            },
        )

        # role B: include owner_id=999, 无 exclude
        dao.upsert(
            role_id=401, bo_id='product', action_name='read',
            data_scope={
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [],
            },
        )

        adapter = IntentScopeAdapter(integration_db, dao=dao)

        # 两个 role 合并: 应该有过滤条件 (role A 自相矛盾, role B 允许)
        result = adapter.get_filter_for_roles(
            role_ids=[400, 401], bo_id='product', action_name='read'
        )
        assert result is not None
        # role A 的 exclude 不阻止 role B 的 include (OR 合并)
        assert 'OR' in result['cond_expr'].upper()

    def test_check_record_allowed_deny_takes_priority(self, integration_db):
        """check_record_allowed: Deny 优先 (任一 role exclude 命中即拒绝)

        [语义] (跟 EffectiveIntentChecker.check_multi_role 一致)
          1. 先检查所有 role 的 exclude (任一命中即拒绝)
          2. 再检查 include (任一匹配即允许)
        """
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        dao = EffectiveIntentDAO(integration_db)

        # role A: 空 include (all) + exclude owner_id=999
        dao.upsert(
            role_id=500, bo_id='product', action_name='read',
            data_scope={
                'include': [],
                'exclude': [{'field': 'owner_id', 'op': '=', 'value': 999}],
            },
        )

        # role B: include owner_id=999 (允许)
        dao.upsert(
            role_id=501, bo_id='product', action_name='read',
            data_scope={
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [],
            },
        )

        adapter = IntentScopeAdapter(integration_db, dao=dao)

        # product 1 owner_id=999
        # role A: exclude 命中 → Deny 优先 → 拒绝
        # role B: include 命中 → 允许 (但被 A 的 exclude 否决)
        result = adapter.check_record_allowed(
            role_ids=[500, 501], bo_id='product',
            action_name='read', record_id=1, user_id=123,
        )
        # Deny 优先: role A 的 exclude 命中 → 拒绝
        assert result['allowed'] is False
        assert result['source'] == 'exclude'


# ============================================================================
# 5. stale 标记不影响拦截器读取
# ============================================================================
class TestStaleIntentStillUsable:
    """stale 标记的 Intent 仍可被拦截器读取 (设计选择)"""

    def test_stale_intent_still_returned_by_dao(self, integration_db):
        """标记为 stale 的 Intent 仍被 DAO 返回"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(integration_db)

        # 插入 Intent
        dao.upsert(
            role_id=600, bo_id='product', action_name='read',
            data_scope={'include': [], 'exclude': []},
        )

        # 标记为 stale
        affected = dao.mark_stale(600)
        assert affected == 1

        # get_for_bo_action 仍返回该 Intent
        intents = dao.get_for_bo_action(600, 'product', 'read')
        assert len(intents) == 1
        assert intents[0]['is_stale'] == 1  # 确实是 stale

    def test_stale_intent_used_by_adapter(self, integration_db):
        """adapter 使用 stale Intent (不因 stale 而跳过)"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        dao = EffectiveIntentDAO(integration_db)
        dao.upsert(
            role_id=601, bo_id='product', action_name='read',
            data_scope={'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                        'exclude': []},
        )
        dao.mark_stale(601)

        adapter = IntentScopeAdapter(integration_db, dao=dao)
        result = adapter.get_filter_for_roles(
            role_ids=[601], bo_id='product', action_name='read'
        )

        # stale Intent 仍被使用 (设计选择: stale 仅提示重推导, 不阻止使用)
        assert result is not None
        assert 'owner_id' in result['cond_expr']

    def test_clear_stale_restores_normal_state(self, integration_db):
        """clear_stale 后 Intent 恢复正常状态"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(integration_db)
        dao.upsert(
            role_id=602, bo_id='product', action_name='read',
            data_scope={'include': [], 'exclude': []},
        )
        dao.mark_stale(602)

        # clear_stale
        affected = dao.clear_stale(602)
        assert affected == 1

        intents = dao.get_for_bo_action(602, 'product', 'read')
        assert intents[0]['is_stale'] == 0
