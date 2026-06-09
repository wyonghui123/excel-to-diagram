## 目录

1. [1. 背景与目标](#1-背景与目标)
2. [2. 功能需求](#2-功能需求)
3. [3. 非功能需求](#3-非功能需求)
4. [4. 行业对比与方案合理性分析](#4-行业对比与方案合理性分析)
5. [5. 实施计划](#5-实施计划)
6. [6. 风险与缓解](#6-风险与缓解)
7. [7. TBD 列表](#7-tbd-列表)

---
# Spec: 前端业务逻辑下沉 — 后端 API 增强

> **版本**: v1.0.0
> **日期**: 2026-06-06
> **状态**: ✅ 已完成（6/6 FR 全部实施）
> **范围**: 后端 API 增强 + 前端推断逻辑消除
> **前置依赖**: [spec-v3-convergence-phase2.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-v3-convergence-phase2.md)（Phase 2 已完成）
> **关联文档**: [spec-ui-business-logic-downflow.md v3.3.1](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md)

---

## 1. 背景与目标

### 1.1 问题根因

Phase 1/2 解决了"fetch 迁移"的表层问题，但深度分析发现前端存在 **3 个根因问题**：

| 根因 | 表现 | 行业对比 |
|------|------|---------|
| **后端返回数据不完整** | 前端 6 个 infer 函数推断 UI 配置 | Salesforce/SAP 后端直接返回 UI-ready 数据，前端零推断 |
| **后端缺少聚合 API** | 前端 N+1 查询 + 多步编排 | PostgREST/Hasura 支持 $expand，一次返回关联数据 |
| **后端缺少权威判定 API** | 前端实现权限/策略引擎 | ServiceNow ACL 后端强制执行，Salesforce 返回 fieldLevelSecurity |

### 1.2 行业最佳实践对比

| 维度 | Salesforce | SAP Fiori | ServiceNow | **本项目** |
|------|-----------|-----------|------------|----------|
| UI 配置在 API 响应中？ | 是（一站式 UI API） | 是（$metadata 注解） | 是（meta API） | **否**（前端推断） |
| 字段级权限在 API 响应中？ | 是（fieldLevelSecurity） | 部分（FieldControl） | 是（ACL + Data Policy） | **否**（前端计算） |
| 前端需要推断？ | 几乎不需要 | 少量 | 执行声明式规则 | **6 个 infer 函数** |
| 前后端策略分离？ | 否（后端决定一切） | 部分 | **是**（UI Policy vs ACL） | **否**（前端独立实现） |

**核心差距**：本项目后端已有 `FieldPolicyEngine`（490 行），但**没有 API 端点暴露**，前端 `useFieldPolicy.js`（390 行）是独立实现，与后端完全脱节。

### 1.3 后端已有能力盘点

| 后端能力 | 文件 | 状态 | 前端是否使用 |
|---------|------|:----:|:----------:|
| FieldPolicyEngine | `meta/services/field_policy_engine.py` (490 行) | 已实现 | **未使用**（无 API 端点） |
| FieldPolicyValidation | `meta/services/field_policy_validation.py` | 已实现 | **未使用** |
| YAML width 字段 | `meta/core/yaml_loader.py` L541,679 | 已定义 | **未使用**（前端 inferColumnWidth） |
| YAML filter_type 字段 | `meta/core/yaml_loader.py` L320,684 | 已定义 | **未使用**（前端 inferFilterType） |
| YAML position 字段 | `meta/core/yaml_loader.py` L680 | 已定义 | **未使用**（前端 inferActionPosition） |
| YAML priority 字段 | `meta/core/yaml_loader.py` L272,1367 | 已定义 | **未使用**（前端 inferColumnPriority） |

**关键发现**：后端 YAML 已支持 `width`/`filter_type`/`position`/`priority` 字段，但前端没有使用，而是自己推断。问题不是"后端没有"，而是"后端有但前端没用"。

### 1.4 业务目标

1. **消除前端推断**：6 个 infer 函数改为读取后端返回的字段
2. **消除 N+1 问题**：批量关联 API，50 次请求 → 1 次
3. **消除前端权限计算**：字段策略由后端权威返回
4. **消除前端数据聚合**：架构预览 API 一次返回完整数据

---

## 2. 功能需求

### FR-BE-001: Schema API 增补 UI 提示字段（消除前端推断）

- **描述**: 后端 schema/ui-config API 必须返回前端需要的 UI 配置字段，消除 6 个前端 infer 函数
- **验收标准**:

  **2.1 后端 schema API 响应增强**：

  `GET /api/v1/meta/objects/{objectType}` 和 `GET /api/v1/meta/ui-config/{objectType}` 响应中，每个字段必须包含：

  | 字段 | 类型 | 来源 | 当前前端推断函数 |
  |------|------|------|----------------|
  | `width` | number | YAML `width` 字段 | `inferColumnWidth` |
  | `min_width` | number | 计算值（width * 0.6） | `inferColumnWidth` |
  | `filter_type` | string | YAML `filter_type` 字段 | `inferFilterType` |
  | `priority` | string | YAML `importance` 字段 | `inferColumnPriority` |
  | `edit_config` | object | 后端推断 | `inferFieldEditConfig` |
  | `position` | string | YAML `position` 字段 | `inferActionPosition` |

  **2.2 edit_config 结构**（后端根据字段类型+语义推断）：

  ```json
  {
    "edit_config": {
      "control_type": "input|textarea|select|date|datetime|number|checkbox|switch",
      "value_help": { "type": "enum|search_help|url", "source": "..." },
      "max_length": 255,
      "placeholder": "请输入..."
    }
  }
  ```

  **2.3 前端 infer 函数降级为 fallback**：

  | 函数 | 变更 |
  |------|------|
  | `inferColumnWidth` | 优先读 `field.width`，无值时才推断 |
  | `inferFilterType` | 优先读 `field.filter_type`，无值时才推断 |
  | `inferColumnPriority` | 优先读 `field.priority`，无值时才推断 |
  | `inferFieldEditConfig` | 优先读 `field.edit_config`，无值时才推断 |
  | `inferActionPosition` | 优先读 `action.position`，无值时才推断 |

- **优先级**: Must
- **来源**: 行业对比 — Salesforce UI API / SAP OData UI.Annotations

### FR-BE-002: 字段策略 API（消除前端权限计算）

- **描述**: 后端必须暴露 FieldPolicyEngine 的评估结果，前端不再独立计算字段可编辑性/可见性/必填性
- **验收标准**:

  **2.1 新增 API 端点**：

  ```
  GET /api/v2/meta/{objectType}/field-policies?context={mutability}&action={read|create|update}
  ```

  响应：
  ```json
  {
    "success": true,
    "data": {
      "field_name": {
        "editable": true,
        "visible": true,
        "required": false,
        "readonly_reason": null
      },
      "status": {
        "editable": false,
        "visible": true,
        "required": false,
        "readonly_reason": "immutable"
      },
      "secret_field": {
        "editable": false,
        "visible": false,
        "required": false,
        "readonly_reason": "hidden"
      }
    }
  }
  ```

  **2.2 前端 useFieldPolicy.js 变更**：

  | 当前行为 | 变更后 |
  |---------|--------|
  | 7 级判断链 + mutability 状态机 | 读取后端 `field_policies` 响应 |
  | editableMap/visibleMap/immutableMap computed | 从 API 响应初始化 |
  | isEditable 多级判断 | `fieldPolicies[field].editable` |
  | evaluateMutability 状态机 | 后端评估，前端只读 |

  **2.3 兼容性**：

  - API 调用失败时，前端 fallback 到当前推断逻辑（降级策略）
  - 后端 FieldPolicyEngine 已有完整实现（490 行），只需暴露 API 端点
  - 参考 ServiceNow 模式：UI Policy（前端体验优化）+ ACL（后端强制执行）

- **优先级**: Must
- **来源**: 行业对比 — Salesforce fieldLevelSecurity / ServiceNow ACL

### FR-BE-003: 批量关联 API（消除 N+1 问题）

- **描述**: 后端必须提供批量关联操作 API，替代前端逐个调用
- **验收标准**:

  **3.1 新增 API 端点**：

  ```
  POST /api/v2/bo/{objectType}/{id}/associations/{assocName}/batch-assign
  Body: { "target_ids": ["id1", "id2", ...], "context": {} }

  POST /api/v2/bo/{objectType}/{id}/associations/{assocName}/batch-unassign
  Body: { "target_ids": ["id1", "id2", ...], "context": {} }
  ```

  响应：
  ```json
  {
    "success": true,
    "data": {
      "assigned": 48,
      "skipped": 2,
      "skipped_ids": ["id49", "id50"],
      "skipped_reasons": { "id49": "already_assigned", "id50": "not_found" }
    }
  }
  ```

  **3.2 事务保证**：

  - 后端在单个事务中执行批量操作
  - 全成功或全失败（原子性）
  - 部分成功时返回详细结果（幂等性：已关联的跳过不报错）

  **3.3 前端变更**：

  | 当前行为 | 变更后 |
  |---------|--------|
  | useDetail.batchAssignAssociation: N 次 boService.associate() | 1 次 batch-assign API |
  | useBOApi.batchAssociate: N 次 boService.associate() | 1 次 batch-assign API |
  | defaultLimiter 并发控制 | 不再需要 |
  | failedCount 统计 | 读取 skipped_ids |

- **优先级**: Must
- **来源**: 行业对比 — PostgREST resource embedding / Hasura bulk mutations

### FR-BE-004: 架构预览聚合 API（消除前端数据聚合）

- **描述**: 后端必须提供架构预览聚合 API，一次返回完整树结构数据
- **验收标准**:

  **4.1 新增 API 端点**：

  ```
  GET /api/v2/architecture/preview?version_id={id}&domain_ids=1,2&sub_domain_ids=3&service_module_ids=4&business_object_ids=5
  ```

  响应：
  ```json
  {
    "success": true,
    "data": {
      "domain_products": { ... },
      "business_objects": [ ... ],
      "service_modules": [ ... ],
      "relationships": [ ... ],
      "center_scope": ["bo_code_1", "bo_code_2"]
    }
  }
  ```

  **4.2 替代前端逻辑**：

  | 当前前端逻辑 | 后端 API 替代 |
  |------------|-------------|
  | archDataConverter.fetchTreeData (5 次 API) | 1 次 /architecture/preview |
  | archDataConverter.buildDomainProducts (前端 join) | 后端直接返回 domain_products |
  | archDataConverter.buildPreviewDataFromArchData (前端过滤) | 后端根据参数过滤 |
  | archDataConverter.convertToCenterScope (前端推导) | 后端返回 center_scope |
  | relationClassifier.buildRelationScopeTree (前端聚合) | 后端返回 classification_tree（可选，Phase 2） |

  **4.3 前端变更**：

  - `archDataConverter.js` 精简为 API 调用 + 数据适配层（~50 行）
  - `relationClassifier.js` 的 `buildRelationScopeTree` 保留前端版本（Phase 2 再下沉，需设计分类树 API）

- **优先级**: Should
- **来源**: 行业对比 — Salesforce UI API 一站式响应 / PostgREST resource embedding

### FR-BE-005: 权威判定 API 增强（消除前端权限/菜单计算）

- **描述**: 后端 API 必须返回权威的权限判定结果，前端不再自行计算
- **验收标准**:

  **5.1 /auth/me 响应增强**：

  ```json
  {
    "user": { ... },
    "is_admin": true,
    "permissions": ["*"],
    "available_actions": ["create", "read", "update", "delete"]
  }
  ```

  | 当前前端逻辑 | 变更后 |
  |------------|--------|
  | authStore.isAdmin: 7 行判断链 | `user.is_admin` |

  **5.2 /menu-permission/visible 响应增强**：

  ```json
  {
    "menus": [ ... ],
    "leaf_menus": [ ... ],
    "object_type_route_map": { "domain": "/domain/list", ... }
  }
  ```

  | 当前前端逻辑 | 变更后 |
  |------------|--------|
  | useMenuPermissions.leafMenus: 前端过滤 | 后端返回 leaf_menus |
  | useMenuPermissions.objectTypeRouteMap: 前端构建 | 后端返回 object_type_route_map |
  | useMenuPermissions._homeOnlyFallback: 硬编码 | 后端保证至少返回首页 |

  **5.3 列表行操作 API 增强**：

  `GET /api/v2/bo/{objectType}?...` 响应中每行增加：

  ```json
  {
    "id": 1,
    "name": "test",
    "_meta": {
      "available_row_actions": ["edit", "delete"],
      "row_mutability": "fully_editable"
    }
  }
  ```

  | 当前前端逻辑 | 变更后 |
  |------------|--------|
  | metaTransformService.filterRowActions: 前端过滤 | 后端返回 available_row_actions |

- **优先级**: Should
- **来源**: 行业对比 — Salesforce fieldLevelSecurity / ServiceNow ACL

### FR-BE-006: 元数据合并 API（消除前端多步请求）

- **描述**: 后端提供合并的元数据 API，减少前端请求次数
- **验收标准**:

  **6.1 新增 API 端点**：

  ```
  GET /api/v2/meta/{objectType}/full
  ```

  响应合并 uiConfig + schema + fieldPolicies：
  ```json
  {
    "success": true,
    "data": {
      "ui_config": { ... },
      "schema": { ... },
      "field_policies": { ... },
      "cascade_chain": [ ... ],
      "parent_id_field": "domain_id"
    }
  }
  ```

  **6.2 替代前端逻辑**：

  | 当前前端逻辑 | 变更后 |
  |------------|--------|
  | metaService.getFullMeta: 2 次 API 并行 | 1 次 /meta/{type}/full |
  | metaService.getCascadeFields: 前端推导 | 后端返回 cascade_chain |
  | metaService.getParentIdField: 前端推断 | 后端返回 parent_id_field |
  | metaService 10min LRU 缓存 | 后端 ETag/304 或减少缓存时间 |

  **6.3 枚举批量预加载**：

  ```
  GET /api/v1/enums/batch?types=type1,type2,type3
  ```

  | 当前前端逻辑 | 变更后 |
  |------------|--------|
  | enumService 逐类型请求 + 5min LRU 缓存 | 批量预加载，减少请求数 |

- **优先级**: Could
- **来源**: 行业对比 — Salesforce UI API 一站式 / SAP $metadata 全量注解

---

## 3. 非功能需求

### NFR-BE-001: 后端 API 性能

- **描述**: 新增聚合 API 的响应时间不超过现有单次 API 的 2 倍
- **测量**: 后端 benchmark
- **优先级**: Should

### NFR-BE-002: 前端降级兼容

- **描述**: 后端新 API 不可用时，前端 fallback 到现有推断逻辑
- **测量**: API 返回 404/500 时，前端行为与当前一致
- **优先级**: Must

### NFR-BE-003: 后端 FieldPolicyEngine 一致性

- **描述**: 后端 FieldPolicyEngine 的评估结果必须与前端 useFieldPolicy 的判断结果一致
- **测量**: 对比测试（同输入，同输出）
- **优先级**: Must

---

## 4. 行业对比与方案合理性分析

### 4.1 方案与行业最佳实践的映射

| 我们的方案 | Salesforce | SAP Fiori | ServiceNow | 合理性 |
|-----------|-----------|-----------|------------|:------:|
| FR-BE-001: Schema 增补 UI 字段 | UI API 返回 editable/required/label | $metadata UI.Annotations | meta API 返回 visible/mandatory | ✅ 符合行业共识 |
| FR-BE-002: 字段策略 API | fieldLevelSecurity | Common.FieldControl | ACL + Data Policy | ✅ 符合行业共识 |
| FR-BE-003: 批量关联 API | N/A（GraphQL） | $batch | N/A | ✅ REST 标准模式 |
| FR-BE-004: 架构预览聚合 | UI API 一站式 | $expand | N/A | ✅ BFF 模式 |
| FR-BE-005: 权威判定 | is_admin + FLS | @restrict | ACL | ✅ 符合行业共识 |
| FR-BE-006: 元数据合并 | UI API | $metadata | meta API | ✅ 减少请求 |

### 4.2 关键差异与取舍

| 决策点 | Salesforce 方案 | 我们的方案 | 理由 |
|--------|---------------|-----------|------|
| UI 配置与数据是否合并 | 合并（UI API） | 分离（schema API + field-policies API） | 渐进式改造，避免大爆炸重构 |
| 前端是否保留 fallback | 否（后端决定一切） | 是（API 不可用时降级） | 兼容性保障，参考 ServiceNow UI Policy vs ACL |
| 权限是静态还是动态 | 静态（layout 级别） | 动态（请求时评估） | 支持 mutability 等上下文相关权限 |
| 是否引入 GraphQL | 否（纯 REST） | 否（保持 REST） | 项目已有 REST 基础设施，GraphQL POC 未启用 |

### 4.3 不采纳的方案

| 方案 | 不采纳理由 |
|------|---------|
| Salesforce 一站式 UI API | 改动面太大，需重构所有前端页面 |
| SAP OData Annotations | 项目不用 OData，引入成本高 |
| Hasura Schema 变形 | 项目不用 GraphQL，且隐式权限不如显式返回直观 |
| 前端完全删除推断逻辑 | 后端 API 不可用时前端会崩溃，需保留 fallback |

---

## 5. 实施计划

### 5.1 优先级与里程碑

| 里程碑 | FR | 内容 | 优先级 |
|--------|-----|------|:------:|
| M1 | FR-BE-001 | Schema 增补 UI 字段 + 前端 infer 降级 | Must |
| M2 | FR-BE-002 | 字段策略 API + 前端 useFieldPolicy 简化 | Must |
| M3 | FR-BE-003 | 批量关联 API + 前端 N+1 消除 | Must |
| M4 | FR-BE-005 | 权威判定 API 增强 | Should |
| M5 | FR-BE-004 | 架构预览聚合 API | Should |
| M6 | FR-BE-006 | 元数据合并 API | Could |

### 5.2 实施顺序

```
M1 (Schema UI 字段) → M2 (字段策略 API) → M3 (批量关联) → M4 (权威判定) → M5 (架构预览) → M6 (元数据合并)
```

**M1 先行**：因为后端 YAML 已支持 width/filter_type/position/priority，只需确保 API 响应中包含这些字段，前端改动最小。

**M2 紧随**：后端 FieldPolicyEngine 已实现，只需暴露 API 端点，收益最高（消除 390 行前端策略引擎）。

**M3 独立**：批量关联 API 是纯新增端点，不依赖 M1/M2。

### 5.3 前端变更量估算

| FR | 前端变更文件 | 变更行数 |
|----|-----------|:-------:|
| FR-BE-001 | metaTransformService.js + filterService.js | ~100 行（infer 函数加 fallback） |
| FR-BE-002 | useFieldPolicy.js | ~300 行（7 级判断链 → API 读取） |
| FR-BE-003 | useDetail.js + useBOApi.js + associationService.js | ~80 行（N 次调用 → 1 次） |
| FR-BE-004 | archDataConverter.js | ~250 行（5 次 API → 1 次） |
| FR-BE-005 | authStore.js + useMenuPermissions.js + metaTransformService.js | ~100 行 |
| FR-BE-006 | metaService.js + enumService.js | ~60 行 |

---

## 6. 风险与缓解

| 风险 | 缓解策略 |
|------|---------|
| 后端 FieldPolicyEngine 与前端 useFieldPolicy 结果不一致 | M2 实施前做对比测试，确保同输入同输出 |
| 聚合 API 响应时间过长 | 后端做性能测试，必要时加缓存 |
| 前端 fallback 逻辑与 API 逻辑冲突 | fallback 仅在 API 不可用时触发，正常路径走 API |
| 批量关联 API 事务超时 | 设置合理的事务超时（如 30s），超时返回部分结果 |

---

## 7. TBD 列表

| ID | 项目 | 结论 | 依据 |
|----|------|------|------|
| TBD-1 | 后端 YAML width/filter_type 字段是否在 API 响应中已返回 | 需验证 | yaml_loader 已解析，但 API 序列化可能未包含 |
| TBD-2 | FieldPolicyEngine 评估结果与前端 useFieldPolicy 是否一致 | 需对比测试 | 两者独立实现，可能存在差异 |
| TBD-3 | 批量关联 API 的事务隔离级别 | 需设计 | 大批量（>100 条）可能需要分批提交 |
| TBD-4 | 架构预览 API 是否包含关系分类树 | Phase 2 决定 | 关系分类树 API 设计复杂，可先返回原始数据 |

---

_Spec 包含 7 个章节，最后一节为"TBD 列表"，内容完整。_
