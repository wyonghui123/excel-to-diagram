# -*- coding: utf-8 -*-
"""[多产品平台] PoC 4：跨应用事件端到端验证（roadmap §10 PoC 4 / §6.14）

场景: WMS（warehouse）出库单状态变为 `shipped` → 事件 `outbound_completed`
      → TMS（tms）自动建运单。

三条关键验证点（§6.14.4 的"不丢 / 不重 / 不无限重试"）:
1. **不丢** 业务写成功后立即崩溃 → 事件仍在（outbox 与业务写同事务落库）;
   重启后重新扫描 outbox 仍能投递（本文件用"停掉后台投递线程 + 新建
   EventDispatcher 实例"表达"kill 后重启"）
2. **不重** 人为再投递一条同载荷事件（同一幂等键）→ TMS 不产生第二张运单
   （`consumed_events` 的 (consumer_app, event_name, idempotency_key) 唯一键）
3. **不死循环** handler 反复抛异常 → attempts 达上限后进死信（status='dead'），
   且去重标记随事务回滚（不留"标记过但没建单"的毒数据）

另验证 §6.14.4 ①（outbox 与业务表同库 / 同事务回滚）与 ④（契约启动期校验）。

注意: 本文件会真实调用 `create_app()`, 必须单独运行:
  python d:\\filework\\test.py --file meta/tests/test_event_outbox_poc4.py

**全文件只调用一次 `create_app()`**（PoC 2 教训, roadmap §10.12）: `bo_framework`
与事件契约注册表都是进程级单例, 重复 `create_app()` 会让拦截器与契约累加。

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.14 / §10 PoC 4
"""
import json
import os
import sqlite3
import warnings
from types import SimpleNamespace

import pytest

from meta.core.app_loader import AppManifestError, load_apps
from meta.core.db_path import get_meta_db_path
from meta.core.event_outbox import (
    EventContractError, EventContractRegistry, EventDispatcher, evaluate_condition,
    get_event_contract_registry,
)

WAREHOUSE = "warehouse"
TMS = "tms"

EVENT_NAME = "outbound_completed"
BO_URL_OUTBOUND = "/api/v2/bo/outbound_order"
TMS_API_WAYBILLS = "/api/v1/apps/tms/waybills"

FAILING_HANDLER_SOURCE = '''
def handle(data_source, payload):
    raise RuntimeError("POC4_FAIL_MARKER: 模拟下游处理失败")
'''


# ─────────────────────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────────────────────
def _keep_env(keys):
    return {k: os.environ.get(k) for k in keys}


def _restore_env(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="module")
def event_env(tmp_path_factory):
    """启用 warehouse + tms 的应用实例（全文件唯一一次 create_app）。"""
    keys = ("SQLITE_DB_DIR", "APP_DB_ROUTING", "ENABLED_APPS")
    previous = _keep_env(keys)
    app_dir = tmp_path_factory.mktemp("eventdata")

    os.environ["SQLITE_DB_DIR"] = str(app_dir)
    os.environ["APP_DB_ROUTING"] = "1"
    os.environ["ENABLED_APPS"] = f"{WAREHOUSE},{TMS}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from meta.server import create_app
        app = create_app()
    app.config["TESTING"] = True

    # 冻结后台投递线程: 本文件要**自己控制投递时机**（表达"崩溃后未投递"与
    # "重复投递"），否则 1s 轮询会让"投递前"的断言不确定。
    from meta.core.event_outbox import stop_event_dispatcher
    stop_event_dispatcher()

    try:
        yield {"app": app, "app_dir": app_dir}
    finally:
        _restore_env(previous)


@pytest.fixture
def client(event_env):
    c = event_env["app"].test_client()
    c.get("/api/v1/auth/dev-login?username=admin")
    return c


# ─────────────────────────────────────────────────────────────────────────────
# A: 契约解析与启动期校验（纯函数, 不触发 create_app）
# ─────────────────────────────────────────────────────────────────────────────
class TestEventContracts:

    @pytest.fixture(autouse=True)
    def _clean_contract_registry(self):
        """契约注册表是进程级单例 —— 本类的用例不得把脏契约留给端到端用例。

        注意只能限定在本类内: 端到端用例依赖 create_app 注册的真实契约,
        若在文件级 autouse 清空, OutboxInterceptor 会因"无契约"而短路。
        """
        yield
        get_event_contract_registry().reset()

    def test_real_apps_declare_matching_contract(self):
        """warehouse 发布 / tms 订阅的声明能正确解析（§6.14.3）。"""
        manifests = {m.app_id: m for m in load_apps([WAREHOUSE, TMS])}

        pubs = manifests[WAREHOUSE].events_publish
        assert len(pubs) == 1, f"warehouse 应声明 1 条 publish, 实际 {pubs}"
        assert pubs[0].name == EVENT_NAME
        assert pubs[0].entity == "outbound_order"
        assert pubs[0].trigger == "after_update"
        assert pubs[0].condition == "status == 'shipped'"
        assert "order_no" in pubs[0].payload

        subs = manifests[TMS].events_subscribe
        assert len(subs) == 1, f"tms 应声明 1 条 subscribe, 实际 {subs}"
        assert subs[0].name == EVENT_NAME
        assert subs[0].source_app == WAREHOUSE
        assert subs[0].idempotency_key == "order_no"

    @pytest.mark.parametrize("events_yaml, expected", [
        ("""
    publish:
      - name: evt
        entity: thing
        trigger: after_save
        payload: [code]
""", "trigger"),
        ("""
    publish:
      - name: evt
        entity: thing
        trigger: after_update
        payload: []
""", "payload"),
        ("""
    publish:
      - name: evt
        entity: thing
        trigger: after_create
        payload: [code]
    subscribe:
      - name: evt
        from: other
        handler: handlers/noop.py
        idempotency_key: code
""", "既发布又订阅"),
    ])
    def test_invalid_event_declarations_rejected(self, tmp_path, events_yaml, expected):
        """非法声明在**加载期**就失败（启动期快速失败, §6.14.4 ④）。"""
        app_dir = _write_app(tmp_path, "badapp", f"""
app:
  id: badapp
  name: 坏应用
  version: 1.0.0
  events:
{events_yaml}""")
        with pytest.raises(AppManifestError) as exc:
            load_apps(["badapp"], apps_root=tmp_path)
        assert expected in str(exc.value), f"错误信息未点明原因: {exc.value}"

    def test_subscribe_to_missing_event_fails_validation(self):
        """订阅了发布方不存在的事件 → 启动期失败（§6.14.4 ④）。"""
        registry = EventContractRegistry()
        registry.register_publish(WAREHOUSE, SimpleNamespace(
            name=EVENT_NAME, entity="outbound_order", trigger="after_update",
            condition="", payload=["order_no"],
        ))
        registry.register_subscribe(TMS, SimpleNamespace(
            name="ghost_event", source_app=WAREHOUSE,
            handler="handlers/noop.py", idempotency_key="order_no",
        ), "")

        with pytest.raises(EventContractError) as exc:
            registry.validate([WAREHOUSE, TMS])
        assert "不存在的事件" in str(exc.value), str(exc.value)

    def test_subscribe_from_disabled_app_fails_validation(self):
        """来源应用未被 ENABLED_APPS 启用 → 启动期失败。"""
        registry = EventContractRegistry()
        registry.register_subscribe(TMS, SimpleNamespace(
            name=EVENT_NAME, source_app=WAREHOUSE,
            handler="handlers/noop.py", idempotency_key="order_no",
        ), "")

        with pytest.raises(EventContractError) as exc:
            registry.validate([TMS])
        assert "未被启用" in str(exc.value), str(exc.value)

    def test_subscribe_without_idempotency_key_fails_validation(self):
        """缺幂等键 → 启动期失败（at-least-once 投递下, 幂等是硬要求）。"""
        registry = EventContractRegistry()
        registry.register_publish(WAREHOUSE, SimpleNamespace(
            name=EVENT_NAME, entity="outbound_order", trigger="after_update",
            condition="", payload=["order_no"],
        ))
        registry.register_subscribe(TMS, SimpleNamespace(
            name=EVENT_NAME, source_app=WAREHOUSE,
            handler="handlers/noop.py", idempotency_key="",
        ), "")

        with pytest.raises(EventContractError) as exc:
            registry.validate([WAREHOUSE, TMS])
        assert "idempotency_key" in str(exc.value), str(exc.value)

    def test_registration_is_idempotent(self):
        """同一 (app, event) 重复注册只保留一份（PoC 2 的拦截器累加教训）。"""
        registry = EventContractRegistry()
        decl = SimpleNamespace(name=EVENT_NAME, entity="outbound_order",
                               trigger="after_update", condition="",
                               payload=["order_no"])
        registry.register_publish(WAREHOUSE, decl)
        registry.register_publish(WAREHOUSE, decl)

        assert len(registry.publishers) == 1
        assert registry.publisher_app_ids == [WAREHOUSE]

    @pytest.mark.parametrize("expression, row, expected", [
        ("status == 'shipped'", {"status": "shipped"}, True),
        ("status == 'shipped'", {"status": "created"}, False),
        ("status == 'shipped'", {}, False),
        ("status in ['shipped', 'done']", {"status": "done"}, True),
        ("status not in ['shipped']", {"status": "created"}, True),
        ("quantity > 1 and status == 'shipped'", {"quantity": 2, "status": "shipped"}, True),
        ("not status == 'shipped'", {"status": "created"}, True),
    ])
    def test_condition_evaluation(self, expression, row, expected):
        assert evaluate_condition(expression, row) is expected

    def test_condition_rejects_non_literal_expression(self):
        """契约属外部输入 —— 只允许字段比较, 不做 eval（R4 同类风险）。"""
        with pytest.raises(EventContractError):
            evaluate_condition("__import__('os').system('echo pwn')", {})


# ─────────────────────────────────────────────────────────────────────────────
# B: 端到端 —— 不丢 / 不重 / 死信
# ─────────────────────────────────────────────────────────────────────────────
class TestCrossAppEventFlow:

    def test_contracts_registered_at_startup(self, event_env):
        """启动期登记: 契约进入进程级注册表（Dispatcher 据此找发布方与订阅方）。"""
        registry = get_event_contract_registry()
        assert [p.app_id for p in registry.publishers] == [WAREHOUSE]
        assert [s.consumer_app for s in registry.subscribers] == [TMS]
        assert registry.subscribers_for(EVENT_NAME)[0].idempotency_key == "order_no"

    def test_event_tables_live_in_app_dbs(self, event_env):
        """事件表与业务表同库（§6.14.4 ①）—— 两个应用库都有各自的表。"""
        for db_file in ("warehouse.db", "tms.db"):
            db = _app_db(event_env, db_file)
            assert _table_exists(db, "event_outbox"), f"{db_file} 缺 event_outbox"
            assert _table_exists(db, "consumed_events"), f"{db_file} 缺 consumed_events"

    def test_business_write_enqueues_event_in_same_db(self, event_env, client):
        """出库单转 shipped → 事件入 outbox, 且落在**发布方应用库**。"""
        before = _count(event_env, "SELECT COUNT(*) FROM event_outbox")
        order_id = _create_order(client, "POC4-ORD-1", quantity=7.5)

        # 触发点是 after_update: 创建本身不产生事件
        assert _outbox_rows(event_env, "POC4-ORD-1") == [], "after_create 不应命中契约"

        _ship(client, order_id)
        rows = _outbox_rows(event_env, "POC4-ORD-1")
        assert len(rows) == 1, f"出库完成未产生事件: {rows}"
        row = rows[0]
        assert row["event_name"] == EVENT_NAME
        assert row["status"] == "pending"
        assert row["entity_id"] == order_id
        assert _count(event_env, "SELECT COUNT(*) FROM event_outbox") == before + 1

        payload = json.loads(row["payload"])
        assert payload["order_no"] == "POC4-ORD-1"
        assert float(payload["quantity"]) == 7.5

        # 事件行不得出现在消费方库 / 平台库（发布方归属唯一）
        assert _outbox_rows(event_env, "POC4-ORD-1", db_file="tms.db") == []
        platform_rows = _rows_if_table(
            get_meta_db_path(), "event_outbox",
            "SELECT id FROM event_outbox WHERE payload LIKE ?",
            ('%"order_no": "POC4-ORD-1"%',))
        assert platform_rows == [], "事件行落到了平台库 —— 库归属错误"

    def test_outbox_row_rolls_back_with_business_transaction(self, event_env):
        """同事务的直接证据: 业务事务回滚 ⇒ outbox 行一并消失（§6.14.4 ①）。"""
        from meta.core.datasource import open_app_data_source
        from meta.core.event_outbox import PublisherContract, enqueue_event

        data_source = open_app_data_source(WAREHOUSE, "data/warehouse.db")
        contract = PublisherContract(
            app_id=WAREHOUSE, name="rollback_probe", entity="outbound_order",
            trigger="after_update", payload=("order_no",),
        )
        before = _count(event_env, "SELECT COUNT(*) FROM event_outbox")

        with pytest.raises(RuntimeError):
            with data_source.transaction():
                enqueue_event(data_source, contract, 999999,
                              {"order_no": "ROLLBACK-PROBE"}, "txn-rollback-probe")
                raise RuntimeError("模拟业务写失败 → 事务回滚")

        assert _count(event_env, "SELECT COUNT(*) FROM event_outbox") == before, \
            "outbox 行未随业务事务回滚 —— 入队不在同一事务内"

    def test_event_survives_simulated_process_kill(self, event_env, client):
        """验证点 1（不丢）: 崩溃前未投递, 事件仍在库里; 重启后投递成功。

        "kill 进程"的等价表达: fixture 已停掉后台投递线程（崩溃点），此时
        业务写已成功提交 —— 若 outbox 不在同一事务, 这里就会丢事件。
        """
        order_id = _create_order(client, "POC4-ORD-2", quantity=3)
        _ship(client, order_id)

        assert _outbox_rows(event_env, "POC4-ORD-2")[0]["status"] == "pending"
        assert _waybills(event_env, "POC4-ORD-2") == [], "未投递就出现运单"
        assert _consumed(event_env, "POC4-ORD-2") == 0

        # 重启: 新建 Dispatcher 实例（新进程的首轮扫描）→ 待投递事件被送达
        stats = _dispatch(event_env)
        assert stats["delivered"] >= 1, f"重启后未投递: {stats}"

        waybills = _waybills(event_env, "POC4-ORD-2")
        assert len(waybills) == 1, f"重启后未建运单: {waybills}"
        assert waybills[0]["waybill_no"] == "WB-POC4-ORD-2"
        assert waybills[0]["status"] == "created"

        row = _outbox_rows(event_env, "POC4-ORD-2")[0]
        assert row["status"] == "delivered" and row["delivered_at"], row
        assert _consumed(event_env, "POC4-ORD-2") == 1

    def test_duplicate_delivery_creates_no_second_waybill(self, event_env):
        """验证点 2（不重）: 同一载荷的事件再投递一次 → 消费端幂等拦下。

        重复投递用 `enqueue_event` 再入队一条**同载荷**事件来表达: 事件 id 不同,
        但订阅契约的幂等键（order_no）相同 —— 正是 at-least-once 下的重投形态。
        """
        from meta.core.datasource import open_app_data_source
        from meta.core.event_outbox import PublisherContract, enqueue_event

        assert _outbox_rows(event_env, "POC4-ORD-2")[0]["status"] == "delivered"
        assert len(_waybills(event_env, "POC4-ORD-2")) == 1
        payload = json.loads(_outbox_rows(event_env, "POC4-ORD-2")[0]["payload"])

        contract = PublisherContract(
            app_id=WAREHOUSE, name=EVENT_NAME, entity="outbound_order",
            trigger="after_update", payload=tuple(payload.keys()),
        )
        data_source = open_app_data_source(WAREHOUSE, "data/warehouse.db")
        with data_source.transaction():
            event_id = enqueue_event(data_source, contract, None, payload, "txn-dup-probe")
        assert event_id, "重复投递探针未入队"

        stats = _dispatch(event_env)
        assert stats["delivered"] == 1, f"重复投递未被当作已处理: {stats}"

        assert len(_waybills(event_env, "POC4-ORD-2")) == 1, "重复投递产生了第二张运单"
        assert _consumed(event_env, "POC4-ORD-2") == 1, "去重表出现了重复行"

    def test_distinct_orders_create_distinct_waybills(self, event_env, client):
        """幂等只针对同一幂等键 —— 不同出库单仍各自建单（不是"全局只建一次"）。"""
        order_id = _create_order(client, "POC4-ORD-3", quantity=1)
        _ship(client, order_id)
        stats = _dispatch(event_env)
        assert stats["delivered"] == 1, stats

        assert len(_waybills(event_env, "POC4-ORD-3")) == 1
        assert len(_waybills(event_env, "POC4-ORD-2")) == 1

    def test_handler_failure_lands_in_dead_letter(self, event_env, client, tmp_path):
        """验证点 3（不无限重试）: handler 反复抛异常 → attempts 达上限后死信。"""
        registry = get_event_contract_registry()
        tms_manifest = load_apps([TMS])[0]
        real_sub = tms_manifest.events_subscribe[0]

        (tmp_path / "fail_handler.py").write_text(FAILING_HANDLER_SOURCE, encoding="utf-8")
        registry.register_subscribe(TMS, SimpleNamespace(
            name=EVENT_NAME, source_app=WAREHOUSE,
            handler="fail_handler.py", idempotency_key="order_no",
        ), str(tmp_path))
        try:
            order_id = _create_order(client, "POC4-ORD-4", quantity=2)
            _ship(client, order_id)

            outcomes = [_dispatch(event_env, max_attempts=3) for _ in range(3)]

            rows = _outbox_rows(event_env, "POC4-ORD-4")
            assert rows[0]["status"] == "dead", \
                f"未进死信（无限重试?）: {rows[0]} / 各轮结果 {outcomes}"
            assert rows[0]["attempts"] == 3, rows[0]
            assert "POC4_FAIL_MARKER" in _last_error(event_env, rows[0]["id"])

            assert _waybills(event_env, "POC4-ORD-4") == [], "失败重试不应建单"
            # 去重标记必须随事务回滚: 否则"标记过但没建单"会永久毒化该幂等键
            assert _consumed(event_env, "POC4-ORD-4") == 0, \
                "handler 失败后去重标记未回滚 —— 重试被永久阻断"

            # 已死信的事件不再被后续扫描重试
            assert _dispatch(event_env)["scanned"] == 0
        finally:
            # 复原真实订阅 —— 后续用例仍按生产 handler 投递
            registry.register_subscribe(TMS, real_sub, str(tms_manifest.app_dir))

    def test_consumer_app_api_reads_own_db(self, event_env, client):
        """消费结果可观测: tms 自定义 API 读自己的库（§6.5 统一出口）。"""
        resp = client.get(TMS_API_WAYBILLS)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
        body = resp.get_json()
        order_nos = {w["order_no"] for w in body["waybills"]}
        assert {"POC4-ORD-2", "POC4-ORD-3"} <= order_nos, f"运单未落到 tms 库: {body}"


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def _write_app(root, app_id, manifest_text):
    """在临时目录写一个最小应用包（供非法声明用例）。"""
    app_dir = root / app_id
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "app.yaml").write_text(manifest_text.strip() + "\n", encoding="utf-8")
    return app_dir


def _app_db(event_env, filename) -> str:
    return str(event_env["app_dir"] / filename)


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _table_exists(db_path, table_name) -> bool:
    if not os.path.isfile(str(db_path)):
        return False
    return bool(_query(str(db_path),
                       "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                       (table_name,)))


def _rows_if_table(db_path, table, sql, params=()):
    """跨库反查: 表不存在 ⇒ 无数据（避免拿"表都没有"当失败）。"""
    if not _table_exists(db_path, table):
        return []
    return _query(db_path, sql, params)


def _count(event_env, sql, params=()) -> int:
    rows = _query(_app_db(event_env, "warehouse.db"), sql, params)
    return int(rows[0][0]) if rows else 0


def _outbox_rows(event_env, order_no, db_file="warehouse.db"):
    """按事件载荷里的业务键定位 outbox 行。"""
    sql = ("SELECT id, event_name, status, attempts, entity_id, payload, delivered_at "
           "FROM event_outbox WHERE payload LIKE ? ORDER BY id")
    rows = _rows_if_table(_app_db(event_env, db_file), "event_outbox", sql,
                          (f'%"order_no": "{order_no}"%',))
    keys = ("id", "event_name", "status", "attempts", "entity_id", "payload",
            "delivered_at")
    return [dict(zip(keys, row)) for row in rows]


def _last_error(event_env, row_id) -> str:
    rows = _query(_app_db(event_env, "warehouse.db"),
                  "SELECT last_error FROM event_outbox WHERE id = ?", (row_id,))
    return rows[0][0] if rows else ""


def _waybills(event_env, order_no):
    rows = _rows_if_table(_app_db(event_env, "tms.db"), "waybills",
                          "SELECT waybill_no, status, quantity FROM waybills "
                          "WHERE order_no = ? ORDER BY id", (order_no,))
    return [{"waybill_no": r[0], "status": r[1], "quantity": r[2]} for r in rows]


def _consumed(event_env, idempotency_key) -> int:
    rows = _rows_if_table(_app_db(event_env, "tms.db"), "consumed_events",
                          "SELECT COUNT(*) FROM consumed_events WHERE consumer_app = ? "
                          "AND idempotency_key = ?", (TMS, idempotency_key))
    return int(rows[0][0]) if rows else 0


def _dispatch(event_env, max_attempts=3):
    """新建 Dispatcher 实例并跑一轮（= 重启后重新扫描 outbox 的进程）。"""
    dispatcher = EventDispatcher(get_event_contract_registry(),
                                 max_attempts=max_attempts, poll_interval=0.01)
    return dispatcher.dispatch_once()


def _create_order(client, order_no, quantity=5.0, item_id=101, warehouse_id=1):
    resp = client.post(BO_URL_OUTBOUND, json={
        "order_no": order_no, "item_id": item_id, "quantity": quantity,
        "warehouse_id": warehouse_id,
    })
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)[:400]
    body = resp.get_json()
    assert body.get("success"), body
    return body["data"]["id"]


def _ship(client, order_id, shipped_at="2026-09-24T10:00:00"):
    resp = client.put(f"{BO_URL_OUTBOUND}/{order_id}",
                      json={"status": "shipped", "shipped_at": shipped_at})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]