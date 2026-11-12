# 单据流服务化（Document Flow Service）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有单据流引擎之上补齐通用服务层、HTTP API、取消语义与元数据驱动前端，让「选择上游实例 → 编辑本次数量 → 生成/追加下游单据」成为平台通用能力（不再依赖 5 条硬编码业务链路）。

**Architecture:** 新增 `DocFlowService`（规则目录 / 未结量查询 / 派生 / 追溯）作为唯一业务入口，内部复用 `derive_batch` 与 `_consumed_in_pool`；新增 `/api/v2/doc-flow` 蓝图做参数校验与错误码映射，数据源用 `resolve_data_source(get_platform_data_source())`。取消语义在三个单据服务的 `cancel()` 内调用新增的 `release_target_edges()` 反向释放上游额度。前端新增无业务常量的三个组件 + 一个 service，通过列表页批量动作与详情页 section 两个入口接入。

**Tech Stack:** Python 3.11 / Flask / Waitress / SQLite ｜ Vue 3 + TS/Vite + Element Plus + Pinia ｜ 测试唯一入口 `python d:\filework\test.py --file <path>`

---

## 0. 前置约束（执行者必读）

1. **Spec 基线**：`docs/superpowers/specs/2026-11-08-doc-flow-service-spec.md`（v1.1）。本计划的任务号与 Spec 章节的映射见文末 Self-Review。
2. **测试铁律**：禁止 `pytest` / `python -m pytest`。唯一入口：
   `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
   期望输出形如：`Total: 9 (P=9, F=0, E=0, S=0) Exit: 0`。
3. **新增 Python 文件统一带 `# -*- coding: utf-8 -*-`**，注释中文、无 Emoji。
4. **前端 UI 约束**：必须用 `AppButton` / `AppModal` / `AppIcon`；可直接用 `el-table` / `el-input` / `el-input-number`；颜色只能来自 CSS 变量；禁止硬编码规则名 / BO 名 / 列 key；禁止 Emoji。
5. **提交规范**：每个 Task 末尾单独 commit；禁止在脏工作树上跨会话。
6. **不引入「数量时段」**（Spec §13 TBD-31 已关闭）；`pool` 只是配额分组，不是时间桶。

### 文件结构（先锁定边界）

新建（8）：

| 文件 | 职责 |
|---|---|
| `meta/services/doc_flow_service.py` | 服务层：`list_rules` / `list_sources` / `derive` / `list_edges` + 错误码 |
| `meta/api/doc_flow_api.py` | 蓝图 + 参数校验 + 错误响应映射（薄壳） |
| `meta/tests/test_doc_flow_service.py` | 服务层与规则元数据测试（含本文件私有夹具） |
| `meta/tests/test_doc_flow_api.py` | 蓝图视图函数契约测试（不经装饰器） |
| `meta/tests/test_doc_flow_cancel.py` | `release_target_edges` 释放额度测试 |
| `src/services/docFlowService.js` | 前端 API 封装 |
| `src/components/business/DocFlow/DocFlowSourcePicker.vue` | 上游选择 + 本次数量编辑（无弹窗，表格主体） |
| `src/components/business/DocFlow/DocFlowDerivePanel.vue` | 弹窗容器 + 提交 + 结果提示 |
| `src/components/business/DocFlow/DocFlowTracePanel.vue` | 详情页页签：上游来源 / 下游去向 |

修改（12）：

| 文件 | 改动 |
|---|---|
| `meta/core/doc_flow_rule_store.py` | 规则声明新增 `display_fields` 列（DDL + 幂等加列 + upsert + 读取解析） |
| `meta/core/doc_flow_derive_engine.py` | `_find_edge_by_key` / `_find_edge_loose` 加 `status='active'`；`DeriveResult` 补溯源字段 |
| `meta/core/doc_flow_schema.py` | 新增索引 `idx_doc_flow_edges_src` |
| `meta/core/doc_flow_reversal.py` | 新增 `release_target_edges()` |
| `meta/core/app_builder.py` | 注册 `doc_flow_bp` |
| `meta/server.py` | 注册 `doc_flow_bp`（第二注册点）+ 服务初始化 |
| `meta/services/shipment_service.py` | `cancel()` 内释放 `shipment_line` 目标边 |
| `meta/services/receipt_service.py` | `cancel()` 内释放 `receipt_line` 目标边 |
| `meta/services/transfer_order_service.py` | `cancel()` 内释放 `transfer_order_line` 目标边 |
| `src/components/common/MetaListPage/MetaListPage.vue` | `onBatchAction` 拦截 `doc_flow_derive` 并透传 |
| `src/views/GenericObjectList.vue` | 监听批量动作，打开派生面板 |
| `src/components/common/DetailPage/DetailPage.vue` | 两处 section 模板注入 `doc_flow_trace` |

### 关键接口事实（避免执行者再猜）

- `derive_batch(app_ds, platform_ds, rule_id, items, head_overrides=None, derived_by="")`，`items=[{"source_id","source_item","quantity"}]`，`quantity=None` 表示取未结量上限。
- `BatchDeriveResult(heads, total_edges, skipped_replays, per_item_open_qty, results)`，`results` 元素是 `DeriveResult`。
- `get_rule(platform_ds, rule_id)` 返回 dict（`field_map`/`split_key` 已解析），规则停用为 `status='deprecated'`。
- `_consumed_in_pool(app_ds, source_bo, source_id, source_item, pool)` 返回 float。
- 取消所需 BO id：`shipment_line` / `receipt_line` / `transfer_order_line`（来自 `meta/schemas/*.yaml`）。
- 交货单 `_write_so_edges` 的边方向是「计划行 → 交货行」，因此取消交货单要按 **target=shipment_line** 释放；收货/调拨的建单边同样是 **target=对应明细行**。
- 前端 `apiV2` 的 baseURL 是 `/api/v2`，故蓝图前缀 `/api/v2/doc-flow` 对应前端路径 `/doc-flow/...`。

---

## Task 1: 规则声明新增 `display_fields`

**Files:**
- Modify: `meta/core/doc_flow_rule_store.py:26-64`, `:110-186`, `:189-209`
- Test: `meta/tests/test_doc_flow_service.py`（新建，含私有夹具）

- [ ] **Step 1: 新建测试文件与夹具**

创建 `meta/tests/test_doc_flow_service.py`：

```python
# -*- coding: utf-8 -*-
"""[单据流 Phase 3] 服务层测试（spec 2026-11-08-doc-flow-service-spec.md §6/§8）。

覆盖：规则元数据下发 / 未结量查询 / 派生校验 / 追溯查询 / 幂等状态过滤。
测试入口：python d:\filework\test.py --file meta/tests/test_doc_flow_service.py
"""
import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_rule_store import (
    ensure_doc_flow_rule_table, get_rule, upsert_rules,
)
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType
from meta.core.models_annotations import SemanticAnnotation

SOURCE_BO = "dfs_order_line"
HEAD_BO = "dfs_delivery"
LINE_BO = "dfs_delivery_line"

_REGISTERED_BOS = (SOURCE_BO, HEAD_BO, LINE_BO)


def _field(fid, ftype, **kw):
    from meta.core.models import MetaField
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _demo_metas():
    from meta.core.models import MetaObject

    source = MetaObject(
        id=SOURCE_BO, name="测试订单行", table_name="dfs_order_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("order_no", FieldType.STRING),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("status", FieldType.STRING, default="open"),
        ],
    )
    head = MetaObject(
        id=HEAD_BO, name="测试交货单头", table_name="dfs_deliveries",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_no", FieldType.STRING),
            _field("order_no", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
            _field("created_at", FieldType.DATETIME),
        ],
    )
    line = MetaObject(
        id=LINE_BO, name="测试交货行", table_name="dfs_delivery_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_id", FieldType.INTEGER,
                   semantics=SemanticAnnotation(parent_key=True)),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
            _field("unit", FieldType.STRING),
        ],
    )
    return source, head, line


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_DIR", str(tmp_path / "db"))
    monkeypatch.delenv("APP_DB_ROUTING", raising=False)
    monkeypatch.delenv("ENABLED_APPS", raising=False)
    _clear_data_source_cache_for_testing()
    yield
    from meta.core.models import registry
    for bo_id in _REGISTERED_BOS:
        registry._objects.pop(bo_id, None)
    _clear_data_source_cache_for_testing()


@pytest.fixture
def dbs(tmp_path):
    app_ds = get_data_source("sqlite", database=str(tmp_path / "biz.db"))
    platform_ds = get_data_source("sqlite", database=str(tmp_path / "platform.db"))
    return app_ds, platform_ds


@pytest.fixture
def ready_env(dbs):
    app_ds, platform_ds = dbs
    from meta.core.models import registry
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import invalidate_cache

    metas = _demo_metas()
    for m in metas:
        registry.register(m)
    invalidate_cache()
    sync_schema_from_meta(app_ds, list(metas))
    ensure_doc_flow_edge_tables(app_ds)
    ensure_doc_flow_rule_table(platform_ds)
    return app_ds, platform_ds


def _make_rule(platform_ds, rule_id="dfs-rule", **overrides):
    rule = {
        "rule_id": rule_id,
        "source_bo": SOURCE_BO,
        "target_bo": HEAD_BO,
        "source_qty_field": "quantity",
    }
    rule.update(overrides)
    upsert_rules(platform_ds, [rule])
    return rule_id


def _insert_source(app_ds, row_id, quantity=100):
    app_ds.insert("dfs_order_lines", {
        "id": row_id, "order_no": "SO-{0}".format(row_id),
        "item_name": "物料A", "quantity": quantity,
        "unit": "PCS", "status": "open",
    })


def test_rule_declares_display_fields(ready_env):
    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, display_fields=["order_no", "item_name"])

    rule = get_rule(platform_ds, "dfs-rule")

    assert rule["display_fields"] == ["order_no", "item_name"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: FAIL，`no such column: display_fields`（或 `KeyError: 'display_fields'`）。

- [ ] **Step 3: 规则表加列**

修改 `meta/core/doc_flow_rule_store.py`：

DDL（`RULE_TABLE_DDL` 中 `head_fk_field` 之后）追加：

```python
    head_fk_field   TEXT NOT NULL DEFAULT '',
    display_fields  TEXT NOT NULL DEFAULT '[]',
```

`_ADDED_COLUMNS` 追加：

```python
    ("head_fk_field", "TEXT NOT NULL DEFAULT ''"),
    ("display_fields", "TEXT NOT NULL DEFAULT '[]'"),
```

`_UPSERT_DECL_FIELDS` 追加 `"display_fields"`：

```python
_UPSERT_DECL_FIELDS = (
    "source_bo", "target_bo", "source_qty_field", "pool",
    "check_hook", "map_hook", "create_hook",
    "field_map", "split_key", "target_line_bo", "head_fk_field",
    "display_fields",
)
```

`upsert_rules` 的 INSERT 列、VALUES 占位、`ON CONFLICT` 更新、参数元组同步改：

```python
            """INSERT INTO doc_flow_rule
               (rule_id, source_bo, target_bo, source_qty_field, pool,
                check_hook, map_hook, create_hook,
                field_map, split_key, target_line_bo, head_fk_field,
                display_fields, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
               ON CONFLICT(rule_id) DO UPDATE SET
                 source_bo = excluded.source_bo,
                 target_bo = excluded.target_bo,
                 source_qty_field = excluded.source_qty_field,
                 pool = excluded.pool,
                 check_hook = excluded.check_hook,
                 map_hook = excluded.map_hook,
                 create_hook = excluded.create_hook,
                 field_map = excluded.field_map,
                 split_key = excluded.split_key,
                 target_line_bo = excluded.target_line_bo,
                 head_fk_field = excluded.head_fk_field,
                 display_fields = excluded.display_fields,
                 updated_at = excluded.updated_at""",
            (
                rule_id,
                rule.get("source_bo", ""),
                rule.get("target_bo", ""),
                rule.get("source_qty_field") or "quantity",
                rule.get("pool") or "default",
                rule.get("check_hook") or None,
                rule.get("map_hook") or None,
                rule.get("create_hook") or None,
                _as_json_text(rule.get("field_map"), "{}"),
                _as_json_text(rule.get("split_key"), "[]"),
                rule.get("target_line_bo") or "",
                rule.get("head_fk_field") or "",
                _as_json_text(rule.get("display_fields"), "[]"),
                now, now,
            ),
```

`get_rule` 与 `list_rules` 的 JSON 解析各补一行：

```python
    rule["display_fields"] = _loads(rule.get("display_fields"), [])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: `Total: 1 (P=1, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 5: 提交**

```bash
git add meta/core/doc_flow_rule_store.py meta/tests/test_doc_flow_service.py
git commit -m "feat(doc-flow): 规则声明新增 display_fields 元数据列"
```

---

## Task 2: 幂等查询只认 active 边（C-05/C-06）

**Files:**
- Modify: `meta/core/doc_flow_derive_engine.py:97-131`
- Test: `meta/tests/test_doc_flow_service.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `meta/tests/test_doc_flow_service.py` 追加：

```python
def test_reversed_edge_does_not_block_rederive(ready_env):
    from meta.core.doc_flow_batch_engine import derive_batch
    from meta.core.doc_flow_reversal import reverse_edge

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)

    first = derive_batch(app_ds, platform_ds, "dfs-rule",
                         [{"source_id": 1, "source_item": "", "quantity": 100}])
    assert first.total_edges == 1
    reverse_edge(app_ds, first.results[0].edge_id, reversed_by="test")

    second = derive_batch(app_ds, platform_ds, "dfs-rule",
                          [{"source_id": 1, "source_item": "", "quantity": 100}])

    assert second.total_edges == 1
    assert second.skipped_replays == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: FAIL，`assert second.total_edges == 1` 实际为 0（reversed 边被当作重放命中）。

- [ ] **Step 3: 两个查找函数加状态过滤**

`meta/core/doc_flow_derive_engine.py` 的 `_find_edge_by_key` 与 `_find_edge_loose`，在 `WHERE rule_id=?` 后各加：

```python
             AND status = 'active'
```

即 `_find_edge_by_key` 的 SQL 变为：

```python
        """SELECT id FROM doc_flow_edges
           WHERE source_bo=? AND source_id=? AND source_item=?
             AND target_bo=? AND target_id=? AND target_item=? AND rule_id=?
             AND status='active'""",
```

`_find_edge_loose` 同理在 `AND rule_id=?` 之后加 `AND status='active'`。

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: `Total: 2 (P=2, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 5: 提交**

```bash
git add meta/core/doc_flow_derive_engine.py meta/tests/test_doc_flow_service.py
git commit -m "fix(doc-flow): 幂等查找忽略已冲销边，允许冲销后重新派生"
```

---

## Task 3: `DeriveResult` 补溯源字段

**Files:**
- Modify: `meta/core/doc_flow_derive_engine.py:65-74`, `:134-145`, `:181-385`
- Test: `meta/tests/test_doc_flow_service.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_derive_result_carries_source_identity(ready_env):
    from meta.core.doc_flow_batch_engine import derive_batch

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 30)

    batch = derive_batch(app_ds, platform_ds, "dfs-rule",
                         [{"source_id": 1, "source_item": "", "quantity": 30}])

    result = batch.results[0]
    assert result.source_id == 1
    assert result.source_item == ""
    assert result.quantity == 30.0
    assert result.target_item
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: FAIL，`AttributeError: 'DeriveResult' object has no attribute 'source_id'`。

- [ ] **Step 3: 扩展 dataclass**

`DeriveResult`（`meta/core/doc_flow_derive_engine.py`）追加四个带默认值的字段：

```python
@dataclass
class DeriveResult:
    edge_id: str
    target_id: str
    replay: bool
    source_qty: float
    consumed_qty: float
    open_qty: float
    source_id: Any = None
    source_item: str = ""
    target_item: str = ""
    quantity: float = 0.0
```

- [ ] **Step 4: 三处构造点补值**

`_replay_result` 增加参数并透传（函数签名追加 `quantity`、`target_item`）：

```python
def _replay_result(app_ds, rule, source_bo_id, source_id, source_item,
                   source_qty, edge_id, target_id, quantity,
                   target_item="") -> "DeriveResult":
```

其 `return DeriveResult(...)` 末尾补：

```python
        source_id=source_id,
        source_item=source_item,
        target_item=target_item,
        quantity=quantity,
    )
```

`_derive_core` 内两处 `return _replay_result(...)` 分别补 `quantity=qty, target_item=target_item`（单表模式）与 `quantity=qty, target_item=existing_item`（头行宽松键）。

`_derive_core` 末尾正常返回补：

```python
        source_id=source_id,
        source_item=source_item,
        target_item=target_item,
        quantity=qty,
    )
```

- [ ] **Step 5: 运行确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: `Total: 3 (P=3, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 6: 提交**

```bash
git add meta/core/doc_flow_derive_engine.py meta/tests/test_doc_flow_service.py
git commit -m "feat(doc-flow): DeriveResult 补源/目标溯源字段"
```

---

## Task 4: `DocFlowService` 骨架 + `list_rules`

**Files:**
- Create: `meta/services/doc_flow_service.py`
- Test: `meta/tests/test_doc_flow_service.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_list_rules_returns_ui_metadata(ready_env):
    from meta.services.doc_flow_service import DocFlowService

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, display_fields=["order_no", "item_name"])
    _make_rule(platform_ds, rule_id="dfs-deprecated")
    platform_ds.execute("UPDATE doc_flow_rule SET status='deprecated' WHERE rule_id='dfs-deprecated'")

    service = DocFlowService(app_ds, platform_ds)
    data = service.list_rules(source_bo=SOURCE_BO)

    assert data["total"] == 1
    rule = data["rules"][0]
    assert rule["rule_id"] == "dfs-rule"
    assert rule["source_columns"] == [
        {"field": "order_no", "label": "order_no"},
        {"field": "item_name", "label": "item_name"},
    ]
    assert rule["allow_append"] is False
    assert rule["append_label"] == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'meta.services.doc_flow_service'`。

- [ ] **Step 3: 创建服务骨架**

创建 `meta/services/doc_flow_service.py`：

```python
# -*- coding: utf-8 -*-
"""[单据流 Phase 3] 通用服务层（spec 2026-11-08-doc-flow-service-spec.md §6）。

职责：
- list_rules   : 规则目录 + UI 所需列元数据
- list_sources : 上游实例 + 已结量 / 未结量（单条 SQL，避免 N+1）
- derive       : 选择上游实例 -> 生成 / 追加下游对象（单事务）
- list_edges   : 单据流追溯（源侧 / 目标侧双口径）

约束：本模块不写业务常量，BO / 表 / 字段全部来自元数据与规则声明。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from meta.core.doc_flow_batch_engine import derive_batch
from meta.core.doc_flow_derive_engine import _consumed_in_pool, _num
from meta.core.doc_flow_rule_store import get_rule, list_rules
from meta.core.doc_flow_schema import DOC_FLOW_CONSUMED_VIEW
from meta.core.models import registry

_QTY_EPSILON = 1e-9
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class DocFlowServiceError(Exception):
    """服务层业务异常：code 直接作为 API 错误码。"""

    def __init__(self, code: str, message: str, status: int = 400,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


class DocFlowService:
    def __init__(self, app_ds, platform_ds):
        self.app_ds = app_ds
        self.platform_ds = platform_ds

    # ------------------------------------------------------------------ 规则
    def list_rules(self, source_bo: Optional[str] = None,
                   target_bo: Optional[str] = None) -> Dict[str, Any]:
        rules = list_rules(self.platform_ds, status="active")
        if source_bo:
            rules = [r for r in rules if r.get("source_bo") == source_bo]
        if target_bo:
            rules = [r for r in rules if r.get("target_bo") == target_bo]
        items = [self._rule_view(r) for r in rules]
        return {"rules": items, "total": len(items)}

    def _rule_view(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        source_obj = registry.get(rule.get("source_bo"))
        columns: List[Dict[str, str]] = []
        if source_obj is not None:
            for fid in rule.get("display_fields") or []:
                field = source_obj.get_field(fid)
                if field is not None:
                    columns.append({"field": fid, "label": field.name or fid})
        two_level = bool(rule.get("target_line_bo"))
        return {
            "rule_id": rule.get("rule_id"),
            "source_bo": rule.get("source_bo"),
            "target_bo": rule.get("target_bo"),
            "source_qty_field": rule.get("source_qty_field") or "quantity",
            "pool": rule.get("pool") or "default",
            "split_key": list(rule.get("split_key") or []),
            "target_line_bo": rule.get("target_line_bo") or "",
            "head_fk_field": rule.get("head_fk_field") or "",
            "display_fields": list(rule.get("display_fields") or []),
            "source_columns": columns,
            "allow_append": two_level,
            "append_label": "追加到当前单据" if two_level else "",
        }

    def _require_rule(self, rule_id: Optional[str]) -> Dict[str, Any]:
        rid = (rule_id or "").strip()
        rule = get_rule(self.platform_ds, rid) if rid else None
        if not rule:
            raise DocFlowServiceError(
                "DOC_FLOW_RULE_NOT_FOUND",
                "单据流规则不存在: {0}".format(rid), 404)
        if rule.get("status") != "active":
            raise DocFlowServiceError(
                "DOC_FLOW_RULE_NOT_FOUND",
                "单据流规则已停用: {0}".format(rid), 404)
        return rule

    def _source_meta(self, rule: Dict[str, Any]):
        obj = registry.get(rule.get("source_bo"))
        if obj is None:
            raise DocFlowServiceError(
                "DOC_FLOW_RULE_INVALID",
                "规则源对象未注册: {0}".format(rule.get("source_bo")), 409)
        id_field = obj.get_field("id")
        qty_field = obj.get_field(rule.get("source_qty_field") or "quantity")
        if id_field is None or qty_field is None:
            raise DocFlowServiceError(
                "DOC_FLOW_RULE_INVALID",
                "规则源字段缺失: {0}".format(rule.get("source_qty_field")), 409)
        return obj, id_field, qty_field
```

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: `Total: 4 (P=4, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 5: 提交**

```bash
git add meta/services/doc_flow_service.py meta/tests/test_doc_flow_service.py
git commit -m "feat(doc-flow): 服务层骨架与规则目录"
```

---

## Task 5: `list_sources`（未结量查询）

**Files:**
- Modify: `meta/services/doc_flow_service.py`
- Test: `meta/tests/test_doc_flow_service.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_list_sources_computes_open_qty(ready_env):
    from meta.core.doc_flow_batch_engine import derive_batch
    from meta.services.doc_flow_service import DocFlowService

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO,
               display_fields=["order_no", "item_name"])
    _insert_source(app_ds, 1, 100)
    _insert_source(app_ds, 2, 50)
    derive_batch(app_ds, platform_ds, "dfs-rule",
                 [{"source_id": 1, "source_item": "", "quantity": 60}])

    service = DocFlowService(app_ds, platform_ds)
    data = service.list_sources("dfs-rule")

    assert data["total"] == 2
    row = [r for r in data["items"] if r["source_id"] == 1][0]
    assert row["quantity"] == 100.0
    assert row["consumed_qty"] == 60.0
    assert row["open_qty"] == 40.0
    assert row["display"] == "SO-1 / 物料A"
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: FAIL，`AttributeError: 'DocFlowService' object has no attribute 'list_sources'`。

- [ ] **Step 3: 实现 `list_sources`**

在 `DocFlowService` 内追加：

```python
    # ------------------------------------------------------------------ 上游
    def list_sources(self, rule_id: str, filters: Optional[Dict[str, Any]] = None,
                     include_zero_open: bool = False, page: int = 1,
                     page_size: int = _DEFAULT_PAGE_SIZE,
                     source_item: str = "") -> Dict[str, Any]:
        rule = self._require_rule(rule_id)
        obj, id_field, qty_field = self._source_meta(rule)
        page = max(1, int(page or 1))
        page_size = min(_MAX_PAGE_SIZE, max(1, int(page_size or _DEFAULT_PAGE_SIZE)))

        used = {"source_id", "quantity", "consumed_qty"}
        display_fields: List[str] = []
        for fid in rule.get("display_fields") or []:
            field = obj.get_field(fid)
            if field is None or field.db_column in used:
                continue
            used.add(field.db_column)
            display_fields.append(fid)
        display_cols = [obj.get_field(fid).db_column for fid in display_fields]

        select_cols = [
            "s.{0} AS source_id".format(id_field.db_column),
            "s.{0} AS quantity".format(qty_field.db_column),
            "COALESCE(c.consumed_qty, 0) AS consumed_qty",
        ] + ["s.{0} AS {0}".format(col) for col in display_cols]

        from_sql = (
            " FROM {table} s LEFT JOIN {view} c"
            " ON c.source_bo = ? AND c.source_item = ? AND c.pool = ?"
            " AND c.source_id = CAST(s.{id_col} AS TEXT)"
        ).format(table=obj.table_name, view=DOC_FLOW_CONSUMED_VIEW,
                 id_col=id_field.db_column)

        where = ["1 = 1"]
        params: List[Any] = [
            rule.get("source_bo"), source_item or "",
            rule.get("pool") or "default",
        ]
        if not include_zero_open:
            where.append(
                "(s.{0} - COALESCE(c.consumed_qty, 0)) > ?".format(
                    qty_field.db_column))
            params.append(_QTY_EPSILON)
        for key, value in (filters or {}).items():
            if value in (None, ""):
                continue
            field = obj.get_field(key)
            if field is None:
                continue
            where.append("CAST(s.{0} AS TEXT) LIKE ?".format(field.db_column))
            params.append("%{0}%".format(value))
        where_sql = " WHERE " + " AND ".join(where)

        count_rows = self.app_ds.execute(
            "SELECT COUNT(*)" + from_sql + where_sql, tuple(params)).fetchall()
        total = int(count_rows[0][0]) if count_rows else 0

        rows = self.app_ds.execute(
            "SELECT " + ", ".join(select_cols) + from_sql + where_sql +
            " ORDER BY s.{0} LIMIT ? OFFSET ?".format(id_field.db_column),
            tuple(params + [page_size, (page - 1) * page_size]),
        ).fetchall()

        keys = ["source_id", "quantity", "consumed_qty"] + display_cols
        items: List[Dict[str, Any]] = []
        for row in rows:
            record = dict(zip(keys, row))
            quantity = _num(record.get("quantity"))
            consumed = _num(record.get("consumed_qty"))
            display_parts = [
                str(record.get(col)).strip()
                for col in display_cols
                if record.get(col) not in (None, "")
            ]
            split_values = {}
            for key in rule.get("split_key") or []:
                field = obj.get_field(key)
                if field is not None:
                    split_values[key] = record.get(field.db_column)
            display_values = {
                fid: record.get(obj.get_field(fid).db_column)
                for fid in display_fields
            }
            items.append({
                "source_id": record.get("source_id"),
                "source_item": source_item or "",
                "quantity": quantity,
                "consumed_qty": consumed,
                "open_qty": round(quantity - consumed, 6),
                "display": " / ".join(display_parts),
                "display_values": display_values,
                "split_key_values": split_values,
            })
        return {"items": items, "total": total,
                "page": page, "page_size": page_size}
```

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: `Total: 5 (P=5, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 5: 提交**

```bash
git add meta/services/doc_flow_service.py meta/tests/test_doc_flow_service.py
git commit -m "feat(doc-flow): 上游实例未结量查询"
```

---

## Task 6: `derive`（7 步校验 + 单事务）

**Files:**
- Modify: `meta/services/doc_flow_service.py`
- Test: `meta/tests/test_doc_flow_service.py`（追加）

- [ ] **Step 1: 写失败测试（覆盖 4 条主路径）**

```python
def _edge_count(app_ds):
    rows = app_ds.execute("SELECT COUNT(*) FROM doc_flow_edges").fetchall()
    return int(rows[0][0])


def test_derive_create_returns_target_and_totals(ready_env):
    from meta.services.doc_flow_service import DocFlowService

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    data = service.derive({
        "rule_id": "dfs-rule",
        "sources": [{"source_id": 1, "quantity": 30}],
        "target": {"mode": "create", "bo": HEAD_BO},
    }, derived_by="tester")

    assert len(data["target"]["ids"]) == 1
    assert data["totals"] == {"requested": 1, "written": 1, "replayed": 0}
    assert data["created"][0]["source_id"] == 1
    assert data["created"][0]["quantity"] == 30.0
    assert _edge_count(app_ds) == 1


def test_derive_quantity_exceeded(ready_env):
    from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    with pytest.raises(DocFlowServiceError) as exc:
        service.derive({
            "rule_id": "dfs-rule",
            "sources": [{"source_id": 1, "quantity": 120}],
            "target": {"mode": "create"},
        })

    assert exc.value.code == "DOC_FLOW_QTY_EXCEEDED"
    assert exc.value.status == 409
    assert exc.value.details["open_qty"] == 100.0
    assert _edge_count(app_ds) == 0


def test_derive_invalid_quantity_and_duplicate_source(ready_env):
    from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    with pytest.raises(DocFlowServiceError) as exc:
        service.derive({"rule_id": "dfs-rule",
                        "sources": [{"source_id": 1, "quantity": 0}],
                        "target": {"mode": "create"}})
    assert exc.value.code == "DOC_FLOW_QTY_INVALID"

    with pytest.raises(DocFlowServiceError) as exc:
        service.derive({"rule_id": "dfs-rule",
                        "sources": [{"source_id": 1}, {"source_id": 1}],
                        "target": {"mode": "create"}})
    assert exc.value.code == "DOC_FLOW_DUPLICATE_SOURCE"


def test_derive_single_table_append_rejected(ready_env):
    from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds)  # 单表模式：无 target_line_bo
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    with pytest.raises(DocFlowServiceError) as exc:
        service.derive({"rule_id": "dfs-rule",
                        "sources": [{"source_id": 1, "quantity": 10}],
                        "target": {"mode": "append", "id": 99}})
    assert exc.value.code == "DOC_FLOW_TARGET_MODE_INVALID"
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: FAIL，`AttributeError: 'DocFlowService' object has no attribute 'derive'`。

- [ ] **Step 3: 实现错误映射与 `derive`**

在 `meta/services/doc_flow_service.py` 顶部（`DocFlowService` 之前）追加映射表：

```python
_ENGINE_ERROR_MAP = {
    "BATCH_EMPTY": ("DOC_FLOW_QTY_INVALID", 400),
    "RULE_NOT_FOUND": ("DOC_FLOW_RULE_NOT_FOUND", 404),
    "RULE_DEPRECATED": ("DOC_FLOW_RULE_NOT_FOUND", 404),
    "BO_NOT_REGISTERED": ("DOC_FLOW_RULE_INVALID", 409),
    "SOURCE_QTY_FIELD_MISSING": ("DOC_FLOW_RULE_INVALID", 409),
    "TARGET_LINE_BO_MISSING": ("DOC_FLOW_RULE_INVALID", 409),
    "HEAD_FK_NOT_FOUND": ("DOC_FLOW_RULE_INVALID", 409),
    "SPLIT_KEY_FIELD_MISSING": ("DOC_FLOW_SPLIT_KEY_FIELD_MISSING", 400),
    "SOURCE_ROW_NOT_FOUND": ("DOC_FLOW_SOURCE_NOT_FOUND", 404),
    "TARGET_ROW_NOT_FOUND": ("DOC_FLOW_TARGET_NOT_FOUND", 404),
    "INVALID_QUANTITY": ("DOC_FLOW_QTY_INVALID", 400),
    "OVER_DERIVE": ("DOC_FLOW_QTY_EXCEEDED", 409),
    "HEAD_LINE_MULTI_NOT_SUPPORTED": ("HEAD_LINE_MULTI_NOT_SUPPORTED", 409),
}
```

在 `DocFlowService` 内追加：

```python
    # ------------------------------------------------------------------ 派生
    def derive(self, payload: Dict[str, Any],
               derived_by: str = "") -> Dict[str, Any]:
        payload = payload or {}
        rule = self._require_rule(payload.get("rule_id"))
        target = payload.get("target") or {}
        mode = target.get("mode") or "create"
        two_level = bool(rule.get("target_line_bo"))

        if mode not in ("create", "append"):
            raise DocFlowServiceError(
                "DOC_FLOW_TARGET_MODE_INVALID",
                "target.mode 仅支持 create / append", 400)
        if mode == "append" and not two_level:
            raise DocFlowServiceError(
                "DOC_FLOW_TARGET_MODE_INVALID",
                "单表模式不支持追加，请使用 create", 400)
        if mode == "append" and target.get("id") in (None, ""):
            raise DocFlowServiceError(
                "DOC_FLOW_TARGET_MODE_INVALID",
                "append 模式必须提供目标单据 ID", 400)

        raw_sources = payload.get("sources") or []
        if not isinstance(raw_sources, list) or not raw_sources:
            raise DocFlowServiceError(
                "DOC_FLOW_QTY_INVALID", "sources 不能为空", 400)

        normalized: List[Dict[str, Any]] = []
        seen = set()
        for raw in raw_sources:
            if not isinstance(raw, dict):
                raise DocFlowServiceError(
                    "DOC_FLOW_QTY_INVALID", "sources 元素必须是对象", 400)
            source_id = raw.get("source_id")
            if source_id in (None, ""):
                raise DocFlowServiceError(
                    "DOC_FLOW_SOURCE_NOT_FOUND", "source_id 不能为空", 404)
            source_item = raw.get("source_item") or ""
            key = (str(source_id), source_item)
            if key in seen:
                raise DocFlowServiceError(
                    "DOC_FLOW_DUPLICATE_SOURCE",
                    "同一源行重复出现: {0}/{1}".format(source_id, source_item), 400)
            seen.add(key)
            quantity = raw.get("quantity")
            if quantity is not None:
                quantity = _num(quantity)
                if not math.isfinite(quantity) or quantity <= 0:
                    raise DocFlowServiceError(
                        "DOC_FLOW_QTY_INVALID",
                        "quantity 必须是大于 0 的有限数", 400)
            normalized.append({"source_id": source_id,
                               "source_item": source_item,
                               "quantity": quantity})

        head_overrides = None
        if mode == "append":
            head_overrides = {"id": target.get("id")}
            if isinstance(target.get("data"), dict):
                head_overrides.update(target["data"])

        with self.app_ds.transaction():
            self._assert_open_qty(rule, normalized)
            try:
                batch = derive_batch(
                    self.app_ds, self.platform_ds, rule["rule_id"],
                    normalized, head_overrides=head_overrides,
                    derived_by=derived_by)
            except Exception as exc:
                self._raise_mapped(exc)
        return self._derive_view(rule, batch)

    def _assert_open_qty(self, rule: Dict[str, Any],
                         items: List[Dict[str, Any]]) -> None:
        obj, id_field, qty_field = self._source_meta(rule)
        pool = rule.get("pool") or "default"
        for item in items:
            rows = self.app_ds.execute(
                "SELECT {0} FROM {1} WHERE {2} = ?".format(
                    qty_field.db_column, obj.table_name, id_field.db_column),
                (item["source_id"],),
            ).fetchall()
            if not rows:
                raise DocFlowServiceError(
                    "DOC_FLOW_SOURCE_NOT_FOUND",
                    "上游记录不存在: {0}".format(item["source_id"]), 404)
            total_qty = _num(rows[0][0])
            consumed = _consumed_in_pool(
                self.app_ds, rule.get("source_bo"), item["source_id"],
                item["source_item"], pool)
            open_qty = total_qty - consumed
            if item["quantity"] is None:
                if open_qty <= _QTY_EPSILON:
                    raise DocFlowServiceError(
                        "DOC_FLOW_QTY_INVALID",
                        "上游已结清，无可用数量: {0}".format(item["source_id"]), 400)
                item["quantity"] = open_qty
            elif item["quantity"] > open_qty + _QTY_EPSILON:
                raise DocFlowServiceError(
                    "DOC_FLOW_QTY_EXCEEDED", "本次生成数量超过未结量", 409,
                    {"source_id": item["source_id"],
                     "source_item": item["source_item"],
                     "open_qty": open_qty,
                     "requested": item["quantity"]})

    def _raise_mapped(self, exc: Exception) -> None:
        code = getattr(exc, "code", "")
        mapped = _ENGINE_ERROR_MAP.get(code)
        if mapped is None:
            raise exc
        new_code, status = mapped
        message = getattr(exc, "message", None) or str(exc)
        raise DocFlowServiceError(new_code, message, status)

    def _derive_view(self, rule: Dict[str, Any], batch) -> Dict[str, Any]:
        created: List[Dict[str, Any]] = []
        replayed: List[Dict[str, Any]] = []
        for result in batch.results:
            entry = {
                "source_id": result.source_id,
                "source_item": result.source_item,
                "target_id": result.target_id,
                "target_item": result.target_item,
                "quantity": result.quantity,
                "edge_id": result.edge_id,
            }
            (replayed if result.replay else created).append(entry)
        return {
            "target": {"bo": rule.get("target_bo"), "ids": list(batch.heads)},
            "created": created,
            "replayed": replayed,
            "totals": {
                "requested": len(created) + len(replayed),
                "written": batch.total_edges,
                "replayed": batch.skipped_replays,
            },
        }
```

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: `Total: 9 (P=9, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 5: 提交**

```bash
git add meta/services/doc_flow_service.py meta/tests/test_doc_flow_service.py
git commit -m "feat(doc-flow): 派生服务（校验/事务/结果映射）"
```

---

## Task 7: `list_edges` 双口径追溯

**Files:**
- Modify: `meta/services/doc_flow_service.py`
- Test: `meta/tests/test_doc_flow_service.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_list_edges_both_directions(ready_env):
    from meta.services.doc_flow_service import DocFlowService

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    head_id = service.derive({
        "rule_id": "dfs-rule",
        "sources": [{"source_id": 1, "quantity": 20}],
        "target": {"mode": "create"},
    })["target"]["ids"][0]

    by_source = service.list_edges(source_bo=SOURCE_BO, source_id=1)
    by_target = service.list_edges(target_bo=HEAD_BO, target_id=head_id)

    assert by_source["total"] == 1
    assert by_target["total"] == 1
    assert by_source["items"][0]["status"] == "active"
    assert by_source["items"][0]["quantity"] == 20.0


def test_list_edges_requires_filter(ready_env):
    from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

    app_ds, platform_ds = ready_env
    service = DocFlowService(app_ds, platform_ds)

    with pytest.raises(DocFlowServiceError) as exc:
        service.list_edges()

    assert exc.value.code == "DOC_FLOW_EDGE_FILTER_REQUIRED"
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: FAIL，`AttributeError: 'DocFlowService' object has no attribute 'list_edges'`。

- [ ] **Step 3: 实现 `list_edges`**

模块顶部追加常量：

```python
_EDGE_COLUMNS = (
    "id", "source_bo", "source_id", "source_item",
    "target_bo", "target_id", "target_item",
    "quantity", "quantity_sign", "rule_id", "status", "pool",
    "edge_kind", "reverses_edge_id", "unit",
    "derived_at", "derived_by",
)
```

`DocFlowService` 内追加：

```python
    # ------------------------------------------------------------------ 追溯
    def list_edges(self, source_bo: Optional[str] = None,
                   source_id: Any = None,
                   source_item: Optional[str] = None,
                   target_bo: Optional[str] = None,
                   target_id: Any = None) -> Dict[str, Any]:
        if source_bo and source_id not in (None, ""):
            where = ["source_bo = ?", "source_id = ?"]
            params: List[Any] = [source_bo, str(source_id)]
            if source_item is not None:
                where.append("source_item = ?")
                params.append(source_item)
        elif target_bo and target_id not in (None, ""):
            where = ["target_bo = ?", "target_id = ?"]
            params = [target_bo, str(target_id)]
        else:
            raise DocFlowServiceError(
                "DOC_FLOW_EDGE_FILTER_REQUIRED",
                "必须提供 source_bo+source_id 或 target_bo+target_id", 400)

        rows = self.app_ds.execute(
            "SELECT " + ", ".join(_EDGE_COLUMNS) + " FROM doc_flow_edges"
            " WHERE " + " AND ".join(where) +
            " ORDER BY derived_at, id",
            tuple(params),
        ).fetchall()
        items = [dict(zip(_EDGE_COLUMNS, row)) for row in rows]
        return {"items": items, "total": len(items)}
```

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: `Total: 11 (P=11, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 5: 提交**

```bash
git add meta/services/doc_flow_service.py meta/tests/test_doc_flow_service.py
git commit -m "feat(doc-flow): 单据流追溯查询（源/目标双口径）"
```

## Task 8: 源行级索引 `idx_doc_flow_edges_src`

**Files:**
- Modify: `meta/core/doc_flow_schema.py:111-117`（在 `idx_doc_flow_target` 之后追加）
- Test: `meta/tests/test_doc_flow_service.py`（追加到文件末尾）

- [ ] **Step 1: 写失败测试**

在 `meta/tests/test_doc_flow_service.py` 末尾追加：

```python
def test_edges_source_item_index_declared():
    from meta.core.doc_flow_schema import _build_edge_meta
    meta = _build_edge_meta()
    names = {idx.name for idx in meta.indexes}
    assert 'idx_doc_flow_edges_src' in names


def test_edges_source_item_index_created_in_sqlite(dbs):
    _, app_ds = dbs
    app_ds.execute('DROP INDEX IF EXISTS idx_doc_flow_edges_src')
    from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
    ensure_doc_flow_edge_tables(app_ds)
    rows = app_ds.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        ('idx_doc_flow_edges_src',)).fetchall()
    assert rows, '索引未创建'
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: FAIL —— `StopIteration`（找不到 `idx_doc_flow_edges_src`）。

- [ ] **Step 3: 在 schema 中声明索引**

在 `meta/core/doc_flow_schema.py` 的 `indexes=[...]` 列表末尾（`idx_doc_flow_target` 之后、`]` 之前）追加：

```python
        MetaIndex(
            fields=["source_bo", "source_id", "source_item", "status"],
            db_columns=["source_bo", "source_id", "source_item", "status"],
            name="idx_doc_flow_edges_src", source=IndexSource.SCHEMA,
            description="源行级已派生子查询（list_edges 按源行追溯 / 未结量按行聚合）",
        ),
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_service.py`
Expected: PASS，`Total: N (P=N, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 5: 提交**

```bash
git add meta/core/doc_flow_schema.py meta/tests/test_doc_flow_service.py
git commit -m "feat(doc-flow): add source-item index for row-level trace"
```

---

## Task 9: HTTP API `/api/v2/doc-flow`

**Files:**
- Create: `meta/api/doc_flow_api.py`
- Modify: `meta/core/app_builder.py:335-370`（import 区 + `register_blueprint` 区）
- Modify: `meta/server.py:658-676`（服务初始化）与 `meta/server.py:1091` 之后（注册蓝图）
- Test: `meta/tests/test_doc_flow_api.py`

- [ ] **Step 1: 写失败测试**

创建 `meta/tests/test_doc_flow_api.py`：

```python
# -*- coding: utf-8 -*-
"""单据流 API 契约测试（路由存在性 + 视图函数行为 + 未登录 401）。"""

import pytest
from flask import Flask

from meta.api.doc_flow_api import doc_flow_bp, init_doc_flow_service
from meta.services.doc_flow_service import DocFlowServiceError


class FakeDocFlowService:
    def __init__(self):
        self.calls = []

    def list_rules(self, source_bo=None, target_bo=None):
        return {'rules': [{'rule_id': 'r1', 'source_bo': source_bo,
                           'target_bo': target_bo}], 'total': 1}

    def list_sources(self, rule_id, filters=None, include_zero_open=False,
                     page=1, page_size=20, source_item=''):
        self.calls.append(('list_sources', rule_id, filters, page, page_size))
        return {'rows': [{'source_id': '1', 'open_qty': 40}], 'total': 1,
                'page': page, 'page_size': page_size}

    def derive(self, payload, derived_by=''):
        self.calls.append(('derive', payload, derived_by))
        if payload.get('rule_id') == 'boom':
            raise DocFlowServiceError('DOC_FLOW_RULE_NOT_FOUND', '规则不存在', 404)
        return {'created': [{'target_id': 'T1'}], 'replayed': [],
                'total_edges': 1}

    def list_edges(self, **kwargs):
        return {'edges': [{'id': 'e1', 'quantity': 10.0}], 'total': 1}


@pytest.fixture()
def api_app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(doc_flow_bp)
    init_doc_flow_service(FakeDocFlowService())
    return app


def test_routes_registered(api_app):
    rules = {r.rule for r in api_app.url_map.iter_rules()}
    assert '/api/v2/doc-flow/rules' in rules
    assert '/api/v2/doc-flow/sources' in rules
    assert '/api/v2/doc-flow/derive' in rules
    assert '/api/v2/doc-flow/edges' in rules


def test_rules_requires_login(api_app):
    resp = api_app.test_client().get('/api/v2/doc-flow/rules')
    assert resp.status_code == 401
    assert resp.get_json()


def test_rules_view_filters_by_source_bo(api_app):
    from meta.api.doc_flow_api import _rules_view
    with api_app.test_request_context('/api/v2/doc-flow/rules?source_bo=shipment'):
        body, status = _rules_view()
    assert status == 200
    assert body['success'] is True
    assert body['data']['rules'][0]['source_bo'] == 'shipment'


def test_sources_view_passes_paging(api_app):
    from meta.api.doc_flow_api import _sources_view
    with api_app.test_request_context(
            '/api/v2/doc-flow/sources?rule_id=r1&page=2&page_size=5'):
        body, status = _sources_view()
    assert status == 200
    assert body['data']['page'] == 2
    assert body['data']['page_size'] == 5


def test_derive_view_requires_rule_id(api_app):
    from meta.api.doc_flow_api import _derive_view
    with api_app.test_request_context('/api/v2/doc-flow/derive', method='POST',
                                      json={'sources': []}):
        body, status = _derive_view()
    assert status == 400
    assert body['code'] == 'DOC_FLOW_QTY_INVALID'


def test_derive_view_maps_service_error(api_app):
    from meta.api.doc_flow_api import _derive_view
    with api_app.test_request_context('/api/v2/doc-flow/derive', method='POST',
                                      json={'rule_id': 'boom', 'sources': []}):
        resp, status = _derive_view()
    assert status == 404
    assert resp['code'] == 'DOC_FLOW_RULE_NOT_FOUND'


def test_edges_view_requires_a_filter(api_app):
    from meta.api.doc_flow_api import _edges_view
    with api_app.test_request_context('/api/v2/doc-flow/edges'):
        body, status = _edges_view()
    assert status == 400
    assert body['code'] == 'DOC_FLOW_EDGE_FILTER_REQUIRED'
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_api.py`
Expected: FAIL —— `ModuleNotFoundError: No module named 'meta.api.doc_flow_api'`

- [ ] **Step 3: 实现 API 模块**

创建 `meta/api/doc_flow_api.py`：

```python
# -*- coding: utf-8 -*-
"""单据流服务 HTTP API（/api/v2/doc-flow）。

四个只做「参数翻译 + 错误映射」的端点：
  GET  /rules    规则清单（含 display_fields / 目标模式）
  GET  /sources  上游实例 + 已生成 + 未结量（分页）
  POST /derive   按上游行生成本次下游数量（批量）
  GET  /edges    边追溯（源侧或目标侧二选一）

视图体与装饰器分离：`_xxx_view()` 是纯函数（测试直接调用），
`xxx()` 只负责套 `@login_required`。
"""

import logging
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, request

from meta.services.auth_middleware import login_required
from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

logger = logging.getLogger(__name__)

doc_flow_bp = Blueprint('doc_flow', __name__, url_prefix='/api/v2/doc-flow')

_service: Optional[DocFlowService] = None

_EDGE_ARGS = ('source_bo', 'source_id', 'source_item', 'target_bo', 'target_id')


def init_doc_flow_service(service: DocFlowService) -> None:
    """由 server / app_builder 在启动期注入单例。"""
    global _service
    _service = service


def _require_service() -> DocFlowService:
    if _service is None:
        raise DocFlowServiceError(
            'DOC_FLOW_SERVICE_UNAVAILABLE', '单据流服务未初始化', 500)
    return _service


def _ok(data: Any, message: str = '') -> Tuple[Dict[str, Any], int]:
    """统一返回 `(payload, status)`，与 `_fail` 同形，便于视图直接作为路由返回值。"""
    return {'success': True, 'data': data, 'message': message}, 200


def _fail(code: str, message: str, status: int = 400) -> Tuple[Dict[str, Any], int]:
    return {'success': False, 'data': None,
            'message': message, 'code': code}, status


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _filters_from_args() -> Dict[str, Any]:
    """把 `filter_<field>=<value>` 折叠成 dict，值域由服务层白名单裁决。"""
    filters: Dict[str, Any] = {}
    for key, value in request.args.items():
        if key.startswith('filter_') and value != '':
            filters[key[len('filter_'):]] = value
    return filters


# ----------------------------------------------------------------------
# 视图体（无装饰器，便于单元测试）
# ----------------------------------------------------------------------
def _rules_view() -> Tuple[Dict[str, Any], int]:
    service = _require_service()
    data = service.list_rules(
        source_bo=request.args.get('source_bo') or None,
        target_bo=request.args.get('target_bo') or None)
    return _ok(data)


def _sources_view() -> Any:
    service = _require_service()
    rule_id = request.args.get('rule_id') or ''
    if not rule_id:
        return _fail('DOC_FLOW_RULE_INVALID', '缺少 rule_id', 400)
    try:
        data = service.list_sources(
            rule_id,
            filters=_filters_from_args(),
            include_zero_open=(request.args.get('include_zero_open') or '')
            .lower() in ('1', 'true', 'yes'),
            page=_as_int(request.args.get('page'), 1),
            page_size=_as_int(request.args.get('page_size'), 20),
            source_item=request.args.get('source_item') or '')
    except DocFlowServiceError as error:
        return _fail(error.code, error.message, error.status)
    return _ok(data)


def _derive_view() -> Any:
    service = _require_service()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return _fail('DOC_FLOW_QTY_INVALID', '请求体必须是 JSON 对象', 400)
    if not payload.get('rule_id'):
        return _fail('DOC_FLOW_QTY_INVALID', '缺少 rule_id', 400)
    try:
        data = service.derive(payload, derived_by='doc_flow_api')
    except DocFlowServiceError as error:
        return _fail(error.code, error.message, error.status)
    return _ok(data, '已生成 {0} 条下游边'.format(data.get('total_edges', 0)))


def _edges_view() -> Any:
    service = _require_service()
    kwargs = {key: request.args.get(key) for key in _EDGE_ARGS
              if request.args.get(key) not in (None, '')}
    if not kwargs:
        return _fail('DOC_FLOW_EDGE_FILTER_REQUIRED',
                     '至少提供一个追溯条件（source_bo+source_id 或 target_bo+target_id）',
                     400)
    try:
        data = service.list_edges(**kwargs)
    except DocFlowServiceError as error:
        return _fail(error.code, error.message, error.status)
    return _ok(data)


# ----------------------------------------------------------------------
# 路由壳
# ----------------------------------------------------------------------
@doc_flow_bp.route('/rules', methods=['GET'])
@login_required
def list_rules_route():
    return _rules_view()


@doc_flow_bp.route('/sources', methods=['GET'])
@login_required
def list_sources_route():
    return _sources_view()


@doc_flow_bp.route('/derive', methods=['POST'])
@login_required
def derive_route():
    return _derive_view()


@doc_flow_bp.route('/edges', methods=['GET'])
@login_required
def list_edges_route():
    return _edges_view()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_api.py`
Expected: PASS，`Total: N (P=N, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 5: 注册蓝图（双注册点）**

在 `meta/core/app_builder.py` 的蓝图 import 区追加：

```python
from meta.api.doc_flow_api import doc_flow_bp
```

在其 `register_blueprint` 区（与其它 `*_bp` 同组）追加：

```python
    app.register_blueprint(doc_flow_bp)
```

在 `meta/server.py` 的服务初始化区（L658-676 附近）追加：

```python
from meta.api.doc_flow_api import init_doc_flow_service
from meta.services.doc_flow_service import DocFlowService

# `data_source` 是本函数内既有的应用库变量；平台库缺省时由服务层回落到应用库
init_doc_flow_service(DocFlowService(data_source, get_platform_data_source()))
```

> `get_platform_data_source` 若尚未在 `meta/server.py` 导入，一并加入其 `meta.core.datasource` 导入行。
> **不要**新建第二个 DataSource 实例——必须复用应用启动期已经建立的 `data_source`（否则事务与连接池分裂）。

在 `meta/server.py:1091` 的 `app.register_blueprint(meta_util_bp)` 之后追加：

```python
from meta.api.doc_flow_api import doc_flow_bp
app.register_blueprint(doc_flow_bp)
```

- [ ] **Step 6: 验证蓝图生效（真实服务）**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_api.py`
Expected: PASS。

再用既有服务验证路由已挂载（服务未启动时先 `python scripts/service_manager.py start`）：

```powershell
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:3011/api/v2/doc-flow/rules
```

Expected: `401`（未登录被 `login_required` 拦截，说明路由存在且守卫生效）。

- [ ] **Step 7: 提交**

```bash
git add meta/api/doc_flow_api.py meta/core/app_builder.py meta/server.py meta/tests/test_doc_flow_api.py
git commit -m "feat(doc-flow): expose rules/sources/derive/edges API"
```

---

## Task 10: 取消释放上游占用（`release_target_edges` + 三个 cancel）

**Files:**
- Modify: `meta/core/doc_flow_reversal.py`（在 `reverse_edge` 之后新增函数）
- Modify: `meta/services/shipment_service.py:623-636`（`cancel`）
- Modify: `meta/services/receipt_service.py:694-710`（`cancel`）
- Modify: `meta/services/transfer_order_service.py:643-667`（`cancel`）
- Test: `meta/tests/test_doc_flow_cancel.py`

**语义（写进 docstring，供后续维护者对照 Spec §8）：**
- 下游单据取消 → 其名下 `active + normal` 边逐条 `reverse_edge`（边保留、视图不计）。
- 单表的「作废」= 释放上游未结量；不做红冲补偿边（不需要红字单据）。
- 幂等：重复取消不会二次翻转（`reverse_edge` 自身 replay）。
- 只处理 `quantity_sign='normal'`：红字边是调整事实，取消单据不等于撤销历史调整。

- [ ] **Step 1: 写失败测试**

创建 `meta/tests/test_doc_flow_cancel.py`：

```python
# -*- coding: utf-8 -*-
"""下游取消 → 释放上游占用（release_target_edges）。"""

import contextlib

import pytest

from meta.core.doc_flow_reversal import release_target_edges


class _Cursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.rowcount = 0

    def fetchall(self):
        return self._rows


class _ReversalResult:
    def __init__(self, replay=False):
        self.replay = replay


class FakeDS:
    def __init__(self, edge_rows=None, line_rows=None):
        self._edge_rows = edge_rows or []
        self._line_rows = line_rows or []
        self.sql = []
        self.transactions = 0

    def execute(self, sql, params=()):
        self.sql.append(('execute', sql, tuple(params)))
        return _Cursor(self._edge_rows)

    def query(self, sql, params=()):
        self.sql.append(('query', sql, tuple(params)))
        return self._line_rows

    @contextlib.contextmanager
    def transaction(self):
        self.transactions += 1
        yield


def test_release_requires_target_bo_and_ids():
    assert release_target_edges(FakeDS(), '', ['1']) == {'released': [], 'replay': []}
    assert release_target_edges(FakeDS(), 'shipment_line', []) == \
        {'released': [], 'replay': []}


def test_release_queries_active_normal_edges(monkeypatch):
    calls = []

    def fake_reverse(ds, edge_id, **kwargs):
        calls.append((edge_id, kwargs))
        return _ReversalResult(replay=False)

    monkeypatch.setattr('meta.core.doc_flow_reversal.reverse_edge', fake_reverse)
    ds = FakeDS(edge_rows=[{'id': 'e1'}, {'id': 'e2'}])
    result = release_target_edges(ds, 'shipment_line', [11, 12],
                                  reversed_by='shipment_service.cancel')
    assert result['released'] == ['e1', 'e2']
    assert result['replay'] == []
    assert [call[0] for call in calls] == ['e1', 'e2']
    sql = ds.sql[0][1]
    assert "target_bo" in sql and "status='active'" in sql \
        and "quantity_sign='normal'" in sql


def test_release_collects_replay(monkeypatch):
    monkeypatch.setattr(
        'meta.core.doc_flow_reversal.reverse_edge',
        lambda ds, edge_id, **kw: _ReversalResult(replay=True))
    ds = FakeDS(edge_rows=[{'id': 'e1'}])
    result = release_target_edges(ds, 'receipt_line', [1], reversed_by='test')
    assert result == {'released': [], 'replay': ['e1']}


def test_release_runs_in_one_transaction(monkeypatch):
    monkeypatch.setattr(
        'meta.core.doc_flow_reversal.reverse_edge',
        lambda ds, edge_id, **kw: _ReversalResult(replay=False))
    ds = FakeDS()
    release_target_edges(ds, 'receipt_line', [1], reversed_by='test')
    assert ds.transactions == 1


def test_shipment_cancel_releases_lines(monkeypatch):
    released = []
    monkeypatch.setattr(
        'meta.services.shipment_service.release_target_edges',
        lambda ds, bo, ids, **kw: released.append((bo, list(ids))))
    from meta.services.shipment_service import ShipmentService

    service = ShipmentService(data_source=FakeDS(line_rows=[{'id': 11}, {'id': 12}]))
    monkeypatch.setattr(service, '_require_header',
                        lambda _id: {'id': _id, 'status': 'draft'})
    service.cancel(7)
    assert released == [('shipment_line', [11, 12])]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_cancel.py`
Expected: FAIL —— `ImportError: cannot import name 'release_target_edges'`

- [ ] **Step 3: 实现 `release_target_edges`**

在 `meta/core/doc_flow_reversal.py` 的 `reverse_edge` 函数之后追加：

```python
def release_target_edges(app_ds, target_bo: str, target_ids,
                         *, reversed_by: str = "") -> Dict[str, Any]:
    """下游单据取消/关闭：释放其名下 active normal 边对上游未结量的占用。

    Args:
        app_ds: 应用库 DataSource（边所在库）
        target_bo: 目标 BO id（shipment_line / receipt_line / transfer_order_line）
        target_ids: 目标行 ID 列表
        reversed_by: 执行者（仅日志）

    Returns:
        {"released": [edge_id...], "replay": [edge_id...]}
    """
    ids = [str(value) for value in (target_ids or [])
           if value not in (None, "")]
    if not target_bo or not ids:
        return {"released": [], "replay": []}

    placeholders = ", ".join(["?"] * len(ids))
    rows = app_ds.execute(
        "SELECT id FROM doc_flow_edges WHERE target_bo=?"
        " AND target_id IN ({0}) AND status='active'"
        " AND quantity_sign='normal' ORDER BY id".format(placeholders),
        tuple([target_bo] + ids),
    ).fetchall()

    released: List[str] = []
    replay: List[str] = []
    with app_ds.transaction():
        for (edge_id,) in rows:
            result = reverse_edge(app_ds, edge_id, reversed_by=reversed_by)
            (replay if result.replay else released).append(edge_id)
    logger.info("[doc_flow] release %s/%s released=%s replay=%s by=%s",
                target_bo, ids, len(released), len(replay), reversed_by)
    return {"released": released, "replay": replay}
```

> `Dict` / `List` 已在模块顶部 `typing` 导入中；若缺 `Dict` 则改为 `dict`。

- [ ] **Step 4: 接入交货单 `cancel`**

把 `meta/services/shipment_service.py` 的 `cancel` 改为：

```python
    def cancel(self, delivery_id: Any) -> Dict[str, Any]:
        """draft / released → cancelled（R-DN-2：shipped 之后不可取消）。

        DOC_FLOW：取消即释放该交货行对上游计划行的占用（边保留、视图不计），
        上游未结量随之回升，可再次派生。
        """
        header = self._require_header(delivery_id)
        if header['status'] not in CANCELLABLE_HEADER_STATUSES:
            raise ShipmentError('仅草稿或已释放的交货单可取消',
                                field_name='status', rule='DN_STATE_INVALID')
        now = _now()
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?' % HEADER_TABLE,
                [STATUS_CANCELLED, now, delivery_id])
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE delivery_id = ?' % LINE_TABLE,
                [STATUS_CANCELLED, now, delivery_id])
            line_ids = [row['id'] for row in self.ds.query(
                'SELECT id FROM %s WHERE delivery_id = ?' % LINE_TABLE,
                [delivery_id])]
            release_target_edges(self.ds, 'shipment_line', line_ids,
                                 reversed_by='shipment_service.cancel')
        return {'id': header['id'], 'status': STATUS_CANCELLED}
```

在 `shipment_service.py` 顶部 import 区追加：

```python
from meta.core.doc_flow_reversal import release_target_edges
```

- [ ] **Step 5: 接入收货单 `cancel`**

在 `meta/services/receipt_service.py` 顶部 import 区追加同样的 import，并把 `cancel` 改为：

```python
    def cancel(self, receipt_id: Any) -> Dict[str, Any]:
        header = self._require_header(receipt_id)
        if header['status'] != STATUS_DRAFT:
            raise ReceiptError('仅草稿收货单可取消',
                               field_name='status', rule='RC_STATE_INVALID')
        now = _now()
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?' % HEADER_TABLE,
                [STATUS_CANCELLED, now, receipt_id])
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ?' % LINE_TABLE,
                [STATUS_CANCELLED, now, receipt_id])
            line_ids = [row['id'] for row in self.ds.query(
                'SELECT id FROM %s WHERE receipt_id = ?' % LINE_TABLE,
                [receipt_id])]
            release_target_edges(self.ds, 'receipt_line', line_ids,
                                 reversed_by='receipt_service.cancel')
        return {'id': header['id'], 'status': STATUS_CANCELLED}
```

> 保留原文件里 `STATUS_DRAFT` / `STATUS_CANCELLED` 常量名与既有报错文案；若原实现用的是
> `CANCELLABLE_HEADER_STATUSES` 之类的集合名，保持原判断不变，只把写操作包进事务并追加释放调用。

- [ ] **Step 6: 接入调拨单 `cancel`**

`meta/services/transfer_order_service.py` 的 `cancel` 已有 `with self.ds.transaction():`，
在前置校验之后、`return` 之前追加：

```python
            line_ids = [row['id'] for row in self.ds.query(
                'SELECT id FROM %s WHERE transfer_order_id = ?' % LINE_TABLE,
                [header['id']])]
            release_target_edges(self.ds, 'transfer_order_line', line_ids,
                                 reversed_by='transfer_order_service.cancel')
```

顶部 import 区追加：

```python
from meta.core.doc_flow_reversal import release_target_edges
```

- [ ] **Step 7: 运行测试确认通过**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_cancel.py`
Expected: PASS，`Total: N (P=N, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 8: 回归三个服务的既有用例**

依次执行（`test.py` 单次只接受一个 `--file`）：

```powershell
python d:\filework\test.py --file meta/tests/test_shipment_service.py
python d:\filework\test.py --file meta/tests/test_receipt_service.py
python d:\filework\test.py --file meta/tests/test_transfer_order_service.py
```

Expected: 三条均为 `F=0, E=0, Exit: 0`（若文件名不符，按实际 `meta/tests/` 下对应文件执行）

- [ ] **Step 9: 提交**

```bash
git add meta/core/doc_flow_reversal.py meta/services/shipment_service.py meta/services/receipt_service.py meta/services/transfer_order_service.py meta/tests/test_doc_flow_cancel.py
git commit -m "feat(doc-flow): release upstream consumption when downstream is cancelled"
```

---

## Task 11: 前端服务层 + 选择器 + 派生面板

**Files:**
- Create: `src/services/docFlowService.js`
- Create: `src/components/business/DocFlow/DocFlowSourcePicker.vue`
- Create: `src/components/business/DocFlow/DocFlowDerivePanel.vue`

**UI 约束（必须遵守）：** 按钮用 `AppButton`、弹窗用 `AppModal`；不得使用 `el-button` / `el-dialog`；
颜色只用 CSS 变量（主色 `#ea580c` 走变量）；文案与列名全部来自服务端 `display_fields.label`，前端零业务常量。

- [ ] **Step 1: 写服务层**

创建 `src/services/docFlowService.js`：

```js
import { apiV2 } from '@/utils/httpClient'

/** 规则清单（可按源 / 目标 BO 过滤） */
export async function listRules(params = {}) {
  const resp = await apiV2.get('/doc-flow/rules', { params })
  return resp.data
}

/** 上游实例 + 已生成 + 未结量（分页） */
export async function listSources(ruleId, params = {}) {
  const resp = await apiV2.get('/doc-flow/sources', {
    params: { rule_id: ruleId, ...params },
  })
  return resp.data
}

/** 按上游行批量生成本次下游数量 */
export async function deriveDocuments(payload) {
  const resp = await apiV2.post('/doc-flow/derive', payload)
  return resp.data
}

/** 边追溯（源侧或目标侧二选一） */
export async function listEdges(params = {}) {
  const resp = await apiV2.get('/doc-flow/edges', { params })
  return resp.data
}
```

- [ ] **Step 2: 写选择器组件**

创建 `src/components/business/DocFlow/DocFlowSourcePicker.vue`：

```vue
<template>
  <div class="doc-flow-picker">
    <div class="doc-flow-picker__toolbar">
      <el-checkbox v-model="includeZero" @change="reload">显示未结量为 0 的行</el-checkbox>
      <AppButton variant="secondary" size="small" :loading="loading" @click="reload">刷新</AppButton>
    </div>

    <el-table
      ref="tableRef"
      v-loading="loading"
      :data="rows"
      row-key="row_key"
      max-height="360"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="46" />
      <el-table-column
        v-for="col in columns"
        :key="col.field"
        :label="col.label"
        min-width="140"
      >
        <template #default="{ row }">{{ row.display_values[col.field] || '' }}</template>
      </el-table-column>
      <el-table-column label="数量" width="110">
        <template #default="{ row }">{{ formatQty(row.quantity) }}</template>
      </el-table-column>
      <el-table-column label="已生成" width="110">
        <template #default="{ row }">{{ formatQty(row.consumed_qty) }}</template>
      </el-table-column>
      <el-table-column label="未结" width="110">
        <template #default="{ row }">{{ formatQty(row.open_qty) }}</template>
      </el-table-column>
      <el-table-column label="本次生成" width="150">
        <template #default="{ row }">
          <el-input-number
            v-model="row.derive_qty"
            :min="0"
            :max="row.open_qty"
            :precision="4"
            :step="1"
            size="small"
            controls-position="right"
          />
        </template>
      </el-table-column>
    </el-table>

    <div class="doc-flow-picker__pager">
      <el-pagination
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import { listRules, listSources } from '@/services/docFlowService'

const props = defineProps({
  ruleId: { type: String, required: true },
  preselectedIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['change'])

const tableRef = ref(null)
const loading = ref(false)
const rows = ref([])
const columns = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const includeZero = ref(false)

function formatQty(value) {
  const num = Number(value || 0)
  return Number.isInteger(num) ? String(num) : num.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

function rowKey(sourceId, sourceItem) {
  return `${sourceId}::${sourceItem || ''}`
}

function onSelectionChange(selection) {
  emit('change', selection.filter((row) => Number(row.derive_qty) > 0))
}

function onPageChange(next) {
  page.value = next
  reload()
}

async function loadColumns() {
  const data = await listRules({})
  const rule = (data.rules || []).find((item) => item.rule_id === props.ruleId)
  // `source_columns` 由服务端把 display_fields 解析成 {field, label}；前端不猜标签
  columns.value = rule?.source_columns || []
}

async function reload() {
  loading.value = true
  try {
    const data = await listSources(props.ruleId, {
      page: page.value,
      page_size: pageSize.value,
      include_zero_open: includeZero.value,
    })
    rows.value = (data.items || []).map((row) => ({
      ...row,
      row_key: rowKey(row.source_id, row.source_item),
      derive_qty: Number(row.open_qty || 0),
    }))
    total.value = Number(data.total || 0)
    await nextTick()
    const wanted = (props.preselectedIds || []).map(String)
    wanted.forEach((id) => {
      const target = rows.value.find((row) => String(row.source_id) === id)
      if (target && tableRef.value) tableRef.value.toggleRowSelection(target, true)
    })
    emit('change', rows.value.filter((row) => wanted.includes(String(row.source_id))))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadColumns()
  await reload()
})
</script>

<style scoped>
.doc-flow-picker__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.doc-flow-picker__pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
```

- [ ] **Step 3: 写派生面板**

创建 `src/components/business/DocFlow/DocFlowDerivePanel.vue`：

```vue
<template>
  <AppModal v-model="visible" :title="title" width="1000px">
    <div v-if="result" class="doc-flow-panel__result">
      <p>已生成边 {{ result.total_edges }} 条；新单据 {{ result.created.length }} 条。</p>
      <el-table :data="result.created" size="small" max-height="240">
        <el-table-column label="源行" prop="source_item" width="120" />
        <el-table-column label="下游单据" prop="target_id" width="180" />
        <el-table-column label="下游行" prop="target_item" width="180" />
        <el-table-column label="数量" prop="quantity" width="110" />
      </el-table>
    </div>

    <DocFlowSourcePicker
      v-else
      :rule-id="ruleId"
      :preselected-ids="preselectedIds"
      @change="onPick"
    />

    <template #footer>
      <AppButton variant="secondary" @click="close">{{ result ? '关闭' : '取消' }}</AppButton>
      <AppButton
        v-if="!result"
        variant="primary"
        :loading="submitting"
        :disabled="picked.length === 0"
        @click="submit"
      >
        生成下游
      </AppButton>
    </template>
  </AppModal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import AppModal from '@/components/common/AppModal/AppModal.vue'
import { deriveDocuments } from '@/services/docFlowService'
import DocFlowSourcePicker from './DocFlowSourcePicker.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  ruleId: { type: String, required: true },
  ruleLabel: { type: String, default: '' },
  preselectedIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'done'])

const submitting = ref(false)
const picked = ref([])
const result = ref(null)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
const title = computed(() => props.ruleLabel || '生成本次下游数量')

watch(() => props.modelValue, (open) => {
  if (open) {
    result.value = null
    picked.value = []
  }
})

function onPick(rows) {
  picked.value = rows
}

async function submit() {
  if (picked.value.length === 0) return
  submitting.value = true
  try {
    const data = await deriveDocuments({
      rule_id: props.ruleId,
      target: { mode: 'create' },
      sources: picked.value.map((row) => ({
        source_id: row.source_id,
        source_item: row.source_item || '',
        quantity: Number(row.derive_qty || 0),
      })),
    })
    result.value = data
    emit('done', data)
  } finally {
    submitting.value = false
  }
}

function close() {
  visible.value = false
}
</script>

<style scoped>
.doc-flow-panel__result {
  padding: 4px 0 12px;
}
</style>
```

- [ ] **Step 4: 构建与静态检查**

```powershell
npm run lint
npm run build
```

Expected: 两条命令均退出码 0；无 `AppButton` / `AppModal` 未解析告警、无未使用变量错误。

- [ ] **Step 5: 提交**

```bash
git add src/services/docFlowService.js src/components/business/DocFlow/DocFlowSourcePicker.vue src/components/business/DocFlow/DocFlowDerivePanel.vue
git commit -m "feat(doc-flow): add source picker and derive panel"
```

---

## Task 12: 追溯面板与两个入口接线

**Files:**
- Create: `src/components/business/DocFlow/DocFlowTracePanel.vue`
- Modify: `src/components/common/MetaListPage/MetaListPage.vue:65-88`（批量按钮渲染）、`:1786-1800`（`onBatchAction`）、props 区
- Modify: `src/views/GenericObjectList.vue`（批量入口）
- Modify: `src/components/common/DetailPage/DetailPage.vue:66-75` 与 `:145-155`（两处 section 注入）

- [ ] **Step 1: 写追溯面板**

创建 `src/components/business/DocFlow/DocFlowTracePanel.vue`：

```vue
<template>
  <div class="doc-flow-trace">
    <h4 class="doc-flow-trace__title">上游来源</h4>
    <el-table v-loading="loading" :data="upstream" size="small" max-height="220">
      <el-table-column label="源单据" prop="source_bo" width="200" />
      <el-table-column label="源行" prop="source_item" width="160" />
      <el-table-column label="数量" prop="quantity" width="110" />
      <el-table-column label="规则" prop="rule_id" width="200" />
      <el-table-column label="状态" prop="status" width="100" />
    </el-table>

    <h4 class="doc-flow-trace__title">下游去向</h4>
    <el-table v-loading="loading" :data="downstream" size="small" max-height="220">
      <el-table-column label="目标单据" prop="target_bo" width="200" />
      <el-table-column label="目标行" prop="target_item" width="160" />
      <el-table-column label="数量" prop="quantity" width="110" />
      <el-table-column label="规则" prop="rule_id" width="200" />
      <el-table-column label="状态" prop="status" width="100" />
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { listEdges } from '@/services/docFlowService'

const props = defineProps({
  objectType: { type: String, required: true },
  recordId: { type: [String, Number], required: true },
})

const loading = ref(false)
const upstream = ref([])
const downstream = ref([])

async function reload() {
  if (!props.recordId) {
    upstream.value = []
    downstream.value = []
    return
  }
  loading.value = true
  try {
    const incoming = await listEdges({ target_bo: props.objectType, target_id: props.recordId })
    upstream.value = incoming.edges || []
    const outgoing = await listEdges({ source_bo: props.objectType, source_id: props.recordId })
    downstream.value = outgoing.edges || []
  } finally {
    loading.value = false
  }
}

onMounted(reload)
watch(() => [props.objectType, props.recordId], reload)
</script>

<style scoped>
.doc-flow-trace__title {
  margin: 12px 0 8px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
</style>
```

- [ ] **Step 2: `MetaListPage` 支持外部批量动作**

a) props 区追加：

```js
  extraBatchActions: { type: Array, default: () => [] },
```

b) `computed` 区追加：

```js
const visibleBatchActions = computed(() => [
  ...(batchActions.value || []),
  ...(props.extraBatchActions || []),
])
```

c) 模板 L65 与 L81 改为：

```vue
          <template v-if="visibleBatchActions.length > 0 && totalSelectedCount > 0 && !hideToolbar">
```

```vue
              v-for="action in visibleBatchActions"
```

d) `onBatchAction` 开头追加早退分支（`batch-action` 已 emit，父组件负责打开面板）：

```js
  if (action.key === 'doc_flow_derive') return
```

- [ ] **Step 3: `GenericObjectList` 接线批量入口**

在 `src/views/GenericObjectList.vue` 的 `<script setup>` 中追加（`props` / `metaListRef` 已存在）。
先把第 20 行的 `import { ref, computed } from 'vue'` 改为：

```js
import { ref, computed, onMounted } from 'vue'
```

再追加以下 import 与代码（**不要**重复 import `ref` / `computed`）：

```js
import { listRules } from '@/services/docFlowService'
import DocFlowDerivePanel from '@/components/business/DocFlow/DocFlowDerivePanel.vue'

const docFlowRules = ref([])
const deriveVisible = ref(false)
const deriveRuleId = ref('')
const deriveRuleLabel = ref('')
const derivePreselected = ref([])

const docFlowRule = computed(
  () => docFlowRules.value.find((rule) => rule.source_bo === props.objectType) || null,
)

const extraBatchActions = computed(() => (
  docFlowRule.value
    ? [{ key: 'doc_flow_derive', label: '生成下游单据', variant: 'primary' }]
    : []
))

async function loadDocFlowRules() {
  try {
    const data = await listRules({})
    docFlowRules.value = data.rules || []
  } catch (error) {
    docFlowRules.value = []
  }
}

function openDerivePanel(ids) {
  if (!docFlowRule.value) return
  deriveRuleId.value = docFlowRule.value.rule_id
  deriveRuleLabel.value = '生成下游单据'
  derivePreselected.value = ids || []
  deriveVisible.value = true
}

function handleBatchAction(payload) {
  if (payload?.action?.key === 'doc_flow_derive') {
    openDerivePanel(payload.ids || [])
  }
}

function refreshList() {
  metaListRef.value?.refresh?.()
}

onMounted(loadDocFlowRules)
```

模板中给 `MetaListPage` 增加两个绑定：

```vue
      :extra-batch-actions="extraBatchActions"
      @batch-action="handleBatchAction"
```

在 `</MetaListPage>` 之后、`</div>` 之前追加：

```vue
    <DocFlowDerivePanel
      v-if="docFlowRule"
      v-model="deriveVisible"
      :rule-id="deriveRuleId"
      :rule-label="deriveRuleLabel"
      :preselected-ids="derivePreselected"
      @done="refreshList"
    />
```

- [ ] **Step 4: `DetailPage` 注入追溯面板（两处）**

`src/components/common/DetailPage/DetailPage.vue` 顶部 import 区追加：

```js
import DocFlowTracePanel from '@/components/business/DocFlow/DocFlowTracePanel.vue'
import { listRules } from '@/services/docFlowService'
```

`<script setup>` 内（`objectType` / `id` 已存在）追加：

```js
const docFlowRules = ref([])

const docFlowMatched = computed(() => docFlowRules.value.some(
  (rule) => rule.source_bo === objectType.value || rule.target_bo === objectType.value,
))

async function loadDocFlowRules() {
  try {
    const data = await listRules({})
    docFlowRules.value = data.rules || []
  } catch (error) {
    docFlowRules.value = []
  }
}

onMounted(loadDocFlowRules)
```

> 若文件未引入 `ref` / `computed` / `onMounted`，合并进其现有 `vue` 导入行，不要新建重复导入。

在两处 `</ObjectPage>` 之后各追加同一块（drawer 约 L76、standalone 约 L160）：

```vue
        <div v-if="docFlowMatched" class="dp-doc-flow">
          <h4 class="dp-doc-flow__title">单据流追溯</h4>
          <DocFlowTracePanel :object-type="objectType" :record-id="id" />
        </div>
```

样式区追加：

```css
.dp-doc-flow {
  margin-top: 16px;
  padding: 12px;
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
}
.dp-doc-flow__title {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
```

> 采用「平台级面板」而非 `detail.facets` 声明：追溯是平台通用能力（任何参与单据流的
> BO 都成立），不应要求每个 BO 的 YAML 重复声明。面板仅在规则命中时才渲染，符合
> 元数据驱动（规则来自服务端，前端零业务常量）。此点已记入「已知偏差」。

- [ ] **Step 5: 构建与静态检查**

```powershell
npm run lint
npm run build
```

Expected: 均退出码 0；Vue 模板无 `visibleBatchActions` / `DocFlowDerivePanel` 未定义错误。

- [ ] **Step 6: 手工验证（服务已启动时）**

Run: `python d:\filework\test.py --file meta/tests/test_doc_flow_api.py`
Expected: PASS；随后在浏览器按以下路径核对：
1. 交货单列表 → 勾选 2 行 →「生成下游单据」→ 面板显示未结量、可改本次数量 → 生成成功提示。
2. 交货单详情 → `doc_flow_trace` section 显示上游计划行与下游库存事务。

- [ ] **Step 7: 提交**

```bash
git add src/components/business/DocFlow/DocFlowTracePanel.vue src/components/common/MetaListPage/MetaListPage.vue src/views/GenericObjectList.vue src/components/common/DetailPage/DetailPage.vue
git commit -m "feat(doc-flow): wire trace panel and batch derive entry"
```

---

## Task 13: 全量回归

**Files:** 无新增

- [ ] **Step 1: 跑本轮新增/修改的全部后端用例**

依次执行：

```powershell
python d:\filework\test.py --file meta/tests/test_doc_flow_service.py
python d:\filework\test.py --file meta/tests/test_doc_flow_api.py
python d:\filework\test.py --file meta/tests/test_doc_flow_cancel.py
python d:\filework\test.py --file meta/tests/test_doc_flow_batch.py
python d:\filework\test.py --file meta/tests/test_doc_flow_derive_engine.py
```

Expected: 每条均 `Total: N (P=N, F=0, E=0, S=0) Exit: 0`

- [ ] **Step 2: 全量（允许并发假失败）**

Run: `python d:\filework\test.py --all`
Expected: 无真实 FAIL；若出现 FAIL，记录用例名。

- [ ] **Step 3: 串行确认**

Run: `python d:\filework\test.py --failed`
Expected: `Total: N (P=N, F=0, E=0, S=0) Exit: 0`（并发假失败在此消失）

- [ ] **Step 4: 提交**

```bash
git add -A meta/ src/
git commit -m "test(doc-flow): full regression pass for document flow service"
```

---

## 已知偏差（实施时必须遵守，勿自行扩权）

| # | 偏差 | 原因 | 处置 |
|---|---|---|---|
| D-1 | 只做 `@login_required`，不做 RBAC 403 | 本轮无权限模型改造预算 | 后续单独 Spec |
| D-2 | `target.mode='append'` 仅头行模式可用；单表模式返回 `DOC_FLOW_TARGET_MODE_INVALID` | 引擎不支持向既有目标行合并数量 | 前端暂不暴露 append 入口 |
| D-3 | `display_fields` 需规则声明显式补齐，缺省回退 `[id_field, qty_field]` | 源 BO 字段千差万别，无法自动猜 | Task 1 已实现回退 |
| D-4 | 新增错误码 `DOC_FLOW_RULE_INVALID` / `DOC_FLOW_DUPLICATE_SOURCE` / `DOC_FLOW_EDGE_FILTER_REQUIRED` | Spec §错误码表未覆盖入参层 | 回写 Spec 时补表 |
| D-5 | 上游选择器用自建 `el-table`，不复用 `SearchHelpDialog` | 后者无法渲染 `open_qty / consumed_qty` 列 | 保持自建，列名仍来自元数据 |
| D-6 | `DocFlowTracePanel` 只读 | 追溯写操作会绕过引擎唯一写入口 | 追加走 derive |
| D-7 | 取消释放只处理 `quantity_sign='normal'` | 红字边是调整事实，非单据占用 | 见 Task 10 docstring |
| D-8 | 详情页追溯用「平台级面板」而非 `detail.facets` 声明 | 追溯对任何参与单据流的 BO 都成立，逐 BO 声明是重复元数据 | 面板仅在规则命中时渲染 |

---

## Self-Review

**1. Spec 覆盖核对**

| Spec 章节 | 落点 |
|---|---|
| §3 边表与索引 | Part 1 Task 1-3、Task 8 |
| §4 规则元数据（含 display_fields） | Task 1 |
| §5 未结量 / 消耗视图 | Task 5 |
| §6 派生与幂等 | Task 2、Task 3、Task 6 |
| §7 红冲 / 取消语义 | Task 10 |
| §8 取消释放上游 | Task 10 |
| §9 服务层 API | Task 4-7 |
| §10 HTTP 契约 | Task 9 |
| §11 前端组件 | Task 11-12 |
| §12 验收 | Task 13 |

**2. 占位符扫描**：未出现 TBD / TODO / “类似 Task N”；每个改代码的步骤均给出完整代码块。

**3. 类型一致性核对**

- `DocFlowService` 方法签名与 API 调用一致：`list_rules(source_bo, target_bo)`、`list_sources(rule_id, filters, include_zero_open, page, page_size, source_item)`、`derive(payload, derived_by)`、`list_edges(...)`。
- `derive` 请求体键名统一为 `rule_id / target{mode,id,data} / sources[{source_id, source_item, quantity}]`，前端 `DocFlowDerivePanel` 与 API `_derive_view` 完全对齐。
- `DeriveResult` 字段（Task 3 扩展后）`source_id / source_item / target_id / target_item / quantity` 与 `_derive_view` 读取字段一致。
- 取消释放目标 BO 名与三条服务的实际行表一致：`shipment_line` / `receipt_line` / `transfer_order_line`。
- 前端服务函数名 `listRules / listSources / deriveDocuments / listEdges` 在 Task 11 定义、Task 12 使用，无错名。