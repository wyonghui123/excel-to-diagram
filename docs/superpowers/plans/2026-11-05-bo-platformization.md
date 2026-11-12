# BO 平台化改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把散落在业务服务与 guard 拦截器里的生命周期、逆向、承诺、取号、组织解析、行语义、追溯七类逻辑，收敛到平台唯一入口，使新增单据只需声明元数据。

**Architecture:** 不新建平行引擎。生命周期复用 `MetaStateTransition` + `StateTransitionExecutor`；逆向复用 `doc_flow_reversal` 的 A/B/C 三档；承诺以 `inventory_reservations` 为唯一事实源，新增 `CommitmentService` 作为平台入口；取号收敛到 `DocumentNumberService`。业务对象只登记策略/规则，不写编排代码。

**Tech Stack:** Python 3.11 + Flask + SQLite；`MetaObject`/YAML 元模型；`meta/core/interceptors` 拦截器链；测试唯一入口 `python d:\filework\test.py`（禁止 pytest）。

---

## 现状基线（本计划的事实依据）

- 212 个 BO schema，101 个使用 `aspects`，56 个声明 `parent_object`，仅 3 个声明状态机规则。
- 61 个拦截器文件，其中约 35 个是对象/域的 guard，状态迁移与关单校验各自硬编码。
- 平台已有 `MetaStateTransition`（`meta/core/models.py`）、`StateTransitionExecutor`（`meta/core/rule_executor.py`）、`StateTransitionSideEffect`、状态迁移 API。
- 平台已有 `doc_flow_reversal`：`reverse_edge`（A 全冲销）、`counter_edge`（B 部分冲销）、`red_ink_edge`（C 红字调整），均幂等。
- 平台已有 `NumberSequenceEngine`，但 5 处业务服务自行取号。
- 承诺层刚落地 `RowDemandPolicy`（服务请求），仍埋在 `InventoryReservationService`。

## 架构决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 生命周期不新建 engine，改用 schema `rules: type=state_transition` | 平台已有执行器、side_effects、preconditions、权限联动，缺的只是“没人用” |
| D2 | 逆向不新建冲销逻辑，新增薄编排层 `ReversalOrchestrator` | `doc_flow_reversal` 已是唯一冲销权威，业务层只需给出档位与承诺策略 |
| D3 | 承诺层保留 `inventory_reservations` 事实源，上移策略与入口 | 事实源与编排分离，避免每类单据复制一套 |
| D4 | 取号收敛为 `DocumentNumberService`，写管线唯一调用 | 编号规则（类型→序列→模式）只应存在一处 |
| D5 | 组织/行/追溯先抽服务、单对象试点，不一次性改 35 个 guard | 控制回归面；每步可独立回滚 |

## 文件结构

**新建**

| 文件 | 职责 |
|---|---|
| `meta/core/reversal_profiles.py` | 单据类型 → 冲销档位（A/B/C）+ 承诺处理策略 |
| `meta/core/reversal_orchestrator.py` | `reverse_document()` 统一入口，调 doc_flow + 承诺钩子 |
| `meta/services/commitment_service.py` | 承诺平台入口：sync / release / fulfill / assert_closable |
| `meta/services/commitment_policies.py` | 行式需求策略注册表（从 reservation service 迁入并扩展） |
| `meta/services/document_number_service.py` | 取号唯一入口 |
| `meta/services/org_context_resolver.py` | 组织/库位/项目/任务解析与兜底 |
| `meta/core/interceptors/line_guard_interceptor.py` | 行号唯一、父子归属、行数量校验 |
| `meta/services/trace_link_service.py` | 序列号 / HU / 单据流链接统一写入 |

**修改**

| 文件 | 改动 |
|---|---|
| `meta/schemas/service_request.yaml` | 增加 `rules: state_transition`（试点对象） |
| `meta/services/demand_entry_service.py` | 状态迁移改走执行器；删除状态硬编码 |
| `meta/core/interceptors/demand_entry_guard_interceptor.py` | 只保留业务校验，状态迁移交给规则 |
| `meta/services/receipt_service.py` | 逆向走编排层；履约改调 `CommitmentService` |
| `meta/services/inventory_reservation_service.py` | 策略迁出，保留低层原语 |
| `meta/api/bo_api.py` | `_allocate_document_no` 改调 `DocumentNumberService` |
| `meta/services/transfer_order_service.py` / `transfer_shipment_service.py` / `requisition_po_conversion.py` | 删除各自取号实现 |
| `meta/core/app_builder.py` | 注册 `LineGuardInterceptor`、`CommitmentFulfillmentHook` |

> 说明：本计划不新增表、不新增迁移。所有能力都落在现有表与元数据上。

## 测试夹具约定

- 数据库替身统一用 `meta.tests.inventory_test_doubles`：`MemDS(build_db())`，需要基础主数据时先 `seed(...)`，与 `meta/tests/test_inventory_reservation_service.py` 完全一致。
- 不在测试里另造 FakeDS；需要额外表时，在测试内用 `CREATE TABLE` 补齐，或复用目标测试文件已有的 `_CORE_DDL`。
- 运行命令统一为 `python d:\filework\test.py --single <相对路径>`；禁止 `pytest` / `python -m pytest`。
- 计划中的 `_ds()` 一律指 `MemDS(build_db())`（或目标测试文件已有的同名夹具）。

---

## Phase 0：准备与基线

### Task 0: 建立隔离工作树与基线

**Files:** 无代码改动。

- [ ] **Step 1: 建工作树**

Run:
```powershell
powershell -File scripts/agent_bootstrap.ps1 -AgentName platform-infra -Port 3012
```
Expected: 输出 worktree 路径 `../platform-infra-worktree/`，分支 `agent/platform-infra`。

- [ ] **Step 2: 记录基线测试结果**

Run（在 worktree 内）:
```powershell
python d:\filework\test.py --single meta/tests/test_inventory_reservation_service.py
python d:\filework\test.py --single meta/tests/test_demand_entry_m1.py
python d:\filework\test.py --single meta/tests/test_rule_engine.py
python d:\filework\test.py --single meta/tests/test_engineering_change.py
```
Expected: 全部 `passed`；把数字记入 `docs/superpowers/plans/2026-11-05-bo-platformization.md` 末尾的“执行记录”。

- [ ] **Step 3: 确认无脏文件**

Run: `git status --short`
Expected: 只有本工作树自己的文件；若发现其他会话改动，不 stash、不提交。

---

## Phase 1：生命周期平台化（P0，试点 service_request）

### Task 1.1: 在 schema 声明状态迁移规则

**Files:**
- Modify: `meta/schemas/service_request.yaml`（`rules:` 段，位于文件末尾 `indexes:` 之前）
- Test: `meta/tests/test_service_request_lifecycle_rules.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
import yaml
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / 'schemas' / 'service_request.yaml'


def _rules():
    data = yaml.safe_load(SCHEMA.read_text(encoding='utf-8'))
    return [r for r in data.get('rules', [])
            if r.get('type') == 'state_transition']


def test_service_request_declares_submit_and_cancel():
    pairs = {(tuple(r['from_states']), r['to_state']) for r in _rules()}
    assert (('draft',), 'submitted') in pairs
    assert (('draft', 'submitted'), 'cancelled') in pairs
    assert (('submitted',), 'approved') in pairs
    assert (('submitted', 'approved'), 'rejected') in pairs
    assert (('approved',), 'completed') in pairs


def test_every_rule_has_action_ref_and_state_field():
    for rule in _rules():
        assert rule['state_field'] == 'status'
        assert rule.get('action_ref'), rule['id']
        assert rule.get('triggers') == ['before_update']
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_service_request_lifecycle_rules.py`
Expected: FAIL（`pairs` 为空或缺少条目）。

- [ ] **Step 3: 写 schema 规则**

在 `meta/schemas/service_request.yaml` 的 `rules:` 段加入（若已有 `rules:` 则追加同级条目）：

```yaml
rules:
  - id: submit_service_request
    name: 提交服务请求
    type: state_transition
    action_ref: submit
    state_field: status
    from_states: [draft]
    to_state: submitted
    triggers: [before_update]

  - id: approve_service_request
    name: 批准服务请求
    type: state_transition
    action_ref: approve
    state_field: status
    from_states: [submitted]
    to_state: approved
    triggers: [before_update]

  - id: reject_service_request
    name: 驳回服务请求
    type: state_transition
    action_ref: reject
    state_field: status
    from_states: [submitted, approved]
    to_state: rejected
    triggers: [before_update]

  - id: complete_service_request
    name: 完成服务请求
    type: state_transition
    action_ref: complete
    state_field: status
    from_states: [approved]
    to_state: completed
    triggers: [before_update]

  - id: close_service_request
    name: 关闭服务请求
    type: state_transition
    action_ref: close
    state_field: status
    from_states: [submitted, approved, completed]
    to_state: closed
    triggers: [before_update]

  - id: cancel_service_request
    name: 取消服务请求
    type: state_transition
    action_ref: cancel
    state_field: status
    from_states: [draft, submitted, approved]
    to_state: cancelled
    triggers: [before_update]
```

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --single meta/tests/test_service_request_lifecycle_rules.py`
Expected: `2 passed`。

- [ ] **Step 5: 提交**

```powershell
git add meta/schemas/service_request.yaml meta/tests/test_service_request_lifecycle_rules.py
git commit -m "feat(platform): service_request 声明状态迁移规则"
```

### Task 1.2: 服务层提交/审批动作改走执行器

**Files:**
- Modify: `meta/services/demand_entry_service.py`
- Test: `meta/tests/test_service_request_lifecycle_rules.py`

- [ ] **Step 1: 写失败测试**

```python
from meta.core.models import FieldType, MetaField, MetaObject, MetaStateTransition
from meta.core.rule_executor import RuleContext, StateTransitionExecutor


def _meta_object():
    return MetaObject(
        id='service_request', name='服务请求', table_name='service_requests',
        fields=[MetaField(id='status', name='状态',
                          field_type=FieldType.STRING,
                          db_column='status')])


def _submit_rule():
    return MetaStateTransition(
        id='submit_service_request', name='提交服务请求',
        state_field='status', from_states=['draft'],
        to_state='submitted', triggers=['before_update'])


def test_submit_rule_transitions_draft_only():
    data = {'status': 'draft'}
    result = StateTransitionExecutor().execute(
        _submit_rule(), RuleContext(meta_object=_meta_object(), data=data))
    assert result.success and data['status'] == 'submitted'


def test_submit_rule_skips_non_draft():
    data = {'status': 'approved'}
    result = StateTransitionExecutor().execute(
        _submit_rule(), RuleContext(meta_object=_meta_object(), data=data))
    assert result.success and data['status'] == 'approved'
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_service_request_lifecycle_rules.py`
Expected: ImportError 或规则行为不符（`MetaField` 缺 `field_type` 时按实际构造签名补参）。

- [ ] **Step 3: 在服务中接入执行器**

在 `DemandEntryService` 新增：

```python
def apply_status_transition(self, object_type, record, to_status):
    """按对象 schema 的 state_transition 规则做状态迁移；无规则则拒绝。"""
    from meta.core.app_registry import get_registry
    from meta.core.rule_executor import RuleContext, StateTransitionExecutor
    from meta.core.models import MetaStateTransition

    meta_obj = get_registry().get_object(object_type)
    rules = [r for r in (meta_obj.rules or [])
             if isinstance(r, MetaStateTransition)
             and r.state_field == 'status']
    if not rules:
        raise ValueError('对象未声明状态迁移规则: %s' % object_type)
    data = dict(record)
    data['status'] = to_status
    executor = StateTransitionExecutor()
    context = RuleContext(meta_object=meta_obj, data=data)
    for rule in rules:
        executor.execute(rule, context)
    if data.get('status') != to_status:
        raise ValueError('非法状态迁移: %s → %s' % (record.get('status'), to_status))
    return data['status']
```

> 若 `get_registry()` 实际函数名不同，以 `meta/core/app_registry.py` 现有入口为准；不得新增第二份 registry。

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --single meta/tests/test_service_request_lifecycle_rules.py`
Expected: `4 passed`。

- [ ] **Step 5: 提交**

```powershell
git add meta/services/demand_entry_service.py meta/tests/test_service_request_lifecycle_rules.py
git commit -m "feat(platform): 服务请求状态迁移走平台执行器"
```

### Task 1.3: 收敛 demand_entry guard 的状态硬编码

**Files:**
- Modify: `meta/core/interceptors/demand_entry_guard_interceptor.py`
- Test: `meta/tests/test_demand_entry_m1.py`

- [ ] **Step 1: 写失败测试**

在 `test_demand_entry_m1.py` 增加：

```python
def test_submit_rejects_illegal_transition():
    """approved → submitted 必须被拒，错误码 STATE_MACHINE_VIOLATION。"""
    response = _post('/api/service_requests/1/actions/submit', {})
    assert response.status_code == 400
    assert response.get_json()['error'] == 'STATE_MACHINE_VIOLATION'
```

（`_post` 用该文件现有请求辅助函数；若名称不同，沿用同文件模式。）

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_demand_entry_m1.py`
Expected: 失败（当前返回 200 或不同错误码）。

- [ ] **Step 3: 删除 guard 里的状态分支**

把 `demand_entry_guard_interceptor.py` 中“按 object_type 写死允许的状态迁移”分支删除，改为调用 `DemandEntryService.apply_status_transition`；保留行级必填、审批策略、预留同步等业务校验。异常映射为 `STATE_MACHINE_VIOLATION`（400）。

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --single meta/tests/test_demand_entry_m1.py`
Expected: 原有用例 + 新用例全部通过。

- [ ] **Step 5: 提交**

```powershell
git add meta/core/interceptors/demand_entry_guard_interceptor.py meta/tests/test_demand_entry_m1.py
git commit -m "refactor(platform): demand_entry 状态迁移去硬编码"
```

### Task 1.4: 推广到 shipment / receipt / work_order（分批）

**Files:**
- Modify: `meta/schemas/shipment.yaml`、`meta/schemas/receipt.yaml`、`meta/schemas/work_order.yaml`
- Test: `meta/tests/test_lifecycle_rule_coverage.py`（新建）

- [ ] **Step 1: 写覆盖测试**

```python
import yaml
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[1] / 'schemas'
DOCS = ['service_request', 'shipment', 'receipt', 'work_order']


def test_document_heads_declare_state_transitions():
    for name in DOCS:
        data = yaml.safe_load((SCHEMAS / ('%s.yaml' % name)).read_text(encoding='utf-8'))
        rules = [r for r in data.get('rules', []) if r.get('type') == 'state_transition']
        assert rules, '%s 未声明状态迁移规则' % name
        for rule in rules:
            assert rule['state_field'] == 'status'
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_lifecycle_rule_coverage.py`
Expected: FAIL（shipment/receipt/work_order 缺规则）。

- [ ] **Step 3: 按对象现有状态枚举补规则**

逐对象读现有 `status` 枚举与 guard 的迁移条件，把“允许迁移”写入 `rules`（不改业务判据）；每完成一个对象跑该对象的现有测试文件。禁止凭空发明状态值。

- [ ] **Step 4: 运行确认通过**

Run:
```powershell
python d:\filework\test.py --single meta/tests/test_lifecycle_rule_coverage.py
python d:\filework\test.py --single meta/tests/test_shipment_flow.py
python d:\filework\test.py --single meta/tests/test_receipt_service.py
```
Expected: 全部通过；新增覆盖测试 `6 passed`。

- [ ] **Step 5: 提交**

```powershell
git add meta/schemas/shipment.yaml meta/schemas/receipt.yaml meta/schemas/work_order.yaml meta/tests/test_lifecycle_rule_coverage.py
git commit -m "feat(platform): 单据头声明状态迁移规则"
```

---

## Phase 2：逆向/取消编排（P0，试点 receipt）

### Task 2.1: 定义冲销档位策略

**Files:**
- Create: `meta/core/reversal_profiles.py`
- Test: `meta/tests/test_reversal_profiles.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
from meta.core.reversal_profiles import get_profile

def test_receipt_profile_is_red_ink_and_no_commitment_revert():
    p = get_profile('receipt')
    assert p['mode'] == 'red_ink'          # 数量调整，原单保留
    assert p['commitment'] == 'no_revert'  # 已发生投料不回退
    assert p['close_guard'] is True

def test_unknown_document_raises():
    import pytest
    with pytest.raises(KeyError):
        get_profile('no_such_doc')
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_reversal_profiles.py`
Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现策略表**

```python
REVERSAL_PROFILES = {
    'receipt': {
        'mode': 'red_ink',          # A=reverse_edge / B=counter_edge / C=red_ink_edge
        'commitment': 'no_revert',
        'close_guard': True,
        'reason_required': True,
    },
    'shipment': {
        'mode': 'counter',
        'commitment': 'release_remaining',
        'close_guard': True,
        'reason_required': True,
    },
    'transfer_shipment': {
        'mode': 'counter',
        'commitment': 'release_remaining',
        'close_guard': True,
        'reason_required': True,
    },
}

def get_profile(document_type):
    return REVERSAL_PROFILES[document_type]
```

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --single meta/tests/test_reversal_profiles.py`
Expected: `2 passed`。

- [ ] **Step 5: 提交**

```powershell
git add meta/core/reversal_profiles.py meta/tests/test_reversal_profiles.py
git commit -m "feat(platform): 冲销档位策略表"
```

### Task 2.2: 统一冲销入口

**Files:**
- Create: `meta/core/reversal_orchestrator.py`
- Test: `meta/tests/test_reversal_orchestrator.py`（新建）

- [ ] **Step 1: 写失败测试（纯分派）**

```python
from meta.core.reversal_orchestrator import resolve_mode

def test_resolve_mode_uses_profile():
    assert resolve_mode('receipt') == 'red_ink'
    assert resolve_mode('shipment') == 'counter'
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_reversal_orchestrator.py`
Expected: ImportError。

- [ ] **Step 3: 实现编排层**

```python
from meta.core.doc_flow_reversal import counter_edge, red_ink_edge, reverse_edge
from meta.core.reversal_profiles import get_profile


def resolve_mode(document_type):
    return get_profile(document_type)['mode']


def reverse_document(app_ds, platform_ds, document_type, *, edge_id,
                     reason, ref_id, quantity=None, return_rule_id=None,
                     target_data=None):
    """业务单据冲销统一入口；档位由 profile 决定，承诺处理由调用方钩子承担。"""
    profile = get_profile(document_type)
    if profile['reason_required'] and not reason:
        raise ValueError('冲销原因必填')
    if profile['mode'] == 'full':
        return reverse_edge(app_ds, edge_id, reversed_by=reason)
    if profile['mode'] == 'counter':
        return counter_edge(app_ds, platform_ds, edge_id,
                            return_rule_id=return_rule_id,
                            quantity=quantity, ref_id=ref_id,
                            target_data=target_data, derived_by=reason)
    return red_ink_edge(app_ds, edge_id, quantity=quantity,
                        ref_id=ref_id, derived_by=reason)
```

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --single meta/tests/test_reversal_orchestrator.py`
Expected: `1 passed`。

- [ ] **Step 5: 提交**

```powershell
git add meta/core/reversal_orchestrator.py meta/tests/test_reversal_orchestrator.py
git commit -m "feat(platform): 冲销编排统一入口"
```

### Task 2.3: receipt 逆向接入编排层

**Files:**
- Modify: `meta/services/receipt_service.py`
- Test: `meta/tests/test_serial_completion_genealogy.py`、`meta/tests/test_receipt_service.py`

- [ ] **Step 1: 写失败测试**

在 `test_receipt_service.py` 增加：

```python
def test_reversal_uses_orchestrator_and_keeps_component_commitment():
    receipt = _posted_receipt()
    before = _outstanding('work_order', receipt['work_order_id'])
    _reverse_receipt(receipt['id'], reason='供应商错发')
    after = _outstanding('work_order', receipt['work_order_id'])
    assert after == before  # 只进不退
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_receipt_service.py`
Expected: 失败或辅助函数不存在（按现有 fixture 改名）。

- [ ] **Step 3: 替换手写红冲**

把 `receipt_service` 中自己拼红字单/负向边的代码改为调用 `reverse_document(... mode='red_ink')`；保留过账、HU、序列号与结算逻辑；承诺处理保持 `no_revert`，并在注释中写明“红冲不回退组件核销”。

- [ ] **Step 4: 运行确认通过**

Run:
```powershell
python d:\filework\test.py --single meta/tests/test_receipt_service.py
python d:\filework\test.py --single meta/tests/test_serial_completion_genealogy.py
```
Expected: 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add meta/services/receipt_service.py meta/tests/test_receipt_service.py
git commit -m "refactor(platform): 收货红冲接入统一编排"
```

---

## Phase 3：承诺层平台化（P0）

### Task 3.1: 策略与入口迁出 inventory 服务

**Files:**
- Create: `meta/services/commitment_policies.py`
- Create: `meta/services/commitment_service.py`
- Modify: `meta/services/inventory_reservation_service.py`
- Test: `meta/tests/test_commitment_service.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
from meta.services.commitment_policies import ROW_DEMAND_POLICIES

def test_service_request_policy_is_registered():
    p = ROW_DEMAND_POLICIES['service_request']
    assert p['demand_object_type'] == 'service_order'
    assert p['qty_field'] == 'qty'
    assert p['peg_type'] == 'soft'
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_commitment_service.py`
Expected: ModuleNotFoundError。

- [ ] **Step 3: 迁移策略并建入口**

把 `ROW_DEMAND_POLICIES` 原样迁到 `commitment_policies.py`；新增：

```python
class CommitmentService:
    """承诺平台入口；低层原语仍在 InventoryReservationService。"""

    def __init__(self, data_source, reservations=None):
        from meta.services.inventory_reservation_service import (
            InventoryReservationService)
        self._reservations = reservations or InventoryReservationService(data_source)

    def sync(self, source_doc_type, doc_id):
        return self._reservations.sync_document_row_demands(source_doc_type, doc_id)

    def release(self, source_doc_type, doc_id, line_id=None, reason=''):
        return self._reservations.release_by_source(
            source_doc_type, doc_id, line_id=line_id, reason=reason)

    def assert_closable(self, source_doc_type, doc_id):
        return self._reservations.assert_source_closable(source_doc_type, doc_id)

    def fulfill_work_order_components(self, work_order_id, completed_qty=None):
        return self._reservations.fulfill_work_order_components(
            work_order_id, completed_qty=completed_qty)
```

`inventory_reservation_service` 改为从 `commitment_policies` 导入，保留 `sync_document_row_demands` 与所有现有公开方法，避免破坏测试。

- [ ] **Step 4: 运行确认通过**

Run:
```powershell
python d:\filework\test.py --single meta/tests/test_commitment_service.py
python d:\filework\test.py --single meta/tests/test_inventory_reservation_service.py
```
Expected: 全部通过（原 39 条 + 新 1 条）。

- [ ] **Step 5: 提交**

```powershell
git add meta/services/commitment_policies.py meta/services/commitment_service.py meta/services/inventory_reservation_service.py meta/tests/test_commitment_service.py
git commit -m "refactor(platform): 承诺策略与入口上移"
```

### Task 3.2: SO 行与 requisition 接入策略

**Files:**
- Modify: `meta/services/commitment_policies.py`
- Modify: `meta/services/commitment_service.py`
- Test: `meta/tests/test_commitment_service.py`

- [ ] **Step 1: 写失败测试**

```python
from meta.services.commitment_policies import ROW_DEMAND_POLICIES

def test_sales_order_line_policy():
    p = ROW_DEMAND_POLICIES['sales_order_line']
    assert p['demand_object_type'] == 'sales_order_line'
    assert p['key_prefix'] == 'SO-LINE'

def test_requisition_policy():
    p = ROW_DEMAND_POLICIES['requisition']
    assert p['demand_object_type'] == 'requisition_line'
    assert p['qty_field'] == 'qty'
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_commitment_service.py`
Expected: KeyError。

- [ ] **Step 3: 登记策略（先读实际表结构）**

按 `sales_order_lines` / `requisition_lines` 的真实列名填写：`doc_table`、`line_table`、`doc_field`、`line_where`、`active_statuses`、`release_statuses`、`org_fields`、`qty_field`、`uom_field`、`key_prefix`。SO 行的“段/钉”特殊逻辑保留在 `sync_sales_order_line` 适配器，不塞进通用策略。

- [ ] **Step 4: 运行确认通过**

Run: `python d:\filework\test.py --single meta/tests/test_commitment_service.py`
Expected: `3 passed`。

- [ ] **Step 5: 提交**

```powershell
git add meta/services/commitment_policies.py meta/tests/test_commitment_service.py
git commit -m "feat(platform): SO 行与采购申请登记承诺策略"
```

### Task 3.3: 履约事件注册，去掉服务内直调

**Files:**
- Create: `meta/services/commitment_handlers.py`
- Modify: `meta/services/receipt_service.py`、`meta/services/inventory_reservation_service.py`
- Modify: `meta/core/app_builder.py`
- Test: `meta/tests/test_commitment_service.py`

- [ ] **Step 1: 写失败测试**

```python
from meta.services.commitment_handlers import HANDLERS, register

def test_receipt_posted_handler_registered():
    assert 'receipt.posted' in HANDLERS

def test_register_is_idempotent():
    calls = []
    fn = lambda payload: calls.append(payload)
    register('x.event', fn)
    register('x.event', fn)
    assert HANDLERS['x.event'] == [fn]
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_commitment_service.py`
Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现轻量同步钩子**

```python
HANDLERS = {}

def register(event, handler):
    handlers = HANDLERS.setdefault(event, [])
    if handler not in handlers:
        handlers.append(handler)

def dispatch(event, payload):
    for handler in HANDLERS.get(event, []):
        handler(payload)
```

`receipt_service._post_work_order` 改为 `dispatch('receipt.posted', {...})`；在 `app_builder.py` 注册 `receipt.posted → CommitmentService.fulfill_work_order_components`。保留 try/except 只告警，不阻断过账。

- [ ] **Step 4: 运行确认通过**

Run:
```powershell
python d:\filework\test.py --single meta/tests/test_commitment_service.py
python d:\filework\test.py --single meta/tests/test_serial_completion_genealogy.py
python d:\filework\test.py --single meta/tests/test_receipt_service.py
```
Expected: 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add meta/services/commitment_handlers.py meta/services/receipt_service.py meta/core/app_builder.py meta/tests/test_commitment_service.py
git commit -m "feat(platform): 履约事件钩子与收货接入"
```

---

## Phase 4：横切能力收敛（P1）

### Task 4.1: 取号唯一入口

**Files:**
- Create: `meta/services/document_number_service.py`
- Modify: `meta/api/bo_api.py`、`meta/services/transfer_order_service.py`、`meta/services/transfer_shipment_service.py`、`meta/services/receipt_service.py`、`meta/services/requisition_po_conversion.py`
- Test: `meta/tests/test_document_number_service.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
def test_allocate_is_idempotent_when_number_present():
    from meta.services.document_number_service import DocumentNumberService
    service = DocumentNumberService(_ds())
    assert service.allocate_for('transfer_order', {'order_no': 'TO-1'}) is None

def test_allocate_uses_type_sequence():
    from meta.services.document_number_service import DocumentNumberService
    number = DocumentNumberService(_ds()).allocate_for('transfer_order', {})
    assert number.startswith('TO-')
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_document_number_service.py`
Expected: ModuleNotFoundError。

- [ ] **Step 3: 抽服务并替换调用点**

把 `bo_api._allocate_document_no` 的实现整体迁入 `DocumentNumberService.allocate_for(object_type, payload)`（包含 `number_sequence_id` 查询、`NumberSequenceEngine.allocate`、已有值不覆盖）；5 个调用点改为调用该服务，删除各自的私有 `_allocate_document_no`。

- [ ] **Step 4: 运行确认通过**

Run:
```powershell
python d:\filework\test.py --single meta/tests/test_document_number_service.py
python d:\filework\test.py --single meta/tests/test_transfer_order.py
python d:\filework\test.py --single meta/tests/test_receipt_service.py
python d:\filework\test.py --single meta/tests/test_requisition_po_conversion.py
```
Expected: 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add meta/services/document_number_service.py meta/api/bo_api.py meta/services/transfer_order_service.py meta/services/transfer_shipment_service.py meta/services/receipt_service.py meta/services/requisition_po_conversion.py meta/tests/test_document_number_service.py
git commit -m "refactor(platform): 单据取号收敛为唯一服务"
```

### Task 4.2: 组织上下文解析

**Files:**
- Create: `meta/services/org_context_resolver.py`
- Modify: `meta/services/inventory_reservation_service.py`
- Test: `meta/tests/test_org_context_resolver.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
def test_priority_fields_first_hit_wins():
    from meta.services.org_context_resolver import OrgContextResolver
    resolver = OrgContextResolver(_ds())
    org = resolver.from_fields({'provider_org_id': 2, 'requester_org_id': 1},
                               ('provider_org_id', 'requester_org_id'))
    assert org == 2

def test_no_source_raises():
    import pytest
    from meta.services.org_context_resolver import OrgContextResolver, OrgNotResolved
    with pytest.raises(OrgNotResolved):
        OrgContextResolver(_ds()).from_fields({}, ('provider_org_id',))
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_org_context_resolver.py`
Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现解析器并接入**

实现 `from_fields(record, fields)`、`from_sales_order_line(...)`、`from_project(...)`、`single_active_org()`；把 `InventoryReservationService._resolve_work_order_org`、`sync_document_row_demands` 的 org 取值改为调用该解析器，保留原错误码 `ORG_NOT_RESOLVED`。

- [ ] **Step 4: 运行确认通过**

Run:
```powershell
python d:\filework\test.py --single meta/tests/test_org_context_resolver.py
python d:\filework\test.py --single meta/tests/test_inventory_reservation_service.py
```
Expected: 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add meta/services/org_context_resolver.py meta/services/inventory_reservation_service.py meta/tests/test_org_context_resolver.py
git commit -m "refactor(platform): 组织上下文解析器"
```

### Task 4.3: 行语义守卫

**Files:**
- Create: `meta/core/interceptors/line_guard_interceptor.py`
- Modify: `meta/core/app_builder.py`
- Test: `meta/tests/test_line_guard.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
from meta.core.interceptors.line_guard_interceptor import LineGuardInterceptor, LineGuardError

def test_duplicate_line_no_rejected():
    interceptor = LineGuardInterceptor()
    payload = {'parent_id': 1, 'lines': [{'line_no': '10'}, {'line_no': '10'}]}
    try:
        interceptor.validate_batch('sales_order_line', 'parent_id', payload)
    except LineGuardError:
        return
    raise AssertionError('重复行号未被拒绝')

def test_positive_qty_required_for_goods_line():
    interceptor = LineGuardInterceptor()
    try:
        interceptor.validate_qty('service_request_line', {'line_type': 'goods', 'qty': 0})
    except LineGuardError:
        return
    raise AssertionError('零数量未被拒绝')
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_line_guard.py`
Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现守卫并注册**

实现 `validate_batch(object_type, parent_field, payload)` 与 `validate_qty(object_type, row)`；在 `app_builder.py` 以 priority 54 注册。先只启用 `service_request_line`，用白名单控制接入对象，避免影响存量对象。

- [ ] **Step 4: 运行确认通过**

Run:
```powershell
python d:\filework\test.py --single meta/tests/test_line_guard.py
python d:\filework\test.py --single meta/tests/test_demand_entry_m1.py
```
Expected: 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add meta/core/interceptors/line_guard_interceptor.py meta/core/app_builder.py meta/tests/test_line_guard.py
git commit -m "feat(platform): 行语义通用守卫（白名单试点）"
```

### Task 4.4: 追溯链接统一

**Files:**
- Create: `meta/services/trace_link_service.py`
- Modify: `meta/services/receipt_service.py`
- Test: `meta/tests/test_trace_link_service.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
def test_link_serial_is_idempotent():
    from meta.services.trace_link_service import TraceLinkService
    service = TraceLinkService(_ds())
    service.link_serial(document_id=7, serial_id=1, qty=2)
    service.link_serial(document_id=7, serial_id=1, qty=2)
    assert service.count_serial_links(7) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `python d:\filework\test.py --single meta/tests/test_trace_link_service.py`
Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现统一链接写入**

封装 `document_serial_link` / `document_hu_link` 的插入（幂等键 + 数量累加），保留 `doc_flow` 边不动；`receipt_service` 的序列号/HU 链接改调该服务。

- [ ] **Step 4: 运行确认通过**

Run:
```powershell
python d:\filework\test.py --single meta/tests/test_trace_link_service.py
python d:\filework\test.py --single meta/tests/test_serial_completion_genealogy.py
```
Expected: 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add meta/services/trace_link_service.py meta/services/receipt_service.py meta/tests/test_trace_link_service.py
git commit -m "refactor(platform): 序列号/HU 链接统一服务"
```

---

## 验收指标

| 指标 | 改造前 | 目标 |
|---|---|---|
| 声明状态迁移的单据头 | 0（仅 3 个非单据对象） | ≥ 5（service_request / shipment / receipt / work_order / transfer_order） |
| 取号实现份数 | 5 | 1 |
| 承诺接入新增单据的改动 | 新增 80–150 行同步方法 | 1 条策略 + 测试 |
| 逆向入口 | 各服务手写 | 全部走 `reverse_document` |
| 组织解析实现份数 | ≥ 3 | 1 |
| 追溯链接写入入口 | 3 套 | 1 |

## 风险与边界

1. **YAML 表达力有限**：`validation_expression` 不适合复杂业务判据；复杂校验继续留在拦截器，不强行入 schema。
2. **服务层绕过通用更新路径**：`StateTransitionExecutor` 挂在 before_update，只覆盖通用更新；业务动作必须显式调用 `apply_status_transition`，否则规则形同虚设。
3. **冲销语义不可合并**：取消（未发生履约）、关闭（终止保留历史）、红冲（冲销已发生事实）必须分别映射，不能做成一个“逆向按钮”。
4. **承诺回退默认保守**：红冲不回退组件核销（只进不退），等反投料/领料单据落地再开 `explicit_revert`。
5. **工作树纪律**：全程在 `platform-infra` worktree；不 stash 其他会话改动；每任务独立提交，便于逐批复滚。

## 执行记录（Phase 0 填写）

| 测试文件 | 基线通过数 | 日期 |
|---|---|---|
| test_inventory_reservation_service.py |  |  |
| test_demand_entry_m1.py |  |  |
| test_rule_engine.py |  |  |
| test_engineering_change.py |  |  |
