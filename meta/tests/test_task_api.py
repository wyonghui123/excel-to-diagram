# -*- coding: utf-8 -*-
"""
GAP-030: task_api (3 端点)

[账本统一 Phase 2c] task-executions retry/cancel 随 Gen1 账本退役一并删除。

[EXPECT] 使用 expect() helper 替代 2 行 (1 行)
"""
import pytest
from meta.tests.shared.assertions import (
    expect, HTTPStatus, get_json,
)

# 状态码域 (复用 HTTPStatus)
OK_500 = HTTPStatus.PAGINATION_OK          # (200, 500)


class TestTaskAPI:
    def test_status_uninitialized(self, api_client):
        r = expect(api_client, 'get', '/api/v2/task-scheduler/status', OK_500)
        if r.status_code == 500:
            data = get_json(r)
            assert 'not initialized' in data.get('error', '').lower() or 'error' in data

    def test_reload_uninitialized(self, api_client):
        expect(api_client, 'post', '/api/v2/task-scheduler/reload', OK_500)

    def test_queue_stats_uninitialized(self, api_client):
        expect(api_client, 'get', '/api/v2/task-queues/stats', OK_500)
