// [NEW BMRD 2026-06-14] E34 解锁: i18n locale composable
// 提供:
// - locale: ref (zh-CN / en-US)
// - elementPlusLocale: ref (Element Plus locale object, 响应式)
// - setLocale(locale): 切换 locale + 持久化 + 同步到后端 user profile
// - availableLocales: 支持的语言列表
import { ref, computed, watch } from 'vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import enUs from 'element-plus/es/locale/lang/en'

const LOCALE_STORAGE_KEY = 'app_locale'
const USER_LOCALE_KEY = 'user_locale'
const DEFAULT_LOCALE = 'zh-CN'

// 支持的语言
export const AVAILABLE_LOCALES = [
  { code: 'zh-CN', label: '简体中文', elementPlusLocale: zhCn },
  { code: 'en-US', label: 'English', elementPlusLocale: enUs },
]

const _locale = ref(localStorage.getItem(LOCALE_STORAGE_KEY) || DEFAULT_LOCALE)

/**
 * 同步 locale 到后端 user profile (user.locale 字段)
 * 静默失败: 不影响 UI
 */
async function syncLocaleToServer(locale) {
  try {
    // 后端会自动从 session 读 user, 只需 PUT/PATCH 当前 user
    // 端点路径参考 user_api.py:412 preference_fields
    const res = await fetch('/api/v2/bo/user/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ locale }),
    })
    if (!res.ok) {
      console.debug('[useLocale] sync to server failed:', res.status)
    }
  } catch (e) {
    console.debug('[useLocale] sync to server error:', e)
  }
}

/**
 * 从 localStorage 恢复, 优先 user.locale (如果 API 已加载)
 */
function getInitialLocale() {
  return localStorage.getItem(LOCALE_STORAGE_KEY) || DEFAULT_LOCALE
}

export function useLocale() {
  const elementPlusLocale = computed(() => {
    const found = AVAILABLE_LOCALES.find(l => l.code === _locale.value)
    return found ? found.elementPlusLocale : AVAILABLE_LOCALES[0].elementPlusLocale
  })

  const setLocale = (newLocale) => {
    if (!AVAILABLE_LOCALES.find(l => l.code === newLocale)) {
      console.warn('[useLocale] unsupported locale:', newLocale)
      return
    }
    _locale.value = newLocale
    localStorage.setItem(LOCALE_STORAGE_KEY, newLocale)
    // 后台同步到服务器 (不阻塞 UI)
    syncLocaleToServer(newLocale)
  }

  // 监听 locale 变化, 自动持久化
  watch(_locale, (newVal) => {
    localStorage.setItem(LOCALE_STORAGE_KEY, newVal)
    document.documentElement.setAttribute('lang', newVal)
  }, { immediate: true })

  return {
    locale: _locale,
    elementPlusLocale,
    setLocale,
    availableLocales: AVAILABLE_LOCALES,
  }
}
