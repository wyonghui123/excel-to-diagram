# -*- coding: utf-8 -*-
"""party 平台模块门控 · 单元测试

依据: meta/core/platform_modules.py 模块头（部署级平台模块开关）
      docs/DEPLOYMENT_STANDARDS.md §9.2（party 的适用边界）

覆盖:
  1. party 已登记为已知且可关闭模块
  2. DISABLED_PLATFORM_MODULES=party 时关闭，且不落进 ineffective_disables
  3. 默认全开（xAPP 业务部署零影响）
  4. org 详情「往来关系」分区在模块关闭时被摘除；结构不符时不抛异常
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.unit


@pytest.fixture()
def modules(monkeypatch):
    from meta.core import platform_modules as pm
    pm.clear_cache()
    yield pm
    monkeypatch.delenv(pm.ENV_DISABLED_PLATFORM_MODULES, raising=False)
    pm.clear_cache()


def test_party_registered_as_closable(modules):
    assert 'party' in modules.KNOWN_PLATFORM_MODULES
    assert 'party' in modules.CLOSABLE_PLATFORM_MODULES


def test_party_enabled_by_default(modules):
    assert modules.is_module_enabled('party') is True


def test_party_disabled_by_env(modules, monkeypatch):
    monkeypatch.setenv(modules.ENV_DISABLED_PLATFORM_MODULES, 'party')
    modules.clear_cache()
    assert modules.is_module_enabled('party') is False
    assert 'party' not in modules.ineffective_disables()


def test_org_detail_section_stripped_when_party_disabled(modules):
    from meta.api.meta_api import _strip_party_detail_section
    config = {
        'ui_view_config': {
            'detail': {
                'tabs': [
                    {'id': 'basic', 'type': 'fields'},
                    {'id': 'party_relations', 'type': 'association'},
                ]
            }
        }
    }
    _strip_party_detail_section(config)
    assert [t['id'] for t in config['ui_view_config']['detail']['tabs']] == ['basic']


def test_org_detail_section_noop_on_unexpected_shape(modules):
    from meta.api.meta_api import _strip_party_detail_section
    config = {'ui_view_config': {'detail': {'tabs': 'not-a-list'}}}
    _strip_party_detail_section(config)  # 不抛异常
    assert config['ui_view_config']['detail']['tabs'] == 'not-a-list'
    empty = {}
    _strip_party_detail_section(empty)
    assert empty == {}


# ==================== L0 视图依赖守卫 ====================

class _FakeRegistry:
    """只实现守卫用到的 get / unregister，避免构造完整 MetaObject。"""

    def __init__(self, view_ids):
        self._objects = {vid: object() for vid in view_ids}
        self.unregistered = []

    def get(self, object_id):
        return self._objects.get(object_id)

    def unregister(self, object_id):
        self._objects.pop(object_id, None)
        self.unregistered.append(object_id)


class _FakeCursor:
    def __init__(self, found):
        self._found = found

    def fetchone(self):
        return ('x',) if self._found else None


class _FakeDataSource:
    """tables=物理表集合；execute_raises 模拟非 SQLite 适配器。"""

    def __init__(self, tables, execute_raises=False, fallback_tables=None):
        self.tables = set(tables)
        self.execute_raises = execute_raises
        self.fallback_tables = set(fallback_tables or ())

    def execute(self, sql, params):
        if self.execute_raises:
            raise RuntimeError('not sqlite')
        return _FakeCursor(params[0] in self.tables)

    def table_exists(self, table_name):
        return table_name in self.fallback_tables


_ALL_VIEWS = ('party_internal', 'org_legal_entity', 'org_sales_org')
_ALL_TABLES = ('parties', 'orgs', 'org_functions')


def test_guard_prunes_all_views_when_org_functions_missing():
    from meta.core.view_dependency_guard import prune_unusable_views
    reg = _FakeRegistry(_ALL_VIEWS)
    ds = _FakeDataSource(tables=('parties', 'orgs'))

    pruned = prune_unusable_views(ds, reg=reg)

    assert pruned == ['party_internal', 'org_legal_entity', 'org_sales_org']
    assert reg.unregistered == pruned


def test_guard_prunes_only_party_internal_when_parties_missing():
    from meta.core.view_dependency_guard import prune_unusable_views
    reg = _FakeRegistry(_ALL_VIEWS)
    ds = _FakeDataSource(tables=('orgs', 'org_functions'))

    pruned = prune_unusable_views(ds, reg=reg)

    assert pruned == ['party_internal']


def test_guard_noop_when_all_tables_present():
    from meta.core.view_dependency_guard import prune_unusable_views
    reg = _FakeRegistry(_ALL_VIEWS)
    ds = _FakeDataSource(tables=_ALL_TABLES)

    assert prune_unusable_views(ds, reg=reg) == []
    assert reg.unregistered == []


def test_guard_noop_when_data_source_is_none():
    from meta.core.view_dependency_guard import prune_unusable_views
    reg = _FakeRegistry(_ALL_VIEWS)

    assert prune_unusable_views(None, reg=reg) == []
    assert reg.unregistered == []


def test_guard_falls_back_to_table_exists_when_execute_fails():
    from meta.core.view_dependency_guard import prune_unusable_views
    reg = _FakeRegistry(_ALL_VIEWS)
    ds = _FakeDataSource(
        tables=(), execute_raises=True, fallback_tables=_ALL_TABLES,
    )

    assert prune_unusable_views(ds, reg=reg) == []
    assert reg.unregistered == []


def test_guard_is_idempotent():
    from meta.core.view_dependency_guard import prune_unusable_views
    reg = _FakeRegistry(_ALL_VIEWS)
    ds = _FakeDataSource(tables=('parties', 'orgs'))

    assert prune_unusable_views(ds, reg=reg) == list(_ALL_VIEWS)
    assert prune_unusable_views(ds, reg=reg) == []

