<template>
  <div class="app-tabs">
    <div class="app-tabs__list" ref="tabsListRef">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['app-tabs__item', { 'is-active': activeTab === tab.id }]"
        @click="handleTabClick(tab)"
      >
        <el-tooltip
          :content="tab.label"
          placement="bottom"
          :show-after="300"
          :teleported="false"
          popper-class="app-tooltip-popper"
        >
          <span class="app-tabs__label app-tabs__label--ellipsis">{{ tab.label }}</span>
        </el-tooltip>
        <span v-if="tab.badge" class="app-tabs__badge">{{ tab.badge }}</span>
        <button
          v-if="tab.closable !== false && !tab.pinned"
          class="app-tabs__close"
          @click.stop="handleTabClose(tab)"
        >
          <AppIcon name="close" size="12" />
        </button>
      </button>
    </div>

    <div v-if="overflowTabs.length > 0" class="app-tabs__more">
      <el-dropdown trigger="click" :teleported="false" popper-class="app-tooltip-popper" @command="handleMoreCommand">
        <button class="app-tabs__more-btn">
          <AppIcon name="more" size="14" />
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="tab in overflowTabs"
              :key="tab.id"
              :command="tab.id"
              :divided="tab.closable !== false && !tab.pinned"
            >
              {{ tab.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { AppIcon } from '@/components/common/AppIcon'

const MAX_VISIBLE_TABS = 8

const props = defineProps({
  tabs: {
    type: Array,
    default: () => []
  },
  modelValue: {
    type: String,
    default: null
  },
  maxTabs: {
    type: Number,
    default: MAX_VISIBLE_TABS
  }
})

const emit = defineEmits(['update:modelValue', 'tab-click', 'tab-close'])

const tabsListRef = ref(null)
const visibleTabs = computed(() => props.tabs.slice(0, props.maxTabs))
const overflowTabs = computed(() => props.tabs.slice(props.maxTabs))
const activeTab = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

function handleTabClick(tab) {
  activeTab.value = tab.id
  emit('tab-click', tab)
}

function handleTabClose(tab) {
  emit('tab-close', tab.id)
}

function handleMoreCommand(tabId) {
  emit('update:modelValue', tabId)
}
</script>

<style scoped>
.app-tabs {
  display: flex;
  align-items: center;
  height: 40px;
  gap: var(--spacing-xs);
}

.app-tabs__list {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  overflow-x: auto;
}

.app-tabs__list::-webkit-scrollbar {
  display: none;
}

.app-tabs__item {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--el-font-size-base, 14px);
  color: var(--el-text-color-regular, #606266);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.app-tabs__item:hover {
  color: var(--yonyou-orange-600, #ea580c);
  background: rgba(234, 88, 12, 0.06);
}

.app-tabs__item.is-active {
  color: var(--yonyou-orange-600, #ea580c);
  background: rgba(234, 88, 12, 0.06);
  font-weight: 500;
}

.app-tabs__label {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-tabs__label--ellipsis {
  display: inline-block;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-tabs__badge {
  padding: 0 4px;
  font-size: 10px;
  background: var(--yonyou-orange-100, #ffedd5);
  color: var(--yonyou-orange-700, #c2410c);
  border-radius: 999px;
}

.app-tabs__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 2px;
  color: var(--el-text-color-placeholder, #a0a8b0);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.app-tabs__item:hover .app-tabs__close {
  opacity: 1;
}

.app-tabs__close:hover {
  background: rgba(0, 0, 0, 0.08);
  color: var(--el-text-color-primary, #1d2129);
}

.app-tabs__more {
  flex-shrink: 0;
}

.app-tabs__more-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--el-text-color-regular, #606266);
  cursor: pointer;
}

.app-tabs__more-btn:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--yonyou-orange-600, #ea580c);
}
</style>
