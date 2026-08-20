# -*- coding: utf-8 -*-
"""
[P2-B7 2026-07-26] 菜单反向推导 (FR-011) 单元测试

测试范围:
  1. _load_role_menus: 从 role_menu_permissions 加载 menu_code 列表
  2. _derive_menus_from_dimensions: BO intents → 菜单列表
  3. _derive_intents_from_menus: 菜单 bo_bindings → BO read intents
  4. _suggest_menus_for_intents: 反向建议应授权的菜单

[FR-011 设计]
  Step 5: 维度→菜单推导 (基于 BO intents 推导角色应该看到的菜单)
  Step 6: 菜单→BO actions 推导 + 反向建议
  - 菜单的 bo_bindings 字段声明关联的 BO 和 role
  - 通过菜单授权, 用户间接获得 BO 的 read 权限
  - 反向建议: 已有 BO intent 但未授权对应菜单 → 建议授权
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
def menu_test_db():
    """创建含 menus + role_menu_permissions 表的测试 DB"""
    tmp_dir = tempfile.mkdtemp(prefix='menu_test_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_code VARCHAR(200) UNIQUE NOT NULL,
            menu_name VARCHAR(200),
            bo_bindings TEXT,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE role_menu_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            menu_code VARCHAR(200) NOT NULL,
            UNIQUE (role_id, menu_code)
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

        -- 测试菜单数据
        INSERT INTO menus (menu_code, menu_name, bo_bindings, sort_order) VALUES
            ('product_management', '产品管理',
             '[{"bo_id":"product","role":"primary","include_actions":["read","list","export"]}]', 1),
            ('sub_domain_management', '子领域管理',
             '[{"bo_id":"sub_domain","role":"primary","include_actions":["read","list","export","create","update"]}]', 2),
            ('multi_bo_menu', '多对象菜单',
             '[{"bo_id":"domain","role":"primary"},{"bo_id":"sub_domain","role":"secondary"}]', 3),
            ('inactive_menu', '已停用菜单',
             '[{"bo_id":"version"}]', 4);

        -- 停用 inactive_menu
        UPDATE menus SET is_active = 0 WHERE menu_code = 'inactive_menu';

        -- 角色 100 已授权 product_management + sub_domain_management
        INSERT INTO role_menu_permissions (role_id, menu_code) VALUES
            (100, 'product_management'),
            (100, 'sub_domain_management');
    ''')
    conn.commit()
    conn.close()
    return db_path


class TestLoadRoleMenus:
    """_load_role_menus: 加载角色已授权菜单"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, menu_test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = menu_test_db
        self.dao = EffectiveIntentDAO(menu_test_db)
        self.pipeline = PermissionDerivationPipeline(db_path=menu_test_db, dao=self.dao)

    def test_load_role_menus_returns_authorized(self):
        """加载 role 100 已授权菜单列表"""
        menus = self.pipeline._load_role_menus(100)
        assert len(menus) == 2
        assert 'product_management' in menus
        assert 'sub_domain_management' in menus

    def test_load_role_menus_empty_for_no_permission(self):
        """无菜单授权的角色返回空列表"""
        menus = self.pipeline._load_role_menus(999)
        assert menus == []

    def test_load_role_menus_table_not_exists_returns_empty(self):
        """role_menu_permissions 表不存在时返回空"""
        # 用临时 DB (无该表)
        tmp_dir = tempfile.mkdtemp(prefix='no_table_')
        empty_db = os.path.join(tmp_dir, 'test.db')
        conn = sqlite3.connect(empty_db)
        conn.execute('CREATE TABLE permission_rules_v2 (id INTEGER PRIMARY KEY)')
        conn.commit()
        conn.close()

        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline
        dao = EffectiveIntentDAO(empty_db)
        pipeline = PermissionDerivationPipeline(db_path=empty_db, dao=dao)

        menus = pipeline._load_role_menus(100)
        assert menus == []


class TestDeriveMenusFromDimensions:
    """_derive_menus_from_dimensions: BO intents → 菜单列表"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, menu_test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = menu_test_db
        self.dao = EffectiveIntentDAO(menu_test_db)
        self.pipeline = PermissionDerivationPipeline(db_path=menu_test_db, dao=self.dao)

    def test_derive_menus_from_sub_domain_intent(self):
        """有 sub_domain intent → 推导出 sub_domain_management + multi_bo_menu"""
        expanded = [
            {'bo_id': 'sub_domain', 'action_name': 'read', 'data_scope': {'include': [], 'exclude': []}},
        ]
        menus = self.pipeline._derive_menus_from_dimensions(expanded)
        # 应包含 sub_domain_management (主绑定)
        # 和 multi_bo_menu (secondary 绑定 sub_domain)
        assert 'sub_domain_management' in menus
        assert 'multi_bo_menu' in menus

    def test_derive_menus_from_product_intent(self):
        """有 product intent → 推导出 product_management"""
        expanded = [
            {'bo_id': 'product', 'action_name': 'read', 'data_scope': {'include': [], 'exclude': []}},
        ]
        menus = self.pipeline._derive_menus_from_dimensions(expanded)
        assert 'product_management' in menus

    def test_derive_menus_excludes_inactive(self):
        """已停用菜单 (is_active=0) 不在推导结果中"""
        expanded = [
            {'bo_id': 'version', 'action_name': 'read', 'data_scope': {'include': [], 'exclude': []}},
        ]
        menus = self.pipeline._derive_menus_from_dimensions(expanded)
        # inactive_menu 应被排除
        assert 'inactive_menu' not in menus

    def test_derive_menus_empty_expanded(self):
        """空 expanded 返回空菜单列表"""
        assert self.pipeline._derive_menus_from_dimensions([]) == []


class TestDeriveIntentsFromMenus:
    """_derive_intents_from_menus: 菜单 bo_bindings → BO intents"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, menu_test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = menu_test_db
        self.dao = EffectiveIntentDAO(menu_test_db)
        self.pipeline = PermissionDerivationPipeline(db_path=menu_test_db, dao=self.dao)

    def test_derive_intents_from_product_menu(self):
        """从 product_management 菜单推导 BO read intents"""
        menus = ['product_management']
        intents = self.pipeline._derive_intents_from_menus(menus)

        # 应含 product 的 read+list+export (include_actions)
        bo_actions = {(i['bo_id'], i['action_name']) for i in intents}
        assert ('product', 'read') in bo_actions
        assert ('product', 'list') in bo_actions
        assert ('product', 'export') in bo_actions

    def test_derive_intents_source_is_menu(self):
        """菜单推导的 intent source='menu'"""
        menus = ['product_management']
        intents = self.pipeline._derive_intents_from_menus(menus)
        for intent in intents:
            assert intent['source'] == 'menu'

    def test_derive_intents_data_scope_empty(self):
        """菜单推导的 intent data_scope = 空 include (全允许)"""
        menus = ['product_management']
        intents = self.pipeline._derive_intents_from_menus(menus)
        for intent in intents:
            scope = intent['data_scope']
            assert scope['include'] == []  # 空 = all
            assert scope['exclude'] == []

    def test_derive_intents_multi_bo_menu(self):
        """多 BO 菜单 (multi_bo_menu) 推导多个 BO 的 intents"""
        menus = ['multi_bo_menu']
        intents = self.pipeline._derive_intents_from_menus(menus)
        # multi_bo_menu 绑定 domain + sub_domain, 但无 include_actions → 用默认
        bo_ids = {i['bo_id'] for i in intents}
        assert 'domain' in bo_ids
        assert 'sub_domain' in bo_ids

    def test_derive_intents_dedup(self):
        """同一 (bo_id, action_name) 不重复"""
        # 两个菜单都绑定 sub_domain → sub_domain:read 不重复
        menus = ['sub_domain_management', 'multi_bo_menu']
        intents = self.pipeline._derive_intents_from_menus(menus)

        # sub_domain:read 应只有 1 个
        sub_domain_read = [
            i for i in intents
            if i['bo_id'] == 'sub_domain' and i['action_name'] == 'read'
        ]
        assert len(sub_domain_read) == 1


class TestSuggestMenusForIntents:
    """_suggest_menus_for_intents: 反向建议应授权的菜单"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, menu_test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = menu_test_db
        self.dao = EffectiveIntentDAO(menu_test_db)
        self.pipeline = PermissionDerivationPipeline(db_path=menu_test_db, dao=self.dao)

    def test_suggest_menus_for_sub_domain_intent(self):
        """有 sub_domain intent 但未授权 sub_domain_management → 建议"""
        expanded = [
            {'bo_id': 'sub_domain', 'action_name': 'read', 'data_scope': {'include': [], 'exclude': []}},
        ]
        current_menus = []  # 未授权任何菜单
        suggestions = self.pipeline._suggest_menus_for_intents(expanded, current_menus)

        # 应建议 sub_domain_management + multi_bo_menu
        assert 'sub_domain_management' in suggestions
        assert 'multi_bo_menu' in suggestions

    def test_suggest_excludes_already_authorized(self):
        """已授权的菜单不在建议中"""
        expanded = [
            {'bo_id': 'sub_domain', 'action_name': 'read', 'data_scope': {'include': [], 'exclude': []}},
            {'bo_id': 'product', 'action_name': 'read', 'data_scope': {'include': [], 'exclude': []}},
        ]
        current_menus = ['sub_domain_management', 'product_management']
        suggestions = self.pipeline._suggest_menus_for_intents(expanded, current_menus)

        # 已授权的不应在建议中
        assert 'sub_domain_management' not in suggestions
        assert 'product_management' not in suggestions
        # 但 multi_bo_menu (绑定 sub_domain) 应被建议
        assert 'multi_bo_menu' in suggestions

    def test_suggest_empty_expanded(self):
        """空 expanded 返回空建议"""
        assert self.pipeline._suggest_menus_for_intents([], []) == []


class TestDeriveWithMenus:
    """derive() 集成测试: 含菜单推导的完整流程"""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, menu_test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.derivation_pipeline import PermissionDerivationPipeline

        self.db_path = menu_test_db
        self.dao = EffectiveIntentDAO(menu_test_db)
        self.pipeline = PermissionDerivationPipeline(db_path=menu_test_db, dao=self.dao)

    def test_derive_returns_derived_menus(self):
        """derive() 返回 derived_menus 列表"""
        # 插入 permission_rule (sub_domain read)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (200, 'sub_domain', 'read', ?)",
            [json.dumps([])]
        )
        conn.commit()
        conn.close()

        result = self.pipeline.derive(role_id=200)

        # derived_menus 应包含绑定 sub_domain 的菜单
        assert 'derived_menus' in result
        assert isinstance(result['derived_menus'], list)
        assert 'sub_domain_management' in result['derived_menus']

    def test_derive_returns_reverse_suggestions(self):
        """derive() 返回 reverse_suggestions 列表"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (201, 'sub_domain', 'read', ?)",
            [json.dumps([])]
        )
        conn.commit()
        conn.close()

        result = self.pipeline.derive(role_id=201)

        # reverse_suggestions 应包含未授权但应该有的菜单
        assert 'reverse_suggestions' in result
        assert isinstance(result['reverse_suggestions'], list)
        # role 201 未授权任何菜单, 应建议 sub_domain_management
        assert 'sub_domain_management' in result['reverse_suggestions']

    def test_derive_menu_intents_added_to_effective(self):
        """derive() 后 effective_intents 含 menu source 的 intents"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (202, 'product', 'read', ?)",
            [json.dumps([])]
        )
        # role 202 已授权 product_management 菜单
        conn.execute(
            "INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (202, 'product_management')"
        )
        conn.commit()
        conn.close()

        self.pipeline.derive(role_id=202)

        intents = self.dao.list_for_role(202)
        # 应含 menu source 的 product intents
        menu_intents = [i for i in intents if i.get('source') == 'menu']
        assert len(menu_intents) >= 1
        # product:read 应在 menu_intents 中 (因为 product_management 菜单绑定 product)
        product_read = [
            i for i in menu_intents
            if i['bo_id'] == 'product' and i['action_name'] == 'read'
        ]
        assert len(product_read) >= 1
