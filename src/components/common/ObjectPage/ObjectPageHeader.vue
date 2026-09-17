<template>
  <header :class="['object-page__header', `object-page__header--${size}`]">
    <div class="object-page__header-left">
      <AppButton v-if="showBackButton" variant="text" size="sm" class="object-page__back-btn" @click="$emit('back')">
        <AppIcon name="arrow-left" size="sm" />
        <span>返回</span>
      </AppButton>
      <span v-if="showBackButton && ($slots.breadcrumb || breadcrumbs?.length)" class="object-page__header-sep"></span>
      <nav v-if="$slots.breadcrumb || breadcrumbs?.length" class="object-page__breadcrumb">
        <slot name="breadcrumb">
          <template v-for="(crumb, index) in breadcrumbs" :key="index">
            <a href="#" :class="['breadcrumb-item', { 'breadcrumb-item--link': index < breadcrumbs.length - 1 }]" @click.prevent="index < breadcrumbs.length - 1 && $emit('navigate', crumb)">
              {{ crumb.label }}
            </a>
            <span v-if="index < breadcrumbs.length - 1" class="breadcrumb-sep">›</span>
          </template>
        </slot>
      </nav>
    </div>
    <div class="object-page__header-right">
      <span v-if="status" :class="['status-badge', `status-badge--${statusType}`]">{{ status }}</span>
      <div
        v-if="showStateTransitions && objectType && objectId && objectId !== 'new' && !editing"
        class="op-state-transitions"
      >
        <StateTransitionButtons
          :object-type="objectType"
          :object-id="objectId"
          size="small"
          @refresh="(payload) => handleStateTransitionRefresh(payload)"
        />
      </div>
      <span v-if="showStateTransitions && objectType && objectId && objectId !== 'new' && !editing && actions && actions.length > 0" class="op-group-sep"></span>
      <div v-if="actions && actions.length > 0" class="op-actions">
        <AppButton v-for="act in visibleActions" :key="act.key" :variant="act.variant" size="sm" :loading="act.key === 'save' && saving" class="op-action-btn" @click="handleAction(act)">
          {{ act.label }}
        </AppButton>
      </div>
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import AppButton from '../AppButton/AppButton.vue'
import AppIcon from '../AppIcon/AppIcon.vue'
import StateTransitionButtons from '@/components/bo/StateTransitionButtons.vue'

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  status: { type: String, default: '' },
  statusType: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'primary', 'success', 'warning', 'error'].includes(v)
  },
  breadcrumbs: { type: Array, default: () => [] },
  showBackButton: { type: Boolean, default: false },
  actions: { type: Array, default: () => [] },
  visibleActions: { type: Array, default: () => [] },
  editing: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  objectType: { type: String, default: null },
  objectId: { type: [String, Number], default: null },
  showStateTransitions: { type: Boolean, default: true },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg'].includes(v)
  }
})

const emit = defineEmits(['back', 'navigate', 'action', 'update:editing', 'refresh'])

const ACTION_SEMANTIC_MAP = {
  'edit': 'start_edit', 'create': 'start_edit', 'update': 'start_edit', 'modify': 'start_edit',
  'save': 'save', 'submit': 'save', 'confirm': 'save',
  'cancel': 'cancel_edit', 'close': 'cancel_edit',
  'delete': 'delete', 'remove': 'delete', 'destroy': 'delete'
}

const DEFAULT_ACTION_ICONS = {
  'edit': 'edit',
  'save': 'check',
  'cancel': 'close',
  'delete': 'trash',
  'create': 'plus',
  'add': 'plus',
  'submit': 'check',
  'confirm': 'check',
  'approve': 'check',
  'reject': 'close',
  'export': 'export',
  'import': 'download',
  'print': 'file',
  'copy': 'copy',
  'refresh': 'refresh',
  'search': 'search',
  'filter': 'filter',
  'settings': 'settings',
  'config': 'settings',
  'more': 'chevron-right',
  'view': 'eye',
  'detail': 'eye',
  'list': 'layers',
  'link': 'link',
  'assign': 'link',
  'unassign': 'close',
  'enable': 'check-circle',
  'disable': 'x-circle',
  'activate': 'check-circle',
  'deactivate': 'x-circle',
  'publish': 'export',
  'unpublish': 'close',
  'archive': 'file',
  'restore': 'refresh'
}

function inferSemantic(actionKey) {
  if (!actionKey) return 'default'
  const key = String(actionKey).toLowerCase()
  return ACTION_SEMANTIC_MAP[key] || key
}

function getDefaultActionIcon(actionKey) {
  if (!actionKey) return 'chevron-right'
  const key = String(actionKey).toLowerCase()
  return DEFAULT_ACTION_ICONS[key] || 'chevron-right'
}

function handleAction(action) {
  emit('action', action)
}

function handleStateTransitionRefresh(payload = {}) {
  console.debug('[ObjectPageHeader] handleStateTransitionRefresh, payload:', payload)
  emit('refresh', payload)
  emit('action', { semantic: 'refresh', ...payload })
}
</script>

<style scoped>
.object-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg-container);
  border-bottom: 1px solid var(--color-border-secondary);
  flex-shrink: 0;
  z-index: var(--z-index-sticky);
  min-height: 36px;
  padding: var(--spacing-xs) var(--spacing-md);
}

.object-page__header--sm {
  padding: var(--spacing-xs) var(--spacing-md);
}

.object-page__header--md {
  padding: var(--spacing-sm) var(--spacing-md);
}

.object-page__header--lg {
  padding: var(--spacing-sm) var(--spacing-lg);
}

.object-page__header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
  min-width: 0;
}

.object-page__back-btn {
  flex-shrink: 0;
  color: var(--color-text-secondary);
  transition: color 0.15s ease;
}

.object-page__back-btn:hover {
  color: var(--color-primary);
}

.object-page__header-sep {
  width: 1px;
  height: 14px;
  background: var(--color-border);
  flex-shrink: 0;
  margin: 0 var(--spacing-md);
}

.object-page__header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
  padding-left: var(--spacing-md);
}

.op-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.op-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.op-action-btn :deep(.el-button) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* [FIX 2026-09-13] state-transition buttons group:
     1) 统一内部按钮 padding/height, 跟 op-actions 一致 (避免"大小不同")
     2) 加分组分隔条, 跟 op-actions 之间形成视觉 group 边界 (避免"组间 vs 组内间隔不一致")
*/
.op-state-transitions {
  display: flex;
  align-items: center;
}

.op-state-transitions :deep(.state-transition-buttons) {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

/* [FIX 2026-09-13] 强制让 state-transition 的 el-button 跟 op-action-btn 一样大小/内边距 */
.op-state-transitions :deep(.state-transition-buttons .el-button) {
  height: 24px;
  padding: 0 11px;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--el-border-radius-base);
}

.op-state-transitions :deep(.state-transition-buttons .el-button + .el-button) {
  margin-left: 0;  /* 覆盖 Element Plus 默认 ml 8px, 让 gap 12px 完全控制 */
}

/* [FIX 2026-09-13] group 分隔: 竖线 + 双倍间距, 跟组内 gap 形成视觉差 */
.op-group-sep {
  display: inline-block;
  width: 1px;
  height: 16px;
  background: var(--color-border, #d4d4d8);
  margin: 0 4px;
  flex-shrink: 0;
}

.object-page__breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: 13px;
  color: var(--color-text-secondary);
  flex: 1;
  min-width: 0;
  line-height: 1.4;
}

.breadcrumb-item {
  color: inherit;
  text-decoration: none;
  transition: color 0.15s ease;
  white-space: nowrap;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

.breadcrumb-item:last-child {
  color: var(--color-text-primary);
  font-weight: 500;
  max-width: 280px;
}

.breadcrumb-item--link {
  color: var(--color-text-tertiary);
  cursor: pointer;
}

.breadcrumb-item--link:hover {
  color: var(--color-primary);
}

.breadcrumb-sep {
  color: var(--color-text-quaternary);
  font-size: 12px;
  flex-shrink: 0;
  margin: 0 4px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-badge);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
  flex-shrink: 0;
}

.status-badge--default {
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.status-badge--primary {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.status-badge--success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-badge--warning {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark, #d48806);
}

.status-badge--error {
  background: var(--color-error-bg);
  color: var(--color-error);
}
</style>
