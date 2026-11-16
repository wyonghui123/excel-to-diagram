# -*- coding: utf-8 -*-
"""集成模块取值域接口（/api/v2/integrations/options）。

口径: 前端下拉的唯一来源是 `meta/schemas/*.yaml` 的 `ui.options`；
      `RETRYABLE_STATUSES` 只能是 `delivery_status` 的子集，不得自造状态。
依据: docs/specs/plan-integration-p1p2-2026-11-16.md §6.4 S3
"""

import pytest

pytestmark = pytest.mark.unit

from meta.api.integration_module_api import RETRYABLE_STATUSES, build_options

_EXPECTED_KEYS = {
    'connection_channel', 'connection_direction', 'connection_auth_type',
    'delivery_status', 'delivery_channel', 'delivery_target_type',
    'delivery_direction', 'staging_status', 'retryable_status',
}


def _values(payload, key):
    return [item['value'] for item in payload[key]]


def test_payload_covers_all_frontend_dropdowns():
    payload = build_options()
    assert set(payload) == _EXPECTED_KEYS
    for key in _EXPECTED_KEYS:
        assert payload[key], '%s 不应为空' % key
        for item in payload[key]:
            assert item.get('value'), '%s 存在空值' % key
            assert item.get('label'), '%s 存在空标题' % key


def test_connection_domains_match_schema():
    payload = build_options()
    assert _values(payload, 'connection_channel') == ['webhook', 'rest', 'file', 'b2b']
    assert _values(payload, 'connection_direction') == ['outbound', 'inbound', 'both']
    assert _values(payload, 'connection_auth_type') == [
        'none', 'api_key', 'basic', 'bearer', 'oauth2_cc', 'hmac']


def test_delivery_domains_match_schema():
    """target_type 必须是 human/system —— 旧前端写的 connection/webhook/... 是错的。"""
    payload = build_options()
    assert _values(payload, 'delivery_status') == [
        'pending', 'sending', 'delivered', 'failed', 'skipped']
    assert _values(payload, 'delivery_target_type') == ['human', 'system']
    assert _values(payload, 'delivery_direction') == ['outbound', 'inbound']


def test_import_staging_domain_matches_schema():
    payload = build_options()
    assert _values(payload, 'staging_status') == [
        'pending', 'valid', 'invalid', 'imported', 'skipped']


def test_retryable_status_is_subset_with_labels():
    payload = build_options()
    labels = {item['value']: item['label'] for item in payload['delivery_status']}
    assert _values(payload, 'retryable_status') == list(RETRYABLE_STATUSES)
    for item in payload['retryable_status']:
        assert item['label'] == labels[item['value']]
