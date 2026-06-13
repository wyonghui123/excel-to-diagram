/**
 * [TR-001] tabStore localStorage → sessionStorage 数据迁移脚本
 *
 * 启动时执行一次：检测旧 `tab-store` localStorage key，
 * 迁移到 sessionStorage 后清除旧 key。
 *
 * 保留 2 个 release 周期的向后兼容：旧 localStorage 仍可读（fallback）。
 */
import { logger } from '@/utils/logger'

const LOCAL_KEY = 'tab-store'
const SESSION_KEY = 'tab-store'

let migrated = false

export function migrateTabStoreLocalToSession() {
  if (migrated) return { migrated: true, already: true }
  if (typeof window === 'undefined') return { migrated: false, reason: 'no-window' }

  try {
    const local = window.localStorage.getItem(LOCAL_KEY)
    const session = window.sessionStorage.getItem(SESSION_KEY)

    if (local && !session) {
      // 迁移：local → session
      window.sessionStorage.setItem(SESSION_KEY, local)
      window.localStorage.removeItem(LOCAL_KEY)
      migrated = true
      logger.info('[migration] tab-store: localStorage → sessionStorage migrated')
      return { migrated: true, source: 'local', target: 'session' }
    } else if (local && session) {
      // 两边都有：清旧保新（避免冲突）
      window.localStorage.removeItem(LOCAL_KEY)
      migrated = true
      logger.info('[migration] tab-store: cleared stale localStorage (session exists)')
      return { migrated: true, source: 'both', action: 'cleared-local' }
    } else if (!local && !session) {
      // 无数据，无需迁移
      return { migrated: false, reason: 'no-data' }
    } else {
      // 只有 session（已在新版本上用过），无需迁移
      return { migrated: false, reason: 'session-only' }
    }
  } catch (e) {
    logger.warn('[migration] tab-store migration failed:', e)
    return { migrated: false, reason: 'error', error: String(e) }
  }
}

// 启动时自动执行（仅一次）
if (typeof window !== 'undefined') {
  // 等待 Pinia plugin 注册后再执行（避免顺序问题）
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      // 延迟到 Vue 应用挂载后
      setTimeout(migrateTabStoreLocalToSession, 100)
    })
  } else {
    setTimeout(migrateTabStoreLocalToSession, 100)
  }
}

export default migrateTabStoreLocalToSession
