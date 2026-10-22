import pytest

pytestmark = pytest.mark.unit

"""
后端测试套件 - YAML加载层测试
测试 meta.core.yaml_loader 模块
"""

import pytest
import os
import shutil
import tempfile
from pathlib import Path


class TestYAMLLoader:
    """YAML加载器测试"""

    def test_load_user_yaml(self):
        """TC-BE-002-01: 加载user.yaml"""
        from meta.core.models import registry

        meta = registry.get('user')

        assert meta is not None
        assert meta.name is not None

    def test_load_role_yaml(self):
        """TC-BE-002-02: 加载role.yaml"""
        from meta.core.models import registry

        meta = registry.get('role')

        assert meta is not None
        assert meta.name is not None

    def test_load_org_yaml(self):
        """TC-BE-002-03: 加载 org.yaml

        [迁移] 原 test_load_user_group_yaml：user_groups → orgs（v072），
        user_group.yaml 已删除，legacy 表由 v089 DROP。
        """
        from meta.core.models import registry

        meta = registry.get('org')

        assert meta is not None

    def test_load_permission_yaml(self):
        """TC-BE-002-04: 加载permission.yaml"""
        from meta.core.models import registry

        meta = registry.get('permission')

        assert meta is not None

    def test_load_with_fields(self):
        """TC-BE-002-11: 字段id映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert 'username' in fields
        assert 'email' in fields
        assert 'status' in fields

    def test_load_field_name_mapping(self):
        """TC-BE-002-12: 字段name映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].name == '用户名'
        assert fields['email'].name == '邮箱'

    def test_load_field_type_mapping(self):
        """TC-BE-002-13: 字段type映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].field_type.value == 'string'

    def test_load_field_db_column_mapping(self):
        """TC-BE-002-14: 字段db_column映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].db_column == 'username'
        assert fields['email'].db_column == 'email'

    def test_load_field_required_mapping(self):
        """TC-BE-002-15: 字段required映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].required == True

    def test_load_field_unique_mapping(self):
        """TC-BE-002-16: 字段unique映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].unique == True

    def test_load_field_default_mapping(self):
        """TC-BE-002-17: 字段default映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        if 'status' in fields:
            assert fields['status'] is not None


class TestYAMLLoaderAssociations:
    """YAML加载关联测试"""

    def test_load_many_to_many_association(self):
        """TC-BE-002-21: many_to_many关联"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        assert 'groups' in meta.associations

        groups = meta.associations['groups']
        assert groups.type == 'many_to_many'
        # [迁移 v072] target/through: user_group/user_group_members → org/org_members
        assert groups.target_entity == 'org'
        assert groups.through == 'org_members'

    def test_load_reference_association(self):
        """TC-BE-002-22: reference关联"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        if 'manager_id' in fields:
            assert fields['manager_id'].field_type.value == 'association'


class TestYAMLLoaderListConfig:
    """YAML加载列表配置测试"""

    def test_load_list_config(self):
        """TC-BE-002-26: list配置解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'ui_view_config') and meta.ui_view_config:
            if hasattr(meta.ui_view_config, 'list'):
                assert meta.ui_view_config.list is not None

    def test_load_list_columns(self):
        """TC-BE-002-27: list columns解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'ui_view_config') and meta.ui_view_config:
            if hasattr(meta.ui_view_config, 'list') and meta.ui_view_config.list:
                if hasattr(meta.ui_view_config.list, 'columns'):
                    assert len(meta.ui_view_config.list.columns) > 0


class TestYAMLLoaderActions:
    """YAML加载操作配置测试"""

    def test_load_actions(self):
        """TC-BE-002-28: actions配置解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        actions = {a.id: a for a in meta.actions}

        assert 'crud_create' in actions or 'user_create' in actions

    def test_load_batch_actions(self):
        """TC-BE-002-29: batch_actions解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'batch_actions') and meta.batch_actions:
            batch_actions = {a.id: a for a in meta.batch_actions}
            if 'batch_delete' in batch_actions:
                assert batch_actions['batch_delete'] is not None


class TestYAMLLoaderImportExport:
    """YAML加载导入导出配置测试"""

    def test_load_import_export_config(self):
        """TC-BE-002-30: import_export解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'import_export') and meta.import_export:
            assert meta.import_export.import_enabled == True


class TestYAMLLoaderRegistry:
    """YAML加载Registry测试"""

    def test_registry_singleton(self):
        """TC-BE-002-36: Registry单例"""
        from meta.core.models import registry

        user1 = registry.get('user')
        user2 = registry.get('user')

        assert user1 is user2

    def test_registry_get_object(self):
        """TC-BE-002-37: Registry.get"""
        from meta.core.models import registry

        user = registry.get('user')
        assert user is not None
        assert user.name is not None

    def test_registry_list_objects(self):
        """TC-BE-002-38: Registry.list_objects"""
        from meta.core.models import registry

        objects = registry.list_objects()

        assert 'user' in objects
        assert 'role' in objects
        # [迁移 v072] user_group.yaml → org.yaml；英文 'user_group' 不是
        # org 的 alias（org.yaml 只保留中文 alias「用户组」），故此处用 'org'。
        assert 'org' in objects

    def test_registry_persistent_objects(self):
        """TC-BE-002-38: Registry持久化对象"""
        from meta.core.models import registry

        if hasattr(registry, 'list_persistent_objects'):
            persistent = registry.list_persistent_objects()
            assert 'user' in persistent
            assert 'role' in persistent

    def test_registry_nonexistent_object(self):
        """TC-BE-002-38: 获取不存在的对象"""
        from meta.core.models import registry

        nonexistent = registry.get('nonexistent_object_xyz')
        assert nonexistent is None


class TestYAMLLoaderHierarchy:
    """YAML加载层级配置测试"""

    def test_load_hierarchy_config(self):
        """TC-BE-002-32: hierarchy配置解析"""
        from meta.core.models import registry

        meta = registry.get('domain')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'hierarchy') and meta.hierarchy:
            assert meta.hierarchy is not None

    def test_load_parent_key(self):
        """TC-BE-002-33: parent_key配置解析"""
        from meta.core.models import registry

        meta = registry.get('sub_domain')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'parent_key') and meta.parent_key:
            assert meta.parent_key is not None


class TestAssociationDerivation:
    """Association 推导功能测试"""

    def test_derive_parent_object(self):
        """测试 parent_object 推导"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_parent_object
        )

        data = {
            'associations': [
                {
                    'name': 'parent',
                    'type': 'composition',
                    'cardinality': 'many_to_one',
                    'target_entity': 'version'
                },
                {
                    'name': 'sub_domains',
                    'type': 'composition',
                    'cardinality': 'one_to_many',
                    'target_entity': 'sub_domain'
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_parent_object(associations)

        assert result == 'version'

    def test_derive_foreign_key_field_explicit(self):
        """测试显式 foreign_key_field"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_foreign_key_field
        )

        data = {
            'associations': [
                {
                    'name': 'parent',
                    'type': 'composition',
                    'cardinality': 'many_to_one',
                    'target_entity': 'version',
                    'foreign_key_field': 'parent_version_id'
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_foreign_key_field(associations)

        assert result == 'parent_version_id'

    def test_derive_foreign_key_field_auto(self):
        """测试自动推导 foreign_key_field"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_foreign_key_field
        )

        data = {
            'associations': [
                {
                    'name': 'parent',
                    'type': 'composition',
                    'cardinality': 'many_to_one',
                    'target_entity': 'version'
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_foreign_key_field(associations)

        assert result == 'version_id'

    def test_derive_hierarchy_fields(self):
        """测试 hierarchy_fields 推导"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_hierarchy_fields
        )

        data = {
            'associations': [
                {
                    'name': 'sub_domains',
                    'type': 'composition',
                    'cardinality': 'one_to_many',
                    'target_entity': 'sub_domain',
                    'hierarchy': True
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_hierarchy_fields(associations)

        assert result['path_field'] == 'hierarchy_path'
        assert result['depth_field'] == 'hierarchy_depth'

    def test_no_hierarchy_derivation(self):
        """测试无层级时推导"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_hierarchy_fields
        )

        data = {
            'associations': [
                {
                    'name': 'roles',
                    'type': 'association',
                    'cardinality': 'many_to_many',
                    'target_entity': 'role'
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_hierarchy_fields(associations)

        assert result['path_field'] is None
        assert result['depth_field'] is None

    def test_empty_associations(self):
        """测试空关联时推导"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_parent_object,
            derive_hierarchy_fields
        )

        data = {'associations': []}

        associations = parse_associations(data)
        assert derive_parent_object(associations) is None

        result = derive_hierarchy_fields(associations)
        assert result['path_field'] is None
        assert result['depth_field'] is None

    def test_parse_association_new_fields(self):
        """测试解析 Association 新字段"""
        from meta.core.yaml_loader import parse_association

        data = {
            'name': 'parent',
            'type': 'composition',
            'cardinality': 'many_to_one',
            'target_entity': 'version',
            'hierarchy': True,
            'foreign_key_field': 'version_id',
            'cascade_delete': True
        }

        assoc = parse_association(data)

        assert assoc.cardinality == 'many_to_one'
        assert assoc.hierarchy == True
        assert assoc.foreign_key_field == 'version_id'
        assert assoc.cascade_delete == True

    def test_parse_association_default_values(self):
        """测试 Association 默认值"""
        from meta.core.yaml_loader import parse_association

        data = {
            'name': 'roles',
            'type': 'association',
            'target_entity': 'role'
        }

        assoc = parse_association(data)

        assert assoc.cardinality == 'many_to_many'
        assert assoc.hierarchy == False
        assert assoc.foreign_key_field is None
        assert assoc.cascade_delete == False


class TestFieldTypeResolution:
    """`parse_field` 类型解析：别名映射 + 未知类型 fail-fast（2026-10-07）。

    背景：`timestamp` / `date` / `decimal` 与更早的 `number` 同属"yaml 侧既有写法
    但没登记进 `FIELD_TYPE_MAP`"，此前静默回落 STRING（金额列建为 VARCHAR）。
    """

    def test_legacy_aliases_map_to_numeric_or_datetime(self):
        from meta.core.models_enums import FieldType
        from meta.core.yaml_loader import parse_field

        cases = {
            'timestamp': FieldType.DATETIME,
            'date': FieldType.DATETIME,
            'decimal': FieldType.FLOAT,
            'number': FieldType.FLOAT,
        }
        for declared, expected in cases.items():
            f = parse_field({'id': 'x_' + declared, 'name': 'X',
                             'type': declared})
            assert f.field_type == expected, declared

    def test_varchar_with_length_maps_to_string(self):
        """raw DDL 写法 `varchar(n)` / `char(n)` 按 string 处理（legacy 方言）。"""
        from meta.core.models_enums import FieldType
        from meta.core.yaml_loader import parse_field

        for declared in ('varchar(100)', 'varchar(20)', 'char(4)'):
            f = parse_field({'id': 'x', 'name': 'X', 'type': declared})
            assert f.field_type == FieldType.STRING, declared

    def test_unknown_type_raises_not_falls_back(self):
        """拼错的类型必须报错——静默回落 STRING 正是这类缺陷的温床。"""
        from meta.core.yaml_loader import UnknownFieldTypeError, parse_field

        with pytest.raises(UnknownFieldTypeError) as exc:
            parse_field({'id': 'bad', 'name': 'X', 'type': 'strin'})
        assert 'strin' in str(exc.value)

    def test_load_yaml_file_does_not_swallow_unknown_type(self, tmp_path):
        """`load_yaml_file` 的兜底 except 不得吞掉本异常（否则对象静默消失）。"""
        from meta.core.yaml_loader import UnknownFieldTypeError, load_yaml_file

        p = tmp_path / 'bad_field_type.yaml'
        p.write_text(
            "id: bad_type_obj\n"
            "name: 坏类型\n"
            "table_name: bad_type_objs\n"
            "fields:\n"
            "  - id: x\n"
            "    name: X\n"
            "    type: strin\n",
            encoding='utf-8')

        with pytest.raises(UnknownFieldTypeError):
            load_yaml_file(str(p))


class TestObjectDefinitionFilter:
    """[2026-10-07] load_yaml_directory 只注册"对象定义"文件。

    schemas/ 目录混放三类 yaml：
      ① 对象定义（顶层有 id:）—— 注册为 MetaObject
      ② 配置字典 / 共享属性（顶层无 id:）—— 由专门消费方单独读取
      ③ `_` 前缀的内部文件（模板 / 共享片段）—— 约定为非对象定义

    原实现靠硬编码文件名黑名单（shared_properties / aspects /
    _standard_actions / _action_groups）区分，漏进黑名单的文件会被静默注册：
      · role_effective_intents.yaml —— 无 id，注册成 id='' 的幽灵对象
      · _template.yaml —— 有 id，注册成业务对象 new_object，被建表 / 建菜单 / 建权限
    改为按"顶层有无 id" + "`_` 前缀"两条语义判据后，此处守护该行为不再退化。
    """

    SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

    @staticmethod
    def _load_dir(schemas_path):
        from meta.core.yaml_loader import load_yaml_directory
        return load_yaml_directory(str(schemas_path))

    def _copy_real_schemas(self, tmp_path):
        """把真实 schemas 目录复制到 tmp，避免污染仓库。"""
        (tmp_path / "schemas").mkdir()
        for src in self.SCHEMA_DIR.glob("*.yaml"):
            shutil.copy2(src, tmp_path / "schemas" / src.name)
        return self._load_dir(tmp_path / "schemas")

    def test_real_schemas_have_no_empty_id_object(self):
        """真实 schemas 全量加载后，不得出现空 id 对象。"""
        with tempfile.TemporaryDirectory() as td:
            objs = self._copy_real_schemas(Path(td))
        ids = [o.id for o in objs]
        assert "" not in ids, "存在 id 为空的幽灵对象，说明无 'id:' 的 yaml 漏过判据"
        assert all(ids), f"存在空 id: {[i for i in ids if not i]}"

    def test_config_dict_files_are_skipped(self):
        """已知配置字典类文件不应被注册为对象。"""
        with tempfile.TemporaryDirectory() as td:
            objs = self._copy_real_schemas(Path(td))
        ids = {o.id for o in objs}
        # 这些文件的顶层是业务键而非 id，各有专门消费方
        for name in ("shared_properties", "aspects", "_standard_actions",
                     "_action_groups", "_audit_materialization",
                     "audit_log_expectations", "resource_types"):
            assert name not in ids, f"{name}.yaml 是配置字典，不应注册为对象"

    def test_template_file_is_not_registered(self):
        """_template.yaml 是给人复制的模板，不得注册成业务对象。"""
        with tempfile.TemporaryDirectory() as td:
            objs = self._copy_real_schemas(Path(td))
        ids = {o.id for o in objs}
        assert "new_object" not in ids, (
            "_template.yaml 被注册成业务对象 new_object —— 会导致 sync_schema 建表 "
            "new_objects、menu_auto_generator 建菜单、permission_sync 建 5 条权限码")

    def test_object_definitions_still_registered(self):
        """对象定义仍须正常注册（防止判据过严导致漏注册）。"""
        with tempfile.TemporaryDirectory() as td:
            objs = self._copy_real_schemas(Path(td))
        ids = {o.id for o in objs}
        for expected in ("address", "key_schema", "factor_catalog", "item"):
            assert expected in ids, f"对象 {expected} 未被注册，判据可能过严"

    def test_object_definition_with_id_is_registered(self):
        """顶层有 id: 且非 `_` 前缀的文件必须注册（判据按内容，不按疑似配置名）。"""
        with tempfile.TemporaryDirectory() as td:
            schemas = Path(td) / "schemas"
            schemas.mkdir()
            (schemas / "looks_like_config.yaml").write_text(
                "id: real_object\n"
                "name: 真实对象\n"
                "table_name: real_objects\n"
                "fields:\n"
                "  - id: code\n"
                "    name: 编码\n"
                "    type: string\n",
                encoding="utf-8")
            objs = self._load_dir(schemas)
        assert [o.id for o in objs] == ["real_object"]

    def test_underscore_prefixed_object_is_skipped(self):
        """`_` 前缀文件即使带合法 id 也不注册（模板约定优先于内容）。"""
        with tempfile.TemporaryDirectory() as td:
            schemas = Path(td) / "schemas"
            schemas.mkdir()
            (schemas / "_tpl.yaml").write_text(
                "id: should_not_register\n"
                "name: 模板\n"
                "table_name: tpl_objects\n"
                "fields:\n"
                "  - id: code\n"
                "    name: 编码\n"
                "    type: string\n",
                encoding="utf-8")
            objs = self._load_dir(schemas)
        assert objs == [], "`_` 前缀文件不应注册为对象"

    def test_yaml_without_top_level_id_is_skipped(self):
        """顶层无 id: 的 yaml 不应被注册（守护判据生效）。"""
        with tempfile.TemporaryDirectory() as td:
            schemas = Path(td) / "schemas"
            schemas.mkdir()
            (schemas / "some_dict.yaml").write_text(
                "alpha: 1\n"
                "beta: 2\n",
                encoding="utf-8")
            objs = self._load_dir(schemas)
        assert objs == [], "无顶层 id 的配置字典不应产生对象"


class TestDetailTabActionParsing:
    """详情 tab 的 action 形态解析：与 facet 同一口径。

    仅 org 的「业务伙伴关系」tab 用 dict 形态声明 create 入口（带 label/variant/
    permission）。若解析时被压平成 id/name 字符串，前端拿不到 label/permission，
    按钮静默消失。字符串形态（assign/unassign/list）必须保持原样。
    """

    def test_dict_action_is_preserved(self):
        from meta.core.yaml_loader import parse_ui_detail_tab

        tab = parse_ui_detail_tab({
            "id": "party_relations",
            "type": "association",
            "actions": [{
                "key": "create",
                "label": "新建伙伴关系",
                "variant": "primary",
                "permission": "party_relation:party_relation_create",
            }],
        })

        assert tab.actions == [{
            "key": "create",
            "label": "新建伙伴关系",
            "variant": "primary",
            "permission": "party_relation:party_relation_create",
        }]

    def test_string_actions_are_unchanged(self):
        from meta.core.yaml_loader import parse_ui_detail_tab

        tab = parse_ui_detail_tab({
            "id": "members",
            "type": "association",
            "actions": ["assign", "unassign"],
        })

        assert tab.actions == ["assign", "unassign"]
