<template>
  <div class="app-side-nav">
    <nav class="nav">
      <div v-for="item in items" :key="item.key" class="nav-group">
        <div
          class="nav-item"
          :class="{ active: isItemActive(item) }"
          @click="handleItemClick(item)"
        >
          <el-icon v-if="item.icon" class="nav-icon"><component :is="iconMap[item.icon]" /></el-icon>
          <span class="label">{{ item.label }}</span>
          <el-icon v-if="item.children?.length" class="arrow-icon">
            <ArrowDown v-if="expandedKeys.includes(item.key)" />
            <ArrowRight v-else />
          </el-icon>
        </div>

        <div v-if="item.children?.length && expandedKeys.includes(item.key)" class="nav-children">
          <div
            v-for="child in item.children"
            :key="child.key"
            class="nav-item child"
            :class="{ active: modelValue === child.key }"
            @click="handleItemClick(child)"
          >
            <el-icon v-if="child.icon" class="nav-icon child-icon"><component :is="iconMap[child.icon]" /></el-icon>
            <span class="label">{{ child.label }}</span>
          </div>
        </div>
      </div>
    </nav>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import {
  DataAnalysis,
  Document,
  Goods,
  Setting,
  User,
  List,
  ArrowDown,
  ArrowRight,
  HomeFilled,
  FolderOpened,
  PictureFilled,
  Box,
  Tools,
  Timer,
  Bell,
  Star,
  Grid,
  Edit,
  Search,
  Lock,
  Key,
  CircleCheck
} from '@element-plus/icons-vue'

const iconMap = {
  Home: HomeFilled,
  FolderOpened,
  PictureFilled,
  Box,
  Setting,
  User,
  Tools,
  List,
  DataAnalysis,
  Document,
  Goods,
  Timer,
  'timer': Timer,
  Bell,
  'bell': Bell,
  Star,
  'star': Star,
  Grid,
  'grid': Grid,
  Edit,
  'edit': Edit,
  Search,
  'search': Search,
  Lock,
  'lock': Lock,
  Key,
  'key': Key,
  CircleCheck,
  'circle-check': CircleCheck
}

const props = defineProps({
  items: { type: Array, required: true },
  modelValue: { type: [String, Number], required: true }
})

const emit = defineEmits(['update:modelValue'])

const expandedKeys = ref([])

function isItemActive(item) {
  if (props.modelValue === item.key) return true
  if (item.children) {
    return item.children.some(child => props.modelValue === child.key)
  }
  return false
}

watch(() => props.modelValue, (newVal) => {
  for (const item of props.items) {
    if (item.children?.some(child => child.key === newVal)) {
      if (!expandedKeys.value.includes(item.key)) {
        expandedKeys.value.push(item.key)
      }
      break
    }
  }
}, { immediate: true })

function handleItemClick(item) {
  if (item.children?.length) {
    const idx = expandedKeys.value.indexOf(item.key)
    if (idx >= 0) {
      expandedKeys.value.splice(idx, 1)
    } else {
      expandedKeys.value.push(item.key)
    }
    return
  }
  if (item.to) {
    emit('update:modelValue', item.key)
  }
}
</script>

<style scoped>
.app-side-nav {
  width: 100%;
  height: 100%;
  background: var(--color-bg-primary);
  overflow-y: auto;
  overflow-x: hidden;
}

.nav {
  padding: var(--spacing-sm) 0;
}

.nav-group {
  margin-bottom: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-lg);
  cursor: pointer;
  transition: all var(--transition-normal);
  border-left: 2px solid transparent;
  color: var(--color-text-secondary);
  background: transparent;
  border-right: none;
  border-top: none;
  border-bottom: none;
  font-size: var(--font-size-sm);
  width: 100%;
  text-align: left;
}

.nav-item:hover {
  color: var(--color-text-primary);
  background: transparent;
}

.nav-item.active {
  border-left-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
  background: transparent;
}

.nav-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.child-icon {
  font-size: 14px;
}

.nav-item .label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.arrow-icon {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
  transition: transform 0.2s;
}

.nav-children {
  padding-left: 20px;
}

.nav-item.child {
  padding: var(--spacing-xs) var(--spacing-lg);
  font-size: var(--font-size-sm);
}
</style>