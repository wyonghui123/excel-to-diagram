# -*- coding: utf-8 -*-
"""[S7.3 2026-11-06] 过账时点强制快照测试。

纯函数 + 临时 SQLite：
  · _document_posting_entry 只在「跨入 posting_state」时为真；
  · 未声明 document_profile 的对象恒为假（零影响）；
  · record(forced=True) 在对象未启用 revision_policy 时也写整单快照；
  · forced=False 保持既有零操作语义。
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from meta.core.action_executor import _document_posting_entry  # noqa: E402
from meta.core.models import (  # noqa: E402
    FieldType,
    MetaDocumentProfile,
    MetaField,
    MetaObject,
)
from meta.core.sql_adapters import SQLiteAdapter  # noqa: E402
from meta.core.table_name_validator import register_table_name  # noqa: E402
from meta.services.revision_service import (  # noqa: E402
    CHANGES_TABLE,
    REVISIONS_TABLE,
    record,
)

DDL = {
    "posting_order": """
        CREATE TABLE IF NOT EXISTS posting_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT,
            status TEXT,
            revision_no INTEGER DEFAULT 1
        )
    """,
    REVISIONS_TABLE: """
        CREATE TABLE IF NOT EXISTS document_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            revision_no INTEGER NOT NULL,
            snapshot TEXT,
            change_request_id TEXT,
            reason_code TEXT,
            change_set_id TEXT,
            created_by TEXT,
            created_at TEXT
        )
    """,
    CHANGES_TABLE: """
        CREATE TABLE IF NOT EXISTS document_revision_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_id INTEGER NOT NULL,
            line_key TEXT,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT
        )
    """,
}


def _obj(with_profile=True):
    obj = MetaObject(
        id="posting_order",
        name="过账单据",
        table_name="posting_order",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER,
                      db_column="id", required=True),
            MetaField(id="order_no", name="单号", field_type=FieldType.STRING,
                      db_column="order_no"),
            MetaField(id="status", name="状态", field_type=FieldType.STRING,
                      db_column="status"),
            MetaField(id="revision_no", name="版本号", field_type=FieldType.INTEGER,
                      db_column="revision_no"),
        ],
    )
    obj.document_profile = (
        MetaDocumentProfile(
            number_field="order_no",
            state_field="status",
            posting_state="confirmed",
            snapshot_fields=["order_no"],
        ) if with_profile else None
    )
    return obj


def test_posting_entry_detected():
    obj = _obj()
    assert _document_posting_entry(obj, {"status": "draft"}, {"status": "confirmed"}) is True


def test_non_entry_not_detected():
    obj = _obj()
    # 已在过账态 → 不是「跨入」
    assert _document_posting_entry(obj, {"status": "confirmed"}, {"status": "confirmed"}) is False
    # 离开过账态 → 不是「跨入」
    assert _document_posting_entry(obj, {"status": "confirmed"}, {"status": "closed"}) is False
    # 普通状态变化 → 不是「跨入」
    assert _document_posting_entry(obj, {"status": "draft"}, {"status": "submitted"}) is False


def test_no_profile_returns_false():
    obj = _obj(with_profile=False)
    assert _document_posting_entry(obj, {"status": "draft"}, {"status": "confirmed"}) is False


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / "posting.db"))
    for name, ddl in DDL.items():
        data_source.execute(ddl)
        register_table_name(name)
    yield data_source
    data_source.disconnect()


def test_forced_record_writes_revision_without_policy(ds):
    obj = _obj()
    row_id = ds.insert("posting_order", {
        "order_no": "PO-1", "status": "confirmed", "revision_no": 1,
    })

    with ds.transaction():
        result = record(
            ds, obj, row_id,
            before={"status": "draft"},
            after={"status": "confirmed", "order_no": "PO-1"},
            changed_fields=[],
            revision_no=2,
            reason_code="POST",
            forced=True,
        )

    assert result == 2
    rows = ds.find(REVISIONS_TABLE, {
        "object_type": "posting_order", "object_id": str(row_id),
    })
    assert len(rows) == 1
    assert rows[0]["revision_no"] == 2
    assert rows[0]["reason_code"] == "POST"
    snapshot = json.loads(rows[0]["snapshot"])
    assert snapshot["header"]["status"] == "confirmed"
    assert snapshot["header"]["order_no"] == "PO-1"


def test_non_forced_record_is_noop_without_policy(ds):
    obj = _obj()
    row_id = ds.insert("posting_order", {
        "order_no": "PO-2", "status": "confirmed", "revision_no": 1,
    })

    with ds.transaction():
        result = record(
            ds, obj, row_id,
            before={"status": "draft"},
            after={"status": "confirmed"},
            changed_fields=[],
            revision_no=2,
            reason_code="POST",
            forced=False,
        )

    assert result == 2
    assert ds.find(REVISIONS_TABLE, {"object_type": "posting_order"}) == []
