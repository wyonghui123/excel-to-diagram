---
title: display_values 全链路 与 useFieldPolicy 完整实现
version: 1.0.0
date: 2026-06-07
status: 活跃
parent: ARCHITECTURE_V2.md
audience: 开发者
---

# display_values 全链路 与 useFieldPolicy 完整实现

> 本文档是 ARCHITECTURE_V2.md v3.0.2 的扩展补充，详细记录 FR-6 7 个子项的完整实现。
>
> 适用读者：后端开发、前端开发、AI Agent（生产诊断）

## 目录

1. [背景与价值](#1-背景与价值)
2. [display_values 全链路](#2-display_values-全链路)
3. [useFieldPolicy 完整实现](#3-usefieldpolicy-完整实现)
4. [前后端联动矩阵](#4-前后端联动矩阵)
5. [API 完整参考](#5-api-完整参考)
6. [测试覆盖](#6-测试覆盖)
7. [风险缓解](#7-风险缓解)

---

## 1. 背景与价值

### 1.1 业务痛点

| 痛点 | 表现 | 影响 |
|------|------|------|
| **FK 字段不友好** | 列表显示"user_123"而不是"张三" | 用户体验差 |
| **枚举显示原始值** | 显示"active"而不是"活跃" | 国际化不友好 |
| **条件必填缺失** | 字段永远是必填或永远非必填 | 业务规则不灵活 |
| **字段可见性硬编码** | UI 写死显隐规则 | 修改需要改前端代码 |

### 1.2 解决方案

后端通过 `display_values` 注入友好文本；前端通过 `useFieldPolicy` 动态获取字段策略。两者结合，实现"零硬编码"的动态 UI。

### 1.3 价值

- **后端**：单一事实源（Single Source of Truth）原则，友好文本由后端返回
- **前端**：零硬编码，UI 组件根据策略动态渲染
- **可维护性**：修改后端一处，全局生效
- **AI Agent 友好**：可读可解析的字段策略

---

## 2. display_values 全链路

### 2.1 后端实现

**文件位置**：[meta/core/interceptors/query_interceptor.py:130-235](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py#L130-L235)

**核心方法**：

```python
def _inject_display_values(self, context, items):
    """为每条记录追加 display_values 字段"""
    if not items:
        return

    for item in items:
        display_values = {}

        # 1. FK 字段 → 显示名称（从关联表查）
        for fk_field in self._get_fk_fields(context.object_type):
            fk_id = item.get(fk_field)
            if fk_id:
                display_values[fk_field] = self._resolve_fk_display(
                    context.object_type, fk_field, fk_id
                )

        # 2. 枚举字段 → 标签
        for enum_field, enum_def in self._get_enum_fields(context.object_type).items():
            raw_value = item.get(enum_field)
            if raw_value in enum_def['values']:
                display_values[enum_field] = enum_def['values'][raw_value]

        # 3. 布尔字段 → "是"/"否"
        for bool_field in self._get_bool_fields(context.object_type):
            if bool_field in item:
                display_values[bool_field] = '是' if item[bool_field] else '否'

        # 4. 日期字段 → 格式化
        for date_field in self._get_date_fields(context.object_type):
            if item.get(date_field):
                display_values[date_field] = self._format_date(item[date_field])

        item['display_values'] = display_values
```

**支持的转换类型**：

| 类型 | 输入 | 输出 | 示例 |
|------|------|------|------|
| FK | `user_id: 123` | `user_id: "张三"` | 主从表关联 |
| 枚举 | `status: "active"` | `status: "活跃"` | 状态、类型 |
| 布尔 | `is_locked: true` | `is_locked: "是"` | 标志位 |
| 日期 | `created_at: "2026-06-07T10:00:00Z"` | `created_at: "2026-06-07"` | 时间格式 |

### 2.2 前端实现

#### 2.2.1 列表页 (useMetaList.js)

**文件位置**：[src/composables/useMetaList.js:1659-1661](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js#L1659-L1661)

```javascript
// getCellValue() 函数
function getCellValue(row, column) {
  const fieldName = column.prop || column.key

  // [NEW] v1.2 / FR-3.3: 优先读后端注入的 display_values
  if (row?.display_values?.[fieldName] !== undefined) {
    return row.display_values[fieldName]
  }

  // Fallback: 本地推断逻辑
  // - 枚举: 查找 options 找 label
  // - FK: 显示 value
  // - 布尔: 转换 "是"/"否"
  return defaultFormat(row[fieldName], column)
}
```

**使用场景**：
- MetaListPage 表格单元格显示
- 排序/过滤不影响（仍用原始 value）

#### 2.2.2 详情页 (ObjectPageField.vue)

**文件位置**：[src/components/common/ObjectPage/ObjectPageField.vue:159-160](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue#L159-L160)

```javascript
// getFieldDisplayValue() 函数
function getFieldDisplayValue(key) {
  // [DECORATIVE] [NEW] v1.3 / FR-6.5: 优先后端 display_values
  const dv = props.formData?.display_values?.[key]
  if (dv !== undefined && dv !== null) return dv

  // Fallback
  return props.formData?.[key] ?? '-'
}
```

**使用场景**：
- ObjectPage 只读字段显示
- 详情页"查看模式"

#### 2.2.3 详情备选 (DetailSection.vue)

**文件位置**：[src/components/common/DetailPage/DetailSection.vue:407-409](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailSection.vue#L407-L409)

```javascript
// getFieldDisplayValue() 函数
function getFieldDisplayValue(field) {
  // [DECORATIVE] [NEW] v1.3 / FR-6.6: 优先后端 display_values
  if (props.data?.display_values?.[field.id] !== undefined) {
    return props.data.display_values[field.id]
  }

  return props.data?.[field.id] ?? '-'
}
```

**使用场景**：
- DetailPage 兼容入口（DetailSection 内部使用）
- 旧版页面

#### 2.2.4 编辑表单 (MetaForm.vue) **🆕 v1.3 新增**

**文件位置**：[src/components/common/MetaForm.vue:286-301](file:///d:/filework/excel-to-diagram/src/components/common/MetaForm.vue#L286-L301)

```javascript
/**
 * [DECORATIVE] [NEW] v1.3: 获取增强的 options（支持 display_values）
 * 对于下拉选择字段，如果后端返回了 display_values，用它来增强 options 的 label
 */
function getOptionsWithDisplay(fieldKey, options) {
  if (!options || !Array.isArray(options)) return options
  const dv = displayValues[fieldKey]
  if (!dv) return options

  // 找到当前值对应的 option，用 display_values 增强 label
  return options.map(opt => {
    if (opt.value === formData[fieldKey] && dv !== opt.label) {
      return { ...opt, label: String(dv) }
    }
    return opt
  })
}
```

**模板使用**：

```vue
<AppSelect
  v-else-if="field.type === 'select' || (field.options && field.options.length > 0)"
  v-model="formData[field.key]"
  :options="getOptionsWithDisplay(field.key, field.options) || []"
  :placeholder="field.placeholder || `请选择${field.label}`"
/>
```

**使用场景**：
- 编辑表单下拉选择
- 显示当前值的友好文本

#### 2.2.5 initFormData 初始化

**文件位置**：[src/components/common/MetaForm.vue:186-209](file:///d:/filework/excel-to-diagram/src/components/common/MetaForm.vue#L186-L209)

```javascript
function initFormData(source) {
  Object.keys(formData).forEach(key => delete formData[key])
  Object.keys(previousFormData).forEach(key => delete previousFormData[key])
  Object.keys(displayValues).forEach(key => delete displayValues[key])  // [NEW] v1.3

  props.fields.forEach(f => {
    formData[f.key] = source?.[f.key] ?? f.defaultValue ?? ''
    previousFormData[f.key] = formData[f.key]
  })

  if (source) {
    Object.keys(source).forEach(key => {
      if (!(key in formData)) {
        formData[key] = source[key]
        previousFormData[key] = source[key]
      }
    })
    // [NEW] v1.3: 初始化 display_values
    if (source.display_values) {
      Object.entries(source.display_values).forEach(([key, displayValue]) => {
        displayValues[key] = displayValue
      })
    }
  }
}
```

### 2.3 完整覆盖矩阵

| 组件 | 文件 | display_values 使用 | 状态 |
|------|------|-------------------|:----:|
| **后端** | [query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py) | `_inject_display_values()` | ✅ |
| **useMetaList** | [useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js) | `getCellValue()` 优先读 | ✅ |
| **ObjectPageField** | [ObjectPageField.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue) | `getFieldDisplayValue()` | ✅ |
| **DetailSection** | [DetailSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailSection.vue) | `getFieldDisplayValue()` | ✅ |
| **MetaForm** | [MetaForm.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaForm.vue) | `getOptionsWithDisplay()` | ✅ v1.3 新增 |

---

## 3. useFieldPolicy 完整实现

### 3.1 文件位置

[src/composables/useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js)

### 3.2 暴露的 API（v1.3）

#### 3.2.1 Map 数据结构（5 个 computed）

```javascript
export function useFieldPolicy(metaConfig, columns) {
  return {
    // Map 数据结构（UI 可直接 v-if="requiredMap[key]"）
    requiredMap: computed,            // 条件必填
    editableMap: computed,            // 可编辑
    visibleMap: computed,             // 可见
    immutableMap: computed,           // 不可变（创建后）
    readonlyAlwaysMap: computed,      // 始终只读
    // ... 其他
  }
}
```

#### 3.2.2 函数 API

| 函数 | 签名 | 用途 |
|------|------|------|
| `isRequired(key)` | `(key) => boolean` | 单值判断（静态） |
| `isRequiredByRow(fieldId, row)` | `(fieldId, row) => boolean` | 条件必填（含 `conditional_required`） |
| `isEditable(key)` | `(key) => boolean` | 可编辑判断 |
| `isVisible(key)` | `(key) => boolean` | 可见判断 |
| `isImmutable(key)` | `(key) => boolean` | 不可变判断 |

#### 3.2.3 入口 API

| 函数 | 签名 | 用途 |
|------|------|------|
| `autoLoad(type, ctx, mut)` | `async (objectType, context, mutability) => boolean` | 主动加载入口 |
| `loadFieldPolicies(type, ctx)` | `async (objectType, context) => void` | 加载 API |
| `fieldPolicies` | `ref` | 原始策略对象 |
| `policiesLoaded` | `ref` | 加载状态 |

### 3.3 FR-6 7 个子项实现状态

| 子项 | 改动 | 状态 | 文件 |
|------|------|:----:|------|
| **6.1** 激活 field-policies | `autoLoad()` 入口 | ✅ | useFieldPolicy.js |
| **6.2** 暴露 Map 数据结构 | 5 个 computed | ✅ | useFieldPolicy.js |
| **6.3** isRequiredByRow 重载 | `conditional_required` 联动 | ✅ | useFieldPolicy.js |
| **6.4** 列表 cell 接入 | `getCellDisplayValue()` | ✅ | useMetaList.js |
| **6.5** 详情只读接入 | `getFieldDisplayValue()` | ✅ | ObjectPageField.vue |
| **6.6** 详情备选接入 | `getFieldDisplayValue()` | ✅ | DetailSection.vue |
| **6.7** 表单条件必填 | `validateField()` 集成 | ✅ | MetaForm.vue |

### 3.4 evaluateCondition 安全沙箱

```javascript
// MVP: 与后端 safe_evaluate 模式一致
function evaluateCondition(condition, row) {
  try {
    const fn = new Function('row', `with(row) { return (${condition}); }`)
    return Boolean(fn(row))
  } catch { return false }
}

// 生产环境: 替换为 JEXL 表达式库（更高安全性）
// import jexl from 'jexl'
// return jexl.evalSync(condition, row)
```

### 3.5 集成示例

#### 3.5.1 在表单中使用

```javascript
// MetaForm.vue
import { useFieldPolicy } from '@/composables/useFieldPolicy'

const fieldPolicy = useFieldPolicy(metaConfig, columns)

// 在 onMounted 中加载
onMounted(async () => {
  await fieldPolicy.autoLoad('user', 'edit', 'full')
})

// 条件必填验证
function validateField(key) {
  // ... 基础验证

  // [NEW] v1.3 / FR-6.7: 条件必填
  if (fieldPolicy.isRequiredByRow(key, formData)) {
    if (!formData[key]) {
      errors[key] = `${getFieldLabel(key)}为必填`
    }
  }
}
```

#### 3.5.2 在列表 cell 中使用

```javascript
// useMetaList.js / getCellDisplayValue()
function getCellDisplayValue(row, column) {
  // [NEW] v1.2 / FR-3.3 + FR-6.4: 优先读后端 display_values
  if (row?.display_values?.[column.prop] !== undefined) {
    return row.display_values[column.prop]
  }

  // Fallback: 本地推断
  return defaultFormat(row[column.prop], column)
}
```

---

## 4. 前后端联动矩阵

| 后端能力 | 前端实现 | 文件位置 |
|---------|---------|---------|
| **display_values** | 5 个组件已接入 | 见 §2.3 |
| **field-policies API** | `autoLoad()` 已调用 | useFieldPolicy.js |
| **requiredMap Map 结构** | 5 个 computed 已暴露 | useFieldPolicy.js |
| **conditional_required** | `isRequiredByRow()` 已实现 | useFieldPolicy.js |

---

## 5. API 完整参考

### 5.1 后端 API

#### 5.1.1 列表查询（带 display_values）

```http
GET /api/v2/bo/user?page=1&page_size=20
Cookie: auth_token=...

Response:
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "username": "zhangsan",
        "status": "active",
        "is_locked": false,
        "display_values": {
          "status": "活跃",
          "is_locked": "否"
        }
      }
    ],
    "total": 100
  }
}
```

#### 5.1.2 详情查询（带 display_values）

```http
GET /api/v2/bo/user/1
Cookie: auth_token=...

Response:
{
  "success": true,
  "data": {
    "id": 1,
    "username": "zhangsan",
    "display_values": {
      "username": "张三",
      "status": "活跃"
    }
  }
}
```

#### 5.1.3 字段策略查询

```http
GET /api/v1/field-policies/user?context=edit
Cookie: auth_token=...

Response:
{
  "success": true,
  "data": {
    "required": ["username", "email"],
    "conditional_required": {
      "phone": "row.role === 'admin'"
    },
    "editable": ["display_name", "email"],
    "immutable": ["username", "created_at"],
    "visible": ["*"]
  }
}
```

### 5.2 前端 Composable

#### 5.2.1 useFieldPolicy

```javascript
import { useFieldPolicy } from '@/composables/useFieldPolicy'

// 基础用法
const fieldPolicy = useFieldPolicy(metaConfig, columns)

// 主动加载
await fieldPolicy.autoLoad('user', 'edit', 'full')

// Map 数据结构访问
if (fieldPolicy.requiredMap.value['phone']) {
  // phone 字段是必填
}

// 函数调用
if (fieldPolicy.isRequired('email')) { /* ... */ }
if (fieldPolicy.isRequiredByRow('phone', formData)) { /* ... */ }
```

#### 5.2.2 useMetaList

```javascript
import { useMetaList } from '@/composables/useMetaList'

const {
  tableData,
  getCellValue,  // [NEW] v1.2 优先 display_values
  // ... 其他
} = useMetaList({ objectType: 'user' })
```

---

## 6. 测试覆盖

### 6.1 后端测试

| 测试文件 | 覆盖点 |
|---------|--------|
| `meta/tests/test_display_values_injection.py` | 后端注入逻辑 |
| `meta/tests/test_field_policies_api.py` | 字段策略 API |

### 6.2 前端测试

| 测试文件 | 覆盖点 |
|---------|--------|
| `tests/useFieldPolicy.test.js` | useFieldPolicy 7 个子项 |
| `tests/MetaForm.test.js` | 表单条件必填（FR-6.7） |
| `tests/MetaListPage.test.js` | 列表 cell 接入（FR-6.4） |

### 6.3 E2E 测试

| 测试文件 | 覆盖点 |
|---------|--------|
| `e2e/features/display-values.spec.js` | display_values 端到端 |

---

## 7. 风险缓解

### 7.1 性能风险

**风险**：display_values 注入需要额外的 FK 查询

**缓解**：
- 批量查询（`IN` 子句）
- 缓存层（Redis）
- 异步注入（不阻塞主查询）

### 7.2 安全风险

**风险**：evaluateCondition 沙箱可能被绕过

**缓解**：
- MVP 阶段使用 `new Function` + try/catch
- 生产环境替换为 JEXL 表达式库
- 限制 condition 长度
- 限制 condition 中的可用方法

### 7.3 兼容风险

**风险**：后端未返回 display_values 时前端报错

**缓解**：
- Fallback 模式：本地推断逻辑保留
- `display_values?.[key] !== undefined` 检查
- 渐进式升级（先部分字段，后全部）

### 7.4 一致性风险

**风险**：前后端字段命名不一致

**缓解**：
- YAML 元数据单一事实源
- 后端 `_inject_display_values()` 严格按 YAML 字段定义
- 自动化测试覆盖

---

## 附录 A：变更历史

| 版本 | 日期 | 维护人 | 变更 |
|------|------|--------|------|
| **1.0.0** | 2026-06-07 | AI Assistant | 初版（FR-6 全链路完成总结） |

## 附录 B：相关文档

- [ARCHITECTURE_V2.md §六](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md#六-前端架构详解) — 前端架构详解
- [architecture/06-frontend-architecture.md](file:///d:/filework/excel-to-diagram/docs/architecture/06-frontend-architecture.md) — 前端架构独立版本
- [useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js) — useFieldPolicy 源码
- [query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py) — 后端 display_values 注入
- [DOCUMENTATION_STANDARDS.md](file:///d:/filework/excel-to-diagram/docs/DOCUMENTATION_STANDARDS.md) — 文档编写规范
