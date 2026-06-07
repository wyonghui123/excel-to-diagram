# Spec: v3.7 — C+D+E 进阶剩余 6 项详细方案 (v1.0)

> **日期**: 2026-06-06
> **作者**: AI Agent (Trae) — 基于 v3.6 现状深入分析
> **状态**: 📋 方案 + 实施 (1 文档含 6 项)
> **关联**: [spec-v3.6-cde-nextlevel.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-v3.6-cde-nextlevel.md) 的剩余项
> **总工时**: 4h

---

## 📋 6 项总览

| # | 任务 | 来源 | 价值 | 工时 |
|---|------|------|:---:|:---:|
| 1️⃣ | **Progress callback (SSE)** | C 7 | 🟠 高 | 45min |
| 2️⃣ | **模板存储 (server-side named subflow)** | C 8 | 🟡 中 | 45min |
| 3️⃣ | **dry-run (preview mode)** | C 9 | 🟡 中 | 30min |
| 4️⃣ | **性能指标 (metrics)** | C 10 | 🟡 中 | 45min |
| 5️⃣ | **CI 检查 (openapi + tsc)** | D 5 + E 5 | 🟡 中 | 30min |
| 6️⃣ | **错误码枚举 (统一 code + TS enum)** | E 6 | 🟢 低 | 30min |
| **总** | | | | **3.75h** |

---

## 1️⃣ Progress callback (SSE) (45min)

### 背景
**场景**: 5+ 步 subflow, 前端想显示"已完成 3/5"
**v3.6 缺失**: 一次性返回结果, 客户端**无法实时**感知

### 方案: Server-Sent Events (SSE)
**优势**: 简单 (HTTP 1.1)、单向、自动重连、浏览器原生 EventSource

### 实施

#### 1.1 新增端点 `/_chain_stream`
```python
@bo_action_bp.route('/_chain_stream', methods=['POST'])
def execute_subflow_stream_endpoint():
    """
    SSE 实时推送 subflow 执行进度
    Content-Type: text/event-stream
    """
    # 鉴权 (同 _chain)
    ...
    
    def generate():
        # 调用 execute_subflow_with_progress
        for event in execute_subflow_with_progress(...):
            yield f'data: {json.dumps(event, ensure_ascii=False)}\n\n'
    
    return Response(generate(), mimetype='text/event-stream')
```

#### 1.2 改造 subflow_engine
```python
def execute_subflow_with_progress(registry, name, steps, ...):
    """
    Generator: 逐 step 返回事件
    Yields: {event: 'start'/'step_complete'/'complete', ...}
    """
    yield {'event': 'start', 'name': name, 'total_steps': len(steps)}
    
    for step in steps:
        yield {'event': 'step_start', 'step_index': i, 'action_id': step['action_id']}
        r = registry.call(...)
        yield {'event': 'step_complete', 'step_index': i, 'success': r['success'], 'duration_ms': ...}
    
    yield {'event': 'complete', 'succeeded': ..., 'failed': ...}
```

#### 1.3 前端使用
```js
const es = new EventSource('/api/v2/action/_chain_stream?payload=...')
es.addEventListener('step_complete', e => {
  const data = JSON.parse(e.data)
  console.log(`Step ${data.step_index} done: ${data.success}`)
})
es.addEventListener('complete', e => {
  es.close()
})
```

#### 1.4 E2E
- 4 步 subflow → 收到 9 个事件 (1 start + 4 step_start + 4 step_complete + 1 complete)
- 并行 step → 收到 step_start 多个 + step_complete 多个 (顺序无关)

---

## 2️⃣ 模板存储 (server-side named subflow) (45min)

### 背景
**场景**: 重复使用的 subflow (用户注册 = 3 Action) 不应每次都传 steps

### 方案: 服务端注册表 + DB 存储
**存储位置**: 新表 `subflow_templates` (in-memory + 持久化)

### 实施

#### 2.1 新表 schema
```sql
CREATE TABLE IF NOT EXISTS subflow_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    steps_json TEXT NOT NULL,        -- JSON 序列化的 steps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    is_active INTEGER DEFAULT 1
);
```

#### 2.2 端点
```python
# 列出所有模板
GET /api/v2/action/_subflow_template

# 创建/更新模板
PUT /api/v2/action/_subflow_template/<name>
{"description": "...", "steps": [...]}

# 删除模板
DELETE /api/v2/action/_subflow_template/<name>

# 调用
POST /api/v2/action/_chain
{
    "template": "user_onboard",  # 🆕 引用模板名
    "params": {"username": "...", "email": "..."}  # 模板参数
}
```

#### 2.3 内部存储
```python
# meta/services/subflow_template_store.py
class SubflowTemplateStore:
    _cache: Dict[str, List[Dict]] = {}  # 内存缓存
    _db_table = 'subflow_templates'
    
    @classmethod
    def get(cls, name: str) -> List[Dict]:
        if name in cls._cache:
            return cls._cache[name]
        # 从 DB 读
        ...
    
    @classmethod
    def set(cls, name: str, steps: List[Dict], description: str = ''):
        cls._cache[name] = steps
        # 写 DB
        ...
```

#### 2.4 E2E
- 创建模板 → 列表显示 → 引用调用 → 验证执行

---

## 3️⃣ dry-run (preview mode) (30min)

### 背景
**场景**: 测试 subflow 是否合理, 但不写 DB

### 方案: `dry_run=true` 参数
**执行**: 模拟每个 step 的执行计划, **不调用** Action handler (或调 but rollback)

### 实施

#### 3.1 execute_subflow 加 dry_run 参数
```python
def execute_subflow(..., dry_run: bool = False):
    if dry_run:
        # 返回每个 step 的"将做什么", 不实际执行
        plan = []
        for i, step in enumerate(steps):
            plan.append({
                'step_index': i,
                'action_id': step['action_id'],
                'params': step.get('params'),
                'as': step.get('as'),
                'parallel': step.get('parallel', False),
                'atomic': atomic,
                'side_effects': _predict_side_effects(step['action_id']),  # 预测
            })
        return {'success': True, 'data': {'dry_run': True, 'plan': plan}}
```

#### 3.2 端点接受 dry_run
```python
body = ...
dry_run = bool(body.get('dry_run', False))
result = execute_subflow(..., dry_run=dry_run)
```

#### 3.3 E2E
- dry_run=true → 返回 plan, DB 未变
- dry_run=true + 真会失败的步骤 → plan 显示 "would fail at step N"

---

## 4️⃣ 性能指标 (metrics) (45min)

### 背景
**场景**: 监控 subflow 执行, 优化瓶颈

### 方案: 内存 metrics + 新端点 `/metrics`

### 实施

#### 4.1 Metrics 数据结构
```python
# meta/services/subflow_metrics.py
class SubflowMetrics:
    _history: List[Dict] = []  # 最近 1000 次
    _counters: Dict[str, int] = {}  # 全局计数器
    
    @classmethod
    def record(cls, name: str, duration_ms: float, succeeded: int, failed: int):
        cls._history.append({...})
        # 限长 1000
        if len(cls._history) > 1000:
            cls._history = cls._history[-1000:]
```

#### 4.2 execute_subflow 末尾调用 record

#### 4.3 新端点
```python
GET /api/v2/action/_subflow_metrics

{
    "summary": {
        "total_executions": 1234,
        "total_steps": 5678,
        "avg_duration_ms": 45.6,
        "p50_duration_ms": 30,
        "p99_duration_ms": 250,
        "failure_rate": 0.02
    },
    "by_action": {
        "user.authenticate": {"count": 100, "avg_ms": 5, "p99_ms": 20},
        ...
    },
    "recent": [
        {"name": "user_onboard", "duration_ms": 89, "succeeded": 3, "failed": 0, "at": "2026-06-06T10:30:00"}
    ]
}
```

#### 4.4 E2E
- 执行 3 次 subflow → metrics 显示 total=3, avg, by_action
- 故意失败 1 次 → failure_rate > 0

---

## 5️⃣ CI 检查 (openapi + tsc) (30min)

### 背景
**场景**: CI 流水线校验 — 后端 Action 与前端类型一致

### 方案: 2 个脚本

### 实施

#### 5.1 脚本 1: openapi 一致性检查
```bash
# scripts/check_openapi_consistency.sh
# 1. 启动 backend
# 2. 调 _openapi.json 与 _schemas
# 3. 比对:
#    - _openapi.json 中所有 action_id ⊆ _schemas
#    - 每个 input_schema 一致
# 4. 失败 exit 1
```

#### 5.2 脚本 2: tsc 类型检查
```bash
# scripts/typecheck_action_types.sh
# 1. 跑 generate_action_types.cjs
# 2. tsc --noEmit useBoAction.types.d.ts
# 3. 检查与 useBoAction.js 签名一致
```

#### 5.3 package.json scripts
```json
{
    "scripts": {
        "ci:openapi": "bash scripts/check_openapi_consistency.sh",
        "ci:types": "bash scripts/typecheck_action_types.sh",
        "ci": "npm run ci:openapi && npm run ci:types"
    }
}
```

#### 5.4 E2E
- 跑 `npm run ci:openapi` → exit 0
- 跑 `npm run ci:types` → exit 0 (tsc 检查)

---

## 6️⃣ 错误码枚举 (统一 code + TS enum) (30min)

### 背景
**场景**: 前端 useBoAction 处理错误时, 需要**统一错误码**

### 方案: 后端统一 `code` + 前端生成 TS enum

### 实施

#### 6.1 后端错误码字典
```python
# meta/core/error_codes.py
class ErrorCode:
    # 鉴权
    UNAUTHORIZED = 'unauthorized'         # 401
    FORBIDDEN = 'forbidden'               # 403
    TOKEN_EXPIRED = 'token_expired'       # 401
    TOKEN_BLACKLISTED = 'token_blacklisted'  # 401

    # Action
    ACTION_NOT_FOUND = 'action_not_found'  # 404
    ACTION_FORBIDDEN = 'action_forbidden'  # 403 (admin)
    ACTION_VALIDATION_ERROR = 'action_validation_error'  # 200 (false)
    ACTION_HANDLER_ERROR = 'action_handler_error'  # 200 (false)

    # Subflow
    SUBFLOW_EMPTY = 'subflow_empty'        # 400
    SUBFLOW_STEP_FAILED = 'subflow_step_failed'  # 200 (false)
    SUBFLOW_ATOMIC_FAILED = 'subflow_atomic_failed'  # 200 (false)
    SUBFLOW_TIMEOUT = 'subflow_timeout'    # 200 (false)

    # 服务端
    INTERNAL_ERROR = 'internal_error'      # 500
    DB_ERROR = 'db_error'                 # 500
    TRANSACTION_FAILED = 'transaction_failed'  # 200 (false)
```

#### 6.2 所有 endpoint 返回 code
```python
# bo_action_api.py:execute_action
result = registry.call(...)
if not result.get('success'):
    code = result.get('code') or ErrorCode.ACTION_HANDLER_ERROR
    return jsonify({
        'success': False,
        'data': None,
        'message': result.get('message'),
        'code': code,  # 🆕
    }), status_code
```

#### 6.3 TS enum 生成
```ts
// src/composables/errorCodes.ts (自动生成)
export const ErrorCodes = {
  UNAUTHORIZED: 'unauthorized',
  FORBIDDEN: 'forbidden',
  TOKEN_EXPIRED: 'token_expired',
  // ...
} as const

export type ErrorCode = typeof ErrorCodes[keyof typeof ErrorCodes]
```

#### 6.4 前端 useBoAction 处理
```js
// useBoAction.js
import { ErrorCodes } from './errorCodes'
// 在错误 catch 时, 透出 r.code
return {
  success: false,
  data: null,
  message: e?.message || '网络错误',
  code: e?.code || ErrorCodes.INTERNAL_ERROR,  // 🆕
}
```

#### 6.5 E2E
- 测试 401/403/404 等不同错误, 验证 `code` 字段正确
- 前端测试 `if (r.code === ErrorCodes.TOKEN_EXPIRED) { ... }`

---

## 📅 实施顺序 (推荐 1 天)

| 时段 | 任务 | 工时 |
|------|------|:---:|
| 上午 1 | 1. Progress callback (SSE) | 45min |
| 上午 2 | 2. 模板存储 | 45min |
| 下午 1 | 3. dry-run + 4. 性能指标 | 1h15 |
| 下午 2 | 5. CI 检查 + 6. 错误码 | 1h |
| 下午 3 | 全量验证 + 进度档 | 30min |
| **总** | | **4h** |

---

## 📊 最终 v3.7 状态预估

| 维度 | v3.6 | v3.7 |
|------|------|------|
| Progress 实时反馈 | ❌ | ✅ SSE |
| 模板复用 | ❌ (每次传 steps) | ✅ 命名模板 |
| dry-run | ❌ | ✅ preview 模式 |
| 性能指标 | ❌ | ✅ /metrics |
| CI 检查 | ❌ | ✅ 2 脚本 |
| 错误码 | ❌ (只有 message) | ✅ 统一 code |
| 业务能力 | 强 | **生产级** |

---

## 🛡️ 实施前置

- [x] DB 备份 (`pre-v3.6.cde.1780709959.bak`)
- [x] `feature/bo-action-v3` 分支
- [x] 19 Action 稳定 (v3.6)

## 🚦 回滚计划

每个增强独立回滚:
- Progress callback: 删除 `/_chain_stream` 端点 + subflow 改动
- 模板存储: 删除 `subflow_templates` 表 + 端点
- dry-run: 仅 subflow 加 `dry_run` 参数, 删除即可
- 性能指标: 删除 `subflow_metrics.py` + `/_subflow_metrics` 端点
- CI 检查: 脚本可随时禁用
- 错误码: 后端加 `code` 字段是**额外**, 不影响老调用

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-06 | C+D+E 剩余 6 项详细 spec |
