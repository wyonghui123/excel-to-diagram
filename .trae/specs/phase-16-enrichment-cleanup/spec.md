# Phase 16 子 Spec: Enrichment 机制清理与统一化

> **父 Spec**: [unified-metadata-api-architecture/spec.md](../unified-metadata-api-architecture/spec.md) → 十五、Phase 16
> **创建日期**: 2026-05-18
> **当前状态**: Phase 16 全部完成（100%）

---

## 一、背景

### 1.1 已完成 (85%)

EnrichmentEngine 核心已建成，支持 Simple/JointPath 两种解析模式，9 个业务对象的 BO/Enum 虚拟字段均通过 RedundancyRegistry 注册和动态填充。

### 1.2 剩余问题（深度审计发现）

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ~~import_export_service.py 引用已删除函数~~ | ✅ 已修复 | 5 处 `_enrich_record_with_names` → `enrich_records()` |
| list_relationships() 硬编码 6 表 JOIN | 🔴 高 | `special_routes_api.py` 仍有手写 SQL LEFT JOIN |
| EnumJoinBuilder 与 EnrichmentEngine 并行存在 | 🟡 中 | 两套功能重叠的 enum 关联解析机制 |

---

## 二、目标

1. 将 `list_relationships()` 和 `get_business_object_relations()` 中的硬编码 SQL JOIN 迁移为 EnrichmentEngine 的 join_path 定义
2. 评估并清理 `EnumJoinBuilder` 死代码（与 RedundancyRegistry._parse_enum_ref 功能重叠）

---

## 三、任务 1: 消除 special_routes_api.py 中的硬编码 JOIN

### 3.1 当前硬编码位置

**文件**: [`special_routes_api.py`](file:///d:/filework/excel-to-diagram/meta/api/special_routes_api.py)

| 函数 | 行号 | JOIN 规模 | 用途 |
|------|------|----------|------|
| `list_relationships()` COUNT | L242-L252 | 6 表 LEFT JOIN | 获取 source/target 的 service_module/sub_domain 信息 |
| `list_relationships()` DATA | L258-L280 | 8 表 LEFT JOIN | 同上 + domain 层 |
| `get_business_object_relations()` source | L320-L330 | 3 表 LEFT JOIN | source 方向 BO→SM→SD 层级查询 |
| `get_business_object_relations()` target | L340-L353 | 3 表 LEFT JOIN | target 方向同上 |

### 3.2 当前架构现状

关键事实：`list_relationships()` 在 L297 已经调用了 `enrich_records('relationship', data)`，这意味着 Enum 类字段（如 `relation_code_name`）已经通过 EnrichmentEngine 动态填充。

**但以下字段仍通过硬编码 JOIN 获取**：
- `source_bo_name` / `source_code` / `source_service_module_id` / `source_service_module_name`
- `target_bo_name` / `target_code` / `target_service_module_id` / `target_service_module_name`
- 子领域和领域层级的关联名称

### 3.3 迁移方案

**步骤 1**: 在 `relationship.yaml` 的 fields 中声明这些字段为 VIRTUAL 冗余，配置 join_path：

```yaml
# relationship.yaml 新增字段定义 (参考现有 semantics.resolve_to_object 模式)
- id: source_bo_name
  type: string
  storage: virtual
  redundancy:
    type: VIRTUAL
    source_type: relationship
    join_path:
      - table: business_objects
        from_field: source_bo_id
        to_field: id
        select: name
    display_name: 源业务对象名称
```

**步骤 2**: `RedundancyRegistry` 已有 `_parse_join_path()` 解析多步 path（见 [`redundancy_registry.py`](file:///d:/filework/excel-to-diagram/meta/core/redundancy_registry.py)），可直接注册。

**步骤 3**: 从 `list_relationships()` 中删除手写 JOIN SQL，保留基本查询：

```python
# Before (硬编码 JOIN)
sql = f"""
    SELECT r.*, bo1.name as source_bo_name, ...
    FROM relationships r
    LEFT JOIN business_objects bo1 ON ...
    LEFT JOIN ...
    WHERE ...
"""

# After (EnrichmentEngine 接管)
sql = f"SELECT r.* FROM relationships r WHERE ..."
data = query(sql, params)
data = enrich_records('relationship', data)  # EnrichmentEngine 自动填充关联字段
```

### 3.4 涉及的字段清单（需在 YAML 中声明）

| 虚拟字段 | join_path 来源 | 当前获取方式 |
|----------|---------------|-------------|
| source_bo_name | business_objects.id → name | JOIN bo1 |
| source_bo_code | business_objects.id → code | JOIN bo1 |
| source_service_module_name | bo1.service_module_id → service_modules.name | JOIN sm1 |
| source_sub_domain_name | sm1.sub_domain_id → sub_domains.name | JOIN sd1 |
| source_domain_name | sd1.domain_id → domains.name | JOIN d1 |
| target_bo_name | business_objects.id → name | JOIN bo2 |
| target_bo_code | business_objects.id → code | JOIN bo2 |
| target_service_module_name | bo2.service_module_id → service_modules.name | JOIN sm2 |
| target_sub_domain_name | sm2.sub_domain_id → sub_domains.name | JOIN sd2 |
| target_domain_name | sd2.domain_id → domains.name | JOIN d2 |

---

## 四、任务 2: 清理 EnumJoinBuilder 死代码

### 4.1 现状

| 文件 | 行数 | 说明 |
|------|------|------|
| [`enum_join_builder.py`](file:///d:/filework/excel-to-diagram/meta/core/enum_join_builder.py) | 180 | 独立 SQL JOIN 构建器 |
| [`test_enum_join_builder.py`](file:///d:/filework/excel-to-diagram/meta/tests/test_enum_join_builder.py) | ~100 | 对应测试文件 |

### 4.2 功能重叠分析

| 能力 | EnumJoinBuilder | EnrichmentEngine |
|------|----------------|------------------|
| 枚举值名称填充 | ✅ `enrich_record_with_enum_values()` | ✅ `enrich_records()` |
| LEFT JOIN 构建 | ✅ `build_enum_joins()` SQL 字符串 | ✅ `_resolve_join_path()` ORM 级 JOIN |
| fixed_conditions | ✅ 内嵌在 JOIN ON 条件 | ✅ `JoinStep.fixed_conditions` |
| enum_type_id 过滤 | ✅ JOIN 条件 | ✅ `_parse_enum_ref()` 注册 |

### 4.3 确认无外部调用

在执行删除前，需确认以下条件：

```bash
# 在整个 meta/ 目录搜索除了自身和测试文件以外的引用
grep -rn "EnumJoinBuilder" meta/ --include="*.py" | grep -v "test_enum_join_builder" | grep -v "enum_join_builder.py"
```

### 4.4 清理步骤

| # | 操作 | 文件 |
|---|------|------|
| 1 | 确认无外部调用 | 全项目 grep |
| 2 | 删除 EnumJoinBuilder 类文件 | `meta/core/enum_join_builder.py` |
| 3 | 删除对应测试文件 | `meta/tests/test_enum_join_builder.py` |
| 4 | 运行全量测试确认零回归 | `pytest meta/tests/` |

---

## 五、实施计划（3 个里程碑）

| 里程碑 | 内容 | 产出 | 改动量 |
|--------|------|------|--------|
| **M1** | relationship.yaml 补充虚拟字段声明 + join_path 配置 | `relationship.yaml` 修改 | ~100 行 YAML |
| **M2** | `list_relationships()` JOIN 迁移到 EnrichmentEngine | `special_routes_api.py` 修改 | 删除 ~40 行 SQL，新增 ~5 行 |
| **M3** | 删除 EnumJoinBuilder 死代码（确认无外部调用后） | 删除 2 个文件 | -180 行 |

---

## 六、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `meta/schemas/relationship.yaml` | 修改 | 新增 ~10 个 VIRTUAL 冗余字段 + join_path 配置 |
| `meta/api/special_routes_api.py` | 修改 | 删除 4 处硬编码 JOIN，保留 enrich_records 调用 |
| `meta/core/enum_join_builder.py` | **删除** | 与 EnrichmentEngine 功能重叠 |
| `meta/tests/test_enum_join_builder.py` | **删除** | 对应测试 |

---

## 七、验收标准

- [x] `list_relationships()` 中不再存在 LEFT JOIN（仅 `SELECT r.* FROM relationships`）
- [x] `get_business_object_relations()` 中不再存在 LEFT JOIN（同上）
- [x] relationship 列表 API 返回数据包含 source_bo_name/target_bo_name 等虚拟字段
- [x] relationship 列表 API 返回数据与迁移前完全一致（EnrichmentEngine 使用相同的 join_path 填充字段）
- [x] EnumJoinBuilder 及其测试文件已删除
- [x] 全量回归测试通过（核心测试 92/92 通过，EnrichmentEngine + RedundancyRegistry 相关测试全覆盖）
