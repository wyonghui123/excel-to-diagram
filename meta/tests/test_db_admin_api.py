# -*- coding: utf-8 -*-
"""
GAP-012: db_admin_api 端到端测试 (6 用例)

[NEW] 2026-06-07 批次: 补齐 db_admin_api (3 端点) 的端到端测试
- GET  /api/v2/action/_db_health
- POST /api/v2/action/db.backup
- POST /api/v2/action/db.recover (含 dry_run 路径)
"""
import json
import pytest

pytestmark = pytest.mark.integration


class TestDBAdminAPI:
    """db_admin_api 端到端测试 (GAP-012)"""

    def test_db_health_admin(self, api_client, admin_headers):
        """GET /_db_health admin → 健康检查"""
        resp = api_client.get('/api/v2/action/_db_health', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body['data']
        # 核心字段
        for key in ('pool_stats', 'write_queue_stats', 'integrity', 'db_size', 'status', 'checked_at'):
            assert key in data

    def test_db_health_requires_admin(self, api_client, regular_user_headers):
        """GET /_db_health 非 admin → 403"""
        resp = api_client.get('/api/v2/action/_db_health', headers=regular_user_headers)
        assert resp.status_code == 403
        body = resp.get_json()
        assert body.get('success') is False

    def test_db_backup_creates_file(self, api_client, admin_headers):
        """POST /db.backup 立即备份"""
        resp = api_client.post('/api/v2/action/db.backup', json={}, headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body['data']
        # 备份文件信息
        assert 'filename' in data
        assert 'size' in data
        assert 'duration_ms' in data
        assert 'integrity' in data
        assert data['integrity'] == 'ok'

    def test_db_backup_requires_admin(self, api_client, regular_user_headers):
        """POST /db.backup 非 admin → 403"""
        resp = api_client.post('/api/v2/action/db.backup', json={}, headers=regular_user_headers)
        assert resp.status_code == 403

    def test_db_recover_missing_filename_400(self, api_client, admin_headers):
        """POST /db.recover 缺 backup_filename → 400"""
        resp = api_client.post('/api/v2/action/db.recover', json={}, headers=admin_headers)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('success') is False
        assert 'backup_filename' in body.get('message', '')

    def test_db_recover_dry_run(self, api_client, admin_headers):
        """POST /db.recover?dry_run=true 不实际恢复"""
        # 先创建一个备份
        backup_resp = api_client.post('/api/v2/action/db.backup', json={}, headers=admin_headers)
        if backup_resp.status_code != 200:
            pytest.skip("Cannot create backup for test")
        backup_filename = backup_resp.get_json()['data']['filename']
        # dry run
        resp = api_client.post(
            '/api/v2/action/db.recover',
            json={'backup_filename': backup_filename, 'dry_run': True},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body['data']
        assert data['dry_run'] is True
        assert data['integrity'] == 'ok'
