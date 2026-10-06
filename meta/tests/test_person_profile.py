# -*- coding: utf-8 -*-
"""person 面一期（person_profile + user 接线）测试 (2026-10-05)

依据: docs/superpowers/specs/2026-10-05-person-profile-and-user-wiring-design.md
      (§3.1 对象设计 / §3.2 权限域 / §3.3 user 接线 / §6 AC-1..AC-9；v1.2 字段收缩)
      S2 + S4 合并为本文件（一期新增 = 2 文件：schema + 测试）

覆盖:
1. 结构        : person_profiles 字段集 {id, party_id, mobile, email}；party_id required+unique；
                  users.party_id nullable 非唯一；索引 idx_person_profile_party_unique / idx_user_party
2. 审计排除口径: mobile/email 在 create/update/delete 三处 exclude；party_id 不在任何 exclude（接线留痕）
3. AC-1 端到端 : 重复 party_id 插入被拒；命名唯一索引存在；缺 party_id 插入被拒（NOT NULL）
4. AC-4 端到端 : 无 party_id 的账号可存续；同 party_id 可挂多账号（user 侧不唯一）
5. AC-3        : PII 不出现在 party_archive / party_internal 视图（列 + view_definition）
6. AC-5        : 5 个动作码显式声明 + auto_crud: false（加载后动作码集合恰为 5 个）
7. AC-7 负向   : mobile/email 不在 SENSITIVE_FIELDS（两处硬编码集合）—— 未脱敏现状如实固定
8. AC-9 负向   : 平台元模型无字段级权限位（SemanticAnnotation 无 permission 类字段）

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db;
         DML 走 ds.insert API（本文件无裸写语句 —— conftest raw-SQL 守卫）
"""
import dataclasses
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

pytestmark = pytest.mark.unit

_FACET_FILES = ['party_archive.yaml', 'party_internal.yaml']


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_yaml(name):
    import yaml
    with open(os.path.join(_SCHEMA_DIR, name), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _pp_yaml():
    return _load_yaml('person_profile.yaml')


def _fields(data=None):
    return {f['id']: f for f in (data if data is not None else _pp_yaml())['fields']}


def _exclude(mode):
    return set((_pp_yaml().get('audit', {}).get(mode) or {}).get('exclude') or [])


# ────────────────────────────────────────
# 夹具（aspects 按平台路径解析，沿 F4 先例）
# ────────────────────────────────────────
@pytest.fixture()
def pp_ds(tmp_path):
    """临时库: 仅建 person_profiles 表 + 索引"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'person_profile.yaml'),
                         aspects_defs=aspects)
    assert obj is not None, 'person_profile.yaml 加载失败'

    ds = get_data_source("sqlite", database=str(tmp_path / 'person_profile.db'))
    sync_schema_from_meta(ds, [obj])
    yield ds
    _clear_data_source_cache_for_testing()


@pytest.fixture()
def user_ds(tmp_path):
    """临时库: 仅建 users 表 + 索引"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'user.yaml'),
                         aspects_defs=aspects)
    assert obj is not None, 'user.yaml 加载失败'

    ds = get_data_source("sqlite", database=str(tmp_path / 'user_party.db'))
    sync_schema_from_meta(ds, [obj])
    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 1. 结构：字段与约束（§3.1 / §3.3）
# ────────────────────────────────────────
class TestStructure:
    def test_identity_and_table(self):
        data = _pp_yaml()
        assert data['id'] == 'person_profile'
        assert data['table_name'] == 'person_profiles'

    def test_field_set(self):
        """v1.2 范围收缩：gender / birth_date 移除后字段集恰为四列"""
        assert set(_fields()) == {'id', 'party_id', 'mobile', 'email'}

    def test_party_id_required_unique_integer(self):
        f = _fields()['party_id']
        assert f['type'] == 'integer'
        assert f['required'] is True
        assert f['unique'] is True

    def test_mobile_email_nullable_lengths(self):
        fields = _fields()
        assert fields['mobile'].get('nullable') is True
        assert fields['mobile'].get('max_length') == 32
        assert fields['email'].get('nullable') is True
        assert fields['email'].get('max_length') == 200

    def test_aspects_declared_no_top_semantics(self):
        data = _pp_yaml()
        assert data.get('aspects') == ['audit_aspect']
        assert 'semantics' not in data

    def test_no_sensitivity_marking(self):
        """§0.1 错误 1：敏感级不落在任何平台字段（data_category 是数据类型非敏感度）"""
        for fid, f in _fields().items():
            sem = f.get('semantics') or {}
            assert 'sensitivity' not in sem, fid

    def test_unique_index_declared(self):
        idxs = [i for i in (_pp_yaml().get('indexes') or []) if i.get('unique')]
        assert len(idxs) == 1, '应恰有一个唯一索引'
        assert idxs[0]['fields'] == ['party_id']
        assert idxs[0]['name'] == 'idx_person_profile_party_unique'


# ────────────────────────────────────────
# 2. 审计排除口径（PII 不入审计；party_id 留痕）
# ────────────────────────────────────────
class TestAuditExclusion:
    def test_pii_excluded_in_all_modes(self):
        """create 也必须显式排除（exclude 对全模式统一过滤，防 PII 明文落审计）"""
        for mode in ('create', 'update', 'delete'):
            assert {'mobile', 'email'} <= _exclude(mode), mode

    def test_mode_fields_declared(self):
        audit = _pp_yaml()['audit']
        assert audit['create']['fields'] == 'all'
        assert audit['update']['fields'] == 'changed_only'
        assert audit['delete']['fields'] == 'business_only'

    def test_party_id_not_excluded_anywhere(self):
        """裁定：party_id 不入 exclude（接线留痕，含删除时最后指向；值非敏感）"""
        for mode in ('create', 'update', 'delete'):
            assert 'party_id' not in _exclude(mode), mode


# ────────────────────────────────────────
# 3. AC-1：1:1 UNIQUE 与 NOT NULL（端到端）
# ────────────────────────────────────────
class TestPartyUniqueEnforced:
    def test_index_created(self, pp_ds):
        names = {r[1] for r in pp_ds.execute(
            "PRAGMA index_list('person_profiles')").fetchall()}
        assert 'idx_person_profile_party_unique' in names

    def test_aspect_columns_resolved(self, pp_ds):
        """aspects 展开: created_at 落列；updated_at 为 virtual 不落列（region 教训）"""
        cols = {r[1] for r in pp_ds.execute(
            "PRAGMA table_info('person_profiles')").fetchall()}
        assert 'created_at' in cols
        assert 'updated_at' not in cols

    def test_duplicate_party_id_rejected(self, pp_ds):
        pp_ds.insert('person_profiles', {'id': 1, 'party_id': 100})
        with pytest.raises(Exception):
            pp_ds.insert('person_profiles', {'id': 2, 'party_id': 100})

    def test_missing_party_id_rejected(self, pp_ds):
        with pytest.raises(Exception):
            pp_ds.insert('person_profiles', {'id': 1})

    def test_distinct_party_id_allowed(self, pp_ds):
        pp_ds.insert('person_profiles', {'id': 1, 'party_id': 100})
        pp_ds.insert('person_profiles', {'id': 2, 'party_id': 101})
        cnt = pp_ds.execute(
            'SELECT COUNT(*) FROM person_profiles').fetchone()[0]
        assert cnt == 2

    def test_pii_values_stored(self, pp_ds):
        pp_ds.insert('person_profiles', {'id': 1, 'party_id': 100,
                                         'mobile': '13800000000',
                                         'email': 'a@example.com'})
        row = pp_ds.execute(
            'SELECT mobile, email FROM person_profiles').fetchone()
        assert row[0] == '13800000000'
        assert row[1] == 'a@example.com'


# ────────────────────────────────────────
# 4. AC-4：users.party_id 可空、非唯一（端到端）
# ────────────────────────────────────────
class TestUserPartyWiring:
    def test_party_id_nullable_non_unique_in_yaml(self):
        fields = {f['id']: f for f in _load_yaml('user.yaml')['fields']}
        f = fields['party_id']
        assert f['type'] == 'integer'
        assert f.get('nullable') is True
        assert not f.get('unique'), 'user 侧不唯一：一人可多账号'

    def test_index_declared_non_unique(self):
        idxs = _load_yaml('user.yaml')['indexes']
        party_idx = [i for i in idxs if i['fields'] == ['party_id']]
        assert len(party_idx) == 1, '应恰有一个 party_id 索引'
        assert party_idx[0].get('unique') in (None, False)
        assert party_idx[0]['name'] == 'idx_user_party'

    def test_index_created(self, user_ds):
        names = {r[1] for r in user_ds.execute(
            "PRAGMA index_list('users')").fetchall()}
        assert 'idx_user_party' in names

    def test_account_without_party_survives(self, user_ds):
        """既有无 party 账号（admin / service）可存续"""
        user_ds.insert('users', {'id': 1, 'username': 'admin',
                                 'email': 'admin@example.com',
                                 'display_name': 'Admin'})
        row = user_ds.execute(
            'SELECT party_id FROM users WHERE id = 1').fetchone()
        assert row[0] is None

    def test_multiple_accounts_share_one_party(self, user_ds):
        """一人可持多账号（本地 + SSO）⇒ 允许多账号指向同一 party"""
        user_ds.insert('users', {'id': 1, 'username': 'local_a',
                                 'email': 'a@example.com',
                                 'display_name': 'A', 'party_id': 500})
        user_ds.insert('users', {'id': 2, 'username': 'sso_b',
                                 'email': 'b@example.com',
                                 'display_name': 'B', 'party_id': 500})
        cnt = user_ds.execute(
            'SELECT COUNT(*) FROM users WHERE party_id = 500').fetchone()[0]
        assert cnt == 2

    def test_party_id_not_in_audit_exclude(self):
        """接线留痕裁定：party_id 有意不入 user 侧 update/delete exclude"""
        audit = _load_yaml('user.yaml')['audit']
        for mode in ('update', 'delete'):
            ex = set(audit[mode].get('exclude') or [])
            assert 'party_id' not in ex, mode


# ────────────────────────────────────────
# 5. AC-3：两个读面不暴露 PII（D6-A）
# ────────────────────────────────────────
class TestReadFacetsNoPii:
    @pytest.mark.parametrize('yaml_name', _FACET_FILES)
    def test_view_fields_exclude_pii(self, yaml_name):
        field_ids = {f['id'] for f in _load_yaml(yaml_name)['fields']}
        assert 'mobile' not in field_ids
        assert 'email' not in field_ids

    @pytest.mark.parametrize('yaml_name', _FACET_FILES)
    def test_view_definition_exclude_pii(self, yaml_name):
        vd = _load_yaml(yaml_name)['view_definition']
        assert 'mobile' not in vd
        assert 'email' not in vd


# ────────────────────────────────────────
# 6. AC-5：独立动作码（独立功能权限域，D3a-A）
# ────────────────────────────────────────
class TestActionCodes:
    _EXPECTED = {
        'person_profile_create', 'person_profile_read', 'person_profile_update',
        'person_profile_delete', 'person_profile_list',
    }

    def test_five_actions_declared(self):
        ids = {a['id'] for a in _pp_yaml()['actions']}
        assert ids == self._EXPECTED

    def test_auto_crud_declared_false(self):
        """声明性意图（parse_import_export_config 未消费该键，沿 audit_log / party 惯例）"""
        assert _pp_yaml()['import_export']['auto_crud'] is False

    def test_loaded_object_actions_exactly_declared(self):
        """加载后动作码集合恰为 5 个（显式声明 ⇒ 不自动补）"""
        from meta.core.yaml_loader import load_yaml_file
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'person_profile.yaml'))
        assert obj is not None
        assert {a.id for a in obj.actions} == self._EXPECTED


# ────────────────────────────────────────
# 7. AC-7 负向：PII 当前不会被自动脱敏（如实固定，防误判已实现）
# ────────────────────────────────────────
class TestNoPiiRedaction:
    def test_not_in_sensitive_fields_action_models(self):
        from meta.core.action_models import SENSITIVE_FIELDS
        assert 'mobile' not in SENSITIVE_FIELDS
        assert 'email' not in SENSITIVE_FIELDS

    def test_not_in_sensitive_fields_config_constants(self):
        from meta.core.ui_config.config_constants import SENSITIVE_FIELDS
        assert 'mobile' not in SENSITIVE_FIELDS
        assert 'email' not in SENSITIVE_FIELDS


# ────────────────────────────────────────
# 8. AC-9 负向：平台元模型无字段级权限位（对象级隔离的上限如实固定）
# ────────────────────────────────────────
class TestNoFieldLevelPermission:
    _PERMISSION_LIKE = (
        'permission', 'security_level', 'security_domain', 'access_level',
        'access_control', 'read_permission', 'write_permission',
        'field_level_security',
    )

    def test_semantic_annotation_has_no_permission_field(self):
        from meta.core.models_annotations import SemanticAnnotation
        names = {f.name for f in dataclasses.fields(SemanticAnnotation)}
        hit = {n for n in names
               if any(p in n for p in self._PERMISSION_LIKE)}
        assert hit == set(), (
            '元模型出现字段级权限位，需重估 D3b / TBD-9: %s' % sorted(hit)
        )