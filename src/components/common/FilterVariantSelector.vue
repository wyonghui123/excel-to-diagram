<template>
  <div class="filter-variant-selector">
    <div class="variant-header">
      <span class="variant-title">过滤方案</span>
      <button class="variant-save-btn" @click="showSaveDialog = true" :disabled="!hasFilters">
        保存
      </button>
    </div>
    
    <div class="variant-list" v-if="variants.length > 0">
      <div
        v-for="variant in variants"
        :key="variant.id"
        :class="['variant-item', { 'variant-active': activeVariantId === variant.id }]"
        @click="applyVariant(variant)"
      >
        <span class="variant-name">
          {{ variant.name }}
          <span v-if="variant.is_shared" class="variant-badge shared">共享</span>
          <span v-if="variant.is_default" class="variant-badge default">默认</span>
        </span>
        <div class="variant-actions">
          <button
            v-if="!variant.is_default"
            class="variant-action-btn"
            @click.stop="setDefault(variant)"
            title="设为默认"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
          </button>
          <button
            v-if="!variant.is_shared"
            class="variant-action-btn delete"
            @click.stop="deleteVariant(variant)"
            title="删除"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
    
    <div v-else class="variant-empty">
      暂无保存的过滤方案
    </div>
    
    <Teleport to="body">
      <div v-if="showSaveDialog" class="variant-dialog-overlay" @click.self="showSaveDialog = false">
        <div class="variant-dialog">
          <div class="variant-dialog-header">
            <h3>保存过滤方案</h3>
            <button class="close-btn" @click="showSaveDialog = false">×</button>
          </div>
          <div class="variant-dialog-body">
            <div class="form-group">
              <label>方案名称</label>
              <input
                v-model="newVariantName"
                type="text"
                placeholder="请输入方案名称"
                class="form-input"
                @keyup.enter="saveVariant"
              />
            </div>
            <div class="form-group" v-if="isAdmin">
              <label class="checkbox-label">
                <input type="checkbox" v-model="newVariantShared" />
                <span>共享给所有用户</span>
              </label>
            </div>
            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" v-model="newVariantDefault" />
                <span>设为默认方案</span>
              </label>
            </div>
          </div>
          <div class="variant-dialog-footer">
            <button class="btn-cancel" @click="showSaveDialog = false">取消</button>
            <button class="btn-primary" @click="saveVariant" :disabled="!newVariantName.trim()">
              保存
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useMessage } from '@/composables/useMessage'
import * as filterVariantService from '@/services/filterVariantService'

const message = useMessage()

const props = defineProps({
  objectType: {
    type: String,
    required: true
  },
  currentFilters: {
    type: Object,
    default: () => ({})
  },
  hasFilters: {
    type: Boolean,
    default: false
  },
  isAdmin: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['apply', 'change'])

const variants = ref([])
const activeVariantId = ref(null)
const showSaveDialog = ref(false)
const newVariantName = ref('')
const newVariantShared = ref(false)
const newVariantDefault = ref(false)

async function loadVariants() {
  try {
    const data = await filterVariantService.queryFilterVariants({ object_type: props.objectType })
    if (data.success) {
      variants.value = data.data || []
      const defaultVariant = variants.value.find(v => v.is_default)
      if (defaultVariant) {
        activeVariantId.value = defaultVariant.id
      }
    }
  } catch (e) {
    console.error('Failed to load filter variants:', e)
  }
}

async function saveVariant() {
  if (!newVariantName.value.trim()) return
  try {
    const data = await filterVariantService.createFilterVariant({
      name: newVariantName.value.trim(),
      object_type: props.objectType,
      filters: props.currentFilters,
      is_shared: newVariantShared.value,
      is_default: newVariantDefault.value
    })
    if (data.success) {
      await loadVariants()
      activeVariantId.value = data.data.id
      showSaveDialog.value = false
      newVariantName.value = ''
      newVariantShared.value = false
      newVariantDefault.value = false
      emit('change')
    }
  } catch (e) {
    console.error('Failed to save filter variant:', e)
  }
}

function applyVariant(variant) {
  activeVariantId.value = variant.id
  emit('apply', variant.filters)
}

async function setDefault(variant) {
  try {
    const data = await filterVariantService.setDefaultFilterVariant(variant.id)
    if (data.success) {
      await loadVariants()
    }
  } catch (e) {
    console.error('Failed to set default variant:', e)
  }
}

async function deleteVariant(variant) {
  const confirmed = await message.confirm({ content: `确定要删除方案"${variant.name}"吗？` })
  if (!confirmed) return
  try {
    const data = await filterVariantService.deleteFilterVariant(variant.id)
    if (data.success) {
      if (activeVariantId.value === variant.id) {
        activeVariantId.value = null
      }
      await loadVariants()
      emit('change')
    }
  } catch (e) {
    console.error('Failed to delete filter variant:', e)
  }
}

watch(() => props.objectType, () => {
  loadVariants()
}, { immediate: true })

onMounted(() => {
  loadVariants()
})
</script>

<style scoped>
.filter-variant-selector {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm);
}

.variant-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--color-border-light);
  margin-bottom: var(--spacing-sm);
}

.variant-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.variant-save-btn {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.variant-save-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.variant-save-btn:disabled {
  background: var(--color-bg-tertiary);
  color: var(--color-text-quaternary);
  cursor: not-allowed;
}

.variant-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.variant-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.variant-item:hover {
  background: var(--color-bg-secondary);
}

.variant-item.variant-active {
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
}

.variant-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.variant-badge {
  font-size: var(--font-size-xs);
  padding: 1px 4px;
  border-radius: var(--radius-xs);
}

.variant-badge.shared {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.variant-badge.default {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.variant-actions {
  display: flex;
  gap: var(--spacing-xs);
  opacity: 0;
  transition: opacity var(--transition-normal);
}

.variant-item:hover .variant-actions {
  opacity: 1;
}

.variant-action-btn {
  padding: 2px;
  background: transparent;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-xs);
  transition: all var(--transition-normal);
}

.variant-action-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.variant-action-btn.delete:hover {
  color: var(--color-error);
}

.variant-empty {
  padding: var(--spacing-md);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.variant-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-index-modal-backdrop);
}

.variant-dialog {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  width: 360px;
  max-width: 90vw;
  box-shadow: var(--shadow-lg);
}

.variant-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-secondary);
}

.variant-dialog-header h3 {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--color-text-tertiary);
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: var(--color-text-secondary);
}

.variant-dialog-body {
  padding: var(--spacing-lg);
}

.form-group {
  margin-bottom: var(--spacing-md);
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-group label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-xs);
}

.form-input {
  width: 100%;
  padding: var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  outline: none;
  transition: border-color var(--transition-normal);
}

.form-input:focus {
  border-color: var(--color-primary);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.checkbox-label input {
  cursor: pointer;
}

.variant-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--color-border-secondary);
}

.btn-cancel {
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  cursor: pointer;
  color: var(--color-text-secondary);
  transition: all var(--transition-normal);
}

.btn-cancel:hover {
  background: var(--color-bg-secondary);
}

.btn-primary {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  cursor: pointer;
  color: white;
  transition: all var(--transition-normal);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  background: var(--color-bg-tertiary);
  cursor: not-allowed;
}
</style>
