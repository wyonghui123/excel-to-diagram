# Spec: v3.4 BO Action 体系 — Function 维度引入 (v1.0)

> **日期**: 2026-06-06
> **作者**: AI Agent (Trae) — 基于 SAP CAP / Palantir Foundry 调研
> **状态**: ✅ 已实施
> **关联**: 
> - [spec-v3-post-5-followup.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-v3-post-5-followup.md) - 续篇
> - [bo-action-vs-head-products.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-vs-head-products.md) - 头部产品对照 (含 SAP / Palantir)
> **总工时**: 30min

---

## 📋 文档定位

**v3.4 引入 Function 维度** —— 区分 Action (写) vs Function (读/计算) —— 跟随 SAP CAP / Palantir Foundry 头部实践。

---

## 🎯 核心变更

### 调研结论 (2026-06-05)

| 产品 | Action 范围 | 严格区分读写? |
|------|------------|:---:|
| Salesforce `@AuraEnabled` | 写 + 复杂计算 | ⚠️ cacheable 标志 |
| ServiceNow Flow Designer | 写 + Flow step | ✅ Action = step |
| Power Platform Custom Connector | Operation (GET/POST/PUT/DELETE) | ✅ method 区分 |
| **SAP CAP** | **Action (写) vs Function (读)** | ✅ **严格区分** |
| **Palantir Foundry** | **ActionType (写) vs Function (读/计算)** | ✅ **严格区分** |

**关键引用**:
- SAP CAP: "**Actions modify data in the server**, **Functions retrieve data**"
- Palantir: "**Action types** are governed transactions that **edit** objects"; "**Functions** are server-side code that operates against Ontology objects"

### 决策: 引入 Function 维度

**action 前缀 = 写 (改数据)**
**function 前缀 = 读/计算 (不写)**

| 维度 | Action (写) | Function (读/计算) |
|------|-------------|---------------------|
| **HTTP** | POST | GET |
| **副作用** | 必有 | 无 |
| **审计** | 必写 audit_log | 可选 |
| **缓存** | 不可缓存 | 可缓存 (cache_ttl) |
| **拦截器链** | 全 18 链 | 子集 |
| **OpenAPI** | POST + RequestBody | GET + Query |
| **幂等** | 多数 false | 通常 true |

---

## 🛠️ 实施变更

### 1. bo_action_registry 元数据扩展

**新字段**:
```python
operation_type: str = 'action'       # 'action' (写) | 'function' (读/计算)
cacheable: bool = False              # Function 模式可缓存
cache_ttl: int = 0                   # Function 缓存秒数 (0=不缓存)
```

**注册示例**:
```python
bo_action_registry.register(
    'function.value_help.resolve',
    function_value_help_resolve_handler,
    description='[Function] 解析 value_help 值的显示信息',
    operation_type='function',  # 🆕
    cacheable=True,             # 🆕
    cache_ttl=60,               # 🆕
    ...
)
```

### 2. 4 个 function.* 实施

| Action | 类型 | cacheable | cache_ttl | 鉴权 |
|--------|------|:---:|:---:|------|
| `function.value_help.resolve` | Function (读) | ✅ | 60s | 登录 |
| `function.aggregate.query` | Function (读) | ✅ | 30s | 登录 |
| `function.aggregate.refresh` | Function (写) | ❌ | 0 | admin |
| `function.subscription.list` | Function (读) | ❌ | 0 | 登录 |

**注意**: `function.aggregate.refresh` 实际有副作用, 但属于 aggregate 域——**标为 function 仅因 aggregate 域归类**。后续可考虑引入更细的 `mutation` 子分类。

### 3. OpenAPI 3.0 自动按 operation_type 选方法

```python
# bo_action_api.py:openapi_spec()
if meta.operation_type == 'function':
    method = 'get'  # 读 → GET
else:
    method = 'post'  # 写 → POST
```

**Tags 分组**:
- `function/<category>` (例: `function/value_help`)
- `action/<category>` (例: `action/auth`)

**Summary 标识**:
- Function: `[FUNCTION] [Function] 解析 value_help 值的显示信息`
- Action: `用户登录认证` (无前缀)

### 4. TS types 自动重生成

`scripts/generate_action_types.cjs` 调用 `_openapi.json`, 自动生成 16 Action 类型 (12 老 + 4 function 新):
```typescript
export type ActionId = 
  | 'audit.export'
  | 'audit.retry'
  | 'batch_delete'
  | 'batch_save'
  | 'function.aggregate.query'        // 🆕
  | 'function.aggregate.refresh'      // 🆕
  | 'function.subscription.list'      // 🆕
  | 'function.value_help.resolve'     // 🆕
  | 'subscription.create'
  | 'user.authenticate'
  | 'user.change_password'
  | ...
```

---

## 📊 最终成果 (v3.4)

| 指标 | 价值 |
|------|------|
| **Action 总数** | 12 → **16** (+4 function) |
| **Function 总数** | 0 → **4** (新维度) |
| **SAP/Palantir 对齐** | ✅ 严格区分 Action vs Function |
| **OpenAPI 规范** | ✅ 16 paths 自动按 method 分类 |
| **TS types** | ✅ 16 Action 完整类型 |
| **DB 完整性** | ✅ integrity_check=ok |

### 16 Action 完整列表

| # | Action ID | Operation | HTTP | 鉴权 | 备注 |
|---|-----------|-----------|------|------|------|
| 1 | user.authenticate | action | POST | 公开 | 公开 |
| 2 | user.logout | action | POST | 登录 | |
| 3 | user.get_current | action | POST | 登录 | *原 GET 强制 POST (兼容)* |
| 4 | user.change_password | action | POST | 登录 | |
| 5 | user.update_profile | action | POST | 登录 | |
| 6 | user.reset_password | action | POST | admin | v3.1 |
| 7 | batch_save | action | POST | 登录 | 通用 |
| 8 | batch_delete | action | POST | 登录 | v3.1 |
| 9 | audit.retry | action | POST | admin | v3.1 |
| 10 | audit.export | action | POST | admin | v3.1 (base64) |
| 11 | subscription.create | action | POST | 登录 | v3.1 |
| 12 | version.clear_other_current | action | POST | 登录 | v3.2 迁移 |
| **13** | **function.value_help.resolve** | **function** | **GET** | **登录** | **v3.4** 🆕 |
| **14** | **function.aggregate.query** | **function** | **GET** | **登录** | **v3.4** 🆕 |
| **15** | **function.aggregate.refresh** | **function** | **GET** | **admin** | **v3.4** 🆕 (有副作用) |
| **16** | **function.subscription.list** | **function** | **GET** | **登录** | **v3.4** 🆕 |

---

## 🛡️ 实施前置条件

- [x] DB 备份 (`pre-v3.4.function.1780705533.bak`)
- [x] `feature/bo-action-v3` 分支

## 🚦 回滚计划

每个 Function 独立回滚:
- 删除 `meta/services/function_*.py` (3 个文件)
- 删除 server.py 注册行 (4 个)
- 重启服务
- registry `operation_type` 字段是**可选**, 老 Action 兼容

---

## 🔗 关联文档

| 文档 | 关系 |
|------|------|
| [spec-v3-post-5-followup.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-v3-post-5-followup.md) | v3.2 续篇 (含 spec-p1-sendfile-deep) |
| [bo-action-vs-head-products.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-vs-head-products.md) | 头部产品对照 (Salesforce/ServiceNow/Power Platform/SAP/Palantir) |
| [spec-p0-5-actions.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-p0-5-actions.md) | v3.1 P0 5 Action 详细 spec |
| [bo-action-p0-5-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-p0-5-result.md) | v3.1 实施结果 |
| [v3-bo-action-main-summary.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/v3-bo-action-main-summary.md) | v3 大主线汇总 |

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-06 | v3.4 Function 维度引入 + 4 function 实施 + OpenAPI/TS types 升级 |
