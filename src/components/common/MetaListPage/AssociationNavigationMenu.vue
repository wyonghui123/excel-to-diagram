<template>
  <el-dropdown
    v-if="visible"
    trigger="click"
    @command="onNavigate"
  >
    <el-button type="default" size="small">
      <el-icon><Link /></el-icon>
      关联导航
      <el-icon class="el-icon--right"><ArrowDown /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu class="assoc-nav-menu">
        <el-dropdown-item
          v-for="assoc in associations"
          :key="assoc.name"
          :command="assoc"
          :disabled="loading"
        >
          <el-icon :size="14">
            <component :is="getIcon(assoc)" />
          </el-icon>
          <span class="assoc-nav-label">{{ getLabel(assoc) }}</span>
          <span v-if="assoc._count !== undefined" class="assoc-nav-count">
            ({{ assoc._count }})
          </span>
        </el-dropdown-item>
        <div v-if="associations.length === 0" class="assoc-nav-empty">
          无可用关联
        </div>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed, watch, ref } from 'vue'
import { ArrowDown, Link, User, Key, Lock, UserFilled, Collection, Document } from '@element-plus/icons-vue'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'

const ICON_COMPONENT_MAP = {
  User,
  Key,
  Lock,
  UserFilled,
  Collection,
  Document,
  Link,
}

const props = defineProps({
  associations: {
    type: Array,
    default: () => []
  },
  selectedIds: {
    type: Set,
    default: () => new Set()
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['navigate'])

const visible = computed(() => {
  return props.selectedIds.size > 0 && props.associations.length > 0
})

function getIcon(assoc) {
  const iconName = assoc.navigation?.icon || 'Link'
  return ICON_COMPONENT_MAP[iconName] || Link
}

function getLabel(assoc) {
  return assoc.navigation?.label || assoc.label || assoc.name || ''
}

function onNavigate(assoc) {
  emit('navigate', assoc)
}
</script>

<style scoped>
.assoc-nav-menu {
  min-width: 180px;
}

.assoc-nav-label {
  margin-left: 4px;
}

.assoc-nav-count {
  margin-left: 4px;
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;
}

.assoc-nav-empty {
  padding: 8px 16px;
  color: var(--el-text-color-secondary, #909399);
  font-size: 13px;
  text-align: center;
}
</style>
