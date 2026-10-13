<template>
  <header class="app-header">
    <div class="app-header__left">
      <button
        v-if="showMenuButton"
        class="sidebar-toggle-btn"
        :class="{ 'is-active': menuOpen }"
        type="button"
        aria-label="切换侧栏"
        @click.stop="emit('menu-toggle')"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path v-if="!menuOpen" d="M3 4H13M3 8H13M3 12H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          <path v-else d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </button>

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
    // 兜底默认值（与 useInstanceInfo.FALLBACK_NAME 保持一致）。
    // 实际由 AppRootLayout 经 AppLayout 传入 useInstanceInfo().displayName（部署级可配），
    // 此处默认值仅在独立使用本组件时生效。
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
  },
  // [FIX 2026-10-13 移动端] 侧栏开关（汉堡按钮）。
  // 从 AppLayout 的 tabs 行上移到头部左侧，与 logo 同排 —— 对齐 GitHub/钉钉/
  // 飞书的成熟形态：汉堡紧邻品牌标识，优先级高于右侧用户区。
  // 按钮只负责渲染，状态与切换逻辑仍由 AppLayout 持有（受控组件）。
  showMenuButton: {
    type: Boolean,
    default: false
  },
  menuOpen: {
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
  'help-click',
  // [FIX 2026-10-13 移动端] 侧栏开关事件，与 showMenuButton 配套
  'menu-toggle'
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

/* [FIX 2026-10-13 移动端] 侧栏开关（汉堡）。样式原在 AppLayout，随按钮一并上移。
   class 名保持不变：AppLayout.handleOutsideClick 靠 closest 匹配该类名，
   判断点击是否落在按钮上，改名会导致「点按钮先关闭再重开」的错误序列。 */
.sidebar-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--el-text-color-secondary, #909399);
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 4px;
  flex-shrink: 0;
}

.sidebar-toggle-btn:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--yonyou-orange-600, #ea580c);
}

.sidebar-toggle-btn.is-active {
  background: var(--yonyou-orange-50, #fff7ed);
  color: var(--yonyou-orange-600, #ea580c);
}

.app-header__left {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  flex: 1;
  /* [FIX 2026-10-13 移动端] 允许收缩，否则 flex 子项默认 min-width:auto，
     logo 文字的 ellipsis 不会生效 */
  min-width: 0;
}

.app-header__logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  cursor: pointer;
  transition: opacity 0.2s;
  min-width: 0;
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
  /* [FIX 2026-10-13 移动端] 与 UserMenu.__name 同因：缺 nowrap 时 flex 收缩
     会把中文压成竖排单字。品牌名恒为单行，超长由 ellipsis 兜底。 */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-header__breadcrumb {
  margin-left: var(--spacing-md);
}

.app-header__right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
  justify-content: flex-end;
}

/* [FIX 2026-10-13 移动端] logo 文字不再在窄屏隐藏。
   实例展示名（PLATFORM_DISPLAY_NAME）是品牌标识而非装饰，隐藏等于让部署改名
   在手机端完全不可见；此时改为缩小字号 + ellipsis 兜底，短名完整显示、
   长名省略不破版。配套改动：移除了空置的 .app-header__center(flex:2)，
   它曾白占 33% 宽度，是文字被挤到只能隐藏的根因。 */
@media screen and (max-width: 768px) {
  .app-header {
    padding: 0 var(--spacing-md);
  }

  .app-header__left {
    gap: var(--spacing-sm, 8px);
  }

  .app-header__logo-text {
    font-size: var(--el-font-size-base, 14px);
  }
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
