import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks / task_events / task_slas）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - 统一心跳（A5）
测试 meta.core.task_tick（§12.1 A5 / §8.2 / §7.6）

覆盖目标：
  1. 三段联动：direct 派工 / claim 超时回收 / SLA 梯队告警（一次心跳全产出）
  2. 幂等：重复 tick 不重复派工、不重复回收、不重复告警
  3. 隔离：单任务失败收集进 errors，其余照常；段级异常不中断后续段
  4. 开关：分段关闸（运维排查用）
"""

import json
from datetime import datetime, timedelta

import meta.core.task_tick as task_tick
from meta.core.task_tick import platform_tick

T0 = datetime(2026, 10, 2, 9, 0, 0)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_schema import ensure_task_tables
    from meta.core.task_sla import ensure_sla_tables

    source = get_data_source("sqlite", database=str(tmp_path / "tick.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_sla_tables(source)
    yield source


def _task(ds, *, task_id="T-1", status="ready", policy="direct",
          assignee=None, candidates=None, claim_timeout=300):
    cols = ["id", "title", "type", "status", "executor_type", "assign_policy",
            "executor_assignee", "executor_candidates", "claim_timeout_seconds",
            "created_at", "updated_at"]
    vals = [task_id, "测试任务", "automation", status, "human", policy,
            assignee, json.dumps(candidates) if candidates is not None else None,
            claim_timeout, T0.isoformat(timespec="seconds"),
            T0.isoformat(timespec="seconds")]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _sla(ds, *, task_id="T-SLA", target=1000, warn=80, alert=100, grace=5000):
    from meta.core.task_sla import open_sla
    return open_sla(ds, task_id=task_id, target_seconds=target,
                    warn_at_pct=warn, alert_at_pct=alert, grace_seconds=grace,
                    start_at=T0)


def _status(ds, task_id):
    return ds.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 编排
# ─────────────────────────────────────────────────────────────────────────────

class TestTick:
    """TC-TICK-001~005 心跳编排"""

    def test_TC_TICK_001_三段联动(self, ds):
        _task(ds, task_id="T-A", policy="direct", assignee="u1")      # 待派工
        _task(ds, task_id="T-B", policy="claim", status="claimed",
              assignee="u2", candidates=["u2"])                       # 待回收
        _task(ds, task_id="T-C", policy="claim", candidates=["u3"])   # claim 不派工
        _sla(ds, task_id="T-SLA", target=1000, warn=80, grace=5000)   # 900s → warn

        result = platform_tick(ds, now=_at(900))

        assert [d["task_id"] for d in result["dispatched"]] == ["T-A"]
        assert result["dispatched"][0]["assignee"] == "u1"
        assert _status(ds, "T-A") == "claimed"
        assert [x["task_id"] for x in result["reclaimed"]] == ["T-B"]
        assert _status(ds, "T-B") == "ready"
        assert _status(ds, "T-C") == "ready"      # claim 策略不派工
        assert len(result["escalations"]) == 1
        esc = result["escalations"][0]
        assert esc["task_id"] == "T-SLA"
        assert esc["rung_name"] == "warn"
        assert esc["action"] == "notify"
        assert result["errors"] == []
        assert result["counts"] == {"dispatched": 1, "reclaimed": 1,
                                    "escalations": 1, "errors": 0}

    def test_TC_TICK_002_重复tick幂等(self, ds):
        _task(ds, task_id="T-A", policy="direct", assignee="u1")
        _task(ds, task_id="T-B", policy="claim", status="claimed",
              assignee="u2", candidates=["u2"])
        _sla(ds, task_id="T-SLA")

        first = platform_tick(ds, now=_at(900))
        second = platform_tick(ds, now=_at(900))

        assert first["counts"] == {"dispatched": 1, "reclaimed": 1,
                                   "escalations": 1, "errors": 0}
        assert second["counts"] == {"dispatched": 0, "reclaimed": 0,
                                    "escalations": 0, "errors": 0}

    def test_TC_TICK_003_单任务失败隔离(self, ds, monkeypatch):
        _task(ds, task_id="T-OK", policy="direct", assignee="u1")
        _task(ds, task_id="T-BAD", policy="direct", assignee="u2")

        real = task_tick.resolve_assignment

        def fake(data_source, task_id, *, now=None):
            if task_id == "T-BAD":
                raise RuntimeError("boom")
            return real(data_source, task_id, now=now)

        monkeypatch.setattr(task_tick, "resolve_assignment", fake)

        result = platform_tick(ds, now=_at(0))

        assert sorted(d["task_id"] for d in result["dispatched"]) == ["T-OK"]
        assert len(result["errors"]) == 1
        assert result["errors"][0]["stage"] == "dispatch"
        assert result["errors"][0]["task_id"] == "T-BAD"
        assert _status(ds, "T-OK") == "claimed"
        assert _status(ds, "T-BAD") == "ready"    # 失败任务未被误改，下轮自愈

    def test_TC_TICK_004_段开关(self, ds):
        _task(ds, task_id="T-A", policy="direct", assignee="u1")

        result = platform_tick(ds, now=_at(0), dispatch=False,
                               reclaim=False, escalate=False)

        assert result["counts"] == {"dispatched": 0, "reclaimed": 0,
                                    "escalations": 0, "errors": 0}
        assert _status(ds, "T-A") == "ready"

    def test_TC_TICK_005_段级异常不中断(self, ds, monkeypatch):
        _task(ds, task_id="T-A", policy="direct", assignee="u1")

        def boom(*args, **kwargs):
            raise RuntimeError("reclaim down")

        monkeypatch.setattr(task_tick, "reclaim_expired", boom)

        result = platform_tick(ds, now=_at(0))

        assert result["counts"]["dispatched"] == 1   # 前一/后一段照常
        assert _status(ds, "T-A") == "claimed"
        assert any(e["stage"] == "reclaim" for e in result["errors"])


# ─────────────────────────────────────────────────────────────────────────────
# 调度挂载适配（A5 接入 TaskScheduler）
# ─────────────────────────────────────────────────────────────────────────────

class TestPlatformTickHandler:
    """TC-TICK-006~008 调度挂载：handler 适配 + 种子行"""

    def test_TC_TICK_006_handler适配(self, ds):
        from meta.handlers.platform_handlers import PlatformTickHandler

        _task(ds, task_id="T-A", policy="direct", assignee="u1")

        result = PlatformTickHandler().execute({}, {'data_source': ds})

        assert result.success is True
        assert result.data["counts"]["dispatched"] == 1
        assert _status(ds, "T-A") == "claimed"

    def test_TC_TICK_007_errors时success为False(self, ds, monkeypatch):
        from meta.handlers.platform_handlers import PlatformTickHandler

        _task(ds, task_id="T-BAD", policy="direct", assignee="u1")

        def boom(data_source, task_id, *, now=None):
            raise RuntimeError("boom")

        monkeypatch.setattr(task_tick, "resolve_assignment", boom)

        result = PlatformTickHandler().execute({}, {'data_source': ds})

        assert result.success is False
        assert result.data["errors"][0]["stage"] == "dispatch"

    def test_TC_TICK_008_种子行可调度(self, ds):
        from meta.core.cron_parser import CronParser
        from meta.scripts.init_task_seed import init_task_seed_data

        init_task_seed_data(ds)

        rows = ds.execute(
            "SELECT handler, trigger_mode, schedule, enabled "
            "FROM scheduled_tasks WHERE code = 'platform_tick'"
        ).fetchall()
        assert len(rows) == 1
        handler, trigger_mode, schedule, enabled = rows[0]
        assert handler == 'platform_tick'      # 与 server.py 注册名一致
        assert trigger_mode == 'cron'
        assert enabled == 1
        # 调度表达式须能被实际调度器解析（否则加载时静默跳过）
        assert CronParser().get_next(schedule, T0) is not None