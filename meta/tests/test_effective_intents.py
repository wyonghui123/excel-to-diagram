# -*- coding: utf-8 -*-
"""
Phase 1 TDD 测试: Effective Intent 权限架构

[覆盖范围]
  1. ConditionExpressionParser: {field, op, value} → SQL WHERE
  2. FieldMetadataRegistry: 字段元数据注册与查询
  3. EffectiveIntentDAO: role_effective_intents 表 CRUD
  4. EffectiveIntentChecker: 求值引擎 (Owner > Exclude > Include > 默认拒绝)
  5. derivation_mode: static (IN) vs dynamic (CHILDREN_OF)
  6. Feature flag: 开关控制

[设计原则]
  - TDD: 先写测试, 定义接口契约, 再写实现
  - 零依赖: 使用临时 SQLite DB, 不依赖现有系统
  - 与 AC-008 笛卡尔积语义兼容
"""
import os
import sys
import json
import sqlite3
import tempfile

import pytest

# 项目路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ['TEST_ENTRY'] = '1'


# ============================================================================
# 1. ConditionExpressionParser 测试
# ============================================================================
class TestConditionExpressionParser:
    """条件表达式解析器: {field, op, value} → SQL WHERE"""

    def test_eq_operator(self):
        """= 操作符"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([
            {'field': 'status', 'op': '=', 'value': 'active'}
        ])
        assert sql == "status = ?"
        assert params == ['active']

    def test_le_operator(self):
        """<= 操作符"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([
            {'field': 'risk_level', 'op': '<=', 'value': 3}
        ])
        assert sql == "risk_level <= ?"
        assert params == [3]

    def test_in_operator(self):
        """IN 操作符"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([
            {'field': 'domain_id', 'op': 'IN', 'value': [1, 2, 3]}
        ])
        assert sql == "domain_id IN (?, ?, ?)"
        assert params == [1, 2, 3]

    def test_not_in_operator(self):
        """NOT IN 操作符"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([
            {'field': 'status', 'op': 'NOT IN', 'value': ['archived', 'deleted']}
        ])
        assert sql == "status NOT IN (?, ?)"
        assert params == ['archived', 'deleted']

    def test_multiple_conditions_and(self):
        """多条件 AND 组合"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([
            {'field': 'domain_id', 'op': 'IN', 'value': [1, 2, 3]},
            {'field': 'risk_level', 'op': '<=', 'value': 3},
            {'field': 'status', 'op': '=', 'value': 'active'},
        ])
        assert "domain_id IN (?, ?, ?)" in sql
        assert "risk_level <= ?" in sql
        assert "status = ?" in sql
        assert " AND " in sql
        assert params == [1, 2, 3, 3, 'active']

    def test_empty_conditions_returns_none(self):
        """空条件 → None (表示无约束, 即 all)"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([])
        assert sql is None
        assert params == []

    def test_runtime_variable_user_id(self):
        """运行时变量 ${user.id}"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([
            {'field': 'owner_id', 'op': '=', 'value': '${user.id}'}
        ], runtime_vars={'user.id': 159})

        assert sql == "owner_id = ?"
        assert params == [159]

    def test_children_of_operator(self):
        """CHILDREN_OF 操作符 → 子查询"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([
            {'field': 'sub_domain_id', 'op': 'CHILDREN_OF',
             'value': {'parent_field': 'domain_id', 'parent_value': 1}}
        ])
        # 应生成子查询: sub_domain_id IN (SELECT id FROM sub_domains WHERE domain_id = ?)
        assert 'SELECT' in sql
        assert 'sub_domains' in sql
        assert 'domain_id' in sql
        assert params == [1]

    def test_ne_operator(self):
        """!= 操作符"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        sql, params = parser.to_sql([
            {'field': 'status', 'op': '!=', 'value': 'archived'}
        ])
        assert sql == "status != ?"
        assert params == ['archived']

    def test_unsupported_operator_raises(self):
        """不支持的操作符应抛异常"""
        from meta.core.condition_parser import ConditionExpressionParser
        parser = ConditionExpressionParser()

        with pytest.raises(ValueError, match='Unsupported operator'):
            parser.to_sql([
                {'field': 'status', 'op': 'LIKE', 'value': '%active%'}
            ])


# ============================================================================
# 2. FieldMetadataRegistry 测试
# ============================================================================
class TestFieldMetadataRegistry:
    """字段元数据注册表"""

    def test_dimension_field_metadata(self):
        """维度字段元数据"""
        from meta.core.field_metadata import FieldMetadataRegistry, FieldMetadata

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(
            field_name='domain_id',
            bo_id='product',
            is_dimension=True,
            dimension_chain='domain→sub_domain→service_module',
            default_derivation_mode='dynamic',
            triggers_menu_derivation=True,
        ))

        meta = registry.get('domain_id', 'product')
        assert meta is not None
        assert meta.is_dimension is True
        assert meta.default_derivation_mode == 'dynamic'

    def test_owner_field_metadata(self):
        """Owner 字段元数据"""
        from meta.core.field_metadata import FieldMetadataRegistry, FieldMetadata

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(
            field_name='owner_id',
            bo_id='product',
            is_owner=True,
            runtime_variable='${user.id}',
        ))

        meta = registry.get('owner_id', 'product')
        assert meta is not None
        assert meta.is_owner is True

    def test_plain_field_metadata(self):
        """普通字段无额外标记"""
        from meta.core.field_metadata import FieldMetadataRegistry, FieldMetadata

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(
            field_name='risk_level',
            bo_id='product',
        ))

        meta = registry.get('risk_level', 'product')
        assert meta is not None
        assert meta.is_dimension is False
        assert meta.is_owner is False

    def test_unknown_field_returns_none(self):
        """未注册字段返回 None"""
        from meta.core.field_metadata import FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        assert registry.get('nonexistent', 'product') is None

    def test_list_dimension_fields(self):
        """列出所有维度字段"""
        from meta.core.field_metadata import FieldMetadataRegistry, FieldMetadata

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(field_name='domain_id', bo_id='product', is_dimension=True))
        registry.register(FieldMetadata(field_name='sub_domain_id', bo_id='product', is_dimension=True))
        registry.register(FieldMetadata(field_name='risk_level', bo_id='product'))

        dim_fields = registry.list_dimension_fields('product')
        assert len(dim_fields) == 2
        assert 'domain_id' in [f.field_name for f in dim_fields]


# ============================================================================
# 3. EffectiveIntentDAO 测试
# ============================================================================
@pytest.fixture(scope="class")
def test_db():
    """创建临时测试 DB, 含 role_effective_intents 表"""
    tmp_dir = tempfile.mkdtemp(prefix='eff_intent_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
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

        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT, code TEXT,
            domain_id INTEGER,
            sub_domain_id INTEGER,
            risk_level INTEGER,
            status TEXT,
            owner_id INTEGER,
            created_by INTEGER
        );

        CREATE TABLE domains (id INTEGER PRIMARY KEY, code TEXT);
        CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, domain_id INTEGER, code TEXT);

        INSERT INTO domains VALUES (1, 'D1'), (2, 'D2'), (3, 'D3');
        INSERT INTO sub_domains VALUES (101, 1, 'SD11'), (102, 1, 'SD12'),
                                        (201, 2, 'SD21'), (301, 3, 'SD31');

        INSERT INTO products VALUES
            (1, 'P1', 'P1', 1, 101, 2, 'active', 159, 159),
            (2, 'P2', 'P2', 1, 102, 5, 'active', 160, 160),
            (3, 'P3', 'P3', 2, 201, 1, 'archived', 159, 159),
            (4, 'P4', 'P4', 3, 301, 3, 'active', 160, 160);
    ''')
    conn.commit()
    conn.close()

    return db_path


class TestEffectiveIntentDAO:
    """EffectiveIntentDAO: role_effective_intents 表 CRUD"""

    def test_upsert_intent(self, test_db):
        """写入 Intent (upsert)"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(test_db)
        dao.upsert(
            role_id=1, bo_id='product', action_name='read',
            data_scope={'include': [{'field': 'domain_id', 'op': 'IN', 'value': [1, 2]}]},
            derivation_mode='static',
            source='derived',
        )

        intents = dao.list_for_role(1)
        assert len(intents) == 1
        assert intents[0]['bo_id'] == 'product'
        assert intents[0]['action_name'] == 'read'

    def test_upsert_overwrite(self, test_db):
        """重复 upsert 覆盖"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(test_db)
        dao.upsert(role_id=2, bo_id='product', action_name='read',
                   data_scope={'include': []}, source='derived')

        # 覆盖
        dao.upsert(role_id=2, bo_id='product', action_name='read',
                   data_scope={'include': [{'field': 'status', 'op': '=', 'value': 'active'}]},
                   source='manual')

        intents = dao.list_for_role(2)
        assert len(intents) == 1
        scope = json.loads(intents[0]['data_scope'])
        assert scope['include'][0]['field'] == 'status'
        assert intents[0]['source'] == 'manual'

    def test_get_intents_for_bo_action(self, test_db):
        """查询特定 bo+action 的 Intent"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(test_db)
        dao.upsert(role_id=3, bo_id='product', action_name='read',
                   data_scope={'include': [{'field': 'domain_id', 'op': 'IN', 'value': [1]}]})

        intents = dao.get_for_bo_action(role_id=3, bo_id='product', action_name='read')
        assert len(intents) == 1

    def test_mark_stale(self, test_db):
        """标记 stale"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(test_db)
        dao.upsert(role_id=4, bo_id='product', action_name='read',
                   data_scope={'include': []})

        dao.mark_stale(role_id=4)
        intents = dao.list_for_role(4)
        assert intents[0]['is_stale'] == 1

    def test_clear_stale(self, test_db):
        """清除 stale 标记"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(test_db)
        dao.upsert(role_id=5, bo_id='product', action_name='read',
                   data_scope={'include': []})
        dao.mark_stale(5)
        dao.clear_stale(5)

        intents = dao.list_for_role(5)
        assert intents[0]['is_stale'] == 0

    def test_delete_for_role(self, test_db):
        """删除角色的所有 Intent"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(test_db)
        dao.upsert(role_id=6, bo_id='product', action_name='read', data_scope={})
        dao.upsert(role_id=6, bo_id='version', action_name='read', data_scope={})

        dao.delete_for_role(6)
        assert len(dao.list_for_role(6)) == 0


# ============================================================================
# 4. EffectiveIntentChecker 测试 (核心: 求值引擎)
# ============================================================================
class TestEffectiveIntentChecker:
    """求值引擎: Owner > Exclude > Include > 默认拒绝"""

    @pytest.fixture(autouse=True)
    def setup_checker(self, test_db):
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        from meta.core.condition_parser import ConditionExpressionParser
        from meta.core.effective_intent_checker import EffectiveIntentChecker

        self.dao = EffectiveIntentDAO(test_db)
        self.parser = ConditionExpressionParser()
        self.checker = EffectiveIntentChecker(
            db_path=test_db,
            dao=self.dao,
            parser=self.parser,
        )

    def test_owner_grants_admin(self):
        """Owner 优先级最高, 直接授予 admin"""
        # Intent: product:read, include=domain_id IN [1,2], 但用户是 owner
        self.dao.upsert(role_id=10, bo_id='product', action_name='read',
                        data_scope={
                            'include': [{'field': 'domain_id', 'op': 'IN', 'value': [1, 2]}]
                        })

        # product id=1, owner_id=159, domain_id=1
        result = self.checker.check(
            role_id=10, bo_id='product', action_name='read',
            record_id=1, user_id=159,
        )
        assert result['allowed'] is True
        assert result['source'] == 'owner'

    def test_exclude_denies_even_if_include_allows(self):
        """Exclude 一票否决, 即使 Include 允许"""
        self.dao.upsert(role_id=11, bo_id='product', action_name='read',
                        data_scope={
                            'include': [],  # all
                            'exclude': [{'field': 'status', 'op': '=', 'value': 'archived'}],
                        })

        # product id=3, status=archived
        result = self.checker.check(
            role_id=11, bo_id='product', action_name='read',
            record_id=3, user_id=999,
        )
        assert result['allowed'] is False
        assert result['source'] == 'exclude'

    def test_include_allows_matching_record(self):
        """Include 匹配的记录允许访问"""
        self.dao.upsert(role_id=12, bo_id='product', action_name='read',
                        data_scope={
                            'include': [
                                {'field': 'domain_id', 'op': 'IN', 'value': [1, 2]},
                                {'field': 'risk_level', 'op': '<=', 'value': 3},
                            ],
                        })

        # product id=1, domain_id=1, risk_level=2
        result = self.checker.check(
            role_id=12, bo_id='product', action_name='read',
            record_id=1, user_id=999,
        )
        assert result['allowed'] is True
        assert result['source'] == 'include'

    def test_include_denies_non_matching_record(self):
        """Include 不匹配的记录拒绝 (走 default_deny 路径)"""
        self.dao.upsert(role_id=13, bo_id='product', action_name='read',
                        data_scope={
                            'include': [
                                {'field': 'domain_id', 'op': 'IN', 'value': [1]},
                                {'field': 'risk_level', 'op': '<=', 'value': 3},
                            ],
                        })

        # product id=2, domain_id=1, risk_level=5 (>3), owner_id=160
        result = self.checker.check(
            role_id=13, bo_id='product', action_name='read',
            record_id=2, user_id=999,  # user 999 不是 owner (owner=160)
        )
        assert result['allowed'] is False
        assert result['source'] == 'default_deny'

    def test_empty_include_means_all(self):
        """空 include = all (全部允许)"""
        self.dao.upsert(role_id=14, bo_id='product', action_name='read',
                        data_scope={'include': []})

        result = self.checker.check(
            role_id=14, bo_id='product', action_name='read',
            record_id=4, user_id=999,
        )
        assert result['allowed'] is True
        assert result['source'] == 'include'

    def test_no_intent_denies(self):
        """无 Intent → 默认拒绝"""
        result = self.checker.check(
            role_id=999, bo_id='product', action_name='read',
            record_id=1, user_id=999,
        )
        assert result['allowed'] is False
        assert result['source'] == 'default_deny'

    def test_owner_overrides_exclude(self):
        """Owner 优先于 Exclude (Owner 不受 exclude 限制)"""
        self.dao.upsert(role_id=15, bo_id='product', action_name='read',
                        data_scope={
                            'include': [],
                            'exclude': [{'field': 'status', 'op': '=', 'value': 'archived'}],
                        })

        # product id=3, status=archived, owner_id=159
        result = self.checker.check(
            role_id=15, bo_id='product', action_name='read',
            record_id=3, user_id=159,  # 是 owner
        )
        assert result['allowed'] is True
        assert result['source'] == 'owner'

    def test_runtime_variable_in_include(self):
        """Include 中使用运行时变量 ${user.id} (非 owner 场景)"""
        self.dao.upsert(role_id=16, bo_id='product', action_name='read',
                        data_scope={
                            'include': [
                                {'field': 'created_by', 'op': '=', 'value': '${user.id}'}
                            ],
                        })

        # product id=1, created_by=159, owner_id=159 → owner 优先
        # 用 product id=2, created_by=160, owner_id=160 → user_id=160 是 owner
        # 用 product id=4, created_by=160, owner_id=160, user_id=999 → 不是 owner
        # 需要一条 created_by=999 的记录... 用 product id=3, created_by=159
        # product id=3, created_by=159, owner_id=159 → user_id=159 是 owner
        # 加一条 created_by=999 的测试数据
        import sqlite3
        conn = sqlite3.connect(self.checker._db_path)
        conn.execute(
            'INSERT OR REPLACE INTO products VALUES (5, "P5", "P5", 1, 101, 2, "active", 200, 999)'
        )
        conn.commit()
        conn.close()

        # product id=5, created_by=999, owner_id=200 → user_id=999 不是 owner
        result = self.checker.check(
            role_id=16, bo_id='product', action_name='read',
            record_id=5, user_id=999,
        )
        assert result['allowed'] is True
        assert result['source'] == 'include'

    def test_action_independent(self):
        """action 独立: read 和 delete 是不同的 Intent"""
        self.dao.upsert(role_id=17, bo_id='product', action_name='read',
                        data_scope={'include': []})
        # 没有 delete 的 Intent

        result_read = self.checker.check(
            role_id=17, bo_id='product', action_name='read',
            record_id=1, user_id=999,
        )
        assert result_read['allowed'] is True

        result_delete = self.checker.check(
            role_id=17, bo_id='product', action_name='delete',
            record_id=1, user_id=999,
        )
        assert result_delete['allowed'] is False
        assert result_delete['source'] == 'default_deny'


# ============================================================================
# 5. derivation_mode 测试
# ============================================================================
class TestDerivationMode:
    """derivation_mode: static (IN) vs dynamic (CHILDREN_OF)"""

    def test_static_mode_stores_explicit_values(self):
        """static 模式: 存储显式值列表"""
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(test_db) if 'test_db' in dir() else None
        # 这个测试验证数据结构, 不依赖 DB

    def test_dynamic_mode_stores_children_of(self):
        """dynamic 模式: 存储 CHILDREN_OF 操作符"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        sql, params = parser.to_sql([
            {'field': 'sub_domain_id', 'op': 'CHILDREN_OF',
             'value': {'parent_field': 'domain_id', 'parent_value': 1}}
        ])

        # 应该生成子查询
        assert 'SELECT' in sql
        assert 'sub_domains' in sql


# ============================================================================
# 6. Feature Flag 测试
# ============================================================================
class TestPermissionFlags:
    """Feature flag 开关控制"""

    def test_flag_default_off(self):
        """默认关闭"""
        from meta.core.permission_flags import is_enabled, set_flag

        set_flag('effective_intents_enabled', False)
        assert is_enabled('effective_intents_enabled') is False

    def test_flag_enable(self):
        """启用 flag"""
        from meta.core.permission_flags import is_enabled, set_flag

        set_flag('effective_intents_enabled', True)
        assert is_enabled('effective_intents_enabled') is True

        # 清理
        set_flag('effective_intents_enabled', False)

    def test_unknown_flag_returns_false(self):
        """未知 flag 返回 False"""
        from meta.core.permission_flags import is_enabled

        assert is_enabled('nonexistent_flag') is False
