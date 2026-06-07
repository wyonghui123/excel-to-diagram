<template>
  <AppLayout
    :show-sidebar="true"
    :show-tabs="true"
    :sidebar-items="navigationItems"
    :sidebar-active="currentRoute"
    :logo-text="'BIP应用架构管理'"
    @sidebar-select="handleNavigation"
    @logo-click="goHome"
    @user-command="handleUserCommand"
  >
    <slot />
  </AppLayout>

  <AccountSettingsDialog
    v-if="showAccountDialog"
    :visible="showAccountDialog"
    @close="showAccountDialog = false"
  />

  <div v-if="showOfflineBanner" class="offline-banner">
    <span>[WARNING] 离线模式：使用缓存数据</span>
    <button @click="refreshMenu">刷新</button>
  </div>

  <div v-if="showCacheError" class="cache-error-banner">
    <span>[X] 无法加载菜单，请检查网络连接后刷新重试</span>
    <button @click="refreshMenu">刷新</button>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { AppLayout } from '@/components/common'
import AccountSettingsDialog from '@/components/AccountSettingsDialog.vue'
import { useTabStore } from '@/stores/tabStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenuPermissions } from '@/composables/useMenuPermissions'
import { useMenuCache } from '@/composables/useMetaCache'
import { generateDynamicRoutes } from '@/router/dynamicRoutes'
import { resolveRoutePath } from '@/utils/routeTemplate'

const router = useRouter()
const route = useRoute()
const tabStore = useTabStore()
const authStore = useAuthStore()
const { accessibleMenus, loadMenuPermissions, reset: resetMenuPermissions } = useMenuPermissions()
const menuCache = useMenuCache()

const showAccountDialog = ref(false)
const menuLoadError = ref(null)

const USE_API_MENU = true

function mapMenuIcon(iconName) {
  const iconMap = {
    'Home': 'Home', 'Goods': 'Goods', 'Box': 'Box',
    'FolderOpened': 'FolderOpened', 'PictureFilled': 'PictureFilled',
    'Setting': 'Setting', 'User': 'User', 'Tools': 'Tools',
    'List': 'List', 'Timer': 'Timer', 'timer': 'Timer',
    'Document': 'Document', 'document': 'Document',
    'DataAnalysis': 'DataAnalysis', 'data-analysis': 'DataAnalysis',
    'Connection': 'Box', 'connection': 'Box',
    'Monitor': 'PictureFilled', 'monitor': 'PictureFilled',
    'Calendar': 'Document', 'calendar': 'Document',
    'Cpu': 'Setting', 'cpu': 'Setting',
    'Finished': 'CircleCheck', 'finished': 'CircleCheck',
    'Grid': 'Grid', 'grid': 'Grid',
    'Star': 'Star', 'Clock': 'Timer', 'clock': 'Timer',
    'Bell': 'Bell', 'bell': 'Bell',
    'Robot': 'Tools', 'robot': 'Tools',
    'Chart': 'DataAnalysis', 'chart': 'DataAnalysis',
    'Edit': 'Edit', 'edit': 'Edit',
    'Search': 'Search', 'search': 'Search',
    'Lock': 'Lock', 'lock': 'Lock',
    'Key': 'Key', 'key': 'Key',
    'App': 'Grid', 'app': 'Grid'
  }
  return iconMap[iconName] || iconName || 'Grid'
}

const apiNavigationItems = computed(() => {
  const menus = accessibleMenus.value
  if (!menus || !menus.length) return null

  return menus
    .filter(m => m.menu_code !== 'dashboard')
    .map(menu => ({
      key: menu.menu_code,
      label: menu.menu_name,
      icon: mapMenuIcon(menu.icon),
      color: menu.color,
      to: menu.menu_path || resolveRoutePath(menu),
      pageType: menu.page_type,
      objectTypes: menu.object_types,
      sortOrder: menu.sort_order ?? 999,
      children: (menu.children || []).map(child => ({
        key: child.menu_code,
        label: child.menu_name,
        icon: mapMenuIcon(child.icon),
        color: child.color,
        to: child.menu_path || resolveRoutePath(child),
        pageType: child.page_type,
        objectTypes: child.object_types,
      }))
    }))
    .sort((a, b) => a.sortOrder - b.sortOrder)
})

const cachedNavigationItems = computed(() => {
  const cached = menuCache.data.value
  if (!cached || !cached.length) return null
  
  return cached
    .filter(m => m.menu_code !== 'dashboard')
    .map(menu => ({
      key: menu.menu_code,
      label: menu.menu_name,
      icon: mapMenuIcon(menu.icon),
      color: menu.color,
      to: menu.menu_path || resolveRoutePath(menu),
      pageType: menu.page_type,
      objectTypes: menu.object_types,
      sortOrder: menu.sort_order ?? 999,
      children: (menu.children || []).map(child => ({
        key: child.menu_code,
        label: child.menu_name,
        icon: mapMenuIcon(child.icon),
        color: child.color,
        to: child.menu_path || resolveRoutePath(child),
        pageType: child.page_type,
        objectTypes: child.object_types,
      }))
    }))
    .sort((a, b) => a.sortOrder - b.sortOrder)
})

const navigationItems = computed(() => {
  if (USE_API_MENU && apiNavigationItems.value && apiNavigationItems.value.length > 0) {
    return apiNavigationItems.value
  }
  if (cachedNavigationItems.value && cachedNavigationItems.value.length > 0) {
    return cachedNavigationItems.value
  }
  return []
})

const showOfflineBanner = computed(() => {
  return menuCache.fromCache.value && menuCache.error.value !== null && navigationItems.value.length > 0
})

const showCacheError = computed(() => {
  return menuLoadError.value !== null && navigationItems.value.length === 0
})

const currentRoute = computed(() => {
  const path = route.path
  if (path === '/') return ''

  function findKey(items) {
    for (const item of items) {
      if (item.children) {
        for (const child of item.children) {
          if (child.to && path.startsWith(child.to)) return child.key
        }
      }
      if (item.to && path.startsWith(item.to)) return item.key
    }
    return ''
  }

  return findKey(navigationItems.value)
})

function _isHomeOnlyFallback(menus) {
  return menus && menus.length === 1 && menus[0]?.menu_code === 'home'
}

async function loadMenuWithCache() {
  try {
    await loadMenuPermissions()

    if (accessibleMenus.value && accessibleMenus.value.length > 0) {
      if (!_isHomeOnlyFallback(accessibleMenus.value)) {
        menuCache.setCache(accessibleMenus.value)
      }
      menuLoadError.value = null
    }
  } catch (e) {
    console.warn('[AppRootLayout] Failed to load menu from API:', e)
    menuLoadError.value = e

    const cached = menuCache.getCache()
    if (cached && cached.data && cached.data.length > 0 && !_isHomeOnlyFallback(cached.data)) {
      menuCache.data.value = cached.data
      menuCache.fromCache.value = true
    }
  }
}

async function refreshMenu() {
  menuLoadError.value = null
  menuCache.clearCache()
  resetMenuPermissions()
  await loadMenuWithCache()
}

onMounted(async () => {
  await loadMenuWithCache()
  await generateDynamicRoutes(router)
})

watch(() => authStore.isLoggedIn, async (loggedIn) => {
  if (loggedIn) {
    await refreshMenu()
    await generateDynamicRoutes(router)
  }
})

function handleNavigation(key) {
  const item = findItemByKey(navigationItems.value, key)

  if (item?.to) {
    const existingTab = tabStore.tabs.find(t => t.id === item.to)
    if (existingTab) {
      tabStore.switchTab(existingTab.id)
    }
    router.push(item.to)
  }
}

function findItemByKey(items, key) {
  for (const item of items) {
    if (item.key === key) return item
    if (item.children) {
      const found = findItemByKey(item.children, key)
      if (found) return found
    }
  }
  return null
}

function handleUserCommand(command) {
  if (command === 'account' || command === 'profile') {
    showAccountDialog.value = true
  } else if (command === 'logout') {
    authStore.logout()
    router.push('/')
  }
}

function goHome() {
  router.push('/')
}
</script>

<style scoped>
.offline-banner,
.cache-error-banner {
  position: fixed;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 16px;
  border-radius: 0 0 8px 8px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 12px;
  z-index: var(--z-index-tour);
}

.offline-banner {
  background: #fff3cd;
  border: 1px solid #ffc107;
  color: #856404;
}

.cache-error-banner {
  background: #f8d7da;
  border: 1px solid #f5c6cb;
  color: #721c24;
}

.offline-banner button,
.cache-error-banner button {
  padding: 4px 12px;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
}

.offline-banner button:hover,
.cache-error-banner button:hover {
  background: rgba(0, 0, 0, 0.05);
}
</style>
