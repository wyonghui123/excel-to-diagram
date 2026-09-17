import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
StandardActionLoader 单元测试

测试 §7.11.4 标准动作加载器的核心功能：
1. load() 加载 16 个标准动作（[Spec 21 PM 反馈 2026-09-12] 从 12 扩到 16：增 unassign/associate/dissociate/grant）
2. get_suffix_map() 返回正确的 16 对映射
3. get_action_codes() 返回全部 16 个 code
4. 文件缺失时抛出 FileNotFoundError
5. auto_load 机制
6. instance_scope 字段正确加载
"""

import pytest
import sys
import os
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


class TestStandardActionLoaderLoad:

    def test_load_returns_16_actions(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        actions = StandardActionLoader.load(schemas_dir)
        assert len(actions) == 16

    def test_load_all_action_ids_present(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        expected_ids = {
            'crud_create', 'crud_read', 'crud_update', 'crud_delete', 'crud_list',
            'export', 'import', 'approve', 'search',
            'assign', 'unassign', 'associate', 'dissociate',
            'grant', 'revoke', 'manage',
        }
        actual_ids = {a.id for a in StandardActionLoader.get_actions()}
        assert actual_ids == expected_ids

    def test_load_missing_file_raises(self):
        from meta.core.standard_action_loader import StandardActionLoader
        with pytest.raises(FileNotFoundError) as exc_info:
            StandardActionLoader.load("/nonexistent/path")
        assert "标准动作声明文件缺失" in str(exc_info.value)

    def test_load_returns_list(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        result = StandardActionLoader.load(schemas_dir)
        assert isinstance(result, list)


class TestStandardActionLoaderSuffixMap:

    def test_crud_prefix_stripped(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        smap = StandardActionLoader.get_suffix_map()
        assert smap['crud_create'] == 'create'
        assert smap['crud_read'] == 'read'
        assert smap['crud_update'] == 'update'
        assert smap['crud_delete'] == 'delete'
        assert smap['crud_list'] == 'list'

    def test_non_crud_unchanged(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        smap = StandardActionLoader.get_suffix_map()
        assert smap['export'] == 'export'
        assert smap['import'] == 'import'
        assert smap['approve'] == 'approve'
        assert smap['search'] == 'search'
        assert smap['assign'] == 'assign'
        assert smap['unassign'] == 'unassign'
        assert smap['associate'] == 'associate'
        assert smap['dissociate'] == 'dissociate'
        assert smap['grant'] == 'grant'
        assert smap['revoke'] == 'revoke'
        assert smap['manage'] == 'manage'

    def test_all_16_mappings_present(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        smap = StandardActionLoader.get_suffix_map()
        assert len(smap) == 16
        assert 'crud_create' in smap
        assert 'manage' in smap


class TestStandardActionLoaderActionCodes:

    def test_contains_all_suffixes(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        codes = StandardActionLoader.get_action_codes()
        expected = {'create', 'read', 'update', 'delete', 'list',
                    'export', 'import', 'approve', 'search',
                    'assign', 'unassign', 'associate', 'dissociate',
                    'grant', 'revoke', 'manage'}
        assert codes == expected

    def test_size_is_16(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        codes = StandardActionLoader.get_action_codes()
        assert len(codes) == 16

    def test_codes_are_strings(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        codes = StandardActionLoader.get_action_codes()
        assert all(isinstance(c, str) for c in codes)


class TestStandardActionLoaderActionTypes:

    def test_crud_actions_have_type_crud(self):
        from meta.core.standard_action_loader import StandardActionLoader
        from meta.core.models import ActionType
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        for action in StandardActionLoader.get_actions():
            if action.id.startswith('crud_'):
                assert action.action_type == ActionType.CRUD

    def test_batch_actions(self):
        from meta.core.standard_action_loader import StandardActionLoader
        from meta.core.models import ActionType
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        actions = {a.id: a for a in StandardActionLoader.get_actions()}
        assert actions['export'].action_type == ActionType.BATCH
        assert actions['import'].action_type == ActionType.BATCH


class TestStandardActionLoaderInstanceScope:
    """[Spec 21 PM 反馈 2026-09-12] instance_scope 字段加载与分类

    覆盖矩阵：
      object 级动作（创建/列表/导入/搜索/管理）→ InstanceScope.OBJECT
      instance 级动作（其余 11 个）              → InstanceScope.INSTANCE
    """

    def test_object_scoped_actions(self):
        from meta.core.standard_action_loader import StandardActionLoader
        from meta.core.models import InstanceScope
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        actions = {a.id: a for a in StandardActionLoader.get_actions()}
        for action_id in ['crud_create', 'crud_list', 'import', 'search', 'manage']:
            assert actions[action_id].instance_scope == InstanceScope.OBJECT, \
                f'{action_id} 应为 object 级'

    def test_instance_scoped_actions(self):
        from meta.core.standard_action_loader import StandardActionLoader
        from meta.core.models import InstanceScope
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        actions = {a.id: a for a in StandardActionLoader.get_actions()}
        for action_id in [
            'crud_read', 'crud_update', 'crud_delete',
            'export', 'approve',
            'assign', 'unassign', 'associate', 'dissociate',
            'grant', 'revoke',
        ]:
            assert actions[action_id].instance_scope == InstanceScope.INSTANCE, \
                f'{action_id} 应为 instance 级'

    def test_instance_scope_count(self):
        """总数 16：object=5, instance=11"""
        from meta.core.standard_action_loader import StandardActionLoader
        from meta.core.models import InstanceScope
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        actions = StandardActionLoader.get_actions()
        n_object = sum(1 for a in actions if a.instance_scope == InstanceScope.OBJECT)
        n_instance = sum(1 for a in actions if a.instance_scope == InstanceScope.INSTANCE)
        assert (n_object, n_instance) == (5, 11), \
            f'应 object=5 / instance=11，实际 object={n_object} / instance={n_instance}'


class TestStandardActionLoaderAutoLoad:

    def test_get_actions_auto_loads(self):
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        actions = StandardActionLoader.get_actions()
        assert len(actions) == 16

    def test_get_suffix_map_auto_loads(self):
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        smap = StandardActionLoader.get_suffix_map()
        assert len(smap) == 16

    def test_get_action_codes_auto_loads(self):
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        codes = StandardActionLoader.get_action_codes()
        assert len(codes) == 16


class TestStandardActionLoaderMetaActionProperties:

    def test_all_actions_have_id_and_name(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        for action in StandardActionLoader.get_actions():
            assert action.id
            assert action.name

    def test_all_actions_have_method(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        for action in StandardActionLoader.get_actions():
            assert action.method in ('GET', 'POST', 'PUT', 'DELETE')

    def test_all_actions_have_instance_scope(self):
        """[Spec 21 PM 反馈 2026-09-12] 所有 action 都必须有 instance_scope"""
        from meta.core.standard_action_loader import StandardActionLoader
        from meta.core.models import InstanceScope
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        for action in StandardActionLoader.get_actions():
            assert action.instance_scope in (InstanceScope.OBJECT, InstanceScope.INSTANCE), \
                f'{action.id} instance_scope={action.instance_scope}'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
