# -*- coding: utf-8 -*-
"""F1 §5.2 护栏 1「读 ⊆ 管」对齐巡检测试（§9.3 收口，口径 α）

依据: docs/superpowers/specs/2026-10-04-f1-governance-domain-design.md
      §5.2 护栏 1（治理域读取范围 ⊆ 管理范围；防"看得见却改不动"漂移）/ §9.3

口径 α（对齐断言）：
  对同一用户 u：
    read_scope(u)   = 其各角色的 org 维度范围并集（子树展开）
    manage_scope(u) = OrgAdminScopeService.get_manageable_org_ids(u)
                    （None=通配 / set()=无委托 / set=具体）
  断言：具体范围下 read_scope(u) ⊆ manage_scope(u)；通配管覆盖任意具体读。

三态口径详见 §5.2 护栏 3（本文件仅覆盖护栏 1 的具体范围子集关系）。
"""
import json
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.factories._dimension_scope_engine_helpers import (
    make_scope_alignment_ds,
    seed_aligned_role,
)

pytestmark = pytest.mark.unit

USER_ID = 7


# ---------------- 口径实现（巡检落点，§9.3） ----------------

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


# ---------------- 测试 ----------------

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