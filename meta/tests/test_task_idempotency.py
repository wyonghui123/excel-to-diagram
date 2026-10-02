import pytest

pytestmark = pytest.mark.unit

"""
后端测试套件 - 任务幂等键（A6）
测试 meta.core.task_idempotency 模块（唯一算法 + 重放无副作用）

覆盖目标（对齐 §12.1 A6 / §9.2 / §9.5）：
  1. 键算法唯一口径：{run}:{task}:{attempt}、adhoc 回退、cron {action}:{window}
  2. 非法键拒绝：空组件、含分隔符、attempt 越界
  3. 去重账表：幂等建表 + legacy 不破坏 + 唯一索引
  4. claim 首次 True / 重放 False；complete + get 往返
  5. run_idempotent 只执行一次、重放返回首次结果、抛异常可安全重试
"""

from meta.core.task_idempotency import (
    ADHOC_RUN,
    IdempotencyKeyError,
    SCOPES,
    STATUSES,
    TABLE,
    build_cron_idem_key,
    build_idem_key,
    claim_idempotent,
    complete_idempotent,
    ensure_idempotency_table,
    get_idempotent,
    idempotency_table_exists,
    run_idempotent,
)


@pytest.fixture()
def ds(tmp_path):
    """独立临时库（不碰 architecture.db），预置一张 legacy 表用于验证不破坏。"""
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "a6.db"))
    with source.transaction():
        source.execute(
            "CREATE TABLE IF NOT EXISTS a6_legacy (id INTEGER PRIMARY KEY, name TEXT)"
        )
        ensure_idempotency_table(source)
    yield source


def _columns(ds, table):
    return [r[1] for r in ds.execute(f"PRAGMA table_info({table})").fetchall()]


def _indexes(ds, table):
    return [r[1] for r in ds.execute(f"PRAGMA index_list({table})").fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# 键算法
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildIdemKey:
    """任务尝试幂等键 {run}:{task}:{attempt}"""

    def test_standard_key(self):
        """TC-TID-001: 标准格式 run:task:attempt"""
        assert build_idem_key("run-9", "task-7", 2) == "run-9:task-7:2"

    def test_adhoc_fallback_when_run_absent(self):
        """TC-TID-002: run 为空 → adhoc 占位（ad-hoc 跨系统回调口径）"""
        assert build_idem_key(None, "t1", 1) == f"{ADHOC_RUN}:t1:1"
        assert build_idem_key("", "t1", 1) == f"{ADHOC_RUN}:t1:1"
        assert build_idem_key("", "t1", 1) == "adhoc:t1:1"

    def test_attempt_must_be_positive_int(self):
        """TC-TID-003: attempt 从 1 起，非正/非整数拒绝"""
        for bad in (0, -1, "x", None):
            with pytest.raises(IdempotencyKeyError):
                build_idem_key("r", "t", bad)

    def test_task_id_required(self):
        """TC-TID-004: task_id 不能为空"""
        with pytest.raises(IdempotencyKeyError):
            build_idem_key("r", "", 1)

    def test_separator_in_components_rejected(self):
        """TC-TID-005: 组件含 ':' 会破坏键结构 → 拒绝"""
        with pytest.raises(IdempotencyKeyError):
            build_idem_key("r:1", "t", 1)
        with pytest.raises(IdempotencyKeyError):
            build_idem_key("r", "t:1", 1)

    def test_same_input_same_key(self):
        """TC-TID-006: 同输入必得同键（跨应用同算法才可对账）"""
        assert build_idem_key("r", "t", 3) == build_idem_key("r", "t", 3)


class TestBuildCronIdemKey:
    """cron 窗口幂等键 {action_id}:{time_window}"""

    def test_standard_key(self):
        """TC-TID-010: 标准格式 action:window（同周期重复触发去重）"""
        assert build_cron_idem_key("act-1", "2026-10-02T17:00") == \
            "act-1:2026-10-02T17:00"

    def test_empty_components_rejected(self):
        """TC-TID-011: action_id / time_window 均不得为空"""
        with pytest.raises(IdempotencyKeyError):
            build_cron_idem_key("", "2026-10-02T17:00")
        with pytest.raises(IdempotencyKeyError):
            build_cron_idem_key("act-1", "")

    def test_separator_in_action_rejected(self):
        """TC-TID-012: action_id 含 ':' 拒绝"""
        with pytest.raises(IdempotencyKeyError):
            build_cron_idem_key("act:1", "w")


# ─────────────────────────────────────────────────────────────────────────────
# 去重账表
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotencyTable:
    """去重账表结构与建表"""

    def test_table_created_with_columns(self, ds):
        """TC-TID-020: 建表含 idem_key/status/result 等列"""
        cols = _columns(ds, TABLE)
        for expected in ("id", "idem_key", "scope", "task_id", "workflow_run_id",
                         "attempt", "status", "result", "created_at", "completed_at"):
            assert expected in cols, expected

    def test_unique_index_on_idem_key(self, ds):
        """TC-TID-021: idem_key 上有唯一索引（去重靠它，等价 INSERT OR IGNORE）"""
        names = _indexes(ds, TABLE)
        assert "uq_task_idem_key" in names

    def test_ensure_is_idempotent(self, ds):
        """TC-TID-022: 重复建表不报错、不破坏已有数据"""
        with ds.transaction():
            claim_idempotent(ds, "r:t:1")
        ensure_idempotency_table(ds)
        assert get_idempotent(ds, "r:t:1") is not None

    def test_legacy_table_preserved(self, ds):
        """TC-TID-023: 建表不破坏同库既有表"""
        rows = ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='a6_legacy'"
        ).fetchall()
        assert rows
        assert idempotency_table_exists(ds) is True

    def test_value_sets(self):
        """TC-TID-024: scope/status 值域锁定"""
        assert set(SCOPES) == {"task_attempt", "cron_window"}
        assert set(STATUSES) == {"claimed", "completed", "failed"}


# ─────────────────────────────────────────────────────────────────────────────
# claim / complete / get
# ─────────────────────────────────────────────────────────────────────────────

class TestClaimAndGet:
    """领取与回写"""

    def test_first_true_second_false(self, ds):
        """TC-TID-030: 首次领取 True，重复（重放）False"""
        with ds.transaction():
            assert claim_idempotent(ds, "r:t:1", scope="task_attempt",
                                    task_id="t", workflow_run_id="r", attempt=1) is True
            assert claim_idempotent(ds, "r:t:1", scope="task_attempt",
                                    task_id="t", workflow_run_id="r", attempt=1) is False

    def test_empty_key_rejected(self):
        """TC-TID-031: 空键拒绝"""
        with pytest.raises(IdempotencyKeyError):
            claim_idempotent(ds, "")

    def test_bad_scope_rejected(self):
        """TC-TID-032: 未知 scope 拒绝"""
        with pytest.raises(IdempotencyKeyError):
            claim_idempotent(ds, "r:t:1", scope="nope")

    def test_complete_then_get_roundtrip(self, ds):
        """TC-TID-033: 回写结果后可原样读回（含 JSON 解析）"""
        with ds.transaction():
            claim_idempotent(ds, "r:t:2", task_id="t", attempt=2)
            complete_idempotent(ds, "r:t:2", {"doc": "DOC-1", "n": 3})
        rec = get_idempotent(ds, "r:t:2")
        assert rec["status"] == "completed"
        assert rec["result"] == {"doc": "DOC-1", "n": 3}
        assert rec["task_id"] == "t"
        assert rec["attempt"] == 2
        assert rec["completed_at"]

    def test_get_missing_returns_none(self, ds):
        """TC-TID-034: 记录不存在返回 None"""
        assert get_idempotent(ds, "no-such-key") is None

    def test_complete_bad_status_rejected(self):
        """TC-TID-035: 非法 status 拒绝"""
        with pytest.raises(IdempotencyKeyError):
            complete_idempotent(ds, "r:t:1", status="weird")


# ─────────────────────────────────────────────────────────────────────────────
# 重放无副作用
# ─────────────────────────────────────────────────────────────────────────────

class TestRunIdempotent:
    """run_idempotent：只执行一次 + 重放取首次结果 + 异常可重试"""

    def test_executes_once_and_replay_returns_first_result(self, ds):
        """TC-TID-040: 首次执行、重放不执行 fn 且返回首次结果"""
        calls = []

        def fn(inner_ds):
            calls.append(1)
            return {"doc": "DOC-9"}

        first = run_idempotent(ds, "r:t:1", fn, task_id="t", workflow_run_id="r",
                               attempt=1)
        second = run_idempotent(ds, "r:t:1", fn, task_id="t", workflow_run_id="r",
                                attempt=1)

        assert first["status"] == "executed"
        assert first["result"] == {"doc": "DOC-9"}
        assert second["status"] == "duplicate"
        assert second["result"] == {"doc": "DOC-9"}   # 重放返回首次结果
        assert len(calls) == 1                        # fn 未被二次调用

    def test_replay_of_unfinished_claim_returns_none_result(self, ds):
        """TC-TID-041: 已领取但未回写 → 重放不执行、结果为 None"""
        calls = []

        with ds.transaction():
            claim_idempotent(ds, "r:t:5", task_id="t", attempt=5)
        out = run_idempotent(ds, "r:t:5", lambda d: calls.append(1),
                             task_id="t", attempt=5)
        assert out["status"] == "duplicate"
        assert out["result"] is None
        assert calls == []

    def test_exception_rolls_back_key_and_can_retry(self, ds):
        """TC-TID-042: fn 抛异常 → 键随事务回滚 → 可安全重试"""
        def boom(inner_ds):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            run_idempotent(ds, "r:t:6", boom, task_id="t", attempt=6)
        assert get_idempotent(ds, "r:t:6") is None   # 去重账未被污染

        out = run_idempotent(ds, "r:t:6", lambda d: "ok", task_id="t", attempt=6)
        assert out["status"] == "executed"
        assert out["result"] == "ok"

    def test_cron_window_scope(self, ds):
        """TC-TID-043: cron 窗口键同口径去重（§9.5）"""
        key = build_cron_idem_key("act-1", "2026-10-02T17:00")
        calls = []

        def fn(inner_ds):
            calls.append(1)
            return "ticked"

        run_idempotent(ds, key, fn, scope="cron_window")
        out = run_idempotent(ds, key, fn, scope="cron_window")
        assert out["status"] == "duplicate"
        assert out["result"] == "ticked"
        assert calls == [1]
        assert get_idempotent(ds, key)["scope"] == "cron_window"

    def test_different_attempt_keys_are_independent(self, ds):
        """TC-TID-044: 不同 attempt 是不同键，各自可执行一次（重试语义）"""
        calls = []
        for attempt in (1, 2):
            out = run_idempotent(ds, build_idem_key("r", "t", attempt),
                                 lambda d, a=attempt: calls.append(a) or a,
                                 task_id="t", workflow_run_id="r", attempt=attempt)
            assert out["status"] == "executed"
        assert calls == [1, 2]


def test_module_exposes_no_delete_api():
    """TC-TID-050: 去重账不被本模块删除（无 delete/drop API）"""
    import meta.core.task_idempotency as mod

    for forbidden in ("delete_idempotent", "drop_table", "clear_idempotency"):
        assert not hasattr(mod, forbidden), forbidden