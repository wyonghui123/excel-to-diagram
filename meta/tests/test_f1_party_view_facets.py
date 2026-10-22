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
5. 写护栏    : 无锚真视图（internal）写入被 READ_ONLY_VIEW 拒（API 侧 400）;
               有锚面（archive, write_anchor=party）护栏放行、转发解析到锚 §7.1-6
6. 绑定不变量 : 绑定只挂 internal（BO YAML dimension_bindings + 全局 applies_to 双声明）;
               基表 / archive 面无绑定
7. 注入不变量 : org 维度条件仅注入 internal; 基表 / archive 永不注入
8. 动作策略  : 基表仅写动作（create/update/delete）; internal 仅读（read/list）§7.1-4;
               archive 读（read/list）+ 写（create/update/delete 转发锚）
9. 枚举出口径: 视图面 party_type 枚举与默认值须与基表一致
               （2026-10-12 缺陷防线: 视图面漏声明 enum_values ⇒ 编辑态下拉零选项）
10. 恒定字段  : 谓词恒定字段须 ui.visible=false（防暴露可编辑噪声控件）;
               面级 org_id 外键须绑 ui.relation（防退化为 el-input-number 数字框）
               （2026-10-17 缺陷防线: 用户手机端实测报障）

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
    # [FK 2026-10-07] parties.org_id 新增真外键 → orgs.id；补最小父表 + 父行
    # （用例中内部行 org_id=1）
    ds.execute("CREATE TABLE IF NOT EXISTS orgs "
               "(id INTEGER PRIMARY KEY AUTOINCREMENT)")
    ds.insert("orgs", {"id": 1})
    # [2026-10-20] party_internal 谓词补齐「org 具备 legal_entity 职能」（与
    # org_legal_entity 同源）⇒ 视图依赖 org_functions；该表由 v073 迁移建、
    # 不在任何 BO YAML 中，且 SQLite 的 CREATE VIEW 不校验引用表 ⇒ 不建它
    # 查询期会报 no such table。DML 走 raw_sql_bridge（未注册进 table_name_validator）。
    from meta.tests.factories._raw_sql_bridge import insert as _raw_insert
    ds.execute(
        'CREATE TABLE IF NOT EXISTS org_functions ('
        '  id INTEGER PRIMARY KEY AUTOINCREMENT,'
        '  org_id INTEGER NOT NULL,'
        '  function_type TEXT NOT NULL,'
        '  is_primary BOOLEAN DEFAULT 0,'
        '  UNIQUE(org_id, function_type))'
    )
    _raw_insert(ds, 'org_functions',
                rows=[{'org_id': 1, 'function_type': 'legal_entity'}])
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


class TestInternalPredicateHomology:
    """[2026-10-20] party_internal 谓词与法人判据同源

    缺陷背景: 原谓词只有 source='org'，而 parties 行由镜像服务「曾经」建出且按
    不删除原则保留 ⇒ org 失去 legal_entity 职能后行仍在视图内 ⇒ 我方侧下拉出现
    「幽灵主体」，与法人域面（org_legal_entity 实时读 org_functions）口径分裂。
    修复: 谓词补 EXISTS(org_functions)，两面读同一张表、同一判据来源。

    [2026-10-21 放宽] 内部台账面判据扩为 (legal_entity, management_unit)：
    我方主体可以是法人，也可以是法人下的管理单元（BU）。法人域面**不放宽**
    （条款只能挂法人）⇒ 两面不再是同一字符串，而是「同一判据源的子集关系」：
    法人面 ⊂ 内部台账面，且内部台账面不得混入运营职能（sales/warehouse）。
    """

    def test_predicate_reads_org_functions(self):
        vd = ' '.join((_load_raw('party_internal').get('view_definition') or '').split())
        assert 'org_functions' in vd, \
            'party_internal 谓词须与法人判据同源（读职能表），否则口径会再次分裂'
        assert "'legal_entity'" in vd

    def test_predicate_is_superset_of_legal_entity_view(self):
        """内部台账面 = 主体职能集合；法人面仍只认 legal_entity（子集）"""
        internal = ' '.join(
            (_load_raw('party_internal')['view_definition'] or '').split())
        legal = ' '.join(
            (_load_raw('org_legal_entity')['view_definition'] or '').split())
        assert "f.function_type = 'legal_entity'" in legal, \
            '法人域面只认法人职能，不得放宽（条款只能挂法人）'
        assert "f.function_type IN ('legal_entity', 'management_unit')" in internal, \
            '内部台账面判据须为 BU/LE 主体职能集合'
        assert "'sales'" not in internal and "'warehouse'" not in internal, \
            '运营职能属条款/库存粒度，不是关系的一方，不得混入我方主体'

    def test_revoking_function_hides_row_without_deleting(self, facets_env):
        """撤职能 ⇒ 行退出视图，但 parties 物理行保留（不删除原则）

        存量关系仍指向该 party id，删除会破坏外键；隐藏由视图谓词完成，
        存量回显走 display_target_bo=party 兜底。
        """
        from meta.tests.factories._raw_sql_bridge import delete

        ds = facets_env
        ds.insert("parties", {"id": 3, "name": "总部", "code": "PATY-00000003",
                              "party_type": "organization",
                              "source": "org", "org_id": 1})
        assert [r[0] for r in ds.execute(
            "SELECT id FROM party_internal").fetchall()] == [3], \
            '前提：org 具备 legal_entity 职能 ⇒ 行可见'

        delete(ds, 'org_functions', org_id=1)

        assert ds.execute("SELECT id FROM party_internal").fetchall() == [], \
            '失去职能后行须退出候选面'
        assert ds.execute(
            "SELECT id FROM parties WHERE id=3").fetchall() == [(3,)], \
            '物理行必须保留（历史关系可能引用，全库 FK 均 NO ACTION）'

    def test_non_legal_org_row_never_visible(self, facets_env):
        """不具备 legal_entity 职能的 org 行（如历史残留）不得进入本面"""
        ds = facets_env
        ds.insert("orgs", {"id": 2})
        ds.insert("parties", {"id": 4, "name": "部门", "code": "PATY-00000004",
                              "party_type": "organization",
                              "source": "org", "org_id": 2})
        assert ds.execute("SELECT id FROM party_internal").fetchall() == [], \
            'org_id=2 无 any 职能行 ⇒ 本面须为空'


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
# 5. 写护栏（[write_anchor 2026-10-11] 有锚转发 / 无锚拒写 §7.1-6）
# ────────────────────────────────────────
class TestWriteGuardFacets:
    def test_base_table_not_blocked(self, party_objs):
        party = next(o for o in party_objs if o.id == 'party')
        assert _bare_manage_service()._reject_if_readonly_view(party) is None

    def test_archive_has_write_anchor_not_blocked(self, party_objs):
        """有锚面：护栏放行（写由 ActionExecutor 转发到锚 party）"""
        archive = next(o for o in party_objs if o.id == 'party_archive')
        assert getattr(archive, 'write_anchor', '') == 'party'
        assert _bare_manage_service()._reject_if_readonly_view(archive) is None

    def test_internal_view_rejects_write(self, party_objs):
        """无锚真视图：仍被 READ_ONLY_VIEW 拒（API 侧 400）"""
        from meta.services.manage_service import (
            CreateRequest, UpdateRequest, DeleteRequest,
        )
        svc = _bare_manage_service()
        results = [
            svc.create(CreateRequest(object_type='party_internal', data={'name': 'x'})),
            svc.update(UpdateRequest(object_type='party_internal', id=1, data={'name': 'y'})),
            svc.delete(DeleteRequest(object_type='party_internal', id=1)),
        ]
        for r in results:
            assert r.success is False
            assert r.error == 'READ_ONLY_VIEW'

    def test_archive_resolves_write_target_to_party(self, party_objs):
        """转发解析：archive 的写目标解析为锚 party"""
        from meta.core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)  # 解析不触 data_source
        archive = next(o for o in party_objs if o.id == 'party_archive')
        target, denied = executor._resolve_view_write_target(archive)
        assert denied is None
        assert target is not None and target.id == 'party'

    def test_internal_resolve_denies_without_anchor(self, party_objs):
        """转发解析：无锚面返回 READ_ONLY_VIEW 拒绝"""
        from meta.core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        internal = next(o for o in party_objs if o.id == 'party_internal')
        target, denied = executor._resolve_view_write_target(internal)
        assert target is None
        assert denied is not None and denied.error == 'READ_ONLY_VIEW'


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

    def test_internal_facet_read_actions_only(self, party_objs):
        """internal 无锚：动作集仅读（read / list）§7.1-4"""
        obj = next(o for o in party_objs if o.id == 'party_internal')
        assert {a.id for a in obj.actions} == {
            'party_internal_read', 'party_internal_list',
        }

    def test_archive_facet_read_write_actions(self, party_objs):
        """[write_anchor 2026-10-11] archive 有锚：读 + 写（写声明后转发锚执行）"""
        obj = next(o for o in party_objs if o.id == 'party_archive')
        assert {a.id for a in obj.actions} == {
            'party_archive_read', 'party_archive_list',
            'party_archive_create', 'party_archive_update', 'party_archive_delete',
        }

    @pytest.mark.parametrize('bo_id', ['party', 'party_archive', 'party_internal'])
    def test_auto_crud_declared_false(self, bo_id):
        """§7.1-4: YAML 声明 auto_crud: false（与 audit_log.yaml 既有惯例一致）。

        注: 框架 ensure_crud_actions 按「已声明任一 {id}_* 动作则跳过」短路，
        auto_crud 键为声明性意图（parse_import_export_config 暂未消费该键）；
        行为侧由上方动作集合断言兜底（未发生自动补全）。
        """
        ie = _load_raw(bo_id).get('import_export') or {}
        assert ie.get('auto_crud') is False


# ────────────────────────────────────────
# 9. 枚举出口径（2026-10-12 缺陷防线）
# ────────────────────────────────────────
class TestEnumParity:
    """视图面枚举 / 默认值须与基表同列出口径（防人工同步漂移）

    历史缺陷: party_archive / party_internal 的 party_type 漏声明 enum_values
    ⇒ ObjectPageShell 取到 options=空 → 字段不入 enumFieldKeys
      ⇒ 只读态退回显示原始英文、编辑态 el-select 零选项。
    同一根因的另一面: 漏声明 default ⇒ 新建表单不预填（apply-defaults 读面字段）。
    基表加枚举/默认值须同步视图面 —— 本组断言锁住该约束（纯 YAML 读取，不触库）。
    """
    VIEW_FACETS = ('party_archive', 'party_internal')
    ENUM_FIELDS = ('party_type',)

    @staticmethod
    def _field(raw, field_id):
        return next(x for x in raw['fields'] if x['id'] == field_id)

    @classmethod
    def _enum_map(cls, raw, field_id):
        f = cls._field(raw, field_id)
        return {e['value']: e['label'] for e in (f.get('enum_values') or [])}

    def test_base_table_declares_enum(self):
        """基表 party.party_type 必须声明 organization / person 两值"""
        assert set(self._enum_map(_load_raw('party'), 'party_type')) == {
            'organization', 'person',
        }

    @pytest.mark.parametrize('facet_id', VIEW_FACETS)
    def test_view_facet_enum_matches_base(self, facet_id):
        """视图面枚举须为基表枚举的子集，且界面词一致

        面可按视图谓词收窄可选值，但不允许出现基表没有的值或缺词/改词。
        """
        for field_id in self.ENUM_FIELDS:
            base = self._enum_map(_load_raw('party'), field_id)
            facet = self._enum_map(_load_raw(facet_id), field_id)
            assert facet, f'{facet_id}.{field_id} 未声明 enum_values（选项为空）'
            assert set(facet) <= set(base), (
                f'{facet_id}.{field_id} 含基表未定义的值: {sorted(set(facet) - set(base))}'
            )
            for value, label in facet.items():
                assert label == base[value], (
                    f'{facet_id}.{field_id} 界面词漂移: {value} -> {label} != {base[value]}'
                )

    def test_internal_facet_enum_is_org_only(self):
        """party_internal 谓词 source='org' ⇒ 本面恒 organization，不得列 person"""
        assert set(self._enum_map(_load_raw('party_internal'), 'party_type')) == {
            'organization',
        }

    @pytest.mark.parametrize('facet_id', VIEW_FACETS)
    def test_view_facet_default_matches_base(self, facet_id):
        """视图面默认值与基表一致（缺 default ⇒ 新建表单不预填该字段）"""
        for field_id in self.ENUM_FIELDS:
            expected = self._field(_load_raw('party'), field_id).get('default')
            actual = self._field(_load_raw(facet_id), field_id).get('default')
            assert actual == expected, (
                f'{facet_id}.{field_id} 默认值与基表 party 漂移: {actual} != {expected}'
            )


# ────────────────────────────────────────
# 10. 恒定字段出口径（2026-10-17 缺陷防线）
# ────────────────────────────────────────
class TestInvariantFieldExposure:
    """视图面「谓词恒定字段」须隐藏；真外键须绑 ui.relation

    历史缺陷: 谓词恒定字段（source/org_id）仍按普通字段渲染出可编辑控件 ——
      source 是文本框（可改且写转发后真落库，把外部记录伪装成内部记录）;
      org_id 是 el-input-number 数字框（缺 ui.relation ⇒ 退回按 type:integer
      渲染，而非走 ObjectPageShell 的 BO 选择器，见其 L246-255）。
    本组锁住: 恒空字段隐藏 + 真外键绑定 relation（纯 YAML 读取，不触库）。
    """
    # facet_id -> 该面上「谓词恒定、对用户无意义」的字段
    INVARIANT_FIELDS = {
        'party_archive': ('source', 'org_id'),   # 谓词已排除内部行 ⇒ 两列恒 NULL
        'party_internal': ('source',),           # 谓词 source='org' ⇒ 恒定值
    }
    # 面上需显示的字段 -> 必须声明 ui.relation（否则退化为数字框）
    REFERENCE_FIELDS = {
        'party_archive': (),                     # org_id 已隐藏，无需绑定
        'party_internal': ('org_id',),           # 本面非空 1:1，是真实业务数据
    }

    @staticmethod
    def _field(raw, field_id):
        return next(x for x in raw['fields'] if x['id'] == field_id)

    @pytest.mark.parametrize('facet_id,field_ids', list(INVARIANT_FIELDS.items()))
    def test_invariant_field_hidden(self, facet_id, field_ids):
        """谓词恒定字段必须 ui.visible=false（否则暴露可编辑噪声控件）"""
        raw = _load_raw(facet_id)
        for field_id in field_ids:
            ui = self._field(raw, field_id).get('ui') or {}
            assert ui.get('visible') is False, (
                f'{facet_id}.{field_id} 是谓词恒定字段，须 ui.visible=false；'
                f'当前 ui={ui} —— 暴露后用户可编辑并经 write_anchor 真实落库'
            )

    @pytest.mark.parametrize('facet_id,field_ids', list(REFERENCE_FIELDS.items()))
    def test_reference_field_binds_relation(self, facet_id, field_ids):
        """需显示的外键字段必须声明 ui.relation（否则渲染成数字框而非选择器）"""
        raw = _load_raw(facet_id)
        for field_id in field_ids:
            ui = self._field(raw, field_id).get('ui') or {}
            assert ui.get('relation'), (
                f'{facet_id}.{field_id} 是 orgs 外键，须 ui.relation 以走 BO 选择器；'
                f'当前 ui={ui} —— 缺 relation 会按 type:integer 渲染成数字输入框'
            )

    @pytest.mark.parametrize('facet_id', list(INVARIANT_FIELDS) + ['party'])
    def test_org_reference_agreement(self, facet_id):
        """org_id 与 org 的关系口径三面一致：基表有 party_to_org relation，
        且面级 org_id 的 ui.relation 指向同一目标（防关系漂移）"""
        raw = _load_raw(facet_id)
        rel = next(
            (r for r in (raw.get('relations') or [])
             if r.get('source_field') == 'org_id'), None
        )
        if rel is not None:
            assert rel['target'] == 'org', f'{facet_id}.org_id relation 目标漂移: {rel}'
        ui = self._field(raw, 'org_id').get('ui') or {}
        assert ui.get('relation', 'org') == 'org', (
            f'{facet_id}.org_id 的 ui.relation 应与基表 party_to_org 同指向 org'
        )