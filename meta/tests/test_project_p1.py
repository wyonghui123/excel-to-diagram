# -*- coding: utf-8 -*-
"""项目对象 P1（AC-01 / AC-02 / AC-03）

依据:
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §0.1 P1
  docs/specs/spec-project-type-object-model-research-2026-10-31.md §6

【本文件守什么】
  AC-01 项目是一等对象: projects 表、业务键 project_no 不可改、类型走
        type_definitions(scope_bo='project' + level='header')、状态枚举、
        只有 budget_amount 一个金额字段（I1）
  AC-02 三处可空挂载: sales_orders / sales_order_lines / sales_order_schedules 的
        project_id 可空 + 索引声明；为空时旧链路行为不变（不进入任一聚合段）
  AC-03 项目 360 只读聚合: ProjectOverviewService 原样返回三处金额，不重算、
        不复制；订单行的 hierarchy.parent_field 仍是 order_id（不被项目改写）

迁移用例另起一组：v169 建表 / 补列 / 建索引 / 权限 / 菜单，复跑幂等，回滚可逆。

建库一律走 factories 的 create_tables / seed_row（conftest 的裸 SQL 守卫
会把含裸 DML 的测试文件整体 skip）。
"""
import logging
import os
import sqlite3
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.datasource import get_data_source  # noqa: E402
from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.migrations.v169__project_object_p1 import (  # noqa: E402
    INDEXES,
    MOUNT_TABLES,
    PERMISSIONS,
    PROJECT_MENU,
    PROJECT_TABLE,
    migrate,
    rollback,
    verify,
)
from meta.services.project_overview_service import (  # noqa: E402
    ProjectNotFound,
    ProjectOverviewService,
)
from meta.tests.factories._pricing_p2_helpers import (  # noqa: E402
    create_tables,
    seed_row,
)

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")

# 声明文件 -> 物理表
MOUNT_YAML = {
    'sales_order': 'sales_orders',
    'sales_order_line': 'sales_order_lines',
    'sales_order_schedule': 'sales_order_schedules',
}

PROJECT_INDEX_NAMES = tuple(
    name for name, table, _sql in INDEXES if table == PROJECT_TABLE
)

pytestmark = pytest.mark.unit


def _load_raw(bo_id):
    with open(os.path.join(SCHEMA_DIR, bo_id + ".yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get("fields") or []:
        if f.get("id") == field_id:
            return f
    return None


def _reload_quietly():
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(SCHEMA_DIR)
    finally:
        logging.disable(logging.NOTSET)


# ─────────────────────────────────────────────────────────────────────────────
# AC-01 声明层
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectDeclaration:

    def test_business_identity(self):
        raw = _load_raw('project')
        assert raw['table_name'] == 'projects'
        assert raw['display_name_field'] == 'name'
        assert raw['semantics']['business_key'] == ['project_no']
        assert raw['deletion_policy']['mode'] == 'restrict'

    def test_project_no_is_required_unique_immutable(self):
        field = _field(_load_raw('project'), 'project_no')
        assert field is not None
        assert field['required'] is True
        assert field['unique'] is True
        assert field['max_length'] == 30
        assert field['semantics']['immutable'] is True

    def test_type_walks_type_definitions_not_enum_column(self):
        """D2: 项目类型走 type_definitions(scope_bo='project' + level='header')。"""
        field = _field(_load_raw('project'), 'project_type_id')
        assert field['required'] is True
        source = field['value_help']['source']
        assert source['target_bo'] == 'type_definition'
        assert source['value_filter'] == {
            'scope_bo': 'project', 'level': 'header', 'status': 'active'}
        assert field['ui']['relation'] == 'type_definition'
        # 不新增枚举列：project_type_id 没有 enum_values
        assert 'enum_values' not in field

    def test_status_enum_starts_from_draft(self):
        field = _field(_load_raw('project'), 'status')
        values = [e['value'] for e in field['enum_values']]
        assert values == ['draft', 'active', 'inactive', 'closed', 'cancelled']
        assert field['default'] == 'draft'
        initial = [e for e in field['enum_values'] if e.get('is_initial')]
        assert len(initial) == 1 and initial[0]['value'] == 'draft'

    def test_only_budget_amount_holds_money(self):
        """I1: 金额只在 SO / line / schedule，项目仅保留预算额度。"""
        fields = _load_raw('project')['fields']
        money = [f['id'] for f in fields if 'amount' in f['id']]
        assert money == ['budget_amount']
        for forbidden in ('net_amount', 'tax_amount', 'total_amount',
                          'discount_amount', 'contract_amount'):
            assert _field({'fields': fields}, forbidden) is None
        budget = _field({'fields': fields}, 'budget_amount')
        assert budget['nullable'] is True
        assert {'type': 'numeric_range', 'decimal_places': 4} in budget['constraints']

    def test_org_required_links_optional(self):
        fields = _load_raw('project')['fields']
        assert _field({'fields': fields}, 'org_id')['required'] is True
        assert _field({'fields': fields}, 'customer_account_id')['nullable'] is True
        assert _field({'fields': fields}, 'manager_user_id')['nullable'] is True

    def test_relations_and_indexes_declared(self):
        raw = _load_raw('project')
        relations = {r['id']: r for r in raw['relations']}
        assert relations['project_to_type_definition']['source_field'] == 'project_type_id'
        assert relations['project_to_type_definition']['target'] == 'type_definition'
        indexes = {i['name']: i for i in raw['indexes']}
        assert set(PROJECT_INDEX_NAMES) == set(indexes)
        assert indexes['uidx_project_no']['unique'] is True
        assert indexes['idx_project_org_status']['fields'] == ['org_id', 'status']

    def test_ui_declares_list_form_and_360_child_section(self):
        ui = _load_raw('project')['ui_view_config']
        assert ui['skip_auto_menu'] is True
        columns = [c['field'] for c in ui['list']['columns']]
        assert {'project_no', 'name', 'project_type_id', 'status'} <= set(columns)
        form_fields = [
            f for section in ui['form']['sections']
            for column in section['columns']
            for f in column['fields']
        ]
        assert 'project_no' in form_fields and 'budget_amount' in form_fields

        child = ui['child_sections'][0]
        assert child['child_object'] == 'sales_order'
        assert child['readonly'] is True
        assert child['enableAutoCrud'] is False
        assert child['useMetaList'] is True
        assert child['pageSize'] == 20

    def test_permission_codes_match_migration(self):
        declared = _load_raw('project')['category_config']
        expected = {p[0] for p in PERMISSIONS}
        assert declared['create_permission'] in expected
        assert declared['update_permission'] in expected
        assert declared['delete_permission'] in expected
        assert all(c.startswith('project:project_') for c in expected)

    def test_generated_ddl_matches_migration_table(self):
        _reload_quietly()
        mo = registry.get('project')
        assert mo is not None
        sql = SchemaGenerator("sqlite").generate_create_table(mo)
        assert 'projects' in sql
        assert 'project_no' in sql and 'budget_amount' in sql
        assert 'FOREIGN KEY (project_type_id) REFERENCES type_definitions(id)' in sql
        assert mo.table_name == PROJECT_TABLE


# ─────────────────────────────────────────────────────────────────────────────
# AC-02 三处可空挂载
# ─────────────────────────────────────────────────────────────────────────────

class TestMountDeclaration:

    def test_each_mount_is_nullable_and_points_to_project(self):
        for bo_id, table in MOUNT_YAML.items():
            raw = _load_raw(bo_id)
            field = _field(raw, 'project_id')
            assert field is not None, bo_id
            assert field['nullable'] is True, bo_id
            assert field['value_help']['source']['target_bo'] == 'project', bo_id
            assert field['ui']['relation'] == 'project', bo_id
            assert field['ui']['multiple'] is False, bo_id

    def test_mount_indexes_declared(self):
        expected = {
            'sales_order': 'idx_sales_order_project',
            'sales_order_line': 'idx_sales_order_line_project',
            'sales_order_schedule': 'idx_schedule_project',
        }
        for bo_id, index_name in expected.items():
            indexes = {i['name']: i for i in _load_raw(bo_id)['indexes']}
            assert indexes[index_name]['fields'] == ['project_id'], bo_id

    def test_order_line_hierarchy_still_order_id(self):
        """AC-02: 订单行的父键不能被项目改写，否则订单详情页签会串数据。"""
        raw = _load_raw('sales_order_line')
        assert raw['hierarchy']['parent_field'] == 'order_id'
        assert raw['hierarchy']['enabled'] is True

    def test_mount_tables_covered_by_migration(self):
        assert set(MOUNT_TABLES) == set(MOUNT_YAML.values())


# ─────────────────────────────────────────────────────────────────────────────
# 迁移 v169
# ─────────────────────────────────────────────────────────────────────────────

# 最小骨架表: 模拟 P1 之前（没有 project_id 列）的存量库
_LEGACY_MOUNT_DDL = (
    """CREATE TABLE {0} (id INTEGER PRIMARY KEY)""",
)

_PERMISSIONS_DDL = """
CREATE TABLE permissions (
    code TEXT PRIMARY KEY, name TEXT, resource_type TEXT, action TEXT
)
"""

_MENUS_DDL = """
CREATE TABLE menus (
    menu_code TEXT PRIMARY KEY, menu_name TEXT, menu_path TEXT, page_type TEXT,
    object_types TEXT, primary_object_type TEXT, bo_bindings TEXT,
    required_permissions TEXT, parent_menu TEXT, icon TEXT, color TEXT,
    description TEXT, sort_order INTEGER, is_active INTEGER,
    show_in_sidebar INTEGER, auto_generated INTEGER
)
"""

_MENU_PERMISSIONS_DDL = """
CREATE TABLE menu_permissions (
    menu_code TEXT PRIMARY KEY, menu_name TEXT, menu_path TEXT,
    required_permissions TEXT, required_any_permission INTEGER,
    parent_menu TEXT, icon TEXT, sort_order INTEGER, is_active INTEGER,
    data_permission_hint TEXT
)
"""


def _columns(path, table):
    conn = sqlite3.connect(str(path))
    try:
        return {row[1] for row in conn.execute('PRAGMA table_info({0})'.format(table))}
    finally:
        conn.close()


def _tables(path):
    conn = sqlite3.connect(str(path))
    try:
        return {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _scalar(path, sql, params=()):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _build_legacy_db(path, with_menus=False):
    conn = sqlite3.connect(str(path))
    try:
        for table in MOUNT_TABLES:
            conn.execute(_LEGACY_MOUNT_DDL[0].format(table))
        if with_menus:
            conn.executescript(_PERMISSIONS_DDL)
            conn.executescript(_MENUS_DDL)
            conn.executescript(_MENU_PERMISSIONS_DDL)
        conn.commit()
    finally:
        conn.close()
    return path


class TestMigration:

    def test_migrate_builds_table_mounts_and_indexes(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'p1_legacy.db')
        assert migrate(db) is True
        assert verify(db) is True

        assert PROJECT_TABLE in _tables(db)
        project_cols = _columns(db, PROJECT_TABLE)
        assert {'project_no', 'name', 'project_type_id', 'status', 'org_id',
                'customer_account_id', 'manager_user_id', 'start_date',
                'end_date', 'budget_amount', 'currency_id'} <= project_cols

        for table in MOUNT_TABLES:
            assert 'project_id' in _columns(db, table), table

    def test_migrate_is_idempotent(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'p1_twice.db')
        assert migrate(db) is True
        assert migrate(db) is True
        assert verify(db) is True

        conn = sqlite3.connect(str(db))
        try:
            for name, table, _sql in INDEXES:
                assert conn.execute(
                    "SELECT COUNT(1) FROM sqlite_master "
                    "WHERE type='index' AND name=?", (name,)).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(1) FROM sqlite_master "
                "WHERE type='table' AND name=?", (PROJECT_TABLE,)).fetchone()[0] == 1
        finally:
            conn.close()

    def test_migrate_writes_permissions_and_menu(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'p1_menu.db', with_menus=True)
        assert migrate(db) is True
        assert verify(db) is True

        for code, _name, resource_type, _action in PERMISSIONS:
            assert _scalar(db, 'SELECT code FROM permissions WHERE code=?',
                           (code,)) == code
            assert _scalar(db, 'SELECT resource_type FROM permissions WHERE code=?',
                           (code,)) == resource_type

        menu = PROJECT_MENU
        assert _scalar(db, 'SELECT is_active FROM menus WHERE menu_code=?',
                       (menu['menu_code'],)) == 1
        assert _scalar(db, 'SELECT menu_path FROM menus WHERE menu_code=?',
                       (menu['menu_code'],)) == menu['menu_path']
        assert _scalar(db, 'SELECT parent_menu FROM menus WHERE menu_code=?',
                       (menu['menu_code'],)) == 'sales'
        assert _scalar(db, 'SELECT bo_bindings FROM menus WHERE menu_code=?',
                       (menu['menu_code'],)) is not None
        assert _scalar(db, 'SELECT menu_code FROM menu_permissions WHERE menu_code=?',
                       (menu['menu_code'],)) == menu['menu_code']

    def test_verify_fails_before_migrate(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'p1_empty.db')
        assert verify(db) is False

    def test_rollback_drops_table_keeps_mount_columns(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'p1_rollback.db')
        assert migrate(db) is True
        assert rollback(db) is True

        assert PROJECT_TABLE not in _tables(db)
        for table in MOUNT_TABLES:
            assert 'project_id' in _columns(db, table), table
        assert verify(db) is False


# ─────────────────────────────────────────────────────────────────────────────
# AC-03 项目 360 只读聚合
# ─────────────────────────────────────────────────────────────────────────────

def _build_project_db(path):
    """真实 YAML 建表 + 播种：1 个项目有单，1 个项目空，3 张未归集单据。"""
    conn = sqlite3.connect(str(path))
    try:
        create_tables(conn, ['project', 'sales_order', 'sales_order_line',
                             'sales_order_schedule'])
        seed_row(conn, 'projects', id=1, project_no='PRJ-001', name='项目甲',
                 project_type_id=7, status='active', org_id=3,
                 customer_account_id=5, budget_amount=1000.5)
        seed_row(conn, 'projects', id=2, project_no='PRJ-002', name='项目乙',
                 project_type_id=7, status='draft', org_id=3)
        seed_row(conn, 'projects', id=3, project_no='PRJ-003', name='项目丙',
                 project_type_id=7, status='inactive', org_id=3)

        seed_row(conn, 'sales_orders', id=11, order_no='SO-001',
                 order_date='2026-01-10', status='confirmed',
                 customer_account_id=5, net_amount=12345.67, project_id=1)
        seed_row(conn, 'sales_orders', id=12, order_no='SO-002',
                 order_date='2026-03-01', status='draft',
                 customer_account_id=5, net_amount=99.99, project_id=1)
        # AC-02: 未归集订单（project_id 为空）不得进入任何项目 360
        seed_row(conn, 'sales_orders', id=13, order_no='SO-003',
                 order_date='2026-02-01', status='confirmed',
                 customer_account_id=5, net_amount=555.55, project_id=None)

        seed_row(conn, 'sales_order_lines', id=21, order_id=11, line_no=10,
                 qty=10, unit_price=1234.567, net_amount=12345.67, project_id=1)
        seed_row(conn, 'sales_order_lines', id=22, order_id=12, line_no=20,
                 qty=1, unit_price=99.99, net_amount=99.99, project_id=1)
        seed_row(conn, 'sales_order_lines', id=23, order_id=13, line_no=10,
                 qty=1, unit_price=555.55, net_amount=555.55, project_id=None)

        seed_row(conn, 'sales_order_schedules', id=31, order_id=11, line_id=21,
                 schedule_no='S1', schedule_kind='delivery',
                 promised_date='2026-02-01', promised_qty=10,
                 billing_percent=100, project_id=1)
        seed_row(conn, 'sales_order_schedules', id=32, order_id=13, line_id=23,
                 schedule_no='S1', schedule_kind='delivery',
                 promised_date='2026-02-20', promised_qty=1,
                 billing_percent=100, project_id=None)
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture()
def overview(tmp_path):
    path = _build_project_db(tmp_path / 'p1_overview.db')
    ds = get_data_source('sqlite', database=str(path))
    try:
        yield ProjectOverviewService(ds), path
    finally:
        ds.disconnect()


class TestProjectOverview:

    def test_project_fields_passed_through(self, overview):
        svc, _path = overview
        data = svc.overview(1)
        assert data['readonly'] is True
        project = data['project']
        assert project['project_no'] == 'PRJ-001'
        assert project['status'] == 'active'
        assert project['budget_amount'] == pytest.approx(1000.5)

    def test_sales_orders_filtered_by_project_and_sorted(self, overview):
        svc, _path = overview
        data = svc.overview(1)
        section = data['sales_orders']
        assert section['total'] == 2
        assert [o['order_no'] for o in section['items']] == ['SO-002', 'SO-001']
        # 不重算：金额原样透传
        by_no = {o['order_no']: o for o in section['items']}
        assert by_no['SO-001']['net_amount'] == pytest.approx(12345.67)
        assert by_no['SO-002']['net_amount'] == pytest.approx(99.99)

    def test_lines_and_schedules_filtered_by_project(self, overview):
        svc, _path = overview
        data = svc.overview(1)
        lines = data['sales_order_lines']
        assert lines['total'] == 2
        assert {l['id'] for l in lines['items']} == {21, 22}
        schedules = data['sales_order_schedules']
        assert schedules['total'] == 1
        assert schedules['items'][0]['id'] == 31
        # billing_amount 是 computed 字段（不落库）：接口只透传 billing_percent
        assert schedules['items'][0]['billing_percent'] == pytest.approx(100)
        assert 'billing_amount' not in schedules['items'][0]

    def test_unmounted_documents_excluded(self, overview):
        """AC-02: project_id 为空的订单 / 行 / 计划行不出现在项目 360。"""
        svc, _path = overview
        data = svc.overview(1)
        assert 13 not in {o['id'] for o in data['sales_orders']['items']}
        assert 23 not in {l['id'] for l in data['sales_order_lines']['items']}
        assert 32 not in {s['id'] for s in data['sales_order_schedules']['items']}

    def test_project_without_documents_returns_empty_sections(self, overview):
        svc, _path = overview
        data = svc.overview(2)
        assert data['project']['project_no'] == 'PRJ-002'
        for key in ('sales_orders', 'sales_order_lines', 'sales_order_schedules'):
            assert data[key] == {'items': [], 'total': 0}

    def test_limit_truncates_items_but_keeps_total(self, overview):
        svc, _path = overview
        data = svc.overview(1, limit=1)
        assert len(data['sales_orders']['items']) == 1
        assert data['sales_orders']['total'] == 2

    def test_missing_project_raises(self, overview):
        svc, _path = overview
        with pytest.raises(ProjectNotFound):
            svc.overview(999)
