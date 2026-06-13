/**
 * i18n - 最小可用的国际化工具（无外部依赖）
 *
 * [W4 PR-4.2] 自研实现，避免引入 vue-i18n 依赖
 *
 * 使用方式：
 *   import { t, setLocale, getLocale } from '@/i18n'
 *   t('common.save', '保存')         // 返回当前语言的值，找不到则用 default
 *   setLocale('en-US')                // 切换语言
 *   getLocale()                        // 'zh-CN' | 'en-US'
 *
 * 持久化：localStorage（key = 'app-locale'）
 * 默认语言：浏览器 navigator.language → 'zh-CN'
 */
import { ref, computed } from 'vue'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'

const STORAGE_KEY = 'app-locale'
const SUPPORTED = ['zh-CN', 'en-US']

const messages = {
  'zh-CN': zhCN,
  'en-US': enUS,
}

const stored = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY)) || null
const browser = (typeof navigator !== 'undefined' && navigator.language) || 'zh-CN'

function detectInitialLocale() {
  if (stored && SUPPORTED.includes(stored)) return stored
  if (browser.startsWith('en')) return 'en-US'
  return 'zh-CN'
}

const _current = ref(detectInitialLocale())

export const currentLocale = computed(() => _current.value)

export function getLocale() {
  return _current.value
}

export function setLocale(locale) {
  if (!SUPPORTED.includes(locale)) {
    console.warn(`[i18n] Unsupported locale: ${locale}, fallback to zh-CN`)
    locale = 'zh-CN'
  }
  _current.value = locale
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, locale)
  }
  // 触发 document.title 更新（如果有全局 title 策略可扩展）
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale
  }
}

/**
 * t - 翻译函数
 * @param {string} key - 翻译 key，点分路径如 'common.save'
 * @param {string} [defaultValue] - 默认值（当 key 不存在时返回）
 * @param {Object} [params] - 插值参数，如 { name: 'John' } 替换模板中的 {name}
 * @returns {string}
 */
export function t(key, defaultValue = '', params = null) {
  const msgs = messages[_current.value] || messages['zh-CN']
  const parts = key.split('.')
  let cur = msgs
  for (const part of parts) {
    if (cur && typeof cur === 'object' && part in cur) {
      cur = cur[part]
    } else {
      return interpolate(defaultValue || key, params)
    }
  }
  return interpolate(typeof cur === 'string' ? cur : (defaultValue || key), params)
}

/**
 * 简单插值：把 {key} 替换为 params[key]
 * 例如 "Hi {name}" + { name: 'Tom' } => "Hi Tom"
 */
function interpolate(template, params) {
  if (!params || typeof template !== 'string') return template
  return template.replace(/\{(\w+)\}/g, (match, key) => {
    return key in params ? String(params[key]) : match
  })
}

export const SUPPORTED_LOCALES = SUPPORTED

export default {
  t,
  setLocale,
  getLocale,
  currentLocale,
  SUPPORTED_LOCALES,
}
