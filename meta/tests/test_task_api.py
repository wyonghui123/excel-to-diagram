# -*- coding: utf-8 -*-
"""
GAP-030: task_api (7 端点)

[EXPECT] 使用 expect() helper 替代 2 行 (1 行)
"""
import pytest
from meta.tests.shared.assertions import (
    expect, HTTPStatus, get_json,
)

# 状态码域 (复用 HTTPStatus)
OK_500 = HTTPStatus.PAGINATION_OK          # (200, 500)
NOT_FOUND_500 = HTTPStatus.NOT_FOUND_500   # (404, 500)


class TestTaskAPI:
    def test_status_uninitialized(self, api_client):
        r = expect(api_client, 'get', '/api/v2/task-scheduler/status', OK_500)
        if r.status_code == 500:
            data = get_json(r)
            assert 'not initialized' in data.get('error', '').lower() or 'error' in data

    def test_reload_uninitialized(self, api_client):
        expect(api_client, 'post', '/api/v2/task-scheduler/reload', OK_500)

    def test_trigger_nonexistent_task(self, api_client):
        expect(api_client, 'post', '/api/v2/tasks/nonexistent_task/trigger', NOT_FOUND_500)

    def test_enable_nonexistent_task(self, api_client):
        expect(api_client, 'post', '/api/v2/tasks/nonexistent_task/enable', OK_500)

    def test_disable_nonexistent_task(self, api_client):
        expect(api_client, 'post', '/api/v2/tasks/nonexistent_task/disable', OK_500)

    def test_retry_nonexistent_execution(self, api_client):
        expect(api_client, 'post', '/api/v2/task-executions/999999/retry', NOT_FOUND_500)

    def test_cancel_nonexistent_execution(self, api_client):
        expect(api_client, 'post', '/api/v2/task-executions/999999/cancel', OK_500)

    def test_queue_stats_uninitialized(self, api_client):
        expect(api_client, 'get', '/api/v2/task-queues/stats', OK_500)
