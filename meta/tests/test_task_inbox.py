import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks / task_events / task_slas）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - 统一收件箱（A8）
测试 meta.core.task_inbox（§9.4 / §12.1 A8 / Q1 行级可见性硬项）

覆盖目标：
  1. 可见性 fail-closed：actor 空 / 无关者不可见；assignee / candidate / 创建者 / 角色→应用
  2. 桶派生：todo / approval / agent_handoff / claimable / alert，每任务一条 + primary 优先级
  3. 告警：SLA 越线任务进 alert 桶（primary 压过 todo）
  4. 排序（updated desc → due asc）/ 过滤 / limit；counts 全量口径
  5. 降级：无 SLA 表不崩；未知桶报错
"""

import json
from datetime import datetime, timedelta

from meta.core.task_inbox import BUCKETS, inbox_counts, inbox_query

T0 = datetime(2026, 10, 2, 9, 0, 0)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _build(tmp_path, name, *, with_sla):
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / name))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        if with_sla:
            from meta.core.task_sla import ensure_sla_tables
            ensure_sla_tables(source)
    return source


@pytest.fixture()
def ds(tmp_path):
    yield _build(tmp_path, "inbox.db", with_sla=True)


@pytest.fixture()
def ds_no_sla(tmp_path):
    yield _build(tmp_path, "inbox_no_sla.db", with_sla=False)


def _task(ds, *, task_id, status="ready", type_="story", policy="direct",
          assignee=None, candidates=None, created_by="owner", app_id="wms",
          updated_at=None, due_at=None, executor_type="human",
          agent_session_id=None):
    cols = ["id", "title", "type", "status", "priority", "app_id",
            "executor_type", "assign_policy", "executor_assignee",
            "executor_candidates", "created_by", "due_at",
            "agent_session_id", "created_at", "updated_at"]
    vals = [task_id, "测试任务", type_, status, "normal", app_id,
            executor_type, policy, assignee,
            json.dumps(candidates) if candidates is not None else None,
            created_by,
            (due_at or updated_at or T0).isoformat(timespec="seconds"),
            agent_session_id,
            T0.isoformat(timespec="seconds"),
            (updated_at or T0).isoformat(timespec="seconds")]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _sla(ds, *, task_id, target=1000, warn=80, alert=100, grace=5000):
    from meta.core.task_sla import open_sla
    return open_sla(ds, task_id=task_id, target_seconds=target,
                    warn_at_pct=warn, alert_at_pct=alert, grace_seconds=grace,
                    start_at=T0)


def _ids(result):
    return [e["task_id"] for e in result["entries"]]


# ─────────────────────────────────────────────────────────────────────────────
# 可见性（Q1 硬项）
# ─────────────────────────────────────────────────────────────────────────────

class TestVisibility:
    """TC-INBOX-001~003 行级可见性 fail-closed"""

    def test_TC_INBOX_001_无身份与无关者不可见(self, ds):
        _task(ds, task_id="T-MINE", assignee="u1", status="in_progress")
        _task(ds, task_id="T-OTHER", assignee="u2", created_by="u2",
              status="in_progress")

        assert inbox_query(ds, actor=None)["total"] == 0      # fail-closed
        assert inbox_query(ds, actor="u9")["total"] == 0      # 无关者
        assert _ids(inbox_query(ds, actor="u1")) == ["T-MINE"]
        assert _ids(inbox_query(ds, actor="u2")) == ["T-OTHER"]

    def test_TC_INBOX_002_候选池可见为可抢单(self, ds):
        _task(ds, task_id="T-CLAIM", policy="claim", candidates=["u1"],
              created_by="u2")

        result = inbox_query(ds, actor="u1")

        assert _ids(result) == ["T-CLAIM"]
        assert result["entries"][0]["buckets"] == ["claimable"]

    def test_TC_INBOX_003_角色应用授权与app收窄(self, ds):
        _task(ds, task_id="T-APP", assignee="u2", created_by="u2",
              app_id="wms", status="in_progress")
        _sla(ds, task_id="T-APP")                            # 900s → warn

        now = _at(900)
        # 无授权：u9 与 T-APP 无关 → 不可见（fail-closed）
        assert inbox_query(ds, actor="u9", now=now)["total"] == 0
        # 角色 → 应用授权命中 → 可见（alert 桶）
        granted = inbox_query(ds, actor="u9", now=now,
                              role_apps={"planner": ["wms"]},
                              actor_roles=["planner"])
        assert _ids(granted) == ["T-APP"]
        assert granted["entries"][0]["primary_bucket"] == "alert"
        # app_id 收窄：不匹配 → 0（即便授权）
        assert inbox_query(ds, actor="u9", now=now, app_id="tms",
                           role_apps={"planner": ["wms"]},
                           actor_roles=["planner"])["total"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 桶派生
# ─────────────────────────────────────────────────────────────────────────────

class TestBuckets:
    """TC-INBOX-010~013 分区与 primary 优先级"""

    def test_TC_INBOX_010_桶派生每任务一条(self, ds):
        _task(ds, task_id="T-TODO", assignee="u1", status="in_progress")
        _task(ds, task_id="T-APPR", assignee="u1", status="ready",
              type_="approval")
        _task(ds, task_id="T-CLAIM", policy="claim", candidates=["u1"])
        _task(ds, task_id="T-HANDOFF", assignee="u1", status="ready",
              executor_type="human", agent_session_id="S-1")

        result = inbox_query(ds, actor="u1")
        entries = {e["task_id"]: e for e in result["entries"]}

        assert len(result["entries"]) == 4                 # 每任务一条
        assert entries["T-TODO"]["buckets"] == ["todo"]
        assert entries["T-APPR"]["buckets"] == ["approval", "todo"]
        assert entries["T-APPR"]["primary_bucket"] == "approval"
        assert entries["T-CLAIM"]["buckets"] == ["claimable"]
        assert entries["T-HANDOFF"]["buckets"] == ["todo", "agent_handoff"]
        assert entries["T-HANDOFF"]["is_handoff"] is True
        assert result["counts"] == {"alert": 0, "approval": 1, "todo": 3,
                                    "agent_handoff": 1, "claimable": 1,
                                    "total": 4}

    def test_TC_INBOX_011_告警桶primary压过todo(self, ds):
        _task(ds, task_id="T-1", assignee="u1", status="in_progress")
        _sla(ds, task_id="T-1")                            # warn 梯级

        result = inbox_query(ds, actor="u1", now=_at(900))
        entry = result["entries"][0]

        assert entry["buckets"] == ["alert", "todo"]
        assert entry["primary_bucket"] == "alert"
        assert entry["alert"]["rung_name"] == "warn"
        assert result["counts"]["alert"] == 1
        assert result["counts"]["todo"] == 1

    def test_TC_INBOX_012_无待办关系不出现(self, ds):
        # 创建者可见但无待办关系 → 不进收件箱（收件箱=待办聚合，不是任务列表）
        _task(ds, task_id="T-BARE", assignee="u2", created_by="owner",
              status="in_progress")

        assert inbox_query(ds, actor="owner")["total"] == 0
        # 无关状态 / 终态任务天然不出现
        _task(ds, task_id="T-DONE", assignee="u1", status="done")
        _task(ds, task_id="T-PEND", assignee="u1", status="pending")
        assert inbox_query(ds, actor="u1")["total"] == 0

    def test_TC_INBOX_013_waiting_approval只在待审口径(self, ds):
        _task(ds, task_id="T-W", assignee="u1", status="waiting_approval",
              type_="approval")
        _task(ds, task_id="T-W2", assignee="u1", status="waiting_approval",
              type_="story")

        result = inbox_query(ds, actor="u1")
        entries = {e["task_id"]: e for e in result["entries"]}

        assert entries["T-W"]["buckets"] == ["approval"]   # 待审口径含等待审批
        assert "T-W2" not in entries                       # 普通任务不进 todo


# ─────────────────────────────────────────────────────────────────────────────
# 排序 / 过滤 / 降级
# ─────────────────────────────────────────────────────────────────────────────

class TestQuery:
    """TC-INBOX-020~023 排序、过滤、limit、降级"""

    def test_TC_INBOX_020_排序与分页(self, ds):
        _task(ds, task_id="T-OLD", assignee="u1", status="in_progress",
              updated_at=T0)
        _task(ds, task_id="T-NEW", assignee="u1", status="in_progress",
              updated_at=_at(60))
        _task(ds, task_id="T-MID", assignee="u1", status="in_progress",
              updated_at=_at(30))

        result = inbox_query(ds, actor="u1")

        assert _ids(result) == ["T-NEW", "T-MID", "T-OLD"]  # updated desc

    def test_TC_INBOX_021_bucket过滤只看收窄counts全量(self, ds):
        _task(ds, task_id="T-TODO", assignee="u1", status="in_progress")
        _task(ds, task_id="T-CLAIM", policy="claim", candidates=["u1"])

        filtered = inbox_query(ds, actor="u1", bucket="claimable", limit=1)

        assert _ids(filtered) == ["T-CLAIM"]
        assert filtered["counts"]["todo"] == 1     # counts 全量口径
        assert filtered["counts"]["total"] == 2

    def test_TC_INBOX_022_limit截断(self, ds):
        _task(ds, task_id="T-1", assignee="u1", status="in_progress",
              updated_at=_at(30))
        _task(ds, task_id="T-2", assignee="u1", status="in_progress",
              updated_at=_at(20))

        limited = inbox_query(ds, actor="u1", limit=1)

        assert _ids(limited) == ["T-1"]
        assert limited["counts"]["total"] == 2

    def test_TC_INBOX_023_无SLA表降级不崩(self, ds_no_sla):
        _task(ds_no_sla, task_id="T-1", assignee="u1", status="in_progress")

        result = inbox_query(ds_no_sla, actor="u1")

        assert _ids(result) == ["T-1"]             # 告警侧缺失按无告警降级
        assert result["entries"][0]["alert"] is None
        assert result["counts"]["alert"] == 0

    def test_TC_INBOX_024_未知桶报错(self, ds):
        with pytest.raises(ValueError):
            inbox_query(ds, actor="u1", bucket="weird")

    def test_TC_INBOX_025_counts接口与query一致(self, ds):
        _task(ds, task_id="T-1", assignee="u1", status="in_progress")
        _task(ds, task_id="T-2", policy="claim", candidates=["u1"])

        assert inbox_counts(ds, actor="u1") == inbox_query(ds, actor="u1")["counts"]
        assert BUCKETS == ("alert", "approval", "todo", "agent_handoff", "claimable")