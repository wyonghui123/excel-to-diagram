import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiV1 } from '@/utils/httpClient'

// [FR-006] 持久化用户偏好: locale / timezone / 时间格式
//  - 不持久化 `loaded` (运行时状态,服务端响应后置 true)
export const useUserPreferencesStore = defineStore('userPreferences', () => {
  const locale = ref('zh-CN')
  const timezone = ref('Asia/Shanghai')
  const dateStyle = ref('medium')
  const timeStyle = ref('short')
  const hourCycle = ref(24)
  const loaded = ref(false)

  function loadFromUser(userData) {
    if (!userData) return
    locale.value = userData.locale || 'zh-CN'
    timezone.value = userData.timezone || 'Asia/Shanghai'
    dateStyle.value = userData.date_style || 'medium'
    timeStyle.value = userData.time_style || 'short'
    hourCycle.value = userData.hour_cycle || 24
    loaded.value = true
  }

  async function fetchFromServer() {
    try {
      const result = await apiV1.get('/users/me')
      if (result.success && result.data) {
        loadFromUser(result.data)
      }
    } catch (e) {
      console.error('[UserPreferences] Fetch failed:', e)
    }
  }

  async function save(updates) {
    try {
      const result = await apiV1.put('/users/me', {
        locale: updates.locale,
        timezone: updates.timezone,
        date_style: updates.dateStyle,
        time_style: updates.timeStyle,
        hour_cycle: updates.hourCycle,
      })
      if (result.success) {
        if (updates.locale !== undefined) locale.value = updates.locale
        if (updates.timezone !== undefined) timezone.value = updates.timezone
        if (updates.dateStyle !== undefined) dateStyle.value = updates.dateStyle
        if (updates.timeStyle !== undefined) timeStyle.value = updates.timeStyle
        if (updates.hourCycle !== undefined) hourCycle.value = updates.hourCycle
        return true
      }
      return false
    } catch (e) {
      console.error('[UserPreferences] Save failed:', e)
      return false
    }
  }

  return {
    locale,
    timezone,
    dateStyle,
    timeStyle,
    hourCycle,
    loaded,
    loadFromUser,
    fetchFromServer,
    save,
  }
}, {
  // [FR-006] 持久化白名单 (排除 `loaded` 运行时标记)
  persist: {
    pick: ['locale', 'timezone', 'dateStyle', 'timeStyle', 'hourCycle']
  }
})
