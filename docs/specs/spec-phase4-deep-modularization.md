# Spec: Phase 4 — 深层模块化拆分

> **版本**: v1.0
> **日期**: 2026-05-26
> **状态**: 待确认（计划稿）
> **前置**: [Phase 3 已完成](./spec-phase3-architecture-optimization.md) — 浅层提取 + 常量 + 安全加固全部到位
> **关联**: 本 Spec 承接 Phase 3 §5.1 中未完成的深层拆分设计

---

## 1. 背景：Phase 3 做了什么 vs 没做什么

### 1.1 Phase 3 已完成

| 层面 | 成果 |
|------|------|
| 纯数据提取 | `models_enums.py`（24个枚举）、`query_models.py`（7个dataclass） |
| 常量提取 | `action_constants.py`（CRUD/ASSOCIATE等）、`ui_config/config_constants.py` |
| 重复消除 | `_downloadBlob()` 统一、`batch_assign`/`batch_unassign` 合并、semantics 数据驱动化 |
| 安全闭环 | `safe_expr_evaluator` 审计+43个测试、CustomEvent→Pinia、并发控制 |
| 架构解耦 | `get_ui_config()` 295行→2行委托、`association_audit.py` 循环依赖打破 |

### 1.2 Phase 3 未完成（本 Spec 要做的）

Phase 3 §5.1 的原始设计目标是把 5 个巨型文件按**职责拆分为独立子模块**：

| 原文件 | 原始行数 | Phase 3 后 | 理想目标 | 差距 |
|------|:---:|:---:|------|:---:|
| `query_service.py` | 2257 | ~2070 | 5 子模块 各 200-400行 | 对 `search()` 等大方法未拆 |
| `models.py` | 2189 | ~1170 | 5 子模块 各 150-300行 | 77 个 dataclass 仍在同一文件 |
| `boService.js` | ~830 | 598 | 4 子服务 各 100-200行 | 仅拆了导出导入，CRUD/关联/搜索仍在 |
| `association_engine.py` | 1344 | ~1289 | 策略模式 5-6 个 handler | batch 优化做了，未拆 handler 类 |
| `bo_framework.py` | ~900 | 498 | ✅ 已完成 | `get_ui_config()` 已完全拆分 |

---

## 2. 逐文件详细拆分方案

### 2.1 `query_service.py` → 6 子模块

**当前**：`query_service.py` 2169 行，33 个类方法 + 3 个模块级函数，`search()` 方法 214 行。

#### 2.1.1 目标架构

```
meta/services/query/
├── __init__.py                 ← re-export QueryService
├── query_builder.py            ← FilterBuilder (~400行)
├── query_sorter.py             ← SortManager + VirtualFieldSort (~350行)
├── query_enricher.py           ← ResultEnricher + AuditEnricher (~300行)
├── query_hierarchy.py          ← HierarchyResolver (~250行)
├── query_aggregator.py         ← AggregateEngine (~200行)
└── query_models.py             ✅ 已有（7个dataclass, 83行）
```

#### 2.1.2 各模块职责和方法归属

**`query_builder.py` — FilterBuilder** (~400行)

| 来源方法 | 行数 | 职责 |
|------|:---:|------|
| `_apply_meta_driven_filters` | 200 | 元数据驱动过滤器：遍历字段→解析过滤条件→构建SQL |
| `_apply_computed_field_filter` | 62 | 计算字段过滤：解析computation→构建WHERE子句 |
| `_parse_filter_value` | 45 | 值解析：支持逗号分隔/范围/JSON数组 |
| `_apply_count_relations_filter` | 87 | 关联计数过滤：子查询COUNT |
| `_apply_count_children_filter` | 52 | 子对象计数过滤 |
| `_build_computed_where_clause` | 33 | 计算字段WHERE子句构建 |
| `_build_virtual_field_filter_exists` | 89 | 虚拟字段过滤：EXISTS子查询 |
| `_apply_cross_table_filters` | 77 | 跨表关联过滤 |
| `_build_exists_subquery` | 99 | EXISTS子查询构建器 |
| `_apply_data_permission` | 38 | 行级数据权限 |
| `_apply_soft_delete_filter` | 23 | 软删除过滤 |

**`query_sorter.py` — SortManager** (~350行)

| 来源方法 | 行数 | 职责 |
|------|:---:|------|
| `_build_virtual_field_order_join` | 84 | 虚拟字段排序：build JOIN + ORDER BY |
| `_execute_virtual_field_query` | 94 | 虚拟字段排序查询执行 |
| `_sort_by_virtual_fields` | 18 | 应用层虚拟字段排序（内存排序fallback） |
| `_sort_by_computed_field` | 61 | 计算字段排序（公式求值+排序） |
| `_execute_computed_field_query` | 165 | 计算字段排序SQL查询 |
| `_ensure_hierarchy_ids_for_relationships` | 71 | 关系字段层级id补齐 |

**`query_enricher.py` — ResultEnricher** (~300行)

| 来源方法 | 行数 | 职责 |
|------|:---:|------|
| `_enrich_audit_virtual_fields` | 71 | 审计虚拟字段填充 |
| `_enrich_with_relations` | 49 | 关联数据填充（N+1 优化点） |
| `enrich_dimension_names` (模块级) | 69 | 维度名称填充 |
| `full_text_search` | 37 | 全文本搜索 |
| `suggest` | 18 | 自动补全建议 |

**`query_hierarchy.py` — HierarchyResolver** (~250行)

| 来源方法 | 行数 | 职责 |
|------|:---:|------|
| `query_by_hierarchy_path` | 39 | 按层级路径查询 |
| `_apply_hierarchy_filter` | 33 | 层级过滤SQL构建 |
| `_apply_path_name_filters` | 59 | 路径名称过滤 |
| `_resolve_object_id_by_depth` | 6 | 按深度解析对象ID |
| `_get_name_field` | 8 | 获取名称字段 |
| `_get_child_object_id` | 6 | 获取子对象ID |
| `_get_parent_field` | 9 | 获取父对象字段 |
| `_get_ancestor_parent_field` | 15 | 获取祖先父字段 |

**`query_aggregator.py` — AggregateEngine** (~200行)

| 来源方法 | 行数 | 职责 |
|------|:---:|------|
| `aggregate` | 67 | 聚合查询主入口 |
| `_apply_filter` | 33 | 聚合过滤应用 |

**`QueryService` 保留** (~200行)

| 方法 | 行数 | 说明 |
|------|:---:|------|
| `__init__` | 2 | 注入子模块 |
| `search` | 214→80 | 编排5个子模块：FilterBuilder→SortManager→Enricher→Hierarchy→Aggregator |
| `discover_analytics_fields` | 19 | 分析字段发现 |

#### 2.1.3 `search()` 方法拆解 — 最关键的改造

当前 `search()` (L260-L474, 214行) 是命令式流水线，拆为：

```python
def search(self, request):
    # Step 1: 构建基础查询
    builder = self._filter_builder.build_base_query(request)
    # Step 2: 应用过滤
    builder = self._filter_builder.apply_all_filters(builder, request)
    # Step 3: 应用排序（含虚拟字段）
    builder, virtual_info = self._sort_manager.apply_sort(builder, request)
    # Step 4: 执行查询（分页）
    records, total = self._sort_manager.execute_paginated(builder, virtual_info, request)
    # Step 5: 富化结果
    records = self._result_enricher.enrich(records, request)
    return SearchResult(records=records, total=total, page=request.page, page_size=request.page_size)
```

#### 2.1.4 延迟导入处理

12 处 `from meta` 延迟导入 → 迁移到子模块，各自在文件头部导入，消除方法内延迟导入。

---

### 2.2 `models.py` → 4 子模块

**当前**：`models.py` ~1170行，77 个非枚举 dataclass/class。

#### 2.2.1 目标架构

```
meta/core/
├── models.py                    ← MetaRegistry + MetaObject + MetaField (~400行, 核心)
├── models_enums.py              ✅ 已有（24个枚举, 246行）
├── models_annotations.py        ← 9个注解类 (~250行)
├── models_value_help.py         ← 8个ValueHelp类 (~250行)
├── models_ui_config.py          ← 14个UIViewConfig类 (~300行)
├── models_rules.py              ← 11个规则/推导类 (~250行)
├── models_actions.py            ← 5个Action类 (~100行)
├── models_queries.py            ← 3个Query类 (~40行)
├── models_views.py              ← 6个View类 (~80行)
├── models_policies.py           ← 5个Policy类 (~50行)
└── models_configs.py            ← 12个杂项配置类 (~200行)
```

#### 2.2.2 各模块分配

| 模块文件 | 包含的类 | 行数 |
|------|------|:---:|
| **models.py** (保留) | `MetaRegistry`, `MetaField`, `EnhancedMetaField`, `MetaRelation`, 全局 `registry` 实例 | ~420 |
| **models_enums.py** | ✅ 24个枚举（已完成） | 246 |
| **models_annotations.py** | `SemanticAnnotation`, `UIAnnotation`, `RenderHints`, `PermissionAnnotation`, `I18nKey`, `EnumReference`, `DimensionReference`, `FieldDependency`, `IndexHint` | ~300 |
| **models_value_help.py** | `ValueHelpConfig`, `ValueHelpParameterBinding`, `ValueHelpOutMapping`, `CascadeSelectConfig`, `ValueHelpSource`, `ValueHelpBehavior`, `ValueHelpDisplayColumn`, `ValueHelpPresentation` | ~280 |
| **models_ui_config.py** | `UIListViewColumn`, `UIListViewConfig`, `UIDetailFacet`, `UIDetailTab`, `UIDetailViewConfig`, `UIFormColumn`, `UIFormSection`, `UIFormViewConfig`, `UIFilterDefinition`, `UIFilterViewConfig`, `ChangeEventConfig`, `WebhookConfig`, `ChangeNotificationConfig`, `UIViewConfig` | ~320 |
| **models_rules.py** | `MetaRule`, `MetaValidation`, `MetaConstraint`, `MetaComputation`, `StateTransitionSideEffect`, `StateTransitionUIHints`, `MetaStateTransition`, `MetaTrigger`, `DerivationAggregate`, `DerivationMapping`, `MetaDerivation` | ~270 |
| **models_actions.py** | `ActionParameter`, `ActionPrecondition`, `ActionEffect`, `ActionBehavior`, `MetaAction` | ~120 |
| **models_queries.py** | `MetaQueryFilter`, `MetaQuerySort`, `MetaQuery` | ~45 |
| **models_views.py** | `ViewSource`, `ViewJoin`, `ViewAggregate`, `ViewFilter`, `ViewConfig`, `VirtualConfig` | ~90 |
| **models_policies.py** | `PolicyRule`, `EditablePolicy`, `VisiblePolicy`, `RequiredPolicy`, `FieldPolicy` | ~55 |
| **models_configs.py** | `HierarchyPathInfo`, `DeletabilityConfig`, `AddabilityConfig`, `DataPermissionDimension`, `MetricReference`, `MetaFunction`, `MetaIndex`, `BoCategoryConfig`, `ImportExportConfig`, `AuditActionConfig`, `AuditConfig`, `MetaObject` | ~300 |

#### 2.2.3 关键决策

- `MetaObject` 是核心类（~300行 + 丰富的 helper 方法），放入 `models_configs.py` 或保留在 `models.py`。建议**保留在 `models.py`**，因为它是注册表的操作对象
- `migrate_to_unified_value_help()` 模块级函数 → 移入 `models_value_help.py`
- `MetaRegistry` 保留在 `models.py`，因为 `registry` 全局实例需要独立文件

---

### 2.3 `boService.js` → 3 新子服务

**当前**：`boService.js` 598行，BOService 类 43 方法。`boExportImportService.js` 已提取。

#### 2.3.1 目标架构

```
src/services/
├── boService.js                ← Facade (~250行)
├── bo/                         ← 子服务目录
│   ├── boCrudService.js        ← CRUD 7个方法 (~120行)
│   ├── boAssociationService.js ← 关联 10个方法 (~200行)
│   ├── boExportImportService.js ✅ 已有（230行）
│   ├── boSearchHelpService.js  ← 搜索帮助 2个方法 (~50行)
│   └── boHierarchyService.js   ← 层级 3个方法 (~45行)
```

#### 2.3.2 各模块分配

**`boCrudService.js`** (~120行)

| 方法 | 行数 | 说明 |
|------|:---:|------|
| `create` | 14 | POST /bo/{type} |
| `read` | 18 | GET /bo/{type}/{id} |
| `query` | 33 | POST /bo/{type}/query（含缓存逻辑） |
| `update` | 14 | PUT /bo/{type}/{id} |
| `delete` | 13 | DELETE /bo/{type}/{id} |
| `batchCreate` | 13 | POST /bo/{type}/batch |
| `batchDelete` | 13 | POST /bo/{type}/batch-delete |

**继承 BaseService**（需 `API_BASE`、`_getHeaders`、`_handleResponse`、`_getAuthStore`、`_clearListCache`）

**`boAssociationService.js`** (~200行)

| 方法 | 行数 | v1/v2 | 说明 |
|------|:---:|:---:|------|
| `associate` | 22 | v1 | POST /bo/{type}/{id}/associate |
| `dissociate` | 21 | v1 | POST /bo/{type}/{id}/dissociate |
| `queryAssociations` | 31 | v1 | GET /bo/{type}/{id}/associations |
| `queryAssociationsV2` | 26 | v2 | GET /bo/{type}/{id}/associations/v2 |
| `countAssociationsV2` | 10 | v2 | GET /bo/{type}/{id}/associations/count |
| `assignAssociationV2` | 21 | v2 | POST /bo/{type}/{id}/associations/v2/assign |
| `unassignAssociationV2` | 21 | v2 | POST /bo/{type}/{id}/associations/v2/unassign |
| `batchAssignAssociationsV2` | 16 | v2 | POST /bo/{type}/{id}/associations/v2/batch-assign |
| `batchUnassignAssociationsV2` | 16 | v2 | POST /bo/{type}/{id}/associations/v2/batch-unassign |
| `batchQueryAssociations` | 11 | v1+v2 | POST /bo/{type}/batch-query-associations |

**可优化点**：
- v1 和 v2 的 `associate`/`dissociate` 差异仅在 URL 路径，可合并
- `assignAssociationV2`/`batchAssignAssociationsV2` 合并为单方法+参数控制

**`boSearchHelpService.js`** (~50行)

| 方法 | 行数 |
|------|:---:|
| `searchValueHelp` | 32 |
| `resolveValueHelp` | 13 |

**`boHierarchyService.js`** (~45行)

| 方法 | 行数 |
|------|:---:|
| `getHierarchyTree` | 16 |
| `getChildCount` | 14 |
| `getObjectPath` | 8 |

#### 2.3.3 `boService.js` Facade (~250行)

```javascript
class BOService extends BaseService {
  constructor() {
    super(100, 5 * 60 * 1000)
    this._crud = new BOCrudService()
    this._association = new BOAssociationService()
    this._exportImport = new BOExportImportService()  // ✅ 已有
    this._searchHelp = new BOSearchHelpService()
    this._hierarchy = new BOHierarchyService()
  }

  // CRUD 委托 — 7个方法，各 2行
  create(type, data) { return this._crud.create(type, data) }
  // ...

  // Association 委托 — 10个方法
  associate(...) { return this._association.associate(...) }
  // ...

  // 其余方法同模式
}
```

**API 调用方零改动** — `boService.create(...)` 签名完全不变。

---

### 2.4 `association_engine.py` → 策略模式

**当前**：`association_engine.py` 1289 行，42 个方法。

#### 2.4.1 目标架构

```
meta/core/association/
├── __init__.py                  ← re-export AssociationEngine
├── engine.py                    ← AssociationEngine 主调度器 (~150行)
├── base_handler.py              ← BaseAssociationHandler 抽象基类 (~80行)
├── m2m_handler.py               ← M2MAssociationHandler (~250行)
├── reference_handler.py         ← ReferenceAssociationHandler (~200行)
├── composition_handler.py       ← CompositionAssociationHandler (~150行)
├── batch_handler.py             ← BatchHandler (~200行)
├── resolvers.py                 ← _resolve_assoc_meta + helpers (~80行)
├── validators.py                ← 校验+约束方法 (~120行)
└── fallback.py                  ← 回退方法 (~60行)
```

#### 2.4.2 策略模式接口

```python
class BaseAssociationHandler(ABC):
    """关联处理器抽象基类"""
    
    @abstractmethod
    def associate(self, context, assoc_meta): ...
    
    @abstractmethod
    def dissociate(self, context, assoc_meta): ...
    
    @abstractmethod
    def query(self, context, assoc_meta): ...
    
    @abstractmethod
    def count(self, context, assoc_meta): ...
    
    def assign(self, context, assoc_meta): ...
    def unassign(self, context, assoc_meta): ...


class M2MAssociationHandler(BaseAssociationHandler):
    # _associate_m2m, _dissociate_m2m, _query_m2m, _count_m2m,
    # _assign_m2m, _unassign_m2m, _check_m2m_exists

class ReferenceAssociationHandler(BaseAssociationHandler):
    # _associate_reference, _dissociate_reference, _query_reference, _count_reference,
    # _assign_reference, _unassign_reference

class CompositionAssociationHandler(BaseAssociationHandler):
    # _associate_composition, _query_composition, _count_composition,
    # _assign_composition
    # (dissociate/unassign = unsupported)
```

#### 2.4.3 各模块方法分配

**`engine.py` — 主调度器** (~150行)

```python
class AssociationEngine:
    def __init__(self):
        self._handlers = {
            'many_to_many': M2MAssociationHandler(),
            'reference': ReferenceAssociationHandler(),
            'composition': CompositionAssociationHandler(),
        }
        self._batch_handler = BatchHandler(self._handlers)
        self._resolver = AssociationResolver()
        self._validator = AssociationValidator()
    
    def _dispatch(self, context, operation):  # ~40行→ 简化
        assoc_meta = self._resolver.resolve(context.object_type, context.params['association_name'])
        handler = self._handlers.get(assoc_meta.get('type'))
        if not handler:
            return self._fallback(context, operation)
        method = getattr(handler, operation)
        return method(context, assoc_meta)
    
    # 6个 public 方法 — 各1行委托
    def associate(self, context): return self._dispatch(context, 'associate')
    def dissociate(self, context): return self._dispatch(context, 'dissociate')
    # ...
```

**`m2m_handler.py`** (~250行)

| 方法 | 行数 |
|------|:---:|
| `associate` | 53 |
| `dissociate` | 25 |
| `query` | 42 |
| `count` | 18 |
| `assign` | 53 |
| `unassign` | 23 |
| `_check_m2m_exists` | 7 |
| 其他内部helper | ~30 |

**`reference_handler.py`** (~200行)

| 方法 | 行数 |
|------|:---:|
| `associate` | 36 |
| `dissociate` | 30 |
| `query` | 37 |
| `assign` | 31 |
| `unassign` | 27 |
| `count` | 21 |

**`composition_handler.py`** (~150行)

| 方法 | 行数 |
|------|:---:|
| `associate` | 36 |
| `query` | 34 |
| `count` | 24 |
| `assign` | 32 |

**`batch_handler.py`** (~200行)

| 方法 | 行数 | 说明 |
|------|:---:|------|
| `batch_assign` | 2 | 委托 |
| `batch_unassign` | 2 | 委托 |
| `_batch_operation` | 33 | ✅ 已有 |
| `_try_bulk_m2m` | 36 | ✅ 已有 |
| `batch_query_associations` | 22 | ✅ 已有 |
| `_batch_query_m2m` | 58 | |
| `_batch_query_composition` | 38 | |
| `_batch_query_reverse_m2m` | 58 | |

**`resolvers.py`** (~80行)

| 方法 | 行数 |
|------|:---:|
| `_resolve_assoc_meta` | 22 |
| `_to_dict` | 9 |
| `_get_attr` | 4 |
| `_get_search_fields` | 16 |

**`validators.py`** (~120行)

| 方法 | 行数 |
|------|:---:|
| `_validate_source_target_existence` | 37 |
| `_check_cardinality_constraint` | 25 |
| `_get_current_association_count` | 39 |
| `_reassign_existing` | 34 |
| `_check_fk_required_before_unassign` | 20 |

**`fallback.py`** (~60行)

| 方法 | 行数 |
|------|:---:|
| `_fallback_associate` | 35 |
| `_fallback_dissociate` | 25 |
| `_fallback_query_associations` | 11 |
| `_query_audit_logs` | 54 |

---

## 3. 里程碑计划

```
M4a: models.py 拆注解/ValueHelp/UIView（最低风险，纯dataclass迁移）
     ├── models_annotations.py      ← 9个注解类
     ├── models_value_help.py       ← 8个ValueHelp类
     ├── models_ui_config.py        ← 14个UIViewConfig类
     └── models.py re-export 保持兼容
     
M4b: boService.js 拆 CRUD/搜索/层级
     ├── boCrudService.js           ← 7个CRUD方法
     ├── boSearchHelpService.js     ← 2个搜索帮助方法
     ├── boHierarchyService.js      ← 3个层级方法
     └── boService.js Facade 委托

M4c: association_engine.py 策略模式
     ├── base_handler.py            ← 抽象基类
     ├── m2m_handler.py             ← 6个M2M方法
     ├── reference_handler.py       ← 6个Reference方法
     ├── composition_handler.py     ← 4个Composition方法
     ├── batch_handler.py           ← 6个batch方法
     └── validators.py + resolvers.py + fallback.py

M4d: query_service.py 拆 Builder/Sorter/Enricher/Hierarchy/Aggregator
     ├── query_builder.py           ← FilterBuilder（12个方法）
     ├── query_sorter.py            ← SortManager（6个方法）
     ├── query_enricher.py          ← ResultEnricher（4个方法）
     ├── query_hierarchy.py         ← HierarchyResolver（8个方法）
     ├── query_aggregator.py        ← AggregateEngine（2个方法）
     └── QueryService 编排层精简

M4e: 深层清理 + 全局审计
     ├── 清理空文件/废弃import
     ├── 延迟导入审计和消除
     └── 全量运行所有测试
```

### 实施顺序建议

| 里程碑 | 风险 | 工时（人天） | 顺序 |
|:---:|:---:|:---:|:---:|
| M4a | 🟢 极低 | 2 | 1️⃣ |
| M4b | 🟢 低 | 1.5 | 2️⃣ |
| M4c | 🟠 中 | 3 | 3️⃣ |
| M4d | 🔴 高 | 4 | 4️⃣ |
| M4e | 🟢 低 | 1 | 5️⃣ |
| **总计** | | **11.5** | |

---

## 4. 风险评估与缓解

| 风险 | 影响文件 | 严重度 | 缓解措施 |
|------|------|:---:|------|
| 循环依赖 | models.py 各子模块 | 🔴 高 | models.py 作为中心 re-export hub，子模块不互相导入 |
| YAML 加载器兼容 | `yaml_loader.py` 依赖 models dataclass | 🟠 中 | 子模块通过 models.py re-export 透明访问 |
| `search()` 编排逻辑断裂 | `query_service.py` | 🔴 高 | 完整单元测试 + 集成测试，每步验证 |
| boService 子服务共享 BaseService | `boCrudService.js` 等 | 🟡 低 | 子服务各自继承 BaseService，Facade 委托 |
| 前端调用方 break | 15+ 个 .vue/.js 文件 | 🟢 极低 | Facade 模式保证 API 签名不变 |

---

## 5. 测试覆盖要求

### 5.1 已覆盖（不变）

- `test_core_engine_layer.py` — QueryBuilder/AssociationEngine/ActionExecutor（14通过）
- `test_safe_expr_evaluator.py` — 43个安全测试（100%通过）
- `test_ui_config_enhanced.py` — UI配置完整性

### 5.2 新增测试

| 测试文件 | 覆盖目标 | 用例数 |
|------|------|:---:|
| `test_query_builder.py` | FilterBuilder 的 12 个过滤方法 | 15+ |
| `test_query_sorter.py` | SortManager 的虚拟字段排序 + 计算字段排序 | 10+ |
| `test_query_enricher.py` | ResultEnricher 的审计填充 + 关联填充 | 8+ |
| `test_association_handlers.py` | M2M/Reference/Composition 三种 handler 独立测试 | 12+ |
| `test_batch_handler.py` | 批量操作 + bulk M2M 路径 | 6+ |

---

## 6. 预期效果

| 指标 | 当前 | 目标 |
|------|:---:|:---:|
| `query_service.py` | 2169行 单文件 | QueryService ~180行 + 5子模块各200-400行 |
| `models.py` | 1170行 | ~420行核心 + 9子模块各50-300行 |
| `boService.js` | 598行 | ~250行 Facade + 4子服务各45-200行 |
| `association_engine.py` | 1289行 | ~150行引擎 + 8子模块各50-250行 |
| 单个文件最大行数 | 2169 | <450 |
| 方法平均行数 | ~65 | <40 |
| API 调用方改动 | — | **0**（全 Facade 委托） |
| 新增单元测试 | 0 | 50+ |
| 测试回归期望 | — | **0** |

---

## 7. TBD 列表

| ID | 项目 | 状态 | 待决断 |
|------|------|:---:|------|
| TBD-4-1 | v1/v2 关联API是否在拆分时统一合并 | 🔴 待决 | `boAssociationService.js` 中有 v1 `associate` 和 v2 `associateV2`，可在拆分时合并为一个方法 |
| TBD-4-2 | `MetaObject` 归属 | 🟡 待决 | 保留在 `models.py` 还是移入 `models_configs.py`？ |
| TBD-4-3 | `query_aggregator.py` 是否需要独立文件 | 🟡 待决 | 目前只有2个方法（67行），可先放在 `query_builder.py` 末尾，后续扩展时独立 |
| TBD-4-4 | `migrate_to_unified_value_help()` 模块级函数归属 | 🟢 建议 | 移入 `models_value_help.py` |

---

> **文档状态**: 计划稿 v1.0。基于对 4 个文件的逐行审计生成。待评审确认后进入执行。
