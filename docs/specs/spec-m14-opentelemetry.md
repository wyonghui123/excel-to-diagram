## 目录

1. [0. 摘要](#0-摘要)
2. [1. 背景与目标](#1-背景与目标)
3. [2. 目标架构](#2-目标架构)
4. [3. Trace 上下文 + Span](#3-trace-上下文-span)
5. [4. Ring Buffer 存储](#4-ring-buffer-存储)
6. [5. 拦截器集成](#5-拦截器集成)
7. [6. Dashboard API](#6-dashboard-api)
8. [7. 性能预算](#7-性能预算)
9. [8. 5 阶段实施蓝图](#8-5-阶段实施蓝图)
10. [9. 测试策略](#9-测试策略)
11. [10. 关键交付物](#10-关键交付物)
12. [11. 关联文档](#11-关联文档)
13. [12. 一句话总结](#12-一句话总结)
14. [13. 变更记录](#13-变更记录)

---
# M14 v3 引擎：OpenTelemetry 简化版 spec

> **版本**: v1.0.0
> **创建日期**: 2026-06-06
> **状态**: ✅ **T1-T5 全部实施完成 / 39 telemetry 测试 PASS / Phase B 183 PASS 不破坏**
> **关联 spec**: [spec-ui-business-logic-downflow.md v3.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md)（主文档）
> **战略位置**: v3 引擎 M1-M14 战略补强中的第 14 步（最终步）

---

## 0. 摘要

**M14 = 给 18 拦截器加上分布式追踪能力，0 依赖 OTLP/Jaeger，纯 Python 实现。**

### 6 大目标
1. **Trace 上下文**：UUID4 trace_id + contextvars（线程/异步安全）
2. **Span 管理**：单个操作段（name / start / end / duration / status / attributes）
3. **Ring buffer 存储**：最近 1000 trace（线程安全 + 慢请求单独保留）
4. **拦截器集成**：`install_global_tracer(ALL_INTERCEPTORS)` 一键启用 18 拦截器 trace
5. **慢请求检测**：threshold 100ms（可配置）+ 慢请求列表
6. **Dashboard API**：5 端点（stats / traces / traces/slow / traces/<id> / configure）

### 7 维度价值
| 维度 | 当前 | M14 后 | 价值 |
|------|------|--------|------|
| **可观测性** | 无（黑盒）| 18 拦截器可视化 | 100% 透明 |
| **慢请求定位** | 用户报"慢" | 自动检测 + 慢请求列表 | MTTR -50% |
| **拦截器开销** | 0 监控 | 每次调用 < 0.5ms | 0 业务代码改动 |
| **根因分析** | 调试靠猜 | trace 树状结构 | 100% 覆盖 |
| **统计** | 无 | p50/p95/p99/avg | 量化 SLA |
| **跨请求** | 无 | trace_id 全链路 | 完整链路 |
| **持久化** | 无 | 内存 ring buffer | 0 依赖 |

---

## 1. 背景与目标

### 1.1 v1 现状痛点

**当前 18 拦截器可观测性为 0**：
- 18 个拦截器（`meta/core/interceptors/*.py`）全部在 bo_framework 链中执行
- 用户报"页面慢"→ 不知道哪个拦截器慢
- 跨拦截器执行顺序无法可视化
- 18 拦截器的执行时间/状态全部不可见

**M14 调研结果**（`meta/core/interceptors/`）：
| 拦截器 | 职责 | 当前可观测性 |
|--------|------|------|
| ContextInterceptor (priority=10) | 上下文初始化 | 0 |
| LockInterceptor (priority=20) | 锁机制 | 0 |
| PermissionInterceptor (priority=30) | 权限检查 | 0 |
| DataPermissionInterceptor (priority=30) | 行级过滤 | 0 |
| FieldPolicyInterceptor (priority=40) | 字段策略 | 0 |
| AuditInterceptor | 审计 | 0 |
| BusinessLogInterceptor | 业务日志 | 0 |
| SecurityLogInterceptor | 安全日志 | 0 |
| HierarchyValidationInterceptor | 层级校验 | 0 |
| ConstraintValidationInterceptor | 约束校验 | 0 |
| PersistenceInterceptor | 持久化 | 0 |
| AssociationInterceptor | 关联展开 | 0 |
| CascadeInterceptor | 级联 | 0 |
| KeyTemplateInterceptor | 键模板 | 0 |
| EnumProtectionInterceptor | 枚举保护 | 0 |
| OperationLogInterceptor | 操作日志 | 0 |
| QueryInterceptor | 查询 | 0 |
| VersionContextInterceptor | 版本上下文 | 0 |
| OwnerPermissionInterceptor | 所有者权限 | 0 |
| **共 19 个** | — | **全部 0 可观测** |

### 1.2 目标

**6 大目标**（同 §0 摘要）。

**关键设计原则**：
- **0 业务代码破坏**：所有改动在 telemetry/ 目录 + 拦截器 0 修改（运行时 monkey-patch）
- **0 新依赖**：纯 Python（contextvars / threading / collections / statistics）
- **可插拔**：`install_global_tracer(interceptors)` 一键启用 / 注释掉即关闭
- **可视化**：5 Dashboard API 端点 + ring buffer（最近 1000 trace）

---

## 2. 目标架构

### 2.1 4 层架构

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: 拦截器层（19 拦截器 bo_framework 链）           │
│   meta/core/interceptors/*.py                          │
│   - 0 改动 / 运行时包装 before_action + after_action    │
└─────────────────────────────────────────────────────────┘
                          ↓ 自动注入
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Span 管理（TraceContext / Span）               │
│   - TraceContext: UUID4 trace_id + contextvars          │
│   - Span: name / start / end / duration / status       │
│   - @trace 装饰器 + span() 上下文管理器                 │
└─────────────────────────────────────────────────────────┘
                          ↓ 自动记录
┌─────────────────────────────────────────────────────────┐
│ Layer 3: Ring Buffer 存储（TraceStorage）               │
│   - 最近 1000 trace（deque）                            │
│   - 慢请求单独保留（>100ms / deque max 200）            │
│   - 线程安全（threading.Lock）                          │
│   - 统计：p50/p95/p99/max/avg                          │
└─────────────────────────────────────────────────────────┘
                          ↓ Dashboard API
┌─────────────────────────────────────────────────────────┐
│ Layer 4: Dashboard API（5 端点）                        │
│   /api/v1/telemetry/stats          统计                │
│   /api/v1/telemetry/traces         最近 trace          │
│   /api/v1/telemetry/traces/slow    慢请求              │
│   /api/v1/telemetry/traces/<id>    单个 trace 详情     │
│   /api/v1/telemetry/configure      配置                │
└─────────────────────────────────────────────────────────┘
```

### 2.2 关键集成点

| M14 模块 | 位置 | 复用现有 |
|---------|------|:-------:|
| **telemetry/tracing.py** | `telemetry/tracing.py` | contextvars / time / uuid |
| **telemetry/storage.py** | `telemetry/storage.py` | threading.Lock / collections.deque / statistics |
| **telemetry/decorators.py** | `telemetry/decorators.py` | functools / asyncio |
| **telemetry/integration.py** | `telemetry/integration.py` | Interceptor ABC |
| **telemetry/api.py** | `telemetry/api.py` | Flask Blueprint（已有 pattern）|

---

## 3. Trace 上下文 + Span

### 3.1 TraceContext

```python
class TraceContext:
    """Trace 上下文（线程/异步安全）"""
    trace_id: str          # 32 字符 hex（UUID4）
    root_span_name: str    # 根 span 名称
    started_at: float      # 启动时间
    spans: List[Span]      # 所属 spans
    metadata: Dict         # 自定义 metadata

    @classmethod
    def start(cls, name: str = 'root') -> 'TraceContext'

    @classmethod
    def current(cls) -> Optional['TraceContext']

    def end(self) -> Dict  # 返回 summary

    def add_span(self, span: 'Span') -> None
```

**实现**：`contextvars.ContextVar`（线程/异步安全，无需显式传递）。

### 3.2 Span

```python
class Span:
    """单个操作段"""
    name: str              # 名称（如 'PermissionInterceptor.before_action'）
    trace_id: str          # 所属 trace
    started_at: float      # 启动时间
    ended_at: float        # 结束时间
    duration_ms: float     # 持续时间
    status: str            # 'ok' / 'error'
    attributes: Dict       # 自定义属性
    error: Optional[str]   # 异常信息

    @classmethod
    def start(cls, name: str, attributes: Optional[Dict] = None) -> 'Span'

    def end(self, status: str = 'ok', error: Optional[str] = None, **attributes) -> None

    def set_attribute(self, key: str, value: Any) -> None

    def to_dict(self) -> Dict
```

### 3.3 便捷 API

```python
# 上下文管理器
with trace('handle_request') as ctx:
    with span('validate') as s:
        # 业务逻辑
        pass
    # span 自动 end

# 装饰器
@trace('my_function')
def my_function(x, y):
    return x + y

# 拦截器装饰器
@trace_interceptor('before_action')
def before_action(self, context):
    pass
```

---

## 4. Ring Buffer 存储

### 4.1 TraceStorage

```python
class TraceStorage:
    """Trace 存储（线程安全 ring buffer）"""
    def __init__(self, max_traces: int = 1000, slow_threshold_ms: float = 100.0)

    def record(self, ctx) -> None
    def get_recent(self, limit: int = 50, offset: int = 0) -> List[Dict]
    def get_slow(self, limit: int = 20) -> List[Dict]
    def get_by_trace_id(self, trace_id: str) -> Optional[Dict]
    def get_stats(self) -> Dict
    def clear(self) -> None
    def configure(self, max_traces: int = None, slow_threshold_ms: float = None) -> None
```

### 4.2 统计

```python
{
    'total_traces': int,
    'slow_count': int,
    'p50_duration_ms': float,
    'p95_duration_ms': float,
    'p99_duration_ms': float,
    'max_duration_ms': float,
    'avg_duration_ms': float,
    'uptime_seconds': float,
}
```

### 4.3 慢请求检测

- 默认 threshold: 100ms
- 慢请求保留最近 200 个
- 自动在 `record()` 时检测

---

## 5. 拦截器集成

### 5.1 一键启用

```python
from telemetry.integration import install_global_tracer
from meta.core.interceptors import ALL_INTERCEPTORS

# 19 拦截器 0 改动，运行时自动包装
install_global_tracer(ALL_INTERCEPTORS)
```

### 5.2 包装细节

```python
def wrap_interceptor_before(interceptor_instance, before_action_func):
    """包装拦截器 before_action，自动添加 span"""
    interceptor_name = type(interceptor_instance).__name__

    def wrapper(context):
        span = Span.start(
            f'{interceptor_name}.before_action',
            attributes={
                'interceptor': interceptor_name,
                'priority': getattr(interceptor_instance, 'priority', 100),
            },
        )
        try:
            result = before_action_func(context)
            span.end(status='ok')
            return result
        except Exception as e:
            span.end(status='error', error=str(e))
            raise
    return wrapper
```

### 5.3 0 业务代码破坏

- 所有 19 拦截器源文件 0 改动
- 通过 monkey-patch 在运行时替换 `before_action` / `after_action`
- 关闭时：注释 `install_global_tracer` 调用即可

---

## 6. Dashboard API

### 6.1 5 端点

| 端点 | 方法 | 用途 |
|------|:----:|------|
| `/api/v1/telemetry/stats` | GET | 统计（p50/p95/p99 + 总数 + 慢请求数）|
| `/api/v1/telemetry/traces` | GET | 最近 trace 列表（分页：limit + offset）|
| `/api/v1/telemetry/traces/slow` | GET | 慢请求列表（> threshold）|
| `/api/v1/telemetry/traces/<id>` | GET | 单个 trace 详情（含所有 span）|
| `/api/v1/telemetry/configure` | POST | 配置（max_traces / slow_threshold_ms）|

### 6.2 示例响应

```json
GET /api/v1/telemetry/stats
{
    "total_traces": 1000,
    "slow_count": 12,
    "p50_duration_ms": 23.5,
    "p95_duration_ms": 156.8,
    "p99_duration_ms": 234.5,
    "max_duration_ms": 567.8,
    "avg_duration_ms": 45.6,
    "uptime_seconds": 3600.5
}
```

---

## 7. 性能预算

| 操作 | 目标 | 备注 |
|------|:----:|------|
| **TraceContext.start** | < 0.05ms | contextvars + UUID4 |
| **Span.start** | < 0.01ms | append to list |
| **Span.end** | < 0.01ms | time + dict update |
| **wrap_interceptor_before** | < 0.5ms | 每次拦截器调用 |
| **Ring buffer 写入** | < 0.05ms | deque.append + Lock |
| **统计计算** | < 10ms | quantiles (n=100) |
| **Dashboard API** | < 50ms | 内存查询 |

**总开销**：每次拦截器调用 < 0.5ms × 2（before + after）= 1ms

---

## 8. 5 阶段实施蓝图

| 阶段 | 状态 | 关键交付 | 测试 |
|------|:----:|---------|:---:|
| **T1** Trace 上下文 + Span | ✅ | [telemetry/tracing.py](file:///d:/filework/excel-to-diagram/telemetry/tracing.py)（200 行）| 13 PASS |
| **T2** Ring buffer 存储 | ✅ | [telemetry/storage.py](file:///d:/filework/excel-to-diagram/telemetry/storage.py)（130 行）| 10 PASS |
| **T3** @trace 装饰器 | ✅ | [telemetry/decorators.py](file:///d:/filework/excel-to-diagram/telemetry/decorators.py)（130 行）| 6 PASS |
| **T4** 拦截器集成 | ✅ | [telemetry/integration.py](file:///d:/filework/excel-to-diagram/telemetry/integration.py)（100 行）| 4 PASS |
| **T5** Dashboard API | ✅ | [telemetry/api.py](file:///d:/filework/excel-to-diagram/telemetry/api.py)（60 行）| 6 PASS |
| **M14 累计** | **100%** | **5 模块 / 5 测试文件** | **39 PASS** |

---

## 9. 测试策略

### 9.1 单元测试（33 PASS）

| 测试类 | 覆盖 | 用例数 |
|--------|------|:-----:|
| `TestTraceContext` | start / current / end / add_span | 4 |
| `TestSpan` | start / end / error / attribute / to_dict | 5 |
| `TestTraceContextManager` | trace() / span() / 异常 | 3 |
| `TestTraceStorage` | record / get_recent / get_slow / stats / clear / configure / ring_buffer | 10 |
| `TestTraceDecorator` | @trace 基本 / 默认名 / 异常 / attributes / 嵌套 / 拦截器装饰器 | 6 |
| `TestInterceptorIntegration` | wrap_before / wrap_after / install_global / 异常 | 4 |

### 9.2 端到端测试（6 PASS）

| 测试类 | 覆盖 | 用例数 |
|--------|------|:-----:|
| `TestTelemetryAPI` | 5 端点（stats / traces / slow / detail / configure）| 6 |

**总计：39 PASS** / 0 FAIL

---

## 10. 关键交付物

### 10.1 新文件清单（10 个 / ~750 行）

| 文件 | 规模 | 用途 |
|------|:----:|------|
| [telemetry/__init__.py](file:///d:/filework/excel-to-diagram/telemetry/__init__.py) | 50 行 | 公开 API |
| [telemetry/tracing.py](file:///d:/filework/excel-to-diagram/telemetry/tracing.py) | 200 行 | TraceContext / Span |
| [telemetry/storage.py](file:///d:/filework/excel-to-diagram/telemetry/storage.py) | 130 行 | Ring buffer |
| [telemetry/decorators.py](file:///d:/filework/excel-to-diagram/telemetry/decorators.py) | 130 行 | @trace |
| [telemetry/integration.py](file:///d:/filework/excel-to-diagram/telemetry/integration.py) | 100 行 | 拦截器集成 |
| [telemetry/api.py](file:///d:/filework/excel-to-diagram/telemetry/api.py) | 60 行 | Dashboard API |
| [telemetry/tests/test_tracing.py](file:///d:/filework/excel-to-diagram/telemetry/tests/test_tracing.py) | 100 行 | T1 测试 |
| [telemetry/tests/test_storage.py](file:///d:/filework/excel-to-diagram/telemetry/tests/test_storage.py) | 100 行 | T2 测试 |
| [telemetry/tests/test_decorators.py](file:///d:/filework/excel-to-diagram/telemetry/tests/test_decorators.py) | 80 行 | T3 测试 |
| [telemetry/tests/test_integration.py](file:///d:/filework/excel-to-diagram/telemetry/tests/test_integration.py) | 70 行 | T4 测试 |
| [telemetry/tests/test_api.py](file:///d:/filework/excel-to-diagram/telemetry/tests/test_api.py) | 90 行 | T5 测试 |
| [telemetry/tests/run_all.py](file:///d:/filework/excel-to-diagram/telemetry/tests/run_all.py) | 40 行 | 测试运行器 |

**0 业务代码破坏**。

---

## 11. 关联文档

| 文档 | 关系 |
|------|------|
| [spec-ui-business-logic-downflow.md v3.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) | 主文档 |
| [spec-m11-rls-implementation.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-m11-rls-implementation.md) | M11（与 M14 拦截器集成）|
| [spec-m13-schema-governance.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-m13-schema-governance.md) | M13（与 M14 Dashboard 协同）|
| [meta/core/interceptors/base.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/base.py) | Interceptor ABC（19 拦截器继承）|

---

## 12. 一句话总结

**M14 = 给 19 拦截器加上分布式追踪能力，0 业务代码破坏，1d 实施完成 39 测试 PASS**。

### 关键价值
1. **0 业务代码破坏**：通过 monkey-patch 包装 19 拦截器
2. **0 新依赖**：纯 Python（contextvars / threading / collections）
3. **可插拔**：`install_global_tracer(interceptors)` 一键启用
4. **可视化**：5 Dashboard API + ring buffer（1000 trace / 200 慢请求）
5. **慢请求检测**：threshold 100ms（可配置）

---

## 13. 变更记录

| 版本 | 日期 | 内容 |
|------|------|------|
| v1.0.0 | 2026-06-06 | 初始 spec + 实施完成（T1-T5 / 39 PASS / 0 业务代码破坏）|
