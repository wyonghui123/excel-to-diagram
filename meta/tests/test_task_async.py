import pytest

pytestmark = pytest.mark.unit

"""
后端测试套件 - 异步补全协议（A7）
测试 meta.core.task_async 模块（complete_async + 三层归位键）

覆盖目标（对齐 §12.1 A7 / §9.2 / Q2 归位键决策）：
  1. 三层归位键：批次信封 + 任务键（A6 口径）+ 可选行键
  2. 两表结构：等待单 + 回执（append-only），唯一索引去重
  3. 开单：同 attempt 唯一、期望行清单、ttl
  4. 整体补全：首条回执即 completed、重放 duplicate
  5. 部分完成（验收硬项）：逐行核销、未回行保持 waiting/partial、全到才 completed
  6. 护栏：token 不存在 / 信封不符 / 路径外行键 / 逐行单据缺行键
"""

from meta.core.task_async import (
    RECEIPT_TABLE,
    WAIT_STATUSES,
    WAIT_TABLE,
    AsyncWaitError,
    async_tables_exist,
    build_async_meta_objects,
    build_receipt_key,
    complete_async,
    ensure_async_tables,
    get_async_wait,
    get_receipt,
    open_async_wait,
)
from meta.core.task_idempotency import build_idem_key


@pytest.fixture()
def ds(tmp_path):
    """独立临时库（不碰 architecture.db），预置 legacy 表验证不破坏。"""
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "a7.db"))
    with source.transaction():
        source.execute(
            "CREATE TABLE IF NOT EXISTS a7_legacy (id INTEGER PRIMARY KEY, name TEXT)"
        )
        ensure_async_tables(source)
    yield source


def _columns(ds, table):
    return [r[1] for r in ds.execute(f"PRAGMA table_info({table})").fetchall()]


def _indexes(ds, table):
    return [r[1] for r in ds.execute(f"PRAGMA index_list({table})").fetchall()]


def _open(ds, **kw):
    params = dict(task_id="T-1", workflow_run_id="R-1", attempt=1,
                  envelope_key="ENV-1")
    params.update(kw)
    return open_async_wait(ds, **params)


# ─────────────────────────────────────────────────────────────────────────────
# 三层归位键
# ─────────────────────────────────────────────────────────────────────────────

class TestReceiptKey:
    """三层归位键 {envelope}:{run}:{task}:{attempt}[:{line}]"""

    def test_key_with_line(self):
        """TC-TAS-001: 三层齐全（信封 + 任务键 + 行键）"""
        idem = build_idem_key("R-1", "T-1", 1)
        assert build_receipt_key("ENV-1", idem, "10") == f"ENV-1:{idem}:10"

    def test_key_without_line(self):
        """TC-TAS-002: 整体补全无行键"""
        idem = build_idem_key("R-1", "T-1", 1)
        assert build_receipt_key("ENV-1", idem) == f"ENV-1:{idem}"

    def test_key_without_envelope(self):
        """TC-TAS-003: 无信封（单件回执）仅中+行两层"""
        idem = build_idem_key("", "T-1", 2)
        assert build_receipt_key("", idem, "L1") == f":{idem}:L1"

    def test_empty_idem_rejected(self):
        """TC-TAS-004: 中层任务键不得为空（必须由 A6 算法产出）"""
        with pytest.raises(AsyncWaitError):
            build_receipt_key("ENV-1", "")

    def test_separator_rejected(self):
        """TC-TAS-005: 组件含 ':' 破坏键结构 → 拒绝"""
        idem = build_idem_key("R-1", "T-1", 1)
        with pytest.raises(AsyncWaitError):
            build_receipt_key("ENV:1", idem)
        with pytest.raises(AsyncWaitError):
            build_receipt_key("ENV-1", idem, "L:1")

    def test_middle_layer_uses_a6_algorithm(self, ds):
        """TC-TAS-006: 中层键唯一口径——开单产物等于 A6 build_idem_key"""
        out = open_async_wait(ds, task_id="T-9", attempt=3)
        assert out["idem_key"] == build_idem_key(None, "T-9", 3) == "adhoc:T-9:3"


# ─────────────────────────────────────────────────────────────────────────────
# 两表
# ─────────────────────────────────────────────────────────────────────────────

class TestTables:
    """等待单 + 回执两表"""

    def test_two_objects(self):
        """TC-TAS-010: 恰两张表 task_async_waits / task_async_receipts"""
        objs = build_async_meta_objects()
        assert [o.table_name for o in objs] == [WAIT_TABLE, RECEIPT_TABLE]

    def test_wait_columns(self, ds):
        """TC-TAS-011: 等待单含三段键列 + 核销列"""
        cols = _columns(ds, WAIT_TABLE)
        for expected in ("async_token", "idem_key", "envelope_key", "task_id",
                         "workflow_run_id", "attempt", "wait_status",
                         "expected_lines", "received_lines", "outputs",
                         "created_at", "expires_at", "completed_at"):
            assert expected in cols, expected

    def test_receipt_columns(self, ds):
        """TC-TAS-012: 回执含 receipt_key / biz_line_no（append-only）"""
        cols = _columns(ds, RECEIPT_TABLE)
        for expected in ("receipt_key", "async_token", "idem_key", "envelope_key",
                         "task_id", "biz_line_no", "outputs", "occurred_at",
                         "created_at"):
            assert expected in cols, expected

    def test_unique_indexes(self, ds):
        """TC-TAS-013: token / 任务键 / 归位键三处唯一（去重靠索引）"""
        assert "uq_task_async_token" in _indexes(ds, WAIT_TABLE)
        assert "uq_task_async_idem" in _indexes(ds, WAIT_TABLE)
        assert "uq_task_async_receipt" in _indexes(ds, RECEIPT_TABLE)

    def test_ensure_idempotent_and_legacy_kept(self, ds):
        """TC-TAS-014: 重复建表无害；legacy 表不被破坏"""
        ensure_async_tables(ds)
        assert async_tables_exist(ds) == {WAIT_TABLE: True, RECEIPT_TABLE: True}
        rows = ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='a7_legacy'"
        ).fetchall()
        assert rows

    def test_wait_status_value_set(self):
        """TC-TAS-015: 等待单状态值域 = waiting/partial/completed（非任务状态）"""
        assert WAIT_STATUSES == ("waiting", "partial", "completed")


# ─────────────────────────────────────────────────────────────────────────────
# 开单
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenWait:
    """开等待单"""

    def test_open_returns_token(self, ds):
        """TC-TAS-020: 返回 token，状态 waiting"""
        out = _open(ds)
        assert out["async_token"]
        assert out["wait_status"] == "waiting"
        assert out["idem_key"] == build_idem_key("R-1", "T-1", 1)
        assert out["envelope_key"] == "ENV-1"
        assert get_async_wait(ds, out["async_token"])["wait_status"] == "waiting"

    def test_open_with_expected_lines(self, ds):
        """TC-TAS-021: 期望行清单入单（部分完成模式）"""
        out = _open(ds, expected_line_refs=["10", "20", "30"])
        assert out["expected_lines"] == ["10", "20", "30"]
        assert get_async_wait(ds, out["async_token"])["received_lines"] == []

    def test_duplicate_open_same_attempt_rejected(self, ds):
        """TC-TAS-022: 同一任务尝试只允许一张等待单"""
        _open(ds)
        with pytest.raises(AsyncWaitError):
            _open(ds)

    def test_different_attempt_allowed(self, ds):
        """TC-TAS-023: 不同 attempt = 不同任务键 → 可各自开单（重试语义）"""
        a = _open(ds, attempt=1)
        b = _open(ds, attempt=2)
        assert a["async_token"] != b["async_token"]

    def test_empty_task_id_rejected(self, ds):
        """TC-TAS-024: task_id 必填"""
        with pytest.raises(AsyncWaitError):
            open_async_wait(ds, task_id="")

    def test_ttl_sets_expires_at(self, ds):
        """TC-TAS-025: ttl 写入 expires_at（超期由引擎判 dead）"""
        out = _open(ds, ttl_seconds=60)
        assert get_async_wait(ds, out["async_token"])["expires_at"]


# ─────────────────────────────────────────────────────────────────────────────
# 整体补全
# ─────────────────────────────────────────────────────────────────────────────

class TestCompleteSingle:
    """无期望行清单 = 整体补全"""

    def test_first_receipt_completes(self, ds):
        """TC-TAS-030: 首条回执即 completed，提示引擎迁 done"""
        token = _open(ds)["async_token"]
        out = complete_async(ds, token, {"ok": True})
        assert out["status"] == "received"
        assert out["wait_status"] == "completed"
        assert out["task_completed"] is True
        assert out["next_status"] == "done"
        assert out["missing_lines"] == []

    def test_replay_is_duplicate(self, ds):
        """TC-TAS-031: 同归位键重放 → duplicate，不重复核销"""
        token = _open(ds)["async_token"]
        complete_async(ds, token, {"n": 1})
        again = complete_async(ds, token, {"n": 1})
        assert again["status"] == "duplicate"
        assert again["wait_status"] == "completed"
        count = ds.execute(f"SELECT COUNT(*) FROM {RECEIPT_TABLE}").fetchone()[0]
        assert count == 1

    def test_unknown_token_rejected(self, ds):
        """TC-TAS-032: token 不存在 → 拒绝"""
        with pytest.raises(AsyncWaitError):
            complete_async(ds, "no-such-token")

    def test_empty_token_rejected(self, ds):
        """TC-TAS-033: 空 token → 拒绝"""
        with pytest.raises(AsyncWaitError):
            complete_async(ds, "")

    def test_envelope_mismatch_rejected(self, ds):
        """TC-TAS-034: 回执信封与开单不符 → 拒绝（fail-closed）"""
        token = _open(ds, envelope_key="ENV-1")["async_token"]
        with pytest.raises(AsyncWaitError):
            complete_async(ds, token, envelope_key="ENV-OTHER")

    def test_receipt_after_completed_rejected(self, ds):
        """TC-TAS-035: 已完成再收新回执（新键）→ 拒绝"""
        token = _open(ds)["async_token"]
        complete_async(ds, token)
        with pytest.raises(AsyncWaitError):
            complete_async(ds, token, biz_line_no="L1")


# ─────────────────────────────────────────────────────────────────────────────
# 部分完成（验收硬项）
# ─────────────────────────────────────────────────────────────────────────────

class TestCompletePartial:
    """同 attempt 下多行分别核销；未回行保持 waiting"""

    def test_line_by_line_settlement(self, ds):
        """TC-TAS-040: 逐行核销，未回行 stay waiting/partial，全到才 completed"""
        token = _open(ds, expected_line_refs=["10", "20", "30"])["async_token"]

        first = complete_async(ds, token, {"line": 10}, biz_line_no="10")
        assert first["wait_status"] == "partial"
        assert first["received_lines"] == ["10"]
        assert first["missing_lines"] == ["20", "30"]
        assert first["task_completed"] is False
        assert first["next_status"] is None

        second = complete_async(ds, token, {"line": 20}, biz_line_no="20")
        assert second["wait_status"] == "partial"
        assert second["missing_lines"] == ["30"]

        third = complete_async(ds, token, {"line": 30}, biz_line_no="30")
        assert third["wait_status"] == "completed"
        assert third["missing_lines"] == []
        assert third["task_completed"] is True

        wait = get_async_wait(ds, token)
        assert wait["received_lines"] == ["10", "20", "30"]
        assert wait["completed_at"]

    def test_unreturned_line_has_no_receipt(self, ds):
        """TC-TAS-041: 未回行不产生回执（保持等待，机器可查）"""
        token = _open(ds, expected_line_refs=["10", "20"])["async_token"]
        complete_async(ds, token, biz_line_no="10")
        rows = ds.execute(
            f"SELECT biz_line_no FROM {RECEIPT_TABLE} WHERE async_token = ?",
            (token,),
        ).fetchall()
        assert [r[0] for r in rows] == ["10"]
        assert get_async_wait(ds, token)["wait_status"] == "partial"

    def test_partial_line_replay_duplicate(self, ds):
        """TC-TAS-042: 同一行重放 → duplicate，行集合不重复累积"""
        token = _open(ds, expected_line_refs=["10", "20"])["async_token"]
        complete_async(ds, token, biz_line_no="10")
        again = complete_async(ds, token, biz_line_no="10")
        assert again["status"] == "duplicate"
        assert again["received_lines"] == ["10"]
        assert again["missing_lines"] == ["20"]

    def test_missing_line_key_rejected(self, ds):
        """TC-TAS-043: 逐行单据缺 biz_line_no → 拒绝"""
        token = _open(ds, expected_line_refs=["10"])["async_token"]
        with pytest.raises(AsyncWaitError):
            complete_async(ds, token)

    def test_unknown_line_rejected(self, ds):
        """TC-TAS-044: 路径外行键 → 拒绝"""
        token = _open(ds, expected_line_refs=["10"])["async_token"]
        with pytest.raises(AsyncWaitError):
            complete_async(ds, token, biz_line_no="99")

    def test_receipt_readable_after_completion(self, ds):
        """TC-TAS-045: 回执可按归位键读回（对账）"""
        token = _open(ds, expected_line_refs=["10"])["async_token"]
        out = complete_async(ds, token, {"x": 1}, biz_line_no="10",
                             envelope_key="ENV-1")
        rec = get_receipt(ds, out["receipt_key"])
        assert rec["biz_line_no"] == "10"
        assert rec["envelope_key"] == "ENV-1"
        assert rec["outputs"] == {"x": 1}
        assert rec["idem_key"] == build_idem_key("R-1", "T-1", 1)