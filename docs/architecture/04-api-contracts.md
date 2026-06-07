# API 契约定义

> 本文档定义了后端 API 的契约规范，包括请求/响应格式、错误处理等。

---

## 一、基础规范

### 1.1 通用格式

**请求头**
```
Content-Type: application/json
Authorization: Bearer <token>
X-User-Id: <user_id>
X-Trace-Id: <trace_id>
```

**响应格式**
```json
// 成功
{
  "success": true,
  "data": { ... },
  "message": "操作成功"
}

// 失败
{
  "success": false,
  "error": "错误信息",
  "code": "ERROR_CODE",
  "details": { ... }
}
```

### 1.2 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

---

## 二、CRUD API

### 2.1 查询列表

**请求**
```
GET /api/v1/{object_type}
```

**查询参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | integer | 页码，默认 1 |
| `page_size` | integer | 每页数量，默认 20 |
| `sort_by` | string | 排序字段 |
| `sort_order` | string | 排序方向 asc/desc |
| `{field}` | string | 字段过滤 |

**响应**
```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

### 2.2 查询详情

**请求**
```
GET /api/v1/{object_type}/{id}
```

**响应**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "对象名称",
    ...
  }
}
```

### 2.3 创建

**请求**
```
POST /api/v1/{object_type}
```

**请求体**
```json
{
  "name": "对象名称",
  "code": "object_code",
  ...
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "id": 1,
    ...
  },
  "message": "创建成功"
}
```

### 2.4 更新

**请求**
```
PUT /api/v1/{object_type}/{id}
```

**请求体**
```json
{
  "name": "新名称",
  ...
}
```

**响应**
```json
{
  "success": true,
  "data": { ... },
  "message": "更新成功"
}
```

### 2.5 删除

**请求**
```
DELETE /api/v1/{object_type}/{id}
```

**响应**
```json
{
  "success": true,
  "message": "删除成功"
}
```

---

## 三、关联 API

### 3.1 查询关联

**请求**
```
GET /api/v1/{object_type}/{id}/{association_name}
```

**响应**
```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 10
  }
}
```

### 3.2 添加关联

**请求**
```
POST /api/v1/{object_type}/{id}/{association_name}
```

**请求体**
```json
{
  "target_ids": [1, 2, 3]
}
```

**响应**
```json
{
  "success": true,
  "message": "添加成功"
}
```

### 3.3 移除关联

**请求**
```
DELETE /api/v1/{object_type}/{id}/{association_name}/{target_id}
```

**响应**
```json
{
  "success": true,
  "message": "移除成功"
}
```

---

## 四、导入导出 API

### 4.1 导出

**请求**
```
GET /api/v1/export/cascade?object_type={type}&filters={json}
```

**响应**
- 返回 Excel 文件流
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

### 4.2 导入模板

**请求**
```
GET /api/v1/export/template?object_type={type}
```

**响应**
- 返回 Excel 模板文件流

### 4.3 导入

**请求**
```
POST /api/v1/import
Content-Type: multipart/form-data

file: <Excel文件>
```

**响应**
```json
{
  "success": true,
  "data": {
    "results": {
      "user": {
        "success": 5,
        "failed": 1,
        "errors": ["第3行: 字段不能为空"]
      }
    }
  }
}
```

---

## 五、元数据 API

### 5.1 获取对象配置

**请求**
```
GET /api/v1/meta/{object_type}/config
```

**响应**
```json
{
  "success": true,
  "data": {
    "id": "user",
    "name": "用户",
    "fields": [
      {
        "id": "name",
        "name": "用户名",
        "type": "string",
        "required": true,
        "visible": true,
        "editable": true,
        "readonly": false
      },
      ...
    ],
    "associations": {
      "roles": {
        "name": "角色",
        "target_type": "role",
        "type": "many_to_many"
      }
    }
  }
}
```

### 5.2 获取视图配置

**请求**
```
GET /api/v1/meta/{object_type}/view
```

**响应**
```json
{
  "success": true,
  "data": {
    "list": {
      "title": "用户管理",
      "columns": [...],
      "actions": [...]
    },
    "detail": {
      "layout": "tabs",
      "tabs": [...]
    }
  }
}
```

---

## 六、错误码定义

| 错误码 | 说明 | HTTP 状态 |
|--------|------|-----------|
| `UNAUTHORIZED` | 未登录 | 401 |
| `FORBIDDEN` | 无权限 | 403 |
| `NOT_FOUND` | 资源不存在 | 404 |
| `VALIDATION_ERROR` | 参数校验失败 | 400 |
| `DUPLICATE_KEY` | 重复键 | 400 |
| `CONSTRAINT_VIOLATION` | 约束违反 | 400 |
| `INTERNAL_ERROR` | 服务器错误 | 500 |

---

## 七、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-05-12 | 初始版本 |
