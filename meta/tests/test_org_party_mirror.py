# -*- coding: utf-8 -*-
"""[2026-10-20] org → party 内部表示镜像 · 单元测试

依据: meta/services/org_party_mirror_service.py 模块头（决策口径 / 不删除原则）
      meta/migrations/v096__backfill_org_party_internal.py

覆盖:
  1. 建行: 具备 legal_entity 职能的 org → 建出一行 source='org'（party_internal 可见）
  2. 不建行: 无 legal_entity 职能 → 不建
  3. 幂等: 重复 sync / backfill 不新增行
  4. 同步: org 更名 / 状态变更 → party 行跟随
  5. 不删除原则: 移除 legal_entity 后已有行保留
  6. 三个触发入口: OrgFunctionService.add_function / Interceptor(P94) / backfill

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db。
          DML 走 factories 桥接（conftest raw-SQL 守卫）。
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.factories._raw_sql_bridge import delete, insert, update

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture()
def mirror_env(tmp_path):
    """临时库: orgs / org_functions / parties（含 idx_party_org_unique）
    / party_relations（引用扫描的被扫表）"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.models import registry
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import invalidate_cache
    from meta.core.yaml_loader import load_yaml_file
    from meta.services.org_party_mirror_service import OrgPartyMirrorService

    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party.yaml'))
    assert obj is not None, 'party.yaml 加载失败'
    # 同批建出 party_internal 视图（谓词 source='org'），用于验证"建出的行确实可见"；
    # party_relations 是引用扫描的被扫表（find_party_references 的 A 类引用面），
    # 连带 party_groups（party_relation.group_id 的 FK 目标）
    objs = [obj]
    for bo_id in ('party_archive', 'party_internal', 'party_group',
                  'party_relation'):
        view_obj = load_yaml_file(os.path.join(_SCHEMA_DIR, bo_id + '.yaml'))
        assert view_obj is not None, '%s.yaml 加载失败' % bo_id
        objs.append(view_obj)

    added = [o.id for o in objs if registry.get(o.id) is None]
    for o in objs:
        if o.id in added:
            registry.register(o)
    invalidate_cache()

    ds = get_data_source('sqlite', database=str(tmp_path / 'mirror.db'))
    ds.execute(
        "CREATE TABLE IF NOT EXISTS orgs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, code VARCHAR(200), "
        "name VARCHAR(200), status VARCHAR(30), org_type VARCHAR(50))"
    )
    ds.execute(
        "CREATE TABLE IF NOT EXISTS org_functions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, org_id INTEGER NOT NULL, "
        "function_type VARCHAR(50) NOT NULL, is_primary INTEGER DEFAULT 0, "
        "UNIQUE(org_id, function_type))"
    )
    sync_schema_from_meta(ds, objs)

    yield ds, OrgPartyMirrorService(ds)

    _clear_data_source_cache_for_testing()
    for bo_id in added:
        registry._objects.pop(bo_id, None)
    invalidate_cache()


def _make_org(ds, code='ORG-1', name='法人甲', status='active',
              legal_entity=True):
    """建一个 org，并按需授予 legal_entity 职能，返回 org id。"""
    cursor = insert(ds, 'orgs', code=code, name=name, status=status,
                    org_type='company')
    org_id = cursor.lastrowid
    insert(ds, 'org_functions', org_id=org_id,
           function_type='legal_entity' if legal_entity else 'administrative',
           is_primary=1)
    return org_id


def _party_rows(ds, org_id):
    return ds.execute(
        "SELECT id, code, name, party_type, source, org_id, status "
        "FROM parties WHERE source='org' AND org_id=?", (org_id,)
    ).fetchall()


def _make_external_party(ds, name='外部伙伴'):
    """建一个对外 party（source 非 'org'）作关系行的对手侧，返回 party id。

    party_relation.party1_id / party2_id 有真 FK ⇒ 造关系行必须指向真实存在的
    party 行，否则 FOREIGN KEY constraint failed。
    """
    cursor = insert(ds, 'parties', code='PATY-EXT-' + name[:4],
                    name=name, party_type='organization', source='manual',
                    status='active')
    return cursor.lastrowid


# ────────────────────────────────────────
# 1-2. 建行 / 不建行
# ────────────────────────────────────────
class TestSyncCreatesRow:
    def test_legal_entity_org_gets_internal_party(self, mirror_env):
        ds, svc = mirror_env
        org_id = _make_org(ds)

        party_id = svc.sync_party_for_org(org_id)

        rows = _party_rows(ds, org_id)
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == party_id
        assert row[1].startswith('PATY-')          # key_template 生效
        assert row[2] == '法人甲'
        assert row[3] == 'organization'
        assert row[4] == 'org'
        assert row[6] == 'active'

    def test_non_legal_entity_org_skipped(self, mirror_env):
        ds, svc = mirror_env
        org_id = _make_org(ds, legal_entity=False)

        assert svc.sync_party_for_org(org_id) is None
        assert _party_rows(ds, org_id) == []

    def test_management_unit_org_gets_internal_party(self, mirror_env):
        """[2026-10-21 放宽] 仅具备 management_unit（BU）也建内部表示。

        这是 party1_id 能选到「非法人内部组织」的前提 —— 否则我方侧候选恒等于
        法人域候选，两个下拉看起来就是重复字段。
        """
        ds, svc = mirror_env
        org_id = _make_org(ds, code='ORG-BU', name='华东销售中心', legal_entity=False)
        delete(ds, 'org_functions', org_id=org_id, function_type='administrative')
        insert(ds, 'org_functions', org_id=org_id,
               function_type='management_unit', is_primary=1)

        party_id = svc.sync_party_for_org(org_id)

        assert party_id
        assert len(_party_rows(ds, org_id)) == 1
        assert svc.is_subject_org(org_id) is True
        assert svc.is_legal_entity(org_id) is False   # 法人域候选不含它

    def test_row_visible_in_party_internal_view(self, mirror_env):
        """写入的行必须能被 party_internal 视图（谓词 source='org'）看见"""
        ds, svc = mirror_env
        org_id = _make_org(ds)
        party_id = svc.sync_party_for_org(org_id)

        visible = ds.execute(
            "SELECT id FROM party_internal WHERE id=?", (party_id,)
        ).fetchall()
        assert len(visible) == 1


# ────────────────────────────────────────
# 3. 幂等
# ────────────────────────────────────────
class TestIdempotency:
    def test_repeated_sync_keeps_single_row(self, mirror_env):
        ds, svc = mirror_env
        org_id = _make_org(ds)

        first = svc.sync_party_for_org(org_id)
        second = svc.sync_party_for_org(org_id)

        assert first == second
        assert len(_party_rows(ds, org_id)) == 1

    def test_backfill_idempotent(self, mirror_env):
        ds, svc = mirror_env
        _make_org(ds, code='ORG-1', name='法人甲')
        _make_org(ds, code='ORG-2', name='法人乙')
        _make_org(ds, code='ORG-3', name='部门丙', legal_entity=False)

        assert svc.backfill() == 2
        assert svc.backfill() == 0
        total = ds.execute(
            "SELECT COUNT(*) FROM parties WHERE source='org'").fetchone()[0]
        assert total == 2


# ────────────────────────────────────────
# 4. 同步 name / status
# ────────────────────────────────────────
class TestSyncFollowsOrg:
    def test_rename_and_status_change_propagate(self, mirror_env):
        ds, svc = mirror_env
        org_id = _make_org(ds)
        party_id = svc.sync_party_for_org(org_id)

        update(ds, 'orgs', {'id': org_id}, name='法人甲（更名）', status='inactive')
        assert svc.sync_party_for_org(org_id) == party_id

        name, status = ds.execute(
            "SELECT name, status FROM parties WHERE id=?", (party_id,)
        ).fetchone()
        assert name == '法人甲（更名）'
        assert status == 'inactive'


# ────────────────────────────────────────
# 5. 不删除原则
# ────────────────────────────────────────
class TestNoDelete:
    def test_losing_function_keeps_existing_row(self, mirror_env):
        ds, svc = mirror_env
        org_id = _make_org(ds)
        party_id = svc.sync_party_for_org(org_id)

        delete(ds, 'org_functions', org_id=org_id,
               function_type='legal_entity')
        assert svc.sync_party_for_org(org_id) is None
        # 行保留（内部表示一旦被引用即历史事实，只能停用不能抹除）
        assert [r[0] for r in _party_rows(ds, org_id)] == [party_id]


# ────────────────────────────────────────
# 6a. 入口一: OrgFunctionService.add_function
# ────────────────────────────────────────
class TestFunctionServiceHook:
    def test_granting_legal_entity_creates_party(self, mirror_env):
        ds, _ = mirror_env
        from meta.services.org_function_service import OrgFunctionService

        cursor = insert(ds, 'orgs', code='ORG-9', name='法人丁', status='active')
        org_id = cursor.lastrowid

        OrgFunctionService(ds).add_function(org_id, 'legal_entity')
        assert len(_party_rows(ds, org_id)) == 1

    def test_non_legal_entity_function_creates_nothing(self, mirror_env):
        ds, _ = mirror_env
        from meta.services.org_function_service import OrgFunctionService

        cursor = insert(ds, 'orgs', code='ORG-10', name='部门戊', status='active')
        org_id = cursor.lastrowid

        OrgFunctionService(ds).add_function(org_id, 'cost_center')
        assert _party_rows(ds, org_id) == []


# ────────────────────────────────────────
# 6b. 入口二: Interceptor
# ────────────────────────────────────────
class TestInterceptorContract:
    def test_priority_runs_after_persistence(self):
        """after 钩子按 priority 降序 ⇒ 必须 < PersistenceInterceptor(95)"""
        from meta.core.interceptors.org_party_mirror_interceptor import (
            OrgPartyMirrorInterceptor,
        )
        from meta.core.interceptors.persistence_interceptor import (
            PersistenceInterceptor,
        )
        assert OrgPartyMirrorInterceptor().priority < PersistenceInterceptor().priority
        assert OrgPartyMirrorInterceptor().priority == 94

    def _ctx(self, object_id, action):
        class _Obj:
            id = object_id

        class _Ctx:
            meta_object = _Obj()

        _Ctx.action = action
        return _Ctx()

    def test_scoped_to_org_crud(self):
        from meta.core.interceptors.org_party_mirror_interceptor import (
            OrgPartyMirrorInterceptor,
        )
        itc = OrgPartyMirrorInterceptor()
        assert itc.should_execute(self._ctx('org', 'crud_create')) is True
        assert itc.should_execute(self._ctx('org', 'crud_update')) is True
        assert itc.should_execute(self._ctx('org', 'crud_read')) is False
        assert itc.should_execute(self._ctx('party', 'crud_create')) is False


# ────────────────────────────────────────
# 7. 引用检测（2026-10-20 方案一第一步：只检测不删除）
# ────────────────────────────────────────
class TestFindPartyReferences:
    """find_party_references —— 决定「零引用 vs 有引用」的唯一防线。

    全库 FK 均为 on_delete=NO ACTION（实测 47 个），即数据库**不阻止**删掉仍被
    引用的 party 行 ⇒ 本方法漏扫 = 悬空引用。故引用面变化必须被测试锁住。
    """

    def _link(self, ds, org_id, party_id, column='party1_id', rel_id=900):
        """在 party_relations 上造一条引用 party_id 的关系行"""
        other_id = _make_external_party(ds, '对手%s' % rel_id)
        insert(ds, 'party_relations', id=rel_id,
               party1_id=party_id if column == 'party1_id' else other_id,
               party2_id=party_id if column == 'party2_id' else other_id,
               role='vendor', internal_mark='external', status='active',
               le_org_id=org_id)

    def test_no_reference_returns_empty(self, mirror_env):
        ds, svc = mirror_env
        org_id = _make_org(ds)
        svc.sync_party_for_org(org_id)

        assert svc.find_party_references(org_id) == []

    def test_detects_party1_reference(self, mirror_env):
        ds, svc = mirror_env
        org_id = _make_org(ds)
        party_id = svc.sync_party_for_org(org_id)
        self._link(ds, org_id, party_id, 'party1_id', rel_id=901)

        refs = svc.find_party_references(org_id)

        assert refs == [{'party_id': party_id,
                         'column': 'party1_id',
                         'relation_id': 901}]

    def test_detects_party2_reference(self, mirror_env):
        """party2_id 侧同样要能扫到（我方主体也可能出现在对手侧）"""
        ds, svc = mirror_env
        org_id = _make_org(ds)
        party_id = svc.sync_party_for_org(org_id)
        self._link(ds, org_id, party_id, 'party2_id', rel_id=902)

        refs = svc.find_party_references(org_id)

        assert len(refs) == 1
        assert refs[0]['column'] == 'party2_id'
        assert refs[0]['relation_id'] == 902

    def test_one_internal_row_per_org_enforced_by_index(self, mirror_env):
        """1:1 是**索引强制的**（party.yaml idx_party_org_unique 部分唯一索引）

        ⇒ find_party_references 只需扫「该 org 的那一行」，不可能漏扫同 org 的
        第二行。此测试把该结构约束锁住：若索引被去掉，本方法的前提即失效。
        """
        ds, svc = mirror_env
        org_id = _make_org(ds)
        svc.sync_party_for_org(org_id)

        import pytest as _pytest
        with _pytest.raises(Exception):
            insert(ds, 'parties', code='PATY-DUP', name='法人甲dup',
                   party_type='organization', source='org', org_id=org_id,
                   status='active')

    def test_nonexistent_org_returns_empty(self, mirror_env):
        """边界：不存在的 org 不得抛错"""
        _, svc = mirror_env
        assert svc.find_party_references(999999) == []


class TestHandleFunctionRevoked:
    """handle_function_revoked —— 只记日志，**绝不删数据**。

    决策依据（2026-10-20）：
      - 全库 FK 无级联保护 ⇒ 删除不可逆、无兜底；
      - 「不删除原则」方向正确，问题在粒度过粗（未区分零引用 / 有引用）；
      - 当前幽灵数据仅 1 行，收益 < 风险。
    故第一版只把游离行变成**可见日志**，证据齐备后再决策是否删除。
    """

    def test_zero_reference_logs_info(self, mirror_env, caplog):
        """零引用 → info：点名该行已脱离 party_internal 候选集"""
        ds, svc = mirror_env
        org_id = _make_org(ds)
        party_id = svc.sync_party_for_org(org_id)
        # [2026-10-21 放宽] 判据是 BU/LE 集合，须先撤掉唯一的 legal_entity，
        #   才构成「已不具备任何主体职能」的前置状态
        delete(ds, 'org_functions', org_id=org_id, function_type='legal_entity')

        with caplog.at_level('INFO', logger='meta.services.org_party_mirror_service'):
            assert svc.handle_function_revoked(org_id) == party_id

        assert '零引用' in caplog.text
        assert '不在 party_internal 候选集中' in caplog.text

    def test_referenced_logs_warning_with_location(self, mirror_env, caplog):
        """有引用 → warning：必须点名是哪条关系行，运维才查得到"""
        ds, svc = mirror_env
        org_id = _make_org(ds)
        party_id = svc.sync_party_for_org(org_id)
        other_id = _make_external_party(ds, '对手丙')
        insert(ds, 'party_relations', id=904,
               party1_id=party_id, party2_id=other_id, role='vendor',
               internal_mark='external', status='active', le_org_id=org_id)
        # [2026-10-21 放宽] 先撤掉唯一主体职能，才进入「已不具备」分支
        delete(ds, 'org_functions', org_id=org_id, function_type='legal_entity')

        with caplog.at_level('WARNING', logger='meta.services.org_party_mirror_service'):
            svc.handle_function_revoked(org_id)

        assert '被引用' in caplog.text
        assert 'party_relations#904' in caplog.text
        assert 'party1_id' in caplog.text

    def test_never_deletes_party_row(self, mirror_env):
        """核心不变量：无论有无引用，本方法都不得删除内部表示行"""
        ds, svc = mirror_env

        # 零引用场景
        org_a = _make_org(ds, code='ORG-A', name='法人A')
        svc.sync_party_for_org(org_a)
        svc.handle_function_revoked(org_a)
        assert _party_rows(ds, org_a), '零引用时也不得删除'

        # 有引用场景
        org_b = _make_org(ds, code='ORG-B', name='法人B')
        pid_b = svc.sync_party_for_org(org_b)
        other_b = _make_external_party(ds, '对手丁')
        insert(ds, 'party_relations', id=905,
               party1_id=pid_b, party2_id=other_b, role='vendor',
               internal_mark='external', status='active', le_org_id=org_b)
        svc.handle_function_revoked(org_b)
        assert _party_rows(ds, org_b), '有引用时不得删除（不删原则）'

    def test_nonexistent_org_returns_none(self, mirror_env):
        _, svc = mirror_env
        assert svc.handle_function_revoked(999999) is None


class TestRemoveFunctionHook:
    """remove_function 的检测挂钩（原实现完全没挂钩，是口径分叉的成因之一）。"""

    def test_hooks_on_legal_entity_revoke(self, mirror_env, caplog):
        ds, svc = mirror_env
        from meta.services.org_function_service import OrgFunctionService
        org_id = _make_org(ds)
        svc.sync_party_for_org(org_id)

        with caplog.at_level('INFO', logger='meta.services.org_party_mirror_service'):
            assert OrgFunctionService(ds).remove_function(
                org_id, 'legal_entity') is True

        assert '已不具备任何主体职能' in caplog.text

    def test_revoking_le_while_bu_remains_keeps_candidate(self, mirror_env, caplog):
        """[2026-10-21 放宽] 撤销法人职能但仍有管理单元职能 ⇒ 仍是主体，不脱离候选集"""
        ds, svc = mirror_env
        org_id = _make_org(ds)
        svc.sync_party_for_org(org_id)
        insert(ds, 'org_functions', org_id=org_id,
               function_type='management_unit', is_primary=0)
        delete(ds, 'org_functions', org_id=org_id, function_type='legal_entity')

        with caplog.at_level('INFO', logger='meta.services.org_party_mirror_service'):
            svc.handle_function_revoked(org_id)

        assert '仍具备其它主体职能' in caplog.text
        assert svc.is_subject_org(org_id) is True
        assert _party_rows(ds, org_id), '不删除原则'

    def test_no_hook_for_non_legal_entity(self, mirror_env, caplog):
        """撤 administrative 等职能与 party 镜像无关，不得触发检测"""
        ds, _ = mirror_env
        from meta.services.org_function_service import OrgFunctionService
        org_id = _make_org(ds, code='ORG-NL', name='部门己', legal_entity=False)

        with caplog.at_level('INFO', logger='meta.services.org_party_mirror_service'):
            assert OrgFunctionService(ds).remove_function(
                org_id, 'administrative') is True

        assert '失去 legal_entity 职能' not in caplog.text

    def test_revoke_missing_function_is_silent(self, mirror_env, caplog):
        """撤 org 上本就不存在的职能：removed=False 且不得重复告警"""
        ds, _ = mirror_env
        from meta.services.org_function_service import OrgFunctionService
        # 该 org 仅有 administrative 职能，无 legal_entity
        org_id = _make_org(ds, code='ORG-NF', name='部门壬', legal_entity=False)

        with caplog.at_level('INFO', logger='meta.services.org_party_mirror_service'):
            assert OrgFunctionService(ds).remove_function(
                org_id, 'legal_entity') is False

        assert '失去 legal_entity 职能' not in caplog.text

    def test_revoke_keeps_party_row(self, mirror_env):
        """撤销职能后内部表示行仍在（不删原则经 remove_function 路径也成立）"""
        ds, svc = mirror_env
        from meta.services.org_function_service import OrgFunctionService
        org_id = _make_org(ds)
        svc.sync_party_for_org(org_id)

        OrgFunctionService(ds).remove_function(org_id, 'legal_entity')

        assert len(_party_rows(ds, org_id)) == 1
        # 但职能已撤 ⇒ 该行不再被 backfill 的 JOIN 命中（两个视图口径由此分叉）
        assert svc.is_legal_entity(org_id) is False


class TestOrphanOrgFunctions:
    """find_orphan_org_functions —— 问题 E：org_functions 无 FK 到 orgs。"""

    def test_no_orphan_returns_empty(self, mirror_env):
        ds, svc = mirror_env
        _make_org(ds)
        assert svc.find_orphan_org_functions() == []

    def test_detects_orphan_rows(self, mirror_env):
        """删 org 不清理 org_functions ⇒ 孤儿行需能被检出"""
        ds, svc = mirror_env
        insert(ds, 'org_functions', org_id=88888,
               function_type='legal_entity', is_primary=1)

        assert 88888 in svc.find_orphan_org_functions()

    def test_orphan_row_invisible_to_backfill_join(self, mirror_env):
        """孤儿行被 backfill 的 JOIN orgs 过滤掉 ⇒ 不可见的脏数据"""
        ds, svc = mirror_env
        insert(ds, 'org_functions', org_id=88899,
               function_type='legal_entity', is_primary=1)

        joined = ds.execute(
            "SELECT f.org_id FROM org_functions f "
            "JOIN orgs o ON o.id = f.org_id "
            "WHERE f.function_type='legal_entity'"
        ).fetchall()

        assert (88899,) not in joined, '孤儿行对 backfill 不可见（故须单独检出）'
        assert 88899 in svc.find_orphan_org_functions()


class TestOrgDeletionCascade:
    """[2026-10-22 补漏] 删除组织时级联清理 org_functions。

    孤儿职能行不只是脏数据：party_internal 视图谓词是 EXISTS(org_functions ...)，
    该行残留会让「已删除组织」的内部表示继续出现在我方主体候选集中（幽灵主体），
    同 id 组织重建时旧职能还会复活。故 org.yaml 必须在 deletion_policy 里声明级联。
    """

    def test_org_yaml_declares_cascade_for_org_functions(self):
        from meta.core.yaml_loader import load_yaml_file

        org_obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'org.yaml'))
        assert org_obj is not None
        policy = getattr(org_obj, 'deletion_policy', None) or {}
        # loader 可能给出 dict 或 dataclass 两种形态，与 CascadeInterceptor 的双形态读取保持一致
        if isinstance(policy, dict):
            cascade = policy.get('cascade_delete', []) or []
        else:
            cascade = getattr(policy, 'cascade_delete', []) or []
        tables = [c if isinstance(c, str) else c.get('table') for c in cascade]

        assert 'org_functions' in tables

    def test_cascade_interceptor_cleans_org_functions(self, mirror_env):
        from types import SimpleNamespace

        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        from meta.core.yaml_loader import load_yaml_file

        ds, _svc = mirror_env
        org_obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'org.yaml'))
        org_id = _make_org(ds)
        count_sql = "SELECT COUNT(*) FROM org_functions WHERE org_id = ?"
        assert ds.execute(count_sql, (org_id,)).fetchone()[0] == 1

        ctx = SimpleNamespace(
            meta_object=org_obj,
            object_id=org_id,
            object_type='org',
            data_source=ds,
        )
        CascadeInterceptor()._cleanup_association_tables(ctx)

        assert ds.execute(count_sql, (org_id,)).fetchone()[0] == 0
