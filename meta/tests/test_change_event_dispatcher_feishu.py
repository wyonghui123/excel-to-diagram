# -*- coding: utf-8 -*-
"""ChangeEventDispatcher 飞书群机器人通道单测（全程 mock，不触网）。

覆盖：
  1. 飞书群机器人 URL 识别（feishu / larksuite）
  2. 消息体转换为飞书要求的 {msg_type, content:{text}}
  3. 配置 secret 时附加 timestamp + sign（飞书 HMAC 算法）
  4. 上游 code != 0 / HTTPError / 非 JSON → failed
  5. channel=webhook + 飞书 URL 时才走飞书分支
"""
import json
import urllib.error

from meta.services import change_event_dispatcher as mod
from meta.services.change_event_dispatcher import (
    ChangeEventDispatcher,
    feishu_bot_sign,
    is_feishu_bot_url,
    parse_feishu_im_target,
)

FEISHU_URL = 'https://open.feishu.cn/open-apis/bot/v2/hook/abc-123'


class _FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode('utf-8')

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _event():
    return {
        'id': 9,
        'object_type': 'product',
        'object_id': 7,
        'event_type': 'updated',
        'changed_fields': ['name', 'price'],
        'created_at': '2026-11-14T10:00:00',
    }


def test_is_feishu_bot_url_recognizes_both_domains():
    assert is_feishu_bot_url(FEISHU_URL) is True
    assert is_feishu_bot_url(
        'https://open.larksuite.com/open-apis/bot/v2/hook/xyz'
    ) is True
    assert is_feishu_bot_url('https://example.com/webhook') is False
    assert is_feishu_bot_url('') is False


def test_deliver_feishu_bot_posts_text_message(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured['url'] = request.full_url
        captured['body'] = json.loads(request.data.decode('utf-8'))
        captured['timeout'] = timeout
        return _FakeResponse({'code': 0, 'msg': 'success'})

    monkeypatch.setattr(mod.urllib.request, 'urlopen', fake_urlopen)
    dispatcher = ChangeEventDispatcher(data_source=None)

    status = dispatcher._deliver_feishu_bot(
        {'id': 1, 'webhook_secret': ''}, _event(), FEISHU_URL
    )

    assert status == 'delivered'
    assert captured['url'] == FEISHU_URL
    assert captured['timeout'] == mod.FEISHU_BOT_TIMEOUT
    assert captured['body']['msg_type'] == 'text'
    text = captured['body']['content']['text']
    assert 'product 7' in text
    assert '已更新' in text
    assert 'name, price' in text
    assert 'timestamp' not in captured['body']
    assert 'sign' not in captured['body']


def test_deliver_feishu_bot_signs_when_secret_configured(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured['body'] = json.loads(request.data.decode('utf-8'))
        return _FakeResponse({'code': 0, 'msg': 'success'})

    monkeypatch.setattr(mod.urllib.request, 'urlopen', fake_urlopen)
    dispatcher = ChangeEventDispatcher(data_source=None)

    status = dispatcher._deliver_feishu_bot(
        {'id': 2, 'webhook_secret': 's3cr3t'}, _event(), FEISHU_URL
    )

    assert status == 'delivered'
    body = captured['body']
    assert body['timestamp'].isdigit()
    assert body['sign'] == feishu_bot_sign(body['timestamp'], 's3cr3t')
    assert body['sign'] != feishu_bot_sign(body['timestamp'], 'other')


def test_deliver_feishu_bot_fails_on_nonzero_code(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return _FakeResponse({'code': 19021, 'msg': 'sign match fail'})

    monkeypatch.setattr(mod.urllib.request, 'urlopen', fake_urlopen)
    dispatcher = ChangeEventDispatcher(data_source=None)

    status = dispatcher._deliver_feishu_bot(
        {'id': 3, 'webhook_secret': 'bad'}, _event(), FEISHU_URL
    )

    assert status == 'failed'


def test_deliver_feishu_bot_fails_on_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(FEISHU_URL, 400, 'Bad Request', None, None)

    monkeypatch.setattr(mod.urllib.request, 'urlopen', fake_urlopen)
    dispatcher = ChangeEventDispatcher(data_source=None)

    status = dispatcher._deliver_feishu_bot(
        {'id': 4, 'webhook_secret': ''}, _event(), FEISHU_URL
    )

    assert status == 'failed'


def test_deliver_feishu_bot_fails_on_non_json(monkeypatch):
    class _RawResponse:
        def read(self):
            return b'<html>gateway</html>'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        mod.urllib.request, 'urlopen', lambda request, timeout=None: _RawResponse()
    )
    dispatcher = ChangeEventDispatcher(data_source=None)

    status = dispatcher._deliver_feishu_bot(
        {'id': 5, 'webhook_secret': ''}, _event(), FEISHU_URL
    )

    assert status == 'failed'


def test_deliver_routes_webhook_channel_to_feishu_only_for_feishu_url(monkeypatch):
    calls = []

    def fake_feishu(self, sub, event, url):
        calls.append(url)
        return 'delivered'

    monkeypatch.setattr(ChangeEventDispatcher, '_deliver_feishu_bot', fake_feishu)
    dispatcher = ChangeEventDispatcher(data_source=None)

    assert dispatcher._deliver(
        {'id': 6, 'channel': 'webhook', 'webhook_url': FEISHU_URL}, _event()
    ) == 'delivered'
    assert calls == [FEISHU_URL]

    # 非飞书 webhook 不得进入飞书分支（缺少依赖时应由 WebhookService 处理）
    calls.clear()
    result = dispatcher._deliver(
        {'id': 7, 'channel': 'webhook', 'webhook_url': 'https://example.com/hook'},
        _event(),
    )
    assert calls == []
    assert result in ('delivered', 'failed', 'skipped')


def test_parse_feishu_im_target():
    assert parse_feishu_im_target('feishu://chat/oc_abc') == 'oc_abc'
    assert parse_feishu_im_target('lark://chat/oc_abc') == 'oc_abc'
    assert parse_feishu_im_target('feishu://default') == ''
    assert parse_feishu_im_target('lark://default') == ''
    assert parse_feishu_im_target('https://open.feishu.cn/open-apis/bot/v2/hook/x') is None
    assert parse_feishu_im_target('https://example.com/hook') is None


def test_deliver_feishu_im_sends_text_via_app(monkeypatch):
    from meta.services.integration_credential_service import (
        integration_credential_service,
    )

    captured = {}

    def fake_request(method, path, query=None, body=None, file_payload=None):
        captured.update({'method': method, 'path': path, 'query': query, 'body': body})
        return {'code': 0, 'msg': 'success', 'data': {'message_id': 'om_1'}}

    monkeypatch.setattr(integration_credential_service, 'feishu_request', fake_request)
    dispatcher = ChangeEventDispatcher(data_source=None)

    status = dispatcher._deliver_feishu_im(
        {'id': 8}, _event(), 'oc_target'
    )

    assert status == 'delivered'
    assert captured['method'] == 'POST'
    assert captured['path'] == '/im/v1/messages'
    assert captured['query'] == {'receive_id_type': 'chat_id'}
    body = captured['body']
    assert body['receive_id'] == 'oc_target'
    assert body['msg_type'] == 'text'
    assert 'product 7' in json.loads(body['content'])['text']


def test_deliver_feishu_im_uses_default_chat_when_unspecified(monkeypatch):
    from meta.services.integration_credential_service import (
        integration_credential_service,
    )

    captured = {}
    monkeypatch.setattr(
        integration_credential_service, 'default_feishu_chat_id', lambda: 'oc_default'
    )
    monkeypatch.setattr(
        integration_credential_service,
        'feishu_request',
        lambda *a, **kw: captured.update(kw) or {'code': 0},
    )
    dispatcher = ChangeEventDispatcher(data_source=None)

    assert dispatcher._deliver_feishu_im({'id': 9}, _event(), '') == 'delivered'
    assert captured['body']['receive_id'] == 'oc_default'


def test_deliver_feishu_im_skips_without_any_chat_id(monkeypatch):
    from meta.services.integration_credential_service import (
        integration_credential_service,
    )

    monkeypatch.setattr(
        integration_credential_service, 'default_feishu_chat_id', lambda: ''
    )
    dispatcher = ChangeEventDispatcher(data_source=None)

    assert dispatcher._deliver_feishu_im({'id': 10}, _event(), '') == 'skipped'


def test_deliver_feishu_im_fails_on_upstream_and_nonzero_code(monkeypatch):
    from meta.services.integration_credential_service import (
        IntegrationUpstreamError,
        integration_credential_service,
    )

    dispatcher = ChangeEventDispatcher(data_source=None)

    def raise_upstream(*args, **kwargs):
        raise IntegrationUpstreamError('上游不可用')

    monkeypatch.setattr(
        integration_credential_service, 'feishu_request', raise_upstream
    )
    assert dispatcher._deliver_feishu_im({'id': 11}, _event(), 'oc_x') == 'failed'

    monkeypatch.setattr(
        integration_credential_service,
        'feishu_request',
        lambda *args, **kwargs: {'code': 230002, 'msg': 'bot not in chat'},
    )
    assert dispatcher._deliver_feishu_im({'id': 12}, _event(), 'oc_x') == 'failed'


def test_deliver_routes_feishu_scheme_to_im(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ChangeEventDispatcher,
        '_deliver_feishu_im',
        lambda self, sub, event, chat_id: calls.append(chat_id) or 'delivered',
    )
    dispatcher = ChangeEventDispatcher(data_source=None)

    status = dispatcher._deliver(
        {'id': 13, 'channel': 'webhook', 'webhook_url': 'feishu://chat/oc_route'},
        _event(),
    )

    assert status == 'delivered'
    assert calls == ['oc_route']