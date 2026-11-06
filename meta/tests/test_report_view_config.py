# -*- coding: utf-8 -*-
"""P9 元数据驱动报表页（report 段 + 菜单）后端配置测试。"""

import os
import sqlite3
import tempfile

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.core.models_ui_config import UIViewConfig
from meta.core.yaml_loader import parse_ui_view_config
from meta.migrations import v225__inventory_aging_report_menu as v225
from meta.services.view_config_service import ViewConfigService

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'schemas', 'inventory_balance.yaml')


def _load_example():
    with open(SCHEMA_PATH, encoding='utf-8') as handle:
        data = yaml.safe_load(handle)
    return parse_ui_view_config(data['ui_view_config'])


class TestReportConfig:
    def test_report_parsed(self):
        config = _load_example()
        assert config.report is not None
        assert config.report.title == '库存库龄'
        assert config.report.endpoint == '/api/v1/inventory-aging/report'
        assert config.report.method == 'GET'

    def test_filters(self):
        report = _load_example().report
        keys = [item.key for item in report.filters]
        assert keys == ['org_id', 'location_id', 'item_id', 'batch_id',
                        'stock_status', 'as_of', 'group_by']
        org = report.filters[0]
        assert org.type == 'value_help'
        assert org.target_type == 'org'
        assert org.required is True
        group = report.filters[-1]
        assert group.default == 'balance'
        assert [opt['value'] for opt in group.options] == [
            'balance', 'item', 'batch']

    def test_kpis_chart_table(self):
        report = _load_example().report
        assert [k.field for k in report.kpis] == ['total_qty', 'unassigned_qty']
        assert report.chart.type == 'bar'
        assert report.chart.data_field == 'summary'
        assert report.table.data_field == 'rows'
        assert report.table.page_size == 20
        assert len(report.table.columns) == 8
        assert len(report.table.row_key) == 10

    def test_drilldown(self):
        drill = _load_example().report.drilldown
        assert drill.endpoint == '/api/v1/inventory-aging/detail'
        assert drill.only_when_group_by == 'balance'
        assert drill.param_map['item_id'] == 'item_id'
        assert drill.param_map['as_of'] == 'as_of'

    def test_report_only_config_not_empty(self):
        config = UIViewConfig()
        config.report = _load_example().report
        assert ViewConfigService._is_config_empty(object(), config) is False

    def test_without_report_is_empty(self):
        assert ViewConfigService._is_config_empty(object(), UIViewConfig()) is True

    def test_absent_report_returns_none(self):
        config = parse_ui_view_config({'list': {'columns': []}})
        assert config.report is None


class TestReportApi:
    @pytest.fixture
    def client(self):
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        return client

    def test_view_config_api_returns_report(self, client):
        resp = client.get('/api/v1/meta/inventory_balance/view-config/default')
        assert resp.status_code == 200, resp.status_code
        data = resp.get_json()['data']
        assert data['report']['endpoint'] == '/api/v1/inventory-aging/report'
        assert data['report']['table']['page_size'] == 20


class TestReportMenuMigration:
    def _make_db(self, path):
        conn = sqlite3.connect(path)
        conn.execute(
            'CREATE TABLE menus (menu_code TEXT PRIMARY KEY, menu_name TEXT, '
            'menu_path TEXT, page_type TEXT, object_types TEXT, '
            'primary_object_type TEXT, bo_bindings TEXT, '
            'required_permissions TEXT, parent_menu TEXT, icon TEXT, '
            'color TEXT, description TEXT, sort_order INTEGER, '
            'is_active INTEGER, show_in_sidebar INTEGER, auto_generated INTEGER)')
        conn.execute(
            'CREATE TABLE menu_permissions (menu_code TEXT PRIMARY KEY, '
            'menu_name TEXT, menu_path TEXT, required_permissions TEXT, '
            'required_any_permission TEXT, parent_menu TEXT, icon TEXT, '
            'sort_order INTEGER, is_active INTEGER, data_permission_hint TEXT)')
        conn.commit()
        conn.close()

    def test_migrate_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, 'menus.db')
            self._make_db(db_path)

            assert v225.migrate(db_path) is True
            assert v225.migrate(db_path) is True

            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                'SELECT page_type, primary_object_type, required_permissions '
                'FROM menus WHERE menu_code=?', ('inventory-aging-report',)
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 'report'
            assert rows[0][1] == 'inventory_balance'
            assert 'inventory_balance_read' in rows[0][2]
            perms = conn.execute(
                'SELECT COUNT(*) FROM menu_permissions WHERE menu_code=?',
                ('inventory-aging-report',)).fetchone()[0]
            assert perms == 1
            conn.close()
            assert v225.verify(db_path) is True
