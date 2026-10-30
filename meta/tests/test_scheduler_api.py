# -*- coding: utf-8 -*-
"""进程内调度器运维端点回归 —— 只读状态 + 按需触发（替换路径收口后补齐）

背景（替换路径第 3 项收口后）:
  清理 scheduled_tasks 历史行、进程内调度器成为唯一 cron 路径后，运维侧暴露三处缺口:
    C1 缺只读视图：看不到两个进程内调度器挂了哪些作业 / 下次何时跑；
    C2 缺按需触发：原走遗留调度器的手工 trigger 入口消失；
    C3 遗留 task_api 的 trigger/enable/disable 对**已迁出作业码**仍回
       success:true（假成功）—— 表里已无该行，改不动却报成功。

  新端点**不能**挂进 task_api_bp：它被 `tasks` 模块开关门控（server.py 仅在
  is_module_enabled('tasks') 时注册），而运维作业是平台基础设施、与任务模块开关
  无关 —— 故本蓝图独立且**无条件注册**。

本测试锁定:
  1. GET /api/v2/schedulers/status 暴露两个调度器的作业状态（含 paused 标志）；
  2. 两个调度器均未接线 → 503；处于暂停态 → 200 且 paused=True；
  3. POST /api/v2/schedulers/<code>/run-now 命中运维作业真派发；
  4. platform_tick 走平台调度器；
  5. 未知 job code → 404；
  6. 遗留 trigger/enable/disable 路由已随 scheduled_tasks 退役（v155）删除 → 404。
"""
import pytest
from flask import Flask

from meta.api.scheduler_api import (
    scheduler_bp,
    set_inprocess_schedulers,
)
from meta.core.maintenance_scheduler import MaintenanceScheduler, JOB_CODES
from meta.core.platform_scheduler import PlatformScheduler


@pytest.fixture(autouse=True)
def _reset_schedulers():
    """每个用例前后都清空注入，避免跨用例串状态。"""
    set_inprocess_schedulers(None, None)
    yield
    set_inprocess_schedulers(None, None)


def _client():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(scheduler_bp)
    return app.test_client()


def _wired(paused=False):
    """接线两个真调度器（handler 用可观测的 lambda 记录派发）。"""
    maint = MaintenanceScheduler(data_source=object())
    plat = PlatformScheduler(data_source=object())
    set_inprocess_schedulers(maint, plat, paused=paused)
    return maint, plat


# ─────────────────────────────────────────────────────────────────────────────
# C1 只读状态
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test调度器状态端点:
    def test_暴露两个调度器的作业(self):
        maint, plat = _wired()
        resp = _client().get('/api/v2/schedulers/status')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        data = body['data']
        assert data['paused'] is False
        # 运维 8 个作业来自 MaintenanceScheduler
        assert set(data['maintenance'].keys()) == {j['code'] for j in maint._jobs}
        assert 'db_analyze' in data['maintenance']
        # 任务域作业来自 PlatformScheduler
        assert 'platform_tick' in data['platform']
        assert set(data['platform'].keys()) == {'platform_tick'}
        # 每作业带 handler 就绪标记（运维可用性自检的立足点）
        assert data['maintenance']['db_analyze']['handler_registered'] is False

    def test_未接线返回503(self):
        resp = _client().get('/api/v2/schedulers/status')
        assert resp.status_code == 503

    def test_暂停态返回200且标记paused(self):
        set_inprocess_schedulers(None, None, paused=True)
        resp = _client().get('/api/v2/schedulers/status')
        assert resp.status_code == 200
        assert resp.get_json()['data']['paused'] is True


# ─────────────────────────────────────────────────────────────────────────────
# C2 按需触发
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test按需触发:
    def test_运维作业真派发(self):
        maint, _ = _wired()
        fired = []
        maint.register_handler('db_analyze', lambda p, c: fired.append('db_analyze'))
        resp = _client().post('/api/v2/schedulers/db_analyze/run-now')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        assert fired == ['db_analyze']

    def test_platform_tick_走平台调度器(self):
        _, plat = _wired()
        fired = []
        plat.register_handler('platform_tick', lambda p, c: fired.append('platform_tick'))
        resp = _client().post('/api/v2/schedulers/platform_tick/run-now')
        assert resp.status_code == 200
        assert fired == ['platform_tick']

    def test_未注册handler返回409(self):
        _wired()  # 两个调度器都接线了，但没有注册任何 handler
        resp = _client().post('/api/v2/schedulers/db_analyze/run-now')
        assert resp.status_code == 409

    def test_未知code返回404(self):
        _wired()
        resp = _client().post('/api/v2/schedulers/not_a_job/run-now')
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# C3 遗留端点不再假成功
# ─────────────────────────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _LegacyDS:
    def __init__(self, rowcount=0):
        self._rowcount = rowcount

    def execute(self, sql, params=None):
        return _Cursor(self._rowcount)

    def commit(self):
        pass


class _LegacySchedulerStub:
    """模拟遗留 TaskScheduler 对已迁出作业码的现况：_tasks 里查不到。"""

    def __init__(self, rowcount=0):
        self.data_source = _LegacyDS(rowcount)

    def trigger_task(self, code):
        raise ValueError(f'Task {code} not found')

    def reload(self):
        pass


def _legacy_client(scheduler):
    from meta.api.task_api import task_api_bp, set_scheduler
    set_scheduler(scheduler)
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(task_api_bp)
    return app.test_client()


@pytest.mark.unit
class Test遗留端点随表退役:
    """[task-two-generation 2026-10-30] scheduled_tasks 退役（v155）后，
    trigger/enable/disable 三条遗留路由已从 task_api_bp 删除 —— 请求应得 404。
    cron 的唯一入口是 /api/v2/schedulers/*（run-now / status）。"""

    def test_trigger_路由已删除(self):
        client = _legacy_client(_LegacySchedulerStub())
        assert client.post('/api/v2/tasks/db_analyze/trigger').status_code == 404

    def test_enable_路由已删除(self):
        client = _legacy_client(_LegacySchedulerStub(rowcount=1))
        assert client.post('/api/v2/tasks/some_legacy_job/enable').status_code == 404

    def test_disable_路由已删除(self):
        client = _legacy_client(_LegacySchedulerStub(rowcount=1))
        assert client.post('/api/v2/tasks/not_a_job/disable').status_code == 404

