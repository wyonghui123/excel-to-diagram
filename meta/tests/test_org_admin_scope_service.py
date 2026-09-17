# -*- coding: utf-8 -*-
"""
Spec 19 M2 单元测试：OrgAdminScopeService（双钥匙之钥匙二）

覆盖：
- get_delegated_org_rules：规则聚合（id = / id IN / '*' / 空条件）
- expand_org_scope：动态子树展开（多根 / 环防护 / 深层）
- check_org_scope：祖先链命中 / 范围外 / 根级拒绝 / 通配
- check_user_scope：归属命中 / 归属外 / 多组织任一命中
- extract_org_ids_from_params：挂载点提取
"""
import os
import sqlite3
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.org_admin_scope_service import OrgAdminScopeService


@pytest.fixture
def db():
    """最小 schema：orgs 树 + 成员 + 权限集链路"""
    conn = sqlite3.connect(':memory:')
    conn.executescript("""
        CREATE TABLE orgs (
            id INTEGER PRIMARY KEY,
            code TEXT, name TEXT,
            parent_id INTEGER REFERENCES orgs(id),
            manager_id INTEGER
        );
        CREATE TABLE org_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            org_id INTEGER NOT NULL,
            is_manager INTEGER DEFAULT 0,
            UNIQUE(user_id, org_id)
        );
        CREATE TABLE permission_sets (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE,
            name TEXT,
            description TEXT,
            is_system INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0
        );
        CREATE TABLE org_permission_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            permission_set_id INTEGER NOT NULL
        );
        CREATE TABLE data_permission_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            rule_type VARCHAR(50) NOT NULL DEFAULT 'condition',
            resource_type VARCHAR(200),
            condition TEXT,
            is_denied INTEGER DEFAULT 0,
            permission_level VARCHAR(50) DEFAULT 'read',
            expires_at VARCHAR(50)
        );
        -- 组织树: 1根 / 2,3子 / 4(2之子) / 5(4之子)
        INSERT INTO orgs (id, code, name, parent_id) VALUES
            (1, 'ROOT', '根组织', NULL),
            (2, 'A', '组织A', 1),
            (3, 'B', '组织B', 1),
            (4, 'A1', '组织A1', 2),
            (5, 'A11', '组织A11', 4);
    """)
    yield conn
    conn.close()


def _bind_org_rule(db, org_id, permission_set_id, condition):
    db.execute(
        "INSERT OR IGNORE INTO permission_sets (id, code, name) VALUES (?, ?, ?)",
        (permission_set_id, f'PS{permission_set_id}', f'权限集{permission_set_id}'),
    )
    db.execute(
        "INSERT INTO org_permission_sets (org_id, permission_set_id) VALUES (?, ?)",
        (org_id, permission_set_id),
    )
    db.execute(
        "INSERT INTO data_permission_rules (permission_set_id, rule_type, resource_type, condition) "
        "VALUES (?, 'condition', 'org', ?)",
        (permission_set_id, condition),
    )
    db.commit()


def _bind_user_to_org(db, user_id, org_id):
    db.execute(
        "INSERT OR IGNORE INTO org_members (user_id, org_id) VALUES (?, ?)",
        (user_id, org_id),
    )
    db.commit()


# ============== 规则解析 ==============

class TestGetDelegatedOrgRules:
    def test_no_delegation(self, db):
        svc = OrgAdminScopeService(db)
        rules = svc.get_delegated_org_rules(99)
        assert rules == {'wildcard': False, 'root_ids': set(), 'rules': []}

    def test_eq_condition(self, db):
        _bind_org_rule(db, 2, 10, 'id = 2')
        _bind_user_to_org(db, 1, 2)
        svc = OrgAdminScopeService(db)
        rules = svc.get_delegated_org_rules(1)
        assert rules['root_ids'] == {2}
        assert rules['wildcard'] is False

    def test_in_condition(self, db):
        _bind_org_rule(db, 2, 10, 'id IN (2, 3)')
        _bind_user_to_org(db, 1, 2)
        svc = OrgAdminScopeService(db)
        assert svc.get_delegated_org_rules(1)['root_ids'] == {2, 3}

    def test_wildcard_condition(self, db):
        _bind_org_rule(db, 1, 10, '*')
        _bind_user_to_org(db, 1, 1)
        svc = OrgAdminScopeService(db)
        rules = svc.get_delegated_org_rules(1)
        assert rules['wildcard'] is True

    def test_denied_rule_excluded(self, db):
        db.execute(
            "INSERT OR IGNORE INTO permission_sets (id, code, name) VALUES (10, 'PS10', 'p10')"
        )
        db.execute(
            "INSERT INTO data_permission_rules (permission_set_id, rule_type, resource_type, "
            "condition, is_denied) VALUES (10, 'condition', 'org', 'id = 2', 1)"
        )
        db.execute("INSERT INTO org_permission_sets (org_id, permission_set_id) VALUES (1, 10)")
        _bind_user_to_org(db, 1, 1)
        db.commit()
        svc = OrgAdminScopeService(db)
        assert svc.get_delegated_org_rules(1)['root_ids'] == set()


# ============== 子树展开 ==============

class TestExpandOrgScope:
    def test_expand_descendants(self, db):
        svc = OrgAdminScopeService(db)
        assert svc.expand_org_scope({2}) == {2, 4, 5}

    def test_multi_root(self, db):
        svc = OrgAdminScopeService(db)
        assert svc.expand_org_scope({2, 3}) == {2, 3, 4, 5}

    def test_cycle_protection(self, db):
        db.execute("UPDATE orgs SET parent_id = 5 WHERE id = 1")  # 制造环
        db.commit()
        svc = OrgAdminScopeService(db)
        scope = svc.expand_org_scope({1})
        assert scope == {1, 2, 3, 4, 5}  # 不死循环，全覆盖

    def test_dangling_root(self, db):
        svc = OrgAdminScopeService(db)
        assert svc.expand_org_scope({999}) == {999}


# ============== org 校验 ==============

class TestCheckOrgScope:
    def test_target_in_subtree(self, db):
        _bind_org_rule(db, 2, 10, 'id = 2')
        _bind_user_to_org(db, 1, 2)
        svc = OrgAdminScopeService(db)
        ok, _ = svc.check_org_scope(1, 5, 'crud_update')  # 5 是 2 的孙
        assert ok is True

    def test_target_is_root_itself(self, db):
        _bind_org_rule(db, 2, 10, 'id = 2')
        _bind_user_to_org(db, 1, 2)
        svc = OrgAdminScopeService(db)
        ok, _ = svc.check_org_scope(1, 2, 'crud_delete')
        assert ok is True

    def test_target_out_of_subtree(self, db):
        _bind_org_rule(db, 2, 10, 'id = 2')
        _bind_user_to_org(db, 1, 2)
        svc = OrgAdminScopeService(db)
        ok, reason = svc.check_org_scope(1, 3, 'crud_delete')  # 3 是兄弟
        assert ok is False
        assert '不在任何受托子树内' in reason

    def test_root_operation_denied_without_wildcard(self, db):
        _bind_org_rule(db, 2, 10, 'id = 2')
        _bind_user_to_org(db, 1, 2)
        svc = OrgAdminScopeService(db)
        ok, reason = svc.check_org_scope(1, None, 'crud_create')
        assert ok is False

    def test_wildcard_allows_root(self, db):
        _bind_org_rule(db, 1, 10, '*')
        _bind_user_to_org(db, 1, 1)
        svc = OrgAdminScopeService(db)
        ok, reason = svc.check_org_scope(1, None, 'crud_create')
        assert ok is True

    def test_no_delegation_denied(self, db):
        svc = OrgAdminScopeService(db)
        ok, reason = svc.check_org_scope(99, 2, 'crud_update')
        assert ok is False
        assert '无组织管理委托' in reason


# ============== user 校验 ==============

class TestCheckUserScope:
    def test_member_in_scope(self, db):
        _bind_org_rule(db, 2, 10, 'id = 2')
        _bind_user_to_org(db, 1, 2)
        _bind_user_to_org(db, 7, 4)  # 目标用户在 4（2 的子孙）
        svc = OrgAdminScopeService(db)
        ok, _ = svc.check_user_scope(1, 7, 'crud_update')
        assert ok is True

    def test_member_out_of_scope(self, db):
        _bind_org_rule(db, 2, 10, 'id = 2')
        _bind_user_to_org(db, 1, 2)
        _bind_user_to_org(db, 7, 3)  # 目标用户在 3（范围外）
        svc = OrgAdminScopeService(db)
        ok, _ = svc.check_user_scope(1, 7, 'crud_update')
        assert ok is False

    def test_member_multi_org_any_hit(self, db):
        _bind_org_rule(db, 2, 10, 'id = 2')
        _bind_user_to_org(db, 1, 2)
        _bind_user_to_org(db, 7, 3)
        _bind_user_to_org(db, 7, 4)  # 同时归属 3(外) 和 4(内)
        svc = OrgAdminScopeService(db)
        ok, reason = svc.check_user_scope(1, 7, 'crud_update')
        assert ok is True
        assert 'org#4' in reason

    def test_wildcard_member(self, db):
        _bind_org_rule(db, 1, 10, '*')
        _bind_user_to_org(db, 1, 1)
        _bind_user_to_org(db, 7, 3)
        svc = OrgAdminScopeService(db)
        ok, _ = svc.check_user_scope(1, 7, 'crud_delete')
        assert ok is True


# ============== 挂载点提取 ==============

class TestExtractOrgIds:
    def test_parent_id(self):
        assert OrgAdminScopeService.extract_org_ids_from_params({'parent_id': 5}) == [5]

    def test_org_ids_list(self):
        assert OrgAdminScopeService.extract_org_ids_from_params(
            {'org_ids': [1, 2]}) == [1, 2]

    def test_mixed(self):
        params = {'parent_id': 3, 'org_ids': [7], 'name': 'x', 'org_ids_str': ['a']}
        assert OrgAdminScopeService.extract_org_ids_from_params(params) == [3, 7]

    def test_empty(self):
        assert OrgAdminScopeService.extract_org_ids_from_params({}) == []
        assert OrgAdminScopeService.extract_org_ids_from_params(None) == []
