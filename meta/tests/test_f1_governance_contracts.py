# -*- coding: utf-8 -*-
"""F1 治理域契约测试（对外档案接线 / 读 ⊆ 管范围对齐）。

[TEST-EFF P2-1] 由两个同域（F1 治理域，纯 YAML + 内存 DS）的 <=5 用例小文件合并：
- test_f1_item_xref_party_wiring.py    (item_xref.partner_id → party_archive)
- test_f1_read_write_scope_alignment.py (§5.2 护栏 1 巡检)

依据: docs/superpowers/specs/2026-10-04-f1-governance-domain-design.md
"""

import json
import os
import sys

import pytest
import yaml

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.factories._dimension_scope_engine_helpers import (  # noqa: E402
    make_scope_alignment_ds,
    seed_aligned_role,
)

pytestmark = pytest.mark.unit

_SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas'
)


# ===========================================================================
# 一、item_xref.partner_id → party 对外档案面（value_help）
# ===========================================================================
# 口径：
#   - 外部标识（客户/供应商/制造商件号）的伙伴 = **对外伙伴** ⇒ value_help 目标 = `party_archive`
#     （视图谓词 COALESCE(source,'') <> 'org'，结构强制排除内部组织表示）。
#   - 不得指向写锚 `party`（无口径）或内部面 `party_internal`（内部表示须走 intra_trade 受控放行）。
#   - partner_type（客户/供应商/制造商）属角色层（命名待 F2），未建前不做过滤。

def _load_raw(bo_id):
    with open(os.path.join(_SCHEMA_DIR, bo_id + '.yaml'), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get('fields') or []:
        if f.get('id') == field_id:
            return f
    return None


class TestPartnerIdValueHelpWiring:
    def test_target_is_archive_face(self):
        """partner_id 的 value_help 目标 = 对外档案面 party_archive。"""
        field = _field(_load_raw('item_xref'), 'partner_id')
        assert field is not None
        source = (field.get('value_help') or {}).get('source') or {}
        assert source.get('type') == 'bo'
        assert source.get('target_bo') == 'party_archive'
        assert source.get('value_field') == 'id'
        assert source.get('display_field') == 'name'
        assert source.get('apply_target_permissions') is True

    def test_display_and_ui_wired(self):
        """关联展示 + 选择控件已接线（不再是裸整数 input）。"""
        field = _field(_load_raw('item_xref'), 'partner_id')
        display = (field.get('semantics') or {}).get('display') or {}
        assert display.get('type') == 'association'
        assert display.get('target_type') == 'party_archive'
        assert display.get('display_field') == 'name'
        ui = field.get('ui') or {}
        assert ui.get('widget') == 'select'
        assert ui.get('relation') == 'party_archive'
        assert ui.get('multiple') is False

    def test_target_bo_not_base_or_internal(self):
        """红线：不得指向写锚 party 或内部面 party_internal（F1 治理分域）。"""
        field = _field(_load_raw('item_xref'), 'partner_id')
        target = (field.get('value_help') or {}).get('source', {}).get('target_bo')
        assert target not in ('party', 'party_internal')

    def test_target_face_is_view_excluding_org_with_anchor_writes(self):
        """目标面确为对外档案：真视图 + NULL 安全排除 source='org'。

        写动作不是本面自写：`write_anchor: party` 使 create/update/delete 转发到身份锚，
        故动作集为读 + 写转发（F1 §7.1-6；对齐 test_f1_party_view_facets 的动作策略）。
        """
        archive = _load_raw('party_archive')
        assert archive.get('object_type') == 'view'
        view_def = archive.get('view_definition') or ''
        assert 'parties' in view_def
        assert "COALESCE(source, '') <> 'org'" in view_def
        assert archive.get('write_anchor') == 'party'
        action_ids = {a.get('id') for a in (archive.get('actions') or [])}
        assert action_ids == {
            'party_archive_read', 'party_archive_list',
            'party_archive_create', 'party_archive_update',
            'party_archive_delete'}
        assert archive.get('import_export', {}).get('auto_crud') is False


# ===========================================================================
# 二、F1 §5.2 护栏 1「读 ⊆ 管」对齐巡检（§9.3 收口，口径 α）
# ===========================================================================
# 口径 α（对齐断言）：
#   对同一用户 u：
#     read_scope(u)   = 其各角色的 org 维度范围并集（子树展开）
#     manage_scope(u) = OrgAdminScopeService.get_manageable_org_ids(u)
#                     （None=通配 / set()=无委托 / set=具体）
#   断言：具体范围下 read_scope(u) ⊆ manage_scope(u)；通配管覆盖任意具体读。

USER_ID = 7


def _parse_org_values(raw):
    """解析 permission_set_dimension_scopes.dimension_values 为 org id 集合。"""
    if not raw:
        return set()
    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return set()
    if not isinstance(parsed, list):
        parsed = [parsed]
    ids = set()
    for value in parsed:
        text = str(value).strip().strip("'\"")
        if text.isdigit():
            ids.add(int(text))
    return ids


def read_org_scope(ds, user_id):
    """读范围（治理域读取范围）= 用户各角色的 org 维度范围并集（子树展开）。"""
    from meta.services.permission_service import PermissionService
    from meta.services.org_admin_scope_service import OrgAdminScopeService

    expander = OrgAdminScopeService(ds)
    scope = set()
    for role in PermissionService(ds).get_user_permission_sets(user_id):
        cursor = ds.execute(
            "SELECT dimension_values, inherit_children "
            "FROM permission_set_dimension_scopes "
            "WHERE permission_set_id = ? AND dimension_code = 'org'",
            [role['id']],
        )
        for values, inherit in cursor.fetchall():
            ids = _parse_org_values(values)
            scope |= expander.expand_org_scope(ids) if inherit else ids
    return scope


def manage_org_scope(ds, user_id):
    """管理范围（钥匙二）= OrgAdminScopeService.get_manageable_org_ids。

    None 表示通配（全组织）。
    """
    from meta.services.org_admin_scope_service import OrgAdminScopeService

    return OrgAdminScopeService(ds).get_manageable_org_ids(user_id)


def check_alignment(ds, user_id):
    """对齐巡检：返回漂移清单（不阻断）。

    aligned = 具体范围下 read ⊆ manage，或 manage 通配。
    """
    read = read_org_scope(ds, user_id)
    manage = manage_org_scope(ds, user_id)
    if manage is None:  # 通配管覆盖任意具体读
        return {'aligned': True, 'drift': [], 'read': read, 'manage': None}
    drift = sorted(read - manage)
    return {'aligned': not drift, 'drift': drift, 'read': read, 'manage': manage}


@pytest.fixture
def ds():
    gen = make_scope_alignment_ds()
    conn_ds = next(gen)
    yield conn_ds
    try:
        next(gen)
    except StopIteration:
        pass


class TestReadSubsetManage:
    def test_aligned_config_has_no_drift(self, ds):
        """读 {2}（子树 {2,3}）与管理 'id = 2'（子树 {2,3}）对齐。"""
        seed_aligned_role(ds, 100, 2, USER_ID, [2], 'id = 2')
        assert read_org_scope(ds, USER_ID) == {2, 3}
        assert manage_org_scope(ds, USER_ID) == {2, 3}
        result = check_alignment(ds, USER_ID)
        assert result['aligned'] is True
        assert result['drift'] == []

    def test_read_exceeds_manage_is_drift(self, ds):
        """读含 {4} 但管理范围 {1,2,3} ⇒ 漂移 = {4}（看得见却改不动）。"""
        seed_aligned_role(ds, 100, 2, USER_ID, [2], 'id = 2')   # 读 {2,3}/管 {2,3}
        seed_aligned_role(ds, 101, 1, USER_ID, [4], 'id = 1')   # 读 {4}/管 {1,2,3}
        result = check_alignment(ds, USER_ID)
        assert result['read'] == {2, 3, 4}
        assert result['manage'] == {1, 2, 3}
        assert result['aligned'] is False
        assert result['drift'] == [4]

    def test_empty_read_and_manage_aligned(self, ds):
        """无角色用户：read = set() ⊆ manage = set()（空集对齐）。"""
        result = check_alignment(ds, 99)
        assert result['read'] == set()
        assert result['manage'] == set()
        assert result['aligned'] is True

    def test_manage_wildcard_covers_read(self, ds):
        """管理通配（'*'）覆盖任意具体读范围。"""
        seed_aligned_role(ds, 102, 2, USER_ID, [2], '*')
        result = check_alignment(ds, USER_ID)
        assert result['read'] == {2, 3}
        assert result['manage'] is None
        assert result['aligned'] is True
