# v2 API 文档

> **版本**: v2
>
> **基础路径**: `/api/v2`
>
> **最后更新**: 2026-05-11

---

## 一、概述

v2 API 是基于 BOFramework 的统一业务对象 API，提供标准的 CRUD 操作和 Association 操作。所有请求需要携带认证 Token。

### 1.1 认证方式

```http
Authorization: Bearer <token>
```

### 1.2 通用请求头

```http
Content-Type: application/json
Accept: application/json
```

### 1.3 通用响应格式

```json
{
  "success": true,
  "data": { },
  "message": "操作成功"
}
```

---

## 二、CRUD 操作

### 2.1 查询列表

```
GET /api/v2/bo/{entity}
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |
| search | string | 否 | 关键词搜索 |
| ordering | string | 否 | 排序字段，前缀 `-` 表示降序 |
| {field} | string | 否 | 过滤字段，精确匹配 |
| {field}__like | string | 否 | 模糊匹配 |
| {field}__in | string | 否 | IN 查询，逗号分隔 |

**示例**:

```bash
# 查询用户列表，第2页，每页50条
GET /api/v2/bo/user?page=2&page_size=50

# 按名称模糊搜索
GET /api/v2/bo/user?search=张三

# 按状态过滤，降序排列
GET /api/v2/bo/user?status=active&ordering=-created_at

# 多值 IN 查询
GET /api/v2/bo/user?role_id__in=1,2,3
```

**响应**:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "username": "admin",
        "display_name": "管理员",
        "email": "admin@example.com",
        "status": "active",
        "created_at": "2026-01-01 10:00:00"
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

---

### 2.2 查询单个对象

```
GET /api/v2/bo/{entity}/{id}
```

**示例**:

```bash
GET /api/v2/bo/user/1
```

**响应**:

```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "admin",
    "display_name": "管理员",
    "email": "admin@example.com",
    "status": "active",
    "created_at": "2026-01-01 10:00:00"
  }
}
```

---

### 2.3 创建对象

```
POST /api/v2/bo/{entity}
```

**请求体**:

```json
{
  "username": "newuser",
  "display_name": "新用户",
  "email": "newuser@example.com",
  "password": "password123"
}
```

**响应**:

```json
{
  "success": true,
  "data": {
    "id": 10,
    "username": "newuser",
    "display_name": "新用户",
    "email": "newuser@example.com",
    "status": "active",
    "created_at": "2026-05-11 12:00:00"
  },
  "message": "创建成功"
}
```

---

### 2.4 更新对象

```
PUT /api/v2/bo/{entity}/{id}
```

**请求体**:

```json
{
  "display_name": "更新后的名称",
  "email": "updated@example.com"
}
```

**响应**:

```json
{
  "success": true,
  "data": {
    "id": 10,
    "username": "newuser",
    "display_name": "更新后的名称",
    "email": "updated@example.com",
    "updated_at": "2026-05-11 13:00:00"
  },
  "message": "更新成功"
}
```

---

### 2.5 删除对象

```
DELETE /api/v2/bo/{entity}/{id}
```

**响应**:

```json
{
  "success": true,
  "message": "删除成功"
}
```

---

### 2.6 批量删除

```
POST /api/v2/bo/{entity}/batch-delete
```

**请求体**:

```json
{
  "ids": [1, 2, 3, 4, 5]
}
```

**响应**:

```json
{
  "success": true,
  "success_count": 5,
  "failed_count": 0,
  "errors": []
}
```

---

## 三、Association 操作

### 3.1 查询关联列表

```
GET /api/v2/bo/{entity}/{id}/associations/{association_name}
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 50 |
| search | string | 否 | 关键词搜索 |

**示例**:

```bash
# 查询用户组1的所有成员
GET /api/v2/bo/user_group/1/associations/members

# 查询用户组1的所有角色
GET /api/v2/bo/user_group/1/associations/roles

# 查询角色1的所有用户
GET /api/v2/bo/role/1/associations/users
```

**响应**:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 101,
        "username": "user1",
        "display_name": "用户1",
        "email": "user1@example.com",
        "is_manager": false,
        "joined_at": "2026-01-01 10:00:00"
      },
      {
        "id": 102,
        "username": "user2",
        "display_name": "用户2",
        "email": "user2@example.com",
        "is_manager": true,
        "joined_at": "2026-01-02 10:00:00"
      }
    ],
    "total": 2,
    "page": 1,
    "page_size": 50
  }
}
```

---

### 3.2 创建关联

```
POST /api/v2/bo/{entity}/{id}/associations/{association_name}
```

**请求体**:

```json
{
  "target_id": 101,
  "metadata": {
    "is_manager": false
  }
}
```

**响应**:

```json
{
  "success": true,
  "message": "关联创建成功",
  "data": {
    "id": 101,
    "username": "user1",
    "display_name": "用户1"
  }
}
```

**批量创建关联**:

```json
{
  "target_ids": [101, 102, 103],
  "metadata": {
    "is_manager": false
  }
}
```

---

### 3.3 删除关联

```
DELETE /api/v2/bo/{entity}/{id}/associations/{association_name}
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| target_id | int | 是 | 目标对象 ID |

**示例**:

```bash
# 从用户组1移除成员101
DELETE /api/v2/bo/user_group/1/associations/members?target_id=101
```

**响应**:

```json
{
  "success": true,
  "message": "关联已解除"
}
```

---

## 四、业务对象实体

### 4.1 User (用户)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 用户 ID |
| username | string | 用户名 |
| display_name | string | 显示名称 |
| email | string | 邮箱 |
| status | string | 状态 (active/inactive/locked) |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

**关联关系**:

| 关联名 | 类型 | 目标 | 说明 |
|--------|------|------|------|
| roles | many_to_many | role | 用户角色 |
| groups | many_to_many | user_group | 用户组 |

---

### 4.2 Role (角色)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 角色 ID |
| code | string | 角色编码 |
| name | string | 角色名称 |
| description | string | 描述 |
| is_system | boolean | 是否系统角色 |
| menu_count | int | 菜单数（计算字段） |
| permission_count | int | 权限数（计算字段） |
| user_count | int | 用户数（计算字段） |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

**关联关系**:

| 关联名 | 类型 | 目标 | 说明 |
|--------|------|------|------|
| permissions | many_to_many | permission | 角色权限 |
| users | many_to_many | user | 角色用户 |
| assigned_groups | reverse_many_to_many | user_group | 分配了该角色的用户组 |

---

### 4.3 UserGroup (用户组)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 用户组 ID |
| code | string | 组编码 |
| name | string | 组名称 |
| parent_id | int | 父组 ID |
| manager_id | int | 管理员 ID |
| description | string | 描述 |
| member_count | int | 成员数（计算字段） |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

**关联关系**:

| 关联名 | 类型 | 目标 | 说明 |
|--------|------|------|------|
| members | many_to_many | user | 用户组成员 |
| roles | many_to_many | role | 用户组角色 |

---

### 4.4 Permission (权限)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 权限 ID |
| code | string | 权限编码 |
| name | string | 权限名称 |
| resource | string | 资源 |
| action | string | 操作 |
| description | string | 描述 |

---

## 五、错误处理

### 5.1 错误响应格式

```json
{
  "success": false,
  "message": "错误信息",
  "code": "ERROR_CODE",
  "errors": []
}
```

### 5.2 错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| UNAUTHORIZED | 401 | 未授权 |
| FORBIDDEN | 403 | 禁止访问 |
| NOT_FOUND | 404 | 资源不存在 |
| VALIDATION_ERROR | 422 | 参数验证失败 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |
| DEPRECATED_API | 200 | API 已废弃（响应中带 `_deprecated: true`） |

---

## 六、废弃 API

以下旧 API 已废弃，请使用 v2 API：

| 旧 API | v2 API | 废弃时间 |
|--------|--------|---------|
| GET /api/v1/user-groups/{id}/members | GET /api/v2/bo/user_group/{id}/associations/members | 2026-05-11 |
| POST /api/v1/user-groups/{id}/members | POST /api/v2/bo/user_group/{id}/associations/members | 2026-05-11 |
| GET /api/v1/user-groups/{id}/roles | GET /api/v2/bo/user_group/{id}/associations/roles | 2026-05-11 |

---

## 七、变更日志

### 2026-05-11

- 新增 v2 API 文档
- 新增 Association 操作端点
- 标记以下旧 API 为废弃：
  - `/api/v1/user-groups/*` 相关路由

---

## 八、参考文档

- [YAML 元数据设计规范](../unified-metadata-api-architecture/spec.md)
- [Phase 9 通用能力模型规范](../phase-9-common-capability-model/spec.md)
