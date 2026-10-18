/**
 * useInstanceInfo - 本实例展示信息（左上角名称 / 登录页标题的数据源）
 *
 * 数据源: GET /api/v2/meta/instance（无鉴权，登录页在拿到 token 之前也要用）
 * 取值优先级由后端裁定：PLATFORM_DISPLAY_NAME 环境变量 > 恰好 1 个 app 时用其 app.yaml name
 *
 * module-level 单例（与 useMenuPermissions 同模式）: 多个组件共享同一次请求，
 * 避免 AppRootLayout 与 LoginPage 各发一次。
 */
import { ref, computed } from 'vue'
import { apiV2 } from '@/utils/httpClient'

// [去品牌兜底 2026-10-17] 初始值改为空串，不再预置任何品牌名。
//   起因（用户手机端报障）：页面加载后左上角先显示「BIP应用架构管理」，约 1 秒后才
//   变成真实的「xAPP」—— 因为旧实现在接口返回前用 FALLBACK_NAME 占位，造成可见的
//   品牌名闪烁/二次跳变。
//   取值原则：品牌名只有一个真源（后端 /meta/instance），前端不猜、不兜底。
//   请求未完成 ⇒ 显示空；请求失败 ⇒ 同样为空（source 仍会标记为 'default' 以便排查）。
//   [FIX 2026-10-13] 此前 TopNavHeader.vue 与 AppLayout.vue 各自硬编码了不同的默认值
//   （前者 BIP应用架构管理、后者 ArchWorkspace），部署改名时必然漏改；组件默认值已统一
//   为空串，兜底责任唯一落在本模块 —— 本次把本模块的兜底也一并去掉。
const displayName = ref('')
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