<template>
  <div class="enum-search-help">
    <button
      type="button"
      class="btn-search-help"
      :disabled="disabled"
      @click="openSearchHelp"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5"/>
        <path d="M11 11l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>

    <!-- Search Help Dialog -->
    <div v-if="visible" class="search-help-overlay" @click="closeSearchHelp">
      <div class="search-help-dialog" @click.stop>
        <div class="search-help-header">
          <h4>{{ title }}</h4>
          <button class="btn-close" @click="closeSearchHelp">&times;</button>
        </div>
        <div class="search-help-filter">
          <input
            v-model="filterText"
            placeholder="搜索..."
            class="filter-input"
            @keydown.esc="closeSearchHelp"
          />
        </div>
        <div class="search-help-list">
          <div v-if="loading" class="search-help-loading">加载中...</div>
          <template v-else>
            <div
              v-for="item in filteredItems"
              :key="item.code"
              class="search-help-item"
              :class="{ 'is-selected': isSelected(item) }"
              @click="selectItem(item)"
            >
              <div class="item-code">{{ item.code }}</div>
              <div class="item-name">{{ item.name }}</div>
              <div v-if="item.description" class="item-desc">{{ item.description }}</div>
            </div>
            <div v-if="filteredItems.length === 0" class="search-help-empty">
              无匹配数据
            </div>
          </template>
        </div>
        <div v-if="showNewButton" class="search-help-footer">
          <button type="button" class="btn-new" @click="handleNew">
            + 新增
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { EnumService } from '@/services/enumService'

const props = defineProps({
  enumType: {
    type: String,
    required: true
  },
  title: {
    type: String,
    default: '选择值'
  },
  modelValue: {
    type: String,
    default: ''
  },
  disabled: {
    type: Boolean,
    default: false
  },
  showNewButton: {
    type: Boolean,
    default: false
  },
  filterFields: {
    type: Array,
    default: () => ['code', 'name', 'description']
  }
})

const emit = defineEmits(['update:modelValue', 'select', 'new'])

const visible = ref(false)
const filterText = ref('')
const loading = ref(false)
const items = ref([])

const filteredItems = computed(() => {
  if (!filterText.value) return items.value
  const text = filterText.value.toLowerCase()
  return items.value.filter(item =>
    props.filterFields.some(field =>
      item[field]?.toLowerCase?.().includes(text)
    )
  )
})

function isSelected(item) {
  return item.code === props.modelValue
}

async function loadItems() {
  loading.value = true
  try {
    const options = await EnumService.loadOptions(props.enumType, { useHighSpeedEndpoint: false })
    items.value = options.map(item => ({
      code: item.value || item.code,
      name: item.label || item.name,
      description: ''
    }))
  } catch (e) {
    console.error('Failed to load enum values:', e)
    items.value = []
  } finally {
    loading.value = false
  }
}

function openSearchHelp() {
  if (props.disabled) return
  visible.value = true
  filterText.value = ''
  loadItems()
}

function closeSearchHelp() {
  visible.value = false
}

function selectItem(item) {
  emit('update:modelValue', item.code)
  emit('select', item)
  closeSearchHelp()
}

function handleNew() {
  emit('new')
}

watch(visible, (val) => {
  if (val) {
    loadItems()
  }
})
</script>

<style scoped>
.enum-search-help {
  display: inline-flex;
}

.btn-search-help {
  padding: var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
  color: var(--color-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast) var(--ease-out);
}

.btn-search-help:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.btn-search-help:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.search-help-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.search-help-dialog {
  background: var(--color-bg-container);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 480px;
  max-height: 600px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.search-help-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-light);
}

.search-help-header h4 {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
}

.btn-close {
  border: none;
  background: transparent;
  font-size: 20px;
  color: var(--color-text-tertiary);
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-close:hover {
  color: var(--color-text-primary);
}

.search-help-filter {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-light);
}

.filter-input {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  outline: none;
  box-sizing: border-box;
}

.filter-input:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.search-help-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-sm) 0;
}

.search-help-loading,
.search-help-empty {
  padding: var(--spacing-lg);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.search-help-item {
  padding: var(--spacing-sm) var(--spacing-lg);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out);
  border-bottom: 1px solid var(--color-border-light);
}

.search-help-item:last-child {
  border-bottom: none;
}

.search-help-item:hover,
.search-help-item.is-selected {
  background: var(--color-bg-secondary);
}

.item-code {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-primary);
  margin-bottom: 2px;
}

.item-name {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  margin-bottom: 2px;
}

.item-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.search-help-footer {
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--color-border-light);
  display: flex;
  justify-content: center;
}

.btn-new {
  padding: var(--spacing-sm) var(--spacing-lg);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
  color: var(--color-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.btn-new:hover {
  border-color: var(--color-primary);
}
</style>
