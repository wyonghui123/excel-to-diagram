# Phase 15 子 Spec: 统一日志架构 M4-M6 细化方案

> **父 Spec**: [unified-metadata-api-architecture/spec.md](../unified-metadata-api-architecture/spec.md) → 十四、Phase 15
> **创建日期**: 2026-05-18
> **更新日期**: 2026-05-19
> **当前状态**: ✅ Phase 15 已完成 100% — M1-M6 全部交付，106+9 测试零回归

---

## 一、背景

### 1.1 已完成 (M1-M3, 59%)

| 里程碑 | 任务数 | 状态 | 测试 |
|--------|--------|------|------|
| M1: 枚举与数据结构 | 7 | ✅ | 36 tests |
| M2: StructuredLogger 核心 | 8 | ✅ | 18 tests |
| M3: 数据库扩展 | 8 | ✅ | 12 tests |

**核心交付物**：[`structured_logger.py`](file:///d:/filework/excel-to-diagram/meta/services/structured_logger.py) — 5种日志类型方法 + 异步写入，业务/安全日志写入 `audit_logs` 表。

### 1.2 关键问题（深度审计发现）

| 问题 | 严重度 | 说明 |
|------|--------|------|
| OPERATION/PERFORMANCE/SYSTEM 日志仅 print() 未持久化 | 🔴 高 | `_log_operation`/`_log_performance`/`_log_system` 不写数据库 |
| 3个专用拦截器不存在 | 🔴 高 | `business_log_interceptor.py` / `security_log_interceptor.py` / `operation_log_interceptor.py` 均为空 |
| 后端 API 不支持 log_category/log_level 过滤 | 🔴 高 | 前端已传参数，后端不接收 |
| 前端无统计图表 | 🟡 中 | 后端 `/audit/overview` 接口已存在，前端未消费 |
| LogRouter 不存在 | 🟡 中 | 当前 `log()` 方法内 if-elif 硬编码路由 |
| log_sources.yaml 不存在 | 🟢 低 | 配置化管理待建立 |

---

## 二、目标

1. **M4**: 为 OPERATION/PERFORMANCE/SYSTEM 三种日志类型补齐持久化写入
2. **M5**: 创建 3 个专用日志拦截器，注入 CRUD 生命周期
3. **M6**: 前端审计页面增强 + 后端 API 补齐 + 端到端集成测试

---

## 三、M4: 补齐三种日志类型的持久化写入

### 3.1 当前状态

| 日志类型 | 当前行为 | 目标 |
|----------|---------|------|
| BUSINESS | ✅ 写入 audit_logs 表 (via AuditService) | 不变 |
| SECURITY | ✅ 写入 audit_logs 表 (via AuditService) | 不变 |
| **OPERATION** | ❌ 仅 `print()` | 写入 audit_logs 表 |
| **PERFORMANCE** | ❌ 仅 `print()` | 写入 audit_logs 表 |
| **SYSTEM** | ❌ 仅 `print()` | 写入 audit_logs 表 |

### 3.2 改动文件

**文件**: [`structured_logger.py`](file:///d:/filework/excel-to-diagram/meta/services/structured_logger.py)

三个内部方法替换 `print()` 为 `_write_to_audit_logs()` 调用：

```python
# L547-L552: _log_operation → 写入 audit_logs
def _log_operation(self, entry):
    return self._write_to_audit_logs(entry)

# L554-L559: _log_performance → 写入 audit_logs
def _log_performance(self, entry):
    return self._write_to_audit_logs(entry)

# L561-L566: _log_system → 写入 audit_logs
def _log_system(self, entry):
    return self._write_to_audit_logs(entry)
```

**验证**: 运行现有 `test_structured_logger.py`，确认三种日志类型的 `_write_to_audit_logs` 调用成功。

---

## 四、M5: 创建 3 个专用日志拦截器

### 4.1 目标

创建可插拔的 BO Framework 拦截器，在 CRUD 生命周期中自动记录结构化日志。

### 4.2 现有拦截器参考

已有 12 个拦截器在 [`meta/core/interceptors/`](file:///d:/filework/excel-to-diagram/meta/core/interceptors/) 下，以 [`audit_interceptor.py`](file:///d:/filework/excel-to-diagram/meta/core/interceptors/audit_interceptor.py) 为模板。

**拦截器基类接口**（[`base.py`](file:///d:/filework/excel-to-diagram/meta/core/interceptors/base.py)）：

```python
class Interceptor:
    async def on_before_create(self, context): pass
    async def on_after_create(self, context): pass
    async def on_before_update(self, context): pass
    async def on_after_update(self, context): pass
    async def on_before_delete(self, context): pass
    async def on_after_delete(self, context): pass
```

### 4.3 文件清单

| # | 新建文件 | 职责 | 触发时机 |
|---|---------|------|---------|
| 1 | `interceptors/business_log_interceptor.py` | 业务操作日志 | on_after_create/update/delete |
| 2 | `interceptors/security_log_interceptor.py` | 安全事件日志 | on_after_create（用户/角色/权限变更时） |
| 3 | `interceptors/operation_log_interceptor.py` | 运维操作日志 | on_after_create/update/delete（管理员操作时） |

### 4.4 business_log_interceptor 详细设计

```python
class BusinessLogInterceptor:
    def on_after_create(self, context):
        structured_logger.log_business(
            action='CREATE',
            object_type=context.object_type,
            object_id=context.result.get('id'),
            user_id=context.user_id,
            user_name=context.user_name,
            new_data=self._sanitize(context.result),
            ip_address=context.request_ip,
            trace_id=context.trace_id
        )
    # on_after_update / on_after_delete 同理，增加 old_data 参数
```

### 4.5 security_log_interceptor 详细设计

触发条件：用户(`user`)/角色(`role`)/权限(`permission`)/用户组(`user_group`)创建时记录安全事件。

```python
class SecurityLogInterceptor:
    SECURITY_OBJECT_TYPES = {'user', 'role', 'permission', 'user_group'}
    
    def on_after_create(self, context):
        if context.object_type not in self.SECURITY_OBJECT_TYPES:
            return
        structured_logger.log_security(
            event_type='ENTITY_CREATED',
            severity='WARNING' if context.object_type == 'permission' else 'INFO',
            user_id=context.user_id,
            source_ip=context.request_ip
        )
    def on_after_delete(self, context):
        if context.object_type not in self.SECURITY_OBJECT_TYPES:
            return
        structured_logger.log_security(
            event_type='ENTITY_DELETED',
            severity='HIGH',
            user_id=context.user_id,
            source_ip=context.request_ip
        )
```

### 4.6 注册到拦截器链

在 [`interceptors/__init__.py`](file:///d:/filework/excel-to-diagram/meta/core/interceptors/__init__.py) 中注册三个新拦截器到 BOEngine 的拦截器链。

### 4.7 测试文件

| # | 新建测试文件 | 覆盖内容 |
|---|-------------|---------|
| 1 | `meta/tests/test_business_log_interceptor.py` | 拦截器注册、on_after_create/update/delete 触发日志 |
| 2 | `meta/tests/test_security_log_interceptor.py` | 安全日志在用户/角色/权限变更时触发 |
| 3 | `meta/tests/test_operation_log_interceptor.py` | 管理员操作日志记录 |

---

## 五、M6: 集成完成

### 5.1 后端 API 补齐：支持 log_category/log_level 过滤

**文件**: [`audit_api.py`](file:///d:/filework/excel-to-diagram/meta/api/audit_api.py) (L92-L191)

当前 `/api/v1/audit/logs` 端点不接收 `log_category` 和 `log_level` 查询参数。

**改动**:
```python
# 新增参数解析
log_category = request.args.get('log_category')
log_level = request.args.get('log_level')

# SQL WHERE 追加
if log_category:
    conditions.append("log_category = ?")
    params.append(log_category)
if log_level:
    conditions.append("log_level = ?")
    params.append(log_level)
```

### 5.2 前端审计页面增强

**文件**: [`AuditLogManagement.vue`](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/AuditLogManagement.vue)

| # | 增强项 | 说明 |
|---|--------|------|
| 1 | 统计概览卡片 | 消费 `GET /api/v1/audit/overview`，4 卡片：今日操作数、安全事件数、错误数、总日志数 |
| 2 | log_type 分布饼图 | 按 log_category（business/security/operation/performance/system）分布 |
| 3 | 操作趋势折线图 | 近 7/30 天操作趋势 |
| 4 | 验证 log_category/log_level 过滤列生效 | 需后端 API 先补齐（见 5.1） |

### 5.3 LogRouter（可选，最低优先级）

**现状**: `log()` 方法内 if-elif 硬编码 5 分支路由。

**目标**: 创建 `meta/core/log_router.py`：

```python
class LogRouter:
    def __init__(self):
        self._handlers = {}
    
    def register(self, category, handler):
        self._handlers[category] = handler
    
    def route(self, entry):
        handler = self._handlers.get(entry.category)
        if handler:
            return handler(entry)
        raise UnsupportedLogCategory(f"No handler for {entry.category}")
```

### 5.4 log_sources.yaml（可选，低优先级）

定义日志源配置，声明哪些模块/拦截器产生什么类型的日志。

```yaml
sources:
  - name: business_log_interceptor
    category: business
    object_types: ["*"]
    events: [create, update, delete]
  - name: security_log_interceptor
    category: security
    object_types: [user, role, permission, user_group]
    events: [create, delete]
```

### 5.5 端到端测试

新增 [`test_log_e2e.py`](file:///d:/filework/excel-to-diagram/meta/tests/test_log_e2e.py)：

| # | 测试场景 |
|---|---------|
| 1 | 创建业务对象 → audit_logs 表中产生 BUSINESS 类型日志 |
| 2 | 创建用户 → audit_logs 表中产生 SECURITY 类型日志 |
| 3 | 管理员删除记录 → audit_logs 表中产生 OPERATION 类型日志 |
| 4 | API 过滤：按 log_category=security 查询返回仅安全日志 |
| 5 | API 过滤：按 log_level=HIGH 查询返回仅 HIGH 级别日志 |

---

## 六、实施计划（5 个里程碑）

| 里程碑 | 内容 | 产出 | 预估 |
|--------|------|------|------|
| **M4** | 补齐 OPERATION/PERFORMANCE/SYSTEM 持久化 | `structured_logger.py` 修改 | 5 行代码改动 |
| **M5a** | 创建 business_log_interceptor | `interceptors/business_log_interceptor.py` + 测试 | ~80 行 |
| **M5b** | 创建 security_log_interceptor | `interceptors/security_log_interceptor.py` + 测试 | ~60 行 |
| **M5c** | 创建 operation_log_interceptor | `interceptors/operation_log_interceptor.py` + 测试 | ~60 行 |
| **M6a** | 后端 API 补齐 log_category/log_level 过滤 | `audit_api.py` 修改 | ~20 行 |
| **M6b** | 前端审计页面统计图表 | `AuditLogManagement.vue` 修改 | ~150 行 |
| **M6c** | 端到端测试 | `test_log_e2e.py` | 5 tests |
| **M6d** | LogRouter + log_sources.yaml（可选） | 2 个新文件 | ~100 行 |

---

## 七、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `meta/services/structured_logger.py` | 修改 | 3 个内部方法 print→写入 audit_logs |
| `meta/core/interceptors/business_log_interceptor.py` | **新建** | CRUD 业务日志拦截器 |
| `meta/core/interceptors/security_log_interceptor.py` | **新建** | 安全事件日志拦截器 |
| `meta/core/interceptors/operation_log_interceptor.py` | **新建** | 运维操作日志拦截器 |
| `meta/core/interceptors/__init__.py` | 修改 | 注册 3 个新拦截器 |
| `meta/api/audit_api.py` | 修改 | 支持 log_category/log_level 过滤 |
| `src/views/SystemManagement/AuditLogManagement.vue` | 修改 | 统计图表 + 过滤列验证 |
| `meta/tests/test_business_log_interceptor.py` | **新建** | 拦截器测试 |
| `meta/tests/test_security_log_interceptor.py` | **新建** | 拦截器测试 |
| `meta/tests/test_operation_log_interceptor.py` | **新建** | 拦截器测试 |
| `meta/tests/test_log_e2e.py` | **新建** | 端到端测试 |

---

## 八、验收标准

- [ ] OPERATION/PERFORMANCE/SYSTEM 三种日志写入 audit_logs 表不再仅 print
- [ ] 3 个拦截器正确注册到 BOEngine 拦截器链
- [ ] 创建/更新/删除业务对象时自动产生 BUSINESS 日志
- [ ] 创建用户/角色/权限时自动产生 SECURITY 日志
- [ ] 管理员操作产生 OPERATION 日志（含 user_id 标识）
- [ ] `GET /api/v1/audit/logs?log_category=security` 正确过滤
- [ ] 前端审计页面显示统计概览卡片
- [ ] 所有新测试通过，现有测试零回归
