# Phase 6 子 Spec: FilterService 抽象层抽离

> **父 Spec**: [unified-metadata-api-architecture/spec.md](../unified-metadata-api-architecture/spec.md) → 八、Phase 6
> **关联 Spec**: [meta-model-driven-filters/spec.md](../meta-model-driven-filters/spec.md)
> **创建日期**: 2026-05-18
> **当前状态**: Phase 6 已完成 95%，剩余 5% 即为本 spec 范围

---

## 一、背景

### 1.1 当前状态

Phase 6 元数据驱动过滤器已实现 9 项核心能力，架构完整：

```
FilterBar.vue (SAP SmartFilterBar)     ← SAP Fiori 风格过滤栏
TableHeaderFilter.vue                   ← 列级悬浮/常驻/手动过滤
filter_service.py (YAML → SQL)          ← 后端过滤构建
filter_variant_api.py                   ← 过滤变体 CRUD (SAP Variant Mgmt)
useFilterFlow.js                        ← 级联依赖 + 多源管理
useGlobalFilters.js                     ← 全局跨表过滤
useWorkspaceFilter.js                   ← 版本上下文 + 层级过滤
useLocalFilters.js                      ← 局部过滤
```

### 1.2 剩余问题

`useMetaList.js`（2560行）中过滤相关代码约 **587 行（占 23%）**，分散在 17 个非连续的代码块中。这违反了单一职责原则，且存在以下具体问题：

| 问题 | 影响 |
|------|------|
| 纯逻辑函数混入 Vue Composable | 无法独立测试，难以复用 |
| `_addFilterParam`/`_buildQueryParams` 在 useMetaList 内部 | useGlobalFilters/useWorkspaceFilter 无法复用参数构建 |
| `_inferFilterType` 等工具函数在前端重复实现 | 与后端 `filter_service.py` 逻辑不一致风险 |
| 过滤变体保存时需临时引用 useMetaList 内部方法 | 架构耦合 |

---

## 二、目标

从 `useMetaList.js` 中抽离纯过滤逻辑到独立的 **`src/services/filterService.js`**，作为纯函数服务层（无 Vue 响应式依赖），被各 Composable 和组件消费。

---

## 三、抽离清单

### 3.1 抽离方法映射（9 个方法）

| # | useMetaList.js 原方法 | 行号 | 新 FilterService 方法 | 行数 | 说明 |
|---|----------------------|------|----------------------|------|------|
| 1 | `_inferFilterType` | L1303-L1332 | `inferFilterType(col)` | ~30 | 根据字段类型推断过滤控件类型 |
| 2 | `_normalizeFilterType` | L1207-L1227 | `normalizeFilterType(rawType)` | ~20 | 标准化过滤类型名称 |
| 3 | `_autoGenerateFiltersFromFields` | L1432-L1496 | `generateFiltersFromFields(fields, metaConfig)` | ~65 | 字段定义 → FilterBar 配置 |
| 4 | `_transformFilters` | L1504-L1538 | `transformFilters(yamlFilters, metaConfig)` | ~35 | YAML filters → FilterBar 格式 |
| 5 | `_backfillColumnFilterType` | L1174-L1205 | `backfillColumnFilterType(columns, rawFilters)` | ~32 | 后端类型信息回填 columns |
| 6 | `_addFilterParam` | L1648-L1732 | `addFilterParam(params, key, value, columns, filterFields)` | ~85 | 构建单个查询过滤参数 |
| 7 | `_buildQueryParams`(过滤部分) | L1760-L1801 | `buildFilterQueryParams(filterValues, headerFilterValues, options)` | ~42 | 过滤值 → API 参数 |
| 8 | `_initDefaultFilterValues` | L1544-L1554 | `getDefaultFilterValues(filterFields)` | ~11 | 提取默认过滤值 |
| 9 | `isVueInternalProp` | L1631-L1646 | `isInternalProp(key)` | ~16 | Vue 内部属性判断 |

### 3.2 不抽离的内容

以下仍留在 `useMetaList.js` 中，因为它们依赖 Vue 响应式状态或与列表生命周期耦合：

| 方法 | 行号 | 保留原因 |
|------|------|---------|
| `handleFilter` | L444-L448 | 触发列表重新加载，依赖响应式 `filterValues` |
| `handleSearch` | L453-L455 | 同上 |
| `handleHeaderFilter` | L663-L671 | 同上 |
| `resetFilters` | L639-L656 | 需清理多个响应式状态 |
| `setContextFilters` | L620-L634 | 依赖 `contextFilters` + 触发 `loadData` |
| `filterValues` / `headerFilterValues` 等响应式状态 | 多处 | Vue ref，不属纯逻辑 |

---

## 四、FilterService API 设计

```javascript
// src/services/filterService.js

// ======== 类型推断 ========

/**
 * 根据字段属性推断过滤控件类型
 * @param {Object} col - 列/字段定义 { type, widget, options, format, enum_type }
 * @returns {'search'|'select'|'date-range'|'number-range'|'multi-select'|'text'}
 */
export function inferFilterType(col)

/**
 * 标准化过滤类型名称（兼容旧命名）
 * @param {string} rawType
 * @returns {string}
 */
export function normalizeFilterType(rawType)

// ======== 字段生成 ========

/**
 * 从 columns/fields 定义自动生成 FilterBar 过滤字段配置
 * @param {Array} fields - YAML 字段定义
 * @param {Object} [metaConfig] - 元数据配置 { field_display_names, columns }
 * @returns {Array} FilterBar fields 配置数组
 */
export function generateFiltersFromFields(fields, metaConfig)

/**
 * 将 YAML filters 数组转化为 FilterBar 格式
 * @param {Array} yamlFilters - YAML 中 filters 数组
 * @param {Object} [metaConfig]
 * @returns {Array}
 */
export function transformFilters(yamlFilters, metaConfig)

/**
 * 用后端 filters 信息补充 columns 的 filter_type
 * @param {Array} columns - 列定义
 * @param {Array} rawFilters - 后端 /api/v2/bo/{type}/_schema 返回的 filters
 */
export function backfillColumnFilterType(columns, rawFilters)

// ======== 参数构建 ========

/**
 * 向参数字典添加单个过滤参数
 * @param {Object} params - 目标参数字典 (mutated)
 * @param {string} key - 字段 key
 * @param {*} value - 过滤值
 * @param {Array} columns - 列定义（用于类型查找）
 * @param {Array} filterFields - 过滤字段定义（用于 filter_type 查找）
 * @param {Object} [options] - { debug: false }
 */
export function addFilterParam(params, key, value, columns, filterFields, options)

/**
 * 从过滤值构建完整 API 查询参数
 * @param {Object} filterValues - FilterBar 当前值
 * @param {Object} headerFilterValues - TableHeaderFilter 当前值
 * @param {Object} options - { columns, filterFields, keyword, sortInfo, defaultOrdering, pagination }
 * @returns {Object} API 请求参数 (filters, keyword, sort, page, page_size 等)
 */
export function buildFilterQueryParams(filterValues, headerFilterValues, options)

/**
 * 获取过滤字段的默认值映射
 * @param {Array} filterFields
 * @returns {Object} { fieldKey: defaultValue }
 */
export function getDefaultFilterValues(filterFields)

// ======== 合并 ========

/**
 * 合并多个过滤源（AND 语义，后覆盖前）
 * @param {...Object} filterSources
 * @returns {Object}
 */
export function mergeFilters(...filterSources)

// ======== 工具 ========

/**
 * 判断是否为 Vue 内部属性（__v_*, $ 等）
 * @param {string} key
 * @returns {boolean}
 */
export function isInternalProp(key)
```

---

## 五、实施计划（5 个里程碑）

### M1: 创建 FilterService 骨架 + 工具函数

**产出**: `src/services/filterService.js`

抽离并导出以下纯工具函数（无外部依赖）：
- `isInternalProp()`
- `normalizeFilterType()`
- `inferFilterType()`

**验证**: 新建 `src/services/__tests__/filterService.spec.js`，覆盖 3 个函数的边界条件

---

### M2: 抽离字段生成逻辑

在 `filterService.js` 中新增：
- `generateFiltersFromFields()` — 需抽象掉对 `field_display_names` 的隐式依赖，改为显式参数
- `transformFilters()`
- `backfillColumnFilterType()`
- `getDefaultFilterValues()`

**useMetaList.js 改动**:
- 将原方法体替换为 `import { generateFiltersFromFields, ... } from '@/services/filterService'`
- 原 `_autoGenerateFiltersFromFields` 中调用 `filterService.auto_generate` 改为调用新方法

**验证**: 5 个单元测试（每种过滤类型生成各 1 个）

---

### M3: 抽离参数构建逻辑

在 `filterService.js` 中新增：
- `addFilterParam()` — **最大最复杂的方法**（~85行），需仔细处理 operator 推断逻辑
- `buildFilterQueryParams()` — 整合 filterValues + headerFilterValues + keyword + sort + pagination
- `mergeFilters()` — AND 语义合并

**特别注意**: `addFilterParam` 中 `operator` 的推断逻辑（`eq`/`like`/`between`/`in`）是业务核心，必须保持与现有行为一致。

**验证**: 8+ 单元测试，覆盖日期范围、多选、外键、文本搜索等场景

---

### M4: useMetaList.js 技侦替换

将 useMetaList.js 中 9 个原方法替换为 `filterService` 调用：

```javascript
// Before (useMetaList.js)
_addFilterParam(params, key, value, columns, filterFields, debug) {
  // ~85 lines of logic
}

// After (useMetaList.js)
import { addFilterParam, buildFilterQueryParams, ... } from '@/services/filterService'

_addFilterParam(params, key, value, columns, filterFields, debug) {
  addFilterParam(params, key, value, columns, filterFields, { debug })
}
```

用薄包装保持 `useMetaList.js` 对外 API 不变，避免连锁改动。

**验证**: 全量回归测试 — 所有涉及过滤的页面（系统管理各页面 + 架构数据管理页面）过滤功能正常

---

### M5: useGlobalFilters / useWorkspaceFilter 消费 FilterService

让 `useGlobalFilters.js` 和 `useWorkspaceFilter.js` 直接消费 `filterService` 的参数构建方法，消除它们各自维护的 `buildFilterParams` 副本。

**验证**: 全局过滤和工作区过滤功能正常，无回归

---

## 六、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/services/filterService.js` | **新建** | FilterService 纯函数服务层 |
| `src/services/__tests__/filterService.spec.js` | **新建** | 单元测试（预计 15+ 用例） |
| `src/composables/useMetaList.js` | **修改** | 9 个方法替换为 filterService 调用，预计减少 ~500 行 |
| `src/composables/useGlobalFilters.js` | **修改** | buildFilterParams 改为消费 filterService |
| `src/composables/useWorkspaceFilter.js` | **修改** | 合并逻辑改为消费 filterService.mergeFilters |

---

## 七、验收标准

- [ ] `filterService.spec.js` 覆盖所有 13 个导出函数，测试通过率 100%
- [ ] useMetaList.js 过滤相关代码从 ~587 行缩减到 ≤ 100 行（仅保留调用封装）
- [ ] 系统管理中所有页面的过滤功能（FilterBar + TableHeaderFilter + 过滤变体）正常
- [ ] 架构数据管理页面的全局过滤 + 工作区过滤正常
- [ ] `useGlobalFilters` 和 `useWorkspaceFilter` 不再重复实现过滤参数构建
- [ ] 无 eslint 错误
