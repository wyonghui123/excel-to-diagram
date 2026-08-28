<!--
  RuleBuilderGroup.vue
  递归渲染 Group 节点 (含嵌套子组)

  [v27 2026-08-26] Phase 4 嵌套 AND/OR 支持
    - 递归组件, 接收 GroupNode + level + maxNestingLevel
    - 子节点: rule → <ConditionRuleRow>; group → <RuleBuilderGroup :level="level+1">
    - 「添加条件」「添加子组」按钮, 子组按钮在达到 maxNestingLevel 时 disabled
    - 顶部 connector radio (中文「且 / 或」) 控制子节点间连接
    - 头部产品对照: Proofpoint Cloud Rule Editor / MetacatUI QueryBuilder

  API:
    node             当前 GroupNode
    level            嵌套层级 (0=顶层, 1=子组, 2=孙组)
    maxNestingLevel  嵌套深度上限 (默认 3, 由父组件传入)
    fieldMetadata    字段元数据
    resourceType     资源类型
    pickerCtx        { form }
    ruleValueFetcher fetcher (rule, ctx, params) => Promise
    isTopLevel       是否顶层 group (决定样式与 connector 默认值)
    disabled         是否禁用全部控件

  Emits:
    update:node      新 GroupNode (整体替换)
    change           任意修改后触发 (用于同步父组件序列化)
-->
<template>
  <div
    class="rule-builder-group"
    :class="{ 'rule-builder-group--nested': !isTopLevel }"
  >
    <!-- [v30 fix5] 子组连接行 (仅子组显示, 顶层无)
     *   - 用 grid 对齐 row: connector(且/或) | 子组 chip+× | (空)
     *   - connector 列承载「子组与外层上一行的连接符」
     *   - chip 列承载「这是一个子组」标识, × 紧随其后(右上角, fix24)
     *   - 删除整个子组仅此一处 (add-row 的「删除子组」按钮已移除 fix24)
    -->
    <div v-if="!isTopLevel" class="rule-builder-group-tag-row">
      <div class="rule-connector">
        <div class="rule-connector-seg" :class="{ 'is-disabled': disabled }">
          <button
            type="button"
            class="rule-connector-seg-btn"
            :class="{ 'is-active': node.connector === 'AND' }"
            :disabled="disabled"
            @click="updateConnector('AND')"
          >且</button>
          <button
            type="button"
            class="rule-connector-seg-btn"
            :class="{ 'is-active': node.connector === 'OR' }"
            :disabled="disabled"
            @click="updateConnector('OR')"
          >或</button>
        </div>
      </div>
      <span class="rule-subgroup-chip-group">
        <span class="rule-subgroup-chip">子组</span>
        <button
          v-if="!disabled"
          type="button"
          class="rule-subgroup-remove"
          title="删除整个子组"
          :disabled="disabled"
          @click="$emit('removeGroup')"
        ><AppIcon name="close" :size="12" /></button>
      </span>
      <span></span>
    </div>

    <!-- 子节点列表 (rule / group 递归) + 添加按钮行
     *   注意: add-row 必须放在 children 内部末尾, 这样子组(add-row 由 fix23
     *   children 的 padding-left:16px 缩进) 的「添加条件」才不会跑到子组竖线外
    -->
    <div class="rule-builder-group-children">
      <template v-for="(child, idx) in node.children" :key="child.id">
        <!-- rule 叶子节点 -->
        <div v-if="child.type === 'rule'" class="rule-builder-row-wrapper">
          <ConditionRuleRow
            :rule="child"
            :field-options="fieldOptions"
            :field-metadata="fieldMetadata"
            :resource-type="resourceType"
            :picker-ctx="pickerCtx"
            :rule-value-fetcher="ruleValueFetcher"
            :is-first="idx === 0"
            :can-delete="canDeleteChild"
            :group-type="isTopLevel ? 'top' : 'subgroup'"
            :can-remove-group="false"
            :disabled="disabled"
            @update:rule="(patch) => updateChild(idx, patch)"
            @change="$emit('change')"
            @remove="removeChild(idx)"
            @remove-group="$emit('change')"
          />
        </div>
        <!-- group 嵌套 -->
        <RuleBuilderGroup
          v-else
          :node="child"
          :level="level + 1"
          :max-nesting-level="maxNestingLevel"
          :field-metadata="fieldMetadata"
          :resource-type="resourceType"
          :picker-ctx="pickerCtx"
          :rule-value-fetcher="ruleValueFetcher"
          :is-top-level="false"
          :disabled="disabled"
          @update:node="(newChild) => replaceChild(idx, newChild)"
          @change="$emit('change')"
          @remove-group="removeChild(idx)"
        />
      </template>

      <!-- [v30] 添加按钮行：
       *   - 顶层: 起点在 grid 第2 列 (field 列), 与顶层 rows connector 列对齐
       *   - 子组: 随 children padding-left 缩进, 与子条件对齐, 竖线覆盖
      -->
      <div class="rule-builder-add-row">
        <button
          v-if="!disabled"
          type="button"
          class="rule-add-btn"
          @click="addRule"
        >
          <AppIcon name="plus" :size="11" />
          <span>添加条件</span>
        </button>
        <button
          v-if="!disabled"
          type="button"
          class="rule-add-btn rule-add-btn--subgroup"
          :disabled="!canAddSubgroup"
          :title="canAddSubgroup ? '添加子组' : `已达最大嵌套深度 ${maxNestingLevel}`"
          @click="addSubgroup"
        >
          <AppIcon name="plus" :size="11" />
          <span>添加子组</span>
        </button>
        <!-- [v30 fix24] 子组删除按钮已移除, 删除子组统一用 tag-row 右上角 × -->
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
// import {} from 'element-plus'  // [v29] 不再需要 ElRadioButton, 用自定义 segmented
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import ConditionRuleRow from './ConditionRuleRow.vue'

const props = defineProps({
  node: { type: Object, required: true },  // GroupNode
  level: { type: Number, default: 0 },
  maxNestingLevel: { type: Number, default: 3 },
  fieldMetadata: { type: Array, default: () => [] },
  resourceType: { type: String, default: '' },
  pickerCtx: { type: Object, default: () => ({}) },
  ruleValueFetcher: { type: Function, required: true },
  isTopLevel: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:node', 'change', 'removeGroup'])

// 字段下拉选项 (与 ConditionRuleBuilder 共享格式)
// [v30 fix8] label 简化: 仅显示字段名 (不附加类型), 避免长字段名 + 类型被截断
//   - 完整信息 (字段名 + 类型) 通过 el-option slot + title tooltip 展示
const fieldOptions = computed(() => {
  return props.fieldMetadata.map((f) => ({
    value: f.db_column,
    label: f.name,
    fieldType: f.field_type,
    rawName: f.name,
  }))
})

// 嵌套深度: 顶层=0, 子组=1, 孙组=2 (maxNestingLevel=3 时)
// level=2 已是最后一层 (level+1=3=maxNestingLevel), 不能再生子组
const canAddSubgroup = computed(() => props.level + 1 < props.maxNestingLevel)

let _idCounter = 1
function nextId(prefix) {
  return `${prefix}-${Date.now()}-${_idCounter++}`
}

function createEmptyRule(connector) {
  return {
    type: 'rule',
    id: nextId('rule'),
    connector: connector || 'AND',
    field: '',
    fieldType: 'string',
    operator: 'IN',
    value: '',
    relationObject: '',
    isBusinessKey: false,
    isEnum: false,
    enumValues: null,
    enumRef: null,
    pickerVisible: false,
    pickerSelectedIds: [],
    pickerSelectedItems: [],
  }
}

function createEmptyGroup(connector) {
  return {
    type: 'group',
    id: nextId('grp'),
    connector: connector || 'AND',
    children: [createEmptyRule('AND')],
  }
}

/** 顶层 group 必须至少保留 1 个 child (防止空表达式) */
const canDeleteChild = computed(() => props.node.children.length > 1)

function emitNewNode(newChildren) {
  emit('update:node', { ...props.node, children: newChildren })
  emit('change')
}

function updateChild(idx, patch) {
  const next = props.node.children.map((c, i) => {
    if (i !== idx) return c
    // 子组件 merge patch, 但保留 type/id 不可变
    return { ...c, ...patch, type: c.type, id: c.id }
  })
  emitNewNode(next)
}

function replaceChild(idx, newChild) {
  const next = props.node.children.map((c, i) => (i === idx ? newChild : c))
  emitNewNode(next)
}

function removeChild(idx) {
  if (props.node.children.length <= 1) return
  const next = props.node.children.filter((_, i) => i !== idx)
  // 首个 child 的 connector 无意义, 清掉避免 UI 误导
  if (next.length > 0) {
    next[0] = { ...next[0], connector: undefined }
  }
  emitNewNode(next)
}

// [v30 fix5] 子组 connector 重新由 RuleBuilderGroup 承担 (tag-row 内 segmented)
//   这里需要 updateConnector 函数更新子组 connector
function updateConnector(val) {
  emit('update:node', { ...props.node, connector: val })
  emit('change')
}

function addRule() {
  const lastChild = props.node.children[props.node.children.length - 1]
  const connector = lastChild ? (lastChild.connector || 'AND') : 'AND'
  const newRule = createEmptyRule(connector)
  emitNewNode([...props.node.children, newRule])
}

function addSubgroup() {
  if (!canAddSubgroup.value) return
  const lastChild = props.node.children[props.node.children.length - 1]
  const connector = lastChild ? (lastChild.connector || 'AND') : 'AND'
  const newGroup = createEmptyGroup(connector)
  emitNewNode([...props.node.children, newGroup])
}
</script>

<style scoped>
.rule-builder-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.rule-builder-group--nested {
  /* 子组对齐坐标系（排查必读）:
   *   - tag-row(且/或+子组) 必须与外部规则行左对齐到同一起点(x=40),
   *     因此 --nested 自身不加缩进(不加 margin/padding)。
   *   - 进深(16px) + 左侧竖线只加在 children 层, 让子组内规则右移体现层级,
   *     竖线占缩进区左侧 4px, 不占内容宽度。 */
  margin-top: 0;
  margin-bottom: 4px;
  min-width: 0;
}

.rule-builder-group--nested .rule-builder-group-children {
  position: relative;
  padding-left: 16px;
}
.rule-builder-group--nested .rule-builder-group-children::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--color-primary-light-7, #fed7aa);
  pointer-events: none;
}

.rule-builder-group-children {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  /* 顶层无缩进(x=0 与 add-row 对齐); 子组 16px 缩进见 --nested 规则 */
}

.rule-builder-row-wrapper {
  display: flex;
  align-items: center;
  min-width: 0;
}

.rule-builder-add-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  /* add-row 起点 = 所在 group 内容区 x=0: 顶层与 connector 列对齐,
   * 子组随 children 缩进(x=56)与子条件对齐 (必须放在 children 内部, 否则跑出竖线) */
  padding-left: 0;
  flex-wrap: wrap;
}

.rule-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1px dashed var(--color-primary, #ea580c);
  background: transparent;
  color: var(--color-primary, #ea580c);
  border-radius: var(--radius-sm, 4px);
  font-size: 12px;
  cursor: pointer;
  width: fit-content;  /* 宽度自适应内容, 不被 flex 拉伸 */
  flex-shrink: 0;
}

.rule-add-btn:hover:not(:disabled) {
  background: var(--color-primary-bg, #fff7ed);
}

.rule-add-btn--subgroup {
  border-style: dotted;
  color: var(--color-text-secondary, #666);
  border-color: var(--color-border, #d9d9d9);
}

.rule-add-btn--subgroup:hover:not(:disabled) {
  border-color: var(--color-primary, #ea580c);
  color: var(--color-primary, #ea580c);
}

.rule-add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 子组 tag-row: grid 3 列(70px connector | chip+× | 空), 与子规则且/或列起点对齐;
 *   顶部无 padding, 让按钮紧贴上边界 */
.rule-builder-group-tag-row {
  display: grid;
  grid-template-columns: 70px auto minmax(0, 1fr);
  gap: 6px;
  align-items: center;
  padding: 0 0 4px;
  margin-bottom: 2px;
  min-width: 0;
}
.rule-builder-group-tag-row .rule-connector {
  display: flex;
  align-items: center;
  justify-content: flex-start;
}
.rule-builder-group-tag-row .rule-connector-seg {
  display: inline-flex;
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: var(--radius-sm, 4px);
  overflow: hidden;
  background: var(--color-bg-container, #fff);
  height: 24px;
}
.rule-builder-group-tag-row .rule-connector-seg.is-disabled {
  opacity: 0.5;
}
.rule-builder-group-tag-row .rule-connector-seg-btn {
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
.rule-builder-group-tag-row .rule-connector-seg-btn:not(:last-child) {
  border-right: 1px solid var(--color-border, #d9d9d9);
}
.rule-builder-group-tag-row .rule-connector-seg-btn:hover:not(.is-active):not(:disabled) {
  background: var(--color-bg-tertiary, #fafafa);
}
.rule-builder-group-tag-row .rule-connector-seg-btn.is-active {
  background: var(--color-primary, #ea580c);
  color: #fff;
}
.rule-builder-group-tag-row .rule-connector-seg-btn:disabled {
  cursor: not-allowed;
}
.rule-builder-group-tag-row .rule-subgroup-chip-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  justify-self: start;
}
.rule-builder-group-tag-row .rule-subgroup-chip {
  font-size: 11px;
  color: var(--color-primary, #ea580c);
  background: var(--color-primary-light-9, #fff7ed);
  padding: 2px 6px;
  border-radius: var(--radius-sm, 4px);
  font-weight: var(--font-weight-medium, 500);
  line-height: 1.4;
  white-space: nowrap;
}
.rule-builder-group-tag-row .rule-subgroup-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-text-tertiary, #999);
  cursor: pointer;
  border-radius: 50%;
  transition: background 0.15s, color 0.15s;
}
.rule-builder-group-tag-row .rule-subgroup-remove:hover:not(:disabled) {
  background: var(--color-danger-light-9, #fef2f2);
  color: var(--color-danger, #dc2626);
}
.rule-builder-group-tag-row .rule-subgroup-remove:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>