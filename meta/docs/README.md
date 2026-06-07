# 元数据对象模型

## 概述

面向语义的元数据对象模型，用于描述业务系统的数据结构和关系。

## 核心概念

### 元数据对象 (MetaObject)

元数据对象描述一个业务实体的完整定义，包括：
- 字段定义 (Fields)
- 关联关系 (Relations)
- 操作定义 (Actions)
- 校验规则 (Validations)
- 语义标注 (Semantics)

### 层级结构

```
产品线 (Product)
    ↓ 1:N
产品版本 (Version)
    ↓ 1:N
领域 (Domain)
    ↓ 1:N
子领域 (SubDomain)
    ↓ 1:N
服务模块 (ServiceModule)
    ↓ 1:N
业务对象 (BusinessObject)
    ↓ N:M
业务关系 (Relationship)
```

## 元数据对象列表

| 对象ID | 名称 | 层级 | 说明 |
|--------|------|------|------|
| `product` | 产品线 | 1 | 业务系统的顶层分类 |
| `version` | 产品版本 | 2 | 产品线的软件版本 |
| `domain` | 领域 | 3 | 业务领域的顶层分类 |
| `sub_domain` | 子领域 | 4 | 业务领域的细分 |
| `service_module` | 服务模块 | 5 | 独立的服务模块 |
| `business_object` | 业务对象 | 6 | 领域模型的核心实体 |
| `relationship` | 业务关系 | 7 | 业务对象之间的关联 |

## AI Agent 使用示例

### 查询元数据对象

```python
from meta import registry, get_meta_object, list_meta_objects

# 列出所有元数据对象
for obj_id in list_meta_objects():
    obj = get_meta_object(obj_id)
    print(f"{obj.name}: {obj.description}")

# 获取业务对象元数据
bo = get_meta_object("business_object")

# 获取字段列表
for field in bo.fields:
    print(f"  {field.name}: {field.field_type.value}")

# 获取关联关系
for rel in bo.relations:
    print(f"  {rel.name} -> {rel.target_object}")
```

### 查询层级路径

```python
from meta import get_hierarchy

# 获取业务对象的层级路径
path = get_hierarchy("business_object")
# 返回: ['product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object']
```

### 查询关联路径

```python
from meta import get_relation_path

# 获取业务对象到产品线的关联路径
path = get_relation_path("business_object", "product")
# 返回关联关系列表
```

## 语义标注说明

语义标注用于描述元数据的业务含义，便于 AI Agent 理解：

| 标注 | 说明 | 示例 |
|------|------|------|
| `meaning` | 业务含义 | "业务对象的唯一编码" |
| `business_key` | 是否为业务标识 | true |
| `display_name` | 是否为显示名称 | true |
| `pattern` | 格式模式 | "^[A-Z][A-Z0-9_]*$" |
| `examples` | 示例值 | ["BO_ORDER", "BO_USER"] |
| `aliases` | 别名列表 | ["BO", "业务对象"] |
| `category` | 业务分类 | "core_entity" |
| `hierarchy_level` | 层级深度 | 6 |

## 文件结构

```
meta/
├── core/
│   └── models.py          # 核心模型定义
├── objects/
│   ├── __init__.py        # 注册所有对象
│   ├── product.py         # 产品线定义
│   ├── version.py         # 版本定义
│   ├── domain.py          # 领域定义
│   ├── sub_domain.py      # 子领域定义
│   ├── service_module.py  # 服务模块定义
│   ├── business_object.py # 业务对象定义
│   └── relationship.py    # 业务关系定义
├── schemas/
│   └── business_object.yaml  # YAML 配置示例
└── docs/
    └── README.md          # 本文档
```

## 扩展指南

### 添加新的元数据对象

1. 在 `meta/objects/` 创建新的 Python 文件
2. 定义 `MetaObject` 实例
3. 在 `meta/objects/__init__.py` 中注册

### 添加新的字段类型

1. 在 `meta/core/models.py` 的 `FieldType` 枚举中添加
2. 更新相关的类型检查逻辑

### 添加新的操作类型

1. 在 `meta/core/models.py` 的 `ActionType` 枚举中添加
2. 实现对应的操作处理器
