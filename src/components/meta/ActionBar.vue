<template>
  <div class="action-bar">
    <el-tooltip
      v-for="item in visibleActions"
      :key="item.id"
      :content="item.tooltip"
      :disabled="!item.tooltip"
      placement="top"
    >
      <span class="action-bar__item">
        <el-button
          :type="item.buttonType"
          :size="item.size || 'small'"
          :disabled="item.disabled"
          :loading="loading"
          @click="onClick(item)"
        >
          {{ item.label }}
        </el-button>
      </span>
    </el-tooltip>
  </div>
</template>

<script setup>
/**
 * ActionBar - 动作条（T13-6）
 *
 * 动作可用性统一走 useBatchActions（后端 actions/evaluate 权威判定）：
 * - enabled=false → 按钮 disabled，并用 el-tooltip 展示 reason 文案
 * - 未返回（pending）/请求失败 → 全部禁用（fail-closed）
 * - 本组件是「动作 → 按钮样式」的唯一映射处，不引入第二套标签映射
 */

import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useBatchActions } from '@/composables/useBatchActions'

const props = defineProps({
  // 对象类型（actions/evaluate 必需）
  objectType: { type: String, default: '' },
  // UiActionMeta 列表（id 或 key 至少一个）
  actions: { type: Array, default: () => [] },
  // 当前选中的记录 id；为空表示对象级动作
  ids: { type: Array, default: () => [] },
  hideDisabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['action'])

// 后端 reason → 用户可读文案
const REASON_TEXT = {
  unsupported: '不支持该动作',
  pending: '正在校验动作可用性…',
  evaluate_failed: '动作校验失败，请稍后重试',
  no_permission: '无权限执行该动作',
  readonly_object: '当前对象只读',
  precondition_false: '当前记录状态不满足执行条件',
  no_selection: '请先选择数据'
}

// 动作样式 → el-button type（唯一的样式映射，缺省不传 ⇒ 默认按钮）
const BUTTON_TYPE_MAP = {
  primary: 'primary',
  success: 'success',
  warning: 'warning',
  danger: 'danger',
  info: 'info'
}

const objectTypeRef = computed(() => props.objectType)
const batch = useBatchActions(objectTypeRef)

/**
 * 批量动作要求所有选中行都可用；返回第一个不可用 verdict（含 reason）。
 */
function resolveAvailability(action) {
  const rowIds = Array.isArray(props.ids) ? props.ids : []
  if (!rowIds.length) {
    // 批量动作未选中任何行 → 整组禁用；对象级动作走后端 `_object` 桶
    if ((action.position || '') === 'batch') return { enabled: false, reason: 'no_selection' }
    return batch.getAction('_object', action)
  }
  let verdict = null
  for (const id of rowIds) {
    const current = batch.getAction(id, action)
    if (!current.enabled) return current
    verdict = current
  }
  return verdict || { enabled: false, reason: 'pending' }
}

const renderedActions = computed(() => (props.actions || []).map(action => {
  const id = action.id || action.key || ''
  const availability = resolveAvailability(action)
  const isDisabled = availability.enabled !== true
  return {
    id,
    label: action.label || id,
    raw: action,
    disabled: isDisabled,
    tooltip: isDisabled ? (REASON_TEXT[availability.reason] || '当前不可用') : '',
    buttonType: BUTTON_TYPE_MAP[action.style || action.variant || action.type] || '',
    size: action.size || 'small'
  }
}))

const visibleActions = computed(() => (
  props.hideDisabled
    ? renderedActions.value.filter(item => !item.disabled)
    : renderedActions.value
))

function needsConfirm(action) {
  return Boolean(action.confirm) || action.style === 'danger' || action.variant === 'danger'
}

function confirmText(action) {
  if (typeof action.confirm === 'string' && action.confirm) return action.confirm
  return action.confirm_text || action.label || '确认执行该动作？'
}

async function onClick(item) {
  if (item.disabled) return
  const action = item.raw
  if (needsConfirm(action)) {
    try {
      await ElMessageBox.confirm(confirmText(action), action.label || '确认', {
        type: 'warning',
        confirmButtonText: '确定',
        cancelButtonText: '取消'
      })
    } catch {
      // 用户取消 → 不触发动作
      return
    }
  }
  emit('action', { action: item.id, ids: [...(props.ids || [])] })
}
</script>

<style scoped>
.action-bar {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.action-bar__item {
  display: inline-flex;
}
</style>