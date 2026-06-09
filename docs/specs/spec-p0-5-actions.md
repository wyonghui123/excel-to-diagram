## 目录

1. [📋 5 个 Action 实施清单](#-5-个-action-实施清单)
2. [🏗️ 基础设施扩展：bo_action_api.py 支持文件流](#-基础设施扩展：bo_action_apipy-支持文件流)
3. [📦 5 个 Action 详细设计](#-5-个-action-详细设计)
4. [🛠️ 详细实施步骤](#-详细实施步骤)
5. [🧪 E2E 测试清单](#-e2e-测试清单)
6. [📊 总工时分解](#-总工时分解)
7. [⚠️ 风险与缓解](#-风险与缓解)
8. [📂 产出清单](#-产出清单)
9. [🛡️ 实施前置条件](#-实施前置条件)
10. [🚦 回滚计划](#-回滚计划)
11. [变更记录](#变更记录)

---
# Spec: BO Action 体系扩展 P0 5 个 Action 详细设计

> **日期**: 2026-06-05
> **作者**: AI Agent (Trae) — 基于深入代码调研
> **目的**: 方案 C 实施 — 5 个 BO Action（含 audit.export 文件流扩展）
> **总工时**: 4-5 小时

---

## 📋 5 个 Action 实施清单

| # | Action | 端点路径 | 复杂度 | 现有 service | 工时 |
|---|--------|----------|:---:|------|:---:|
| 1 | `user.reset_password` | `/api/v2/action/user.reset_password` | 🟡 中 | 复用 `_hash_password` | 30min |
| 2 | `audit.retry` | `/api/v2/action/audit.retry` | 🟢 极简 | `audit_service.retry_failed_record` | 30min |
| 3 | `audit.export` | `/api/v2/action/audit.export` | 🟠 中（**含文件流扩展**）| `audit_service.export_audit_log` | 1.5h |
| 4 | `batch_delete` | `/api/v2/action/batch_delete` | 🟡 中（**通用**）| `manage_service.batch_delete` | 1h |
| 5 | `subscription.create` | `/api/v2/action/subscription.create` | 🟡 中 | 直接 `ds.insert` | 1h |

**新增基础设施**: `bo_action_api.py` 扩展 `file_response` 支持（1h，含在 #3 工时内）

---

## 🏗️ 基础设施扩展：bo_action_api.py 支持文件流

### 当前限制

`bo_action_api.py:107-130` 当前 `execute_action` 仅支持 JSON 返回：
```python
return jsonify(result), status_code
```

### 需要扩展

Action handler 返回 `Dict`（JSON）或特殊值（文件流）。

### 设计：handler 返回类型扩展

```python
# 新增 ActionResult 协议
@dataclass
class ActionResult:
    success: bool
    data: Any = None
    message: str = ''
    # 🆕 新增: 文件流支持
    file_data: Optional[bytes] = None
    file_mimetype: Optional[str] = None  # e.g. 'text/csv', 'application/vnd.ms-excel'
    file_filename: Optional[str] = None  # e.g. 'audit_logs_20260605.csv'
```

### 修改点

**文件**: [meta/api/bo_action_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_action_api.py)

1. **新增** `ActionResult` dataclass（与 `dict` 返回向后兼容）
2. **新增** `bo_action_registry.register()` 支持 `return_type` 参数（默认 'json'）
3. **修改** `execute_action()` 检测返回类型：
   - `dict` → `jsonify`（现状）
   - `ActionResult` 且 `file_data` → `Response(file_data, mimetype=..., headers={'Content-Disposition': ...})`
4. **handler** 用 `return ActionResult(success=True, file_data=..., file_mimetype='text/csv', file_filename=...)`

### 兼容性

- 老 handler `return dict` 100% 兼容
- 新 handler 可选择性用 `ActionResult`
- 前端 `useBoAction.callGet()` 检测 `response.headers.get('Content-Type')`：
  - `application/json` → 现有 `resp.json()` 流程
  - `text/csv` / `application/vnd.ms-excel` → `resp.blob()` 下载流程

---

## 📦 5 个 Action 详细设计

### 1️⃣ user.reset_password

#### API 契约
```http
POST /api/v2/action/user.reset_password
Content-Type: application/json
Cookie: auth_token=...

{
  "user_id": 123,
  "new_password": "new_pwd_123"
}
```

#### 响应（成功）
```json
{
  "success": true,
  "data": {
    "user_id": 123,
    "reset_by": "admin",
    "must_change_password": true
  },
  "message": "密码重置成功，用户下次登录需修改密码"
}
```

#### 响应（失败）
| 场景 | message | status |
|------|---------|:---:|
| 非 admin | "需要管理员权限" | 403 |
| 新密码 < 6 位 | "新密码长度不能少于6位" | 200 (false) |
| 用户不存在 | "用户不存在" | 200 (false) |

#### Handler 业务逻辑
```python
def user_reset_password_handler(params, context):
    # 1. 鉴权: 必须 admin
    if not is_admin():
        return {'success': False, 'data': None, 'message': '需要管理员权限'}

    # 2. 参数校验
    user_id = params.get('user_id')
    new_password = params.get('new_password', '')
    if not new_password or len(new_password) < 6:
        return {'success': False, 'data': None, 'message': '新密码长度不能少于6位'}

    # 3. 查用户
    cursor = _data_source.execute("SELECT username FROM users WHERE id = ?", [user_id])
    row = cursor.fetchone()
    if not row:
        return {'success': False, 'data': None, 'message': '用户不存在'}

    # 4. 写新密码
    password_hash = _hash_password_pbdkdf2(new_password)
    with _data_source.transaction():
        _data_source.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
            [password_hash, user_id]
        )

    # 5. 写审计日志 (复用 user_api.py:483-489 模式)
    operator_id = context.get('user_id')
    operator_name = context.get('user_name')
    ip_addr = context.get('ip_address')
    _data_source.execute(
        """INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name,
           field_name, new_data, ip_address, created_at, log_category, log_level)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'security', 'INFO')""",
        ['user', user_id, 'RESET_PASSWORD', operator_id, operator_name,
         'password_hash', f'reset by {operator_name}', ip_addr]
    )

    return {
        'success': True,
        'data': {'user_id': user_id, 'must_change_password': True},
        'message': '密码重置成功，用户下次登录需修改密码'
    }
```

#### 文件位置
- `meta/services/user_reset_password.py`（新建）

#### 风险
- 🟢 低：纯 admin 操作，与 user_api.py:446-491 业务逻辑完全一致
- 🟢 低：审计日志格式一致

---

### 2️⃣ audit.retry

#### API 契约
```http
POST /api/v2/action/audit.retry
Content-Type: application/json
Cookie: auth_token=...

{
  "record_id": 12345
}
```

#### 响应
```json
{
  "success": true,
  "data": {
    "record_id": 12345,
    "new_status": "written",
    "retry_count": 2
  },
  "message": "重试成功，状态已更新为written"
}
```

#### Handler（直接调 service）
```python
def audit_retry_handler(params, context):
    # 1. admin 鉴权
    if not is_admin():
        return {'success': False, 'data': None, 'message': '需要管理员权限'}

    # 2. 取参数
    record_id = params.get('record_id')
    if not record_id:
        return {'success': False, 'data': None, 'message': 'record_id 必填'}

    # 3. 调 service
    from meta.services.audit_service import AuditService
    audit_service = get_audit_service()
    result = audit_service.retry_failed_record(record_id)

    if not result.get('success'):
        return {'success': False, 'data': None, 'message': result.get('message', '重试失败')}

    return {
        'success': True,
        'data': {
            'record_id': record_id,
            'new_status': 'written',
        },
        'message': result.get('message', '重试成功')
    }
```

#### 文件位置
- `meta/services/audit_retry.py`（新建）

#### 风险
- 🟢 低：直接调现有 service，复用 retry_failed_record

---

### 3️⃣ audit.export（**含文件流扩展**）

#### 基础设施扩展（前置）
**必须先扩展 `bo_action_api.py`**：见上文「🏗️ 基础设施扩展」

#### API 契约
```http
POST /api/v2/action/audit.export
Content-Type: application/json
Cookie: auth_token=...

{
  "action": "",                  // 操作类型过滤
  "object_type": "",              // 对象类型过滤
  "user_name": "",                // 用户名 LIKE 匹配
  "start_date": "2026-06-01",     // 起始日期
  "end_date": "2026-06-05",       // 结束日期
  "format": "xlsx"                // xlsx | csv
}
```

#### 响应（**文件流**）
```
HTTP/1.1 200 OK
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename=audit_logs_20260605_143000.xlsx

[二进制 xlsx 数据]
```

#### Handler 实现
```python
def audit_export_handler(params, context):
    # 1. admin 鉴权
    if not is_admin():
        return {'success': False, 'data': None, 'message': '需要管理员权限'}

    # 2. 构造 query
    from meta.services.audit_service import AuditQuery, AuditService
    query = AuditQuery(
        action=params.get('action', ''),
        object_type=params.get('object_type', ''),
        user_name=params.get('user_name', ''),
        start_date=params.get('start_date', ''),
        end_date=params.get('end_date', ''),
    )
    format_type = params.get('format', 'xlsx')

    # 3. 调 service 生成文件
    audit_service = get_audit_service()
    file_path = audit_service.export_audit_log(query, format=format_type)

    # 4. 读文件为字节流
    import os
    with open(file_path, 'rb') as f:
        file_data = f.read()

    # 5. 删临时文件 (可选)
    try:
        os.remove(file_path)
    except OSError:
        pass

    # 6. 返回 ActionResult (文件流)
    from meta.api.bo_action_api import ActionResult
    if format_type == 'xlsx':
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        mimetype = 'text/csv'
    filename = f'audit_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.{format_type}'

    return ActionResult(
        success=True,
        data={'filename': filename, 'size_bytes': len(file_data)},
        message='导出成功',
        file_data=file_data,
        file_mimetype=mimetype,
        file_filename=filename,
    )
```

#### 文件位置
- `meta/services/audit_export.py`（新建）

#### 风险
- 🟡 中：**需先扩展 bo_action_api.py**
- 🟢 低：service 现有 export_audit_log 写 xlsx 到 disk（已验证 864-880 行）

---

### 4️⃣ batch_delete（**通用**）

#### API 契约
```http
POST /api/v2/action/batch_delete
Content-Type: application/json
Cookie: auth_token=...

{
  "object_type": "user",
  "ids": [1, 2, 3],
  "force": false
}
```

#### 响应
```json
{
  "success": true,
  "data": {
    "object_type": "user",
    "total": 3,
    "success_count": 3,
    "failed_count": 0,
    "results": [
      {"id": 1, "success": true, "message": "已删除"},
      {"id": 2, "success": true, "message": "已删除"},
      {"id": 3, "success": true, "message": "已删除"}
    ]
  },
  "message": "成功删除 3 项"
}
```

#### Handler
```python
def batch_delete_handler(params, context):
    # 1. 鉴权 (调 BO 内部权限)
    object_type = params.get('object_type')
    if not object_type:
        return {'success': False, 'data': None, 'message': 'object_type 必填'}
    ids = params.get('ids', [])
    if not ids:
        return {'success': True, 'data': {
            'total': 0, 'success_count': 0, 'failed_count': 0, 'results': []
        }, 'message': '没有要删除的项'}
    force = params.get('force', False)

    # 2. 设置用户上下文 (审计用)
    _set_user_context()

    # 3. 调 manage_service
    from meta.services.manage_service import ManageService
    manage = ManageService(_data_source)
    result = manage.batch_delete(object_type, ids, force)

    return {
        'success': result.failed_count == 0,
        'data': {
            'object_type': object_type,
            'total': len(ids),
            'success_count': result.success_count,
            'failed_count': result.failed_count,
            'results': [r.to_dict() if hasattr(r, 'to_dict') else
                        {'success': getattr(r, 'success', True),
                         'data': getattr(r, 'data', None),
                         'message': getattr(r, 'message', ''),
                         'error': getattr(r, 'error', None)} for r in result.results],
            'errors': getattr(result, 'errors', []),
        },
        'message': f"成功删除 {result.success_count} 项，失败 {result.failed_count} 项"
    }
```

#### 文件位置
- `meta/services/batch_delete.py`（新建）

#### 风险
- 🟡 中：**删除不可逆**——但与 manage_api.py:984-998 完全一致
- 🟢 低：与 batch_save 完全对称

---

### 5️⃣ subscription.create

#### API 契约
```http
POST /api/v2/action/subscription.create
Content-Type: application/json
Cookie: auth_token=...

{
  "object_type": "user",
  "event_types": ["created", "updated", "deleted"],
  "channel": "websocket",          // websocket | webhook
  "webhook_url": "",               // webhook 必填
  "webhook_secret": "",            // 可选
  "filter_condition": {}           // 可选
}
```

#### 响应
```json
{
  "success": true,
  "data": {
    "subscription_id": 100,
    "object_type": "user",
    "channel": "websocket"
  },
  "message": "订阅创建成功"
}
```

#### Handler
```python
def subscription_create_handler(params, context):
    # 1. 鉴权: 必须登录
    user_info = g.current_user if hasattr(g, 'current_user') else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}
    user_id = user_info.get('user_id')

    # 2. 校验
    object_type = params.get('object_type')
    if not object_type:
        return {'success': False, 'data': None, 'message': 'object_type 必填'}

    channel = params.get('channel', 'websocket')
    if channel == 'webhook' and not params.get('webhook_url'):
        return {'success': False, 'data': None, 'message': 'webhook 模式必须提供 webhook_url'}

    # 3. 构造订阅
    import json
    subscription = {
        'user_id': user_id,
        'object_type': object_type,
        'event_types': json.dumps(params.get('event_types', ['created', 'updated', 'deleted'])),
        'channel': channel,
        'webhook_url': params.get('webhook_url', ''),
        'webhook_secret': params.get('webhook_secret', ''),
        'filter_condition': json.dumps(params.get('filter_condition', {})),
        'enabled': 1,
        'created_at': datetime.now().isoformat(),
    }

    # 4. 写库
    sub_id = _data_source.insert('change_subscriptions', subscription)

    return {
        'success': True,
        'data': {
            'subscription_id': sub_id,
            'object_type': object_type,
            'channel': channel,
        },
        'message': '订阅创建成功'
    }
```

#### 文件位置
- `meta/services/subscription_create.py`（新建）

#### 风险
- 🟢 低：纯插入，逻辑与 notification_api.py:190-235 完全一致
- 🟢 低：仅登录鉴权（非 admin）

---

## 🛠️ 详细实施步骤

### Step 1: 扩展 bo_action_api.py 支持文件流（45min）

```python
# 在 bo_action_api.py 顶部添加:
from dataclasses import dataclass
from typing import Optional

@dataclass
class ActionResult:
    success: bool
    data: Any = None
    message: str = ''
    file_data: Optional[bytes] = None
    file_mimetype: Optional[str] = None
    file_filename: Optional[str] = None
```

```python
# 修改 execute_action:
result = bo_action_registry.call(action_id, params, context)

# 🆕 文件流支持
if isinstance(result, ActionResult) and result.file_data:
    from flask import Response
    return Response(
        result.file_data,
        mimetype=result.file_mimetype or 'application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename={result.file_filename or "download.bin"}',
            'X-Action-Success': str(result.success),
        },
        status=200,
    )

# 现有 JSON 路径
duration_ms = (time.time() - start) * 1000
...
```

### Step 2: 5 个 service 文件（2-3h）

按上文章节**逐个**创建：
- `meta/services/user_reset_password.py`
- `meta/services/audit_retry.py`
- `meta/services/audit_export.py`
- `meta/services/batch_delete.py`
- `meta/services/subscription_create.py`

### Step 3: server.py 注册 5 个 Action（15min）

在现有 6 个 Action 注册后追加：
```python
from meta.services.user_reset_password import user_reset_password_handler
from meta.services.audit_retry import audit_retry_handler
from meta.services.audit_export import audit_export_handler
from meta.services.batch_delete import batch_delete_handler
from meta.services.subscription_create import subscription_create_handler

bo_action_registry.register('user.reset_password', user_reset_password_handler, ...)
bo_action_registry.register('audit.retry', audit_retry_handler, ...)
bo_action_registry.register('audit.export', audit_export_handler, ...)
bo_action_registry.register('batch_delete', batch_delete_handler, ...)
bo_action_registry.register('subscription.create', subscription_create_handler, ...)

# 最终验证
_bo_logger.info(f"[BO Action] Registered {len(bo_action_registry.list_ids())} business action(s)")
```

### Step 4: 重启 + 验证（30min）

- `service_manager.ps1 stop && start`
- `_health` 检查注册数 = 11（6 + 5）
- 逐个 E2E 测试

### Step 5: 端到端测试（1h）

每个 Action 8-10 个测试用例：
- 鉴权（无登录 / 普通用户 / admin）
- 必填参数缺失
- 业务校验
- 成功路径
- 边界场景

---

## 🧪 E2E 测试清单

### Test 1: user.reset_password
| # | 场景 | 期望 |
|---|------|------|
| 1 | admin 重置 admin 自己密码 | success, must_change_password=1 |
| 2 | admin 重置非 admin 用户密码 | success |
| 3 | 普通用户尝试重置 | 403 |
| 4 | 不存在的 user_id | "用户不存在" |
| 5 | new_password < 6 位 | "新密码长度不能少于6位" |
| 6 | 缺 new_password | "新密码长度不能少于6位" |
| 7 | 重置后 audit_logs 记录 | 1 条 RESET_PASSWORD |
| 8 | 重置后该用户 login 需要 must_change | 登录后 must_change_password=1 |

### Test 2: audit.retry
| # | 场景 | 期望 |
|---|------|------|
| 1 | 重置不存在 record_id | "记录不存在" |
| 2 | 重置非 failed 状态的 record | "记录状态不是failed" |
| 3 | admin 重置 failed record | success, status→written |
| 4 | 普通用户尝试 | 403 |
| 5 | 无登录 | 401 |
| 6 | retry_count 累加 | retry_count + 1 |

### Test 3: audit.export
| # | 场景 | 期望 |
|---|------|------|
| 1 | admin 导出 xlsx | 200, file_data 是 xlsx 字节 |
| 2 | admin 导出 csv | 200, file_data 是 csv 文本 |
| 3 | 普通用户尝试 | 403 |
| 4 | 无登录 | 401 |
| 5 | start_date/end_date 过滤 | 文件包含范围数据 |
| 6 | object_type 过滤 | 文件只含该类型 |
| 7 | 大数据集 (1万条) | 正常返回 |
| 8 | Content-Disposition header | filename=audit_logs_*.xlsx |

### Test 4: batch_delete
| # | 场景 | 期望 |
|---|------|------|
| 1 | 普通用户尝试 user batch_delete | 403 |
| 2 | admin 删除 1 个 user | success_count=1 |
| 3 | admin 删除混合 (存在+不存在) | partial success |
| 4 | force=true 强制删除有引用的 | success |
| 5 | ids=[] | "没有要删除的项" |
| 6 | 缺 object_type | "object_type 必填" |
| 7 | 无登录 | 401 |
| 8 | 删除后 audit_logs 记录 | N 条 DELETE |

### Test 5: subscription.create
| # | 场景 | 期望 |
|---|------|------|
| 1 | admin 创建 user/websocket 订阅 | success, sub_id |
| 2 | 创建 user/webhook 订阅（带 url） | success |
| 3 | 创建 webhook 订阅（无 url） | "webhook_url is required" |
| 4 | 缺 object_type | "object_type 必填" |
| 5 | 普通用户创建自己的订阅 | success |
| 6 | 跨用户创建订阅（强制 user_id） | 忽略外部 user_id，使用登录用户 |
| 7 | 重复创建 (相同 user+object+channel) | success（不查重，行为与现状一致） |
| 8 | 无登录 | 401 |

---

## 📊 总工时分解

| 步骤 | 任务 | 工时 |
|------|------|:---:|
| 1 | 扩展 bo_action_api.py (file_response) | 45min |
| 2 | user_reset_password.py + E2E | 45min |
| 3 | audit_retry.py + E2E | 45min |
| 4 | audit_export.py + E2E | 45min |
| 5 | batch_delete.py + E2E | 45min |
| 6 | subscription_create.py + E2E | 45min |
| 7 | server.py 注册 + 重启 + 总验证 | 15min |
| **总计** | | **4.75h** |

---

## ⚠️ 风险与缓解

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| `bo_action_api.py` 文件流扩展破坏现有 6 个 Action | 🟡 中 | 严格条件判断 `isinstance(result, ActionResult) and result.file_data` |
| `audit.export` 文件流返回可能大（10000 条） | 🟢 低 | 已限制 10000 条，xlsx 约 ~500KB |
| `batch_delete` 误删 | 🟡 中 | 与现状完全一致，无新风险 |
| `subscription.create` 数据库 schema 假设 | 🟢 低 | 直接复用 notification_api.py 模式 |
| service 文件 `_data_source` 引用 | 🟢 低 | 复用 user_logout 等已有 pattern |

---

## 📂 产出清单

### 新建（5 个 service + 进度）
| 文件 | 估计行数 |
|------|:---:|
| `meta/services/user_reset_password.py` | ~75 |
| `meta/services/audit_retry.py` | ~50 |
| `meta/services/audit_export.py` | ~80 |
| `meta/services/batch_delete.py` | ~70 |
| `meta/services/subscription_create.py` | ~80 |
| `docs/progress/bo-action-p0-5-result.md` | 进度 |

### 修改（2 个）
| 文件 | 改动 |
|------|------|
| `meta/api/bo_action_api.py` | +30 行 (ActionResult + file_response) |
| `meta/server.py` | +30 行 (注册 5 Action) |

### 验证
- 11 个 Action E2E 全通过
- 现有 6 个 Action **不受影响**

---

## 🛡️ 实施前置条件

- [x] 当前 `feature/bo-action-v3` 分支
- [ ] DB 备份（实施前 1 次，参考 `pre-corrupt-fix.1780673774.bak`）
- [x] 服务重启机制验证（Round 1-3 已验证 6 次重启 OK）
- [x] E2E 测试脚本模板（已验证 4 套）
- [x] V2 BO API 端点保留（**不删除**老 endpoint）

---

## 🚦 回滚计划

每个 Action 可独立回滚：
- 删除 `meta/services/X.py`
- 删除 server.py 注册行
- 重启服务
- 该 Action 不再注册，但**老端点继续工作**（无功能损失）

bo_action_api.py 文件流扩展回滚：
- 删除 ActionResult dataclass
- 删除 file_response 分支
- 重启服务
- **现有 6 个 Action 不受影响**（未用 ActionResult）

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-05 | 创建详细 spec (5 Action + 文件流扩展) |
