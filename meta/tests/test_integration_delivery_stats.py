# -*- coding: utf-8 -*-
"""投递运行面统计（GET /api/v2/integrations/deliveries/stats）。

覆盖:
  · 状态顺序 / 标题一律取自 YAML `delivery_status`（单一事实，不硬编码）；
  · `retryable` = `RETRYABLE_STATUSES` 子集计数；
  · `retry_exhausted` 是派生判定，不新增状态值；
  · 空库返回全 0；未声明状态保留在末尾不丢数。

依据: docs/specs/plan-integration-p1p2-2026-11-16.md §6.4 S6
"""

import pytest

pytestmark = pytest.mark.unit

from meta.api.integration_module_api import (
    RETRYABLE_STATUSES,
    build_options,
    integration_module_bp,
    shape_delivery_stats,
)


def _declared():
    return build_options()['delivery_status']


def test_empty_library_returns_zero_filled_statuses():
    stats = shape_delivery_stats({}, retry_exhausted=0)

    assert stats['total'] == 0
    assert stats['retryable'] == 0
    assert stats['retry_exhausted'] == 0
    assert stats['avg_latency_ms'] is None
    assert [item['value'] for item in stats['by_status']] == [
        item['value'] for item in _declared()]
    assert all(item['count'] == 0 for item in stats['by_status'])


def test_status_order_and_labels_come_from_yaml():
    stats = shape_delivery_stats({'delivered': 3, 'failed': 1}, 1)

    declared = _declared()
    assert [item['label'] for item in stats['by_status']] == [
        item['label'] for item in declared]


def test_totals_and_retryable_subset():
    counts = {'pending': 2, 'failed': 3, 'skipped': 1, 'delivered': 4}
    stats = shape_delivery_stats(counts, retry_exhausted=2)

    assert stats['total'] == 10
    assert stats['retryable'] == sum(
        counts.get(status, 0) for status in RETRYABLE_STATUSES)
    assert stats['retry_exhausted'] == 2


def test_undeclared_status_is_appended_not_dropped():
    stats = shape_delivery_stats({'failed': 1, 'legacy_state': 5}, 0)

    values = [item['value'] for item in stats['by_status']]
    assert values[-1] == 'legacy_state'
    assert stats['total'] == 6


def test_latency_is_rounded_int():
    stats = shape_delivery_stats({'delivered': 1}, 0, 1234.6)
    assert stats['avg_latency_ms'] == 1235


def test_stats_route_is_registered():
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(integration_module_bp)
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert '/api/v2/integrations/deliveries/stats' in rules