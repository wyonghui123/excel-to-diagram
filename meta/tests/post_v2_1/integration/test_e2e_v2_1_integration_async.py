# -*- coding: utf-8 -*-
"""
test_e2e_v2_1_integration_async.py
跨域集成 E: thread-local + 异步导出
"""
import pytest
import threading
from pathlib import Path

pytestmark = [pytest.mark.post_v2_1, pytest.mark.integration]


class TestThreadLocalAsyncExport:
    def test_set_thread_user_passes_permissions(self, thread_local_user_setter):
        setter, clearer = thread_local_user_setter
        admin_user = {
            'user_id': 1,
            'username': 'admin',
            'permissions': ['*'],
        }
        setter(admin_user)
        try:
            from meta.services.query_service import _get_thread_user
            u = _get_thread_user()
            assert u is not None
            assert u.get('permissions') == ['*']
        finally:
            clearer()

    def test_is_admin_correct_in_async_thread(self, thread_local_user_setter):
        setter, clearer = thread_local_user_setter
        result = {}

        def async_work():
            setter({'user_id': 1, 'username': 'admin', 'permissions': ['*']})
            try:
                from meta.services.query_service import _get_thread_user
                u = _get_thread_user()
                result['user'] = u
                result['is_admin_correct'] = u and u.get('permissions') == ['*']
            finally:
                clearer()

        t = threading.Thread(target=async_work)
        t.start()
        t.join(timeout=5)

        assert result.get('is_admin_correct'), f"async thread-local 不正确: {result}"

    def test_thread_isolation(self, thread_local_user_setter):
        setter, clearer = thread_local_user_setter
        results = {}

        def worker(name, perm):
            setter({'user_id': 99, 'username': name, 'permissions': perm})
            try:
                from meta.services.query_service import _get_thread_user
                results[name] = _get_thread_user()
            finally:
                clearer()

        threads = [
            threading.Thread(target=worker, args=('A', ['perm_a'])),
            threading.Thread(target=worker, args=('B', ['perm_b'])),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert results.get('A') and results['A']['permissions'] == ['perm_a']
        assert results.get('B') and results['B']['permissions'] == ['perm_b']


class TestAsyncExportIntegration:
    def test_async_export_uses_thread_user(self):
        ie_source_path = Path('meta/services/import_export_service.py')
        if ie_source_path.exists():
            source = ie_source_path.read_text(encoding='utf-8')
            assert 'set_thread_user' in source or '_thread_local' in source

    def test_query_service_exposes_set_thread_user(self):
        from meta.services.query_service import set_thread_user, clear_thread_user_id
        assert callable(set_thread_user)
        assert callable(clear_thread_user_id)
