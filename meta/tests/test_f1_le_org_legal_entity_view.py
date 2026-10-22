# -*- coding: utf-8 -*-
"""F1 法人域候选集收窄 · org_legal_entity 视图 BO 不变量测试 (2026-10-20)

依据: docs/superpowers/specs/2026-10-20-legal-entity-view-bo.md

背景: party_relation.le_org_id（法人域）语义为「这条关系以哪个法人主体名义存在」，
候选集本应只含具备 legal_entity 职能的 org。此前 target_bo: org ⇒ 下拉返回全部 64 个
org（含部门 / Test Group / 测试用户组），而全库仅 1 个法人。

覆盖（声明口径 / 视图结构 / 抽样对照 / 同源性 / 护栏 / 绑定不变量 / 回显）:
1. 声明口径  : le_org_id 的 target_bo = org_legal_entity（候选集口径收窄）;
               display_target_bo = org（展示解析口径回身份锚）; semantics.display.target_type
               仍为 org（展示口径，非遗漏）
2. 视图结构  : object_type=view; 谓词同时含 org_functions 与 'legal_entity';
               无 write_anchor（纯只读面）; relations: []（FK 口径留在基表侧）
3. 抽样对照  : 临时库真实建表 / 视图 → 2 部门 + 1 职能法人 ⇒ 视图仅 1 行
4. 同源性    : 视图结果集 == org_functions 判据集合（与 org_party_mirror_service 同源，
               结构上不可能口径分裂）—— 2026-10-20 修复原 value_filter 方案会引入的分裂
5. 写护栏    : 无锚真视图写入被 READ_ONLY_VIEW 拒（API 侧 400）
6. 绑定不变量: 不挂 org 维度绑定（对齐 party_archive）⇒ org 维度 applies_to 无本面条目
7. 回显兼容  : 存量值（已不在视图内的 org id）经 display_target_bo 兜底仍能取名，
               不退化为显示技术 id（AC-6）
8. 菜单抑制  : skip_auto_menu: true（本面是字段级候选集，不应出现在左侧菜单）

测试隔离:
- temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db
- DML 走 ds.insert API; 本文件不出现裸写语句（conftest raw-SQL 守卫）
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

_VIEW_ID = 'org_legal_entity'
_BASE_ID = 'org'

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_raw(bo_id):
    """直接读原始 YAML（不经 loader，避免注册表副作用）"""
    import yaml
    with open(os.path.join(_SCHEMA_DIR, bo_id + '.yaml'), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _party_relation_raw():
    return _load_raw('party_relation')


def _le_org_field():
    """取 party_relation.le_org_id 的原始字段声明"""
    for f in _party_relation_raw().get('fields', []):
        if f.get('id') == 'le_org_id':
            return f
    raise AssertionError('party_relation.yaml 未找到 le_org_id 字段')


def _bare_manage_service():
    """裸实例: 仅验证只读护栏分支（拒写发生在触碰 data_source 之前）"""
    from meta.services.manage_service import ManageService
    return ManageService.__new__(ManageService)


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture()
def view_objs():
    """加载 org 基表 + 法人视图两个真实 YAML 并注册 registry"""
    from meta.core.models import registry
    from meta.core.table_name_validator import invalidate_cache
    from meta.core.yaml_loader import load_yaml_file

    objs = []
    for bo_id in (_BASE_ID, _VIEW_ID):
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
def legal_entity_ds(tmp_path, view_objs):
    """临时 SQLite 库: orgs 基表 + org_functions + org_legal_entity 视图

    造 3 个 org: 两个只有 administrative 职能（非法人）、一个带 legal_entity 职能
    ⇒ 视图应只返回后者。
    """
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.tests.factories._raw_sql_bridge import insert

    ds = get_data_source("sqlite", database=str(tmp_path / 'le_org_view.db'))
    sync_schema_from_meta(ds, list(view_objs))
    # [视图谓词依赖 org_functions 一对多子表] 该表由 v073 迁移建、不在任何 BO YAML 中
    # ⇒ 视图 CREATE 之前须先存在，否则 SQLite 建视图不报错但查询期报 no such table。
    # 建表走 ds.execute（DDL 不受 table_name_validator 约束）。
    ds.execute(
        'CREATE TABLE IF NOT EXISTS org_functions ('
        '  id INTEGER PRIMARY KEY AUTOINCREMENT,'
        '  org_id INTEGER NOT NULL,'
        '  function_type TEXT NOT NULL,'
        '  is_primary BOOLEAN DEFAULT 0,'
        '  UNIQUE(org_id, function_type))'
    )

    # 三个组织：2 个非法人（仅 administrative）+ 1 个法人（legal_entity）。
    # DML 走 raw_sql_bridge —— org_functions 未注册进 table_name_validator，
    # ds.insert 会被拒。
    insert(ds, 'orgs', rows=[
        {'id': 1, 'code': 'dept_a', 'name': '部门甲',
         'org_type': 'department', 'status': 'active'},
        {'id': 2, 'code': 'team_b', 'name': '团队乙',
         'org_type': 'team', 'status': 'active'},
        {'id': 3, 'code': 'viewgroup', 'name': 'YonBIP应用架构',
         'org_type': 'company', 'status': 'active'},
    ])
    insert(ds, 'org_functions', rows=[
        {'org_id': 1, 'function_type': 'administrative'},
        {'org_id': 2, 'function_type': 'administrative'},
        {'org_id': 3, 'function_type': 'legal_entity'},
    ])

    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 1. 声明口径（spec §4.3 / AC-8）
# ────────────────────────────────────────
class TestDeclaration:
    def test_candidate_scope_points_to_view(self):
        """候选集口径 = 法人视图（而非 org 全表）"""
        src = _le_org_field()['value_help']['source']
        assert src['target_bo'] == _VIEW_ID, \
            '候选集口径须收窄到法人视图，当前=%r' % src.get('target_bo')

    def test_display_scope_falls_back_to_org(self):
        """展示解析口径 = org 身份锚（存量值失职能后仍可回显）"""
        src = _le_org_field()['value_help']['source']
        assert src.get('display_target_bo') == _BASE_ID, \
            '须声明 display_target_bo=org 作为回显兜底'

    def test_display_semantics_still_points_to_org(self):
        """semantics.display.target_type 是展示解析口径，须仍为 org（非遗漏）"""
        disp = _le_org_field()['semantics']['display']
        assert disp['type'] == 'association'
        assert disp['target_type'] == _BASE_ID
        assert disp['display_field'] == 'name'

    def test_both_scopes_are_declared_and_differ(self):
        """两口径必须同时存在且不同——这才是「口径分离」本身"""
        src = _le_org_field()['value_help']['source']
        assert src['target_bo'] != src.get('display_target_bo'), \
            '若两口径相同则退化为旧行为，候选集不会被收窄'


# ────────────────────────────────────────
# 2. 视图结构（spec §4.1 / AC-1）
# ────────────────────────────────────────
class TestViewStructure:
    def test_is_view_type(self):
        assert _load_raw(_VIEW_ID).get('object_type') == 'view'

    def test_predicate_reads_org_functions(self):
        """谓词以 org_functions 为事实源（而非 org_type 枚举）"""
        vd = ' '.join((_load_raw(_VIEW_ID).get('view_definition') or '').split())
        assert 'org_functions' in vd, \
            '法人判据必须来自职能表，org_type=company 方案会与镜像服务口径分裂'

    def test_predicate_matches_legal_entity(self):
        vd = ' '.join((_load_raw(_VIEW_ID).get('view_definition') or '').split())
        assert "'legal_entity'" in vd

    def test_no_write_anchor(self):
        """纯只读面：无 write_anchor ⇒ 写请求由 READ_ONLY_VIEW 护栏拒绝"""
        raw = _load_raw(_VIEW_ID)
        assert not raw.get('write_anchor'), '法人面不应有写锚'

    def test_relations_empty(self):
        """视图上不建 FK（le_org_id → org 的外键口径留在 party_relation 侧）"""
        assert _load_raw(_VIEW_ID).get('relations') == []

    def test_skip_auto_menu(self):
        """本面是字段级候选集，不应出现在左侧菜单"""
        assert _load_raw(_VIEW_ID).get('ui_view_config', {}).get('skip_auto_menu') is True

    def test_display_name_field(self):
        assert _load_raw(_VIEW_ID).get('display_name_field') == 'name'

    def test_org_type_enum_not_hardcoded(self):
        """不在本面写死 org_type 枚举——职能与组织类型是两个独立维度"""
        for f in _load_raw(_VIEW_ID).get('fields', []):
            if f.get('id') == 'org_type':
                ev = f.get('enum_values')
                assert ev is None or len(ev) >= 4, \
                    'org_type 枚举应保留全部 4 类，避免暗示 company == 法人'
                return
        raise AssertionError('视图未声明 org_type 字段')


# ────────────────────────────────────────
# 3. 抽样对照（spec §4.2 / AC-2）
# ────────────────────────────────────────
class TestViewContent:
    def test_only_legal_entity_org_visible(self, legal_entity_ds):
        rows = legal_entity_ds.query(
            'SELECT id, code, name FROM org_legal_entity ORDER BY id')
        assert [r['id'] for r in rows] == [3], \
            '视图须只返回带 legal_entity 职能的 org'

    def test_narrower_than_base_table(self, legal_entity_ds):
        total_orgs = legal_entity_ds.query('SELECT COUNT(*) AS c FROM orgs')[0]['c']
        total_view = legal_entity_ds.query(
            'SELECT COUNT(*) AS c FROM org_legal_entity')[0]['c']
        assert total_view < total_orgs, '视图必须比基表窄，否则收窄无效'

    def test_selected_columns_resolvable(self, legal_entity_ds):
        """视图声明的每个列都真的存在（防 SELECT 到不存在列导致运行期报错）"""
        cols = {r['id'] for r in legal_entity_ds.query(
            'SELECT id, code, name, org_type, parent_id, manager_id, status '
            'FROM org_legal_entity')}
        assert cols == {3}

    def test_base_table_unaffected(self, legal_entity_ds):
        """视图不得影响 org 基表数据完整性"""
        assert legal_entity_ds.query('SELECT COUNT(*) AS c FROM orgs')[0]['c'] == 3


# ────────────────────────────────────────
# 4. 同源性（spec §3.3.3 / AC-3）
# ────────────────────────────────────────
class TestMirrorParity:
    def test_view_set_equals_function_judgement(self, legal_entity_ds):
        """视图集合 == org_functions 判据集合

        这是本方案的核心价值：与 org_party_mirror_service 读同一张表、同一谓词，
        结构上不可能口径分裂（org_type 方案会）。
        """
        view_ids = [r['id'] for r in legal_entity_ds.query(
            'SELECT id FROM org_legal_entity ORDER BY id')]
        fn_ids = [r['org_id'] for r in legal_entity_ds.query(
            "SELECT org_id FROM org_functions "
            "WHERE function_type = 'legal_entity' ORDER BY org_id")]
        assert view_ids == fn_ids

    def test_mirror_service_uses_same_function_type(self):
        """镜像服务的判据常量必须就是视图谓词里的那个字符串"""
        from meta.services.org_party_mirror_service import (
            LEGAL_ENTITY_FUNCTION,
        )
        vd = ' '.join((_load_raw(_VIEW_ID).get('view_definition') or '').split())
        assert "'%s'" % LEGAL_ENTITY_FUNCTION in vd


# ────────────────────────────────────────
# 5. 写护栏（spec §4.1 / AC-7）
# ────────────────────────────────────────
class TestWriteGuard:
    def test_create_denied_readonly_view(self):
        """无锚真视图：create / update / delete 均被 READ_ONLY_VIEW 拒（API 侧 400）"""
        from meta.services.manage_service import (
            CreateRequest, UpdateRequest, DeleteRequest,
        )
        svc = _bare_manage_service()
        results = [
            svc.create(CreateRequest(object_type=_VIEW_ID,
                                    data={'name': 'x'})),
            svc.update(UpdateRequest(object_type=_VIEW_ID, id=1,
                                    data={'name': 'y'})),
            svc.delete(DeleteRequest(object_type=_VIEW_ID, id=1)),
        ]
        for r in results:
            assert r.success is False
            assert r.error == 'READ_ONLY_VIEW'


# ────────────────────────────────────────
# 6. 绑定不变量（spec §4.1 决策）
# ────────────────────────────────────────
class TestNoDimensionBinding:
    @staticmethod
    def _org_dimension_bound_bos():
        import yaml
        with open(os.path.join(_SCHEMA_DIR,
                               'dimension_object_mapping.yaml'),
                  'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        bound = []
        for dim in data.get('dimension_object_mappings') or []:
            if dim.get('dimension_code') != 'org':
                continue
            for a in dim.get('applies_to') or []:
                bound.append(a.get('bo'))
        return bound

    def test_org_dimension_not_registered_for_view(self):
        """法人面不挂 org 维度（对齐 party_archive）"""
        bound = self._org_dimension_bound_bos()
        assert _VIEW_ID not in bound, \
            '法人面是主数据非业务数据行，不应注入 org 范围过滤'

    def test_baseline_org_dimension_still_binds_party_internal(self):
        """防误伤：party_internal 的既有绑定不得被本次改动波及"""
        bound = self._org_dimension_bound_bos()
        assert 'party_internal' in bound


# ────────────────────────────────────────
# 7. 回显兼容（spec §4.4 / AC-6）
# ────────────────────────────────────────
class TestDisplayFallback:
    def test_org_id_outside_view_still_resolvable(self, legal_entity_ds):
        """AC-6: 有 le_org_id 但已不在视图内的行，回显不得退化为技术 id

        造一个「曾是法人、后被摘掉职能」的 org（id=1）—— 视图内查不到，
        但 display_target_bo=org 兜底能取到名称。
        """
        in_view = legal_entity_ds.query(
            'SELECT id FROM org_legal_entity WHERE id = 1')
        assert in_view == [], '前提：id=1 已不在视图内'

        from meta.core.models import ValueHelpSource
        from meta.core.value_help_providers import BoValueHelpProvider
        from meta.core.models import registry

        from meta.services import query_service
        prev = query_service._data_source_instance
        query_service._data_source_instance = legal_entity_ds
        try:
            provider = BoValueHelpProvider(ValueHelpSource(
                type='bo', target_bo=_VIEW_ID,
                value_field='id', display_field='name', code_field='code',
                display_target_bo=_BASE_ID,
            ))
            res = provider.resolve(1)
            assert res is not None, '须经 display_target_bo 兜底解析出记录'
            assert res['display'] == '部门甲', \
                '回退取名失败，实际=%r' % (res or {}).get('display')
        finally:
            query_service._data_source_instance = prev

    def test_resolve_hit_inside_view(self, legal_entity_ds):
        """视图内的值直接命中（不依赖兜底）"""
        from meta.core.models import ValueHelpSource
        from meta.core.value_help_providers import BoValueHelpProvider
        from meta.services import query_service

        prev = query_service._data_source_instance
        query_service._data_source_instance = legal_entity_ds
        try:
            provider = BoValueHelpProvider(ValueHelpSource(
                type='bo', target_bo=_VIEW_ID,
                value_field='id', display_field='name', code_field='code',
                display_target_bo=_BASE_ID,
            ))
            res = provider.resolve(3)
            assert res is not None
            assert res['display'] == 'YonBIP应用架构'
        finally:
            query_service._data_source_instance = prev


# ────────────────────────────────────────
# 9. 停用主体不收窄视图、只收窄候选集（问题 F · 2026-10-20）
# ────────────────────────────────────────
class TestCandidateStatusFilter:
    """停用法人不得作为新建关系的候选，但存量行仍须可回显。

    实现口径: status 过滤放 value_help.source.value_filter（候选集口径），
    不写进视图谓词 —— 视图保留 status 列，仍是可筛的真实维度；且 resolve
    端点不读 value_filter，故停用行的历史显示不受影响。
    """

    def test_declared_value_filter_active_only(self):
        src = _le_org_field()['value_help']['source']
        assert src.get('value_filter') == {'status': 'active'}, \
            '法人域候选集须只取启用法人'

    def test_view_predicate_keeps_status_column_free(self):
        """视图谓词不得滤 status（否则该列恒为 active，筛选维度失效）"""
        vd = ' '.join((_load_raw(_VIEW_ID).get('view_definition') or '').split())
        assert 'status' not in vd.split('WHERE', 1)[1], \
            'status 收窄应落在 value_filter，不应写进视图谓词'

    def test_inactive_excluded_from_candidates_but_resolvable(
            self, legal_entity_ds):
        from meta.core.models import ValueHelpSource
        from meta.core.value_help_providers import BoValueHelpProvider
        from meta.services import query_service
        from meta.tests.factories._raw_sql_bridge import insert

        ds = legal_entity_ds
        insert(ds, 'orgs', rows=[
            {'id': 4, 'code': 'old_le', 'name': '已停用法人',
             'org_type': 'company', 'status': 'inactive'},
        ])
        insert(ds, 'org_functions',
               rows=[{'org_id': 4, 'function_type': 'legal_entity'}])

        prev = query_service._data_source_instance
        query_service._data_source_instance = ds
        try:
            provider = BoValueHelpProvider(ValueHelpSource(
                type='bo', target_bo=_VIEW_ID,
                value_field='id', display_field='name', code_field='code',
                display_target_bo=_BASE_ID,
                value_filter={'status': 'active'},
                # [2026-10-20] 单元测试无 Flask 应用上下文 ⇒ 数据权限分支
                #   fail-closed 注入 id = -1（query_service.py L1644-1651），
                #   结果恒空、与本用例要验证的「候选集按 status 收窄」无关。
                #   关闭后只测 value_filter 语义（生产环境由已登录用户上下文接管）。
                apply_target_permissions=False,
            ))
            res = provider.search('', ['code', 'name'], {}, 1, 50, [])
            assert [it['value'] for it in res['data']] == [3], \
                '停用法人不得进入候选集'

            hit = provider.resolve(4)
            assert hit is not None and hit['display'] == '已停用法人', \
                '存量行的停用法人仍须可回显（resolve 不读 value_filter）'
        finally:
            query_service._data_source_instance = prev


# ────────────────────────────────────────
# 8. FK 口径未退化（spec §4.3）
# ────────────────────────────────────────
class TestForeignKeyIntact:
    def test_relation_still_targets_org_base_table(self):
        """物理 FK 仍指向 orgs.id（视图与基表同列同 id 空间）"""
        rels = _party_relation_raw().get('relations', [])
        target = [r for r in rels if r.get('id') == 'party_relation_to_le_org']
        assert target, 'party_relation_to_le_org 关系声明丢失'
        assert target[0]['target'] == _BASE_ID

    def test_view_id_matches_orgs_row_id_space(self):
        """视图 id 与 orgs.id 同空间（存量 le_org_id 值无需迁移）"""
        raw = _load_raw(_VIEW_ID)
        assert raw['table_name'] == _VIEW_ID
        vd = ' '.join(raw['view_definition'].split())
        assert vd.startswith('SELECT o.id'), '视图须直取 orgs.id，不得另生成主键'
