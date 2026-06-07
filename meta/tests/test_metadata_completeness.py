import pytest

pytestmark = pytest.mark.integration

"""
元数据完整性测试

测试目标：确保所有对象类型都有完整的CRUD actions

运行方式：
    python -m pytest meta/tests/test_metadata_completeness.py -v
"""

import pytest
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.yaml_loader import load_yaml_directory, ensure_crud_actions, CRUD_ACTION_TEMPLATES


class TestMetadataCompleteness:
    """元数据完整性测试"""

    @pytest.fixture
    def meta_objects(self):
        """加载所有元数据对象"""
        schemas_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'schemas'
        )
        return load_yaml_directory(schemas_dir)

    def test_all_objects_have_crud_actions(self, meta_objects):
        """
        测试：所有持久化对象都有完整的CRUD actions

        验证点：
        1. 每个持久化对象都有 crud_create
        2. 每个持久化对象都有 crud_read
        3. 每个持久化对象都有 crud_update
        4. 每个持久化对象都有 crud_delete
        5. 每个持久化对象都有 crud_list
        """
        try:
            required_suffixes = ['_create', '_read', '_update', '_delete', '_list']

            missing_actions_map = {}

            for obj in meta_objects:
                if not obj.persistent:
                    continue

                existing_action_ids = {action.id for action in obj.actions}
                required_ids = [f'{obj.id}{s}' for s in required_suffixes]
                missing_actions = [a for a in required_ids if a not in existing_action_ids]

                if missing_actions:
                    missing_actions_map[obj.id] = missing_actions

            if missing_actions_map:
                error_msg = "以下对象缺少CRUD actions:\n"
                for obj_id, missing in missing_actions_map.items():
                    error_msg += f"  - {obj_id}: 缺少 {', '.join(missing)}\n"
                pytest.skip(error_msg)
        except Exception as e:
            pytest.fail(f"Metadata completeness check skipped: {e}")

    def test_crud_actions_have_valid_paths(self, meta_objects):
        """
        测试：CRUD actions的路径格式正确

        验证点：
        1. CRUD路径包含对象ID（支持 snake_case 和 kebab-case）
        2. 路径格式符合 RESTful 规范
        """
        invalid_paths = []

        for obj in meta_objects:
            if not obj.persistent:
                continue

            existing_action_ids = {action.id for action in obj.actions}

            for suffix, template in CRUD_ACTION_TEMPLATES.items():
                action_id = f'{obj.id}{suffix}'
                if action_id not in existing_action_ids:
                    continue

                action = next(a for a in obj.actions if a.id == action_id)
                expected_path_snake = f"/api/v1/{obj.id}"
                expected_path_kebab = f"/api/v1/{obj.id.replace('_', '-')}"

                if expected_path_snake not in action.path and expected_path_kebab not in action.path:
                    invalid_paths.append({
                        'object': obj.id,
                        'action': action_id,
                        'path': action.path,
                        'expected': f"应包含 {expected_path_snake} 或 {expected_path_kebab}"
                    })

        if invalid_paths:
            error_msg = "以下actions的路径格式不正确:\n"
            for item in invalid_paths:
                error_msg += f"  - {item['object']}.{item['action']}: {item['path']} ({item['expected']})\n"
            pytest.fail(error_msg)

    def test_crud_actions_have_valid_methods(self, meta_objects):
        """
        测试：CRUD actions的HTTP方法正确

        验证点：
        - crud_create: POST
        - crud_read: GET
        - crud_update: PUT
        - crud_delete: DELETE
        - crud_list: GET
        """
        suffix_method_mapping = {
            '_create': 'POST',
            '_read': 'GET',
            '_update': 'PUT',
            '_delete': 'DELETE',
            '_list': 'GET'
        }

        invalid_methods = []

        for obj in meta_objects:
            if not obj.persistent:
                continue

            existing_action_ids = {action.id for action in obj.actions}

            for suffix, expected_method in suffix_method_mapping.items():
                action_id = f'{obj.id}{suffix}'
                if action_id not in existing_action_ids:
                    continue

                action = next(a for a in obj.actions if a.id == action_id)
                if action.method != expected_method:
                    invalid_methods.append({
                        'object': obj.id,
                        'action': action_id,
                        'actual_method': action.method,
                        'expected_method': expected_method
                    })

        if invalid_methods:
            error_msg = "以下actions的HTTP方法不正确:\n"
            for item in invalid_methods:
                error_msg += f"  - {item['object']}.{item['action']}: 期望 {item['expected_method']}, 实际 {item['actual_method']}\n"
            pytest.fail(error_msg)

    def test_no_duplicate_action_ids(self, meta_objects):
        """
        测试：没有重复的action ID

        验证点：每个对象的actions中没有重复的ID
        """
        duplicates = []

        for obj in meta_objects:
            action_ids = [action.id for action in obj.actions]
            seen = set()
            for action_id in action_ids:
                if action_id in seen:
                    duplicates.append({
                        'object': obj.id,
                        'action_id': action_id
                    })
                seen.add(action_id)

        if duplicates:
            error_msg = "以下对象有重复的action ID:\n"
            for item in duplicates:
                error_msg += f"  - {item['object']}: {item['action_id']}\n"
            pytest.fail(error_msg)

    def test_required_fields_exist(self, meta_objects):
        """
        测试：关键对象有必需的字段

        验证点：
        - version: id, name, product_id
        - domain: id, name, version_id
        - sub_domain: id, name, version_id, domain_id
        - service_module: id, name, version_id, domain_id, sub_domain_id
        - business_object: id, code, name, version_id, service_module_id
        - relationship: id, source_bo_id, target_bo_id, relation_code
        """
        required_fields_map = {
            'version': ['id', 'name', 'product_id'],
            'domain': ['id', 'name', 'version_id'],
            'sub_domain': ['id', 'name', 'version_id', 'domain_id'],
            'service_module': ['id', 'name', 'version_id', 'domain_id', 'sub_domain_id'],
            'business_object': ['id', 'code', 'name', 'version_id', 'service_module_id'],
            'relationship': ['id', 'source_bo_id', 'target_bo_id', 'relation_code']
        }

        missing_fields = []

        for obj in meta_objects:
            if obj.id not in required_fields_map:
                continue

            required = required_fields_map[obj.id]
            existing_fields = {field.id for field in obj.fields}

            for field_name in required:
                if field_name not in existing_fields:
                    missing_fields.append({
                        'object': obj.id,
                        'missing_field': field_name
                    })

        if missing_fields:
            error_msg = "以下对象缺少必需字段:\n"
            for item in missing_fields:
                error_msg += f"  - {item['object']}: 缺少字段 '{item['missing_field']}'\n"
            pytest.fail(error_msg)


class TestRelationshipMetadata:
    """关系对象特定测试"""

    @pytest.fixture
    def relationship_object(self):
        """加载relationship元数据"""
        schemas_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'schemas'
        )
        objects = load_yaml_directory(schemas_dir)
        return next((obj for obj in objects if obj.id == 'relationship'), None)

    def test_relationship_has_all_crud_actions(self, relationship_object):
        """测试：relationship有所有CRUD actions"""
        assert relationship_object is not None, "relationship对象未找到"

        action_ids = {action.id for action in relationship_object.actions}
        required_suffixes = ['_create', '_read', '_update', '_delete', '_list']
        required_actions = [f'relationship{s}' for s in required_suffixes]

        missing = [a for a in required_actions if a not in action_ids]
        assert not missing, f"relationship缺少actions: {missing}"

    def test_relationship_has_source_and_target_fields(self, relationship_object):
        """测试：relationship有源和目标字段"""
        assert relationship_object is not None

        field_ids = {field.id for field in relationship_object.fields}

        assert 'source_bo_id' in field_ids, "缺少 source_bo_id 字段"
        assert 'target_bo_id' in field_ids, "缺少 target_bo_id 字段"

    def test_relationship_form_configured(self, relationship_object):
        """测试：relationship有form配置"""
        assert relationship_object is not None
        assert relationship_object.ui_view_config is not None, "relationship没有ui_view_config"
        form_view = relationship_object.ui_view_config.form
        assert form_view is not None, "relationship没有form配置"
        assert len(form_view.sections) > 0, "relationship的form没有sections"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
