import pytest

pytestmark = pytest.mark.unit

# 平台内部表（event_outbox）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - bo.status_changed 反向事件原子能力（D3 §9.7 规范 4）
测试 meta.core.bo_status_event 的 detect / build / enqueue

覆盖目标：
  1. 检测：状态变化 → (from, to)
  2. 检测：状态未变 → None
  3. 检测：缺字段 / None → None（fail-closed，不误发）
  4. 载荷：仅含声明字段 + from/to + event_key
  5. 入队：写入 outbox 一行，事件名 / entity_id / 载荷正确
  6. 入队：同事务重复入队去重（返回 None）
"""

import json

from meta.core.bo_status_event import (
    BO_STATUS_CHANGED, build_status_payload, detect_status_change,
    enqueue_bo_status_changed,
)

ENTITY = "outbound_order"
APP = "warehouse"


def _contract(payload_fields=("order_no", "status")):
    from meta.core.event_outbox import PublisherContract
    return PublisherContract(
        app_id=APP, name=BO_STATUS_CHANGED, entity=ENTITY,
        trigger="after_update", condition="", payload=tuple(payload_fields),
    )


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.event_outbox import ensure_outbox_table

    source = get_data_source("sqlite", database=str(tmp_path / "bse.db"))
    with source.transaction():
        ensure_outbox_table(source)
    yield source


def _count(ds):
    return ds.execute("SELECT COUNT(*) FROM event_outbox").fetchall()[0][0]


class TestDetectStatusChange:
    """TC-BSE-001~003 状态变更检测"""

    def test_TC_BSE_001_状态变化返回from_to(self):
        assert detect_status_change(
            {"status": "submitted"}, {"status": "approved"}) == ("submitted", "approved")

    def test_TC_BSE_002_状态未变返回None(self):
        assert detect_status_change(
            {"status": "approved"}, {"status": "approved"}) is None

    def test_TC_BSE_003_缺字段返回None(self):
        assert detect_status_change({}, {"status": "approved"}) is None
        assert detect_status_change({"status": None}, {"status": "approved"}) is None
        assert detect_status_change({"status": "approved"}, {"status": None}) is None


class TestPayloadAndEnqueue:
    """TC-BSE-004~006 载荷构造与入队"""

    def test_TC_BSE_004_载荷含声明字段与from_to与幂等键(self):
        row = {"order_no": "SO-1", "status": "approved", "secret": "x"}

        payload = build_status_payload(
            row, "submitted", "approved",
            payload_fields=("order_no", "status"),
            event_key="outbound_order:7:submitted->approved",
        )

        assert payload["order_no"] == "SO-1"
        assert payload["status"] == "approved"
        assert payload["from_status"] == "submitted"
        assert payload["to_status"] == "approved"
        assert payload["event_key"] == "outbound_order:7:submitted->approved"
        assert "secret" not in payload          # 只带声明字段

    def test_TC_BSE_005_入队一行且事件名与载荷正确(self, ds):
        row = {"order_no": "SO-1", "status": "approved"}

        event_id = enqueue_bo_status_changed(
            ds, _contract(), entity_id=7, row=row,
            from_status="submitted", to_status="approved", transaction_id="txn-1",
        )

        assert event_id
        rows = ds.execute(
            "SELECT event_name, entity_id, payload FROM event_outbox").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == BO_STATUS_CHANGED
        assert rows[0][1] == 7
        payload = json.loads(rows[0][2])
        assert payload["from_status"] == "submitted"
        assert payload["to_status"] == "approved"
        assert payload["event_key"] == "outbound_order:7:submitted->approved"

    def test_TC_BSE_006_同事务重复入队去重(self, ds):
        row = {"order_no": "SO-1", "status": "approved"}
        first = enqueue_bo_status_changed(
            ds, _contract(), entity_id=7, row=row,
            from_status="submitted", to_status="approved", transaction_id="txn-1")
        second = enqueue_bo_status_changed(
            ds, _contract(), entity_id=7, row=row,
            from_status="submitted", to_status="approved", transaction_id="txn-1")

        assert first and second is None          # 同 (event, entity_id, txn) 去重
        assert _count(ds) == 1