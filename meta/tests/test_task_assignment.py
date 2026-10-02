import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks / task_events）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - 分配与认领（A4）
测试 meta.core.task_assignment（§8.2 决策树 / §12.1 A4 / §13 R5）

覆盖目标：
  1. direct：锁定 assignee（ready→claimed + 事件账）
  2. claim：投递候选池不锁人；候选命中方可认领
  3. 门禁：非候选 / 非 claim 策略 / 非 ready / 三策略关闸 / 未知策略 → 拒绝
  4. 并发：条件 UPDATE 抢单，第二个失败
  5. 回收：超 claim_timeout 自动 claimed→ready + 清 assignee；未超时不动
  6. 反查：list_claimable 按候选池过滤
"""

import json
from datetime import datetime, timedelta

from meta.core.task_assignment import (
    DEFAULT_ASSIGN_POLICY,
    DEFERRED_POLICIES,
    ENABLED_POLICIES,
    AssignmentError,
    claim_task,
    is_candidate,
    list_claimable,
    reclaim_expired,
    resolve_assignment,
)

T0 = datetime(2026, 10, 2, 9, 0, 0)


def _at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "a4.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
    yield source


def _task(ds, *, task_id="T-1", status="ready", policy="direct",
          assignee=None, candidates=None, claim_timeout=300, run_id="R-1"):
    cols = ["id", "title", "type", "status", "executor_type", "assign_policy",
            "executor_assignee", "executor_candidates", "claim_timeout_seconds",
            "workflow_run_id", "created_at", "updated_at"]
    vals = [task_id, "测试任务", "automation", status, "human", policy,
            assignee, json.dumps(candidates) if candidates is not None else None,
            claim_timeout, run_id, T0.isoformat(timespec="seconds"),
            T0.isoformat(timespec="seconds")]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _status(ds, task_id):
    return ds.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]


def _assignee(ds, task_id):
    return ds.execute("SELECT executor_assignee FROM tasks WHERE id = ?",
                      (task_id,)).fetchall()[0][0]


def _count(ds, table, where="1=1", params=()):
    return ds.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchall()[0][0]


def _events(ds, task_id):
    return ds.execute(
        "SELECT from_status, to_status, actor FROM task_events WHERE task_id = ? "
        "ORDER BY occurred_at", (task_id,),
    ).fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# 投递
# ─────────────────────────────────────────────────────────────────────────────

class TestResolve:
    """TC-A4-001~004 投递决策"""

    def test_TC_A4_001_direct锁定认领人(self, ds):
        _task(ds, policy="direct", assignee="u1")

        result = resolve_assignment(ds, "T-1", now=_at(0))

        assert result["status"] == "claimed"
        assert result["assignee"] == "u1"
        assert _status(ds, "T-1") == "claimed"
        assert _assignee(ds, "T-1") == "u1"
        assert _events(ds, "T-1") == [("ready", "claimed", "u1")]
        assert _count(ds, "task_worklogs", "task_id = ?", ("T-1",)) == 1

    def test_TC_A4_002_direct缺指派人拒绝(self, ds):
        _task(ds, policy="direct", assignee=None)

        with pytest.raises(AssignmentError):
            resolve_assignment(ds, "T-1")

        assert _status(ds, "T-1") == "ready"
        assert _count(ds, "task_events") == 0

    def test_TC_A4_003_非ready不可投递(self, ds):
        _task(ds, policy="direct", assignee="u1", status="pending")

        with pytest.raises(AssignmentError):
            resolve_assignment(ds, "T-1")

    def test_TC_A4_004_claim投递不锁人(self, ds):
        _task(ds, policy="claim", candidates=["u1", "u2"])

        result = resolve_assignment(ds, "T-1")

        assert result["status"] == "ready"
        assert result["assignee"] is None
        assert _status(ds, "T-1") == "ready"          # 仍等人认领
        assert _assignee(ds, "T-1") is None


# ─────────────────────────────────────────────────────────────────────────────
# 认领
# ─────────────────────────────────────────────────────────────────────────────

class TestClaim:
    """TC-A4-010~014 抢单"""

    def test_TC_A4_010_候选命中认领成功(self, ds):
        _task(ds, policy="claim", candidates=["u1", "u2"])

        result = claim_task(ds, "T-1", "u1", now=_at(0))

        assert result["status"] == "claimed"
        assert _status(ds, "T-1") == "claimed"
        assert _assignee(ds, "T-1") == "u1"
        assert _events(ds, "T-1") == [("ready", "claimed", "u1")]

    def test_TC_A4_011_非候选拒绝(self, ds):
        _task(ds, policy="claim", candidates=["u2"])

        with pytest.raises(AssignmentError):
            claim_task(ds, "T-1", "u1")

        assert _status(ds, "T-1") == "ready"
        assert _count(ds, "task_events") == 0

    def test_TC_A4_012_direct策略不可抢单(self, ds):
        _task(ds, policy="direct", assignee="u1")

        with pytest.raises(AssignmentError):
            claim_task(ds, "T-1", "u1")

    def test_TC_A4_013_并发第二个被拒(self, ds):
        _task(ds, policy="claim", candidates=["u1", "u2"])
        claim_task(ds, "T-1", "u1")

        with pytest.raises(AssignmentError):
            claim_task(ds, "T-1", "u2")

        assert _assignee(ds, "T-1") == "u1"           # 先到者胜
        assert _count(ds, "task_events") == 1

    def test_TC_A4_014_非ready不可认领(self, ds):
        _task(ds, policy="claim", candidates=["u1"], status="in_progress")

        with pytest.raises(AssignmentError):
            claim_task(ds, "T-1", "u1")


# ─────────────────────────────────────────────────────────────────────────────
# 超时回收
# ─────────────────────────────────────────────────────────────────────────────

class TestReclaim:
    """TC-A4-020~023 claimed→ready（claim_timed_out）"""

    def test_TC_A4_020_超时回收(self, ds):
        _task(ds, policy="claim", candidates=["u1"], claim_timeout=300)
        claim_task(ds, "T-1", "u1", now=_at(0))

        reclaimed = reclaim_expired(ds, now=_at(301))

        assert [x["task_id"] for x in reclaimed] == ["T-1"]
        assert _status(ds, "T-1") == "ready"
        assert _assignee(ds, "T-1") is None           # 清空认领人
        assert ("claimed", "ready", "system") in _events(ds, "T-1")

    def test_TC_A4_021_未超时不动(self, ds):
        _task(ds, policy="claim", candidates=["u1"], claim_timeout=300)
        claim_task(ds, "T-1", "u1", now=_at(0))

        assert reclaim_expired(ds, now=_at(1)) == []     # 60s < 300s
        assert _status(ds, "T-1") == "claimed"

    def test_TC_A4_022_等于超时不回收(self, ds):
        _task(ds, policy="claim", candidates=["u1"], claim_timeout=300)
        claim_task(ds, "T-1", "u1", now=_at(0))

        assert reclaim_expired(ds, now=_at(5)) == []     # 恰 300s；守卫为严格 >
        assert _status(ds, "T-1") == "claimed"

    def test_TC_A4_023_direct不参与回收(self, ds):
        _task(ds, policy="direct", assignee="u1", claim_timeout=1)
        resolve_assignment(ds, "T-1", now=_at(0))

        assert reclaim_expired(ds, now=_at(9999)) == []  # 只扫 claim
        assert _status(ds, "T-1") == "claimed"

    def test_TC_A4_024_无认领事件回退updated_at回收(self, ds):
        # 经非 claim_task 路径进入 claimed（无 ready→claimed 事件）：
        # 回退 tasks.updated_at 作为认领时间，仍可超时回收（不永久卡死）
        _task(ds, status="claimed", policy="claim", assignee="u1",
              candidates=["u1"], claim_timeout=300)
        assert _events(ds, "T-1") == []

        reclaimed = reclaim_expired(ds, now=_at(301))

        assert [x["task_id"] for x in reclaimed] == ["T-1"]
        assert _status(ds, "T-1") == "ready"
        assert _assignee(ds, "T-1") is None

    def test_TC_A4_025_无事件且无updated_at跳过(self, ds):
        # 两个时间源都缺失 → 跳过（不臆造时间，fail-closed）
        _task(ds, status="claimed", policy="claim", assignee="u1",
              candidates=["u1"], claim_timeout=300)
        ds.execute("UPDATE tasks SET updated_at = NULL WHERE id = ?", ("T-1",))

        assert reclaim_expired(ds, now=_at(9999)) == []
        assert _status(ds, "T-1") == "claimed"


# ─────────────────────────────────────────────────────────────────────────────
# 策略门禁 / 反查
# ─────────────────────────────────────────────────────────────────────────────

class TestPolicyGate:
    """TC-A4-030~032 未开启策略 fail-closed"""

    @pytest.mark.parametrize("policy", DEFERRED_POLICIES)
    def test_TC_A4_030_三策略关闸(self, ds, policy):
        _task(ds, policy=policy, candidates=["u1"])

        with pytest.raises(AssignmentError):
            resolve_assignment(ds, "T-1")

        assert _status(ds, "T-1") == "ready"

    def test_TC_A4_031_未知策略拒绝(self, ds):
        _task(ds, policy="weird", candidates=["u1"])

        with pytest.raises(AssignmentError):
            resolve_assignment(ds, "T-1")

    def test_TC_A4_032_已开启集合(self):
        assert ENABLED_POLICIES == ("direct", "claim")
        assert DEFAULT_ASSIGN_POLICY == "direct"
        assert "round_robin" in DEFERRED_POLICIES


class TestVisibility:
    """TC-A4-040 候选池反查"""

    def test_TC_A4_040_只返回自己可认领的(self, ds):
        _task(ds, task_id="T-1", policy="claim", candidates=["u1", "u2"])
        _task(ds, task_id="T-2", policy="claim", candidates=["u2"])
        _task(ds, task_id="T-3", policy="direct", assignee="u1")

        mine = list_claimable(ds, "u1")

        assert [x["task_id"] for x in mine] == ["T-1"]
        assert is_candidate({"executor_candidates": ["u9"]}, "u1") is False


class TestRowcountFallback:
    """TC-A4-050~051 驱动不返回 rowcount 时的回读复核（fail-closed）"""

    def test_TC_A4_050_rowcount缺失回读复核成功(self, ds, monkeypatch):
        _task(ds, policy="claim", candidates=["u1"])
        real_execute = ds.execute

        class _NoRowcount:
            def __init__(self, cur):
                self._cur = cur

            def fetchall(self):
                return self._cur.fetchall()

            @property
            def rowcount(self):
                return None

        def wrap(command, params=None):
            cur = real_execute(command, params)
            if command.strip().startswith("UPDATE"):
                return _NoRowcount(cur)   # 模拟驱动不返回 rowcount
            return cur

        monkeypatch.setattr(ds, "execute", wrap, raising=False)

        result = claim_task(ds, "T-1", "u1", now=_at(0))

        assert result["status"] == "claimed"
        assert _status(ds, "T-1") == "claimed"

    def test_TC_A4_051_rowcount缺失且未更新拒绝认领(self, ds, monkeypatch):
        _task(ds, policy="claim", candidates=["u1"])
        real_execute = ds.execute

        class _NoRowcount:
            @property
            def rowcount(self):
                return None

            def fetchall(self):
                return []

        def wrap(command, params=None):
            if command.strip().startswith("UPDATE"):
                return _NoRowcount()      # 模拟更新未生效
            return real_execute(command, params)

        monkeypatch.setattr(ds, "execute", wrap, raising=False)

        with pytest.raises(AssignmentError):
            claim_task(ds, "T-1", "u1", now=_at(0))

        assert _status(ds, "T-1") == "ready"   # fail-closed：不把失败当成功