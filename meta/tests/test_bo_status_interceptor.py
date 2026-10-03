import pytest

pytestmark = pytest.mark.unit

# 平台内部表（event_outbox / 业务表）暂无 Factory；走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - BoStatusInterceptor（D3 §9.7 规范 4）
测试 meta.core.interceptors.bo_status_interceptor.BoStatusInterceptor

覆盖目标：
  1. crud_update + 状态变化 + 有保留契约 → 入队一行，载荷含 from/to/event_key
  2. 状态未变 → 不入队
  3. 无保留契约 → should_execute False
  4. 非 crud_update（crud_create）→ should_execute False
  5. OutboxInterceptor 对保留事件名让位（不再重复入队）
"""

import json
from types import SimpleNamespace

from meta.core.action_context import ActionContext, ActionResult
from meta.core.bo_status_event import BO_STATUS_CHANGED
from meta.core.interceptors.bo_status_interceptor import BoStatusInterceptor

APP = "warehouse"
ENTITY = "outbound_order"


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.event_outbox import ensure_outbox_table
    # 测试替身表：_load_row 复用了 OutboxInterceptor 的 validate_table_name 白名单，
    # 非 YAML 注册表需显式登记（仓库既有惯例，见 test_allocation_allocate.py）。
    from meta.core.table_name_validator import register_table_name
    register_table_name(ENTITY)

    source = get_data_source("sqlite", database=str(tmp_path / "bsi.db"))
    with source.transaction():
        source.execute(
            "CREATE TABLE outbound_order "
            "(id INTEGER PRIMARY KEY, order_no TEXT, status TEXT)")
        source.execute(
            "INSERT INTO outbound_order (id, order_no, status) "
            "VALUES (1, 'SO-1', 'submitted')")
        ensure_outbox_table(source)
    yield source


@pytest.fixture()
def registry():
    from meta.core.event_outbox import get_event_contract_registry

    reg = get_event_contract_registry()
    reg.reset()
    yield reg
    reg.reset()


def _declare(registry, *, name=BO_STATUS_CHANGED, entity=ENTITY,
             trigger="after_update", payload=("order_no", "status")):
    registry.register_publish(APP, SimpleNamespace(
        name=name, entity=entity, trigger=trigger,
        condition="", payload=list(payload)))


def _ctx(ds, *, action="crud_update", old_status="submitted"):
    return ActionContext(
        meta_object=SimpleNamespace(id=ENTITY, table_name=ENTITY),
        action=action,
        params={"id": 1},
        data_source=ds,
        old_data=({"status": old_status} if old_status is not None else None),
        transaction_id="txn-1",
    )


def _write(ds, status):
    ds.execute("UPDATE outbound_order SET status = ? WHERE id = 1", (status,))


def _count(ds):
    return ds.execute("SELECT COUNT(*) FROM event_outbox").fetchall()[0][0]


class TestBoStatusInterceptor:
    """TC-BSI-001~005 状态变更发射"""

    def test_TC_BSI_001_状态变化发一行事件(self, ds, registry):
        _declare(registry)
        ctx = _ctx(ds, old_status="submitted")
        ctx.result = ActionResult(success=True)
        _write(ds, "approved")
        interceptor = BoStatusInterceptor()

        assert interceptor.should_execute(ctx) is True
        interceptor.after_action(ctx)

        rows = ds.execute(
            "SELECT event_name, entity_id, payload FROM event_outbox").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == BO_STATUS_CHANGED
        assert rows[0][1] == 1
        payload = json.loads(rows[0][2])
        assert (payload["from_status"], payload["to_status"]) == ("submitted", "approved")
        assert payload["event_key"] == "outbound_order:1:submitted->approved"

    def test_TC_BSI_002_状态未变不发事件(self, ds, registry):
        _declare(registry)
        ctx = _ctx(ds, old_status="submitted")
        ctx.result = ActionResult(success=True)
        _write(ds, "submitted")

        BoStatusInterceptor().after_action(ctx)

        assert _count(ds) == 0

    def test_TC_BSI_003_无契约不执行(self, ds, registry):
        ctx = _ctx(ds)

        assert BoStatusInterceptor().should_execute(ctx) is False

    def test_TC_BSI_004_仅update生效(self, ds, registry):
        _declare(registry)
        ctx = _ctx(ds, action="crud_create")

        assert BoStatusInterceptor().should_execute(ctx) is False

    def test_TC_BSI_005_outbox拦截器让位保留事件(self, ds, registry, monkeypatch):
        import meta.core.app_registry as app_registry
        from meta.core.interceptors.outbox_interceptor import OutboxInterceptor

        _declare(registry)
        # OutboxInterceptor 内部按 app_id 取契约；打桩让 app_id 非空，
        # 从而真正走到「保留名让位」分支（否则会因 app_id 为空提前返回）
        monkeypatch.setattr(app_registry, "get_app_id_for_bo", lambda bo_id: APP)

        ctx = _ctx(ds)
        ctx.result = ActionResult(success=True)
        _write(ds, "approved")

        OutboxInterceptor().after_action(ctx)

        assert _count(ds) == 0          # 让位：保留事件不由 OutboxInterceptor 发