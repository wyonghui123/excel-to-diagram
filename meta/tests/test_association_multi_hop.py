# -*- coding: utf-8 -*-
"""
P12 unit tests: Association multi-hop permission scenarios.

Covers permission chains across the full 6-level hierarchy:
  product -> version -> domain -> sub_domain -> service_module -> business_object

Tests user->group->role->data_perm multi-hop chains and owner inheritance
across multiple hierarchy levels.
"""
import pytest

pytestmark = pytest.mark.integration

import sys
import os
import sqlite3
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.data_permission_service import DataPermissionService


# ============== Helpers ==============

def _insert_user(ds, username='u'):
    ds.execute("INSERT INTO users (username) VALUES (?)", [username])
    return ds.execute("SELECT id FROM users WHERE username = ?", [username]).fetchone()[0]


def _insert_group(ds, code='g1', name='Group1'):
    ds.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)", [code, name])
    return ds.execute("SELECT id FROM user_groups WHERE code = ?", [code]).fetchone()[0]


def _insert_group_member(ds, user_id, group_id, is_manager=0):
    ds.execute(
        "INSERT OR IGNORE INTO user_group_members (user_id, group_id, is_manager) VALUES (?, ?, ?)",
        [user_id, group_id, is_manager]
    )


def _insert_role(ds, code='r1', name='Role1', priority=10):
    ds.execute("INSERT INTO roles (code, name, priority) VALUES (?, ?, ?)", [code, name, priority])
    return ds.execute("SELECT id FROM roles WHERE code = ?", [code]).fetchone()[0]


def _insert_group_role(ds, group_id, role_id):
    ds.execute(
        "INSERT OR IGNORE INTO group_roles (group_id, role_id) VALUES (?, ?)",
        [group_id, role_id]
    )


def _insert_product(ds, name='P1', code='p1', owner_id=None, created_by=None):
    ds.execute(
        "INSERT INTO products (name, code, owner_id, created_by) VALUES (?, ?, ?, ?)",
        [name, code, owner_id, created_by]
    )
    return ds.execute("SELECT id FROM products WHERE code = ?", [code]).fetchone()[0]


def _insert_version(ds, name='V1', code='v1', product_id=None, owner_id=None, created_by=None):
    ds.execute(
        "INSERT INTO versions (name, code, product_id, owner_id, created_by) VALUES (?, ?, ?, ?, ?)",
        [name, code, product_id, owner_id, created_by]
    )
    return ds.execute("SELECT id FROM versions WHERE code = ?", [code]).fetchone()[0]


def _insert_domain(ds, name='D1', code='d1', version_id=None, owner_id=None, created_by=None):
    ds.execute(
        "INSERT INTO domains (name, domain_name, code, version_id, owner_id, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        [name, name, code, version_id, owner_id, created_by]
    )
    return ds.execute("SELECT id FROM domains WHERE code = ?", [code]).fetchone()[0]


def _insert_sub_domain(ds, name='SD1', code='sd1', domain_id=None, owner_id=None, created_by=None):
    ds.execute(
        "INSERT INTO sub_domains (name, sub_domain_name, code, domain_id, owner_id, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        [name, name, code, domain_id, owner_id, created_by]
    )
    return ds.execute("SELECT id FROM sub_domains WHERE code = ?", [code]).fetchone()[0]


def _insert_service_module(ds, name='SM1', code='sm1', sub_domain_id=None, owner_id=None, created_by=None):
    ds.execute(
        "INSERT INTO service_modules (name, module_name, code, sub_domain_id, owner_id, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        [name, name, code, sub_domain_id, owner_id, created_by]
    )
    return ds.execute("SELECT id FROM service_modules WHERE code = ?", [code]).fetchone()[0]


def _insert_business_object(ds, name='BO1', code='bo1', service_module_id=None, owner_id=None, created_by=None):
    ds.execute(
        "INSERT INTO business_objects (name, object_name, code, service_module_id, owner_id, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        [name, name, code, service_module_id, owner_id, created_by]
    )
    return ds.execute("SELECT id FROM business_objects WHERE code = ?", [code]).fetchone()[0]


# ============== Fixtures ==============

@pytest.fixture
def ds():
    """Full 6-level hierarchy schema with 3 permission tables."""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT
        );
        CREATE TABLE user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        );
        CREATE TABLE user_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            is_manager INTEGER DEFAULT 0,
            UNIQUE(user_id, group_id)
        );
        CREATE TABLE roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            is_system INTEGER DEFAULT 0
        );
        CREATE TABLE group_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            created_by INTEGER,
            UNIQUE(group_id, role_id)
        );

        -- 6-level hierarchy
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT,
            created_by INTEGER, owner_id INTEGER
        );
        CREATE TABLE versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT, product_id INTEGER,
            created_by INTEGER, owner_id INTEGER
        );
        CREATE TABLE domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, domain_name TEXT, code TEXT,
            version_id INTEGER,
            created_by INTEGER, owner_id INTEGER
        );
        CREATE TABLE sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, sub_domain_name TEXT, code TEXT,
            domain_id INTEGER,
            created_by INTEGER, owner_id INTEGER
        );
        CREATE TABLE service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, module_name TEXT, code TEXT,
            sub_domain_id INTEGER,
            created_by INTEGER, owner_id INTEGER
        );
        CREATE TABLE business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, object_name TEXT, code TEXT,
            service_module_id INTEGER,
            created_by INTEGER, owner_id INTEGER
        );

        -- 3 permission tables
        CREATE TABLE data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resource_type TEXT,
            resource_id INTEGER,
            permission_level TEXT,
            inherit_to_children INTEGER DEFAULT 1
        );
        CREATE TABLE role_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            resource_type TEXT,
            resource_id INTEGER,
            permission_level TEXT,
            inherit_to_children INTEGER DEFAULT 1,
            created_by INTEGER
        );
        CREATE TABLE group_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            resource_type TEXT,
            resource_id INTEGER,
            permission_level TEXT,
            inherit_to_children INTEGER DEFAULT 1,
            is_deprecated INTEGER DEFAULT 1
        );

        -- hierarchy config
        CREATE TABLE hierarchies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT,
            filter_param TEXT
        );
        INSERT INTO hierarchies (code, name, filter_param) VALUES
            ('product', 'Product', 'product_id'),
            ('version', 'Version', 'version_id'),
            ('domain', 'Domain', 'domain_id'),
            ('sub_domain', 'SubDomain', 'sub_domain_id'),
            ('service_module', 'ServiceModule', 'service_module_id'),
            ('business_object', 'BusinessObject', 'business_object_id');
    """)
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection
        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor
        def commit(self):
            self._conn.commit()

    yield MockDS(conn)
    conn.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def svc(ds):
    return DataPermissionService(ds)


# ============== A. Multi-hop resource path building ==============

def test_resource_path_6_level_chain(svc, ds):
    """_build_resource_path: product->version->domain->sub_domain->sm->bo = 6 entries."""
    p = _insert_product(ds, 'P1', 'p1')
    v = _insert_version(ds, 'V1', 'v1', product_id=p)
    d = _insert_domain(ds, 'D1', 'd1', version_id=v)
    sd = _insert_sub_domain(ds, 'SD1', 'sd1', domain_id=d)
    sm = _insert_service_module(ds, 'SM1', 'sm1', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BO1', 'bo1', service_module_id=sm)

    path = svc._build_resource_path('business_object', bo)
    assert len(path) == 6
    assert path[0]['type'] == 'product'
    assert path[1]['type'] == 'version'
    assert path[2]['type'] == 'domain'
    assert path[3]['type'] == 'sub_domain'
    assert path[4]['type'] == 'service_module'
    assert path[5]['type'] == 'business_object'


def test_resource_path_3_level_sub_domain(svc, ds):
    """_build_resource_path: product->version->domain->sub_domain = 4 entries."""
    p = _insert_product(ds, 'P2', 'p2')
    v = _insert_version(ds, 'V2', 'v2', product_id=p)
    d = _insert_domain(ds, 'D2', 'd2', version_id=v)
    sd = _insert_sub_domain(ds, 'SD2', 'sd2', domain_id=d)

    path = svc._build_resource_path('sub_domain', sd)
    assert len(path) == 4
    assert path[0]['type'] == 'product'
    assert path[-1]['id'] == sd


def test_resource_path_top_level_product(svc, ds):
    """_build_resource_path: product (no parent) = 1 entry."""
    p = _insert_product(ds, 'P3', 'p3')
    path = svc._build_resource_path('product', p)
    assert len(path) == 1
    assert path[0]['type'] == 'product'
    assert path[0]['id'] == p


def test_resource_path_version_only(svc, ds):
    """_build_resource_path: product->version = 2 entries."""
    p = _insert_product(ds, 'P4', 'p4')
    v = _insert_version(ds, 'V4', 'v4', product_id=p)
    path = svc._build_resource_path('version', v)
    assert len(path) == 2
    assert path[0]['type'] == 'product'
    assert path[1]['type'] == 'version'


def test_resource_path_service_module_middle(svc, ds):
    """_build_resource_path: product->version->domain->sub_domain->sm = 5 entries."""
    p = _insert_product(ds, 'P5', 'p5')
    v = _insert_version(ds, 'V5', 'v5', product_id=p)
    d = _insert_domain(ds, 'D5', 'd5', version_id=v)
    sd = _insert_sub_domain(ds, 'SD5', 'sd5', domain_id=d)
    sm = _insert_service_module(ds, 'SM5', 'sm5', sub_domain_id=sd)

    path = svc._build_resource_path('service_module', sm)
    assert len(path) == 5
    assert path[0]['type'] == 'product'
    assert path[-1]['id'] == sm


# ============== B. Multi-hop parent visibility (upward propagation) ==============

def test_parent_visibility_1_hop_sm_to_sd(svc, ds):
    """parent_visibility: write on SM -> read visible on parent SD (1 hop)."""
    uid = _insert_user(ds, 'vis_user1')
    p = _insert_product(ds, 'PV1', 'pv1')
    v = _insert_version(ds, 'VV1', 'vv1', product_id=p)
    d = _insert_domain(ds, 'DV1', 'dv1', version_id=v)
    sd = _insert_sub_domain(ds, 'SDV1', 'sdv1', domain_id=d)
    sm = _insert_service_module(ds, 'SMV1', 'smv1', sub_domain_id=sd)

    svc.add_data_permission(uid, 'service_module', sm, 'write', inherit_to_children=False)

    level = svc.get_effective_permission_level(uid, 'sub_domain', sd)
    assert level == 'read'


def test_parent_visibility_2_hop_sm_to_domain(svc, ds):
    """parent_visibility: write on SM -> read visible on domain (2 hops)."""
    uid = _insert_user(ds, 'vis_user2')
    p = _insert_product(ds, 'PV2', 'pv2')
    v = _insert_version(ds, 'VV2', 'vv2', product_id=p)
    d = _insert_domain(ds, 'DV2', 'dv2', version_id=v)
    sd = _insert_sub_domain(ds, 'SDV2', 'sdv2', domain_id=d)
    sm = _insert_service_module(ds, 'SMV2', 'smv2', sub_domain_id=sd)

    svc.add_data_permission(uid, 'service_module', sm, 'write', inherit_to_children=False)

    level = svc.get_effective_permission_level(uid, 'domain', d)
    assert level == 'read'


def test_parent_visibility_3_hop_sm_to_version(svc, ds):
    """parent_visibility: write on SM -> read visible on version (3 hops)."""
    uid = _insert_user(ds, 'vis_user3')
    p = _insert_product(ds, 'PV3', 'pv3')
    v = _insert_version(ds, 'VV3', 'vv3', product_id=p)
    d = _insert_domain(ds, 'DV3', 'dv3', version_id=v)
    sd = _insert_sub_domain(ds, 'SDV3', 'sdv3', domain_id=d)
    sm = _insert_service_module(ds, 'SMV3', 'smv3', sub_domain_id=sd)

    svc.add_data_permission(uid, 'service_module', sm, 'write', inherit_to_children=False)

    level = svc.get_effective_permission_level(uid, 'version', v)
    assert level == 'read'


def test_parent_visibility_4_hop_bo_to_product(svc, ds):
    """parent_visibility: write on BO -> read visible on product (4 hops up)."""
    uid = _insert_user(ds, 'vis_user4')
    p = _insert_product(ds, 'PV4', 'pv4')
    v = _insert_version(ds, 'VV4', 'vv4', product_id=p)
    d = _insert_domain(ds, 'DV4', 'dv4', version_id=v)
    sd = _insert_sub_domain(ds, 'SDV4', 'sdv4', domain_id=d)
    sm = _insert_service_module(ds, 'SMV4', 'smv4', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOV4', 'bov4', service_module_id=sm)

    svc.add_data_permission(uid, 'business_object', bo, 'write', inherit_to_children=False)

    level = svc.get_effective_permission_level(uid, 'product', p)
    assert level == 'read'


# ============== C. Multi-hop inherit_to_children (downward propagation) ==============

def test_inherit_1_hop_product_to_version(svc, ds):
    """inherit_to_children: write on product -> write on version (1 hop down)."""
    uid = _insert_user(ds, 'inh_user1')
    p = _insert_product(ds, 'PI1', 'pi1')
    v = _insert_version(ds, 'VI1', 'vi1', product_id=p)

    svc.add_data_permission(uid, 'product', p, 'write', inherit_to_children=True)

    level = svc.get_effective_permission_level(uid, 'version', v)
    assert level == 'write'


def test_inherit_2_hop_product_to_domain(svc, ds):
    """inherit_to_children: write on product -> write on domain (2 hops down)."""
    uid = _insert_user(ds, 'inh_user2')
    p = _insert_product(ds, 'PI2', 'pi2')
    v = _insert_version(ds, 'VI2', 'vi2', product_id=p)
    d = _insert_domain(ds, 'DI2', 'di2', version_id=v)

    svc.add_data_permission(uid, 'product', p, 'write', inherit_to_children=True)

    level = svc.get_effective_permission_level(uid, 'domain', d)
    assert level == 'write'


def test_inherit_3_hop_product_to_sub_domain(svc, ds):
    """inherit_to_children: write on product -> write on sub_domain (3 hops down)."""
    uid = _insert_user(ds, 'inh_user3')
    p = _insert_product(ds, 'PI3', 'pi3')
    v = _insert_version(ds, 'VI3', 'vi3', product_id=p)
    d = _insert_domain(ds, 'DI3', 'di3', version_id=v)
    sd = _insert_sub_domain(ds, 'SDI3', 'sdi3', domain_id=d)

    svc.add_data_permission(uid, 'product', p, 'write', inherit_to_children=True)

    level = svc.get_effective_permission_level(uid, 'sub_domain', sd)
    assert level == 'write'


def test_inherit_5_hop_product_to_bo(svc, ds):
    """inherit_to_children: write on product -> write on BO (5 hops down)."""
    uid = _insert_user(ds, 'inh_user4')
    p = _insert_product(ds, 'PI4', 'pi4')
    v = _insert_version(ds, 'VI4', 'vi4', product_id=p)
    d = _insert_domain(ds, 'DI4', 'di4', version_id=v)
    sd = _insert_sub_domain(ds, 'SDI4', 'sdi4', domain_id=d)
    sm = _insert_service_module(ds, 'SMI4', 'smi4', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOI4', 'boi4', service_module_id=sm)

    svc.add_data_permission(uid, 'product', p, 'write', inherit_to_children=True)

    level = svc.get_effective_permission_level(uid, 'business_object', bo)
    assert level == 'write'


# ============== D. Multi-hop user->group->role->data_perm chain ==============

def test_user_group_role_data_perm_5_hop(svc, ds):
    """5-hop chain: user->group->role->data_perm on sub_domain yields write on SD."""
    uid = _insert_user(ds, 'chain_user1')
    gid = _insert_group(ds, 'chain_g1', 'Chain Group')
    _insert_group_member(ds, uid, gid)
    rid = _insert_role(ds, 'chain_r1', 'Chain Role', priority=10)
    _insert_group_role(ds, gid, rid)

    p = _insert_product(ds, 'PC1', 'pc1')
    v = _insert_version(ds, 'VC1', 'vc1', product_id=p)
    d = _insert_domain(ds, 'DC1', 'dc1', version_id=v)
    sd = _insert_sub_domain(ds, 'SDC1', 'sdc1', domain_id=d)

    svc.add_role_data_permission(rid, 'sub_domain', sd, 'write', inherit_to_children=False, created_by=uid)

    level = svc.get_effective_permission_level(uid, 'sub_domain', sd)
    assert level == 'write'


def test_user_group_role_data_perm_bo_write(svc, ds):
    """5-hop chain + inherit: user->group->role->perm on domain -> write on BO."""
    uid = _insert_user(ds, 'chain_user2')
    gid = _insert_group(ds, 'chain_g2', 'Chain Group 2')
    _insert_group_member(ds, uid, gid)
    rid = _insert_role(ds, 'chain_r2', 'Chain Role 2', priority=10)
    _insert_group_role(ds, gid, rid)

    p = _insert_product(ds, 'PC2', 'pc2')
    v = _insert_version(ds, 'VC2', 'vc2', product_id=p)
    d = _insert_domain(ds, 'DC2', 'dc2', version_id=v)
    sd = _insert_sub_domain(ds, 'SDC2', 'sdc2', domain_id=d)
    sm = _insert_service_module(ds, 'SMC2', 'smc2', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOC2', 'boc2', service_module_id=sm)

    svc.add_role_data_permission(rid, 'domain', d, 'write', inherit_to_children=True, created_by=uid)

    level = svc.get_effective_permission_level(uid, 'business_object', bo)
    assert level == 'write'


# ============== E. Multi-hop inherited_resource_ids ==============

def test_inherited_resource_ids_domain_to_bo(svc, ds):
    """_get_inherited_resource_ids: domain->sub_domain->sm->bo = 3 hops down."""
    p = _insert_product(ds, 'PE1', 'pe1')
    v = _insert_version(ds, 'VE1', 've1', product_id=p)
    d = _insert_domain(ds, 'DE1', 'de1', version_id=v)
    sd1 = _insert_sub_domain(ds, 'SDE1a', 'sde1a', domain_id=d)
    sd2 = _insert_sub_domain(ds, 'SDE1b', 'sde1b', domain_id=d)
    sm1 = _insert_service_module(ds, 'SME1a', 'sme1a', sub_domain_id=sd1)
    sm2 = _insert_service_module(ds, 'SME1b', 'sme1b', sub_domain_id=sd2)
    bo1 = _insert_business_object(ds, 'BOE1a', 'boe1a', service_module_id=sm1)
    bo2 = _insert_business_object(ds, 'BOE1b', 'boe1b', service_module_id=sm2)

    ids = svc._get_inherited_resource_ids('domain', d, 'business_object')
    assert len(ids) >= 2
    assert bo1 in ids
    assert bo2 in ids


def test_inherited_resource_ids_product_to_version(svc, ds):
    """_get_inherited_resource_ids: product->version = 1 hop down."""
    p = _insert_product(ds, 'PE2', 'pe2')
    v = _insert_version(ds, 'VE2', 've2', product_id=p)

    ids = svc._get_inherited_resource_ids('product', p, 'version')
    assert len(ids) == 1
    assert v in ids


# ============== F. Multi-hop find_parent_id ==============

def test_find_parent_id_bo_to_product(svc, ds):
    """_find_parent_id: business_object -> product = 5 hops up."""
    p = _insert_product(ds, 'PF1', 'pf1')
    v = _insert_version(ds, 'VF1', 'vf1', product_id=p)
    d = _insert_domain(ds, 'DF1', 'df1', version_id=v)
    sd = _insert_sub_domain(ds, 'SDF1', 'sdf1', domain_id=d)
    sm = _insert_service_module(ds, 'SMF1', 'smf1', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOF1', 'bof1', service_module_id=sm)

    parent_id = svc._find_parent_id('business_object', bo, 'product')
    assert parent_id == p


def test_find_parent_id_sm_to_version(svc, ds):
    """_find_parent_id: service_module -> version = 3 hops up."""
    p = _insert_product(ds, 'PF2', 'pf2')
    v = _insert_version(ds, 'VF2', 'vf2', product_id=p)
    d = _insert_domain(ds, 'DF2', 'df2', version_id=v)
    sd = _insert_sub_domain(ds, 'SDF2', 'sdf2', domain_id=d)
    sm = _insert_service_module(ds, 'SMF2', 'smf2', sub_domain_id=sd)

    parent_id = svc._find_parent_id('service_module', sm, 'version')
    assert parent_id == v


def test_find_parent_id_bo_to_domain(svc, ds):
    """_find_parent_id: business_object -> domain = 3 hops up."""
    p = _insert_product(ds, 'PF3', 'pf3')
    v = _insert_version(ds, 'VF3', 'vf3', product_id=p)
    d = _insert_domain(ds, 'DF3', 'df3', version_id=v)
    sd = _insert_sub_domain(ds, 'SDF3', 'sdf3', domain_id=d)
    sm = _insert_service_module(ds, 'SMF3', 'smf3', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOF3', 'bof3', service_module_id=sm)

    parent_id = svc._find_parent_id('business_object', bo, 'domain')
    assert parent_id == d


# ============== G. Multi-hop visible_parent_ids ==============

def test_visible_parent_ids_bo_triggers_all_ancestors(svc, ds):
    """visible_parent_ids: write on BO -> all ancestors visible (product, version, domain, sub_domain, sm)."""
    uid = _insert_user(ds, 'vid_user1')
    p = _insert_product(ds, 'PG1', 'pg1')
    v = _insert_version(ds, 'VG1', 'vg1', product_id=p)
    d = _insert_domain(ds, 'DG1', 'dg1', version_id=v)
    sd = _insert_sub_domain(ds, 'SDG1', 'sdg1', domain_id=d)
    sm = _insert_service_module(ds, 'SMG1', 'smg1', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOG1', 'bog1', service_module_id=sm)

    svc.add_data_permission(uid, 'business_object', bo, 'write', inherit_to_children=False)

    # Check each ancestor is visible
    product_ids = svc.get_allowed_resource_ids(uid, 'product')
    version_ids = svc.get_allowed_resource_ids(uid, 'version')
    domain_ids = svc.get_allowed_resource_ids(uid, 'domain')
    sub_domain_ids = svc.get_allowed_resource_ids(uid, 'sub_domain')
    sm_ids = svc.get_allowed_resource_ids(uid, 'service_module')

    assert p in product_ids
    assert v in version_ids
    assert d in domain_ids
    assert sd in sub_domain_ids
    assert sm in sm_ids


def test_visible_parent_ids_sm_triggers_partial_ancestors(svc, ds):
    """visible_parent_ids: write on SM -> ancestors above SM visible (product, version, domain, sub_domain)."""
    uid = _insert_user(ds, 'vid_user2')
    p = _insert_product(ds, 'PG2', 'pg2')
    v = _insert_version(ds, 'VG2', 'vg2', product_id=p)
    d = _insert_domain(ds, 'DG2', 'dg2', version_id=v)
    sd = _insert_sub_domain(ds, 'SDG2', 'sdg2', domain_id=d)
    sm = _insert_service_module(ds, 'SMG2', 'smg2', sub_domain_id=sd)

    svc.add_data_permission(uid, 'service_module', sm, 'write', inherit_to_children=False)

    product_ids = svc.get_allowed_resource_ids(uid, 'product')
    version_ids = svc.get_allowed_resource_ids(uid, 'version')

    assert p in product_ids
    assert v in version_ids


# ============== H. Multi-hop Owner inheritance ==============

def test_owner_is_admin_even_at_leaf_level(svc, ds):
    """Owner check works at BO level (deepest hierarchy level, 6 hops from root)."""
    uid = _insert_user(ds, 'own_user1')
    p = _insert_product(ds, 'PH1', 'ph1')
    v = _insert_version(ds, 'VH1', 'vh1', product_id=p)
    d = _insert_domain(ds, 'DH1', 'dh1', version_id=v)
    sd = _insert_sub_domain(ds, 'SDH1', 'sdh1', domain_id=d)
    sm = _insert_service_module(ds, 'SMH1', 'smh1', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOH1', 'boh1', service_module_id=sm, owner_id=uid)

    assert svc._is_owner(uid, 'business_object', bo) is True
    assert svc.get_permission_level(uid, 'business_object', bo) == 'admin'
    assert svc.has_access(uid, 'business_object', bo, action='delete') is True


def test_owner_multi_hop_has_access_to_ancestors(svc, ds):
    """Owner of leaf BO has access to ancestors through parent visibility."""
    uid = _insert_user(ds, 'own_user2')
    p = _insert_product(ds, 'PH2', 'ph2')
    v = _insert_version(ds, 'VH2', 'vh2', product_id=p)
    d = _insert_domain(ds, 'DH2', 'dh2', version_id=v)
    sd = _insert_sub_domain(ds, 'SDH2', 'sdh2', domain_id=d)
    sm = _insert_service_module(ds, 'SMH2', 'smh2', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOH2', 'boh2', service_module_id=sm, owner_id=uid)

    # Owner gets admin on the BO itself
    assert svc.get_permission_level(uid, 'business_object', bo) == 'admin'
    assert svc.has_access(uid, 'business_object', bo, 'delete') is True

    # Parent visibility requires explicit permission entries in DB
    # Add explicit write on BO, then check ancestor visibility
    svc.add_data_permission(uid, 'business_object', bo, 'write', inherit_to_children=False)
    product_ids = svc.get_allowed_resource_ids(uid, 'product')
    assert p in product_ids


# ============== I. Multi-hop has_access ==============

def test_has_access_multi_hop_inherited(svc, ds):
    """has_access: product write -> BO write via 5-hop inheritance chain."""
    uid = _insert_user(ds, 'ha_user1')
    p = _insert_product(ds, 'PHA1', 'pha1')
    v = _insert_version(ds, 'VHA1', 'vha1', product_id=p)
    d = _insert_domain(ds, 'DHA1', 'dha1', version_id=v)
    sd = _insert_sub_domain(ds, 'SDHA1', 'sdha1', domain_id=d)
    sm = _insert_service_module(ds, 'SMHA1', 'smha1', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOHA1', 'boha1', service_module_id=sm)

    svc.add_data_permission(uid, 'product', p, 'write', inherit_to_children=True)

    assert svc.has_access(uid, 'business_object', bo, 'read') is True
    assert svc.has_access(uid, 'business_object', bo, 'write') is True
    assert svc.has_access(uid, 'business_object', bo, 'delete') is False


def test_has_access_read_only_multi_hop(svc, ds):
    """has_access: product read -> BO read (not write/delete) via 5-hop inheritance."""
    uid = _insert_user(ds, 'ha_user2')
    p = _insert_product(ds, 'PHA2', 'pha2')
    v = _insert_version(ds, 'VHA2', 'vha2', product_id=p)
    d = _insert_domain(ds, 'DHA2', 'dha2', version_id=v)
    sd = _insert_sub_domain(ds, 'SDHA2', 'sdha2', domain_id=d)
    sm = _insert_service_module(ds, 'SMHA2', 'smha2', sub_domain_id=sd)
    bo = _insert_business_object(ds, 'BOHA2', 'boha2', service_module_id=sm)

    svc.add_data_permission(uid, 'product', p, 'read', inherit_to_children=True)

    assert svc.has_access(uid, 'business_object', bo, 'read') is True
    assert svc.has_access(uid, 'business_object', bo, 'write') is False
    assert svc.has_access(uid, 'business_object', bo, 'delete') is False
