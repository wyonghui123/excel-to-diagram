# -*- coding: utf-8 -*-
"""
[P2-B9 2026-07-26] 对象基线 OWD (FR-012) 单元测试

测试范围:
  1. _load_object_owd: 加载 object_owd 表
  2. _apply_owd_baseline: 应用 OWD 兜底 intent
  3. derive() 集成: OWD 作为最低优先级兜底
  4. 三种 visibility (private / public_read / public_read_write)

[FR-012 设计]
  OWD (Object Wide Defaults) 借鉴 Salesforce 概念:
    - private:           仅 owner 可见 (默认, 拒绝其他用户)
    - public_read:       所有用户可读 (兜底 read intent)
    - public_read_write: 所有用户可读写 (兜底 read+create+update intent)

  优先级: manual > derived > menu > owd
  当角色对某 BO 无任何配置时, 使用 OWD 作为基线.
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
def owd_test_db():
    """创建含 object_owd 表的测试 DB"""
    tmp_dir = tempfile.mkdtemp(prefix='owd_test_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE object_owd (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bo_id VARCHAR(100) NOT NULL UNIQUE,
            default_visibility VARCHAR(50) NOT NULL DEFAULT 'private',
            default_permission_level VARCHAR(50) NOT NULL DEFAULT 'none',
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE permission_rules_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            resource_type VARCHAR(200) NOT NULL,
            permission_level VARCHAR(50) DEFAULT 'read',
            include_conditions TEXT,
            exclude_conditions TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'manual'
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
            UNIQUE (role_id, bo_id, action_name)
        );

        -- 测试 OWD 配置
        INSERT INTO object_owd (bo_id, default_visibility, default_permission_level) VALUES
            ('product', 'private', 'none'),
            ('enum_type', 'public_read', 'read'),
            ('enum_value', 'public_read_write', 'write'),
            ('annotation', 'public_read', 'read'),
            ('audit_log', 'private', 'none');
    ''')
    conn.commit()
    conn.close()
    return db_path


class TestLoadObjectOwd:
    """_load_object_owd: 加载 OWD 配置"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, owd_test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = owd_test_db
        self.dao = EffectiveIntentDAO(owd_test_db)
        self.pipeline = PermissionDerivationPipeline(db_path=owd_test_db, dao=self.dao)

    def test_load_owd_returns_dict(self):
        """_load_object_owd 返回 {bo_id: {visibility, permission_level}}"""
        owd = self.pipeline._load_object_owd()
        assert isinstance(owd, dict)
        assert len(owd) >= 4  # 至少 4 个 BO

    def test_load_owd_includes_all_bos(self):
        """OWD 含所有配置的 BO"""
        owd = self.pipeline._load_object_owd()
        assert 'product' in owd
        assert 'enum_type' in owd
        assert 'enum_value' in owd

    def test_load_owd_private_for_product(self):
        """product OWD = private"""
        owd = self.pipeline._load_object_owd()
        assert owd['product']['visibility'] == 'private'
        assert owd['product']['permission_level'] == 'none'

    def test_load_owd_public_read_for_enum_type(self):
        """enum_type OWD = public_read"""
        owd = self.pipeline._load_object_owd()
        assert owd['enum_type']['visibility'] == 'public_read'

    def test_load_owd_public_read_write_for_enum_value(self):
        """enum_value OWD = public_read_write"""
        owd = self.pipeline._load_object_owd()
        assert owd['enum_value']['visibility'] == 'public_read_write'

    def test_load_owd_table_not_exists_returns_empty(self):
        """object_owd 表不存在时返回空 dict"""
        tmp_dir = tempfile.mkdtemp(prefix='no_owd_')
        empty_db = os.path.join(tmp_dir, 'test.db')
        conn = sqlite3.connect(empty_db)
        conn.execute('CREATE TABLE permission_rules_v2 (id INTEGER PRIMARY KEY)')
        conn.commit()
        conn.close()

        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline
        dao = EffectiveIntentDAO(empty_db)
        pipeline = PermissionDerivationPipeline(db_path=empty_db, dao=dao)

        owd = pipeline._load_object_owd()
        assert owd == {}


class TestApplyOwdBaseline:
    """_apply_owd_baseline: 应用 OWD 兜底"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, owd_test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = owd_test_db
        self.dao = EffectiveIntentDAO(owd_test_db)
        self.pipeline = PermissionDerivationPipeline(db_path=owd_test_db, dao=self.dao)

    def test_public_read_adds_read_intents(self):
        """public_read 添加 read+list+export intent"""
        owd = {'enum_type': {'visibility': 'public_read', 'permission_level': 'read'}}
        expanded = []

        self.pipeline._apply_owd_baseline(expanded, owd)

        # 应添加 read+list+export
        assert len(expanded) == 3
        actions = {i['action_name'] for i in expanded}
        assert 'read' in actions
        assert 'list' in actions
        assert 'export' in actions
        # source 应是 'owd'
        for i in expanded:
            assert i['source'] == 'owd'
            assert i['bo_id'] == 'enum_type'

    def test_public_read_write_adds_write_intents(self):
        """public_read_write 添加 read+list+export+create+update intent"""
        owd = {'enum_value': {'visibility': 'public_read_write', 'permission_level': 'write'}}
        expanded = []

        self.pipeline._apply_owd_baseline(expanded, owd)

        actions = {i['action_name'] for i in expanded}
        assert 'read' in actions
        assert 'create' in actions
        assert 'update' in actions
        # delete 不在 write level
        assert 'delete' not in actions

    def test_public_read_write_admin_adds_delete(self):
        """public_read_write + admin level 添加 delete"""
        owd = {'enum_value': {'visibility': 'public_read_write', 'permission_level': 'admin'}}
        expanded = []

        self.pipeline._apply_owd_baseline(expanded, owd)

        actions = {i['action_name'] for i in expanded}
        assert 'delete' in actions  # admin 含 delete

    def test_private_adds_nothing(self):
        """private 不添加兜底 intent"""
        owd = {'product': {'visibility': 'private', 'permission_level': 'none'}}
        expanded = []

        self.pipeline._apply_owd_baseline(expanded, owd)

        # private 不添加 intent
        assert len(expanded) == 0

    def test_owd_does_not_override_existing(self):
        """OWD 不覆盖已存在的 intent (优先级最低)"""
        owd = {'enum_type': {'visibility': 'public_read', 'permission_level': 'read'}}
        expanded = [
            {
                'bo_id': 'enum_type',
                'action_name': 'read',
                'data_scope': {'include': [{'field': 'id', 'op': 'IN', 'value': [1, 2]}], 'exclude': []},
                'derivation_mode': 'static',
                'source': 'derived',
            }
        ]

        self.pipeline._apply_owd_baseline(expanded, owd)

        # read intent 已存在, OWD 不重复添加
        read_intents = [i for i in expanded if i['action_name'] == 'read']
        assert len(read_intents) == 1  # 只有 derived 的
        # data_scope 应保持 derived 的 (不被 OWD 覆盖)
        assert read_intents[0]['data_scope']['include'] == [{'field': 'id', 'op': 'IN', 'value': [1, 2]}]
        # 但 list/export 应被 OWD 添加 (derived 没有)
        list_intents = [i for i in expanded if i['action_name'] == 'list']
        assert len(list_intents) == 1
        assert list_intents[0]['source'] == 'owd'

    def test_owd_data_scope_empty(self):
        """OWD intent 的 data_scope = 空 include (全允许)"""
        owd = {'enum_type': {'visibility': 'public_read', 'permission_level': 'read'}}
        expanded = []

        self.pipeline._apply_owd_baseline(expanded, owd)

        for i in expanded:
            scope = i['data_scope']
            assert scope['include'] == []  # 空 = all
            assert scope['exclude'] == []

    def test_owd_derivation_mode_static(self):
        """OWD intent 的 derivation_mode = static"""
        owd = {'enum_type': {'visibility': 'public_read', 'permission_level': 'read'}}
        expanded = []

        self.pipeline._apply_owd_baseline(expanded, owd)

        for i in expanded:
            assert i['derivation_mode'] == 'static'

    def test_empty_owd_no_change(self):
        """空 OWD 不修改 expanded"""
        expanded = []
        self.pipeline._apply_owd_baseline(expanded, {})
        assert expanded == []


class TestDeriveWithOwd:
    """derive() 集成测试: OWD 兜底生效"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, owd_test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = owd_test_db
        self.dao = EffectiveIntentDAO(owd_test_db)
        self.pipeline = PermissionDerivationPipeline(db_path=owd_test_db, dao=self.dao)

    def test_derive_applies_owd_for_unconfigured_bo(self):
        """derive() 后, 未配置的 BO (enum_type) 应有 OWD intent"""
        # 只配置 product 规则
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (300, 'product', 'read', ?)",
            [json.dumps([])]
        )
        conn.commit()
        conn.close()

        self.pipeline.derive(role_id=300)

        intents = self.dao.list_for_role(300)
        # enum_type 应有 OWD 推导的 read intent (public_read)
        enum_type_intents = [i for i in intents if i['bo_id'] == 'enum_type']
        assert len(enum_type_intents) >= 1
        # 应有 source='owd' 的 intent
        owd_intents = [i for i in enum_type_intents if i.get('source') == 'owd']
        assert len(owd_intents) >= 1

    def test_derive_private_bo_no_owd_intent(self):
        """derive() 后, private BO 不应有 OWD intent"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (301, 'product', 'read', ?)",
            [json.dumps([])]
        )
        conn.commit()
        conn.close()

        self.pipeline.derive(role_id=301)

        intents = self.dao.list_for_role(301)
        # audit_log 是 private, 不应有 OWD intent
        audit_intents = [i for i in intents if i['bo_id'] == 'audit_log']
        # 不应有 source='owd' 的 audit_log intent (private 不添加)
        owd_audit = [i for i in audit_intents if i.get('source') == 'owd']
        assert len(owd_audit) == 0
