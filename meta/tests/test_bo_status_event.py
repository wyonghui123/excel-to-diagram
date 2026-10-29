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
    enqueue_bo_status_changed, normalize_state_value,
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

    def test_TC_BSE_011_载荷含state_field(self):
        """[Spec 2026-10-29] 载荷必须说明比较的是哪个状态维度。"""
        payload = build_status_payload(
            {"is_active": "true"}, "false", "true",
            payload_fields=("is_active",), event_key="k", state_field="is_active")

        assert payload["state_field"] == "is_active"
        assert (payload["from_status"], payload["to_status"]) == ("false", "true")

    def test_TC_BSE_012_载荷state_field默认status(self):
        """缺省保持向后兼容（旧契约未声明 state_field）。"""
        payload = build_status_payload(
            {"status": "approved"}, "submitted", "approved",
            payload_fields=("status",), event_key="k")

        assert payload["state_field"] == "status"


class TestNormalizeStateValue:
    """TC-BSE-007~008 状态值归一（Spec 2026-10-29）"""

    def test_TC_BSE_007_布尔字段归一两态(self):
        assert normalize_state_value(True, boolean_field=True) == "true"
        assert normalize_state_value(False, boolean_field=True) == "false"
        assert normalize_state_value(1, boolean_field=True) == "true"
        assert normalize_state_value(0, boolean_field=True) == "false"
        assert normalize_state_value("1", boolean_field=True) == "true"
        assert normalize_state_value("true", boolean_field=True) == "true"
        assert normalize_state_value("0", boolean_field=True) == "false"
        assert normalize_state_value("", boolean_field=True) == "false"
        assert normalize_state_value(None, boolean_field=True) is None

    def test_TC_BSE_008_非布尔字段保留码值(self):
        assert normalize_state_value("submitted") == "submitted"
        assert normalize_state_value(3) == "3"
        assert normalize_state_value(True) == "true"
        assert normalize_state_value(None) is None


class TestCustomStateField:
    """TC-BSE-009~010 自定义状态维度（is_active 等）"""

    def test_TC_BSE_009_自定义布尔字段变化(self):
        assert detect_status_change(
            {"is_active": 0}, {"is_active": 1}, "is_active", boolean_field=True,
        ) == ("false", "true")

    def test_TC_BSE_010_多状态维度互不干扰(self):
        old = {"status": "active", "is_active": 1}
        new = {"status": "active", "is_active": 0}

        assert detect_status_change(old, new, "is_active", boolean_field=True) == ("true", "false")
        assert detect_status_change(old, new, "status") is None


# ─────────────────────────────────────────────────────────────────────────────
# [Spec 2026-10-29] 启动期契约解析：契约声明 > 元模型唯一推导 > 回落 status
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def meta_object_factory():
    """临时登记元模型对象，测试结束逐个注销（不动真实 schema）。"""
    from meta.core.models import (
        FieldType, MetaField, MetaObject, MetaStateTransition, registry,
    )

    created = []

    def _make(object_id, *, field_ids=("status",), state_fields=()):
        obj = MetaObject(
            id=object_id, name=object_id, table_name=object_id,
            fields=[
                MetaField(id=f, name=f, field_type=FieldType.STRING, db_column=f)
                for f in field_ids
            ],
            rules=[
                MetaStateTransition(id=f"st-{i}", name="st", state_field=sf)
                for i, sf in enumerate(state_fields)
            ],
        )
        registry.register(obj)
        created.append(object_id)
        return obj

    yield _make
    for object_id in created:
        registry.unregister(object_id)


def _publish_decl(entity, *, payload=(), state_field=""):
    from types import SimpleNamespace
    return SimpleNamespace(
        name=BO_STATUS_CHANGED, entity=entity, trigger="after_update",
        condition="", payload=list(payload), state_field=state_field,
    )


class TestResolveStateField:
    """TC-BSE-013~018 契约启动期解析 state_field"""

    def test_TC_BSE_013_契约声明优先(self, meta_object_factory):
        from meta.core.app_registry import _resolve_bo_status_state_field

        meta_object_factory("t_bse_declared", field_ids=("status", "is_active"))
        resolved = _resolve_bo_status_state_field(
            APP, _publish_decl("t_bse_declared", payload=("is_active",),
                               state_field="is_active"))
        assert resolved == "is_active"

    def test_TC_BSE_014_声明字段不存在报错(self, meta_object_factory):
        from meta.core.app_registry import (
            AppRegistrationError, _resolve_bo_status_state_field,
        )

        meta_object_factory("t_bse_bad_declared", field_ids=("status",))
        with pytest.raises(AppRegistrationError):
            _resolve_bo_status_state_field(
                APP, _publish_decl("t_bse_bad_declared", state_field="is_active"))

    def test_TC_BSE_015_元模型唯一推导(self, meta_object_factory):
        from meta.core.app_registry import _resolve_bo_status_state_field

        meta_object_factory("t_bse_derived", field_ids=("status", "is_active"),
                            state_fields=("is_active",))
        resolved = _resolve_bo_status_state_field(
            APP, _publish_decl("t_bse_derived", payload=("is_active",)))
        assert resolved == "is_active"

    def test_TC_BSE_016_多状态维度歧义报错(self, meta_object_factory):
        from meta.core.app_registry import (
            AppRegistrationError, _resolve_bo_status_state_field,
        )

        meta_object_factory("t_bse_ambiguous",
                            field_ids=("status", "is_active", "is_current"),
                            state_fields=("is_active", "is_current"))
        with pytest.raises(AppRegistrationError):
            _resolve_bo_status_state_field(
                APP, _publish_decl("t_bse_ambiguous"))

    def test_TC_BSE_017_无规则但有status字段回落(self, meta_object_factory):
        from meta.core.app_registry import _resolve_bo_status_state_field

        meta_object_factory("t_bse_fallback", field_ids=("status",))
        resolved = _resolve_bo_status_state_field(
            APP, _publish_decl("t_bse_fallback", payload=("status",)))
        assert resolved == "status"

    def test_TC_BSE_018_无状态字段且未声明报错(self, meta_object_factory):
        from meta.core.app_registry import (
            AppRegistrationError, _resolve_bo_status_state_field,
        )

        meta_object_factory("t_bse_no_field", field_ids=("name",))
        with pytest.raises(AppRegistrationError):
            _resolve_bo_status_state_field(
                APP, _publish_decl("t_bse_no_field", payload=("name",)))

    def test_TC_BSE_019_非保留事件不解析(self):
        from types import SimpleNamespace
        from meta.core.app_registry import _resolve_bo_status_state_field

        decl = SimpleNamespace(name="outbound_completed", entity="whatever",
                               trigger="after_update", condition="", payload=[])
        assert _resolve_bo_status_state_field(APP, decl) == ""