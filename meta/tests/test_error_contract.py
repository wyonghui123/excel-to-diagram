# -*- coding: utf-8 -*-
"""统一错误契约测试（spec-error-warning-framework M1 / TR-001 / TR-002）。

覆盖：
  1. ``ERROR_HTTP_STATUS`` 覆盖全部错误码，且 HTTP 状态映射表自身合法；
  2. ``error_response`` 输出 ``success/message/code/error_code/request_id``，
     且缺省 status 由错误码推导；
  3. 裸 Flask app 注册 ``register_error_handlers`` 后，400/401/403/404/405/422/500
     一律返回 JSON + ``success: false`` + ``error_code``；
  4. 未捕获异常 500 不泄露 ``str(e)`` / 堆栈 / 文件路径；
  5. ``PLATFORM_ERROR_CONTRACT_MODE=off`` 回滚旧式响应形状。

不启动真实服务、不读库；全部在内存 Flask app 内完成。
"""
import pytest
from flask import Flask, abort

from meta.api._response_contract import (
    error_response,
    normalize_error_code,
)
from meta.core.error_codes import ALL_CODES, ERROR_HTTP_STATUS, ErrorCode
from meta.core.error_handlers import register_error_handlers
from meta.core.platform_flags import ENV_ERROR_CONTRACT

pytestmark = pytest.mark.integration


def _app() -> Flask:
    app = Flask(__name__)
    app.config['TESTING'] = True
    # 关闭异常透传，让错误处理器接管（Flask 在 TESTING 下默认会重新抛出）
    app.config['PROPAGATE_EXCEPTIONS'] = False
    register_error_handlers(app)

    @app.route('/raise-400')
    def _raise_400():
        abort(400)

    @app.route('/raise-401')
    def _raise_401():
        abort(401)

    @app.route('/raise-403')
    def _raise_403():
        abort(403)

    @app.route('/raise-405', methods=['POST'])
    def _raise_405():
        return 'ok'

    @app.route('/raise-422')
    def _raise_422():
        abort(422)

    @app.route('/raise-500')
    def _raise_500():
        abort(500)

    @app.route('/boom')
    def _boom():
        raise RuntimeError('secret-db-path C:\\tmp\\architecture.db')

    @app.route('/manual')
    def _manual():
        return error_response('参数不对', error_code='data_invalid')

    return app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv(ENV_ERROR_CONTRACT, raising=False)
    return _app().test_client()


def test_all_codes_have_http_status():
    missing = sorted(set(ALL_CODES) - set(ERROR_HTTP_STATUS))
    assert missing == [], f'ERROR_HTTP_STATUS 缺少错误码映射: {missing}'


def test_http_status_table_is_valid():
    for code, status in ERROR_HTTP_STATUS.items():
        assert code in ALL_CODES, f'映射表出现未登记错误码: {code}'
        assert isinstance(status, int)
        assert 200 <= status <= 599


def test_error_codes_values_are_strings():
    # str Enum 的哈希陷阱回归：键必须是字符串 value，而非枚举成员
    assert ERROR_HTTP_STATUS.get(ErrorCode.UNAUTHORIZED.value) == 401
    assert ERROR_HTTP_STATUS.get('internal_error') == 500


def test_error_response_fields(client):
    resp = client.get('/manual')
    body = resp.get_json()

    assert resp.status_code == 400
    assert resp.mimetype == 'application/json'
    assert body['success'] is False
    assert body['message'] == '参数不对'
    assert body['code'] == 'data_invalid'
    assert body['error_code'] == 'data_invalid'
    assert isinstance(body['request_id'], str) and body['request_id']


def test_error_response_derives_status_from_code(client):
    resp = client.get('/api/not-exists')  # 404 由 HTTPException 处理器产生
    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == 'not_found'


@pytest.mark.parametrize('path,status,expected_code', [
    ('/raise-400', 400, 'bad_request'),
    ('/raise-401', 401, 'unauthorized'),
    ('/raise-403', 403, 'forbidden'),
    ('/api/not-exists', 404, 'not_found'),
    ('/raise-405', 405, 'method_not_allowed'),
    ('/raise-422', 422, 'unprocessable_entity'),
    ('/raise-500', 500, 'internal_error'),
])
def test_http_exceptions_share_json_contract(client, path, status, expected_code):
    resp = client.get(path)

    assert resp.status_code == status
    assert resp.mimetype == 'application/json'
    body = resp.get_json()
    assert body['success'] is False
    assert body['error_code'] == expected_code
    assert body['code'] == expected_code
    assert body['message']
    assert body['request_id']


def test_unhandled_exception_hides_technical_details(client):
    resp = client.get('/boom')
    body = resp.get_json()

    assert resp.status_code == 500
    assert body['error_code'] == 'internal_error'
    assert body['message'] == '系统内部错误，请稍后重试'
    # 技术细节只允许出现在 details（非生产环境），不能进 message
    assert 'secret-db-path' not in body['message']
    assert 'RuntimeError' not in body['message']
    assert 'Traceback' not in body['message']
    assert 'architecture.db' not in body['message']


def test_unhandled_exception_in_production_drops_details(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    resp = _app().test_client().get('/boom')
    body = resp.get_json()
    raw = resp.get_data(as_text=True)

    assert resp.status_code == 500
    assert body['error_code'] == 'internal_error'
    assert 'details' not in body
    assert 'secret-db-path' not in raw
    assert 'Traceback' not in raw
    assert 'architecture.db' not in raw


def test_off_mode_rolls_back_to_legacy_shape(monkeypatch):
    monkeypatch.setenv(ENV_ERROR_CONTRACT, 'off')
    resp = _app().test_client().get('/raise-404')

    assert resp.status_code == 404
    body = resp.get_json()
    assert body['success'] is False
    assert 'error' in body and 'message' in body and 'status_code' in body
    assert 'error_code' not in body


@pytest.mark.parametrize('raw,expected', [
    ('NOT_FOUND', 'not_found'),
    ('UNAUTHORIZED', 'unauthorized'),
    ('STATE_MACHINE_VIOLATION', 'STATE_MACHINE_VIOLATION'),
    ('VALUE_HELP_VALIDATION_FAILED', 'VALUE_HELP_VALIDATION_FAILED'),
    ('not_a_real_code', 'internal_error'),
    (None, 'internal_error'),
])
def test_normalize_error_code_aliases(raw, expected):
    assert normalize_error_code(raw) == expected