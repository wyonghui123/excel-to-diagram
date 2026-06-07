# API 契约定义 v2.0 (API Contracts)

> **版本**: v2.0.0
> **更新日期**: 2026-05-19
> **状态**: 正式版 (Production Ready)
> **基础路径**: `/api/v2/bo`
> **API 风格**: RESTful + SAP OData V2 ($associations)
> **认证方式**: JWT Bearer Token

---

## 目录

1. [API 总览与设计原则](#一-api-总览与设计原则)
2. [通用规范](#二-通用规范)
3. [Core CRUD API](#三-core-crud-api)
4. [Association API（关联操作）](#四-association-api关联操作)
5. [Value Help API](#五-value-help-api)
6. [Filter Variant API](#六-filter-variant-api)
7. [Meta Data API](#七-meta-data-api)
8. [Import/Export API](#八-importexport-api)
9. [认证与授权](#九-认证与授权)
10. [错误码体系](#十-错误码体系)
11. [版本兼容性（v1 → v2 迁移）](#十-一-版本兼容性v1--v2-迁移)
12. [附录：完整端点清单](#附录完整端点清单)

---

## 一、API 总览与设计原则

### 1.1 API 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        v2 API 端点分类                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │  Core CRUD      │  │  Association    │  │  Value Help     │   │
│  │  (7 endpoints)  │  │  (12 endpoints) │  │  (2 endpoints)  │   │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤   │
│  │ POST /{entity}  │  │ GET /$assoc     │  │ GET /value-help/│   │
│  │ GET /{entity}    │  │ POST /assign    │  │ {type}/{id}     │   │
│  │ PUT /{entity}/id │  │ POST /unassign  │  │ GET /resolve    │   │
│  │ DELETE /id       │  │ POST /batch_*   │  └─────────────────┘   │
│  │ POST /deep       │  │ GET /count      │                         │
│  │ POST /actions    │  │ POST /batch-query│┌─────────────────┐   │
│  │ GET /retrieve    │  └─────────────────┘  │  Filter Variant │   │
│  └─────────────────┘                       │  (5 endpoints)  │   │
│                                            ├─────────────────┤   │
│  ┌─────────────────┐                      │  Meta Data      │   │
│  │  Legacy v1 API  │                      │  (4 endpoints)  │   │
│  │  (向后兼容)     │                      ├─────────────────┤   │
│  ├─────────────────┤                      │  Import/Export  │   │
│  │ /api/v1/{type}  │                      │  (4 endpoints)  │   │
│  └─────────────────┘                      └─────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 设计原则

| 原则 | 说明 | 示例 |
|------|------|------|
| **RESTful** | 使用标准 HTTP 方法 | GET 查询, POST 创建, PUT 更新, DELETE 删除 |
| **SAP OData V2** | 关联操作使用 `$` 前缀 | `/$associations`, `/assign`, `/unassign` |
| **统一响应格式** | 所有端点返回 `{success, data, message}` | 见第二章 |
| **JWT 认证** | Bearer Token 认证 | `Authorization: Bearer <token>` |
| **请求追踪** | 支持 X-Trace-Id 头 | 用于日志关联和调试 |

### 1.3 命名约定

| 类型 | 规范 | 示例 |
|------|------|------|
| **实体名 (Entity)** | snake_case, 单数 | `user`, `role`, `user_group` |
| **关联名 (Association)** | snake_case, 复数 | `roles`, `permissions` |
| **动作名 (Action)** | snake_case | `activate_user`, `lock_user` |
| **查询参数** | snake_case | `page_size`, `sort_by`, `search` |

---

## 二、通用规范

### 2.1 基础 URL

```
生产环境: https://api.example.com/api/v2/bo
开发环境: http://localhost:5000/api/v2/bo
```

### 2.2 请求头

```http
Content-Type: application/json
Authorization: Bearer <jwt_token>
X-User-Id: <user_id>
X-Trace-Id: <trace_id>          # 可选，用于请求追踪
```

### 2.3 统一响应格式

#### 成功响应

```json
{
  "success": true,
  "data": { ... },
  "message": "操作成功"
}
```

#### 列表查询响应（分页）

```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  },
  "message": "查询成功"
}
```

#### 创建成功响应

```json
{
  "success": true,
  "data": {
    "id": 42,
    "username": "new_user",
    ...
  },
  "message": "创建成功"
}
```

HTTP Status Code: **201 Created**

#### 无内容响应（SAP 风格）

对于 assign/unassign 操作，成功时返回 HTTP **204 No Content**（无响应体）。

#### 错误响应

```json
{
  "success": false,
  "error": "错误信息",
  "code": "ERROR_CODE",
  "details": {
    "field": "username",
    "message": "用户名已存在"
  },
  "errors": [...]              // 批量操作时的多个错误
}
```

### 2.4 HTTP 状态码

| 状态码 | 说明 | 使用场景 |
|--------|------|---------|
| **200** | OK | GET/PUT 请求成功 |
| **201** | Created | POST 创建成功 |
| **204** | No Content | assign/unassign 操作成功（SAP 风格） |
| **400** | Bad Request | 参数校验失败、业务规则违反 |
| **401** | Unauthorized | 未登录或 Token 过期 |
| **403** | Forbidden | 无权限访问该资源 |
| **404** | Not Found | 资源不存在 |
| **500** | Internal Server Error | 服务器内部错误 |

### 2.5 分页参数

所有列表接口支持以下分页参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | integer | 1 | 页码（从 1 开始） |
| `page_size` | integer | 20 | 每页数量（最大 100） |
| `_offset` | integer | 0 | 偏移量（高级用法） |
| `_limit` | integer | 20 | 限制数量（高级用法） |

### 2.6 排序参数

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `ordering` | string | 排序字段和方向 | `created_at` 或 `-created_at`（降序） |
| `_order_by` | string | 高级排序（支持多字段） | `name,-created_at` |

**排序方向约定**：
- 无前缀：升序（ASC）
- `-` 前缀：降序（DESC）

**示例**：
```
GET /api/v2/bo/user?ordering=-created_at&page_size=50
```

### 2.7 过滤参数

过滤参数直接作为 Query String 传递：

```
GET /api/v2/bo/user?status=active&role_id=1&keyword=admin
```

支持的过滤类型：

| 过滤类型 | 参数格式 | 示例 |
|---------|---------|------|
| **精确匹配** | `field=value` | `?status=active` |
| **关键词搜索** | `keyword=text` | `?keyword=admin` |
| **范围过滤** | `field__gte=value` | `?created_at__gte=2024-01-01` |
| **列表过滤** | `field__in=v1,v2` | `?status__in=active,inactive` |

---

## 三、Core CRUD API

### 3.1 创建记录

**端点**: `POST /api/v2/bo/{entity}`

**权限**: 需要 `{entity}.create` 权限

**请求体**:
```json
{
  "username": "new_user",
  "email": "user@example.com",
  "status": "active",
  "role_ids": [1, 2]
}
```

**响应** (201):
```json
{
  "success": true,
  "data": {
    "id": 42,
    "username": "new_user",
    "email": "user@example.com",
    "status": "active",
    "created_at": "2026-05-19T10:30:00Z"
  },
  "message": "创建成功"
}
```

**错误示例** (400):
```json
{
  "success": false,
  "error": "用户名已存在",
  "code": "DUPLICATE_KEY"
}
```

**特殊行为**：
- 自动设置 `created_at`, `created_by`, `updated_at`, `updated_by`
- 如果配置了 `audit_aspect`，自动写入审计日志
- 如果字段有 `value_help`，会校验值的有效性
- 如果字段有 `constraints: immutable`，创建后不可修改

---

### 3.2 查询列表 ⭐

**端点**: `GET /api/v2/bo/{entity}`

**权限**: 需要 `{entity}.read` 权限

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | integer | 1 | 页码 |
| `page_size` | integer | 20 | 每页数量 |
| `ordering` | string | - | 排序字段 |
| `keyword` | string | - | 关键词搜索 |
| `{field}` | any | - | 字段精确过滤 |

**请求示例**:
```
GET /api/v2/bo/user?page=1&page_size=50&ordering=-created_at&status=active&keyword=admin
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "username": "admin",
        "email": "admin@example.com",
        "status": "active",
        "display_name": "admin (管理员)",
        "_enriched": true
      },
      {
        "id": 2,
        "username": "user1",
        "email": "user1@example.com",
        "status": "active",
        "display_name": "user1",
        "_enriched": true
      }
    ],
    "total": 150,
    "page": 1,
    "page_size": 50
  },
  "message": "查询成功"
}
```

**数据增强说明** (`_enriched`)：
- 后端会自动执行 EnrichmentEngine，解析关联字段的显示名称
- 例如：`role_id` 字段会额外返回 `role_name: "管理员"`
- 前端可直接使用增强后的数据进行展示

---

### 3.3 查询详情

**端点**: `GET /api/v2/bo/{entity}/{id}`

**权限**: 需要 `{entity}.read` 权限

**URL 参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | integer/string | 记录 ID（支持整数或字符串 ID） |

**请求示例**:
```
GET /api/v2/bo/user/1
GET /api/v2/bo/user/admin_code  # 支持字符串 ID
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "status": "active",
    "created_at": "2026-05-19T10:30:00Z",
    "updated_at": "2026-05-19T14:20:00Z",
    "created_by": null,
    "updated_by": null
  }
}
```

**错误响应** (404):
```json
{
  "success": false,
  "message": "用户不存在"
}
```

---

### 3.4 更新记录

**端点**: `PUT /api/v2/bo/{entity}/{id}`

**权限**: 需要 `{entity}.update` 权限

**请求体**:
```json
{
  "email": "new_email@example.com",
  "status": "inactive"
}
```

**注意**：只需提交要更新的字段，无需提交完整对象。

**响应** (200):
```json
{
  "success": true,
  "data": {
    "id": 1,
    "email": "new_email@example.com",
    "status": "inactive",
    "updated_at": "2026-05-19T15:00:00Z"
  },
  "message": "更新成功"
}
```

**约束检查**：
- 如果字段有 `constraints: immutable`，更新时会拒绝
- 如果字段是 `business_key`，创建后不可修改
- 如果字段是 `readonly`（由系统推导），更新时会忽略

---

### 3.5 删除记录

**端点**: `DELETE /api/v2/bo/{entity}/{id}`

**权限**: 需要 `{entity}.delete` 权限

**请求示例**:
```
DELETE /api/v2/bo/user/99
```

**响应** (200):
```json
{
  "success": true,
  "message": "删除成功"
}
```

**删除前检查**：
- 检查 `deletability.condition`（如果配置）
- 检查是否存在关联子对象（如果配置了 `hierarchy`）
- 检查是否为系统内置对象（`is_system: true`）

---

### 3.6 深度插入（Deep Insert）

**端点**: `POST /api/v2/bo/{entity}/deep`

**权限**: 需要 `{entity}.create` 权限

**说明**：一次性创建主对象及其关联的子对象。

**请求体**:
```json
{
  "code": "PRD001",
  "name": "新产品",
  "versions": [
    {
      "name": "v1.0",
      "version": "1.0.0",
      "is_active": true
    },
    {
      "name": "v2.0",
      "version": "2.0.0",
      "is_active": false
    }
  ]
}
```

**响应** (201):
```json
{
  "success": true,
  "data": {
    "id": 10,
    "code": "PRD001",
    "name": "新产品",
    "child_count": 2,
    "versions": [
      {"id": 101, "name": "v1.0", ...},
      {"id": 102, "name": "v2.0", ...}
    ]
  },
  "message": "深度插入成功"
}
```

**使用场景**：
- 产品 + 版本一次性创建
- 用户组 + 成员批量添加
- 订单 + 订单项一次性创建

---

### 3.7 执行自定义动作

**端点**: `POST /api/v2/bo/{entity}/{id}/actions/{action_id}`

**权限**: 需要动作对应的权限（通常由 rules 定义）

**说明**：执行 YAML 中定义的自定义业务动作（如状态转换）。

**请求体**:
```json
{
  "comment": "激活此用户",
  "params": {}
}
```

**请求示例**:
```
POST /api/v2/bo/user/5/actions/activate_user
POST /api/v2/bo/user/5/actions/lock_user
POST /api/v2/bo/product/10/actions/publish
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "id": 5,
    "status": "active",           // 状态已变更
    "previous_status": "inactive" // 原状态（可选）
  },
  "message": "用户已激活"
}
```

**内部处理流程**：
1. 加载 YAML 中 `rules` 定义的动作配置
2. 执行前置条件检查（`from_states`, `condition`）
3. 执行状态转换逻辑
4. 触发后置钩子（审计日志、通知等）
5. 返回结果

---

### 3.8 深度获取（Retrieve with Associations）

**端点**: `GET /api/v2/bo/{entity}/{id}/retrieve`

**权限**: 需要 `{entity}.read` 权限

**说明**：获取对象详情并内嵌关联数据。

**查询参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `associations` | string | * (所有) | 要加载的关联，逗号分隔。`*` 表示全部 |
| `depth` | integer | 1 | 加载深度（1=直接关联, 2=关联的关联） |

**请求示例**:
```
GET /api/v2/bo/user/1/retrieve?associations=roles,permissions&depth=1
GET /api/v2/bo/product/10/retrieve?associations=*&depth=2
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",

    "_associations": {
      "roles": {
        "items": [
          {"id": 1, "name": "管理员", "code": "admin"},
          {"id": 2, "name": "审核员", "code": "reviewer"}
        ],
        "total": 2
      },
      "permissions": {
        "items": [
          {"id": 10, "name": "用户管理"},
          {"id": 11, "name": "角色管理"}
        ],
        "total": 2
      }
    },

    "_metadata": {
      "object_type": "user",
      "loaded_associations": ["roles", "permissions"],
      "depth": 1
    }
  }
}
```

**深度限制**：
- 最大 depth = **2**（防止循环引用）
- 超过限制返回 400 错误

---

## 四、Association API（关联操作）

### 4.1 API 风格对比

v2 API 提供**两种风格**的关联操作接口：

| 风格 | 路径前缀 | 特点 | 适用场景 |
|------|---------|------|---------|
| **v1 风格** | `/associations/` | RESTful 标准 | 通用 CRUD |
| **SAP 风格** | `/$associations/` | SAP OData V2 规范 | 企业级应用（推荐）⭐ |

### 4.2 v1 风格关联操作（Legacy）

#### 4.2.1 查询关联列表

**端点**: `GET /api/v2/bo/{entity}/{id}/associations/{association_name}`

**请求示例**:
```
GET /api/v2/bo/user/1/roles?page=1&page_size=20
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "items": [
      {"id": 1, "name": "管理员", "code": "admin"},
      {"id": 2, "name": "审核员", "code": "reviewer"}
    ],
    "total": 2
  }
}
```

#### 4.2.2 添加关联

**端点**: `POST /api/v2/bo/{entity}/{id}/associations/{association_name}`

**请求体**:
```json
{
  "target_id": 3,
  "target_type": "role",
  "metadata": {
    "assigned_by": 1,
    "remark": "临时授权"
  }
}
```

**响应** (200):
```json
{
  "success": true,
  "message": "关联添加成功"
}
```

#### 4.2.3 移除关联

**端点**: `DELETE /api/v2/bo/{entity}/{id}/associations/{association_name}?target_id={target_id}`

**或者通过请求体**:
```json
{"target_id": 3}
```

**响应** (200):
```json
{
  "success": true,
  "message": "关联移除成功"
}
```

---

### 4.3 SAP 风格关联操作 ⭐（推荐）

#### 4.3.1 查询关联列表

**端点**: `GET /api/v2/bo/{entity}/{id}/$associations/{association_name}`

**请求示例**:
```
GET /api/v2/bo/user/1/$associations/roles?page=1&page_size=20&search=管理
```

**查询参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | integer | 1 | 页码 |
| `page_size` | integer | 50 | 每页数量 |
| `search` | string | - | 关键词搜索 |

**响应** (200): 同 4.2.1

---

#### 4.3.2 统计关联数量

**端点**: `GET /api/v2/bo/{entity}/{id}/$associations/{association_name}/count`

**请求示例**:
```
GET /api/v2/bo/user/1/$associations/roles/count
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "count": 5
  }
}
```

**使用场景**：
- 列表页显示关联数量标签
- 权限预检查（是否有关联数据阻止删除）

---

#### 4.3.3 分配单个关联 ⭐

**端点**: `POST /api/v2/bo/{entity}/{id}/$associations/{association_name}/assign`

**请求体**:
```json
{
  "target_id": 3,
  "target_type": "role",
  "metadata": {
    "assigned_at": "2026-05-19T15:00:00Z",
    "remark": "业务需要"
  }
}
```

**响应**: **204 No Content**（SAP 风格，成功时无响应体）

**错误响应** (400):
```json
{
  "success": false,
  "message": "目标对象不存在"
}
```

---

#### 4.3.4 取消分配单个关联 ⭐

**端点**: `POST /api/v2/bo/{entity}/{id}/$associations/{association_name}/unassign`

**请求体**（两种方式）:

**方式 1：通过 target_id**
```json
{
  "target_id": 3,
  "target_type": "role"
}
```

**方式 2：通过 association_record_id**（中间表主键）
```json
{
  "association_record_id": 999
}
```

**响应**: **204 No Content**

**特殊处理**：
- 如果关联使用 `through` 中间表，且提供了 `association_record_id`，会直接从中间表删除
- 这比先查询再删除更高效

---

#### 4.3.5 批量分配关联 ⭐

**端点**: `POST /api/v2/bo/{entity}/{id}/$associations/{association_name}/batch_assign`

**请求体**:
```json
{
  "target_ids": [3, 4, 5],
  "target_type": "role",
  "metadata": {
    "batch_operation": true,
    "source": "ui_batch_action"
  }
}
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "assigned_count": 3,
    "skipped_count": 0,
    "errors": []
  },
  "message": "批量分配成功"
}
```

**性能优化**：
- 使用事务包裹所有分配操作
- 跳过已存在的关联（幂等性）
- 支持最多 100 个目标 ID

---

#### 4.3.6 批量取消分配关联 ⭐

**端点**: `POST /api/v2/bo/{entity}/{id}/$associations/{association_name}/batch_unassign`

**请求体**（两种方式）:

**方式 1：通过 target_ids**
```json
{
  "target_ids": [3, 4, 5],
  "target_type": "role"
}
```

**方式 2：通过 association_record_ids**
```json
{
  "association_record_ids": [1001, 1002, 1003]
}
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "removed_count": 3
  },
  "message": "成功删除 3 条关联记录"
}
```

---

#### 4.3.7 批量查询关联

**端点**: `POST /api/v2/bo/{entity}/$associations/{association_name}/batch-query`

**说明**：一次查询多个源对象的关联数据。

**请求体**:
```json
{
  "source_ids": [1, 2, 3, 4, 5],
  "page": 1,
  "page_size": 20,
  "search": ""
}
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "items": [
      {"source_id": 1, "target_id": 3, "target_name": "管理员"},
      {"source_id": 2, "target_id": 3, "target_name": "管理员"},
      {"source_id": 5, "target_id": 4, "target_name": "审核员"}
    ],
    "total": 3,
    "counts": {
      "1": 1,
      "2": 1,
      "3": 0,
      "4": 0,
      "5": 1
    }
  }
}
```

**使用场景**：
- 列表页批量显示每个对象的关联数量
- 减少前端 N+1 查询问题

---

## 五、Value Help API

### 5.1 Value Help 搜索

**端点**: `GET /api/v2/value-help/{source_type}/{source_id}`

**权限**: 需要对应对象的读取权限

**URL 参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `search` | string | "" | 搜索关键词 |
| `search_fields` | string | - | 搜索字段（逗号分隔） |
| `page` | integer | 1 | 页码 |
| `pageSize` | integer | 50 | 每页数量 |
| `sort` | string | - | 排序（格式: `field:direction`） |
| `filters[{field}]` | any | - | 高级过滤条件 |

**source_type 类型**:
| type | source_id 含义 | 示例 |
|------|---------------|------|
| `enum` | 枚举类型 ID | `user_status`, `yes_no` |
| `bo` | 业务对象 ID | `user`, `role`, `product` |
| `custom` | 自定义端点 URL | - |

**请求示例**:
```
# 搜索枚举值
GET /api/v2/value-help/enum/user_status?search=激

# 搜索业务对象（角色选择器）
GET /api/v2/value-help/bo/role?search=管理&page=1&pageSize=20&sort=name:asc
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "value": "active",
        "label": "活跃",
        "color": "success",
        "sort_order": 1
      },
      {
        "value": "inactive",
        "label": "未激活",
        "color": "info",
        "sort_order": 2
      }
    ],
    "total": 4,
    "page": 1,
    "pageSize": 50
  }
}
```

**Enum 类型特殊响应**:
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "value": "admin",
        "label": "管理员",
        "description": "拥有所有权限",
        "color": "",
        "sort_order": 1
      }
    ]
  }
}
```

**BO 类型特殊响应**:
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "value": 1,
        "label": "管理员",
        "code": "admin",
        "display_name": "admin (管理员)",
        "is_active": true
      }
    ],
    "total": 10
  }
}
```

---

### 5.2 Value Help 解析（单值解析）

**端点**: `GET /api/v2/value-help/{source_type}/{source_id}/resolve`

**URL 参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `value` | string | ✅ | 要解析的值 |

**请求示例**:
```
GET /api/v2/value-help/enum/user_status/resolve?value=active
GET /api/v2/value-help/bo/role/resolve?value=1
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "value": "active",
    "label": "活跃",
    "color": "success",
    "resolved": true
  }
}
```

**错误响应** (404):
```json
{
  "success": false,
  "error": "Value not found"
}
```

**使用场景**：
- 将存储值转换为显示标签
- 导出 Excel 时将 code 转换为 name
- 审计日志中展示可读的状态名称

---

## 六、Filter Variant API

> 参考 SAP Fiori SmartFilterBar 的变体管理功能

### 6.1 基础信息

**基础路径**: `/api/v1/filter-variants`

**说明**：保存和管理用户的过滤条件预设，方便快速切换常用筛选组合。

### 6.2 获取变体列表

**端点**: `GET /api/v1/filter-variants`

**查询参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `object_type` | string | - | 对象类型（可选） |
| `include_shared` | boolean | true | 是否包含共享变体 |

**响应** (200):
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "我的常用筛选",
      "object_type": "user",
      "filters": "{\"status\":\"active\",\"role_id\":\"1\"}",
      "user_id": 1,
      "is_shared": false,
      "is_default": true,
      "created_at": "2026-05-19T10:00:00Z",
      "updated_at": "2026-05-19T10:00:00Z"
    },
    {
      "id": 2,
      "name": "管理员视角",
      "object_type": "user",
      "filters": "{\"role_id\":\"1\"}",
      "user_id": null,
      "is_shared": true,
      "is_default": false,
      "created_at": "2026-05-18T15:00:00Z",
      "updated_at": "2026-05-18T15:00:00Z"
    }
  ]
}
```

### 6.3 创建变体

**端点**: `POST /api/v1/filter-variants`

**请求体**:
```json
{
  "name": "我的新筛选",
  "object_type": "user",
  "filters": "{\"status\":\"active\",\"keyword\":\"admin\"}",
  "is_shared": false,
  "is_default": false
}
```

**响应** (201):
```json
{
  "success": true,
  "data": {
    "id": 3,
    "name": "我的新筛选",
    ...
  }
}
```

### 6.4 更新变体

**端点**: `PUT /api/v1/filter-variants/{id}`

### 6.5 删除变体

**端点**: `DELETE /api/v1/filter-variants/{id}`

---

## 七、Meta Data API

### 7.1 获取对象 UI 配置

**端点**: `GET /api/v2/bo/{entity}/ui-config`

**权限**: 公开（或需 read 权限，取决于配置）

**说明**：返回对象的 UI 配置，包括字段权限智能推导结果。

**请求示例**:
```
GET /api/v2/bo/user/ui-config
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "object_type": "user",
    "display_name_field": "username",
    "fields": [
      {
        "id": "username",
        "name": "用户名",
        "type": "string",
        "required": true,
        "ui": {
          "visible": true,
          "editable": true,
          "readonly": false
        },
        "value_help": {
          "source": {"type": "text"},
          "presentation": {"result_type": "input"}
        }
      },
      {
        "id": "password_hash",
        "name": "密码哈希",
        "type": "string",
        "ui": {
          "visible": false,
          "hidden_in_list": true,
          "hidden_in_detail": true,
          "hidden_in_form": true,
          "hidden_in_export": true,
          "hidden_in_import": true
        }
      },
      {
        "id": "status",
        "name": "状态",
        "type": "string",
        "value_help": {
          "source": {"type": "enum", "enum_type_id": "user_status"},
          "presentation": {
            "result_type": "dropdown",
            "color_mapping": {
              "active": "success",
              "inactive": "info",
              "locked": "warning"
            }
          }
        }
      }
    ],
    "list_columns": [
      {"key": "username", "title": "用户名", "width": 120},
      {"key": "email", "title": "邮箱", "width": 180},
      {"key": "status", "title": "状态", "width": 80, "type": "tag"}
    ],
    "actions": [
      {"id": "create", "label": "新建用户", "icon": "plus", "type": "primary"}
    ],
    "row_actions": [
      {"id": "edit", "label": "编辑"},
      {"id": "delete", "label": "删除", "type": "danger"}
    ]
  }
}
```

**关键特性**：
- 字段权限已根据当前用户角色智能推导
- 敏感字段自动标记为不可见
- Value Help 配置完整传递给前端
- 列定义包含渲染提示（type: tag 等）

---

### 7.2 获取 Schema 定义

**端点**: `GET /api/v2/bo/{entity}/schema`

**说明**：返回对象的完整 Schema 元数据（不含权限推导）。

**响应** (200):
```json
{
  "success": true,
  "data": {
    "id": "user",
    "name": "用户",
    "table_name": "users",
    "fields": [
      {
        "id": "username",
        "name": "用户名",
        "type": "string",
        "required": true,
        "unique": true,
        "semantics": {
          "business_key": true,
          "display_name": true
        }
      }
    ],
    "associations": [
      {
        "id": "roles",
        "name": "角色",
        "type": "many_to_many",
        "target_entity": "role",
        "through": "user_roles"
      }
    ],
    "rules": [
      {
        "id": "activate_user",
        "type": "state_transition",
        "from_states": ["inactive"],
        "to_state": "active"
      }
    ]
  }
}
```

**使用场景**：
- 动态表单生成
- 动态验证规则构建
- 开发者工具/调试界面

---

### 7.3 重载元数据

**端点**: `POST /api/v1/meta/reload`

**权限**: 仅管理员

**说明**：强制重新加载所有 YAML 元数据文件，清除缓存。

**请求体**:
```json
{}
```

**响应** (200):
```json
{
  "success": true,
  "message": "元数据重载完成",
  "data": {
    "reloaded_objects": 25,
    "cache_cleared": true,
    "timestamp": "2026-05-19T16:00:00Z"
  }
}
```

**触发时机**：
- 修改了 YAML 文件但不想重启服务
- 开发调试时快速验证修改效果
- 生产环境慎用（会导致短暂性能下降）

---

## 八、Import/Export API

### 8.1 导出数据

**端点**: `GET /api/v1/export`

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `object_type` | string | ✅ | 对象类型 |
| `format` | string | ❌ | 格式：xlsx（默认）/ csv |
| `filters` | string | ❌ | JSON 格式的过滤条件 |
| `columns` | string | ❌ | 要导出的列（逗号分隔） |
| `cascade` | boolean | ❌ | 是否级联导出关联数据 |

**请求示例**:
```
GET /api/v1/export?object_type=user&format=xlsx&columns=id,username,email,status
GET /api/v1/export?object_type=product&cascade=true
```

**响应**:
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Content-Disposition: `attachment; filename="users_20260519.xlsx"`

**特性**：
- 根据 YAML 的 `import_export.export_visible` 控制列可见性
- 敏感字段自动排除
- Enum 值自动转换为 label
- 支持百万级数据流式导出

---

### 8.2 下载导出文件

**端点**: `GET /api/v1/export/download/{filename}`

**说明**：下载之前异步生成的导出文件。

---

### 8.3 导入数据

**端点**: `POST /api/v1/import`

**Content-Type**: `multipart/form-data`

**请求参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | ✅ | Excel 文件（.xlsx, .xls, .csv） |
| `object_type` | string | ✅ | 目标对象类型 |
| `conflict_strategy` | string | ❌ | 冲突策略：upsert（默认）/ skip / error |
| `dry_run` | boolean | ❌ | 仅预览不导入 |

**请求示例（FormData）**:
```
file: <binary file data>
object_type: user
conflict_strategy: upsert
dry_run: false
```

**响应** (200):
```json
{
  "success": true,
  "data": {
    "results": {
      "user": {
        "total_rows": 100,
        "success": 95,
        "failed": 5,
        "skipped": 0,
        "errors": [
          {"row": 3, "field": "username", "message": "用户名已存在"},
          {"row": 15, "field": "email", "message": "邮箱格式不正确"}
        ]
      }
    },
    "summary": {
      "total_objects": 1,
      "total_processed": 100,
      "total_success": 95,
      "total_failed": 5
    }
  }
}
```

**导入流程**：
1. 解析 Excel 文件
2. 校验每行数据的必填字段和格式
3. 根据 conflict_strategy 处理冲突
4. 通过 BO Framework 执行插入/更新
5. 写入审计日志
6. 返回详细的结果报告

---

### 8.4 导入预览

**端点**: `POST /api/v1/import/preview`

**说明**：仅解析和校验，不实际写入数据库。用于导入前的确认。

**请求参数**: 同 8.3

**响应** (200):
```json
{
  "success": true,
  "data": {
    "preview": [
      {"row": 1, "username": "user1", "email": "user1@test.com", "status": "✅ 有效"},
      {"row": 2, "username": "user2", "email": "invalid", "status": "❌ 邮箱格式错误"}
    ],
    "statistics": {
      "valid_count": 8,
      "invalid_count": 2,
      "warnings": ["第5行：缺少可选字段 department"]
    }
  }
}
```

---

## 九、认证与授权

### 9.1 JWT 认证

**获取 Token**:
```
POST /api/v1/auth/login
{
  "username": "admin",
  "password": "password123"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_in": 3600,
    "token_type": "Bearer",
    "user": {
      "id": 1,
      "username": "admin",
      "roles": ["admin"]
    }
  }
}
```

**使用 Token**:
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 9.2 权限模型

**RBAC（基于角色的访问控制）**：

```
用户 → 角色 → 权限 → 资源
```

**权限粒度**：

| 层级 | 检查位置 | 示例 |
|------|---------|------|
| **对象级** | YAML `permissions.create/read/update/delete` | 是否能访问 User 对象 |
| **字段级** | YAML `fields[].ui.editable/.visible` | 是否能看到 password_hash |
| **行级** | DataPermissionInterceptor | 只能看到自己部门的数据 |
| **操作级** | YAML `row_actions[].permission` | 是否能执行"激活"操作 |

### 9.3 请求追踪

**X-Trace-Id Header**:

用于在分布式系统中追踪一个请求的完整生命周期。

```http
X-Trace-Id: abcdef123456
```

**生成规则**：
- 前端首次请求生成 UUID
- 后端在每个响应头中返回相同的 Trace-ID
- 审计日志自动记录 Trace-ID
- 可用于日志关联和问题排查

---

## 十、错误码体系

### 10.1 标准错误码

| 错误码 | HTTP 状态 | 说明 | 示例场景 |
|--------|----------|------|---------|
| `UNAUTHORIZED` | 401 | 未认证 | Token 缺失或过期 |
| `FORBIDDEN` | 403 | 无权限 | 普通用户尝试删除 |
| `NOT_FOUND` | 404 | 资源不存在 | ID=9999 的用户 |
| `VALIDATION_ERROR` | 400 | 参数校验失败 | 必填字段为空 |
| `DUPLICATE_KEY` | 400 | 唯一键冲突 | 用户名重复 |
| `CONSTRAINT_VIOLATION` | 400 | 约束违反 | 外键不存在 |
| `IMMUTABLE_FIELD` | 400 | 不可变字段修改 | 尝试修改 business_key |
| `STATE_TRANSITION_INVALID` | 400 | 状态转换无效 | 从 active 直接到 deleted |
| `ASSOCIATION_EXISTS` | 400 | 关联已存在 | 重复分配同一角色 |
| `DELETION_NOT_ALLOWED` | 400 | 不允许删除 | 存在子对象 |
| `INTERNAL_ERROR` | 500 | 服务器错误 | 数据库连接失败 |
| `METADATA_NOT_FOUND` | 404 | 元数据不存在 | object_type=unknown |

### 10.2 业务错误码

| 错误码 | 说明 | 所属对象 |
|--------|------|---------|
| `USER_LOCKED` | 用户已被锁定 | user |
| `ROLE_IS_SYSTEM` | 系统角色不可删除 | role |
| `ENUM_IN_USE` | 枚举值正在被使用 | enum_value |
| `PRODUCT_HAS_VERSIONS` | 产品下有版本不能删除 | product |

### 10.3 错误响应结构

**简单错误**:
```json
{
  "success": false,
  "message": "用户名已存在",
  "code": "DUPLICATE_KEY"
}
```

**详细错误（含字段信息）**:
```json
{
  "success": false,
  "message": "参数校验失败",
  "code": "VALIDATION_ERROR",
  "details": {
    "field": "email",
    "message": "邮箱格式不正确",
    "constraint": "email_format"
  }
}
```

**批量操作错误**:
```json
{
  "success": false,
  "message": "部分操作失败",
  "errors": [
    {"index": 0, "target_id": 3, "message": "关联已存在"},
    {"index": 2, "target_id": 5, "message": "目标对象不存在"}
  ],
  "success_count": 3,
  "failed_count": 2
}
```

---

## 十一、版本兼容性（v1 → v2 迁移）

### 11.1 主要变化

| 维度 | v1 API | v2 API |
|------|--------|--------|
| **基础路径** | `/api/v1/{object_type}` | `/api/v2/bo/{entity}` |
| **CRUD 方法** | 标准 RESTful | 标准 RESTful（保持一致） |
| **关联操作** | `/associations/` | **新增** `/$associations/`（SAP 风格） |
| **响应格式** | `{success, data, message}` | 保持一致 |
| **Value Help** | 内嵌在 meta API | **独立** `/api/v2/value-help/` |
| **UI Config** | `/api/v1/meta/{type}/config` | **迁移至** `/api/v2/bo/{entity}/ui-config` |
| **深度查询** | 不支持 | **新增** `/retrieve` 和 `/deep` |

### 11.2 迁移指南

#### 前端迁移

```javascript
// ❌ v1 旧写法
const response = await api.get(`/api/v1/user`)
const response = await api.post(`/api/v1/user/1/roles`, { target_id: 3 })

// ✅ v2 新写法
const response = await api.get('/api/v2/bo/user')
const response = await api.post('/api/v2/bo/user/1/$associations/roles/assign', { target_id: 3 })
```

#### 后端兼容性

v1 API 端点仍然可用（向后兼容），但建议逐步迁移到 v2：

```
时间线：
2026-Q2: v1 + v2 并存（当前状态）
2026-Q3: 新功能仅在 v2 实现
2026-Q4: v1 标记为 Deprecated
2027-Q1: v1 移除（计划）
```

### 11.3 废弃列表（Deprecated）

以下 v1 端点将在未来版本移除，请迁移到 v2 替代品：

| v1 端点 | v2 替代品 | 移除时间表 |
|--------|----------|-----------|
| `GET /api/v1/{type}` | `GET /api/v2/bo/{entity}` | 2027-Q1 |
| `POST /api/v1/{type}/{id}/{assoc}` | `POST /.../$associations/{assoc}/assign` | 2027-Q1 |
| `GET /api/v1/meta/{type}/config` | `GET /api/v2/bo/{entity}/ui-config` | 2027-Q1 |

---

## 附录：完整端点清单

### Core CRUD (7 个)

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| POST | `/api/v2/bo/{entity}` | 创建记录 | bo_api.py L36 |
| GET | `/api/v2/bo/{entity}` | 查询列表 | bo_api.py L74 |
| GET | `/api/v2/bo/{entity}/{id}` | 查询详情（整数ID） | bo_api.py L53 |
| GET | `/api/v2/bo/{entity}/{path:id}` | 查询详情（字符串ID） | bo_api.py L63 |
| PUT | `/api/v2/bo/{entity}/{id}` | 更新记录 | bo_api.py L151 |
| DELETE | `/api/v2/bo/{entity}/{id}` | 删除记录 | bo_api.py L162 |
| POST | `/api/v2/bo/{entity}/deep` | 深度插入 | bo_api.py L136 |

### Action & Retrieve (2 个)

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| POST | `/api/v2/bo/{entity}/{id}/actions/{action_id}` | 执行自定义动作 | bo_api.py L174 |
| GET | `/api/v2/bo/{entity}/{id}/retrieve` | 深度获取（含关联） | bo_api.py L484 |

### Association v1 风格 (3 个)

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| GET | `/.../{id}/associations/{assoc}` | 查询关联 | bo_api.py L248 |
| POST | `/.../{id}/associations/{assoc}` | 添加关联 | bo_api.py L188 |
| DELETE | `/.../{id}/associations/{assoc}` | 移除关联 | bo_api.py L217 |

### Association SAP 风格 (7 个) ⭐

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| GET | `/.../{id}/$associations/{assoc}` | 查询关联 | bo_api.py L270 |
| GET | `/.../{id}/$associations/{assoc}/count` | 统计关联数量 | bo_api.py L293 |
| POST | `/.../{id}/$associations/{assoc}/assign` | 分配关联 | bo_api.py L309 |
| POST | `/.../{id}/$associations/{assoc}/unassign` | 取消分配 | bo_api.py L339 |
| POST | `/.../{id}/$associations/{assoc}/batch_assign` | 批量分配 | bo_api.py L382 |
| POST | `/.../{id}/$associations/{assoc}/batch_unassign` | 批量取消 | bo_api.py L412 |
| POST | `/.../$associations/{assoc}/batch-query` | 批量查询 | bo_api.py L457 |

### Value Help (2 个)

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| GET | `/api/v2/value-help/{type}/{id}` | 搜索值帮助 | value_help_api.py L32 |
| GET | `/api/v2/value-help/{type}/{id}/resolve` | 解析单个值 | value_help_api.py L80 |

### Filter Variant (5 个)

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| GET | `/api/v1/filter-variants` | 获取变体列表 | filter_variant_api.py L81 |
| POST | `/api/v1/filter-variants` | 创建变体 | - |
| PUT | `/api/v1/filter-variants/{id}` | 更新变体 | - |
| DELETE | `/api/v1/filter-variants/{id}` | 删除变体 | - |
| GET | `/api/v1/filter-variants/{id}` | 获取单个变体 | - |

### Meta Data (3 个)

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| GET | `/api/v2/bo/{entity}/ui-config` | 获取 UI 配置 | bo_framework.py |
| GET | `/api/v2/bo/{entity}/schema` | 获取 Schema | yaml_loader.py |
| POST | `/api/v1/meta/reload` | 重载元数据 | meta_api.py |

### Import/Export (4 个)

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| GET | `/api/v1/export` | 导出数据 | export_import_api.py |
| GET | `/api/v1/export/download/{filename}` | 下载文件 | export_import_api.py |
| POST | `/api/v1/import` | 导入数据 | export_import_api.py |
| POST | `/api/v1/import/preview` | 导入预览 | export_import_api.py |

### Auth (2+ 个)

| Method | Endpoint | 说明 | 文件位置 |
|--------|----------|------|---------|
| POST | `/api/v1/auth/login` | 登录获取 Token | auth_api.py |
| POST | `/api/v1/auth/logout` | 登出 | auth_api.py |
| GET | `/api/v1/auth/me` | 获取当前用户信息 | auth_api.py |

---

**总计**: **34 个正式端点** + Legacy v1 兼容端点

---

## 文档维护信息

| 项目 | 信息 |
|------|------|
| **当前版本** | v2.0.0 |
| **创建日期** | 2026-05-19 |
| **最后更新** | 2026-05-19 |
| **维护者** | Architecture Team |
| **下次审查日期** | 2026-06-19 |
| **对应代码文件** | meta/api/bo_api.py, value_help_api.py, filter_variant_api.py |
| **测试覆盖** | E2E 测试 + 单元测试 |

---

> **重要提醒**：本文档是前后端交互的唯一权威契约。任何 API 变更必须同步更新本文档。
>
> **快速参考**：日常开发时可重点阅读第三章（CRUD）、第四章（Association）、第五章（Value Help）。
