"""
test_api.py - M14 v1.0.0 Telemetry Dashboard API 测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestTelemetryAPI(unittest.TestCase):
    """Telemetry Dashboard API 测试"""

    def setUp(self):
        from flask import Flask
        from telemetry.api import telemetry_bp
        from telemetry.tracing import TraceContext
        from telemetry.storage import reset_storage
        TraceContext._local.set(None)
        reset_storage()
        self.app = Flask(__name__)
        self.app.register_blueprint(telemetry_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        from telemetry.tracing import TraceContext
        from telemetry.storage import reset_storage
        TraceContext._local.set(None)
        reset_storage()

    def test_stats_endpoint(self):
        """测试 stats 端点"""
        resp = self.client.get('/api/v1/telemetry/stats')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('total_traces', data)
        self.assertIn('p50_duration_ms', data)
        self.assertIn('p95_duration_ms', data)
        self.assertIn('p99_duration_ms', data)
        self.assertIn('max_duration_ms', data)
        self.assertIn('avg_duration_ms', data)
        self.assertIn('uptime_seconds', data)

    def test_traces_endpoint_empty(self):
        """测试 traces 端点（空）"""
        resp = self.client.get('/api/v1/telemetry/traces')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(len(data['traces']), 0)

    def test_traces_endpoint_with_data(self):
        """测试 traces 端点（有数据）"""
        from telemetry.tracing import trace
        from telemetry.storage import get_storage
        with trace('test1'):
            pass
        with trace('test2'):
            pass
        resp = self.client.get('/api/v1/telemetry/traces')
        data = resp.get_json()
        self.assertEqual(data['count'], 2)

    def test_traces_slow_endpoint(self):
        """测试 traces/slow 端点"""
        resp = self.client.get('/api/v1/telemetry/traces/slow')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('count', data)
        self.assertIn('traces', data)

    def test_trace_detail_not_found(self):
        """测试单个 trace 不存在"""
        resp = self.client.get('/api/v1/telemetry/traces/non_existent')
        self.assertEqual(resp.status_code, 404)

    def test_trace_detail_found(self):
        """测试单个 trace 详情"""
        from telemetry.tracing import trace
        from telemetry.storage import get_storage
        ctx = None
        with trace('detail_test') as c:
            ctx = c
        target_id = ctx.trace_id
        resp = self.client.get(f'/api/v1/telemetry/traces/{target_id}')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['trace_id'], target_id)

    def test_configure_endpoint(self):
        """测试 configure 端点"""
        resp = self.client.post(
            '/api/v1/telemetry/configure',
            json={'max_traces': 500, 'slow_threshold_ms': 200},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['max_traces'], 500)
        self.assertEqual(data['slow_threshold_ms'], 200)


if __name__ == '__main__':
    unittest.main()
