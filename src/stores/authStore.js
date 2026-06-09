import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useUserPreferencesStore } from '@/stores/userPreferences'
import * as authService from '@/services/authService'
import { logger } from '@/utils/logger'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(false)
  const error = ref('')
  const mustChangePassword = ref(false)
  const sessionReady = ref(false)
  const activeDataPermissionHint = ref(null)

  function setActiveDataPermissionHint(hint) {
    activeDataPermissionHint.value = hint
  }

  const isLoggedIn = computed(() => !!user.value)
  const isAdmin = computed(() => {
    if (!user.value) return false
    // Prefer server-provided is_admin field
    if (typeof user.value.is_admin === 'boolean') return user.value.is_admin
    // Fallback: derive from permissions/roles
    if (user.value.permissions?.includes('*')) return true
    const roles = user.value.roles || []
    for (const role of roles) {
      if (typeof role === 'object' && role?.is_super_admin) {
        return true
      }
    }
    return false
  })
  const userDisplayName = computed(
    () => user.value?.display_name || user.value?.username || ''
  )

  /**
   * 从 Cookie 恢复/刷新会话（合并原 restoreSession + fetchCurrentUser）
   *
   * @param {'restore'|'refresh'} mode
   *   - 'restore': 应用启动时调用，无论成功失败都设 sessionReady=true
   *   - 'refresh': 路由守卫等场景调用，不翻转 sessionReady
   * @returns {Promise<boolean>} 是否成功获取用户信息
   */
  async function loadFromCookie(mode = 'restore') {
    const r = await authService.getCurrentUser()
    if (r.success && r.data) {
      user.value = r.data
      if (mode === 'restore') {
        sessionReady.value = true
      }
      try {
        useUserPreferencesStore().loadFromUser(r.data)
      } catch (e) {
        // pref store not yet initialized
      }
      return true
    }
    user.value = null
    if (mode === 'restore') {
      sessionReady.value = true
    }
    if (r.message && r.message.includes('Token')) {
      logger.debug('[Auth] Session expired, clearing')
    }
    return false
  }

  async function login(username, password) {
    loading.value = true
    error.value = ''
    const r = await authService.login(username, password)
    if (r.success) {
      user.value = r.data.user
      mustChangePassword.value = r.data.must_change_password || false
      loading.value = false
      return true
    } else {
      error.value = r.message || '登录失败'
      loading.value = false
      return false
    }
  }

  /**
   * [FIX v1.0.4 2026-06-09] 退出登录 - 彻底清空所有状态
   *
   * 修复场景: admin 退出后用 TEST60 登录, 看到 admin 的菜单
   * 根因:
   *   1. 原版只 user.value = null, 其他 ref (loading/error/sessionReady) 残留
   *   2. router.push 抢跑 (async logout 未 await)
   *   3. sessionStorage 中 useMultiObjectPage 缓存的 BO state 未清
   * 修复:
   *   1. 显式重置所有 ref 到初始值
   *   2. 清空 sessionStorage (项目命名空间)
   *   3. 调用方必须 await 本函数
   */
  async function logout() {
    try {
      await authService.logout()
    } catch (e) {
      logger.warn('[authStore.logout] authService.logout failed:', e)
    }
    // 1. 清空 auth store 全部 state
    user.value = null
    loading.value = false
    error.value = ''
    mustChangePassword.value = false
    sessionReady.value = false
    activeDataPermissionHint.value = null
    // 2. 清空 sessionStorage (项目命名空间, 避免误删用户其他站点数据)
    try {
      // useMultiObjectPage 缓存的 page state
      sessionStorage.removeItem('archManagerStateBeforeDiagram')
      sessionStorage.removeItem('returningFromDiagram')
      // useVersionContext 缓存的 LAST_CONTEXT
      sessionStorage.removeItem('arch-context-last')
      // 可能存在的 user 缓存
      sessionStorage.removeItem('auth_user_cache')
      // [NOTE] localStorage 中 FREQUENT_PRODUCTS 是用户偏好, 不清
    } catch (e) {
      logger.warn('[authStore.logout] clear storage failed:', e)
    }
  }

  async function changePassword(oldPassword, newPassword) {
    const r = await authService.changePassword(oldPassword, newPassword)
    if (r.success) {
      mustChangePassword.value = false
    }
    return r
  }

  async function updateProfile(profileData) {
    const r = await authService.updateProfile(profileData)
    if (r.success && r.data && r.data.user_id) {
      // 重新拉取当前用户, 拿最新值
      const cur = await authService.getCurrentUser()
      if (cur.success && cur.data) {
        user.value = cur.data
      }
    }
    return r
  }

  /**
   * 返回认证请求头（Cookie 模式下为空对象）
   *
   * Cookie 由浏览器自动携带（http-only 模式），无需手动设置 Authorization 头。
   * 保留此方法以维持类型一致性，调用方可安全展开 `...authStore.getAuthHeaders()`。
   *
   * @returns {Object} 当前始终返回空对象
   */
  function getAuthHeaders() {
    return {}
  }

  function hasPermission(perm) {
    if (!user.value) return false
    if (typeof perm !== 'string') return false
    if (perm === '*') return isAdmin.value
    const perms = user.value.permissions || []
    if (perms.includes('*')) return true
    return perms.includes(perm)
  }

  return {
    user,
    loading,
    error,
    mustChangePassword,
    sessionReady,
    isLoggedIn,
    isAdmin,
    hasPermission,
    userDisplayName,
    login,
    logout,
    loadFromCookie,
    changePassword,
    updateProfile,
    getAuthHeaders,
    activeDataPermissionHint,
    setActiveDataPermissionHint,
  }
}, {
  persist: {
    key: 'app-auth',
    pick: ['user'],
  }
})
