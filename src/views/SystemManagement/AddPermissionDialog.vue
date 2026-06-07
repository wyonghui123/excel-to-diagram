<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog-card">
      <div class="dialog-header">
        <h3>添加数据权限</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="dialog-body">
        <div class="form-group">
          <label>权限名称 <span class="required">*</span></label>
          <input v-model="form.name" placeholder="例如：领域A的数据查看权限" />
        </div>

        <div class="form-group">
          <label>资源类型 <span class="required">*</span></label>
          <select v-model="form.resource_type" @change="onResourceTypeChange">
            <option value="">请选择...</option>
            <option v-for="rt in resourceTypes" :key="rt.value" :value="rt.value">
              {{ rt.label }}
            </option>
          </select>
        </div>

        <div class="form-group">
          <label>
            选择资源 <span class="required">*</span>
            <span v-if="selectedResources.length > 0" class="selected-count">
              (已选 {{ selectedResources.length }} 项)
            </span>
          </label>

          <div v-if="!form.resource_type" class="resource-placeholder">
            请先选择资源类型
          </div>

          <div v-else class="resource-selector">
            <div class="selector-toolbar">
              <input
                v-model="resourceKeyword"
                placeholder="搜索资源名称或编码..."
                @input="debounceSearchResources"
                class="search-input"
              />
              <button class="btn-clear" @click="clearSelection" v-if="selectedResources.length > 0">
                清空选择
              </button>
            </div>

            <div class="selector-list">
              <div v-if="loadingResources" class="loading-state">加载中...</div>
              <div v-else-if="filteredResources.length === 0" class="empty-state">
                {{ resourceKeyword ? '未找到匹配的资源' : '暂无可选资源' }}
              </div>
              <template v-else>
                <label
                  v-for="res in filteredResources"
                  :key="res.id"
                  class="resource-item"
                  :class="{ selected: isSelected(res.id) }"
                >
                  <input
                    type="checkbox"
                    :checked="isSelected(res.id)"
                    @change="toggleSelection(res)"
                  />
                  <div class="resource-info">
                    <span class="resource-name">{{ res.name || res.code || '-' }}</span>
                    <span class="resource-code">{{ res.code || `ID: ${res.id}` }}</span>
                  </div>
                </label>
              </template>
            </div>

            <div v-if="hasMoreResources" class="load-more">
              <button @click="loadMoreResources">加载更多...</button>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label>权限级别 <span class="required">*</span></label>
          <select v-model="form.permission_level">
            <option value="">请选择...</option>
            <option v-for="pl in permissionLevels" :key="pl.value" :value="pl.value">
              {{ pl.label }}
            </option>
          </select>
          <div class="field-hint">{{ currentPermissionHint }}</div>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="form.inherit_to_children" />
            继承到子级资源
          </label>
          <div class="field-hint">勾选后，该权限会自动应用到所选资源的所有下级资源</div>
        </div>

        <div v-if="error" class="error-msg">{{ error }}</div>
      </div>

      <div class="dialog-footer">
        <button class="btn btn-secondary" @click="$emit('close')">取消</button>
        <button class="btn btn-primary" @click="handleSubmit" :disabled="submitting || selectedResources.length === 0">
          {{ submitting ? '添加中...' : `确认添加 (${selectedResources.length})` }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import * as permService from '@/services/permissionService'
import { useMessage } from '@/composables/useMessage'

const props = defineProps({
  groupId: { type: [String, Number], required: true },
  existingPermissions: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'added'])
const message = useMessage()

const objectTypesMap = ref({})
const resourceTypes = computed(() => {
  if (!objectTypesMap.value || Object.keys(objectTypesMap.value).length === 0) {
    return Object.entries(permService.RESOURCE_LABELS).map(([value, label]) => ({ value, label }))
  }
  const list = []
  for (const [id, obj] of Object.entries(objectTypesMap.value)) {
    list.push({ value: id, label: obj.name })
  }
  return list.sort((a, b) => a.label.localeCompare(b.label))
})

async function loadObjectTypes() {
  try {
    const data = await permService.loadObjectTypes()
    if (data.success && data.data) {
      const map = {}
      for (const obj of data.data) map[obj.id] = obj
      objectTypesMap.value = map
    }
  } catch (e) {}
}

const permissionLevels = computed(() =>
  Object.entries(permService.PERMISSION_LEVELS).map(([value, { label }]) => ({ value, label }))
)

const form = reactive({
  name: '',
  resource_type: '',
  permission_level: '',
  inherit_to_children: true,
})

const resourceKeyword = ref('')
const resources = ref([])
const selectedResources = ref([])
const loadingResources = ref(false)
const resourcePage = ref(1)
const resourceTotal = ref(0)
const pageSize = 20

const error = ref('')
const submitting = ref(false)
let searchTimeout = null

const filteredResources = computed(() => resources.value)

const hasMoreResources = computed(() => resources.value.length < resourceTotal.value)

const currentPermissionHint = computed(() => {
  const pl = permissionLevels.value.find(p => p.value === form.permission_level)
  return pl?.label || ''
})

function onResourceTypeChange() {
  resources.value = []
  selectedResources.value = []
  resourcePage.value = 1
  resourceTotal.value = 0
  resourceKeyword.value = ''
  if (form.resource_type) {
    loadResources()
  }
}

async function loadResources(append = false) {
  if (!form.resource_type) return

  loadingResources.value = true
  try {
    const params = { page: resourcePage.value, page_size: pageSize }
    if (resourceKeyword.value) {
      params.keyword = resourceKeyword.value
    }

    const data = await permService.loadResources(form.resource_type, params)

    if (data.success) {
      if (append) {
        resources.value = [...resources.value, ...data.data]
      } else {
        resources.value = data.data
      }
      resourceTotal.value = data.total || data.data.length
    }
  } catch (e) {
    console.error('Failed to load resources:', e)
  } finally {
    loadingResources.value = false
  }
}

function debounceSearchResources() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    resourcePage.value = 1
    loadResources()
  }, 300)
}

function loadMoreResources() {
  resourcePage.value++
  loadResources(true)
}

function isSelected(id) {
  return selectedResources.value.some(r => r.id === id)
}

function toggleSelection(res) {
  const idx = selectedResources.value.findIndex(r => r.id === res.id)
  if (idx >= 0) {
    selectedResources.value.splice(idx, 1)
  } else {
    selectedResources.value.push(res)
  }
}

function clearSelection() {
  selectedResources.value = []
}

async function handleSubmit() {
  error.value = ''

  if (!form.name.trim()) {
    error.value = '请输入权限名称'
    return
  }

  if (!form.resource_type) {
    error.value = '请选择资源类型'
    return
  }

  if (selectedResources.value.length === 0) {
    error.value = '请选择至少一个资源'
    return
  }

  if (!form.permission_level) {
    error.value = '请选择权限级别'
    return
  }

  submitting.value = true

  try {
    let successCount = 0
    let failCount = 0

    for (const res of selectedResources.value) {
      const data = await permService.addGroupDataPermission(props.groupId, {
        name: selectedResources.value.length === 1
          ? form.name
          : `${form.name} - ${res.name || res.code}`,
        resource_type: form.resource_type,
        resource_id: res.id,
        permission_level: form.permission_level,
        inherit_to_children: form.inherit_to_children,
      })
      if (data.success) {
        successCount++
      } else {
        failCount++
      }
    }

    if (successCount > 0) {
      message.success(`成功添加 ${successCount} 条权限${failCount > 0 ? `，${failCount} 条失败` : ''}`)
      emit('added')
      emit('close')
    } else {
      error.value = '添加失败，请重试'
    }
  } catch (e) {
    message.error('网络错误')
  } finally {
    submitting.value = false
  }
}

onMounted(() => { loadObjectTypes() })
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-index-modal-backdrop);
}

.dialog-card {
  background: var(--color-bg-container);
  border-radius: var(--radius-xl);
  width: 560px;
  max-width: 95vw;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: var(--shadow-xl);
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-lg) var(--spacing-lg) 0;
}

.dialog-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  color: var(--color-text-primary);
}

.close-btn {
  border: none;
  background: transparent;
  font-size: 24px;
  color: var(--color-text-quaternary);
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: var(--color-text-primary);
}

.dialog-body {
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-group > label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.selected-count {
  font-weight: normal;
  color: var(--color-primary);
  margin-left: var(--spacing-xs);
}

.required {
  color: var(--color-error);
}

.field-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
}

.form-group input[type="text"],
.form-group input[type="number"],
.form-group select {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  outline: none;
  font-family: inherit;
}

.form-group input:focus,
.form-group select:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
}

.resource-placeholder {
  padding: var(--spacing-xl);
  text-align: center;
  color: var(--color-text-quaternary);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-md);
  border: 1px dashed var(--color-border);
}

.resource-selector {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.selector-toolbar {
  display: flex;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm);
  background: var(--color-bg-spotlight);
  border-bottom: 1px solid var(--color-border);
}

.search-input {
  flex: 1;
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  outline: none;
}

.search-input:focus {
  border-color: var(--color-primary);
}

.btn-clear {
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-container);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.btn-clear:hover {
  background: var(--color-bg-spotlight);
}

.selector-list {
  max-height: 240px;
  overflow-y: auto;
}

.loading-state,
.empty-state {
  padding: var(--spacing-xl);
  text-align: center;
  color: var(--color-text-quaternary);
  font-size: var(--font-size-sm);
}

.resource-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  border-bottom: 1px solid var(--color-border-secondary);
  transition: background var(--duration-fast);
}

.resource-item:last-child {
  border-bottom: none;
}

.resource-item:hover {
  background: var(--color-bg-spotlight);
}

.resource-item.selected {
  background: var(--color-primary-bg);
}

.resource-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
}

.resource-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.resource-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.resource-code {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.load-more {
  padding: var(--spacing-sm);
  text-align: center;
  border-top: 1px solid var(--color-border);
}

.load-more button {
  background: none;
  border: none;
  color: var(--color-primary);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.load-more button:hover {
  text-decoration: underline;
}

.error-msg {
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  border: 1px solid var(--color-error-border);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg) var(--spacing-lg);
}

.btn {
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  border: none;
  transition: all var(--duration-fast) var(--ease-out);
}

.btn-primary {
  background: var(--color-primary);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  background: var(--color-primary-disabled);
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.btn-secondary:hover {
  background: var(--color-border-secondary);
}
</style>
