/**
 * useInstanceInfo - 本实例展示信息（左上角名称 / 登录页标题的数据源）
 *
 * 数据源: GET /api/v2/meta/instance（无鉴权，登录页在拿到 token 之前也要用）
 * 取值优先级由后端裁定，这里只负责取回 + 失败兜底：
 *   PLATFORM_DISPLAY_NAME 环境变量 > 恰好 1 个 app 时用其 app.yaml name > 默认值
 *
 * module-level 单例（与 useMenuPermissions 同模式）: 多个组件共享同一次请求，
 * 避免 AppRootLayout 与 LoginPage 各发一次。
 */
import { ref, computed } from 'vue'
import { apiV2 } from '@/utils/httpClient'

// 与后端 DEFAULT_DISPLAY_NAME 保持一致；请求失败时用这个兜底，不阻塞渲染
// [FIX 2026-10-13] 此前 TopNavHeader.vue 与 AppLayout.vue 各自硬编码了
// 不同的默认值（前者同此值、后者为 ArchWorkspace），部署改名时必然漏改。
// 组件默认值统一改为空串：真实值一律由 AppRootLayout 经 useInstanceInfo 注入，
// 组件不再持有任何品牌名，兜底责任唯一落在本模块。
const FALLBACK_NAME = 'BIP应用架构管理'

const displayName = ref(FALLBACK_NAME)
const source = ref('default')
const instanceApps = ref([])
const loaded = ref(false)
let _loading = null

async function load() {
  // 并发调用共享同一次请求（AppRootLayout 与 LoginPage 都会调）
  if (_loading) return _loading
  _loading = (async () => {
    try {
      const result = await apiV2.get('/meta/instance')
      if (result.success) {
        const data = result.data ?? {}
        if (data.display_name) displayName.value = data.display_name
        if (data.source) source.value = data.source
        if (Array.isArray(data.apps)) instanceApps.value = data.apps
      }
    } catch {
      // 静默回落默认值 —— 展示名不是关键路径，不该因它报错影响登录
    } finally {
      loaded.value = true
    }
  })()
  try {
    await _loading
  } finally {
    _loading = null
  }
}

export function useInstanceInfo() {
  return {
    displayName,
    source,
    apps: instanceApps,
    loaded,
    loadInstanceInfo: load,
  }
}