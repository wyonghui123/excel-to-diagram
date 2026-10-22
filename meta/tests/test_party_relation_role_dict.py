# -*- coding: utf-8 -*-
"""F3 · 往来关系角色轴字典化 + 镜像行防护（2026-10-20）

依据: docs/superpowers/specs/2026-10-20-party-relation-role-dictionary-and-mirror-guard.md
      §4（D1–D5）/ §6（验收判据）

覆盖:
  A. 字典化（§6.1）: role 内联 enum_values 保留；value_help 指向 party_relation_role；
     seed 幂等；category=system + mutability=extensible；值集与内联一致。
  B. role_scope 依赖登记（§6.1 / §4.3）: 与 role 字典**独立**；both 为分组侧专有值；
     schema 注释登记子集依赖。
  C. 镜像行防护（§6.2）: 反向行被拒；角色不同 / 法人不同 / le_org_id 空 放行；
     update 排除自身；仅 party_relation 生效。

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta；DML 走 _raw_sql_bridge；
         不触碰 architecture.db。
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.factories._raw_sql_bridge import insert

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

_ROLE_DICT_ID = 'party_relation_role'
_SCOPE_DICT_ID = 'party_group_role_scope'

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _yaml(name):
    import yaml
    with open(os.path.join(_SCHEMA_DIR, name), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _raw_text(name):
    with open(os.path.join(_SCHEMA_DIR, name), 'r', encoding='utf-8') as f:
        return f.read()


def _field(yaml_name, field_id):
    for f in _yaml(yaml_name)['fields']:
        if f['id'] == field_id:
            return f
    raise AssertionError(f'{yaml_name} 缺少字段 {field_id}')


# ────────────────────────────────────────
# A. 字典化
# ────────────────────────────────────────
class TestRoleDictionary:
    def test_inline_enum_values_kept(self):
        """§6.1-6: 内联 enum_values 未删（静态回退 + 列表列配色）"""
        f = _field('party_relation.yaml', 'role')
        codes = [ev['value'] for ev in f['enum_values']]
        assert codes == ['customer', 'vendor']
        colors = {ev['value']: ev['color'] for ev in f['enum_values']}
        assert colors['customer'] == 'primary'
        assert colors['vendor'] == 'success'

    def test_value_help_points_to_dictionary(self):
        """§6.1-3: role 挂 value_help（source.type=enum → party_relation_role）"""
        f = _field('party_relation.yaml', 'role')
        src = f['value_help']['source']
        assert src['type'] == 'enum'
        assert src['enum_type_id'] == _ROLE_DICT_ID
        assert f['value_help']['behavior']['binding_strength'] == 'strict'

    def test_seed_codes_match_inline(self):
        """§8 双轨漂移缓解: 字典种子值与内联 enum_values 一致"""
        from meta.scripts.migrate_enums import PARTY_RELATION_ROLE_VALUES
        inline = [ev['value'] for ev in _field('party_relation.yaml', 'role')['enum_values']]
        assert [v[0] for v in PARTY_RELATION_ROLE_VALUES] == inline

    def test_role_field_is_not_filter(self):
        """role 非列表过滤器（故改 widget/value_help 无过滤面影响）"""
        f = _field('party_relation.yaml', 'role')
        assert not (f.get('semantics') or {}).get('filterable')

    def test_header_registers_dictionary(self):
        text = _raw_text('party_relation.yaml')
        assert _ROLE_DICT_ID in text
        assert 'extensible' in text


class TestRoleDictionarySeed:
    @pytest.fixture()
    def enum_ds(self, tmp_path):
        from meta.core.datasource import (
            _clear_data_source_cache_for_testing, get_data_source,
        )
        ds = get_data_source('sqlite', database=str(tmp_path / 'f3_enum.db'))
        ds.execute(
            'CREATE TABLE enum_types ('
            'id TEXT PRIMARY KEY, name TEXT, category TEXT, mutability TEXT, '
            'dimension_schema TEXT, description TEXT, created_at TEXT)'
        )
        ds.execute(
            'CREATE TABLE enum_values ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT, enum_type_id TEXT, code TEXT, '
            'name TEXT, name_en TEXT, dimensions TEXT, sort_order INTEGER, '
            'is_active INTEGER, is_system INTEGER, created_at TEXT)'
        )
        yield ds
        _clear_data_source_cache_for_testing()

    def test_seed_creates_type_and_values(self, enum_ds):
        """§6.1-1: 幂等 seed 建出类型与 2 个值"""
        from meta.scripts.migrate_enums import seed_party_relation_role
        types_created, values_created = seed_party_relation_role(enum_ds)
        assert (types_created, values_created) == (1, 2)

        row = enum_ds.query(
            'SELECT id, category, mutability FROM enum_types WHERE id = ?',
            [_ROLE_DICT_ID],
        )[0]
        assert row['category'] == 'system'
        assert row['mutability'] == 'extensible'

        codes = [r['code'] for r in enum_ds.query(
            'SELECT code FROM enum_values WHERE enum_type_id = ? ORDER BY sort_order',
            [_ROLE_DICT_ID],
        )]
        assert codes == ['customer', 'vendor']

    def test_seed_is_idempotent(self, enum_ds):
        """§6.1-1: 二次执行不产生新行"""
        from meta.scripts.migrate_enums import seed_party_relation_role
        seed_party_relation_role(enum_ds)
        again = seed_party_relation_role(enum_ds)
        assert again == (0, 0)
        assert len(enum_ds.query(
            'SELECT id FROM enum_values WHERE enum_type_id = ?', [_ROLE_DICT_ID],
        )) == 2

    def test_seeded_values_are_system_protected(self, enum_ds):
        """§8: 种子值 is_system=1（extensible 下仍禁改/删）"""
        from meta.scripts.migrate_enums import seed_party_relation_role
        seed_party_relation_role(enum_ds)
        flags = [r['is_system'] for r in enum_ds.query(
            'SELECT is_system FROM enum_values WHERE enum_type_id = ?', [_ROLE_DICT_ID],
        )]
        assert flags and all(f == 1 for f in flags)

    def test_scope_dictionary_seeded_separately(self, enum_ds):
        """§4.3: role_scope 独立字典（3 值，含 both）"""
        from meta.scripts.migrate_enums import seed_party_group_role_scope
        types_created, values_created = seed_party_group_role_scope(enum_ds)
        assert (types_created, values_created) == (1, 3)
        codes = [r['code'] for r in enum_ds.query(
            'SELECT code FROM enum_values WHERE enum_type_id = ? ORDER BY sort_order',
            [_SCOPE_DICT_ID],
        )]
        assert codes == ['customer', 'vendor', 'both']


# ────────────────────────────────────────
# B. role_scope 依赖登记（§4.3）
# ────────────────────────────────────────
class TestRoleScopeDependency:
    def test_both_is_scope_only(self):
        """§4.3: both 是分组侧专有值，不进入角色轴"""
        from meta.scripts.migrate_enums import (
            PARTY_GROUP_ROLE_SCOPE_VALUES, PARTY_RELATION_ROLE_VALUES,
        )
        role_codes = {v[0] for v in PARTY_RELATION_ROLE_VALUES}
        scope_codes = {v[0] for v in PARTY_GROUP_ROLE_SCOPE_VALUES}
        assert 'both' in scope_codes
        assert 'both' not in role_codes

    def test_scope_role_values_are_subset_of_role(self):
        """§4.3: scope 的 customer/vendor 是 role 字典的子集"""
        from meta.scripts.migrate_enums import (
            PARTY_GROUP_ROLE_SCOPE_VALUES, PARTY_RELATION_ROLE_VALUES,
        )
        role_codes = {v[0] for v in PARTY_RELATION_ROLE_VALUES}
        scope_shared = {v[0] for v in PARTY_GROUP_ROLE_SCOPE_VALUES} - {'both'}
        assert scope_shared <= role_codes

    def test_dependency_registered_in_schema_comment(self):
        """§4.3: schema 注释登记子集依赖（yaml.load 会丢注释，故查原文）"""
        text = _raw_text('party_group.yaml')
        assert _ROLE_DICT_ID in text
        assert '不进入角色轴' in text

    def test_scope_value_help_points_to_dictionary(self):
        """§4.3: role_scope 挂 value_help → party_group_role_scope（对称 role 写法）"""
        f = _field('party_group.yaml', 'role_scope')
        src = f['value_help']['source']
        assert src['type'] == 'enum'
        assert src['enum_type_id'] == _SCOPE_DICT_ID
        assert f['value_help']['behavior']['binding_strength'] == 'strict'
        # 内联静态回退保留（3 值，含 both）
        codes = [ev['value'] for ev in f['enum_values']]
        assert codes == ['customer', 'vendor', 'both']


# ────────────────────────────────────────
# C. 镜像行防护（§6.2）
# ────────────────────────────────────────
class TestMirrorGuardService:
    @pytest.fixture()
    def guard_ds(self, tmp_path):
        from meta.core.datasource import (
            _clear_data_source_cache_for_testing, get_data_source,
        )
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file

        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
        ds = get_data_source('sqlite', database=str(tmp_path / 'f3_guard.db'))
        sync_schema_from_meta(ds, [obj])
        ds.execute('CREATE TABLE IF NOT EXISTS parties '
                   '(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)')
        ds.execute('CREATE TABLE IF NOT EXISTS orgs '
                   '(id INTEGER PRIMARY KEY AUTOINCREMENT)')
        ds.execute('CREATE TABLE IF NOT EXISTS party_groups '
                   '(id INTEGER PRIMARY KEY AUTOINCREMENT)')
        insert(ds, 'parties', id=1, name='我方甲')
        insert(ds, 'parties', id=2, name='对手乙')
        insert(ds, 'orgs', id=10)
        insert(ds, 'orgs', id=20)
        yield ds
        _clear_data_source_cache_for_testing()

    @staticmethod
    def _add(ds, party1, party2, role='customer', le_org_id=10):
        insert(ds, 'party_relations',
               party1_id=party1, party2_id=party2, role=role,
               internal_mark='external', le_org_id=le_org_id, status='active')

    def _svc(self, ds):
        from meta.services.party_relation_guard_service import (
            PartyRelationGuardService,
        )
        return PartyRelationGuardService(ds)

    def test_mirror_row_rejected(self, guard_ds):
        """§6.2-7: (A,B,客户,10) 已存在 ⇒ (B,A,客户,10) 被拒"""
        from meta.services.party_relation_guard_service import MirrorRowError
        self._add(guard_ds, 1, 2)
        with pytest.raises(MirrorRowError) as ei:
            self._svc(guard_ds).assert_no_mirror({
                'party1_id': 2, 'party2_id': 1, 'role': 'customer', 'le_org_id': 10,
            })
        msg = str(ei.value)
        assert '反向关系已存在' in msg
        assert '客户' in msg

    def test_reverse_different_role_allowed(self, guard_ds):
        """§6.2-8: 角色不同 ⇒ 放行（双角色两条实例，语义合法）"""
        self._add(guard_ds, 1, 2, role='customer')
        self._svc(guard_ds).assert_no_mirror({
            'party1_id': 2, 'party2_id': 1, 'role': 'vendor', 'le_org_id': 10,
        })

    def test_reverse_different_le_allowed(self, guard_ds):
        """§6.2-9: 法人域不同 ⇒ 放行"""
        self._add(guard_ds, 1, 2, le_org_id=10)
        self._svc(guard_ds).assert_no_mirror({
            'party1_id': 2, 'party2_id': 1, 'role': 'customer', 'le_org_id': 20,
        })

    def test_null_le_not_guarded(self, guard_ds):
        """§6.2-10: le_org_id 空 ⇒ 不参与（与部唯一索引 condition 口径一致）"""
        self._add(guard_ds, 1, 2, le_org_id=None)
        self._svc(guard_ds).assert_no_mirror({
            'party1_id': 2, 'party2_id': 1, 'role': 'customer', 'le_org_id': None,
        })

    def test_update_excludes_self(self, guard_ds):
        """§6.2-11: update 排除自身 ⇒ 原地更新不误伤"""
        self._add(guard_ds, 1, 2, le_org_id=10)
        row_id = guard_ds.query(
            'SELECT id FROM party_relations WHERE party1_id = 1 AND party2_id = 2',
            [],
        )[0]['id']
        self._svc(guard_ds).assert_no_mirror(
            {'party1_id': 1, 'party2_id': 2, 'role': 'customer', 'le_org_id': 10},
            exclude_id=row_id,
        )

    def test_non_mirror_pair_allowed(self, guard_ds):
        """无反向行 ⇒ 放行"""
        self._add(guard_ds, 1, 2, le_org_id=10)
        self._svc(guard_ds).assert_no_mirror({
            'party1_id': 3, 'party2_id': 4, 'role': 'customer', 'le_org_id': 10,
        })

    def test_missing_tuple_parts_short_circuit(self, guard_ds):
        """三要素缺失 ⇒ 不判定（避免误伤）"""
        self._svc(guard_ds).assert_no_mirror({'role': 'customer'})
        self._svc(guard_ds).assert_no_mirror({'party1_id': 1, 'party2_id': 2})


class TestSelfRelationGuard:
    """[2026-10-20] 自反关系（两侧同一单位）恒拒。

    与镜像行分开：镜像 SQL 查反向行，A==B 时查到的就是自己那组 ⇒ 查不到 ⇒ 放行。
    故必须在镜像判定之前单独拦截（第三 tab 与详情入口同样适用）。
    """

    @pytest.fixture()
    def guard_ds(self, tmp_path):
        from meta.core.datasource import (
            _clear_data_source_cache_for_testing, get_data_source,
        )
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file

        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
        ds = get_data_source('sqlite', database=str(tmp_path / 'self_guard.db'))
        sync_schema_from_meta(ds, [obj])
        ds.execute('CREATE TABLE IF NOT EXISTS parties '
                   '(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)')
        ds.execute('CREATE TABLE IF NOT EXISTS orgs '
                   '(id INTEGER PRIMARY KEY AUTOINCREMENT)')
        insert(ds, 'parties', id=1, name='我方甲')
        insert(ds, 'orgs', id=10)
        yield ds
        _clear_data_source_cache_for_testing()

    def _svc(self, ds):
        from meta.services.party_relation_guard_service import (
            PartyRelationGuardService,
        )
        return PartyRelationGuardService(ds)

    def test_self_relation_rejected(self, guard_ds):
        """两侧同为 id=1 ⇒ 拒"""
        from meta.services.party_relation_guard_service import SelfRelationError
        with pytest.raises(SelfRelationError) as ei:
            self._svc(guard_ds).assert_no_mirror({
                'party1_id': 1, 'party2_id': 1, 'role': 'customer', 'le_org_id': 10,
            })
        msg = str(ei.value)
        assert '不能是同一个' in msg
        assert '我方甲' in msg

    def test_self_relation_rejected_without_role_or_le(self, guard_ds):
        """无 role / 无 le_org_id 也拒（自反与这两者无关）"""
        from meta.services.party_relation_guard_service import SelfRelationError
        with pytest.raises(SelfRelationError):
            self._svc(guard_ds).assert_no_mirror(
                {'party1_id': 1, 'party2_id': 1, 'role': None, 'le_org_id': None})

    def test_self_relation_rejected_with_string_id(self, guard_ds):
        """id 传字符串形态（'1' vs 1）同样识别为自反"""
        from meta.services.party_relation_guard_service import SelfRelationError
        with pytest.raises(SelfRelationError):
            self._svc(guard_ds).assert_no_mirror({
                'party1_id': '1', 'party2_id': 1, 'role': 'customer', 'le_org_id': 10,
            })

    def test_distinct_pair_still_allowed(self, guard_ds):
        """非自反对不受影响（守卫不误伤）"""
        self._svc(guard_ds).assert_no_mirror({
            'party1_id': 1, 'party2_id': 2, 'role': 'customer', 'le_org_id': 10,
        })

    def test_self_relation_error_is_distinct_from_mirror(self, guard_ds):
        """自反异常不得混入 MirrorRowError（调用方按类型分流文案/定位字段）"""
        from meta.services.party_relation_guard_service import (
            MirrorRowError, SelfRelationError,
        )
        assert not issubclass(SelfRelationError, MirrorRowError)


class TestMirrorGuardInterceptor:
    @staticmethod
    def _ctx(action, **params):
        from types import SimpleNamespace
        from meta.core.action_context import ActionContext
        return ActionContext(
            meta_object=SimpleNamespace(id='party_relation'),
            action=action,
            params=params,
            data_source=None,
        )

    def test_priority_is_43(self):
        """§4.4: 优先级 43（约束校验 42 之后、层级校验 45 之前）"""
        from meta.core.interceptors.party_relation_guard_interceptor import (
            PartyRelationGuardInterceptor,
        )
        assert PartyRelationGuardInterceptor().priority == 43

    def test_scope_only_party_relation_crud(self):
        """§6.2-12: 仅 party_relation 的 create/update 生效，其余零开销短路"""
        from types import SimpleNamespace
        from meta.core.action_context import ActionContext
        from meta.core.interceptors.party_relation_guard_interceptor import (
            PartyRelationGuardInterceptor,
        )
        ic = PartyRelationGuardInterceptor()
        assert ic.should_execute(self._ctx('crud_create')) is True
        assert ic.should_execute(self._ctx('crud_update')) is True
        assert ic.should_execute(self._ctx('crud_read')) is False

        other = ActionContext(
            meta_object=SimpleNamespace(id='party'),
            action='crud_create', params={}, data_source=None,
        )
        assert ic.should_execute(other) is False

    def test_before_action_raises_validation_error(self, tmp_path):
        """创建命中镜像 ⇒ 抛 ValidationFailedError（可读消息）"""
        from types import SimpleNamespace
        from meta.core.action_context import ActionContext
        from meta.core.datasource import (
            _clear_data_source_cache_for_testing, get_data_source,
        )
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file
        from meta.core.exceptions import ValidationFailedError
        from meta.core.interceptors.party_relation_guard_interceptor import (
            PartyRelationGuardInterceptor,
        )

        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
        ds = get_data_source('sqlite', database=str(tmp_path / 'f3_int.db'))
        try:
            sync_schema_from_meta(ds, [obj])
            ds.execute('CREATE TABLE IF NOT EXISTS parties '
                       '(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)')
            ds.execute('CREATE TABLE IF NOT EXISTS orgs '
                       '(id INTEGER PRIMARY KEY AUTOINCREMENT)')
            ds.execute('CREATE TABLE IF NOT EXISTS party_groups '
                       '(id INTEGER PRIMARY KEY AUTOINCREMENT)')
            insert(ds, 'parties', id=1, name='我方甲')
            insert(ds, 'parties', id=2, name='对手乙')
            insert(ds, 'orgs', id=10)
            insert(ds, 'party_relations',
                   party1_id=1, party2_id=2, role='customer',
                   internal_mark='external', le_org_id=10, status='active')

            ctx = ActionContext(
                meta_object=SimpleNamespace(id='party_relation'),
                action='crud_create',
                params={'party1_id': 2, 'party2_id': 1, 'role': 'customer',
                        'internal_mark': 'external', 'le_org_id': 10},
                data_source=ds,
            )
            with pytest.raises(ValidationFailedError):
                PartyRelationGuardInterceptor().before_action(ctx)
        finally:
            _clear_data_source_cache_for_testing()
