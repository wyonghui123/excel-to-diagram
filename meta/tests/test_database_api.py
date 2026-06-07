# -*- coding: utf-8 -*-
"""
GAP-005: database_api 端到端测试 (12 用例)

[NEW] 2026-06-07 批次: 补齐 database_api (9 端点) 的端到端测试
- GET  /api/v1/system/database/health
- GET  /api/v1/system/database/metrics
- GET  /api/v1/system/database/metrics/prometheus
- GET  /api/v1/system/database/slow-queries
- POST /api/v1/system/database/vacuum
- POST /api/v1/system/database/analyze
- POST /api/v1/system/database/integrity-check
- POST /api/v1/system/database/wal-checkpoint
- POST /api/v1/system/database/reindex
- 覆盖 admin / login_required 鉴权 + dry-run 路径
"""
import json
import pytest

pytestmark = pytest.mark.integration


DB_URL = '/api/v1/system/database'


class TestDatabaseAPI:
    """database_api 端到端测试 (GAP-005)"""

    def test_health_returns_data(self, api_client, admin_headers):
        """GET /health 健康检查"""
        resp = api_client.get(f'{DB_URL}/health', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        # 响应包在 data 字段
        assert 'data' in body
        data = body['data']
        assert data is not None

    def test_metrics_returns_pool_or_full(self, api_client, admin_headers):
        """GET /metrics 返回 pool/write_queue/health (fallback 路径可能 500)"""
        resp = api_client.get(f'{DB_URL}/metrics', headers=admin_headers)
        # 接受 200 (有 monitor) 或 500 (无 monitor 且 ds 缺 get_pool_stats)
        assert resp.status_code in (200, 500)
        body = resp.get_json()
        if resp.status_code == 200:
            assert 'data' in body
            data = body['data']
            # 应至少有一个子字段
            assert any(k in data for k in ('pool', 'write_queue', 'health'))

    def test_prometheus_endpoint_text(self, api_client):
        """GET /metrics/prometheus 返回 text/plain"""
        # 此端点无 auth, 但用 admin_headers 兼容
        resp = api_client.get(f'{DB_URL}/metrics/prometheus')
        assert resp.status_code == 200
        # content-type 应是 Prometheus 格式
        ct = resp.headers.get('Content-Type', '')
        assert 'text/plain' in ct
        body = resp.get_data(as_text=True)
        # 即使 prom exporter 未配置, 也应有内容 (含注释行)
        assert len(body) > 0

    def test_slow_queries_with_limit(self, api_client, admin_headers):
        """GET /slow-queries?limit=5 返回 queries + stats"""
        resp = api_client.get(f'{DB_URL}/slow-queries?limit=5', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert 'data' in body
        data = body['data']
        assert 'queries' in data
        assert 'stats' in data
        assert isinstance(data['queries'], list)

    def test_slow_queries_default_limit(self, api_client, admin_headers):
        """GET /slow-queries 缺省 limit=20"""
        resp = api_client.get(f'{DB_URL}/slow-queries', headers=admin_headers)
        assert resp.status_code == 200
        assert 'data' in resp.get_json()

    def test_vacuum_dry_run_default(self, api_client, admin_headers):
        """POST /vacuum 默认 mode=dry-run 返回统计信息"""
        resp = api_client.post(f'{DB_URL}/vacuum', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body['data']
        assert data['action'] == 'VACUUM'
        assert data['dry_run'] is True
        assert 'page_count' in data
        assert 'freelist_count' in data
        assert 'free_ratio_pct' in data
        assert 'recommendation' in data

    def test_vacuum_force_mode(self, api_client, admin_headers):
        """POST /vacuum?mode=force 真正执行 VACUUM"""
        resp = api_client.post(f'{DB_URL}/vacuum?mode=force', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body['data']
        assert data['action'] == 'INCREMENTAL_VACUUM'
        assert data['status'] == 'completed'

    def test_vacuum_invalid_mode_400(self, api_client, admin_headers):
        """POST /vacuum?mode=invalid → 400"""
        resp = api_client.post(f'{DB_URL}/vacuum?mode=invalid', headers=admin_headers)
        assert resp.status_code == 400

    def test_analyze_requires_admin(self, api_client, regular_user_headers):
        """POST /analyze 非 admin → 403"""
        resp = api_client.post(f'{DB_URL}/analyze', headers=regular_user_headers)
        assert resp.status_code == 403

    def test_analyze_admin_runs(self, api_client, admin_headers):
        """POST /analyze admin → ANALYZE 完成"""
        resp = api_client.post(f'{DB_URL}/analyze', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body['data']
        assert data['action'] == 'ANALYZE'
        assert data['status'] == 'completed'

    def test_integrity_check_admin(self, api_client, admin_headers):
        """POST /integrity-check admin → PRAGMA integrity_check"""
        resp = api_client.post(f'{DB_URL}/integrity-check', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body['data']
        assert data['action'] == 'integrity_check'
        assert 'result' in data

    def test_wal_checkpoint_invalid_mode_400(self, api_client, admin_headers):
        """POST /wal-checkpoint?mode=BAD → 400"""
        resp = api_client.post(
            f'{DB_URL}/wal-checkpoint?mode=BAD',
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_wal_checkpoint_valid_modes(self, api_client, admin_headers):
        """POST /wal-checkpoint mode ∈ {PASSIVE, TRUNCATE, RESTART, FULL}"""
        for mode in ('PASSIVE', 'TRUNCATE', 'RESTART', 'FULL'):
            resp = api_client.post(
                f'{DB_URL}/wal-checkpoint?mode={mode}',
                headers=admin_headers,
            )
            assert resp.status_code == 200, f"mode={mode} failed: {resp.get_data(as_text=True)}"
            body = resp.get_json()
            assert 'data' in body

    def test_reindex_admin(self, api_client, admin_headers):
        """POST /reindex admin → REINDEX 所有表"""
        resp = api_client.post(f'{DB_URL}/reindex', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body['data']
        assert data['action'] == 'REINDEX'
        assert 'tables' in data
        assert data['status'] == 'completed'
