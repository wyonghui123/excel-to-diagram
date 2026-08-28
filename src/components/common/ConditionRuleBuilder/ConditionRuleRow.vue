<!--
  ConditionRuleRow.vue
  单行规则: [connector] [field] [operator] [value]

  [v26 2026-08-26] 抽取自 ConditionRuleDialog.vue

  设计原则:
    - 字段未选时禁用 operator + 值控件（渐进式披露）
    - 值控件按 field_type 派发到 5 个分支:
      1. FK / business key / enum → SearchHelpDialog picker
      2. datetime → ElDatePicker
      3. integer/float → ElInputNumber
      4. boolean → AppSelect
      5. 兜底 → input
    - 字段切换时: 重置 operator + value + picker 缓存（v23 修复）

  Props:
    rule           当前 rule 节点（v-model 直接修改）
    fieldOptions   字段下拉选项 (AppSelect format)
    fieldMetadata  完整字段元数据 (用于 onFieldChange 查 fieldType)
    resourceType   当前资源类型 (picker 显示用)
    pickerCtx      { form } — 业务主键 self-reference
    ruleValueFetcher (rule, ctx, params) => Promise
    isFirst        是否首行（首行不显示 connector）
    canDelete      是否可删除
    disabled       整体禁用

  Emits:
    update:rule    patch 对象 — 父组件合并到 rule
    change         任意修改后触发 (用于同步父组件 serializedText)
    remove         删除本行
-->
<template>
  <div class="rule-row" :class="{ 'rule-row--subgroup': groupType === 'subgroup' }">
    <!-- connector 列: 首行占位空, 非首行显示且/或 segmented (chip 在 RuleBuilderGroup tag-row) -->
    <div
      class="rule-connector"
      :class="{ 'rule-connector--first': isConnectorEmpty }"
    >
      <!-- 且/或 segmented（首行空时不显示） -->
      <div v-if="!isConnectorEmpty" class="rule-connector-seg">
        <button
          type="button"
          class="rule-connector-seg-btn"
          :class="{ 'is-active': rule.connector === 'AND' }"
          :disabled="disabled"
          @click="patch({ connector: 'AND' })"
        >且</button>
        <button
          type="button"
          class="rule-connector-seg-btn"
          :class="{ 'is-active': rule.connector === 'OR' }"
          :disabled="disabled"
          @click="patch({ connector: 'OR' })"
        >或</button>
      </div>
    </div>

    <!-- 字段下拉 -->
    <AppSelect
      :model-value="rule.field"
      :options="fieldOptions"
      placeholder="选择字段"
      size="small"
      class="rule-field"
      :disabled="disabled"
      @update:model-value="onFieldChange"
    />

    <!-- 操作符下拉 -->
    <AppSelect
      :model-value="rule.operator"
      :options="operatorOptions"
      :placeholder="rule.field ? '操作符' : '请先选择字段'"
      :disabled="!rule.field || disabled"
      size="small"
      class="rule-operator"
      @update:model-value="(val) => patch({ operator: val })"
    />

    <!-- 值输入 -->
    <div class="rule-value-wrapper">
      <!-- 1. FK / 业务主键 / enum → SearchHelpDialog picker -->
      <template v-if="usePicker">
        <!-- [v50 2026-08-27] 对齐头部产品方案（Element Plus 多选下拉 / Salesforce·Datadog 筛选器）：
             已选 tag 内嵌在输入框内部（此前 v49 挂在框外，不符合直觉）
             - 点框体空白区 → 打开 picker
             - tag 上 × → 原地移除单项；多于 1 项时末尾出现「清空」
             - 外层用 div[role=button]：button 不能嵌套 button（tag × 是真按钮） -->
        <div
          class="rule-value-picker-trigger"
          :class="{
            'rule-value-picker-trigger--empty': !rule.value,
            'rule-value-picker-trigger--disabled': !rule.field || disabled
          }"
          :aria-disabled="!rule.field || disabled"
          role="button"
          tabindex="0"
          @click="openPicker"
          @keydown.enter.prevent="openPicker"
        >
          <AppIcon name="filter-alt" :size="11" class="rule-value-picker-glyph" />
          <!-- 有已选值且可编辑：内嵌 tag 列表（带逐项 × / 清空） -->
          <div v-if="pickTags.length > 0 && !disabled" class="rule-value-tags">
            <span
              v-for="tag in pickTags"
              :key="String(tag.id)"
              class="rule-value-tag"
              :title="tag.label"
            >
              <span class="rule-value-tag-text">{{ tag.label }}</span>
              <button
                type="button"
                class="rule-value-tag-remove"
                title="移除该项"
                @click.stop="removePickItem(tag.id)"
              >
                <AppIcon name="close" :size="9" />
              </button>
            </span>
            <button
              v-if="pickTags.length > 1"
              type="button"
              class="rule-value-tags-clear"
              title="清空全部已选值"
              @click.stop="clearPickItems"
            >清空</button>
          </div>
          <!-- 空态占位 / 只读态纯文本摘要 -->
          <template v-else>
            <span v-if="rule.value" class="rule-value-picker-text">{{ formattedValue }}</span>
            <span v-else class="rule-value-picker-placeholder">{{ pickerPlaceholder }}</span>
          </template>
          <AppIcon name="edit" :size="10" class="rule-value-picker-edit" />
        </div>
        <SearchHelpDialog
          v-model:visible="pickerVisibleLocal"
          :value-help-config="valueHelpConfig"
          :multiple="isMultiPicker"
          :selected-value="parseRuleValueIds(rule)"
          :custom-fetcher="(params) => ruleValueFetcher(rule, pickerCtx, params)"
          @confirm="(selection) => onPickerConfirm(selection)"
        />
      </template>

      <!-- 2. datetime → ElDatePicker -->
      <ElDatePicker
        v-else-if="isDate && !isInMulti"
        :model-value="rule.value || null"
        type="datetime"
        :placeholder="rule.field ? '选择日期时间' : '请先选择字段'"
        :disabled="!rule.field || disabled"
        format="YYYY-MM-DD HH:mm:ss"
        value-format="YYYY-MM-DD HH:mm:ss"
        size="small"
        class="rule-value-datetime"
        @update:model-value="(val) => patch({ value: val || '' })"
      />

      <!-- 3. number → ElInputNumber -->
      <ElInputNumber
        v-else-if="isNumber"
        :model-value="rule.value === '' || rule.value == null ? null : Number(rule.value)"
        :placeholder="rule.field ? getRuleValuePlaceholder(rule) : '请先选择字段'"
        :disabled="!rule.field || disabled"
        :controls="false"
        size="small"
        class="rule-value-number"
        @update:model-value="(val) => patch({ value: val == null ? '' : String(val) })"
      />

      <!-- 4. boolean → AppSelect -->
      <AppSelect
        v-else-if="isBoolean"
        :model-value="rule.value"
        :options="BOOLEAN_VALUE_OPTIONS"
        :placeholder="rule.field ? '选择布尔值' : '请先选择字段'"
        :disabled="!rule.field || disabled"
        size="small"
        class="rule-value-boolean"
        @update:model-value="(val) => patch({ value: val })"
      />

      <!-- 5. 兜底 input -->
      <input
        v-else
        :value="rule.value"
        :placeholder="rule.field ? getRuleValuePlaceholder(rule) : '请先选择字段'"
        :disabled="!rule.field || disabled"
        class="rule-value-input"
        @input="(e) => patch({ value: e.target.value })"
      />
    </div>

    <!-- 删除行 -->
    <button
      type="button"
      class="rule-remove"
      :disabled="disabled || !canDelete"
      :title="canDelete ? '删除此规则' : '至少保留一行'"
      @click="$emit('remove')"
    >
      <AppIcon name="close" :size="12" />
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElDatePicker, ElInputNumber } from 'element-plus'
import { AppSelect } from '@/components/common/AppSelect'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import SearchHelpDialog from '@/components/common/SearchHelpDialog.vue'
import {
  getOperatorOptions,
  getRuleValuePlaceholder,
  BOOLEAN_VALUE_OPTIONS,
  isBooleanFieldType,
  isDateFieldType,
  isNumberFieldType,
} from './operators.ts'
import { initRuleForField } from './rule-init.ts'
import {
  getRuleValueHelpConfig,
  handleRulePickerConfirm,
  parseRuleValueIds,
  formatRuleValue,
} from './rule-helpers.ts'

const props = defineProps({
  rule: { type: Object, required: true },
  fieldOptions: { type: Array, default: () => [] },
  fieldMetadata: { type: Array, default: () => [] },
  resourceType: { type: String, default: '' },
  pickerCtx: { type: Object, default: () => ({}) },
  ruleValueFetcher: { type: Function, required: true },
  isFirst: { type: Boolean, default: false },
  canDelete: { type: Boolean, default: true },
  // [v30] 子组支持
  groupType: { type: String, default: 'top' }, // 'top' | 'subgroup'
  canRemoveGroup: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:rule', 'change', 'remove', 'removeGroup'])

// [v30 fix5] connector 列是否为空（占位）
//   - 首行 (无论顶层/子组): true（占位, 保留列宽对齐）
//   - 非首行: false (显示且/或 segmented)
// 子组 connector 改由 RuleBuilderGroup tag-row 承担, 这里只关心 per-row connector
const isConnectorEmpty = computed(() => props.isFirst)

const operatorOptions = computed(() => getOperatorOptions(props.rule.fieldType))
const isDate = computed(() => isDateFieldType(props.rule.fieldType))
const isNumber = computed(() => isNumberFieldType(props.rule.fieldType))
const isBoolean = computed(() => isBooleanFieldType(props.rule.fieldType))
const isInMulti = computed(() => ['IN', 'NOT IN'].includes(props.rule.operator))

// picker: FK / 业务主键 / enum
const usePicker = computed(() => {
  const r = props.rule
  return r.relationObject || r.isBusinessKey || r.isEnum || (r.enumValues && r.enumValues.length > 0) || r.enumRef
})
const isMultiPicker = computed(() => ['IN', 'NOT IN', 'LIKE', 'NOT LIKE'].includes(props.rule.operator))

// picker 显隐状态用本地 ref 维护（避免直接 mutation prop 的 lint 警告）
// 打开时同步给父组件规则数据（用于显示），关闭时同样同步
const pickerVisibleLocal = computed({
  get: () => !!props.rule.pickerVisible,
  set: (v) => emit('update:rule', { pickerVisible: v }),
})

const pickerPlaceholder = computed(() => {
  if (!props.rule.field) return '请先选择字段'
  const r = props.rule
  if (r.isBusinessKey) return `选择${props.resourceType || '记录'}...`
  if (r.isEnum) return `选择${r.enumRef || '枚举值'}...`
  return `选择${r.relationObject}...`
})

const valueHelpConfig = computed(() => getRuleValueHelpConfig(props.rule, props.pickerCtx))

const formattedValue = computed(() => formatRuleValue(props.rule))

function openPicker() {
  if (!props.rule.field || props.disabled) return
  patch({ pickerVisible: true })
}

function onPickerConfirm(selection) {
  // picker 状态写入 rule（rule 是 reactive 对象，直接修改即可）
  handleRulePickerConfirm(props.rule, selection)
  emit('change')  // 通知父组件同步序列化
}

// [v49 2026-08-27] 已选值 tag 数据源：优先 pickerSelectedItems（有显示名），
//   兜底 value 字符串解析为 ID（刷新后回填无缓存的场景）
const pickTags = computed(() => {
  const r = props.rule
  if (Array.isArray(r.pickerSelectedItems) && r.pickerSelectedItems.length > 0) {
    return r.pickerSelectedItems.map((i) => ({ id: i.id, label: i.name || i.code || String(i.id) }))
  }
  if (!r.value) return []
  return parseRuleValueIds(r).map((id) => ({ id, label: String(id) }))
})

// [v49] tag × 移除单项 — 同步裁剪 picker 缓存与 value 序列化串
function removePickItem(id) {
  if (props.disabled) return
  const r = props.rule
  const remaining = parseRuleValueIds(r).filter((v) => String(v) !== String(id))
  r.value = remaining.join(',')
  r.pickerSelectedIds = remaining.slice()
  r.pickerSelectedItems = (r.pickerSelectedItems || []).filter(
    (i) => String(i.id) !== String(id)
  )
  emit('change')
}

// [v49] 一键清空全部已选值
function clearPickItems() {
  if (props.disabled) return
  const r = props.rule
  r.value = ''
  r.pickerSelectedIds = []
  r.pickerSelectedItems = []
  emit('change')
}

// 字段变化时重置 operator + value + picker 缓存 (v23 修复 + v28 重构)
function onFieldChange(field) {
  const meta = props.fieldMetadata.find((f) => f.db_column === field)
  // v28: 委托给 initRuleForField 纯函数, 与父组件预填路径共享同一逻辑
  emit('update:rule', initRuleForField(props.rule, meta || null))
  emit('change')
}

function patch(p) {
  emit('update:rule', p)
  emit('change')
}
</script>

<style scoped>
.rule-row {
  display: grid;
  /* [v30 fix4] 列布局: 顶层/子组 connector 列统一 70px (chip 移到独立行)
   *   - 顶层: 70px (空 chip 槽) / field / operator / value / 24px (×)
   *   - 子组: 同上, 子组 chip 由 RuleBuilderGroup 的独立行承载
   */
  grid-template-columns: 70px minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1.4fr) 24px;
  gap: 6px;
  align-items: center;
  padding: 4px 0;
  min-width: 0;
  /* 撑满父容器: 父级 .rule-builder-row-wrapper 是 display:flex + align-items:center,
   *   flex item 默认 shrink-to-fit(宽度由内容决定) → 首行(短文本)比后续行窄, fr 列错位。
   *   width:100% 让所有行等宽, field/operator/value 三列跨行对齐。 */
  width: 100%;
}

.rule-connector {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  flex-shrink: 0;
  /* [v30 fix4] 子组 chip 由 RuleBuilderGroup 的 tag-row 独立行承载,
   *   本行 connector 只负责且/或 segmented */
}
.rule-connector--first {
  /* 首行无连接符，仅占位（仅顶层首行用） */
  visibility: hidden;
}

/* [v29 fix3] 自定义 segmented button — 绕开 ElRadioButton slot bug */
.rule-connector-seg {
  display: inline-flex;
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: var(--radius-sm, 4px);
  overflow: hidden;
  background: var(--color-bg-container, #fff);
  height: 24px;
}
.rule-connector-seg.is-disabled {
  opacity: 0.5;
}
.rule-connector-seg-btn {
  border: 0;
  background: transparent;
  padding: 0 10px;
  font-size: 12px;
  line-height: 22px;
  cursor: pointer;
  color: var(--color-text-regular, #333);
  transition: background 0.15s, color 0.15s;
  min-width: 28px;
  white-space: nowrap;
}
.rule-connector-seg-btn:not(:last-child) {
  border-right: 1px solid var(--color-border, #d9d9d9);
}
.rule-connector-seg-btn:hover:not(.is-active):not(:disabled) {
  background: var(--color-bg-tertiary, #fafafa);
}
.rule-connector-seg-btn.is-active {
  background: var(--color-primary, #ea580c);
  color: #fff;
}
.rule-connector-seg-btn:disabled {
  cursor: not-allowed;
}

.rule-field,
.rule-operator,
.rule-value-wrapper,
.rule-value-boolean,
.rule-value-datetime,
.rule-value-number {
  width: 100%;
  min-width: 0;
}

/* [v29 fix4] 强制 ElSelect 占满父容器 (ElSelect 默认 inline-block 不会自动 100%) */
.rule-field :deep(.el-select),
.rule-operator :deep(.el-select),
.rule-value-boolean :deep(.el-select),
.rule-value-boolean :deep(.app-select),
.rule-value-number :deep(.el-input-number) {
  width: 100%;
  min-width: 0;
  display: block;
}

/* EP wrapper 占满列宽 (ElSelect 是 inline-block, 不自动 100%)。
   min-width:0 允许内部收缩; box-sizing:border-box 防 padding 撑出。
   注: 行宽最终由 .rule-row{width:100%} 统一, 此规则让 select 填满 grid 列 */
.rule-field :deep(.el-select__wrapper),
.rule-operator :deep(.el-select__wrapper),
.rule-value-boolean :deep(.el-select__wrapper) {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

/* 选中 label 承载在 .el-select__placeholder 元素内 (EP 单选中复用 placeholder 元素),
   min-width:0 允许收缩, 不要给它设 width/flex (flex 无效且 width 会把 label 裁成 0) */
.rule-field :deep(.el-select__selected-item),
.rule-operator :deep(.el-select__selected-item),
.rule-value-boolean :deep(.el-select__selected-item) {
  min-width: 0;
}
.rule-field :deep(.el-select__selection),
.rule-operator :deep(.el-select__selection),
.rule-value-boolean :deep(.el-select__selection) {
  min-width: 0;
  width: 100%;
}

/* value 列兜底 input 占满列宽, 防止 placeholder 撑开 cell */
.rule-value-input {
  width: 100%;
  display: block;
}

/* 统一字号/高度/padding, 让选中态与空态、picker trigger 视觉一致 */
.rule-field :deep(.el-select__wrapper),
.rule-operator :deep(.el-select__wrapper),
.rule-value-boolean :deep(.el-select__wrapper) {
  font-size: 12px;
  line-height: 24px;
  min-height: 28px;   /* 高度统一 28px, 与 picker trigger / input 对齐 */
  padding-left: 12px; /* 文字起点统一 12px */
  padding-right: 12px;
}
.rule-field :deep(.el-select__placeholder),
.rule-operator :deep(.el-select__placeholder),
.rule-value-boolean :deep(.el-select__placeholder),
.rule-field :deep(.el-select__selected-item span),
.rule-operator :deep(.el-select__selected-item span),
.rule-value-boolean :deep(.el-select__selected-item span),
.rule-field :deep(.el-select__selection-item),
.rule-operator :deep(.el-select__selection-item),
.rule-value-boolean :deep(.el-select__selection-item) {
  font-size: 12px;
  line-height: 24px;
}

/* placeholder 文本过长时省略 */
.rule-field :deep(.el-select__placeholder),
.rule-operator :deep(.el-select__placeholder),
.rule-value-boolean :deep(.el-select__placeholder) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.rule-value-wrapper {
  position: relative;
  min-width: 0;
}

/* [v50] 触发器改为 div[role=button]（button 内不能嵌套 button），
   高度自适应：无已选值时与 ElSelect 一致 28px；有 tag 时框体增高容纳 */
.rule-value-picker-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;  /* 文本过长时省略 */
  min-height: 28px;
  padding: 2px 10px 2px 12px; /* 与 ElSelect wrapper padding 对齐, 文字起点一致 */
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: var(--radius-sm, 4px);
  background: var(--color-bg-container, #fff);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  user-select: none;
  box-sizing: border-box;
}
.rule-value-picker-trigger:hover:not(.rule-value-picker-trigger--disabled) {
  border-color: var(--color-primary, #ea580c);
}
.rule-value-picker-glyph,
.rule-value-picker-edit {
  flex-shrink: 0;
}
.rule-value-picker-trigger--empty {
  color: var(--color-text-placeholder, #bbb);
}
.rule-value-picker-trigger--disabled {
  background: var(--color-bg-tertiary, #fafafa);
  border-color: var(--color-border, #d9d9d9);
  color: var(--color-text-quaternary, #bbb);
  cursor: not-allowed;
}
.rule-value-picker-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-value-input {
  width: 100%;
  min-width: 0;  /* 文本输入框可正确收缩 */
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: var(--radius-sm, 4px);
  font-size: 12px;
  outline: none;
  background: var(--color-bg-container, #fff);
}
.rule-value-input:focus {
  border-color: var(--color-primary, #ea580c);
}
.rule-value-input:disabled {
  background: var(--color-bg-tertiary, #fafafa);
  border-color: var(--color-border, #d9d9d9);
  color: var(--color-text-quaternary, #bbb);
  cursor: not-allowed;
}

.rule-remove {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #999);
  cursor: pointer;
  border-radius: var(--radius-sm, 4px);
}
.rule-remove:hover:not(:disabled) {
  background: var(--color-error-bg, #fef2f2);
  color: var(--color-error, #dc2626);
}
.rule-remove:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* [v50] 已选值 tag 条 — 内嵌在触发器框体内部（对齐 Element Plus 多选下拉交互）
     - flex:1 占据 icon 与 edit 图标之间的主体区域
     - 超过 2 行(约46px)内部滚动，避免单行无限撑高行距 */
.rule-value-tags {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  align-content: center;
  gap: 3px;
  min-width: 0;
  max-height: 46px;
  overflow-y: auto;
}
.rule-value-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  max-width: 100%;
  padding: 0 2px 0 6px;
  height: 18px;
  background: var(--color-primary-bg, #fff7ed);
  color: var(--color-primary, #ea580c);
  font-size: 11px;
  border-radius: 3px;
}
.rule-value-tag-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rule-value-tag-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  border-radius: 2px;
  padding: 0;
}
.rule-value-tag-remove:hover {
  background: rgba(234, 88, 12, 0.15);
}
.rule-value-tags-clear {
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #999);
  font-size: 11px;
  cursor: pointer;
  padding: 0 2px;
  height: 18px;
  line-height: 18px;
}
.rule-value-tags-clear:hover {
  color: var(--color-error, #dc2626);
}
</style>