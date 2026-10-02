import pytest

pytestmark = pytest.mark.unit

# 平台内部表（task_slas / tasks / task_events）暂无 Factory；
# 按仓库既有惯例走 raw SQL escape hatch，避免用例被 conftest 整文件拦跳。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - SLA 独立对象（F2）
测试 meta.core.task_sla（第二轴：Stage × Has breached）

覆盖目标（对齐 §12.1 F2 / 综合 §4.2-3 / §12.1 Q3）：
  1. 独立第二轴：Stage（in_progress/paused/completed/cancelled）+ has_breached 正交
  2. 业务时间口径：暂停累计扣除；结束态按 ended_at 冻结
  3. 阈值快照：warn_at_pct / alert_at_pct / grace_seconds / on_breach
  4. 不污染主状态：SLA 生命周期不写 Task 状态列、不入事件账
"""

import json
from datetime import datetime, timedelta

from meta.core.task_sla import (
    ACTIVE_STAGES,
    ON_BREACH_ACTIONS,
    SLA_STAGES,
    SlaError,
    cancel_sla,
    close_sla,
    ensure_sla_tables,
    evaluate_sla,
    get_sla,
    list_slas,
    open_sla,
    open_sla_for_task,
    pause_sla,
    resume_sla,
    sla_tables_exist,
)

T0 = datetime(2026, 10, 2, 9, 0, 0)


def _at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（F2 表 + A1/A3 底座用于验证「不污染主状态」）。"""
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "f2.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_sla_tables(source)
    yield source


def _task_row(ds, task_id="T-1", *, sla=None, due_at=None):
    now = T0.isoformat(timespec="seconds")
    cols = ["id", "title", "type", "status", "executor_type", "sla", "due_at",
            "priority", "created_at", "updated_at"]
    vals = [task_id, "任务", "story", "in_progress", "human",
            json.dumps(sla) if sla is not None else None,
            due_at.isoformat(timespec="seconds") if due_at else None,
            "P2", now, now]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _count(ds, table, where="1=1", params=()):
    return ds.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchall()[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 表结构
# ─────────────────────────────────────────────────────────────────────────────

class TestSchema:
    """TC-F2-001~002 建表"""

    def test_TC_F2_001_建表(self, ds):
        assert sla_tables_exist(ds) == {"task_slas": True}
        assert SLA_STAGES == ("in_progress", "paused", "completed", "cancelled")
        assert ACTIVE_STAGES == ("in_progress", "paused")

    def test_TC_F2_002_建表幂等(self, ds):
        ensure_sla_tables(ds)          # 重放不报错
        ensure_sla_tables(ds)
        assert sla_tables_exist(ds)["task_slas"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 开单
# ─────────────────────────────────────────────────────────────────────────────

class TestOpen:
    """TC-F2-010~012 开单与任务桥接"""

    def test_TC_F2_010_开单派生due(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0,
                       on_breach="reassign")

        assert sla["stage"] == "in_progress"
        assert sla["has_breached"] == 0
        assert sla["last_escalation_rung"] == 0
        assert sla["on_breach"] == "reassign"
        assert sla["start_at"] == T0.isoformat(timespec="seconds")
        assert sla["due_at"] == _at(60).isoformat(timespec="seconds")

    def test_TC_F2_011_按任务快照开单(self, ds):
        _task_row(ds, sla={"warn_at_pct": 70, "grace_seconds": 300,
                           "on_breach": "escalate_fallback"},
                  due_at=_at(120))
        sla = open_sla_for_task(ds, "T-1", start_at=T0)

        assert sla["warn_at_pct"] == 70
        assert sla["grace_seconds"] == 300
        assert sla["on_breach"] == "escalate_fallback"
        assert sla["target_seconds"] == 7200        # 由 due_at 反推
        assert sla["workflow_run_id"] is None

    def test_TC_F2_012_任务不存在(self, ds):
        with pytest.raises(SlaError):
            open_sla_for_task(ds, "T-nope")


# ─────────────────────────────────────────────────────────────────────────────
# 进度派生（业务时间口径）
# ─────────────────────────────────────────────────────────────────────────────

class TestProgress:
    """TC-F2-020~026 evaluate_sla"""

    def test_TC_F2_020_初始无告警(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        p = evaluate_sla(sla, now=T0)

        assert p["pct_used"] == 0.0
        assert p["is_warn"] is False and p["is_breached"] is False

    def test_TC_F2_021_到预警阈值(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, warn_at_pct=80,
                       start_at=T0)
        p = evaluate_sla(sla, now=_at(49))          # 49min / 60min ≈ 81.7%

        assert p["is_warn"] is True
        assert p["is_breached"] is False

    def test_TC_F2_022_越线(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        p = evaluate_sla(sla, now=_at(61))

        assert p["is_breached"] is True
        assert p["is_dead_letter"] is False

    def test_TC_F2_023_宽限期后死信(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, grace_seconds=600,
                       start_at=T0)

        assert evaluate_sla(sla, now=_at(65))["is_dead_letter"] is False
        assert evaluate_sla(sla, now=_at(71))["is_dead_letter"] is True

    def test_TC_F2_024_暂停扣除业务时间(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        pause_sla(ds, sla["id"], at=_at(30))

        p = evaluate_sla(get_sla(ds, sla["id"]), now=_at(50))

        # 暂停期间业务时间冻结在 30min
        assert p["elapsed_seconds"] == pytest.approx(1800, abs=1)

    def test_TC_F2_025_恢复后继续计时(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        pause_sla(ds, sla["id"], at=_at(30))
        resumed = resume_sla(ds, sla["id"], at=_at(50))

        assert resumed["stage"] == "in_progress"
        assert resumed["paused_seconds"] == pytest.approx(1200, abs=1)
        p = evaluate_sla(resumed, now=_at(70))
        assert p["elapsed_seconds"] == pytest.approx(3000, abs=1)   # 70 - 20(暂停)

    def test_TC_F2_026_结束态冻结(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        closed = close_sla(ds, sla["id"], achieved=True, at=_at(30))

        p = evaluate_sla(closed, now=_at(999))
        assert p["pct_used"] == pytest.approx(50.0, abs=0.1)
        assert p["is_breached"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 状态推进
# ─────────────────────────────────────────────────────────────────────────────

class TestLifecycle:
    """TC-F2-030~033 pause/resume/close/cancel"""

    def test_TC_F2_030_暂停态校验(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        pause_sla(ds, sla["id"], at=_at(10))

        with pytest.raises(SlaError):
            pause_sla(ds, sla["id"], at=_at(20))      # 已 paused，不能重复暂停
        with pytest.raises(SlaError):
            resume_sla(ds, open_sla(ds, task_id="T-2", target_seconds=60,
                                    start_at=T0)["id"], at=_at(20))  # 未暂停不能恢复

    def test_TC_F2_031_关闭记越线(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        closed = close_sla(ds, sla["id"], achieved=False, at=_at(30))

        assert closed["stage"] == "completed"
        assert closed["has_breached"] == 1
        assert closed["ended_at"] is not None

    def test_TC_F2_032_作废不计越线(self, ds):
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        cancelled = cancel_sla(ds, sla["id"], at=_at(120))

        assert cancelled["stage"] == "cancelled"
        assert cancelled["has_breached"] == 0

    def test_TC_F2_033_按任务与活跃过滤(self, ds):
        a = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        open_sla(ds, task_id="T-2", target_seconds=3600, start_at=T0)
        close_sla(ds, a["id"], achieved=True, at=_at(10))

        assert len(list_slas(ds, task_id="T-1")) == 1
        assert len(list_slas(ds, task_id="T-1", active_only=True)) == 0
        assert len(list_slas(ds, active_only=True)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 第二轴纪律（不污染主状态 / 不入事件账）
# ─────────────────────────────────────────────────────────────────────────────

class TestSecondAxis:
    """TC-F2-040~041 双轴 ≠ 双状态列"""

    def test_TC_F2_040_不写任务状态不落事件账(self, ds):
        _task_row(ds, "T-1")
        sla = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        pause_sla(ds, sla["id"], at=_at(10))
        resume_sla(ds, sla["id"], at=_at(20))
        close_sla(ds, sla["id"], achieved=False, at=_at(4000))

        # 任务状态列与事件账完全未被 SLA 生命周期触碰（Q3 拍板）
        assert ds.execute("SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "in_progress"
        assert _count(ds, "task_events") == 0

    def test_TC_F2_041_两轴正交(self, ds):
        """stage 与 has_breached 是两条独立轴：未越线也可关闭，越线也可仍在计时。"""
        a = open_sla(ds, task_id="T-1", target_seconds=3600, start_at=T0)
        b = open_sla(ds, task_id="T-2", target_seconds=60, start_at=T0)
        closed = close_sla(ds, a["id"], achieved=True, at=_at(10))

        assert closed["stage"] == "completed" and closed["has_breached"] == 0
        still = get_sla(ds, b["id"])
        assert still["stage"] == "in_progress"
        assert evaluate_sla(still, now=_at(30))["is_breached"] is True
        assert ON_BREACH_ACTIONS == ("notify", "reassign", "escalate_fallback", "dead_letter")