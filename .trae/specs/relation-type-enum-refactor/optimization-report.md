# 关系类型枚举化 — 当前状态报告

> **注意**：原 `optimization-report.md` 声称"所有优化已完成"，经代码审计发现与实际情况不符。
> 本文档为 2026-05-25 审计后的**真实状态**。

---

## 已完成项

### Phase 1: 枚举类型定义 ✅

- ✅ `relation_type` 枚举类型已创建（GENERATES/UPDATES/TRIGGERS/REFERENCES），含 dimension_schema 和中文名
- ✅ `relation_category` 枚举类型已创建（data_flow/process_flow/dependency）
- ✅ `models.py` 中 `BusinessRelationType` 和 `RelationCategory` 枚举类已注册
- ✅ `migrate_enums.py` 中已注册，启动时自动同步
- ✅ `init_database.py` 中的 `init_relation_enums()` 已重构为委托 `migrate_enums()`，消除重复维护

### 数据库枚举值清理 ✅

- ✅ 元模型 `RelationType` 从 `ENUM_CLASSES` 移除，不再写入 `enum_values` 表
- ✅ `parent_child`/`reference`/`many_to_many`/`composition` 已通过 `cleanup_orphan_enum_values()` 清理
- ✅ `relation_type` 枚举 API 返回干净的 4 个业务值（GENERATES/UPDATES/TRIGGERS/REFERENCES）

---

## 未完成 / 待修正项

### 维度未独立化 ⚡ 高优先级 — [新 spec 已建立]

原 spec 将 `direction` / `dependency_strength` 内嵌为 `dimension_schema` JSON 字符串，
无法在枚举管理页面维护，不可复用。**新方案见**：

- [spec.md](file:///d:/filework/excel-to-diagram/.trae/specs/relation-type-enum-refactor/spec.md) — Spec
- [optimization-plan.md](file:///d:/filework/excel-to-diagram/.trae/specs/relation-type-enum-refactor/optimization-plan.md) — 实现方案
- [tasks.md](file:///d:/filework/excel-to-diagram/.trae/specs/relation-type-enum-refactor/tasks.md) — 任务分解

### EnumJoinBuilder 不存在

原 `optimization-report.md` 声称的 `meta/core/enum_join_builder.py` 不存在于当前代码库。
不过 `RedundancyRegistry._parse_enum_ref` 提供了等价的基础能力。

### 前端 EnumFieldDisplay 零使用

`EnumFieldDisplay.vue` 已创建但未被任何 Vue 组件导入/使用。
`ObjectPage.vue` 仍在硬编码 `prop="relation_code"`。

### manage_api.py 中无硬编码 JOIN

`manage_api.py` 已不包含关系查询代码，那些逻辑已迁移到 `special_routes_api.py`。
`special_routes_api.py` 的 `list_relationships()` 不包含任何 enum JOIN。

---

## 文件实际状态

| 文件 | 原报告声称 | 实际状态 |
|------|-----------|---------
| `meta/core/enum_join_builder.py` | ✅ 已创建 | ❌ 不存在 |
| `meta/api/manage_api.py` | ✅ 已重构 | 🔄 不包含关系查询代码（已迁移） |
| `src/components/EnumFieldDisplay.vue` | ✅ 已创建 | ✅ 存在但零使用 |
| `src/views/.../DynamicDetail.vue` | ✅ 已重构 | ❌ 该目录已不存在（架构演进） |
| `meta/schemas/relationship.yaml` | ✅ enum_join_fields | ❌ relation_type 字段缺少 `semantics.enum_type_ref` |

---

## Fix Log

### 2026-05-25 — 枚举重复/孤儿值清理

- 移除 `RelationType` (PARENT_CHILD/COMPOSITION...) 从 enum 管理页面
- 添加 `cleanup_orphan_enum_values()` 自动清理孤立枚举值
- 统一 `init_database.py` → `migrate_enums.py` 的枚举数据流

### 2026-05-25 — 枚举维度独立化 Spec

- 研究 Salesforce/Palantir/SAP/Datadog/OpenMetadata 枚举依赖模型
- 设计 `enum_dimension_links` 关联表方案
- 编写完整 spec/tasks/checklist 三件套
