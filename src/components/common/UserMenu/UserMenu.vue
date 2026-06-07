<template>
  <div class="user-menu">
    <el-dropdown trigger="click" :teleported="false" popper-class="app-tooltip-popper" @command="handleCommand">
      <div class="user-menu__trigger">
        <el-avatar
          :src="user?.avatar"
          :size="32"
          class="user-menu__avatar"
        >
          {{ user?.name?.charAt(0) || 'U' }}
        </el-avatar>
        <span v-if="showName" class="user-menu__name">
          {{ user?.name || '用户' }}
        </span>
        <el-icon class="user-menu__arrow">
          <ArrowDown />
        </el-icon>
      </div>

      <template #dropdown>
        <div class="user-menu__header" v-if="showHeader">
          <el-avatar :src="user?.avatar" :size="40">
            {{ user?.name?.charAt(0) || 'U' }}
          </el-avatar>
          <div class="user-menu__info">
            <div class="user-menu__username">{{ user?.name }}</div>
            <div v-if="user?.email" class="user-menu__email">
              {{ user.email }}
            </div>
            <el-tag v-if="user?.role" size="small" type="warning">
              {{ user.role }}
            </el-tag>
          </div>
        </div>

        <el-dropdown-menu class="user-menu__list">
          <el-dropdown-item
            v-for="item in menuItems"
            :key="item.key"
            :command="item.key"
            :divided="item.divided"
            :disabled="item.disabled"
            :danger="item.danger"
          >
            <el-icon v-if="item.icon">
              <component :is="item.icon" />
            </el-icon>
            {{ item.label }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { ArrowDown } from '@element-plus/icons-vue'

defineProps({
  user: {
    type: Object,
    default: () => ({})
  },
  menuItems: {
    type: Array,
    default: () => [
      { key: 'account', label: '账户设置', icon: 'User', divided: true },
      { key: 'logout', label: '退出登录', icon: 'SwitchButton', danger: true }
    ]
  },
  showName: {
    type: Boolean,
    default: false
  },
  showHeader: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['command'])

function handleCommand(key) {
  emit('command', key)
}
</script>

<style scoped>
.user-menu {
  display: inline-flex;
  align-items: center;
}

.user-menu__trigger {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--spacing-sm);
  cursor: pointer;
  transition: background-color 0.2s;
}

.user-menu__trigger:hover {
  background: var(--fill-color-light, #f5f7fa);
}

.user-menu__avatar {
  flex-shrink: 0;
}

.user-menu__name {
  font-size: var(--el-font-size-base, 14px);
  color: var(--el-text-color-regular, #606266);
}

.user-menu__arrow {
  color: var(--el-text-color-placeholder, #a0a8b0);
  font-size: 12px;
}

.user-menu__header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--el-border-color, #e5e6eb);
}

.user-menu__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-menu__username {
  font-size: var(--el-font-size-base, 14px);
  font-weight: 500;
  color: var(--el-text-color-primary, #1d2129);
}

.user-menu__email {
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-secondary, #86909c);
}

.user-menu__list {
  min-width: 160px;
}

.user-menu__list .el-dropdown-menu__item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
}

.user-menu__list .el-icon {
  margin-right: 0;
}
</style>
