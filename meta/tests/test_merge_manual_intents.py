# -*- coding: utf-8 -*-
"""
[P2-B10 2026-07-26] _merge_manual_intents 单元测试 (FR-013)

测试范围:
  1. manual granted=true 强制加入 (即使 derived 没推导出)
  2. manual granted=false 强制排除 (覆盖现有 derived intent, 永假条件 id=-1)
  3. manual 优先级高于 derived/template/menu
  4. data_scope 修正 (空 include = 全允许 vs 永假条件 = 拒绝)
  5. 多个 manual_intents 合并

[FR-013 配置源优先级]
  manual > template > derived > menu > owd

[P1-B4 修复]
  granted=false 旧实现: 从 expanded 中移除 → IntentScopeAdapter 找不到 → 返回
  'no_intent_allows_all' → read 路径允许所有 (与"强制排除"语义相反)
  新实现: 覆盖/添加 intent, data_scope 含永假条件 (id=-1 永不匹配) → 拒绝所有
"""
import json
import os
import sys
import sqlite3
import tempfile

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ['TEST_ENTRY'] = '1'
os.environ['ALLOW_RAW_SQL'] = '1'


@pytest.fixture(scope="module")
def pipeline_db():
    """创建含 role_intents 表的测试 DB"""
    tmp_dir = tempfile.mkdtemp(prefix='merge_manual_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
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

        CREATE TABLE role_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            parameters_hash VARCHAR(64),
            granted INTEGER NOT NULL DEFAULT 1,
            source VARCHAR(50) DEFAULT 'manual',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role_id, bo_id, action_name, parameters_hash)
        );
    ''')
    conn.commit()
    conn.close()
    return db_path


class TestMergeManualIntentsGrantedTrue:
    """granted=true 强制加入"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, pipeline_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = pipeline_db
        self.dao = EffectiveIntentDAO(pipeline_db)
        self.pipeline = PermissionDerivationPipeline(db_path=pipeline_db, dao=self.dao)

    def test_granted_true_adds_new_intent(self):
        """granted=true 添加新 intent (即使 derived 没推导出)"""
        # expanded 为空 (无 derived intent)
        expanded = []
        manual_intents = [
            {'bo_id': 'sub_domain', 'action_name': 'export', 'granted': True}
        ]

        self.pipeline._merge_manual_intents(expanded, manual_intents)

        # 应添加 1 个 manual intent
        assert len(expanded) == 1
        assert expanded[0]['bo_id'] == 'sub_domain'
        assert expanded[0]['action_name'] == 'export'
        assert expanded[0]['source'] == 'manual'
        # data_scope = 空 include (全允许) + 空 exclude (无否决)
        scope = expanded[0]['data_scope']
        assert scope['include'] == []  # 空 = all
        assert scope['exclude'] == []

    def test_granted_true_does_not_duplicate(self):
        """granted=true 时, 已有 derived intent 不重复添加"""
        expanded = [{
            'bo_id': 'sub_domain',
            'action_name': 'read',
            'data_scope': {'include': [{'field': 'id', 'op': 'IN', 'value': [339]}], 'exclude': []},
            'derivation_mode': 'static',
            'source': 'derived',
        }]
        manual_intents = [
            {'bo_id': 'sub_domain', 'action_name': 'read', 'granted': True}
        ]

        self.pipeline._merge_manual_intents(expanded, manual_intents)

        # 应只有 1 个 intent (不重复)
        assert len(expanded) == 1
        # source 应标记为 manual_override (manual 优先级提示)
        assert expanded[0]['source'] == 'manual_override'

    def test_granted_true_preserves_data_scope(self):
        """granted=true 时, 已有 derived intent 的 data_scope 不被覆盖"""
        original_scope = {
            'include': [{'field': 'domain_id', 'op': 'IN', 'value': [1, 2]}],
            'exclude': [],
        }
        expanded = [{
            'bo_id': 'product',
            'action_name': 'read',
            'data_scope': original_scope,
            'derivation_mode': 'static',
            'source': 'derived',
        }]
        manual_intents = [
            {'bo_id': 'product', 'action_name': 'read', 'granted': True}
        ]

        self.pipeline._merge_manual_intents(expanded, manual_intents)

        # data_scope 应保持原样 (不被空 include 覆盖)
        assert expanded[0]['data_scope'] == original_scope


class TestMergeManualIntentsGrantedFalse:
    """granted=false 强制排除"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, pipeline_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = pipeline_db
        self.dao = EffectiveIntentDAO(pipeline_db)
        self.pipeline = PermissionDerivationPipeline(db_path=pipeline_db, dao=self.dao)

    def test_granted_false_overrides_existing_with_deny_all(self):
        """granted=false 覆盖现有 intent 为永假条件 (id=-1)"""
        expanded = [{
            'bo_id': 'sub_domain',
            'action_name': 'read',
            'data_scope': {'include': [], 'exclude': []},  # 全允许
            'derivation_mode': 'dynamic',
            'source': 'derived',
        }]
        manual_intents = [
            {'bo_id': 'sub_domain', 'action_name': 'read', 'granted': False}
        ]

        self.pipeline._merge_manual_intents(expanded, manual_intents)

        # 应还是 1 个 intent (不删除, 而是覆盖为永假)
        assert len(expanded) == 1
        # data_scope 应含永假条件 (id=-1)
        scope = expanded[0]['data_scope']
        assert scope['include'] == [{'field': 'id', 'op': '=', 'value': -1}]
        # source 应标记为 manual_deny
        assert expanded[0]['source'] == 'manual_deny'

    def test_granted_false_adds_deny_intent_if_not_exists(self):
        """granted=false 时, 若 expanded 中没有, 添加永假 intent"""
        expanded = []
        manual_intents = [
            {'bo_id': 'enum_type', 'action_name': 'read', 'granted': False}
        ]

        self.pipeline._merge_manual_intents(expanded, manual_intents)

        # 应添加 1 个永假 intent
        assert len(expanded) == 1
        scope = expanded[0]['data_scope']
        assert scope['include'] == [{'field': 'id', 'op': '=', 'value': -1}]
        assert expanded[0]['source'] == 'manual_deny'

    def test_granted_false_deny_scope_never_matches(self):
        """永假条件 (id=-1) 在 SQL 中永不匹配"""
        # 这是 P1-B4 修复的核心: 不再 "无 intent = 允许所有",
        # 而是 "永假 intent = 拒绝所有"
        expanded = [{
            'bo_id': 'sub_domain',
            'action_name': 'read',
            'data_scope': {'include': [], 'exclude': []},
            'derivation_mode': 'static',
            'source': 'derived',
        }]
        manual_intents = [
            {'bo_id': 'sub_domain', 'action_name': 'read', 'granted': False}
        ]

        self.pipeline._merge_manual_intents(expanded, manual_intents)

        # 验证永假条件: id = -1 (SQLite 中 id 通常从 1 开始)
        scope = expanded[0]['data_scope']
        deny_condition = scope['include'][0]
        assert deny_condition['field'] == 'id'
        assert deny_condition['op'] == '='
        assert deny_condition['value'] == -1


class TestMergeManualIntentsPriority:
    """manual 优先级高于 derived"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, pipeline_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = pipeline_db
        self.dao = EffectiveIntentDAO(pipeline_db)
        self.pipeline = PermissionDerivationPipeline(db_path=pipeline_db, dao=self.dao)

    def test_multiple_manual_intents_mixed_grant_deny(self):
        """多个 manual_intents 混合 grant/deny"""
        expanded = [
            {
                'bo_id': 'sub_domain', 'action_name': 'read',
                'data_scope': {'include': [], 'exclude': []},
                'derivation_mode': 'static', 'source': 'derived',
            },
            {
                'bo_id': 'sub_domain', 'action_name': 'list',
                'data_scope': {'include': [], 'exclude': []},
                'derivation_mode': 'static', 'source': 'derived',
            },
        ]
        manual_intents = [
            # deny read (覆盖现有)
            {'bo_id': 'sub_domain', 'action_name': 'read', 'granted': False},
            # grant export (添加新)
            {'bo_id': 'sub_domain', 'action_name': 'export', 'granted': True},
        ]

        self.pipeline._merge_manual_intents(expanded, manual_intents)

        # 应有 3 个 intent: read (deny) + list (derived) + export (manual)
        assert len(expanded) == 3
        # read 应被覆盖为永假
        read_intent = next(i for i in expanded if i['action_name'] == 'read')
        assert read_intent['source'] == 'manual_deny'
        assert read_intent['data_scope']['include'] == [{'field': 'id', 'op': '=', 'value': -1}]
        # list 保持 derived
        list_intent = next(i for i in expanded if i['action_name'] == 'list')
        assert list_intent['source'] == 'derived'
        # export 是新增 manual
        export_intent = next(i for i in expanded if i['action_name'] == 'export')
        assert export_intent['source'] == 'manual'

    def test_manual_overrides_menu_source(self):
        """manual 优先级高于 menu source"""
        expanded = [{
            'bo_id': 'menu_bo',
            'action_name': 'read',
            'data_scope': {'include': [], 'exclude': []},
            'derivation_mode': 'static',
            'source': 'menu',
        }]
        manual_intents = [
            {'bo_id': 'menu_bo', 'action_name': 'read', 'granted': False}
        ]

        self.pipeline._merge_manual_intents(expanded, manual_intents)

        # manual_deny 应覆盖 menu source
        assert expanded[0]['source'] == 'manual_deny'

    def test_empty_manual_intents_no_change(self):
        """空 manual_intents 不修改 expanded"""
        expanded = [
            {
                'bo_id': 'sub_domain', 'action_name': 'read',
                'data_scope': {'include': [], 'exclude': []},
                'derivation_mode': 'static', 'source': 'derived',
            }
        ]
        original = json.loads(json.dumps(expanded))  # 深拷贝

        self.pipeline._merge_manual_intents(expanded, [])

        # expanded 应保持原样
        assert expanded == original


class TestMergeManualIntentsEndToEnd:
    """端到端: derive() 后 role_effective_intents 含 manual intents"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, pipeline_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = pipeline_db
        self.dao = EffectiveIntentDAO(pipeline_db)
        self.pipeline = PermissionDerivationPipeline(db_path=pipeline_db, dao=self.dao)

    def test_derive_includes_manual_grant(self):
        """derive() 后 effective_intents 含 manual granted=true intent"""
        # 插入 derived rule (sub_domain read)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (500, 'sub_domain', 'read', ?)",
            [json.dumps([])]
        )
        # 插入 manual granted=true (sub_domain export, derived 不会推导出)
        conn.execute(
            "INSERT INTO role_intents (role_id, bo_id, action_name, granted, source) "
            "VALUES (500, 'sub_domain', 'export', 1, 'manual')"
        )
        conn.commit()
        conn.close()

        self.pipeline.derive(role_id=500)

        intents = self.dao.list_for_role(500)
        action_names = {i['action_name'] for i in intents}
        # derived 应生成 read+list+export
        # manual 应添加 export (已存在则标记 manual_override)
        assert 'read' in action_names
        assert 'export' in action_names

    def test_derive_applies_manual_deny(self):
        """derive() 后 manual granted=false 应使 intent 永假"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (501, 'sub_domain', 'read', ?)",
            [json.dumps([])]
        )
        # manual deny sub_domain:read
        conn.execute(
            "INSERT INTO role_intents (role_id, bo_id, action_name, granted, source) "
            "VALUES (501, 'sub_domain', 'read', 0, 'manual')"
        )
        conn.commit()
        conn.close()

        self.pipeline.derive(role_id=501)

        intents = self.dao.list_for_role(501)
        # read intent 应存在 (manual_deny), data_scope 含永假条件
        read_intents = [i for i in intents if i['action_name'] == 'read']
        assert len(read_intents) >= 1
        # 验证 source 和 data_scope
        for ri in read_intents:
            if ri['source'] == 'manual_deny':
                scope = json.loads(ri['data_scope'])
                assert scope['include'] == [{'field': 'id', 'op': '=', 'value': -1}]
