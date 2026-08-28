<template>
  <div class="permission-dimension-selector">
    <div class="permission-dimension-selector__header">
      <h3 class="permission-dimension-selector__title">权限维度选择器</h3>
    </div>

    <div class="permission-dimension-selector__toolbar">
      <div class="permission-dimension-selector__search">
        <AppInput
          v-model="searchQuery"
          placeholder="搜索维度..."
          clearable
          @input="handleSearch"
        >
          <template #prefix>
            <AppIcon name="search" />
          </template>
        </AppInput>
      </div>

      <div class="permission-dimension-selector__view-toggle">
        <el-button-group>
          <AppButton
            :variant="localViewMode === 'list' ? 'primary' : 'secondary'"
            size="sm"
            @click="handleViewModeChange('list')"
          >
            <AppIcon name="list" />
            列表
          </AppButton>
          <AppButton
            :variant="localViewMode === 'card' ? 'primary' : 'secondary'"
            size="sm"
            @click="handleViewModeChange('card')"
          >
            <AppIcon name="grid" />
            卡片
          </AppButton>
        </el-button-group>
      </div>
    </div>

    <div class="permission-dimension-selector__content">
      <div v-if="loading" class="permission-dimension-selector__loading">
        <AppIcon name="refresh" class="pds-loading-icon" />
        <span>加载中...</span>
      </div>

      <div v-else-if="filteredDimensions.length === 0" class="permission-dimension-selector__empty">
        <el-empty description="暂无维度数据" />
      </div>

      <div
        v-else
        :class="contentClasses"
      >
        <div
          v-for="dimension in filteredDimensions"
          :key="dimension.id"
          :class="getDimensionClasses(dimension)"
          @click="handleDimensionClick(dimension)"
        >
          <div class="dimension-item__icon">
            <AppIcon :name="getIconName(dimension.icon)" :size="32" />
          </div>

          <div class="dimension-item__info">
            <div class="dimension-item__name">{{ dimension.name }}</div>
            <div v-if="dimension.description" class="dimension-item__description">
              {{ dimension.description }}
            </div>
            <div class="dimension-item__meta">
              <span class="dimension-item__rules">
                <AppIcon name="file" />
                {{ dimension.ruleCount || 0 }} 规则
              </span>
            </div>
          </div>

          <div v-if="isSelected(dimension)" class="dimension-item__check">
            <AppIcon name="check" :size="20" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import AppInput from '../AppInput/AppInput.vue'
import AppButton from '../AppButton/AppButton.vue'
import AppIcon from '../AppIcon/AppIcon.vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  dimensions: {
    type: Array,
    default: () => []
  },
  viewMode: {
    type: String,
    default: 'card',
    validator: (value) => ['list', 'card'].includes(value)
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'view-mode-change'])

const searchQuery = ref('')
const localViewMode = ref(props.viewMode)

const filteredDimensions = computed(() => {
  if (!searchQuery.value) {
    return props.dimensions
  }

  const query = searchQuery.value.toLowerCase().trim()
  return props.dimensions.filter(dimension => {
    return (
      dimension.name?.toLowerCase().includes(query) ||
      dimension.code?.toLowerCase().includes(query) ||
      dimension.description?.toLowerCase().includes(query)
    )
  })
})

const contentClasses = computed(() => [
  'permission-dimension-selector__dimensions',
  `permission-dimension-selector__dimensions--${localViewMode.value}`
])

const isSelected = (dimension) => {
  return props.modelValue === dimension.id
}

const getDimensionClasses = (dimension) => [
  'dimension-item',
  `dimension-item--${localViewMode.value}`,
  {
    'dimension-item--selected': isSelected(dimension),
    'dimension-item--disabled': dimension.disabled
  }
]

const getIconName = (iconName) => {
  const iconMap = {
    'product': 'box',
    'version': 'file',
    'domain': 'building',
    'sub-domain': 'folder',
    'setting': 'settings',
    'user': 'user',
    'calendar': 'calendar',
    'location': 'location',
    'coin': 'coin',
    'default': 'file'
  }

  return iconMap[iconName] || iconMap.default
}

const handleSearch = () => {
}

const handleViewModeChange = (mode) => {
  localViewMode.value = mode
  emit('view-mode-change', mode)
}

const handleDimensionClick = (dimension) => {
  if (dimension.disabled) return
  emit('update:modelValue', dimension.id)
}

watch(() => props.viewMode, (newVal) => {
  localViewMode.value = newVal
})
</script>

<style scoped>
.permission-dimension-selector {
  background: var(--color-bg-container, #fff);
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
}

.permission-dimension-selector__header {
  padding: var(--spacing-lg, 16px);
  border-bottom: 1px solid var(--color-border-secondary, #f0f0f0);
}

.permission-dimension-selector__title {
  margin: 0;
  font-size: var(--font-size-lg, 16px);
  font-weight: var(--font-weight-medium, 500);
  color: var(--color-text-primary, rgba(0, 0, 0, 0.85));
}

.permission-dimension-selector__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md, 12px);
  padding: var(--spacing-md, 12px) var(--spacing-lg, 16px);
  border-bottom: 1px solid var(--color-border-secondary, #f0f0f0);
}

.permission-dimension-selector__search {
  flex: 1;
  max-width: 400px;
}

.permission-dimension-selector__view-toggle {
  flex-shrink: 0;
}

.permission-dimension-selector__content {
  padding: var(--spacing-lg, 16px);
  min-height: 200px;
}

.permission-dimension-selector__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxl, 48px);
  color: var(--color-text-secondary, rgba(0, 0, 0, 0.45));
  gap: var(--spacing-sm, 8px);
}

.pds-loading-icon {
  animation: pds-rotating 1.2s linear infinite;
}

@keyframes pds-rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.permission-dimension-selector__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxl, 48px);
}

.permission-dimension-selector__dimensions {
  display: grid;
  gap: var(--spacing-md, 12px);
}

.permission-dimension-selector__dimensions--card {
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
}

.permission-dimension-selector__dimensions--list {
  grid-template-columns: 1fr;
}

.dimension-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md, 12px);
  padding: var(--spacing-md, 12px);
  background: var(--color-bg-primary, #fff);
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  transition: all 0.3s;
}

.dimension-item:hover:not(.dimension-item--disabled) {
  border-color: var(--color-primary, #1890ff);
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
  transform: translateY(-2px);
}

.dimension-item--selected {
  border-color: var(--color-primary, #1890ff);
  background: var(--color-primary-bg, #e6f7ff);
}

.dimension-item--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dimension-item--card {
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: var(--spacing-lg, 16px);
}

.dimension-item--list {
  flex-direction: row;
  align-items: center;
}

.dimension-item__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  background: var(--color-bg-secondary, #fafafa);
  border-radius: var(--radius-md, 8px);
  color: var(--color-primary, #1890ff);
  flex-shrink: 0;
}

.dimension-item--card .dimension-item__icon {
  width: 64px;
  height: 64px;
}

.dimension-item__info {
  flex: 1;
  min-width: 0;
}

.dimension-item--card .dimension-item__info {
  width: 100%;
}

.dimension-item__name {
  font-size: var(--font-size-base, 14px);
  font-weight: var(--font-weight-medium, 500);
  color: var(--color-text-primary, rgba(0, 0, 0, 0.85));
  margin-bottom: var(--spacing-xs, 4px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dimension-item--card .dimension-item__name {
  white-space: normal;
  word-break: break-word;
}

.dimension-item__description {
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-secondary, rgba(0, 0, 0, 0.45));
  margin-bottom: var(--spacing-xs, 4px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dimension-item--card .dimension-item__description {
  white-space: normal;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.dimension-item__meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  margin-top: var(--spacing-xs, 4px);
}

.dimension-item__rules {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs, 4px);
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-tertiary, rgba(0, 0, 0, 0.25));
}

.dimension-item__check {
  position: absolute;
  top: var(--spacing-sm, 8px);
  right: var(--spacing-sm, 8px);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: var(--color-primary, #1890ff);
  border-radius: 50%;
  color: #fff;
}

@media (max-width: 768px) {
  .permission-dimension-selector__toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .permission-dimension-selector__search {
    max-width: 100%;
  }

  .permission-dimension-selector__view-toggle {
    display: flex;
    justify-content: center;
  }

  .permission-dimension-selector__dimensions--card {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }
}

@media (max-width: 480px) {
  .permission-dimension-selector__dimensions--card {
    grid-template-columns: 1fr;
  }
}
</style>
