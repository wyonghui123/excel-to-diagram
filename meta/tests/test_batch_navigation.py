import pytest

pytestmark = pytest.mark.integration

"""
关联导航批量查询测试套件
测试 AssociationEngine.batch_query_associations 及其子方法
"""

import pytest
from unittest.mock import Mock, MagicMock, patch


class TestBatchQueryAssociationsEntry:
    """batch_query_associations 入口方法测试"""

    def test_empty_source_ids_returns_empty(self):
        """TC-BATCH-001: 空 source_ids 返回空结果"""
        from meta.core.association_engine import AssociationEngine
        from meta.core.action_context import ActionContext

        engine = AssociationEngine()
        context = ActionContext(
            meta_object=MagicMock(),
            action='batch_query_associations',
            params={'source_ids': [], 'association_name': 'roles'},
            data_source=Mock(),
        )

        result = engine.batch_query_associations(context)

        assert result.success is True
        assert result.data.get('items', []) == []
        assert result.data.get('total', 0) == 0
        assert result.data['counts'] == {}

    def test_missing_source_ids_returns_empty(self):
        """TC-BATCH-002: 缺少 source_ids 返回空结果"""
        from meta.core.association_engine import AssociationEngine
        from meta.core.action_context import ActionContext

        engine = AssociationEngine()
        context = ActionContext(
            meta_object=MagicMock(),
            action='batch_query_associations',
            params={'association_name': 'roles'},
            data_source=Mock(),
        )

        result = engine.batch_query_associations(context)

        assert result.success is True
        assert result.data.get('items', []) == []

    @patch('meta.core.association_engine.registry')
    def test_unknown_object_type_returns_empty(self, mock_registry):
        """TC-BATCH-003: 未知对象类型返回空结果"""
        from meta.core.association_engine import AssociationEngine
        from meta.core.action_context import ActionContext

        mock_registry.get.return_value = None
        engine = AssociationEngine()
        mock_unknown = MagicMock()
        mock_unknown.id = 'unknown_type'
        context = ActionContext(
            meta_object=mock_unknown,
            action='batch_query_associations',
            params={'source_ids': [1, 2], 'association_name': 'roles'},
            data_source=Mock(),
        )

        result = engine.batch_query_associations(context)

        assert result.success is True
        assert result.data.get('items', []) == []
        assert result.data['counts'] == {}

    @patch('meta.core.association_engine.registry')
    def test_unknown_association_returns_empty(self, mock_registry):
        """TC-BATCH-004: 未知关联名返回空结果"""
        from meta.core.association_engine import AssociationEngine
        from meta.core.action_context import ActionContext

        mock_meta = MagicMock()
        mock_meta.id = 'user'
        mock_meta.associations = {'roles': {}}
        mock_registry.get.return_value = mock_meta

        engine = AssociationEngine()
        context = ActionContext(
            meta_object=mock_meta,
            action='batch_query_associations',
            params={'source_ids': [1], 'association_name': 'nonexistent'},
            data_source=Mock(),
        )

        result = engine.batch_query_associations(context)

        assert result.success is True
        assert result.data.get('items', []) == []


class TestBatchQueryM2M:
    """_batch_query_m2m 多对多批量查询测试"""

    def _make_m2m_context(self, db_connection, source_ids, assoc_meta, page=1, page_size=20, search=''):
        from meta.core.action_context import ActionContext
        return ActionContext(
            meta_object=MagicMock(),
            action='batch_query_associations',
            params={
                'source_ids': source_ids,
                'association_name': 'roles',
                'page': page,
                'page_size': page_size,
                'search': search,
            },
            data_source=db_connection,
        )

    def _create_user_group_with_roles(self, cursor, user_ids, role_ids, group_code=None):
        """创建用户组并将用户添加到组，然后给组分配角色"""
        if group_code is None:
            import uuid
            group_code = f'test_group_{uuid.uuid4().hex[:8]}'
        cursor.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)",
            (group_code, f'Test Group {group_code}'))
        group_id = cursor.lastrowid
        for user_id in user_ids:
            cursor.execute("INSERT INTO user_group_members (user_id, group_id) VALUES (?, ?)",
                (user_id, group_id))
        for role_id in role_ids:
            cursor.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)",
                (group_id, role_id))
        return group_id

    def test_m2m_single_source_id(self, db_connection, user_with_role):
        """TC-BATCH-M2M-001: 单个源ID查询关联目标"""
        from meta.core.association_engine import AssociationEngine

        user_id = user_with_role['user']['id']
        role_id = user_with_role['role']['id']
        group_id = user_with_role.get('group_id')

        if not group_id:
            pytest.skip("No group association in user_with_role")

        assoc_meta = {
            'name': 'roles',
            'type': 'many_to_many',
            'target_entity': 'role',
            'through': 'group_roles',
            'source_key': 'group_id',
            'target_key': 'role_id',
        }

        engine = AssociationEngine()
        context = self._make_m2m_context(db_connection, [group_id], assoc_meta)

        with patch.object(engine, '_resolve_assoc_meta', return_value=assoc_meta):
            with patch('meta.core.association_engine.registry') as mock_reg:
                mock_target = MagicMock()
                mock_target.table_name = 'roles'
                mock_target.fields = []
                mock_reg.get.side_effect = lambda x: mock_target if x == 'role' else MagicMock()

                result = engine._batch_query_m2m(context, assoc_meta, [group_id])

        assert result.success is True
        items = result.data.get('items', [])
        found_ids = {item['id'] for item in items}
        assert role_id in found_ids
        assert len(items) >= 1

    def test_m2m_multiple_source_ids(self, db_connection, multiple_users, multiple_roles):
        """TC-BATCH-M2M-002: 多个源ID合并查询"""
        from meta.core.association_engine import AssociationEngine

        cursor = db_connection.cursor()
        user_ids = [u['id'] for u in multiple_users[:3]]
        role_ids = [r['id'] for r in multiple_roles[:2]]
        group_id = self._create_user_group_with_roles(cursor, user_ids, role_ids)
        db_connection.commit()

        assoc_meta = {
            'name': 'roles',
            'type': 'many_to_many',
            'target_entity': 'role',
            'through': 'group_roles',
            'source_key': 'group_id',
            'target_key': 'role_id',
        }

        engine = AssociationEngine()
        context = self._make_m2m_context(db_connection, [group_id], assoc_meta)

        with patch.object(engine, '_resolve_assoc_meta', return_value=assoc_meta):
            with patch('meta.core.association_engine.registry') as mock_reg:
                mock_target = MagicMock()
                mock_target.table_name = 'roles'
                mock_target.fields = []
                mock_reg.get.side_effect = lambda x: mock_target if x == 'role' else MagicMock()

                result = engine._batch_query_m2m(context, assoc_meta, [group_id])

        assert result.success is True
        counts = result.data['counts']
        assert len(counts) > 0
        assert group_id in counts
        assert counts[group_id] >= 1

    def test_m2m_no_associations(self, db_connection, created_user):
        """TC-BATCH-M2M-003: 无关联数据时返回空列表"""
        from meta.core.association_engine import AssociationEngine

        cursor = db_connection.cursor()
        cursor.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('empty_group', 'Empty Group'))
        group_id = cursor.lastrowid
        db_connection.commit()

        assoc_meta = {
            'name': 'roles',
            'type': 'many_to_many',
            'target_entity': 'role',
            'through': 'group_roles',
            'source_key': 'group_id',
            'target_key': 'role_id',
        }

        engine = AssociationEngine()
        context = self._make_m2m_context(db_connection, [group_id], assoc_meta)

        with patch.object(engine, '_resolve_assoc_meta', return_value=assoc_meta):
            with patch('meta.core.association_engine.registry') as mock_reg:
                mock_target = MagicMock()
                mock_target.table_name = 'roles'
                mock_target.fields = []
                mock_reg.get.side_effect = lambda x: mock_target if x == 'role' else MagicMock()

                result = engine._batch_query_m2m(context, assoc_meta, [created_user['id']])

        assert result.success is True
        assert result.data.get('items', []) == []
        assert result.data.get('total', 0) == 0

    def test_m2m_counts_per_source(self, db_connection, multiple_users, multiple_roles):
        """TC-BATCH-M2M-004: 每个源的计数正确"""
        from meta.core.association_engine import AssociationEngine

        cursor = db_connection.cursor()
        user0 = multiple_users[0]
        user1 = multiple_users[1]

        role_ids = [r['id'] for r in multiple_roles[:2]]
        group1_roles = role_ids[:2]
        group2_roles = role_ids[:1]
        self._create_user_group_with_roles(cursor, [user0['id']], group1_roles)
        self._create_user_group_with_roles(cursor, [user1['id']], group2_roles)
        db_connection.commit()

        source_ids = [user0['id'], user1['id']]
        assoc_meta = {
            'name': 'roles', 'type': 'many_to_many', 'target_entity': 'role',
            'through': 'group_roles', 'source_key': 'group_id', 'target_key': 'role_id',
        }

        engine = AssociationEngine()
        context = self._make_m2m_context(db_connection, source_ids, assoc_meta)

        with patch.object(engine, '_resolve_assoc_meta', return_value=assoc_meta):
            with patch('meta.core.association_engine.registry') as mock_reg:
                mock_target = MagicMock()
                mock_target.table_name = 'roles'
                mock_target.fields = []
                mock_reg.get.side_effect = lambda x: mock_target if x == 'role' else MagicMock()

                result = engine._batch_query_m2m(context, assoc_meta, source_ids)

        counts = result.data['counts']
        assert counts[user0['id']] == 2
        assert counts[user1['id']] == 1


class TestBatchQueryComposition:
    """_batch_query_composition 组合关系批量查询测试"""

    def test_composition_basic(self, db_connection, created_user):
        """TC-BATCH-COMP-001: 组合关系批量查询基本功能"""
        from meta.core.association_engine import AssociationEngine

        cursor = db_connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS child_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_user_id INTEGER NOT NULL,
                name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO child_objects (parent_user_id, name) VALUES (?, ?)
        """, (created_user['id'], 'child1'))
        db_connection.commit()

        assoc_meta = {
            'name': 'children',
            'type': 'composition',
            'target_entity': 'child_obj',
            'source_key': 'parent_user_id',
        }

        engine = AssociationEngine()
        from meta.core.action_context import ActionContext
        context = ActionContext(
            meta_object=MagicMock(), action='batch_query_associations',
            params={'source_ids': [created_user['id']], 'page': 1, 'page_size': 20},
            data_source=db_connection,
        )

        with patch.object(engine, '_resolve_assoc_meta', return_value=assoc_meta):
            with patch('meta.core.association_engine.registry') as mock_reg:
                mock_target = MagicMock()
                mock_target.table_name = 'child_objects'
                mock_target.fields = []
                mock_reg.get.side_effect = lambda x: mock_target if x == 'child_obj' else MagicMock()

                result = engine._batch_query_composition(context, assoc_meta, [created_user['id']])

        assert result.success is True
        assert result.data.get('total', 0) >= 1
        assert len(result.data.get('items', [])) >= 1


class TestBOFrameworkBatchQueryIntegration:
    """BOFramework batch_query_associations 集成测试"""

    def test_bo_framework_has_batch_query_method(self):
        """TC-BATCH-INTEG-001: BOFramework 有 batch_query_associations 方法"""
        from meta.core.bo_framework import BOFramework

        bf = BOFramework()
        assert hasattr(bf, 'batch_query_associations')

    def test_batch_query_convenience_calls_engine(self, bo_framework):
        """TC-BATCH-INTEG-002: batch_query_associations 调用引擎方法"""
        result = bo_framework.batch_query_associations('user', 'roles', {
            'source_ids': [999],
            'page': 1,
            'page_size': 10
        })
        assert result is not None
