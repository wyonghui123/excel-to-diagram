# Schema 管理 API 使用说明

## 概述

Schema API 提供 HTTP 接口来管理数据库表结构，支持：
- 自动同步 YAML 元模型到数据库
- 查看表结构状态
- 创建新表
- 增量更新列

## API 列表

### 1. 同步所有表
```bash
POST /api/v1/schema/sync
```
根据 YAML 元模型自动创建或更新所有表。

**响应示例：**
```json
{
  "success": true,
  "message": "Schema 同步完成",
  "data": {
    "created": [
      {"object": "annotation", "table": "annotations"}
    ],
    "updated": [
      {"object": "product", "table": "products", "message": "已存在"}
    ],
    "errors": []
  }
}
```

### 2. 查看同步状态
```bash
GET /api/v1/schema/status
```

**响应示例：**
```json
{
  "success": true,
  "data": {
    "synced": [
      {"object": "product", "table": "products"}
    ],
    "missing": [
      {"object": "annotation", "table": "annotations"}
    ],
    "mismatch": [
      {
        "object": "business_object",
        "table": "business_objects",
        "missing_columns": ["annotation_category"]
      }
    ]
  }
}
```

### 3. 列出所有表
```bash
GET /api/v1/schema/tables
```

### 4. 查看表结构
```bash
GET /api/v1/schema/tables/{table_name}
```

**示例：**
```bash
GET /api/v1/schema/tables/annotations
```

### 5. 创建单个表
```bash
POST /api/v1/schema/tables/{table_name}/create
Content-Type: application/json

{
  "object_id": "annotation"
}
```

## 使用示例

### 场景1：首次初始化数据库
```bash
# 同步所有表
curl -X POST http://localhost:5000/api/v1/schema/sync
```

### 场景2：添加新表（如 annotations）
```bash
# 方法1：同步所有
curl -X POST http://localhost:5000/api/v1/schema/sync

# 方法2：只创建 annotations 表
curl -X POST http://localhost:5000/api/v1/schema/tables/annotations/create \
  -H "Content-Type: application/json" \
  -d '{"object_id": "annotation"}'
```

### 场景3：检查缺失的表
```bash
# 查看状态
curl http://localhost:5000/api/v1/schema/status

# 如果发现 annotations 表缺失，执行同步
curl -X POST http://localhost:5000/api/v1/schema/sync
```

## 注册 API

在 `meta/server.py` 中添加：

```python
from meta.api.schema_api import schema_bp

# ... 其他蓝图注册
app.register_blueprint(schema_bp)
```

## 注意事项

1. **自动创建列**：同步时会自动添加 YAML 中定义但数据库中不存在的列
2. **不删除列**：为了安全，不会自动删除数据库中已存在的列
3. **幂等性**：可以多次执行同步，不会重复创建表
4. **权限**：需要确保运行用户有数据库写权限
