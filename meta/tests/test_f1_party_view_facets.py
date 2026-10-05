# -*- coding: utf-8 -*-
"""F1 治理分域 · 步 2 身份锚（party）+ 双视图面不变量测试 (2026-10-05)

依据: docs/superpowers/specs/2026-10-04-f1-governance-domain-design.md
      (§3.1 写锚 / §3.2 绑定声明 / §3.5 视图分面 / §7.2 验收清单)

覆盖（面清单 / 谓词 / 抽样 / 1:1 / 写护栏 / 绑定 / 注入 / 动作策略）:
1. 面清单    : 引用 parties 的对象恰为 {party, party_archive, party_internal}
               （一 entity 写锚 + 两 view 真视图面）
2. 谓词口径  : archive 面 SQL 结构含 NULL 安全排除谓词（COALESCE … <> 'org'）;
               internal 面含 source = 'org' 谓词 —— 口径由 SQL 结构强制
3. 抽样       : 临时库真实建表 / 视图 / 部分唯一索引 → 三行数据两面对照（含空 source）
4. 1:1 强约束 : 部分唯一索引仅约束 source='org' 行; 外部空 org_id 不冲突
5. 写护栏    : 两面写入被 READ_ONLY_VIEW 拒（API 侧 400）; 基表 party 不拦
6. 绑定不变量 : 绑定只挂 internal（BO YAML dimension_bindings + 全局 applies_to 双声明）;
               基表 / archive 面无绑定
7. 注入不变量 : org 维度条件仅注入 internal; 基表 / archive 永不注入
8. 动作策略  : 基表仅写动作（create/update/delete）; 两面仅读动作（read/list）§7.1-4

测试隔离:
- temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db
- DML 走 ds.insert API; 本文件不出现裸写语句（conftest raw-SQL 守卫）
"""
import os
import sqlite3
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

PARTY_IDS = ('party', 'party_archive', 'party_internal')

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _scan_schema_references():
    """扫描 meta/schemas/*.yaml, 返回引用 parties 的对象 {id: raw_dict}"""
    import yaml
    hits = {}
    for fname in sorted(os.listdir(_SCHEMA_DIR)):
        if not fname.endswith('.yaml'):
            continue
        with open(os.path.join(_SCHEMA_DIR, fname), 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            continue
        if data.get('table_name') == 'parties' or \
                'FROM parties' in (data.get('view_definition') or ''):
            hits[data.get('id')] = data
    return hits


def _load_raw(bo_id):
    import yaml
    with open(os.path.join(_SCHEMA_DIR, bo_id + '.yaml'), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _bare_manage_service():
    """裸实例: 仅验证只读护栏分支（拒写发生在触碰 data_source 之前）"""
    from meta.services.manage_service import ManageService
    return ManageService.__new__(ManageService)


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture(autouse=True)
def _fresh_dim_loader():
    """强制维度映射 loader 重读真实 YAML（防跨测试缓存污染）"""
    from meta.core.dimension_object_mapping_loader import (
        get_dimension_object_mapping_loader,
    )
    loader = get_dimension_object_mapping_loader()
    loader._config = None
    loader._config_time = 0
    loader._load_failed = False
    yield


@pytest.fixture()
def party_objs():
    """加载三个真实 YAML 并注册 registry（teardown 仅清理本次新增项）"""
    from meta.core.models import registry
    from meta.core.table_name_validator import invalidate_cache
    from meta.core.yaml_loader import load_yaml_file

    objs = []
    for bo_id in PARTY_IDS:
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, bo_id + '.yaml'))
        assert obj is not None, 'YAML 加载失败: %s' % bo_id
        objs.append(obj)

    added = []
    for obj in objs:
        if registry.get(obj.id) is None:
            registry.register(obj)
            added.append(obj.id)
    invalidate_cache()

    yield objs

    for bo_id in added:
        registry._objects.pop(bo_id, None)
    invalidate_cache()


@pytest.fixture()
def facets_env(tmp_path, party_objs):
    """临时 SQLite 库: sync_schema_from_meta 真实建表 / 视图 / 部分唯一索引"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta

    ds = get_data_source("sqlite", database=str(tmp_path / 'party_facets.db'))
    sync_schema_from_meta(ds, list(party_objs))
    yield ds
    _clear_data_source_cache_for_testing()


@pytest.fixture()
def scope_ds():
    """org 树临时库（注入测试用: 1→2→3 / 1→4→5）"""
    from meta.tests.factories._dimension_scope_engine_helpers import (
        make_dim_scope_engine_ds, seed_org_tree,
    )
    gen = make_dim_scope_engine_ds()
    ds = next(gen)
    seed_org_tree(ds)
    yield ds


# ────────────────────────────────────────
# 1. 面清单 + 类型（§3.5）
# ────────────────────────────────────────
class TestFaceManifest:
    def test_referencing_objects_are_exactly_three(self):
        assert set(_scan_schema_references().keys()) == set(PARTY_IDS)

    def test_one_entity_two_views(self):
        refs = _scan_schema_references()
        assert refs['party'].get('object_type', 'entity') == 'entity'
        assert refs['party_archive'].get('object_type') == 'view'
        assert refs['party_internal'].get('object_type') == 'view'


# ────────────────────────────────────────
# 2. 谓词口径（口径由 SQL 结构强制）
# ────────────────────────────────────────
class TestViewPredicates:
    def test_archive_excludes_internal_rows(self):
        vd = _scan_schema_references()['party_archive'].get('view_definition') or ''
        assert "COALESCE(source, '') <> 'org'" in vd

    def test_internal_keeps_only_org_rows(self):
        vd = _scan_schema_references()['party_internal'].get('view_definition') or ''
        assert "source = 'org'" in vd


# ────────────────────────────────────────
# 3+4. 真实建表抽样 + 1:1 强约束（§3.1）
# ────────────────────────────────────────
class TestSamplingRealSchema:
    def test_schema_objects_created(self, facets_env):
        rows = facets_env.execute(
            "SELECT type, name FROM sqlite_master WHERE name IN "
            "('parties', 'party_archive', 'party_internal')"
        ).fetchall()
        kinds = {r[1]: r[0] for r in rows}
        assert kinds.get('parties') == 'table'
        assert kinds.get('party_archive') == 'view'
        assert kinds.get('party_internal') == 'view'

    def test_partial_unique_index_ddl(self, facets_env):
        row = facets_env.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND name='idx_party_org_unique'"
        ).fetchone()
        assert row is not None
        assert "WHERE source = 'org'" in row[0]

    def test_sampling_two_facets(self, facets_env):
        ds = facets_env
        ds.insert("parties", {"id": 1, "name": "外部供应商A", "code": "PATY-00000001",
                              "party_type": "organization"})
        ds.insert("parties", {"id": 2, "name": "个人B", "code": "PATY-00000002",
                              "party_type": "person", "source": None})
        ds.insert("parties", {"id": 3, "name": "总部", "code": "PATY-00000003",
                              "party_type": "organization",
                              "source": "org", "org_id": 1})

        archive_ids = {r[0] for r in ds.execute(
            "SELECT id FROM party_archive ORDER BY id").fetchall()}
        assert archive_ids == {1, 2}

        internal_rows = ds.execute(
            "SELECT id, source FROM party_internal").fetchall()
        assert {r[0] for r in internal_rows} == {3}
        assert all(r[1] == 'org' for r in internal_rows)


class TestOrgOneToOneConstraint:
    def test_duplicate_internal_org_rejected(self, facets_env):
        ds = facets_env
        ds.insert("parties", {"id": 10, "name": "总部A", "code": "PATY-00000010",
                              "party_type": "organization",
                              "source": "org", "org_id": 1})
        with pytest.raises(sqlite3.IntegrityError):
            ds.insert("parties", {"id": 11, "name": "总部A重复", "code": "PATY-00000011",
                                  "party_type": "organization",
                                  "source": "org", "org_id": 1})

    def test_external_null_not_conflicting(self, facets_env):
        ds = facets_env
        ds.insert("parties", {"id": 12, "name": "外部C", "code": "PATY-00000012",
                              "party_type": "organization"})
        ds.insert("parties", {"id": 13, "name": "外部D", "code": "PATY-00000013",
                              "party_type": "organization"})
        count = ds.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
        assert count == 2


# ────────────────────────────────────────
# 5. 写护栏（真视图只读 → API 400）
# ────────────────────────────────────────
class TestWriteGuardFacets:
    def test_base_table_not_blocked(self, party_objs):
        party = next(o for o in party_objs if o.id == 'party')
        assert _bare_manage_service()._reject_if_readonly_view(party) is None

    @pytest.mark.parametrize('bo_id', ['party_archive', 'party_internal'])
    def test_view_facets_reject_write(self, party_objs, bo_id):
        from meta.services.manage_service import (
            CreateRequest, UpdateRequest, DeleteRequest,
        )
        svc = _bare_manage_service()
        results = [
            svc.create(CreateRequest(object_type=bo_id, data={'name': 'x'})),
            svc.update(UpdateRequest(object_type=bo_id, id=1, data={'name': 'y'})),
            svc.delete(DeleteRequest(object_type=bo_id, id=1)),
        ]
        for r in results:
            assert r.success is False
            assert r.error == 'READ_ONLY_VIEW'


# ────────────────────────────────────────
# 6. 绑定不变量（§3.2 双声明）
# ────────────────────────────────────────
class TestBindingInvariants:
    def test_bo_yaml_bindings_only_on_internal(self):
        assert _load_raw('party').get('dimension_bindings') in (None, [])
        assert _load_raw('party_archive').get('dimension_bindings') in (None, [])
        assert _load_raw('party_internal').get('dimension_bindings') == [
            {'dimension': 'org', 'field': 'org_id'},
        ]

    def test_global_mapping_registers_internal_only(self):
        raw = _load_raw('dimension_object_mapping')
        org = next(m for m in raw.get('dimension_object_mappings', [])
                   if m.get('dimension_code') == 'org')
        assert org.get('applies_to') == [
            {'bo': 'party_internal', 'field': 'org_id', 'filter_type': 'direct'},
        ]


# ────────────────────────────────────────
# 7. 注入不变量（查询管线按 BO id 注入）
# ────────────────────────────────────────
class TestOrgDimensionInjection:
    def test_injection_only_on_internal(self, scope_ds):
        import unittest.mock as mock
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        from meta.tests.factories._spec20_bizkey_helpers import add_scope

        engine = DimensionScopeEngine(scope_ds)
        add_scope(scope_ds, 1, 'org', [1])

        with mock.patch.object(engine, '_get_all_resource_types',
                               return_value=['party', 'party_archive',
                                             'party_internal']):
            conditions = engine.derive_data_conditions(1)

        assert conditions.get('party_internal') == 'org_id IN (1,2,3,4,5)'
        assert 'party' not in conditions
        assert 'party_archive' not in conditions


# ────────────────────────────────────────
# 8. 动作策略（§7.1-4 auto_crud 仅供写）
# ────────────────────────────────────────
class TestFrameActions:
    def test_base_table_write_actions_only(self, party_objs):
        obj = next(o for o in party_objs if o.id == 'party')
        assert {a.id for a in obj.actions} == {
            'party_create', 'party_update', 'party_delete',
        }

    @pytest.mark.parametrize('bo_id,expected', [
        ('party_archive', {'party_archive_read', 'party_archive_list'}),
        ('party_internal', {'party_internal_read', 'party_internal_list'}),
    ])
    def test_facets_read_actions_only(self, party_objs, bo_id, expected):
        obj = next(o for o in party_objs if o.id == bo_id)
        assert {a.id for a in obj.actions} == expected

    @pytest.mark.parametrize('bo_id', ['party', 'party_archive', 'party_internal'])
    def test_auto_crud_declared_false(self, bo_id):
        """§7.1-4: YAML 声明 auto_crud: false（与 audit_log.yaml 既有惯例一致）。

        注: 框架 ensure_crud_actions 按「已声明任一 {id}_* 动作则跳过」短路，
        auto_crud 键为声明性意图（parse_import_export_config 暂未消费该键）；
        行为侧由上方动作集合断言兜底（未发生自动补全）。
        """
        ie = _load_raw(bo_id).get('import_export') or {}
        assert ie.get('auto_crud') is False