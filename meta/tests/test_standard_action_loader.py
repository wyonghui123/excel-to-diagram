import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
StandardActionLoader 单元测试

测试 §7.11.4 标准动作加载器的核心功能：
1. load() 加载 12 个标准动作
2. get_suffix_map() 返回正确的 12 对映射
3. get_action_codes() 返回全部 12 个 code
4. 文件缺失时抛出 FileNotFoundError
5. auto_load 机制
"""

import pytest
import sys
import os
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


class TestStandardActionLoaderLoad:

    def test_load_returns_12_actions(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        actions = StandardActionLoader.load(schemas_dir)
        assert len(actions) == 12

    def test_load_all_action_ids_present(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        expected_ids = {
            'crud_create', 'crud_read', 'crud_update', 'crud_delete', 'crud_list',
            'export', 'import', 'approve', 'search',
            'assign', 'revoke', 'manage'
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
        assert smap['revoke'] == 'revoke'
        assert smap['manage'] == 'manage'

    def test_all_12_mappings_present(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        smap = StandardActionLoader.get_suffix_map()
        assert len(smap) == 12
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
                    'assign', 'revoke', 'manage'}
        assert codes == expected

    def test_size_is_12(self):
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        StandardActionLoader.load(schemas_dir)
        codes = StandardActionLoader.get_action_codes()
        assert len(codes) == 12

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


class TestStandardActionLoaderAutoLoad:

    def test_get_actions_auto_loads(self):
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        actions = StandardActionLoader.get_actions()
        assert len(actions) == 12

    def test_get_suffix_map_auto_loads(self):
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        smap = StandardActionLoader.get_suffix_map()
        assert len(smap) == 12

    def test_get_action_codes_auto_loads(self):
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        codes = StandardActionLoader.get_action_codes()
        assert len(codes) == 12


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


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
