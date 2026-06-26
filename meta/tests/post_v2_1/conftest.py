# -*- coding: utf-8 -*-
"""
Post-V2.1 共享 conftest.py
"""
import os
import sys
import pytest
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('ALLOW_RAW_SQL', '1')


@pytest.fixture(scope='session')
def data_source():
    from meta.core.datasource import get_data_source
    db_path = PROJECT_ROOT / 'meta' / 'architecture.db'
    return get_data_source('sqlite', database=str(db_path))


@pytest.fixture
def ds(data_source):
    return data_source


@pytest.fixture
def admin_user():
    return {
        'user_id': 1,
        'username': 'admin',
        'display_name': '系统管理员',
        'permissions': ['*'],
        'is_admin': True,
    }


@pytest.fixture
def test_user():
    return {
        'user_id': 3,
        'username': 'TEST333',
        'display_name': 'TEST333 测试用户',
        'permissions': [],
        'is_admin': False,
    }


@pytest.fixture
def thread_local_user_setter():
    from meta.services.query_service import set_thread_user, clear_thread_user_id

    def setter(user):
        set_thread_user(user)

    def clearer():
        clear_thread_user_id()

    return setter, clearer


@pytest.fixture
def test_product_factory(data_source):
    created_pids = []

    def _factory(name, code, owner_id=3, visibility='private', is_active=1):
        cur = data_source.execute(
            "INSERT INTO products (name, code, owner_id, visibility, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (name, code, owner_id, visibility, is_active)
        )
        pid = cur.lastrowid
        created_pids.append(pid)
        return pid

    yield _factory

    for pid in created_pids:
        try:
            data_source.execute("DELETE FROM products WHERE id = ?", (pid,))
        except Exception:
            pass


@pytest.fixture
def test_version_factory(data_source, test_product_factory):
    created_vids = []

    def _factory(prod_name, prod_code, version_name='V1.0'):
        pid = test_product_factory(prod_name, prod_code)
        cur = data_source.execute(
            "INSERT INTO versions (product_id, name, created_at) VALUES (?, ?, datetime('now'))",
            (pid, version_name)
        )
        vid = cur.lastrowid
        created_vids.append(vid)
        return pid, vid

    yield _factory

    for vid in created_vids:
        try:
            data_source.execute("DELETE FROM versions WHERE id = ?", (vid,))
        except Exception:
            pass


@pytest.fixture(autouse=True)
def cleanup_audit_logs_after(data_source):
    yield
    try:
        data_source.execute(
            "DELETE FROM audit_logs WHERE user_name LIKE 'TEST%' OR object_type LIKE 'TEST%'"
        )
    except Exception:
        pass


@pytest.fixture
def perm_service_mock():
    class _PermMock:
        def __init__(self):
            self._perms = {}

        def set(self, key, value):
            self._perms[key] = value

        def get(self, key, default=False):
            return self._perms.get(key, default)

        def reset(self):
            self._perms = {}

    mock = _PermMock()
    yield mock
    mock.reset()


@pytest.fixture
def cross_domain_data(data_source):
    return {
        'product': {'table': 'products', 'pk': 'id'},
        'version': {'table': 'versions', 'pk': 'id', 'fk': 'product_id'},
    }


def pytest_collection_modifyitems(config, items):
    for item in items:
        fpath = str(item.fspath)
        if '/post_v2_1/import_export/' in fpath:
            item.add_marker(pytest.mark.post_v2_1)
            item.add_marker(pytest.mark.import_export)
        elif '/post_v2_1/permission/' in fpath:
            item.add_marker(pytest.mark.post_v2_1)
            item.add_marker(pytest.mark.permission)
        elif '/post_v2_1/audit_help/' in fpath:
            item.add_marker(pytest.mark.post_v2_1)
            item.add_marker(pytest.mark.audit_help)
        elif '/post_v2_1/cascade/' in fpath:
            item.add_marker(pytest.mark.post_v2_1)
            item.add_marker(pytest.mark.cascade)
        elif '/post_v2_1/frontend/' in fpath:
            item.add_marker(pytest.mark.post_v2_1)
            item.add_marker(pytest.mark.frontend)
        elif '/post_v2_1/integration/' in fpath:
            item.add_marker(pytest.mark.post_v2_1)
            item.add_marker(pytest.mark.integration)


def pytest_configure(config):
    config.addinivalue_line("markers", "post_v2_1: 6月22日之后的测试")
    config.addinivalue_line("markers", "import_export: Import/Export 主题")
    config.addinivalue_line("markers", "permission: Permission/RBAC + Write Scope 主题")
    config.addinivalue_line("markers", "audit_help: Audit + Help + Debug 主题")
    config.addinivalue_line("markers", "cascade: Delete FK Cascade 主题")
    config.addinivalue_line("markers", "frontend: Frontend Detail/List 主题")
    config.addinivalue_line("markers", "integration: 跨域集成测试")
