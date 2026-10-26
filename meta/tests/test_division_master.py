# -*- coding: utf-8 -*-
"""产品组（division）受控值集 —— 工作包 B 落地测试（T-B-1 ~ T-B-6）

依据: docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md §3
      （已批准 Spec: .trae/specs/excel-to-diagram/add-sales-order-master-data/spec.md）

覆盖:
  T-B-1  迁移首次运行: 种子 DEFAULT + 存量去重回填 + 非法 code 清单不阻断 + verify
  T-B-2  重复运行全 SKIP: 行数不变、无 [NEW]
  T-B-3  value_help 候选只返回 active
  T-B-4  合法 code 可写入订单抬头，并可回显
  T-B-5  停用 / 不存在的 code 不进候选集（严格绑定声明在案）
  T-B-6  迁移后存量订单的 division_code 原值仍可读（停用值不回溯）

测试隔离: tmp_path 临时 SQLite；建表走 factories 助手，本文件不含裸 SQL DML；
         不触碰 architecture.db 或其他共享库。
"""
import importlib.util
import logging
import os
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.models import registry  # noqa: E402
from meta.tests.factories._pricing_p2_helpers import (  # noqa: E402
    create_tables, seed_row,
)

SCHEMA_DIR = os.path.join(ROOT, 'meta', 'schemas')
_MIGRATION = (Path(__file__).resolve().parents[1]
              / 'migrations' / 'v137__division.py')

pytestmark = pytest.mark.unit

# 菜单 / 权限表暂无 Factory，此处只建表（无 DML）供 v137 种子写入与 verify 读取
_MENU_DDL = """
CREATE TABLE menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code VARCHAR(200) NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200),
    page_type VARCHAR(200) NOT NULL,
    object_types TEXT,
    primary_object_type VARCHAR(200),
    bo_bindings TEXT,
    required_permissions TEXT,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    color VARCHAR(200),
    description VARCHAR(500),
    sort_order INTEGER,
    is_active INTEGER,
    show_in_sidebar INTEGER,
    auto_generated INTEGER
);
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL UNIQUE,
    name VARCHAR(200),
    resource_type VARCHAR(200),
    action VARCHAR(50)
);
CREATE TABLE menu_permissions (
    menu_code VARCHAR(200) NOT NULL UNIQUE,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200) NOT NULL,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    sort_order INTEGER,
    is_active INTEGER,
    data_permission_hint TEXT
);
"""

#: 存量订单样本: 含重复值、停用候选、非法 code、空串、NULL
_LEGACY_ORDERS = [
    ('SO-1', 'D01'),
    ('SO-2', 'D01'),
    ('SO-3', 'D02'),
    ('SO-4', 'D-01'),
    ('SO-5', ''),
    ('SO-6', None),
]


@pytest.fixture(scope='module', autouse=True)
def _schemas():
    """按真实 YAML 载入注册表（division 必须能被注册）。"""
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(SCHEMA_DIR)
    finally:
        logging.disable(logging.NOTSET)


def _load_migration():
    spec = importlib.util.spec_from_file_location('v137_division', _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_db(path, orders=_LEGACY_ORDERS):
    """临时库: 按 YAML 真建 divisions / sales_orders + 菜单权限四表 + 存量订单。"""
    conn = sqlite3.connect(str(path))
    try:
        create_tables(conn, ['division', 'sales_order'])
        conn.executescript(_MENU_DDL)
        for order_no, code in orders:
            seed_row(conn, 'sales_orders', order_no=order_no, division_code=code)
        conn.commit()
    finally:
        conn.close()
    return path


def _query(path, sql, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _scalar(path, sql, params=()):
    rows = _query(path, sql, params)
    return rows[0][0] if rows else None


def _division_rows(path):
    return {code: (name, status) for code, name, status in _query(
        path, 'SELECT code, name, status FROM divisions')}


class TestMigration:
    def test_first_run_seeds_backfills_and_verifies(self, tmp_path, capsys):
        """T-B-1: DEFAULT 种子 + 去重回填 + 非法 code 清单（不阻断）+ verify。"""
        db = _build_db(tmp_path / 'v137_first.db')
        mod = _load_migration()
        assert mod.migrate(db) is True
        out = capsys.readouterr().out

        rows = _division_rows(db)
        assert rows['DEFAULT'] == ('默认产品组', 'active')
        # 去重回填: D01 两条订单只落一行; D02 虽已停用语义但存量回填为 active
        assert rows['D01'] == ('D01', 'active')
        assert rows['D02'] == ('D02', 'active')
        assert rows['D-01'] == ('D-01', 'active')
        # 空串 / NULL 不回填
        assert '' not in rows
        assert None not in rows

        # 非法 code 只登记清单，不阻断迁移
        assert '[CHECK]' in out and 'D-01' in out
        assert mod.verify(db) is True

        # 菜单 / 权限种子就位
        assert _scalar(
            db, "SELECT COUNT(1) FROM permissions "
                "WHERE code LIKE 'division:division\\_%' ESCAPE '\\'") == 5
        assert _scalar(
            db, "SELECT COUNT(1) FROM menus WHERE menu_code = 'division-list'") == 1
        assert _scalar(
            db, "SELECT COUNT(1) FROM menu_permissions "
                "WHERE menu_code = 'division-list'") == 1

    def test_second_run_is_all_skip(self, tmp_path, capsys):
        """T-B-2: 重复执行幂等 —— 行数不变、只输出 [SKIP]。"""
        db = _build_db(tmp_path / 'v137_second.db')
        mod = _load_migration()
        assert mod.migrate(db) is True
        capsys.readouterr()

        tables = ('divisions', 'permissions', 'menus', 'menu_permissions')
        before = {t: _scalar(db, 'SELECT COUNT(1) FROM {0}'.format(t))
                  for t in tables}

        assert mod.migrate(db) is True
        out = capsys.readouterr().out

        after = {t: _scalar(db, 'SELECT COUNT(1) FROM {0}'.format(t))
                 for t in tables}
        assert after == before
        assert '[NEW]' not in out
        assert '[SKIP]' in out

    def test_rollback_keeps_table_and_data(self, tmp_path):
        """rollback 只回收菜单 / 菜单权限 / 补建索引，保留表、数据与权限码。"""
        db = _build_db(tmp_path / 'v137_rollback.db')
        mod = _load_migration()
        assert mod.migrate(db) is True
        before = _scalar(db, 'SELECT COUNT(1) FROM divisions')
        perms_before = _scalar(db, 'SELECT COUNT(1) FROM permissions')

        assert mod.rollback(db) is True

        assert _scalar(db, 'SELECT COUNT(1) FROM divisions') == before
        assert _scalar(db, 'SELECT COUNT(1) FROM permissions') == perms_before
        assert _scalar(
            db, "SELECT COUNT(1) FROM menus WHERE menu_code = 'division-list'") == 0
        assert _scalar(
            db, "SELECT COUNT(1) FROM menu_permissions "
                "WHERE menu_code = 'division-list'") == 0
        assert _query(
            db, "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND name = 'uidx_division_code'") == []

    def test_legacy_order_values_readable(self, tmp_path):
        """T-B-6: 迁移不改写订单抬头，存量 division_code 原值可读。"""
        db = _build_db(tmp_path / 'v137_legacy.db')
        mod = _load_migration()
        assert mod.migrate(db) is True

        rows = dict(_query(
            db, 'SELECT order_no, division_code FROM sales_orders'))
        assert rows['SO-1'] == 'D01'
        assert rows['SO-2'] == 'D01'
        assert rows['SO-3'] == 'D02'
        assert rows['SO-4'] == 'D-01'
        assert rows['SO-5'] == ''
        assert rows['SO-6'] is None


@pytest.fixture()
def division_ds(tmp_path):
    """临时库 + 已注入 query_service 的数据源（division 候选集测试用）。"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.services import query_service

    db = tmp_path / 'division_vh.db'
    conn = sqlite3.connect(str(db))
    try:
        create_tables(conn, ['division', 'sales_order'])
        seed_row(conn, 'divisions', code='DEFAULT', name='默认产品组',
                 status='active')
        seed_row(conn, 'divisions', code='D01', name='华东产品组',
                 status='active')
        seed_row(conn, 'divisions', code='D02', name='停用产品组',
                 status='inactive')
        seed_row(conn, 'sales_orders', order_no='SO-VH-1', division_code='D01')
        conn.commit()
    finally:
        conn.close()

    ds = get_data_source('sqlite', database=str(db))
    query_service._data_source_instance = ds
    yield db, ds
    query_service._data_source_instance = None
    _clear_data_source_cache_for_testing()


def _division_field():
    mo = registry.get('sales_order')
    assert mo is not None, 'sales_order 未注册'
    return next(f for f in mo.fields if f.id == 'division_code')


def _provider():
    from dataclasses import replace
    from meta.core.value_help_accessor import get_value_help
    from meta.core.value_help_providers import BoValueHelpProvider

    vh = get_value_help(_division_field())
    assert vh is not None, 'division_code 缺 value_help'
    return BoValueHelpProvider(replace(vh.source, apply_target_permissions=False))


class TestValueHelp:
    def test_field_declares_strict_bo_value_help(self):
        """字段契约: select + relation division + active 过滤 + strict。"""
        from meta.core.value_help_accessor import get_value_help

        field = _division_field()
        vh = get_value_help(field)
        assert field.ui.widget == 'select'
        assert field.ui.relation == 'division'
        # clearable 只存在于 YAML 声明层（UIAnnotation 未建模该键）
        with open(os.path.join(SCHEMA_DIR, 'sales_order.yaml'),
                  'r', encoding='utf-8') as f:
            raw = yaml.safe_load(f)
        raw_field = next(f for f in raw['fields'] if f.get('id') == 'division_code')
        assert raw_field['ui']['clearable'] is True
        assert vh.source.type == 'bo'
        assert vh.source.target_bo == 'division'
        assert vh.source.value_field == 'code'
        assert vh.source.display_field == 'name'
        assert vh.source.value_filter == {'status': 'active'}
        assert vh.behavior.binding_strength == 'strict'
        assert vh.behavior.validation is True
        assert vh.presentation.result_type == 'dropdown'

    def test_search_returns_active_only(self, division_ds):
        """T-B-3: 候选集中只有 active 产品组。"""
        result = _provider().search('', [], {}, page=1, page_size=50, sort=[])
        codes = {item['code'] for item in result['data']}
        assert codes == {'DEFAULT', 'D01'}
        assert 'D02' not in codes

    def test_valid_code_resolves_and_writes_to_order(self, division_ds):
        """T-B-4: 合法 code 可回显，也可写入订单抬头并读回。"""
        db, _ds = division_ds
        resolved = _provider().resolve('D01')
        assert resolved is not None
        assert resolved['value'] == 'D01'
        assert resolved['code'] == 'D01'
        assert resolved['display'] == '华东产品组'

        conn = sqlite3.connect(str(db))
        try:
            seed_row(conn, 'sales_orders', order_no='SO-VH-2',
                     division_code='D01')
            conn.commit()
        finally:
            conn.close()

        rows = _query(
            db, "SELECT division_code FROM sales_orders WHERE order_no = 'SO-VH-2'")
        assert rows == [('D01',)]

    def test_inactive_and_unknown_not_in_candidates(self, division_ds):
        """T-B-5: 停用 / 不存在 code 不可被选中（严格绑定声明在案）。

        口径说明: 平台当前对 string code 字段的 strict 校验落在 UI 候选集层
        （provider 按 value_filter 过滤）；存量停用值仍可回显，不回溯改写。
        """
        provider = _provider()
        result = provider.search('', [], {}, page=1, page_size=50, sort=[])
        codes = {item['code'] for item in result['data']}
        assert 'D-01' not in codes
        assert 'NOPE' not in codes

        legacy = provider.resolve('D02')
        assert legacy is not None and legacy['display'] == '停用产品组'
        assert provider.resolve('NOPE') is None
