# FilterService 规格文档

> **版本**: 1.0.0
> **创建日期**: 2026-05-19
> **文件**: `src/services/filterService.js`
> **测试**: `src/services/__tests__/filterService.spec.js` (50 tests)

---

## 1. 概述

FilterService 是前端过滤逻辑的**纯函数抽象层**，从 `useMetaList.js` 抽离（-309 行）。

### 设计原则

| 原则 | 说明 |
|------|------|
| **纯函数** | 无副作用，相同输入永远产生相同输出 |
| **单一职责** | 每个函数只做一件事 |
| **可组合** | 函数之间可相互调用构建复杂逻辑 |
| **无状态** | 不依赖 Vue 响应式状态，可在任何上下文使用 |

### 设计参考

- SAP SADL (Service Adaptation Definition Language) 过滤框架
- Salesforce LDS (Lightning Data Service) Filter
- 后端 `filter_service.py` 的设计模式

---

## 2. API 规格

### 2.1 isInternalProp(key)

判断是否为 Vue 内部属性。

**参数**:
- `key` {string} - 属性名

**返回**: `{boolean}`

**示例**:
```javascript
isInternalProp('__v_isRef')  // true
isInternalProp('name')       // false
```

**用途**: 过滤 Vue 响应式代理对象的内部属性。

---

### 2.2 formatDate(date, isEndTime)

格式化日期为 `YYYY-MM-DD HH:mm:ss` 格式。

**参数**:
- `date` {Date|string} - 日期
- `isEndTime` {boolean} - 是否是结束时间（自动设置为 23:59:59）

**返回**: `{string}`

**示例**:
```javascript
formatDate('2026-05-19')              // '2026-05-19 00:00:00'
formatDate('2026-05-19', true)        // '2026-05-19 23:59:59'
formatDate(new Date())                // '2026-05-19 14:30:00'
```

**用途**: 日期范围过滤的参数格式化。

---

### 2.3 inferFilterType(col)

根据字段属性推断过滤控件类型。

**参数**:
- `col` {Object} - 列/字段定义 `{ type, widget, options, format }`

**返回**: `{string}` - 过滤控件类型

| 返回值 | 说明 |
|--------|------|
| `date-range` | 日期范围选择器 |
| `select` | 下拉选择器 |
| `number-range` | 数字范围输入 |
| `search` | 文本搜索框 |

**推断规则**:
1. `type=datetime|timestamp|date` → `date-range`
2. `options.length > 0` → `select`
3. `type=enum` → `select`
4. `widget=select|badge|tag|radio` → `select`
5. `type=integer|number|float|decimal` → `number-range`
6. 默认 → `search`

---

### 2.4 normalizeFilterType(filterType)

标准化过滤类型名称（兼容旧命名）。

**参数**:
- `filterType` {string}

**返回**: `{string}` - 标准化后的类型

**兼容映射**:
```javascript
{
  'date_range': 'date-range',
  'daterange': 'date-range',
  'number_range': 'number-range',
  'multi_select': 'multi-select',
  'text': 'search'
}
```

---

### 2.5 generateFiltersFromFields(fields, metaConfig)

从字段定义自动生成过滤字段配置。

**参数**:
- `fields` {Array} - YAML 字段定义数组
- `metaConfig` {Object} - 元数据配置 `{ field_display_names }`

**返回**: `{Array}` - FilterBar fields 配置数组

**示例**:
```javascript
const fields = [
  { id: 'name', type: 'string', filterable: true },
  { id: 'status', type: 'enum', filterable: true, options: [...] }
]
const filterFields = generateFiltersFromFields(fields)
// [{ field: 'name', type: 'search' }, { field: 'status', type: 'select', options: [...] }]
```

---

### 2.6 transformFilters(yamlFilters, metaConfig)

转换 YAML 过滤定义为 FilterBar 格式。

**参数**:
- `yamlFilters` {Array} - YAML filters 配置
- `metaConfig` {Object} - 元数据配置

**返回**: `{Array}` - FilterBar fields 配置

---

### 2.7 backfillColumnFilterType(columns, rawFilters)

回填列过滤器类型（支持 `value_help` 类型）。

**参数**:
- `columns` {Array} - 表格列配置
- `rawFilters` {Array} - 原始过滤字段配置

**返回**: `{Array}` - 补充后的列配置

**关键逻辑**:
```javascript
// 检测 value_help 类型
if (col.value_help || col.filter_config?.value_help) {
  col.filterType = 'value_help'
  col.valueHelpConfig = col.value_help || col.filter_config?.value_help
}
```

---

### 2.8 getDefaultFilterValues(filterFields)

获取过滤器默认值。

**参数**:
- `filterFields` {Array} - 过滤字段配置

**返回**: `{Object}` - `{ [field]: defaultValue }`

**示例**:
```javascript
const filterFields = [
  { field: 'status', type: 'select', options: [{ value: 'active', label: 'Active' }] }
]
const defaults = getDefaultFilterValues(filterFields)
// { status: 'active' }
```

---

### 2.9 addFilterParam(params, key, value, columns, filterFields, options)

添加过滤器参数到 params 对象。

**参数**:
- `params` {Object} - 查询参数对象（会被修改）
- `key` {string} - 过滤字段名
- `value` {any} - 过滤值
- `columns` {Array} - 表格列配置
- `filterFields` {Array} - 过滤字段配置
- `options` {Object} - 额外选项

**支持的过滤类型**:
- `search`: `filters[field] LIKE %value%`
- `select`: `filters[field] = value`
- `multi-select`: `filters[field] = value1,value2`
- `date-range`: `filters[field]_start`, `filters[field]_end`
- `number-range`: `filters[field]_min`, `filters[field]_max`

---

### 2.10 buildFilterQueryParams(options)

构建过滤器查询参数对象。

**参数**:
- `options` {Object}
  - `filterValues` {Object} - 过滤器值 `{ [field]: value }`
  - `columns` {Array} - 表格列配置
  - `filterFields` {Array} - 过滤字段配置
  - `extraParams` {Object} - 额外参数

**返回**: `{Object}` - 可直接用于 API 请求的参数对象

**示例**:
```javascript
const params = buildFilterQueryParams({
  filterValues: { name: 'test', status: 'active' },
  columns,
  filterFields
})
// { 'filters[name]': 'test', 'filters[status]': 'active' }
```

---

### 2.11 mergeFilters(...filterSources)

合并多个过滤器配置源。

**参数**:
- `filterSources` {...Array|Object} - 过滤器配置源

**返回**: `{Array}` - 合并后的过滤器配置

**合并规则**:
1. 后面的源覆盖前面的同字段配置
2. 数组合并，对象覆盖

---

## 3. 使用示例

### 3.1 基础使用

```javascript
import {
  inferFilterType,
  buildFilterQueryParams,
  getDefaultFilterValues
} from '@/services/filterService'

// 推断过滤类型
const filterType = inferFilterType({ type: 'datetime' })  // 'date-range'

// 构建查询参数
const params = buildFilterQueryParams({
  filterValues: { created_at: ['2026-05-01', '2026-05-19'] },
  columns: [{ prop: 'created_at', filterType: 'date-range' }],
  filterFields: [{ field: 'created_at', type: 'date-range' }]
})
// { 'filters[created_at]_start': '2026-05-01 00:00:00', 'filters[created_at]_end': '2026-05-19 23:59:59' }
```

### 3.2 在 useMetaList 中使用

```javascript
// useMetaList.js
import { buildFilterQueryParams, backfillColumnFilterType } from '@/services/filterService'

function _buildQueryParams() {
  return buildFilterQueryParams({
    filterValues: filterValuesRef.value,
    columns: columnsRef.value,
    filterFields: filterFieldsRef.value
  })
}
```

---

## 4. 测试覆盖

| 函数 | 测试数 | 覆盖场景 |
|------|--------|---------|
| isInternalProp | 2 | Vue 内部属性、业务属性 |
| formatDate | 4 | 字符串日期、Date 对象、开始/结束时间 |
| inferFilterType | 8 | datetime/enum/number/string/widget |
| normalizeFilterType | 4 | 旧命名兼容、未知类型 |
| generateFiltersFromFields | 4 | 空数组、可过滤字段、类型推断 |
| transformFilters | 3 | YAML 转换、display_name 映射 |
| backfillColumnFilterType | 4 | value_help 检测、filter_config 回填 |
| getDefaultFilterValues | 3 | select 默认值、空配置 |
| addFilterParam | 6 | search/select/date-range/number-range/multi-select |
| buildFilterQueryParams | 4 | 综合构建、额外参数 |
| mergeFilters | 3 | 数组合并、对象覆盖 |

**总计**: 50 tests

---

## 5. 与后端 filter_service.py 对应

| 前端函数 | 后端对应 | 说明 |
|---------|---------|------|
| inferFilterType | `_infer_filter_type()` | 类型推断逻辑一致 |
| buildFilterQueryParams | `build_filter_params()` | 参数构建格式一致 |
| formatDate | `format_date_range()` | 日期格式化一致 |
| mergeFilters | `merge_filter_configs()` | 合并逻辑一致 |

---

## 6. 扩展指南

### 添加新的过滤类型

1. 在 `inferFilterType()` 中添加类型检测逻辑
2. 在 `normalizeFilterType()` 中添加命名兼容
3. 在 `addFilterParam()` 中添加参数构建逻辑
4. 编写单元测试

### 示例：添加 `tree-select` 类型

```javascript
// inferFilterType
if (widget === 'tree-select' || col.hierarchy) {
  return 'tree-select'
}

// addFilterParam
if (filterType === 'tree-select') {
  params[`filters[${key}]`] = Array.isArray(value) ? value.join(',') : value
}
```
