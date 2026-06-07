import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * App Store（精简版）
 *
 * 已拆分的域：
 * - Tab 管理 → useTabStore (stores/tabStore.ts)
 * - 侧边栏 → useSidebarStore (stores/sidebarStore.ts)
 * - 通知 → useNotificationStore (stores/notificationStore.ts)
 *
 * 本 store 仅保留：用户状态、搜索、收藏夹、最近访问
 * 这些功能目前仅被 dev 测试页面使用，生产代码不依赖
 */

export interface User {
  id: string
  name: string
  email?: string
  avatar?: string
  role?: string
}

export interface FavoriteItem {
  id: string
  label: string
  path?: string
  icon?: string
  type?: 'page' | 'record' | 'document'
  metadata?: Record<string, any>
}

export interface RecentItem {
  id: string
  label: string
  path?: string
  icon?: string
  type?: 'page' | 'record' | 'document'
  visitedAt: string
  metadata?: Record<string, any>
}

export const useAppStore = defineStore('app', () => {
  // [FR-006] 不持久化 currentUser (走 cookie + 单独 authStore)
  //  - searchQuery/searchResults 瞬态
  //  - favorites + maxFavorites 持久化 (用户收藏,小,跨会话保留)
  //  - recentItems 较大且频繁变化,不持久化
  const currentUser = ref<User | null>(null)

  const searchQuery = ref('')
  const searchResults = ref<any[]>([])

  const favorites = ref<FavoriteItem[]>([])
  const maxFavorites = ref(20)

  const recentItems = ref<RecentItem[]>([])
  const maxRecentItems = ref(30)

  // Actions - 用户
  function setUser(user: User | null) {
    currentUser.value = user
  }

  function logout() {
    currentUser.value = null
  }

  // Actions - 搜索
  function setSearchQuery(query: string) {
    searchQuery.value = query
  }

  function setSearchResults(results: any[]) {
    searchResults.value = results
  }

  // Actions - 收藏夹
  function addFavorite(item: Omit<FavoriteItem, 'id'> & { id?: string }) {
    const itemId = item.id || item.path || String(Date.now())

    const existing = favorites.value.find(f => f.id === itemId)
    if (existing) return

    if (favorites.value.length >= maxFavorites.value) {
      favorites.value.pop()
    }

    favorites.value.unshift({
      id: itemId,
      label: item.label,
      path: item.path,
      icon: item.icon,
      type: item.type || 'page',
      metadata: item.metadata
    })
  }

  function removeFavorite(id: string) {
    const index = favorites.value.findIndex(f => f.id === id)
    if (index !== -1) {
      favorites.value.splice(index, 1)
    }
  }

  function isFavorite(id: string): boolean {
    return favorites.value.some(f => f.id === id)
  }

  // Actions - 最近访问
  function addRecentItem(item: Omit<RecentItem, 'id' | 'visitedAt'> & { id?: string }) {
    const itemId = item.id || item.path || String(Date.now())

    const existingIndex = recentItems.value.findIndex(r => r.id === itemId)
    if (existingIndex !== -1) {
      recentItems.value.splice(existingIndex, 1)
    }

    recentItems.value.unshift({
      id: itemId,
      label: item.label,
      path: item.path,
      icon: item.icon,
      type: item.type || 'page',
      visitedAt: new Date().toISOString(),
      metadata: item.metadata
    })

    if (recentItems.value.length > maxRecentItems.value) {
      recentItems.value = recentItems.value.slice(0, maxRecentItems.value)
    }
  }

  function clearRecentItems() {
    recentItems.value = []
  }

  // Getters
  const favoriteCount = computed(() => favorites.value.length)
  const recentCount = computed(() => recentItems.value.length)

  return {
    currentUser,
    searchQuery,
    searchResults,
    favorites,
    maxFavorites,
    recentItems,
    maxRecentItems,
    setUser,
    logout,
    setSearchQuery,
    setSearchResults,
    addFavorite,
    removeFavorite,
    isFavorite,
    addRecentItem,
    clearRecentItems,
    favoriteCount,
    recentCount
  }
}, {
  // [FR-006] 持久化白名单: 仅 favorites + maxFavorites
  //  - 升级到 v4 语法 (pick 替代 paths)
  //  - 从 sessionStorage 改为 localStorage (跨标签页)
  //  - 移除 recentItems (较大且频繁变化)
  persist: {
    key: 'app-store',
    storage: localStorage,
    pick: ['favorites', 'maxFavorites']
  }
})

export default useAppStore
