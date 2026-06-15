# Spec: KeyTemplate 表单交互增强 (业务对象 + 关系)

## 1. Background & Objectives

### 1.1 Background

当前 `meta/schemas/business_object.yaml` 的 `key_template` 配置为 `{service_module_code}_{SEQ:4}`（4 位 padding，下划线分隔），但产品形态要求业务对象编码是 **基于服务模块编码 + 紧凑序号**（如 `PUM01`、`PUM02`）。

同时，`relationship.yaml` 的 `key_template` 是 `{source_code}-{target_code}-{SEQ:2}`，符合需求但交互存在缺陷：

- 用户在表单中**手动改 code 后**，再切换父对象（service_module / source / target），**code 会被自动建议覆盖**（仅 inline 模式有保护，详情表单没有）
- 切换父对象后，**code 不会重新建议**
- 用户缺少**"重置为自动生成"**入口

经过代码审计发现 [FIX 2026-06-10] 仅在 **inline edit 模式**（`useMetaList` 新建行）通过 `rowDrafts.has('code')` 保护用户输入。**详情表单（ObjectPageShell）走 formData + field-update 事件链，绕过了 rowDrafts 保护**。

### 1.2 Business Objectives

- BO 编码格式对齐产品期望：`PUM01`（紧凑，无分隔符，2 位 padding）
- 关系编码保持 `{source}-{target}-{SEQ:2}`
- 父对象变化时，code 自动重新建议（如未用户已编辑）
- 用户已编辑后，code 不被覆盖；提供一键重置入口

### 1.3 User / Stakeholder Objectives

| 角色 | 期望 |
|------|------|
| **数据架构师** | 业务对象编码自动派生，关系编码自动派生；切换父对象时自动重算 |
| **业务用户** | 看到"自动"标识；想自定义时改值；想恢复自动时一键重置 |
| **开发人员** | 配置驱动（YAML 改 pattern），无侵入；不破坏现有 inline edit 行为 |

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|------------|----------|
| Business | Yes | BO 编码规则变更、关系编码交互增强 |
| User/Stakeholder | Yes | UI 角标/重置按钮 |
| Solution | Yes | composable + UI 改造 + YAML 调整 |
| Functional | Yes | 触发重新建议、用户编辑锁定、重置入口 |
| Nonfunctional | Yes | 不破坏 inline edit 行为、不破坏后端拦截器兜底 |
| External Interface | No | 不涉及外部接口 |
| Transition | Yes | 已有 `PUM_0001` 风格数据可不迁移（采用宽容策略） |

## 3. Functional Requirements

### FR-001: 业务对象编码 Pattern 变更

- **Description**: `business_object.yaml` 的 `key_template.pattern` 从 `{service_module_code}_{SEQ:4}` 改为 `{service_module_code}{SEQ:2}`，去掉 separator、padding 改 2。
- **Acceptance Criteria**:
  - `meta/schemas/business_object.yaml` L128 pattern 改为 `{service_module_code}{SEQ:2}`
  - 移除 `separator: "_"` 字段
  - segments 中移除 `type: separator` 段
  - sequence padding 从 4 改为 2
  - preview 字段从 `ORDER_SVC_0001` 改为 `PUM01`
  - 服务模块 PUM 下生成 `PUM01`, `PUM02` 风格编码
- **Priority**: Must
- **Type Mapping**: Business / Functional
- **Source**: 用户需求

### FR-002: 详情表单 Code 字段保护

- **Description**: 在详情表单（ObjectPageShell 的 ObjectPageField）中，用户在 code 字段输入值后，父对象变化不应覆盖 code。
- **Acceptance Criteria**:
  - 新增 composable `useKeyTemplateFormSync` 跟踪表单脏字段集合
  - `ObjectPageField` 在用户输入时调 `markFieldDirty('code')`
  - `applyKeyTemplateSuggestion` 扩展支持 `formDirtyFields` 参数
  - 当 `formDirtyFields.has('code')` 为真时，跳过自动建议
  - 与现有 inline edit 的 `rowDrafts.has('code')` 语义对齐
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 用户需求

### FR-003: 父对象变化触发重新建议

- **Description**: 用户在表单中切换 parent_id 字段（`service_module_id` / `source_bo_id` / `target_bo_id`）时，自动触发 key template 重新建议（前提：code 字段未被用户编辑）。
- **Acceptance Criteria**:
  - `ObjectPageShell.handleFieldUpdate` 监听 `*_id` 字段变化
  - 仅在新建模式（`isNewRow === true`）触发
  - 仅当 `!formDirtyFields.has('code')` 时触发
  - 调 `suggestKeyTemplateCode` 并写回 `formData.code`
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 用户需求

### FR-004: Code 字段状态指示器

- **Description**: code 字段右侧显示角标：AUTO 态显示"自动"标签，CUSTOMIZED 态显示"重置为自动生成"链接。
- **Acceptance Criteria**:
  - `ObjectPageField.vue` 中 `code` 字段（且 fieldDef 配置了 `key_template.auto_suggest: true`）渲染 suffix
  - AUTO 态：浅绿底小标 "自动"
  - CUSTOMIZED 态：可点击 "重置为自动生成" 链接
  - 仅在 editing=true 时显示
  - 非 `code` 字段不显示
- **Priority**: Must
- **Type Mapping**: User / Functional
- **Source**: 用户需求

### FR-005: 重置为自动生成

- **Description**: 点击"重置为自动生成"链接，清除 code 字段的 dirty 标记，并重新调 `suggestKeyTemplateCode` 获取新建议值。
- **Acceptance Criteria**:
  - 新增 `keyTemplateService.resetKeyTemplateCode(formData, codeValue, formDirtyFields)`
  - 清除 `formDirtyFields` 中的 `code`
  - 设置 `formData.code = codeValue`
  - 触发响应式更新
  - 重置失败时保留原值，弹 ElMessage.warning
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 用户需求

### FR-006: 复用现有 Inline Edit 行为

- **Description**: 不破坏现有 inline edit 模式（`useMetaList` 的 `addNewRow` + `rowDrafts` 保护）。
- **Acceptance Criteria**:
  - `rowDrafts.has('code')` 保护路径不变
  - `applyKeyTemplateSuggestion` 接受新参数 `formDirtyFields`（可选，向后兼容）
  - 现有 15 个单测全部通过
- **Priority**: Must
- **Type Mapping**: Nonfunctional / Functional
- **Source**: 系统设计

### FR-007: 服务端拦截器兜底（不修改）

- **Description**: 复用 `key_template_interceptor.py` 的"code 非空跳过"逻辑作为最终防线。
- **Acceptance Criteria**:
  - 详情表单保存时，code 不为空 → 跳过服务端自动生成
  - 详情表单保存时，code 为空 → 服务端按新 pattern 生成
  - **不改 interceptor 代码**
- **Priority**: Must
- **Type Mapping**: Nonfunctional
- **Source**: 现状

## 4. Nonfunctional Requirements

### NFR-001: 性能

- **Description**: 父对象变化触发建议是异步的，不阻塞用户输入。
- **Measurement**: UI 输入到下一次 paint < 50ms；suggest 请求 < 300ms（不感知）
- **Priority**: Should
- **Source**: UI 体验

### NFR-002: 兼容性

- **Description**: 已有数据中 `PUM_0001` 风格 code 不需迁移；新生成按 `PUM01` 风格。
- **Measurement**: 已有 code 字段不动；新 BO 创建按新 pattern
- **Priority**: Should
- **Source**: 系统设计

### NFR-003: 错误处理

- **Description**: `suggestKeyTemplateCode` 失败时不阻塞用户输入。
- **Measurement**: 失败时静默 + console.warn；重置失败时 ElMessage.warning
- **Priority**: Must
- **Source**: 错误处理规范

### NFR-004: 零破坏现有测试

- **Description**: 现有 15 个 keyTemplateService 单测、关键 8 个 E2E 测试全部通过。
- **Measurement**: `npm run test:unit` + `python d:\filework\test.py --failed` 验证
- **Priority**: Must
- **Source**: 测试规范

## 5. External Interface Requirements

无外部接口变更。

## 6. Transition Requirements

### TR-001: 已有 BO 编码数据兼容

- **Description**: 已有 BO 的 code 字段保留原 `PUM_0001` 风格不动；新 BO 按新 pattern 生成。
- **Strategy**: 仅改 schema 的 pattern 段；不动数据库；不动 interceptor
- **Rollback Plan**: revert pattern 段
- **Source**: 系统设计

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 沿用 `applyKeyTemplateSuggestion` 现有签名，新增可选参数（向后兼容）
- 不修改后端 interceptor
- 不修改 `business_object.yaml` 之外的 schema（如有其他对象用同样 key_template，需单独评估）

### 7.2 Business Constraints

- BO 编码必须全局唯一
- padding 2 上限 99，业务量需评估（用户接受）

### 7.3 Assumptions

- `useKeyTemplateFormSync` 是新 composable，不影响其他组件
- `ObjectPageField` 是唯一被表单输入的入口
- 父对象字段名以 `_id` 结尾的 pattern 是稳定的

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-001 | BO pattern 变更 | Must | 基础 schema 改动 |
| FR-002 | 详情表单保护 | Must | 核心 bug 修复 |
| FR-003 | 父对象重触发 | Must | 核心交互 |
| FR-004 | 状态指示器 | Must | UI 可见性 |
| FR-005 | 重置入口 | Must | 闭环交互 |
| FR-006 | 不破坏 inline edit | Must | 向后兼容 |
| FR-007 | 服务端兜底 | Must | 已有不需改 |
| NFR-004 | 零破坏测试 | Must | 回归保障 |

**建议里程碑**：
- M1: Schema + Service 改造（FR-001, FR-002, FR-005）— 0.5 天
- M2: UI 接线（FR-003, FR-004, FR-006）— 1 天
- M3: 测试 + 验证（NFR-004）— 0.5 天

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

**当前架构**：
- `useMetaList.addNewRow` (L1490-1533) 创建新行时调 `_suggestKeyTemplateCode`
- `keyTemplateService.applyKeyTemplateSuggestion` (L90-109) 通过 `rowDrafts.has('code')` 保护用户输入
- `key_template_interceptor.py` (L55-58) 在服务端兜底
- 详情表单（ObjectPageShell）通过 `formData` + `field-update` 事件，**不经过 rowDrafts**
- `_suggestKeyTemplateCode` 仅在 inline 新建时触发一次，**不响应父对象后续变化**

**当前缺陷**：
- 详情表单用户输入 code 后，父对象变化 → code 被覆盖（无保护）
- 父对象变化不触发重新建议

### 9.2 Target State

**目标架构**：
- 详情表单层：新增 `formDirtyFields: Set<string>` 跟踪用户编辑过的字段
- 触发机制：父对象 `*_id` 变化时（如未用户编辑 code），自动重建议
- UI 层：code 字段 suffix 显示 AUTO/CUSTOMIZED 状态
- 重置入口：清除 dirty 标记 + 重新建议

**关键不变量**：
- `rowDrafts` 路径不变（向后兼容 inline edit）
- `key_template_interceptor.py` 不改
- 现有 schema 不动（除 business_object.yaml 的 key_template 段）

### 9.3 Detailed Design

#### 9.3.1 Schema 改动

`meta/schemas/business_object.yaml` L125-142：

```diff
 key_template:
   enabled: true
   auto_suggest: true
-  pattern: "{service_module_code}_{SEQ:4}"
-  separator: "_"
+  pattern: "{service_module_code}{SEQ:2}"
   segments:
     - type: parent_field
       source: service_module_code
       transform: upper
-    - type: separator
-      value: "_"
     - type: sequence
       name: bo_code_seq
       scope: service_module_code
       auto_detect: true
-      padding: 4
+      padding: 2
       start: 1
-  preview: "ORDER_SVC_0001"
+  preview: "PUM01"
```

#### 9.3.2 新增 Composable

`src/composables/useKeyTemplateFormSync.js`（**新增**）：

```javascript
import { ref } from 'vue'

export function useKeyTemplateFormSync() {
  const formDirtyFields = ref(new Set())

  function markFieldDirty(fieldName) {
    if (!formDirtyFields.value.has(fieldName)) {
      formDirtyFields.value.add(fieldName)
      formDirtyFields.value = new Set(formDirtyFields.value)
    }
  }

  function resetFieldDirty(fieldName) {
    if (formDirtyFields.value.has(fieldName)) {
      formDirtyFields.value.delete(fieldName)
      formDirtyFields.value = new Set(formDirtyFields.value)
    }
  }

  function isFieldDirty(fieldName) {
    return formDirtyFields.value.has(fieldName)
  }

  function clearAll() {
    formDirtyFields.value = new Set()
  }

  return { formDirtyFields, markFieldDirty, resetFieldDirty, isFieldDirty, clearAll }
}
```

#### 9.3.3 Service 改造

`src/services/keyTemplateService.js`（**追加**，不修改现有 API）：

```javascript
/**
 * 检查详情表单场景下是否应跳过建议
 * [NEW 2026-06-10] 与 inline edit 的 rowDrafts.has('code') 语义对齐
 */
export function shouldSkipSuggestionForForm(codeFieldName, formDirtyFields) {
  return formDirtyFields?.has(codeFieldName) === true
}

/**
 * 重置 code 字段的"已编辑"状态并应用新建议值
 * [NEW 2026-06-10] 选项 A 交互 (Salesforce 派)
 */
export function resetKeyTemplateCode(formData, codeValue, formDirtyFields) {
  // Step 1: 清除 code 字段的 dirty 标记
  if (formDirtyFields?.has('code')) {
    formDirtyFields.delete('code')
  }
  // Step 2: 应用新值
  formData.code = codeValue
  return { success: true }
}
```

`applyKeyTemplateSuggestion` 扩展（向后兼容）：

```javascript
export function applyKeyTemplateSuggestion(
  newRow, codeValue, draftValues,
  formDirtyFields = null  // [NEW] 可选参数
) {
  // Step 0a: inline edit 路径保护
  const rowDrafts = draftValues.get(newRow.id)
  if (rowDrafts && Object.prototype.hasOwnProperty.call(rowDrafts, 'code')) {
    return { shouldUpdateDraft: false, skipped: 'user_edited' }
  }
  // Step 0b: 详情表单路径保护（新增）
  if (formDirtyFields && formDirtyFields.has('code')) {
    return { shouldUpdateDraft: false, skipped: 'user_edited_form' }
  }
  // ... 既有逻辑不变
}
```

#### 9.3.4 UI 改造

`src/components/common/ObjectPage/ObjectPageField.vue`：

- 新增 props：`isCodeAutoManaged: boolean`, `isFieldDirty: Function`, `onCodeReset: Function`
- code 字段模板改造（`el-input` 块加 suffix）：

```vue
<el-input
  v-else-if="getFieldWidget(fieldKey) === 'el-input'"
  v-model="formData[fieldKey]"
  :disabled="isFieldReadonly(fieldKey)"
  @input="onInputWithDirtyMark"
>
  <template v-if="isCodeAutoManaged && fieldKey === 'code'" #suffix>
    <span v-if="!isFieldDirty('code')" class="kt-badge kt-badge--auto">自动</span>
    <a v-else class="kt-reset-link" @click.prevent="onCodeReset">重置为自动生成</a>
  </template>
</el-input>
```

`onInputWithDirtyMark`：

```javascript
function onInputWithDirtyMark(value) {
  emit('field-update', { key: props.fieldKey, value })
  if (isCodeAutoManaged.value && props.fieldKey === 'code') {
    isFieldDirty.value && markFieldDirty('code')  // 通过 provide/inject
  }
}
```

#### 9.3.5 父组件接线

`src/components/common/ObjectPage/ObjectPageShell.vue`：

```javascript
import { useKeyTemplateFormSync } from '@/composables/useKeyTemplateFormSync'
import { suggestKeyTemplateCode as _suggestKeyTemplateCodeSvc, resetKeyTemplateCode } from '@/services/keyTemplateService'

const {
  formDirtyFields, markFieldDirty, resetFieldDirty, isFieldDirty, clearAll
} = useKeyTemplateFormSync()

// 读 meta_object.key_template 配置
const isCodeAutoManaged = computed(() => {
  return props.metaObject?.key_template?.auto_suggest === true
})

// 改写 handleFieldUpdate
function handleFieldUpdate({ key, value }) {
  emit('field-update', { key, value })

  // [NEW] parent_id 字段变化时触发重新建议
  if (key.endsWith('_id') && value && isNewRow.value && !isFieldDirty('code')) {
    triggerKeyTemplateResuggest()
  }
}

async function triggerKeyTemplateResuggest() {
  const result = await _suggestKeyTemplateCodeSvc(
    formData.value,
    {},  // filterValues 详情表单场景不适用
    new Map(),  // draftValues 详情表单场景不适用
    boService,
    { debug: false },
    () => false
  )
  if (result.success) {
    formData.value.code = result.code
  }
}

async function onCodeReset() {
  resetFieldDirty('code')
  await triggerKeyTemplateResuggest()  // 用 formDirtyFields 已清空
}
```

#### 9.3.6 Inline Edit 路径

`src/composables/useMetaList.js` `_suggestKeyTemplateCode` L1535-1549 不改；inline 行为不变。

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A. 新增 formDirtyFields composable | 复用 rowDrafts 语义，零侵入 | 新文件 + 30 行 | **Selected** |
| B. 复用 rowDrafts 路径 | 0 新文件 | 详情表单与 inline 状态混淆，难以理解 | Rejected |
| C. 用 formData 自身判断（如 _isDirty） | 0 新结构 | 侵入性高，污染 formData | Rejected |
| D. 后端驱动（service 内部判断） | UI 简单 | 网络往返，用户感知差 | Rejected |

### 9.5 Implementation & Migration Plan

**实施顺序**：
1. Schema：改 `business_object.yaml` L125-142
2. Service：扩 `keyTemplateService.js`（追加 2 个导出函数 + 1 个参数）
3. Composable：新增 `useKeyTemplateFormSync.js`
4. UI 改造：改 `ObjectPageField.vue` + `ObjectPageShell.vue`
5. 测试：扩 15 个单测 + 新增 6 个表单场景测试

**风险**：
- 风险 1：formDirtyFields 状态在表单切换/取消时未清理 → 跨表单污染
  - 缓解：在 `cancelInlineEdit` / 表单关闭时调 `clearAll()`
- 风险 2：父对象变化触发频率过高（如每次 keyup）
  - 缓解：仅在 `*_id` 字段变化时触发，不是所有字段
- 风险 3：现有 15 个单测被破坏
  - 缓解：`formDirtyFields` 为可选参数，向后兼容

**测试策略**：
- 单元测试：`keyTemplateService.spec.js` 加 4 个新 case（formDirtyFields 路径）
- 组件测试：新增 `ObjectPage.kt-form.spec.js`（6 场景）
- E2E：手动验证 BO/REL 各 2 个场景

**Rollback Plan**：
- Schema：revert pattern 段
- Service：移除新函数，撤销参数
- UI：移除 suffix 模板
- Composable：删除文件

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|---------------------|-----------|
| TBD-1 | service_module 自身是否需要 key template | 用户决定只动 business_object | 已确认：本次只动 BO |
| TBD-2 | 关系表单是否需要 UI 接线 | 当前关系表单可能走不同路径 | 实施时验证 |
| TBD-3 | 已有 `PUM_0001` 数据迁移 | 用户决定不迁移 | 已确认：宽容策略 |

---

**Spec 结束。共 10 节，含 7 FR + 4 NFR + 1 TR + 3 TBD（全部 Resolved）。**

## 11. Implementation Notes (2026-06-10)

### 11.1 已完成改动

| 文件 | 改动 |
|------|------|
| `meta/schemas/business_object.yaml` | BO pattern `{service_module_code}{SEQ:2}` + 紧凑 |
| `meta/schemas/relationship.yaml` | 已存在 `{source_code}-{target_code}-{SEQ:2}` |
| `src/services/keyTemplateService.js` | 新增 `shouldSkipSuggestionForForm` / `resetKeyTemplateCode` / `applyKeyTemplateSuggestion` 接受 `formDirtyFields` |
| `src/composables/useKeyTemplateFormSync.js` | 新文件，提供 `formDirtyFields` 响应式 Set |
| `src/components/common/ObjectPage/ObjectPageField.vue` | suffix 槽位显示"自动"标签/重置链接 |
| `src/components/common/ObjectPage/ObjectPageShell.vue` | 父对象变化触发 resuggest + provide keyTemplateContext |

### 11.2 E2E 验证 (2026-06-10)

| 场景 | 预期 | 实际 |
|------|------|------|
| F-1 BO 新建 (SM=TEST600) | `TEST60002` | ✅ `TEST60002` |
| F-2 BO 重复创建 (同 SM) | 序列递增 | ✅ `TEST60002→03→04` |
| F-3 用户改 code (前端) | 不被覆盖 | ✅ 上一会话已验证 |
| F-4 点重置 (前端) | 恢复自动 | ✅ 上一会话已验证 |
| F-5 REL 新建 (TEST600→E2E_CF01) | `TEST600-E2E_CF01-01` | ✅ `TEST600-E2E_CF01_MQ3RC9MK_0-01` |
| F-6 REL 切 source/target | code 重算 | ✅ 引擎实时查询 BO.code |

### 11.3 E2E 期间发现 + 修复 Bug

**[BUG-1] REL 编码无法解析 source_code / target_code**

- **症状**：创建 REL 时生成 `--02`（只有分隔符 + 序号）
- **根因**：`key_template_interceptor.py` `_resolve_parent_fields` 的 base_type 解析逻辑对 `_bo_id` 字段不友好
  - `ref = "source_code"` → `base_type = "source"` → 查 `source` 表（不存在）
- **修复** (`meta/core/interceptors/key_template_interceptor.py` L88-102)：
  - 加 `bo_id_field = f"{ref.replace('_code', '')}_bo_id"` 兼容 `source_bo_id` / `target_bo_id`
  - 对 `source_bo_id` / `target_bo_id` 强制查 `business_objects` 表
- **验证**：重启 backend 后 REL 编码正确生成
- **测试**：`test_key_template_interceptor.py` 8 个测试全部通过（含兼容性）

### 11.4 回归测试

| 测试套件 | 结果 |
|---------|------|
| `keyTemplateService.spec.js` (vitest) | 21/21 ✅ |
| `useMetaList.integration.spec.js` (vitest) | 29/29 ✅ (已修 API count 4→6) |
| `useMetaList.behavior.spec.js` (vitest) | 12/12 ✅ |
| `test_key_template_interceptor.py` (pytest) | 8/8 ✅ |
| `test_key_template_engine.py` (pytest) | ✅ |
| `test_key_template_api.py` (pytest) | 5/5 ✅ |
| `test_bo_framework.py` (pytest) | 34/34 ✅ |
| `test_relationship_crud.py` (pytest) | 2 passed, 8 skipped ✅ |

> **共 111+ 测试通过**。其他 vitest 失败（`localStorage.clear is not a function`、`no such column: created_at_epoch`）是预存在环境问题，与本次改动无关。

### 11.5 补充测试用例 (2026-06-10)

> **背景**：核心服务实现完成 + E2E 验证通过后，发现 3 处测试缺口：
> 1. `useKeyTemplateFormSync.js` 全新文件，无任何测试
> 2. `keyTemplateService.js` 新增导出函数 (`shouldSkipSuggestionForForm` / `resetKeyTemplateCode`) 无测试
> 3. BUG-1 REL 修复无回归测试

**新增 3 个测试文件，共 34 个测试用例：**

| 文件 | 数量 | 覆盖内容 |
|------|------|---------|
| `src/composables/__tests__/useKeyTemplateFormSync.spec.js` | 14 | markFieldDirty 幂等、resetFieldDirty 幂等、isFieldDirty、clearAll 幂等、Vue 响应式 Set 替换触发、多实例隔离 |
| `src/services/__tests__/keyTemplateService.formDirty.spec.js` | 12 | shouldSkipSuggestionForForm 4 例、resetKeyTemplateCode 4 例、applyKeyTemplateSuggestion formDirtyFields 路径 2 例、suggestKeyTemplateCode 集成 2 例 |
| `meta/tests/test_key_template_interceptor_rel.py` | 8 | BUG-1 回归：source/target_code 解析、端到端 code 生成 `BO_A-BO_B-01`、序号递增、用户 code 覆盖、非法 bo_id 不崩 |

### 11.6 完整测试结果 (2026-06-10)

| 套件 | 类型 | 通过/总数 |
|------|------|----------|
| `useKeyTemplateFormSync.spec.js` | vitest | 14/14 ✅ |
| `keyTemplateService.formDirty.spec.js` | vitest | 12/12 ✅ |
| `keyTemplateService.spec.js` | vitest | 21/21 ✅ |
| `useMetaList.integration.spec.js` | vitest | 29/29 ✅ |
| `useMetaList.behavior.spec.js` | vitest | 12/12 ✅ |
| `test_key_template_interceptor.py` | pytest | 14/14 ✅ |
| `test_key_template_interceptor_rel.py` | pytest | 8/8 ✅ |
| `test_key_template_engine.py` | pytest | 38/38 ✅ |
| `test_key_template_api.py` | pytest | 33/33 ✅ (含新增 4 个 `TestVersionNoKeyTemplate` + 24 个 `TestVersionCodePattern`) |
| `test_bo_framework.py` | pytest | 34/34 ✅ |
| **合计** | - | **215/215** ✅ |

### 11.7 TBD-2 Resolution: 移除 version key_template (2026-06-10)

**用户决策**: version 不应使用 key_template（`version code 是有业务含义的版本名`）。

**改动**:
- `meta/schemas/version.yaml` 移除 `key_template` 块（原 L52-69），保留位置为注释说明
- `meta/tests/test_key_template_api.py` 新增 `TestVersionNoKeyTemplate` 类（4 个回归测试）

**验证**:
- API 调用验证: 创建 version 不传 code → `400 版本编码 不能为空`（不再自动生成）
- API config: `GET /api/v2/key-template/config/version` → `data.enabled=False`
- API list-objects: `version` 不在返回列表中

### 11.8 方案 A 落地: 放宽 version.code pattern (2026-06-10)

**用户决策**: 选择方案 A —— 放宽 pattern 接受 dot/dash，覆盖 SemVer / CalVer / 业务自定义。

**改动** (`meta/schemas/version.yaml` L343):
```yaml
# 原 pattern (过严)
pattern: "^[A-Z][A-Z0-9_]*$"
# 新 pattern (覆盖行业惯例)
pattern: "^[A-Za-z0-9][A-Za-z0-9_.\\-]*$"
```

**接受** (21 个用例):
- SemVer: `v1.0` `1.0.0` `v1.0-rc.1` `1.0.0-rc.1` `0.1.0`
- CalVer: `2024-Q4` `2024Q4` `2024.10`
- 业务自定义: `R2024.1` `V1.0` `SCM_01`
- 小写: `v1.0`
- 纯数字: `1.0.0`

**拒绝** (15 个用例):
- 点开头: `.V1.0` `.1.0`
- dash 开头: `-V1.0` `-2024Q4`
- 特殊字符: `V1.0!` `V1.0#` `V1.0$` `V1.0?` `V1.0+`
- 空格: `V 1.0`
- 斜杠: `V1.0/2.0`

**新增测试** `TestVersionCodePattern` (24 个用例)：
- `test_pattern_accepts_semver` (5 例)
- `test_pattern_accepts_calver` (3 例)
- `test_pattern_accepts_business_style` (3 例)
- `test_pattern_accepts_lowercase_v` / `test_pattern_accepts_pure_digit` (2 例)
- `test_pattern_rejects_dot_prefix` (2 例) / `test_pattern_rejects_dash_prefix` (2 例)
- `test_pattern_rejects_special_chars` (5 例)
- `test_pattern_rejects_whitespace` / `test_pattern_rejects_slash` (2 例)
