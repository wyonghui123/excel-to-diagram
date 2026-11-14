# -*- coding: utf-8 -*-
"""三方集成凭证收口 API 回归（P0-1）

锁定：
  1. 配置视图只下发 masked secret，响应体不出现真实密钥；
  2. AI 校验走后端代理，前端请求体不含 key；
  3. 未配置 / 上游失败 → valid=false + issues，不 500；
  4. 飞书接口按白名单代理，token 进程内缓存；
  5. 未登录 → 401。
"""
import pytest
from flask import Flask

from meta.api.integration_api import integration_bp
from meta.services.integration_credential_service import (
    integration_credential_service,
)

AUTH = {'Authorization': 'Bearer test-token'}

_ENV_KEYS = (
    'DEEPSEEK_API_KEY',
    'ZHIPU_API_KEY',
    'FEISHU_APP_ID',
    'FEISHU_APP_SECRET',
    'FEISHU_CHAT_ID',
    # 历史命名（tools/_setup_lark_env.ps1 写入用户级变量），
    # 不清会污染"未配置"场景，导致契约用例读真实凭证
    'LARK_APP_ID',
    'LARK_APP_SECRET',
    'LARK_CHAT_ID',
    'AI_PROVIDER',
)


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _auth(monkeypatch):
    monkeypatch.setattr(
        'meta.services.auth_middleware.TokenService.verify_token',
        lambda token: {'user_id': 1, 'permissions': ['*']})
    monkeypatch.setattr(
        'meta.services.auth_middleware.token_blacklist_service.is_blacklisted',
        lambda token: False)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    integration_credential_service._tenant_token = ''
    integration_credential_service._tenant_token_expires_at = 0.0
    yield


def _client():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(integration_bp)
    return app.test_client()


# ─────────────────────────────────────────────────────────────────────────────
# 配置视图
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test集成配置视图:
    def test_未配置时返回空状态(self):
        resp = _client().get('/api/v2/system/settings/integrations', headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['feishu'] == {
            'app_id': '', 'has_secret': False, 'app_secret_masked': '',
            'has_chat_id': False,
        }
        assert data['ai']['has_key'] is False

    def test_已配置时密钥只返回掩码(self, monkeypatch):
        monkeypatch.setenv('FEISHU_APP_ID', 'cli_test')
        monkeypatch.setenv('FEISHU_APP_SECRET', 'feishu-real-secret')
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-real-secret')
        monkeypatch.setenv('AI_PROVIDER', 'deepseek')

        resp = _client().get('/api/v2/system/settings/integrations', headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['feishu']['app_id'] == 'cli_test'
        assert data['feishu']['has_secret'] is True
        assert data['feishu']['app_secret_masked'] == '******'
        assert data['ai'] == {'provider': 'deepseek', 'has_key': True}
        raw = resp.get_data(as_text=True)
        assert 'feishu-real-secret' not in raw
        assert 'sk-real-secret' not in raw


# ─────────────────────────────────────────────────────────────────────────────
# AI 校验代理
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAI校验代理:
    def test_缺参数返回400(self):
        resp = _client().post(
            '/api/v2/integrations/ai/validate', json={'provider': 'deepseek'},
            headers=AUTH)
        assert resp.status_code == 400

    def test_未配置密钥返回valid_false(self):
        resp = _client().post(
            '/api/v2/integrations/ai/validate',
            json={'provider': 'deepseek', 'messages': [{'role': 'user', 'content': 'x'}]},
            headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['valid'] is False
        assert data['issues'][0]['message']

    def test_代理调用成功且密钥不出前端(self, monkeypatch):
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-test-key')
        captured = {}

        def _post(url, headers=None, json=None, timeout=None):
            captured['url'] = url
            captured['headers'] = headers
            captured['json'] = json
            return _FakeResponse({
                'choices': [{'message': {'content': '[{"index":1,"result":"PASS"}]'}}],
            })

        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.post', _post)

        resp = _client().post(
            '/api/v2/integrations/ai/validate',
            json={'provider': 'deepseek',
                  'messages': [{'role': 'user', 'content': 'check'}]},
            headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['valid'] is True
        assert 'PASS' in data['content']
        assert captured['headers']['Authorization'] == 'Bearer sk-test-key'
        assert captured['json']['messages'][0]['content'] == 'check'
        assert 'sk-test-key' not in resp.get_data(as_text=True)

    def test_上游失败返回valid_false(self, monkeypatch):
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-test-key')
        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.post',
            lambda *a, **kw: _FakeResponse({'error': {'message': 'bad key'}}, 401))

        resp = _client().post(
            '/api/v2/integrations/ai/validate',
            json={'provider': 'deepseek', 'messages': [{'role': 'user', 'content': 'x'}]},
            headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['valid'] is False
        assert 'bad key' in data['issues'][0]['message']


# ─────────────────────────────────────────────────────────────────────────────
# 飞书代理
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test飞书代理:
    def _configure(self, monkeypatch):
        monkeypatch.setenv('FEISHU_APP_ID', 'cli_test')
        monkeypatch.setenv('FEISHU_APP_SECRET', 'feishu-secret')

    def test_未配置返回400(self):
        resp = _client().post(
            '/api/v2/integrations/feishu/request',
            json={'method': 'GET', 'path': '/bot/v3/info'},
            headers=AUTH)
        assert resp.status_code == 400

    def test_路径白名单外返回400(self, monkeypatch):
        self._configure(monkeypatch)
        resp = _client().post(
            '/api/v2/integrations/feishu/request',
            json={'method': 'GET', 'path': 'https://evil.example.com/x'},
            headers=AUTH)
        assert resp.status_code == 400

    def test_代理成功并缓存token(self, monkeypatch):
        self._configure(monkeypatch)
        calls = {'token': 0, 'request': []}

        def _token_post(url, json=None, timeout=None):
            calls['token'] += 1
            return _FakeResponse({
                'code': 0, 'tenant_access_token': 't-123', 'expire': 7200,
            })

        def _request(method, url, **kwargs):
            calls['request'].append((method, url, kwargs))
            return _FakeResponse({'code': 0, 'data': {'chat_id': 'oc_1'}})

        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.post', _token_post)
        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.request', _request)

        client = _client()
        for _ in range(2):
            resp = client.post(
                '/api/v2/integrations/feishu/request',
                json={'method': 'GET', 'path': '/im/v1/chats',
                      'query': {'page_size': 100}},
                headers=AUTH)
            assert resp.status_code == 200
            assert resp.get_json()['data']['code'] == 0

        assert calls['token'] == 1
        method, url, kwargs = calls['request'][0]
        assert method == 'GET'
        assert url == 'https://open.feishu.cn/open-apis/im/v1/chats'
        assert kwargs['headers']['Authorization'] == 'Bearer t-123'
        assert kwargs['params'] == {'page_size': 100}

    def test_token失效时强制刷新一次(self, monkeypatch):
        self._configure(monkeypatch)
        state = {'token': 0, 'request': 0}

        def _token_post(url, json=None, timeout=None):
            state['token'] += 1
            return _FakeResponse({
                'code': 0, 'tenant_access_token': f't-{state["token"]}', 'expire': 7200,
            })

        def _request(method, url, **kwargs):
            state['request'] += 1
            if state['request'] == 1:
                return _FakeResponse({'code': 99991663, 'msg': 'token invalid'})
            return _FakeResponse({'code': 0, 'data': {}})

        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.post', _token_post)
        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.request', _request)

        resp = _client().post(
            '/api/v2/integrations/feishu/request',
            json={'method': 'GET', 'path': '/bot/v3/info'},
            headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()['data']['code'] == 0
        assert state['token'] == 2

    def test_上传文件走base64转发(self, monkeypatch):
        import base64
        self._configure(monkeypatch)
        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.post',
            lambda *a, **kw: _FakeResponse(
                {'code': 0, 'tenant_access_token': 't-123', 'expire': 7200}))
        captured = {}

        def _request(method, url, **kwargs):
            captured.update(kwargs)
            return _FakeResponse({'code': 0, 'data': {'image_key': 'img_1'}})

        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.request', _request)

        resp = _client().post(
            '/api/v2/integrations/feishu/request',
            json={'method': 'POST', 'path': '/im/v1/images',
                  'body': {'image_type': 'message'},
                  'file': {'name': 'a.png', 'content_type': 'image/png',
                           'content_base64': base64.b64encode(b'png').decode()}},
            headers=AUTH)
        assert resp.status_code == 200
        assert captured['data'] == {'image_type': 'message'}
        assert captured['files']['image'][0] == 'a.png'
        assert captured['files']['image'][1] == b'png'

    def test_连通性自检(self, monkeypatch):
        self._configure(monkeypatch)
        monkeypatch.setattr(
            'meta.services.integration_credential_service.requests.post',
            lambda *a, **kw: _FakeResponse(
                {'code': 0, 'tenant_access_token': 't-123', 'expire': 7200}))

        resp = _client().post(
            '/api/v2/integrations/feishu/test', headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['valid'] is True
        assert data['app_id'] == 'cli_test'


# ─────────────────────────────────────────────────────────────────────────────
# 鉴权
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test鉴权:
    def test_未登录返回401(self):
        client = _client()
        assert client.get(
            '/api/v2/system/settings/integrations').status_code == 401
        assert client.post(
            '/api/v2/integrations/ai/validate', json={}).status_code == 401
        assert client.post(
            '/api/v2/integrations/feishu/request', json={}).status_code == 401