# keyTemplateService

> **服务路径**: `src/services/keyTemplateService.js`
> **创建日期**: 2026-06-06
> **创建者**: AI Agent (Trae)
> **关联 PR**: PR 4 (FR-UI-004)
> **关联 spec**: [spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md) §5
> **测试覆盖**: 15 个单测 ([keyTemplateService.spec.js](file:///d:/filework/excel-to-diagram/src/services/__tests__/keyTemplateService.spec.js))

---

## 1. 服务目的

将 `useMetaList.js` 中关于"新建行时根据 parent_id 推导 code"的纯函数业务逻辑抽取到独立 service。

**业务场景**：用户在列表页面点击"新增"按钮时，系统自动根据当前列表的过滤值（如 `user_id`）和新行中的关联字段（如 `order_id`），调用后端 `boService.suggestKeyTemplateCode` 生成符合规则的 code。

## 2. 公开 API

### 2.1 `extractParentParams(filterValues, newRow, isVueInternalProp)`

**作用**：提取新建行的 parent_id 字段（用于键模板推导）

**业务规则**：
1. 从 `filterValues` 中提取 `*_id` 字段
2. 从 `newRow` 中提取 `*_id` 字段（**不覆盖** filterValues 中已存在的）
3. 跳过 Vue 内部 prop（`isVueInternalProp` 判断）
4. 跳过 `_` 开头的字段
5. 跳过 `id` 字段

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `filterValues` | `Object` | ✅ | 列表过滤值（响应式对象）|
| `newRow` | `Object` | ✅ | 新建行数据 |
| `isVueInternalProp` | `Function` | ✅ | Vue 内部 prop 判断函数 |

**返回**：`Object` parentParams

**示例**：

```javascript
import { extractParentParams } from '@/services/keyTemplateService'

const filterValues = { user_id: 1, status: 'active' }
const newRow = { order_id: 5, name: 'New Order' }
const result = extractParentParams(filterValues, newRow, key => key.startsWith('$'))
// → { user_id: 1, order_id: 5 }
```

### 2.2 `hasInvalidParentId(parentParams)`

**作用**：检查 parentParams 是否包含无效 parent_id

**业务规则**：parent record 未保存（值为 `'new'` / `''` / `null` / `undefined`）时返回 `true`

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `parentParams` | `Object` | ✅ | `extractParentParams` 的输出 |

**返回**：`boolean`

### 2.3 `applyKeyTemplateSuggestion(newRow, codeValue, draftValues)`

**作用**：应用建议的 code 到新建行 + draftValues

**注意**：直接修改 `newRow.code` 和 `newRow._initialValues.code` 字段

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `newRow` | `Object` | ✅ | 新建行（直接修改）|
| `codeValue` | `string` | ✅ | 建议的 code |
| `draftValues` | `Map` | ✅ | 草稿 Map（用于同步 rowDrafts.code）|

**返回**：`{ shouldUpdateDraft: boolean }` 是否需要触发响应式更新

### 2.4 `suggestKeyTemplateCode(newRow, filterValues, draftValues, boService, config, isVueInternalProp)`

**作用**：主入口 - 完整业务流程

**完整流程**：
1. 提取 `parentParams`
2. 检查 `parentParams` 是否为空（是 → 返回 `skipped: 'no_parent'`）
3. 检查是否包含无效 parent_id（是 → 返回 `skipped: 'invalid_parent'`）
4. 调用 `boService.suggestKeyTemplateCode`
5. 应用建议到 `newRow` + `draftValues`

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `newRow` | `Object` | ✅ | 新建行 |
| `filterValues` | `Object` | ✅ | 列表过滤值 |
| `draftValues` | `Map` | ✅ | 草稿 Map |
| `boService` | `Object` | ✅ | 注入式依赖（boService）|
| `config` | `Object` | ❌ | useMetaList 配置 `{debug: boolean}` |
| `isVueInternalProp` | `Function` | ❌ | Vue 内部 prop 判断函数 |

**返回**：

```typescript
Promise<{
  success: boolean,
  code?: string,                  // 建议的 code
  shouldUpdateDraft?: boolean,    // 是否需要触发响应式
  skipped?: 'no_parent' | 'invalid_parent' | 'no_code',
  error?: Error,
}>
```

## 3. 业务规则

### 3.1 键模板推导规则

```
parentParams = {}
  + filterValues 中所有 *_id 字段
  + newRow 中所有 *_id 字段（不覆盖 filterValues）

if parentParams 为空 → skipped
if parentParams 包含无效 parent_id → skipped
否则调用 boService.suggestKeyTemplateCode(objectType, {}, parentParams)
  → 成功后设置 newRow.code + newRow._initialValues.code
```

### 3.2 注入式依赖（设计原则）

- `boService` 通过参数注入（避免 service 直接依赖 composables）
- `config.debug` 控制日志输出
- `isVueInternalProp` 来自 useMetaList 内部（保持纯函数特性）

## 4. 单测矩阵（15 个用例）

| # | 用例 | 覆盖点 |
|:-:|------|------|
| TC-1 | extractParentParams 仅有 filterValues | 基础功能 |
| TC-2 | extractParentParams 仅有 newRow | 基础功能 |
| TC-3 | extractParentParams 合并 + 不覆盖 | 业务规则 |
| TC-4 | extractParentParams 跳过 Vue 内部 | 边界条件 |
| TC-5 | extractParentParams newRow 跳过 `_` 开头 | 边界条件 |
| TC-6 | extractParentParams 跳过 `id` 字段 | 边界条件 |
| TC-7 | hasInvalidParentId `'new'` | 业务规则 |
| TC-8 | hasInvalidParentId `''` | 业务规则 |
| TC-9 | hasInvalidParentId `null` | 业务规则 |
| TC-10 | hasInvalidParentId `undefined` | 业务规则 |
| TC-11 | hasInvalidParentId 正常数字 | 反向用例 |
| TC-12 | applyKeyTemplateSuggestion 有 drafts | shouldUpdateDraft=true |
| TC-13 | applyKeyTemplateSuggestion 无 drafts | shouldUpdateDraft=false |
| TC-14 | suggestKeyTemplateCode 完整成功流程 | 主入口 |
| TC-15 | suggestKeyTemplateCode 失败处理 | 错误处理 |

## 5. 调用方

### 5.1 useMetaList.js

```javascript
// src/composables/useMetaList.js L1931
import { suggestKeyTemplateCode as _suggestKeyTemplateCodeSvc } from '@/services/keyTemplateService'

async function _suggestKeyTemplateCode(newRow) {
  // 业务逻辑下沉到 keyTemplateService（PR 4）
  const result = await _suggestKeyTemplateCodeSvc(
    newRow,
    filterValues.value,
    draftValues.value,
    boService,
    config,
    isVueInternalProp
  )
  // 触发响应式更新（service 是纯函数，调用方负责）
  if (result.success && result.shouldUpdateDraft) {
    draftValues.value = new Map(draftValues.value)
  }
}
```

## 6. 设计决策

### 6.1 为什么是纯函数？

- **可测试性**：不需要 mock Vue 响应式
- **可复用性**：可在其他组件中直接使用
- **可维护性**：业务规则集中在一处

### 6.2 为什么 boService 注入式？

- 避免 service 直接 import composables（循环依赖）
- 测试时容易 mock
- 符合"composable 编排，service 实现"分层

### 6.3 为什么 shouldUpdateDraft 返回？

- service 不能触发响应式（保持纯函数）
- 响应式更新由调用方决定时机
- draftValues 实际是 Map（不是普通对象），需要 `new Map(...)` 触发响应式

## 7. 错误处理

| 场景 | 行为 |
|------|------|
| `filterValues` 为 null/undefined | 视为空对象 |
| `newRow` 为 null/undefined | 视为空对象 |
| `boService.suggestKeyTemplateCode` 抛异常 | 返回 `{success: false, error}` |
| `boService.suggestKeyTemplateCode` 返回 `success: false` | 返回 `{success: false, skipped: 'no_code'}` |
| `result.data?.code` 为空 | 返回 `{success: false, skipped: 'no_code'}` |
| objectType 缺失 | 返回 `{success: false, error: new Error('Missing objectType')}` |

## 8. 未来扩展

- [ ] 支持多字段 key template（不仅是 code）
- [ ] 支持自定义模板规则（不仅 *_id）
- [ ] 支持异步缓存建议结果

## 9. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-06 | 初稿；从 useMetaList.js L1931-1977 抽取 | AI Agent (Trae) |
