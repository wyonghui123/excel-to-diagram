# -*- coding: utf-8 -*-
"""[FR-009/010] 统一告警聚合与 /ops 端点测试

覆盖：group_wait 聚合、repeat_interval、恢复后不再提醒、
单 fingerprint 限流、dead_letter 与 replay、/ops/health|metrics|alerts 契约。
所有用例均不触达真实 DB（AlertService._ds 被替换为 None）。
"""
import time

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def alert_env(monkeypatch):
    monkeypatch.setenv('ALERT_ENABLED', '1')
    monkeypatch.setenv('ALERT_FLUSHER_AUTOSTART', '0')
    monkeypatch.delenv('ALERT_FEISHU_WEBHOOK', raising=False)
    monkeypatch.delenv('FEISHU_ALERT_WEBHOOK', raising=False)
    monkeypatch.delenv('FEISHU_WEBHOOK_URL', raising=False)
    from meta.core import alert_service as mod
    monkeypatch.setattr(mod, 'GROUP_WAIT_SECONDS', 30.0, raising=False)
    monkeypatch.setattr(mod, 'GROUP_INTERVAL_SECONDS', 300.0, raising=False)
    monkeypatch.setattr(mod, 'REPEAT_INTERVAL_SECONDS', 14400.0, raising=False)
    monkeypatch.setattr(mod, 'PER_FINGERPRINT_PER_MINUTE', 20, raising=False)
    monkeypatch.setattr(mod, 'PLATFORM_PER_MINUTE', 100, raising=False)
    monkeypatch.setattr(mod, 'PLATFORM_PER_SECOND', 5, raising=False)
    monkeypatch.setattr(mod, 'MAX_ATTEMPTS', 3, raising=False)
    monkeypatch.setattr(mod.AlertService, '_ds', lambda self: None)
    service = mod.AlertService()
    return service, mod


def test_group_wait_aggregates_duplicate_errors(alert_env):
    service, _mod = alert_env
    start = time.time()
    for _ in range(10):
        service.report('internal_error', endpoint='/api/v1/demo')

    # group_wait 未到 → 不发送
    assert service.flush(now=start + 10) == 0
    # 超过 30s → 聚合成 1 条
    assert service.flush(now=start + 31) == 1

    rows = service.list_alerts()
    assert len(rows) == 1
    assert rows[0]['count'] == 10
    assert rows[0]['fingerprint'] == 'internal_error::/api/v1/demo'


def test_repeat_interval_and_resolve(alert_env):
    service, _mod = alert_env
    start = time.time()
    service.report('internal_error', endpoint='/api/v1/demo')
    assert service.flush(now=start + 31) == 1

    # 新增错误：group_interval 内不再提醒
    service.report('internal_error', endpoint='/api/v1/demo')
    assert service.flush(now=start + 32) == 0

    # 超过 group_interval 但未到 repeat_interval → 只吞待发计数
    assert service.flush(now=start + 1 + 300) == 0

    # 超过 repeat_interval → 重复提醒一次
    service.report('internal_error', endpoint='/api/v1/demo')
    assert service.flush(now=start + 31 + 14401) == 1

    # 恢复后不再提醒
    assert service.resolve(error_code='internal_error', endpoint='/api/v1/demo') is True
    service.report('internal_error', endpoint='/api/v1/demo')
    # 恢复后再次出现属于新事件，需重新等待 group_wait
    assert service.flush(now=time.time() + 1) == 0


def test_fingerprint_rate_limit(alert_env):
    service, mod = alert_env
    mod.PER_FINGERPRINT_PER_MINUTE = 2
    fp = service.report('db_error', endpoint='/api/v1/demo')
    group = service._groups[fp]

    now = time.time()
    assert service._deliver(group, now=now) is True
    assert service._deliver(group, now=now + 1) is True
    # 第 3 次在 60s 窗口内 → 限流降级
    assert service._deliver(group, now=now + 2) is False
    assert group.delivery_status == 'rate_limited'
    assert group.next_retry_at is not None


def test_dead_letter_and_replay(alert_env):
    service, mod = alert_env
    service._send = lambda text: ('feishu', 'boom')  # noqa: E731

    fp = service.report('alert_delivery_failed', object_type='alert')
    group = service._groups[fp]
    now = time.time()
    for i in range(mod.MAX_ATTEMPTS):
        service._deliver(group, now=now + i)

    assert group.delivery_status == 'dead_letter'
    assert group.next_retry_at is None
    assert group.delivery_attempts == mod.MAX_ATTEMPTS

    assert service.replay(fingerprint=fp) is True
    assert group.delivery_status == 'retrying'
    assert group.next_retry_at is not None


def _ops_client(monkeypatch):
    monkeypatch.delenv('OPS_ADMIN_TOKEN', raising=False)
    from flask import Flask
    from meta.api.ops_api import ops_bp
    app = Flask(__name__)
    app.register_blueprint(ops_bp)
    app.config['TESTING'] = True
    return app.test_client()


def test_ops_health_contract(monkeypatch):
    client = _ops_client(monkeypatch)
    resp = client.get('/ops/health')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'status' in body
    assert isinstance(body['checks'], dict)


def test_ops_metrics_contract(monkeypatch):
    client = _ops_client(monkeypatch)
    resp = client.get('/ops/metrics')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'counters' in body['data']
    assert 'alerts' in body['data']


def test_ops_alerts_requires_token_when_configured(monkeypatch):
    client = _ops_client(monkeypatch)
    monkeypatch.setenv('OPS_ADMIN_TOKEN', 'secret-token')
    resp = client.get('/ops/alerts')
    assert resp.status_code == 401
    assert resp.get_json()['error_code'] == 'unauthorized'

    resp = client.get('/ops/alerts', headers={'X-Ops-Token': 'secret-token'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert isinstance(body['data'], list)


def test_ops_alert_replay_contract(monkeypatch):
    client = _ops_client(monkeypatch)
    import meta.core.alert_service as alert_mod

    monkeypatch.setattr(alert_mod, 'replay_alert', lambda alert_id=None: alert_id == 7)
    resp = client.post('/ops/alerts/7/replay')
    assert resp.status_code == 200
    assert resp.get_json() == {'success': True, 'message': 'replayed'}

    resp = client.post('/ops/alerts/8/replay')
    assert resp.get_json()['success'] is False


def test_scheduler_consecutive_failures_alert(monkeypatch):
    """[FR-010] 调度任务连续失败 3 次：状态可见且触发告警，恢复后清零。"""
    from meta.core.maintenance_scheduler import MaintenanceScheduler
    import meta.core.alert_service as alert_mod

    calls = []
    monkeypatch.setattr(alert_mod, 'report_alert',
                        lambda code, **kw: calls.append((code, kw)))
    monkeypatch.setattr(alert_mod, 'resolve_alert',
                        lambda **kw: calls.append(('resolve', kw)))

    sched = MaintenanceScheduler.__new__(MaintenanceScheduler)
    sched._run_stats = {}
    for _ in range(3):
        sched._record_run_outcome('cleanup', 'boom')

    stats = sched._run_stats['cleanup']
    assert stats['consecutive_failures'] == 3
    assert stats['last_status'] == 'failed'
    assert [c[0] for c in calls] == ['scheduler_job_failed'] * 3

    sched._record_run_outcome('cleanup', None)
    assert stats['consecutive_failures'] == 0
    assert stats['last_status'] == 'success'
    assert calls[-1][0] == 'resolve'


# ---------------------------------------------------------------- FR-012 监控接线


def test_monitor_db_reads_wal_size_kb(monkeypatch):
    from meta.core import monitor_runner as mr
    import meta.core.db_health_monitor as dbm

    calls = []
    monkeypatch.setattr(mr, '_alert', lambda c, o, m: calls.append(('alert', c, o)))
    monkeypatch.setattr(mr, '_resolve', lambda c, o: calls.append(('resolve', c, o)))

    class FakeMonitor:
        def get_report(self):
            return {'status': 'healthy', 'metrics': {'wal_size_kb': 200 * 1024}}

    monkeypatch.setattr(dbm, 'get_monitor', lambda path=None: FakeMonitor())
    mr._check_db()
    assert ('alert', 'db_health_warning', 'database') in calls
    assert not any(c[0] == 'resolve' for c in calls)


def test_monitor_cache_reads_performance_metrics(monkeypatch):
    from meta.core import monitor_runner as mr
    import meta.services.cache_monitor as cm
    import meta.api.permission_dimension_api as pda

    calls = []
    monkeypatch.setattr(mr, '_alert', lambda c, o, m: calls.append(('alert', c, o)))
    monkeypatch.setattr(mr, '_resolve', lambda c, o: calls.append(('resolve', c, o)))

    class FakeMonitor:
        def __init__(self, engine):
            pass

        def get_performance_report(self):
            return {'performance_metrics': {'hit_rate_value': 42.0}}

        def get_cache_stats(self):
            return {}

    monkeypatch.setattr(cm, 'CacheMonitor', FakeMonitor)
    monkeypatch.setattr(pda, '_get_engine', lambda: None)
    result = mr._check_cache()
    assert result['hit_rate'] == 42.0
    assert ('alert', 'db_health_warning', 'cache') in calls


def test_monitor_index_missing_triggers_alert(monkeypatch):
    from meta.core import monitor_runner as mr
    import meta.core.index_monitor as im
    import meta.core.datasource as ds_mod

    calls = []
    monkeypatch.setattr(mr, '_alert', lambda c, o, m: calls.append(('alert', c, o)))
    monkeypatch.setattr(mr, '_resolve', lambda c, o: calls.append(('resolve', c, o)))

    class FakeIndexMonitor:
        def __init__(self, ds):
            pass

        def get_summary(self):
            return {'total_missing_indexes': 2, 'critical_issues': 1}

    monkeypatch.setattr(im, 'IndexMonitor', FakeIndexMonitor)
    monkeypatch.setattr(ds_mod, 'get_platform_data_source', lambda: object())
    result = mr._check_indexes()
    assert result['missing_indexes'] == 2
    assert ('alert', 'db_health_warning', 'index') in calls


def test_monitor_cycle_respects_intervals(monkeypatch):
    from meta.core import monitor_runner as mr

    mr.reset_monitor_runner()
    calls = []
    monkeypatch.setattr(mr, '_check_db', lambda: calls.append('db') or {})
    monkeypatch.setattr(mr, '_check_db_lock', lambda: calls.append('db_lock'))
    monkeypatch.setattr(mr, '_check_indexes', lambda: calls.append('index') or {})
    monkeypatch.setattr(mr, '_check_cache', lambda: calls.append('cache') or {})

    mr.run_monitor_cycle(now=1000, force=True)
    assert set(calls) == {'db', 'db_lock', 'index', 'cache'}

    calls.clear()
    mr.run_monitor_cycle(now=1001, force=False)
    assert calls == []

    mr.run_monitor_cycle(now=1061, force=False)
    assert set(calls) == {'db', 'db_lock'}
    snapshot = mr.get_monitor_snapshot()
    assert set(snapshot['latest']) == {'db', 'db_lock', 'index', 'cache'}
    mr.reset_monitor_runner()