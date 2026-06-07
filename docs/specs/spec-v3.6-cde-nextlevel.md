# Spec: v3.6 进阶 — Subflow 增强 + OpenAPI 文档站 + TS 类型工具链 (v1.0)

> **日期**: 2026-06-06
> **作者**: AI Agent (Trae) — 基于 v3.2 现状深入分析
> **状态**: 📋 方案阶段
> **关联**: [spec-v3-post-5-followup.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-v3-post-5-followup.md) C+D+E 任务
> **总工时**: 8h (C 4h + D 2h + E 2h)

---

## 📋 文档定位

**C / D / E 3 个任务已在 v3.2 基础实施**。本 spec 描述**进阶增强**, 让 3 个能力达到 **生产可用 + 开发者体验良好** 的状态。

---

# 📊 3 任务当前现状

| 任务 | v3.2 基础 | 差距 |
|------|----------|------|
| **C Subflow** | `_chain` 端点 + 简化 Jinja2 + skip_if | 无批量 / 无异步 / 无嵌套 / 无事务回滚 / 无超时 |
| **D OpenAPI** | `_openapi.json` 端点 | 无工具链 (Postman/Apifox/Swagger UI) / 无同步 CI / 无 OpenAPI 3.0 完整字段 |
| **E TS types** | `generate_action_types.cjs` (19 Action) | 无 watch mode / 无 IDE 集成 / 无 form generator / 无 actions-ui |

---

# C: Subflow chain_call 增强 (4h)

## 当前能力 (v3.2)

```python
# meta/services/subflow_engine.py
- resolve_jinja2(value, alias_data)  # $alias.data.field
- eval_skip_if(expression, alias_data)
- execute_subflow(registry, name, steps, atomic, context, user_info)
```

**已支持**: 单步 / 多步串行 / 变量引用 / 条件跳过 / 上下文传递 / 审计 (1 条 SUBFLOW)
**未支持**: 批量 step / 异步 step / 嵌套 subflow / 真事务回滚 / 超时 / 重试 / 错误回滚到某 step

## 11 项增强 (按价值排序)

### 1️⃣ **并行 step (parallel batch)** (1h) 🔴 极高

**业务用例**: 批量查 5 个 aggregate (无依赖) → 并行执行 = 5x 加速

```http
POST /api/v2/action/_chain
{
  "name": "parallel_aggregates",
  "steps": [
    {"action_id": "function.aggregate.query", "params": {"aggregate_id": "user_stats"}, "as": "users"},
    {"action_id": "function.aggregate.query", "params": {"aggregate_id": "order_stats"}, "as": "orders", "parallel": true},
    {"action_id": "function.aggregate.query", "params": {"aggregate_id": "product_stats"}, "as": "products", "parallel": true}
  ]
}
```

**实现**:
```python
# subflow_engine.py: 加 parallel_group
parallel_steps = [s for s in steps if s.get('parallel')]
if parallel_steps:
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(registry.call, s['action_id'], s.get('params', {}), ctx): s for s in parallel_steps}
        for f in concurrent.futures.as_completed(futures):
            step = futures[f]
            r = f.result()
            # 保存到 alias_data
            if step.get('as') and r.get('success'):
                alias_data[step['as']] = r
```

### 2️⃣ **事务回滚 (transactional atomic)** (1h) 🔴 极高

**业务用例**: 注册用户 = create + update_profile + subscription.create, 任一失败全部回滚

**实现**:
```python
# subflow_engine.py: atomic=True 时用真事务
if atomic:
    from meta.core.datasource import get_data_source
    ds = get_data_source("sqlite", database=...)
    
    with ds.transaction():  # BEGIN IMMEDIATE
        for step in steps:
            result = registry.call(step['action_id'], step.get('params', {}), ctx)
            if not result.get('success'):
                # 自动 raise 触发 transaction 回滚
                raise RuntimeError(f"Step {i} failed: {result.get('message')}")
```

**限制**: 只能回滚**直接写 DB 的 Action** (走 ds.transaction 的)。BO framework 内的 Action 自动支持。Function 类 (read) 无副作用, 直接放行。

### 3️⃣ **嵌套 subflow (nested chain)** (30min) 🟠 高

**业务用例**: 大型业务 = 多个 subflow 嵌套组合

```http
POST /api/v2/action/_chain
{
  "name": "user_onboard",
  "steps": [
    {"subflow": "create_user", "as": "user"},  # 嵌套 subflow 引用
    {"subflow": "setup_notifications", "use": {"user_id": "$user.data.user_id"}, "as": "notif"}
  ]
}
```

**实现**: 在 subflow 之前, 把已注册的 subflow 存为"模板", 嵌套调用 = 模板展开

### 4️⃣ **单步超时 (per_step_timeout)** (30min) 🟡 中

**实现**:
```python
# per step: timeout_seconds: 30 (default)
# 整体: total_timeout: 300
import signal
def timeout_handler(signum, frame):
    raise TimeoutError("Step execution exceeded timeout")
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(params.get('timeout_seconds', 30))
try:
    result = registry.call(...)
finally:
    signal.alarm(0)
```

### 5️⃣ **重试机制 (retry policy)** (30min) 🟡 中

```python
# per step: retry: { max_attempts: 3, backoff: 'exponential' | 'linear', delay: 1 }
```

### 6️⃣ **错误处理 (on_error step)** (30min) 🟡 中

```python
# per step: on_error: { action_id: 'audit.retry', params: {...} }
# 失败时自动调用补偿 Action
```

### 7️⃣ **进度回调 (progress callback)** (30min) 🟢 低

**场景**: Subflow 太长, 前端想显示进度

```http
POST /api/v2/action/_chain?progress=true
```

返回 **Server-Sent Events (SSE)** 流, 每完成 1 step 推送 1 次。

### 8️⃣ **Subflow 模板存储 (server-side named subflow)** (30min) 🟢 低

**场景**: 重复使用的 subflow, 存为命名模板

```http
POST /api/v2/action/_subflow_template
{
  "name": "user_onboard",
  "steps": [...]
}

# 调用时:
POST /api/v2/action/_chain
{
  "template": "user_onboard",
  "params": { "username": "...", "email": "..." }
}
```

**存储**: `subflow_templates` 表 (新)

### 9️⃣ **Subflow 测试端点 (dry-run)** (15min) 🟢 低

```http
POST /api/v2/action/_chain?dry_run=true
```

执行但不写库, 返回"将做什么"。

### 🔟 **Subflow 性能指标** (15min) 🟢 低

每个 subflow 自动记录: total_duration / avg_step / 99th percentile / 失败率

### 1️⃣1️⃣ **Subflow 事件总线** (30min) 🟢 低

**场景**: Subflow 完成时, 发事件 → 通知订阅者

## 推荐 v3.6 实施范围

**4h 内实施** (按价值/工时比):
- ✅ 1️⃣ 并行 step (1h) — 极高价值
- ✅ 2️⃣ 事务回滚 (1h) — 极高价值
- ✅ 3️⃣ 嵌套 subflow (30min) — 高价值
- ✅ 4️⃣ 单步超时 (30min) — 中等
- ✅ 5️⃣ 重试机制 (30min) — 中等
- ✅ 6️⃣ 错误处理 (30min) — 中等

**剩余 (后续 v3.7)**:
- 7-11️⃣ 全部 deferred

---

# D: OpenAPI 3.0 文档站 + 工具链 (2h)

## 当前能力 (v3.2)

```python
# meta/api/bo_action_api.py:openapi_spec()
- 输出 OpenAPI 3.0 paths + components.schemas
- 19 Action 全部映射
- action→POST, function→GET
```

**已支持**: 基本 OpenAPI 3.0 spec
**未支持**: 完整 spec (info/contact/license/servers) / Swagger UI / Postman 导出 / 集成 CI

## 5 项增强

### 1️⃣ **Swagger UI 集成** (30min) 🔴 极高

**业务价值**: 浏览器实时浏览所有 Action, 试调

**实施**:
- 在 `bo_action_api.py` 加 `/api/v2/action/_docs` 端点
- 返回 HTML, 内嵌 swagger-ui-dist CDN
- 实时调 _openapi.json

```python
@bo_action_bp.route('/_docs')
def swagger_ui():
    return render_template_string("""
    <!DOCTYPE html>
    <html><head>
      <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    </head>
    <body>
      <div id="swagger-ui"></div>
      <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
      <script>
        SwaggerUIBundle({ url: '/api/v2/action/_openapi.json', dom_id: '#swagger-ui' })
      </script>
    </body></html>
    """)
```

### 2️⃣ **完整 OpenAPI 3.0 字段** (30min) 🟠 高

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "BO Action API",
    "version": "v3.6",
    "description": "...",
    "contact": {"name": "...", "email": "..."},
    "license": {"name": "MIT"}
  },
  "servers": [{"url": "http://localhost:3010", "description": "dev"}],
  "tags": [
    {"name": "action/auth", "description": "认证相关"},
    {"name": "function/value_help", "description": "值帮助查询"}
  ],
  "components": {
    "securitySchemes": {"cookieAuth": {"type": "apiKey", "in": "cookie", "name": "auth_token"}},
    "schemas": {...}
  },
  "security": [{"cookieAuth": []}]
}
```

### 3️⃣ **Postman / Apifox 一键导出** (30min) 🟡 中

**实施**:
- `scripts/export_postman.py` — 调 _openapi.json → 转 Postman v2.1 collection
- `scripts/export_apifox.py` — 转 Apifox 格式
- 输出到 `docs/api/`

**价值**: 团队用 Postman 调试, 直接 import 即可

### 4️⃣ **客户端 SDK 自动生成 (openapi-generator)** (30min) 🟡 中

**实施**:
- 在 `scripts/generate_sdks.sh` 调用 openapi-generator-cli
- 生成 Python / JavaScript / TypeScript SDK
- 提交到 `sdk/` 目录 (可选)

**前置**: 需要 `openapi-generator-cli` (npm / java)

### 5️⃣ **openapi.json CI 同步检查** (15min) 🟢 低

**实施**:
- `scripts/check_openapi_consistency.sh` — 验证 _openapi.json 与 registry 一致
- 添加到 .git/hooks (或 CI 流程)

## 推荐 v3.6 实施范围

**2h 内实施**:
- ✅ 1️⃣ Swagger UI (30min) — 极高价值
- ✅ 2️⃣ 完整 OpenAPI 字段 (30min) — 高价值
- ✅ 3️⃣ Postman 导出 (30min) — 中等
- ✅ 4️⃣ 客户端 SDK (30min) — 中等 (可能改 deferred)

---

# E: TypeScript 类型工具链 (2h)

## 当前能力 (v3.2)

```js
// scripts/generate_action_types.cjs
- 调 _openapi.json
- 输出 useBoAction.types.d.ts
- 19 Action 完整类型
```

**已支持**: 基本 .d.ts 生成
**未支持**: watch mode / form schema / actions-ui 组件 / IDE 集成

## 6 项增强

### 1️⃣ **Watch mode (auto-regenerate on backend change)** (15min) 🔴 极高

**业务价值**: 后端改了 schema, 前端 .d.ts 自动更新

**实施**:
```js
// scripts/generate_action_types.cjs: --watch 模式
// 启动后端 dev 时, 周期 poll _openapi.json
// hash 检测, 变化时重生成 + console 提示
```

或者用文件 watch (后端 server.py 改动触发)。

### 2️⃣ **Form schema 生成 (JSON Schema → Vue 组件)** (45min) 🔴 极高

**业务价值**: input_schema 直接生成表单, 不用手写 .vue

**实施**:
- 新增 `src/composables/useBoActionForm.js`
- 基于 input_schema 自动生成:
  - 文本框 (string)
  - 数字框 (integer/number)
  - 复选框 (boolean)
  - 下拉框 (enum)
  - 日期选择器 (format=date)
  - JSON 编辑器 (object)

```js
import { useBoActionForm } from '@/composables/useBoActionForm'
const { Form, validate } = useBoActionForm('enum_type.create', { initial: {} })
// 自动渲染 <Form> 组件, 含所有字段 + 校验
```

### 3️⃣ **Actions-UI 组件 (Action Explorer)** (45min) 🟠 高

**业务价值**: 浏览器内浏览所有 Action, 试调

**实施**:
- `src/views/admin/ActionExplorer.vue`
- 调 `_schemas` 端点
- 列出 19 Action, 每个含: name / description / input_schema / 按钮 "Try"
- "Try" 按钮 = 弹出 form (用 useBoActionForm) + submit

### 4️⃣ **IDE 集成 (VSCode snippet + 任务)** (15min) 🟡 中

**实施**:
- `.vscode/snippets/useBoAction.code-snippets` — 快捷调用模板
- `.vscode/tasks.json` — `Run Type Generation` 任务

### 5️⃣ **CI 检查 (TS 编译期校验)** (15min) 🟡 中

**实施**:
- `package.json` 加 `typecheck:action` 脚本
- 调用 `tsc --noEmit` 校验 useBoAction.types.d.ts 与 useBoAction.js 签名一致

### 6️⃣ **Action 错误码枚举 (前端类型)** (15min) 🟢 低

**实施**:
- 提取后端错误码 → `src/composables/useBoAction.errors.ts`
- 前端 useBoAction 处理 401/403/404/500 各类型错误

## 推荐 v3.6 实施范围

**2h 内实施**:
- ✅ 1️⃣ Watch mode (15min) — 极高价值
- ✅ 2️⃣ Form schema 生成 (45min) — 极高价值
- ✅ 3️⃣ Actions-UI 组件 (45min) — 高价值
- ✅ 4️⃣ IDE 集成 (15min) — 中等

**剩余 (v3.7)**:
- 5️⃣ CI 检查 — deferred
- 6️⃣ 错误码枚举 — deferred

---

# 📅 实施时间线 (1 周内)

| 日 | 任务 | 工时 |
|---|------|:---:|
| Day 1 | C-1 并行 step + C-2 事务回滚 | 2h |
| Day 1 | C-3 嵌套 subflow + C-4 单步超时 | 1h |
| Day 2 | C-5 重试 + C-6 错误处理 + C 全量 E2E | 1h |
| Day 2 | D-1 Swagger UI + D-2 完整 OpenAPI 字段 | 1h |
| Day 3 | D-3 Postman 导出 + D-4 SDK 生成 (或 deferred) | 1h |
| Day 3 | E-1 Watch mode + E-2 Form schema + E-3 Actions-UI | 2h |
| Day 3 | 全量回归 + 写 v3.6 进度档 | 1h |
| **总** | | **8h (3 天)** |

---

# 📊 最终 v3.6 状态预估

| 维度 | v3.5 | v3.6 |
|------|------|------|
| Subflow 能力 | 基础 (1 步 + 1 step) | **并行/事务/嵌套/超时/重试/补偿** |
| OpenAPI | 基本 spec | **Swagger UI + 完整字段 + Postman** |
| TS types | 静态 .d.ts | **Watch + Form 生成 + UI 浏览器** |
| 开发者体验 | 手动调用 | **零代码试调 (Actions-UI)** |
| 业务能力 | 中 | **强** (Subflow 高级) |

---

# 🛡️ 实施前置

- [x] DB 备份
- [x] `feature/bo-action-v3` 分支
- [x] 19 Action 稳定 (v3.5)

# 🚦 回滚计划

每个增强独立回滚:
- Subflow 增强: 删除 subflow_engine.py 新增函数
- OpenAPI 增强: 删除 _docs 端点 / 还原 _openapi.json
- TS types 增强: 还原 .d.ts / 删除新组件

---

# 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-06 | C+D+E 3 任务进阶 spec (11+5+6 项增强) |
