# 枚举 API 规范

> **版本**: v1.0.0
> **创建日期**: 2026-05-08
> **参考**: OpenAPI Specification 3.0

---

## 一、概述

本文档定义了枚举类型相关 API 的规范，包括路径约定、请求格式、响应格式等。所有枚举相关 API 必须遵循本规范。

---

## 二、API 端点

### 2.1 获取枚举类型列表

**端点**: `GET /api/v1/enum-types`

**描述**: 获取所有枚举类型的基本信息列表

**请求参数**:

| 参数 | 类型 | 位置 | 必需 | 说明 |
|------|------|------|------|------|
| page | integer | query | 否 | 页码，默认 1 |
| page_size | integer | query | 否 | 每页数量，默认 50 |
| category | string | query | 否 | 枚举分类筛选 |

**响应格式**:

```json
{
  "success": true,
  "data": [
    {
      "id": "annotation_category",
      "name": "备注分类",
      "category": "business",
      "value_count": 5
    }
  ],
  "page": 1,
  "page_size": 50,
  "total": 10
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| success | boolean | 请求是否成功 |
| data | array | 枚举类型列表 |
| data[].id | string | 枚举类型 ID（唯一标识） |
| data[].name | string | 枚举类型显示名称 |
| data[].category | string | 枚举分类 |
| data[].value_count | integer | 枚举值数量 |
| page | integer | 当前页码 |
| page_size | integer | 每页数量 |
| total | integer | 总数量 |

---

### 2.2 获取枚举类型详情

**端点**: `GET /api/v1/enum-types/{enum_type_id}`

**描述**: 获取指定枚举类型的详细信息（不包含值列表）

**路径参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| enum_type_id | string | 是 | 枚举类型 ID |

**响应格式**:

```json
{
  "success": true,
  "data": {
    "id": "annotation_category",
    "name": "备注分类",
    "category": "business",
    "description": "备注分类",
    "mutability": "fully_editable",
    "dimension_count": 0,
    "value_count": 5,
    "created_at": "2026-05-05T23:10:26.116975",
    "updated_at": "2026-05-06T10:30:43.110454"
  },
  "message": "Success"
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 枚举类型 ID |
| name | string | 枚举类型名称 |
| category | string | 枚举分类（system/business） |
| description | string | 枚举描述 |
| mutability | string | 可维护性 |
| dimension_count | integer | 维度数量 |
| value_count | integer | 枚举值数量 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

---

### 2.3 获取枚举值列表

**端点**: `GET /api/v1/enum-types/{enum_type_id}/values`

**描述**: 获取指定枚举类型的所有枚举值

**路径参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| enum_type_id | string | 是 | 枚举类型 ID |

**请求参数**:

| 参数 | 类型 | 位置 | 必需 | 说明 |
|------|------|------|------|------|
| page | integer | query | 否 | 页码，默认 1 |
| page_size | integer | query | 否 | 每页数量，默认 50 |
| is_active | boolean | query | 否 | 是否激活 |

**响应格式**:

```json
{
  "success": true,
  "data": {
    "data": [
      {
        "id": 421,
        "code": "important",
        "name": "IMPORTANT",
        "name_en": null,
        "parent_code": null,
        "dimensions": null,
        "sort_order": 0,
        "is_system": 1,
        "is_active": 1,
        "metadata": null,
        "enum_type_id": "annotation_category",
        "created_at": "2026-05-05T23:10:26.118156",
        "updated_at": "2026-05-06T10:30:43.110637"
      }
    ],
    "enum_type": {
      "id": "annotation_category",
      "name": "备注分类",
      "category": "business",
      "description": "备注分类"
    },
    "page": 1,
    "page_size": 50,
    "total": 5
  },
  "message": "Success"
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| data.data | array | 枚举值列表 |
| data.data[].id | integer | 枚举值 ID |
| data.data[].code | string | 枚举值代码（唯一标识） |
| data.data[].name | string | 枚举值名称（用于显示） |
| data.data[].name_en | string | 英文名称 |
| data.data[].parent_code | string | 父级代码（层级枚举用） |
| data.data[].sort_order | integer | 排序顺序 |
| data.data[].is_system | integer | 是否系统预置（1=是，0=否） |
| data.data[].is_active | integer | 是否激活（1=是，0=否） |
| data.data[].dimensions | object | 维度配置 |
| data.data[].metadata | object | 元数据 |
| data.data[].enum_type_id | string | 所属枚举类型 ID |
| data.enum_type | object | 所属枚举类型详情 |
| data.page | integer | 当前页码 |
| data.page_size | integer | 每页数量 |
| data.total | integer | 总数量 |

---

### 2.4 创建枚举值

**端点**: `POST /api/v1/enum-types/{enum_type_id}/values`

**描述**: 为指定枚举类型创建新枚举值

**路径参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| enum_type_id | string | 是 | 枚举类型 ID |

**请求体**:

```json
{
  "code": "custom_value",
  "name": "自定义值",
  "name_en": "Custom Value",
  "sort_order": 10,
  "dimensions": {}
}
```

**请求字段说明**:

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| code | string | 是 | 枚举值代码（唯一） |
| name | string | 是 | 枚举值名称 |
| name_en | string | 否 | 英文名称 |
| sort_order | integer | 否 | 排序顺序 |
| dimensions | object | 否 | 维度配置 |
| metadata | object | 否 | 元数据 |

**响应格式**:

```json
{
  "success": true,
  "data": {
    "id": 429,
    "code": "custom_value",
    "name": "自定义值"
  },
  "message": "Success"
}
```

---

### 2.5 更新枚举值

**端点**: `PUT /api/v1/enum-values/{value_id}`

**描述**: 更新指定枚举值

**路径参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| value_id | integer | 是 | 枚举值 ID |

**请求体**:

```json
{
  "name": "更新后的名称",
  "sort_order": 5,
  "is_active": 1
}
```

---

### 2.6 删除枚举值

**端点**: `DELETE /api/v1/enum-values/{value_id}`

**描述**: 删除指定枚举值

**路径参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| value_id | integer | 是 | 枚举值 ID |

---

## 三、API 规范要点

### 3.1 路径约定

| 规范 | 说明 |
|------|------|
| 复数形式 | 使用 `/enum-types`（复数）而非 `/enum-type` |
| 资源嵌套 | 值列表使用 `/enum-types/{id}/values` |
| 层级关系 | 使用路径参数而非查询参数 |

**正确示例**:
- `GET /api/v1/enum-types` - 枚举类型列表
- `GET /api/v1/enum-types/{id}` - 枚举类型详情
- `GET /api/v1/enum-types/{id}/values` - 枚举值列表

**错误示例**:
- ❌ `GET /api/v1/enums/{id}` - 单数形式
- ❌ `GET /api/v1/enum-type-values?enum_type_id=xxx` - 使用查询参数

---

### 3.2 响应格式约定

| 规范 | 说明 |
|------|------|
| 统一包装 | 所有响应使用 `{success, data, message}` 结构 |
| 嵌套数据 | 列表数据使用 `data.data` 嵌套结构 |
| 分页信息 | 分页信息包含在 `data` 中 |

**响应格式示例**:

```json
{
  "success": true,
  "data": {
    "data": [],      // 实际数据列表
    "enum_type": {}, // 关联对象
    "page": 1,
    "page_size": 50,
    "total": 100
  },
  "message": "Success"
}
```

---

### 3.3 错误响应格式

```json
{
  "success": false,
  "data": null,
  "message": "错误描述信息",
  "code": "ERROR_CODE"
}
```

**常见错误码**:

| 错误码 | 说明 |
|--------|------|
| NOT_FOUND | 资源不存在 |
| VALIDATION_ERROR | 参数验证失败 |
| DUPLICATE_CODE | 代码重复 |
| UNAUTHORIZED | 未授权 |
| FORBIDDEN | 无权限 |

---

## 四、前端调用示例

### 4.1 使用 fetch

```javascript
// 加载枚举选项
async function loadEnumOptions(enumTypeId) {
  const token = localStorage.getItem('auth_token');
  
  const response = await fetch(
    `/api/v1/enum-types/${enumTypeId}/values`,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  
  const result = await response.json();
  
  if (!result.success) {
    throw new Error(result.message);
  }
  
  // 解析枚举值（注意 data.data 嵌套结构）
  const values = result.data.data || [];
  
  return values.map(v => ({
    value: v.code,
    label: v.name
  }));
}

// 使用示例
const options = await loadEnumOptions('annotation_category');
console.log(options);
// 输出: [{value: 'important', label: 'IMPORTANT'}, ...]
```

### 4.2 使用 axios

```javascript
import axios from 'axios';

async function loadEnumOptions(enumTypeId) {
  const response = await axios.get(
    `/api/v1/enum-types/${enumTypeId}/values`,
    {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
      }
    }
  );
  
  const result = response.data;
  
  if (!result.success) {
    throw new Error(result.message);
  }
  
  const values = result.data.data || [];
  
  return values.map(v => ({
    value: v.code,
    label: v.name
  }));
}
```

---

## 五、相关文档

- [跨表过滤配置文档](../metadata/cross-table-filters.md)
- [组件治理规范](../../.trae/rules/component-governance.md)
- [元模型驱动过滤规范](../../.trae/specs/meta-model-driven-filters/spec.md)

---

**最后更新**: 2026-05-08
