<template>
  <header class="app-header">
    <div class="app-header__left">
      <div class="app-header__logo" @click="handleLogoClick">
        <svg v-if="!logoUrl" class="app-header__logo-icon" width="28" height="28" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="32" height="32" rx="6" fill="var(--yonyou-orange-600, #ea580c)"/>
          <rect x="4" y="5" width="10" height="7" rx="1.5" fill="white" fill-opacity="0.9"/>
          <rect x="18" y="5" width="10" height="7" rx="1.5" fill="white" fill-opacity="0.9"/>
          <rect x="9" y="17" width="14" height="10" rx="2" fill="white" fill-opacity="0.9"/>
          <path d="M9 12V15L16 19" stroke="white" stroke-width="1.3" stroke-linecap="round"/>
          <path d="M23 12V15L16 19" stroke="white" stroke-width="1.3" stroke-linecap="round"/>
        </svg>
        <img v-if="logoUrl" :src="logoUrl" :alt="logoAlt" class="app-header__logo-img" />
        <span class="app-header__logo-text">{{ logoText }}</span>
      </div>

      <BreadcrumbNav
        v-if="breadcrumbs.length > 0"
        :items="breadcrumbs"
        class="app-header__breadcrumb"
      />
    </div>

    <div class="app-header__center">
    </div>

    <div class="app-header__right">
      <UserMenu
        :user="currentUser"
        :menu-items="userMenuItems"
        show-name
        @command="handleUserCommand"
      />
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/appStore'
import { useAuthStore } from '@/stores/authStore'
import { BreadcrumbNav } from '@/components/common/BreadcrumbNav'
import { UserMenu } from '@/components/common/UserMenu'

const props = defineProps({
  logoUrl: {
    type: String,
    default: ''
  },
  logoAlt: {
    type: String,
    default: 'Logo'
  },
  logoText: {
    type: String,
    default: 'BIP应用架构管理'
  },
  breadcrumbs: {
    type: Array,
    default: () => []
  },
  userMenuItems: {
    type: Array,
    default: () => [
      { key: 'profile', label: '个人设置', icon: 'User' },
      { key: 'help', label: '帮助中心', icon: 'QuestionFilled', divided: true },
      { key: 'logout', label: '退出登录', icon: 'SwitchButton', danger: true, divided: true }
    ]
  },
  isHelpActive: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'logo-click',
  'notification-click',
  'search',
  'suggestion-click',
  'user-command',
  'ai-click',
  'favorites-click',
  'recent-click',
  'help-click'
])

const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

const currentUser = computed(() => {
  const user = authStore.user
  if (!user) return null
  return {
    id: user.id,
    name: user.display_name || user.username || '用户',
    email: user.email,
    avatar: user.avatar,
    role: user.roles?.[0]?.name || user.role
  }
})

function handleLogoClick() {
  emit('logo-click')
  router.push('/')
}

function handleUserCommand(key) {
  emit('user-command', key)
}
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--spacing-lg);
  background: #fff;
  border-bottom: 1px solid var(--el-border-color, #e5e6eb);
}

.app-header__left {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  flex: 1;
}

.app-header__logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  cursor: pointer;
  transition: opacity 0.2s;
}

.app-header__logo:hover {
  opacity: 0.8;
}

.app-header__logo-img {
  height: 32px;
  width: auto;
}

.app-header__logo-icon {
  flex-shrink: 0;
}

.app-header__logo-text {
  font-size: var(--el-font-size-large, 16px);
  font-weight: 600;
  color: var(--yonyou-orange-600, #ea580c);
}

.app-header__breadcrumb {
  margin-left: var(--spacing-md);
}

.app-header__center {
  flex: 2;
  display: flex;
  justify-content: center;
}

.app-header__right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
  justify-content: flex-end;
}

.app-header__notification-btn {
  border: none;
  background: transparent;
  color: var(--el-text-color-regular, #606266);
}

.app-header__notification-btn:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--yonyou-orange-600, #ea580c);
}

.app-header__ai-btn,
.app-header__favorites-btn,
.app-header__recent-btn {
  border: none;
  background: transparent;
  color: var(--el-text-color-regular, #606266);
}

.app-header__ai-btn:hover,
.app-header__favorites-btn:hover,
.app-header__recent-btn:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--yonyou-orange-600, #ea580c);
}

.app-header__ai-btn {
  color: var(--yonyou-orange-600, #ea580c);
}
</style>
