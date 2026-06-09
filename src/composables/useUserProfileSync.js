/**
 * useUserProfileSync - 用户资料变更实时同步器
 *
 * 解决问题：
 *   修改 display_name 后顶部菜单/头像首字母/UserMenu 等组件不立即刷新，
 *   用户误以为"没保存成功"或"账号被锁"。
 *
 * 设计：
 *   - 单一真相源：authStore.user.display_name
 *   - sync() 是前端乐观更新（保存成功立即调用），Vue reactivity 自动触发所有依赖组件重渲染
 *   - reload() 是从服务端拉取（admin 修改用户资料后，强制刷新当前登录用户视图）
 *
 * 使用示例：
 *   const sync = useUserProfileSync()
 *   const data = await authService.updateProfile({ display_name: '新名' })
 *   if (data.success) {
 *     sync.sync({ display_name: '新名', email: 'x@y.com' })
 *     message.profileUpdated()
 *   }
 *
 * @see docs/superpowers/specs/2026-06-09-user-lock-and-feedback-design.md
 */
import { useAuthStore } from '@/stores/authStore'

export function useUserProfileSync() {
  const authStore = useAuthStore()

  /**
   * 同步到 authStore（前端乐观更新）
   * @param {object} updates - 待同步字段，支持 display_name / email
   */
  function sync(updates) {
    if (!authStore.user) return
    if (!updates) return

    if ('display_name' in updates) {
      authStore.user.display_name = updates.display_name
    }
    if ('email' in updates) {
      authStore.user.email = updates.email
    }
  }

  /**
   * 从服务端重载（admin 改完用户资料后，被改用户需要 refresh）
   * @returns {Promise<boolean>} 是否成功
   */
  async function reload() {
    const ok = await authStore.loadFromCookie?.('refresh')
    return !!ok
  }

  return { sync, reload }
}