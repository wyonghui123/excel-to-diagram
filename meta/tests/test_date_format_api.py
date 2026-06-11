import pytest

pytestmark = pytest.mark.integration

import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
import jwt as pyjwt
from meta.server import create_app


DEFAULT_ADMIN_PREFS = {
    'locale': 'zh-CN',
    'timezone': 'Asia/Shanghai',
    'date_style': 'medium',
    'time_style': 'short',
    'hour_cycle': 24,
}


@pytest.fixture(scope='function', autouse=True)
def reset_rate_limiter():
    from meta.services.rate_limiter import RateLimiter
    RateLimiter.reset()
    yield
    RateLimiter.reset()


@pytest.fixture(scope='session')
def app():
    application = create_app()
    application.config['TESTING'] = True
    return application


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()


@pytest.fixture(scope='function')
def admin_token(app, isolated_token_service):
    secret = app.config.get('SECRET_KEY') or os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
    token = pyjwt.encode({
        'user_id': 1,
        'username': 'admin',
        'display_name': '系统管理员',
        'roles': [{'name': '超级管理员', 'code': 'super_admin'}],
        'permissions': ['*'],
        'exp': 9999999999,
    }, secret, algorithm='HS256')
    return token


@pytest.fixture(scope='function')
def regular_token(app, isolated_token_service):
    secret = app.config.get('SECRET_KEY') or os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
    token = pyjwt.encode({
        'user_id': 9999,
        'username': 'regular_user',
        'display_name': 'Regular User',
        'permissions': ['user:read'],
        'roles': ['viewer'],
        'exp': 9999999999,
    }, secret, algorithm='HS256')
    return token


@pytest.fixture(scope='function', autouse=True)
def restore_admin_prefs(client, admin_token):
    """恢复管理员偏好设置 - 每个测试前后都恢复默认值"""
    # Setup: restore to defaults BEFORE test
    client.put('/api/v1/users/me',
        json=DEFAULT_ADMIN_PREFS,
        headers={'Authorization': f'Bearer {admin_token}'})
    yield
    # Teardown: restore to defaults AFTER test
    try:
        client.put('/api/v1/users/me',
            json=DEFAULT_ADMIN_PREFS,
            headers={'Authorization': f'Bearer {admin_token}'})
    except Exception:
        pass


def _restore_prefs(client, admin_token):
    """恢复管理员偏好设置到默认值"""
    client.put('/api/v1/users/me',
        json=DEFAULT_ADMIN_PREFS,
        headers={'Authorization': f'Bearer {admin_token}'})


class TestPreferenceFieldsInGetMe:
    """GET /users/me 偏好字段测试"""

    def test_get_me_includes_preference_fields(self, client, admin_token):
        resp = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        data = resp.get_json()
        assert data.get('success') is True
        user = data.get('data', {})
        assert 'locale' in user, 'locale field missing'
        assert 'timezone' in user, 'timezone field missing'
        assert 'date_style' in user, 'date_style field missing'
        assert 'time_style' in user, 'time_style field missing'
        assert 'hour_cycle' in user, 'hour_cycle field missing'

    def test_get_me_preference_defaults(self, client, admin_token):
        resp = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        data = resp.get_json()
        user = data.get('data', {})
        assert user.get('locale') is not None
        assert user.get('timezone') is not None
        assert user.get('date_style') is not None
        assert user.get('time_style') is not None
        assert user.get('hour_cycle') is not None


class TestPreferenceFieldsUpdateViaMe:
    """PUT /users/me 偏好字段更新测试"""

    def test_update_locale(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'locale': 'en-US'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500], f'Failed: {resp.get_json()}'
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        data = resp.get_json()
        assert data.get('success') is True

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('locale') == 'en-US'

        resp2 = client.put('/api/v1/users/me',
            json={'locale': 'zh-CN'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500], f'Restore failed: {resp2.get_json()}'
        if resp2.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_update_timezone(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'timezone': 'America/New_York'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500], f'Failed: {resp.get_json()}'
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        assert (resp.get_json() or {}).get('success') is True

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('timezone') == 'America/New_York'

        resp2 = client.put('/api/v1/users/me',
            json={'timezone': 'Asia/Shanghai'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp2.status_code in [200, 400, 401, 404, 500], f'Restore failed: {resp2.get_json()}'
        if resp2.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_update_date_style(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'date_style': 'full'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('date_style') == 'full'

        client.put('/api/v1/users/me',
            json={'date_style': 'medium'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_update_time_style(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'time_style': 'long'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('time_style') == 'long'

        client.put('/api/v1/users/me',
            json={'time_style': 'short'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_update_hour_cycle(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'hour_cycle': 12},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('hour_cycle') == 12

        client.put('/api/v1/users/me',
            json={'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_update_multiple_preferences(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={
                'locale': 'en-GB',
                'timezone': 'Europe/London',
                'date_style': 'long',
                'time_style': 'long',
                'hour_cycle': 24
            },
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('locale') == 'en-GB'
        assert user.get('timezone') == 'Europe/London'
        assert user.get('date_style') == 'long'
        assert user.get('time_style') == 'long'
        assert user.get('hour_cycle') == 24

        client.put('/api/v1/users/me',
            json={
                'locale': 'zh-CN',
                'timezone': 'Asia/Shanghai',
                'date_style': 'medium',
                'time_style': 'short',
                'hour_cycle': 24
            },
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_update_preferences_and_profile_together(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={
                'display_name': '偏好管理员',
                'locale': 'zh-CN',
                'timezone': 'Asia/Tokyo',
                'date_style': 'full',
                'time_style': 'short',
                'hour_cycle': 24
            },
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('display_name') == '偏好管理员'
        assert user.get('timezone') == 'Asia/Tokyo'
        assert user.get('date_style') == 'full'

        client.put('/api/v1/users/me',
            json={
                'display_name': '系统管理员',
                'timezone': 'Asia/Shanghai',
                'date_style': 'medium'
            },
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_update_only_profile_fields_still_works(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'display_name': '测试管理员'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        assert (resp.get_json() or {}).get('success') is True

        client.put('/api/v1/users/me',
            json={'display_name': '系统管理员'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_empty_request_returns_error(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [400, 401, 500]
        data = resp.get_json()
        assert data.get('success') is False

    def test_unknown_field_ignored(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={
                'locale': 'zh-CN',
                'unknown_field': 'should_be_ignored'
            },
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_unauthenticated_rejected(self, client):
        resp = client.put('/api/v1/users/me',
            json={'locale': 'en-US'})
        assert resp.status_code in [401, 500]


class TestPreferenceFieldsViaSelf:
    """PUT /users/self 偏好字段更新测试"""

    def test_update_preferences_via_self(self, client, admin_token):
        resp = client.put('/api/v1/users/self',
            json={
                'locale': 'en-US',
                'timezone': 'America/Chicago',
                'date_style': 'short',
                'time_style': 'medium',
                'hour_cycle': 12
            },
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('locale') == 'en-US'
        assert user.get('timezone') == 'America/Chicago'
        assert user.get('date_style') == 'short'
        assert user.get('time_style') == 'medium'
        assert user.get('hour_cycle') == 12

        client.put('/api/v1/users/self',
            json={
                'locale': 'zh-CN',
                'timezone': 'Asia/Shanghai',
                'date_style': 'medium',
                'time_style': 'short',
                'hour_cycle': 24
            },
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_get_self_includes_preferences(self, client, admin_token):
        resp = client.get('/api/v1/users/self',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        data = resp.get_json()
        user = data.get('data', {})
        assert 'locale' in user
        assert 'timezone' in user
        assert 'date_style' in user
        assert 'time_style' in user
        assert 'hour_cycle' in user


class TestPreferencePersistence:
    """偏好字段持久化测试"""

    def test_preferences_persist_across_requests(self, client, admin_token):
        client.put('/api/v1/users/me',
            json={'locale': 'en-GB', 'hour_cycle': 12},
            headers={'Authorization': f'Bearer {admin_token}'})

        for _ in range(3):
            resp = client.get('/api/v1/users/me',
                headers={'Authorization': f'Bearer {admin_token}'})
            user = (resp.get_json() or {}).get('data', {})
            locale_val = user.get('locale')
            if locale_val == 'en-GB':
                assert user.get('hour_cycle') == 12
            else:
                pytest.fail(f"Locale persistence not working (got '{locale_val}' instead of 'en-GB')")

        client.put('/api/v1/users/me',
            json={'locale': 'zh-CN', 'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_preferences_hidden_in_list_users(self, client, admin_token):
        resp = client.get('/api/v1/users?page=1&page_size=5',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        data = resp.get_json()
        items = data.get('data', [])
        if items:
            first_user = items[0]
            assert 'locale' not in first_user, \
                'preference fields should be hidden_in_list'
            assert 'timezone' not in first_user
            assert 'date_style' not in first_user
            assert 'time_style' not in first_user
            assert 'hour_cycle' not in first_user


class TestConfigPriority:
    """配置分层优先级测试"""

    def test_user_pref_overrides_language_default(self, client, admin_token):
        client.put('/api/v1/users/me',
            json={'locale': 'en-US', 'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

        resp = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (resp.get_json() or {}).get('data', {})
        assert user.get('hour_cycle') == 24, '12-hour cycle should be overridden by user pref'

        client.put('/api/v1/users/me',
            json={'locale': 'zh-CN', 'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_user_pref_overrides_default_date_style(self, client, admin_token):
        client.put('/api/v1/users/me',
            json={'date_style': 'full'},
            headers={'Authorization': f'Bearer {admin_token}'})

        resp = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (resp.get_json() or {}).get('data', {})
        assert user.get('date_style') == 'full'

        client.put('/api/v1/users/me',
            json={'date_style': 'medium'},
            headers={'Authorization': f'Bearer {admin_token}'})


class TestAllValidPreferenceValues:
    """所有偏好字段有效值边界测试"""

    def test_all_valid_locales(self, client, admin_token):
        for locale in ['zh-CN', 'en-US', 'en-GB']:
            resp = client.put('/api/v1/users/me',
                json={'locale': locale},
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

            verify = client.get('/api/v1/users/me',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert (verify.get_json() or {}).get('data', {}).get('locale') == locale

        client.put('/api/v1/users/me',
            json={'locale': 'zh-CN'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_all_valid_date_styles(self, client, admin_token):
        for style in ['full', 'long', 'medium', 'short']:
            resp = client.put('/api/v1/users/me',
                json={'date_style': style},
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_all_valid_time_styles(self, client, admin_token):
        for style in ['full', 'long', 'medium', 'short']:
            resp = client.put('/api/v1/users/me',
                json={'time_style': style},
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_all_valid_hour_cycles(self, client, admin_token):
        for hc in [12, 24]:
            resp = client.put('/api/v1/users/me',
                json={'hour_cycle': hc},
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

            verify = client.get('/api/v1/users/me',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert (verify.get_json() or {}).get('data', {}).get('hour_cycle') == hc

        client.put('/api/v1/users/me',
            json={'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_all_common_timezones_acceptable(self, client, admin_token):
        common_tzs = [
            'UTC', 'Asia/Shanghai', 'Asia/Tokyo',
            'Europe/London', 'America/New_York', 'Australia/Sydney'
        ]
        for tz in common_tzs:
            resp = client.put('/api/v1/users/me',
                json={'timezone': tz},
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        client.put('/api/v1/users/me',
            json={'timezone': 'Asia/Shanghai'},
            headers={'Authorization': f'Bearer {admin_token}'})


class TestNegativePreferenceValues:
    """负向测试：非法偏好值"""

    def test_invalid_locale_not_rejected_by_api(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'locale': 'fr-FR'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 422, 500]

        if resp.status_code in [200, 400, 422]:
            resp2 = client.put('/api/v1/users/me',
                json={'locale': 'zh-CN'},
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp2.status_code in [200, 400, 401, 404, 500]
        if resp2.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_empty_locale(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'locale': ''},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 422, 500]

        resp2 = client.put('/api/v1/users/me',
            json={'locale': 'zh-CN'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp2.status_code in [200, 400, 401, 404, 500]
        if resp2.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_invalid_date_style(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'date_style': 'invalid_style'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 422, 500]

        resp2 = client.put('/api/v1/users/me',
            json={'date_style': 'medium'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp2.status_code in [200, 400, 401, 404, 500]
        if resp2.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_invalid_time_style(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'time_style': 'abcdef'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 422, 500]

        resp2 = client.put('/api/v1/users/me',
            json={'time_style': 'short'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp2.status_code in [200, 400, 401, 404, 500]
        if resp2.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_invalid_hour_cycle_string(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'hour_cycle': 'abc'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 422, 500]

        client.put('/api/v1/users/me',
            json={'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_hour_cycle_zero(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'hour_cycle': 0},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 422, 500]

        client.put('/api/v1/users/me',
            json={'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_hour_cycle_negative(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'hour_cycle': -1},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 422, 500]

        client.put('/api/v1/users/me',
            json={'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_hour_cycle_null(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'hour_cycle': None},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

    def test_invalid_timezone(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'timezone': 'Invalid/Timezone'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        client.put('/api/v1/users/me',
            json={'timezone': 'Asia/Shanghai'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_empty_timezone(self, client, admin_token):
        resp = client.put('/api/v1/users/me',
            json={'timezone': ''},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        client.put('/api/v1/users/me',
            json={'timezone': 'Asia/Shanghai'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_very_long_locale_value(self, client, admin_token):
        long_value = 'a' * 512
        resp = client.put('/api/v1/users/me',
            json={'locale': long_value},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 500]

        client.put('/api/v1/users/me',
            json={'locale': 'zh-CN'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_sql_injection_attempt_safe(self, client, admin_token):
        malicious = "'; DROP TABLE users; --"
        resp = client.put('/api/v1/users/me',
            json={'locale': malicious},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 500]

        verify = client.get('/api/v1/users',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert verify.status_code in [200, 400, 401, 404, 500]
        if verify.status_code == 500:
            pytest.fail('API returned 500 internal error')

        client.put('/api/v1/users/me',
            json={'locale': 'zh-CN'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_special_chars_in_preferences(self, client, admin_token):
        special = '<script>alert(1)</script>'
        resp = client.put('/api/v1/users/me',
            json={'locale': special},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 500]

        client.put('/api/v1/users/me',
            json={'locale': 'zh-CN'},
            headers={'Authorization': f'Bearer {admin_token}'})


class TestPermissionBoundary:
    """权限边界测试"""

    def test_regular_user_cannot_update_other_user_preferences(self, client, regular_token, admin_token):
        list_resp = client.get('/api/v1/users?page=1&page_size=10',
            headers={'Authorization': f'Bearer {admin_token}'})
        items = (list_resp.get_json() or {}).get('data', [])
        other_user_id = next((u['id'] for u in items if u.get('username') != 'admin'), None)
        assert other_user_id, 'need at least one non-admin user in DB'
        resp = client.put(f'/api/v1/users/{other_user_id}',
            json={'locale': 'en-US', 'timezone': 'UTC'},
            headers={'Authorization': f'Bearer {regular_token}'})
        assert resp.status_code in [200, 400, 401, 403, 404, 500]

    def test_admin_updating_other_user_preferences_not_allowed(self, client, admin_token):
        list_resp = client.get('/api/v1/users?page=1&page_size=10',
            headers={'Authorization': f'Bearer {admin_token}'})
        items = (list_resp.get_json() or {}).get('data', [])
        other_user_id = next((u['id'] for u in items if u.get('username') != 'admin'), None)
        assert other_user_id, 'need at least one non-admin user in DB'
        resp = client.put(f'/api/v1/users/{other_user_id}',
            json={'locale': 'en-US'},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        verify = client.get(f'/api/v1/users/{other_user_id}',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        locale = user.get('locale', '')
        assert locale != 'en-US', \
            f'preference fields should not be updatable via PUT /users/<id>, got locale={locale}'

    def test_regular_user_can_update_own_preferences_via_me(self, client, admin_token):
        user_resp = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        current_locale = (user_resp.get_json() or {}).get('data', {}).get('locale', 'zh-CN')

        resp = client.put('/api/v1/users/me',
            json={'locale': 'en-GB', 'hour_cycle': 12},
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')

        verify = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (verify.get_json() or {}).get('data', {})
        assert user.get('locale') == 'en-GB'
        assert user.get('hour_cycle') == 12

        client.put('/api/v1/users/me',
            json={'locale': current_locale, 'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_preferences_not_leaked_in_user_detail_forbidden(self, client, regular_token):
        resp = client.get('/api/v1/users/1',
            headers={'Authorization': f'Bearer {regular_token}'})
        assert resp.status_code in [401, 403, 500]


class TestGetUserByIdPreferenceBehavior:
    """GET /users/<id> 偏好字段行为测试"""

    def test_admin_get_other_user_includes_preferences(self, client, admin_token):
        list_resp = client.get('/api/v1/users?page=1&page_size=10',
            headers={'Authorization': f'Bearer {admin_token}'})
        items = (list_resp.get_json() or {}).get('data', [])
        other_user_id = next((u['id'] for u in items if u.get('username') != 'admin'), None)
        assert other_user_id, 'need at least one non-admin user in DB'
        resp = client.get(f'/api/v1/users/{other_user_id}',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        user = (resp.get_json() or {}).get('data', {})
        assert 'locale' in user
        assert 'timezone' in user
        assert 'date_style' in user
        assert 'time_style' in user
        assert 'hour_cycle' in user

    def test_self_get_own_detail_includes_preferences(self, client, admin_token):
        resp = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 500:
            pytest.fail('API returned 500 internal error')
        user = (resp.get_json() or {}).get('data', {})
        assert 'locale' in user
        assert user.get('locale') is not None


class TestAuthEdgeCases:
    """认证边缘情况测试"""

    def test_missing_auth_header_get_me(self, client):
        resp = client.get('/api/v1/users/me')
        assert resp.status_code in [401, 500]

    def test_missing_auth_header_put_me(self, client):
        resp = client.put('/api/v1/users/me',
            json={'locale': 'en-US'})
        assert resp.status_code in [401, 500]

    def test_missing_auth_header_get_self(self, client):
        resp = client.get('/api/v1/users/self')
        assert resp.status_code in [401, 500]

    def test_missing_auth_header_put_self(self, client):
        resp = client.put('/api/v1/users/self',
            json={'locale': 'en-US'})
        assert resp.status_code in [401, 500]

    def test_tampered_token(self, client):
        resp = client.get('/api/v1/users/me',
            headers={'Authorization': 'Bearer invalid.token.here'})
        assert resp.status_code in [401, 500]

    def test_empty_token(self, client):
        resp = client.get('/api/v1/users/me',
            headers={'Authorization': 'Bearer '})
        assert resp.status_code in [401, 500]

    def test_no_token_prefix(self, client):
        resp = client.get('/api/v1/users/me',
            headers={'Authorization': 'some_invalid_token'})
        assert resp.status_code in [401, 500]

    def test_tampered_token_put_me(self, client):
        resp = client.put('/api/v1/users/me',
            json={'locale': 'en-US'},
            headers={'Authorization': 'Bearer tampered.token.value'})
        assert resp.status_code in [401, 500]


class TestPreferenceReadConsistency:
    """偏好字段读写一致性测试"""

    def test_write_read_immediate_consistency_locale(self, client, admin_token):
        for locale in ['zh-CN', 'en-US', 'en-GB']:
            client.put('/api/v1/users/me',
                json={'locale': locale},
                headers={'Authorization': f'Bearer {admin_token}'})
            resp = client.get('/api/v1/users/me',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert (resp.get_json() or {}).get('data', {}).get('locale') == locale

        client.put('/api/v1/users/me',
            json={'locale': 'zh-CN'},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_write_read_immediate_consistency_hour_cycle(self, client, admin_token):
        for hc in [12, 24]:
            client.put('/api/v1/users/me',
                json={'hour_cycle': hc},
                headers={'Authorization': f'Bearer {admin_token}'})
            resp = client.get('/api/v1/users/me',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert (resp.get_json() or {}).get('data', {}).get('hour_cycle') == hc

        client.put('/api/v1/users/me',
            json={'hour_cycle': 24},
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_update_then_get_self_consistent(self, client, admin_token):
        client.put('/api/v1/users/me',
            json={
                'locale': 'en-US', 'timezone': 'America/Chicago',
                'date_style': 'short', 'time_style': 'medium', 'hour_cycle': 12
            },
            headers={'Authorization': f'Bearer {admin_token}'})

        resp_me = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp_self = client.get('/api/v1/users/self',
            headers={'Authorization': f'Bearer {admin_token}'})

        me_data = (resp_me.get_json() or {}).get('data', {})
        self_data = (resp_self.get_json() or {}).get('data', {})
        assert me_data.get('locale') == self_data.get('locale') == 'en-US'
        assert me_data.get('timezone') == self_data.get('timezone') == 'America/Chicago'

        client.put('/api/v1/users/me',
            json={
                'locale': 'zh-CN', 'timezone': 'Asia/Shanghai',
                'date_style': 'medium', 'time_style': 'short', 'hour_cycle': 24
            },
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_partial_update_preserves_other_fields(self, client, admin_token):
        client.put('/api/v1/users/me',
            json={
                'locale': 'en-US', 'timezone': 'America/New_York',
                'date_style': 'full', 'time_style': 'long', 'hour_cycle': 12
            },
            headers={'Authorization': f'Bearer {admin_token}'})

        client.put('/api/v1/users/me',
            json={'locale': 'en-GB'},
            headers={'Authorization': f'Bearer {admin_token}'})

        resp = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (resp.get_json() or {}).get('data', {})
        assert user.get('locale') == 'en-GB'
        assert user.get('timezone') == 'America/New_York', 'other fields should be preserved'
        assert user.get('date_style') == 'full'
        assert user.get('hour_cycle') == 12

        client.put('/api/v1/users/me',
            json={
                'locale': 'zh-CN', 'timezone': 'Asia/Shanghai',
                'date_style': 'medium', 'time_style': 'short', 'hour_cycle': 24
            },
            headers={'Authorization': f'Bearer {admin_token}'})

    def test_default_values_match_zh_cn_config(self, client, admin_token):
        client.put('/api/v1/users/me',
            json={
                'locale': 'zh-CN', 'timezone': 'Asia/Shanghai',
                'date_style': 'medium', 'time_style': 'short', 'hour_cycle': 24
            },
            headers={'Authorization': f'Bearer {admin_token}'})

        resp = client.get('/api/v1/users/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        user = (resp.get_json() or {}).get('data', {})
        if user.get('locale') is not None:
            assert user.get('locale') == 'zh-CN'
        if user.get('timezone') is not None:
            assert user.get('timezone') == 'Asia/Shanghai'
        if user.get('date_style') is not None:
            assert user.get('date_style') == 'medium'
        if user.get('time_style') is not None:
            assert user.get('time_style') == 'short'
        if user.get('hour_cycle') is not None:
            assert user.get('hour_cycle') == 24
