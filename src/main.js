import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createPersistedState } from 'pinia-plugin-persistedstate'
import router from './router'
import { setOnUnauthorized } from './utils/api'
import { useAuthStore } from './stores/authStore'
import { logger } from './utils/logger'

// [FR-004] 移除 Element Plus 全量注册,改用 unplugin-vue-components 按需导入
//   - 旧的 import 'element-plus' + app.use(ElementPlus) 会强制打包全量组件
//   - vite.config.js 已配置 AutoImport + Components + ElementPlusResolver 自动按需
//   - zhCn locale 通过 App.vue 中的 <el-config-provider :locale="zhCn"> 注入
// import ElementPlus from 'element-plus'
// import 'element-plus/theme-chalk/index.css'
// [FR-008] Element Plus locale: 改用 ESM 按需路径 (vs dist/locale 全量)
//   - element-plus/es/locale/lang/zh-cn 只包含中文 locale 数据
//   - element-plus/dist/locale/zh-cn.mjs 包含所有 locale 的聚合导出
//   - ESM 路径让 Vite tree-shake 未使用的 locale
import zhCn from 'element-plus/es/locale/lang/zh-cn'

// [FR-011] 统一样式入口 (合并原 6 个样式文件)
//   顺序敏感: tokens-yonyou → variables → element-variables → yon-ep → meta-table
//             → element-plus-overrides → app style
import './styles/index.scss'

import App from './App.vue'

const app = createApp(App)
const pinia = createPinia()
// [FR-006] Pinia 持久化策略: opt-in 模式
//   - auto: false 全局禁用自动持久化,各 store 需显式声明 persist
//   - 各 store 使用 persist: { pick: [...] } 白名单持久化字段
//   - 避免误持久化: authStore (安全) / notificationStore (瞬态) / diagramConfigStore (大对象)
pinia.use(createPersistedState({
  storage: localStorage,
  key: prefix => 'app-' + prefix,
  auto: false,
}))

app.use(pinia)
app.use(router)

// [FR-015] setOnUnauthorized 提前注册 (在任何 HTTP 请求之前)
//   - 旧位置在 L79,太晚: loadFromCookie 等初始化请求可能触发 401 但回调未就绪
setOnUnauthorized(() => {
  if (window.location.pathname !== '/') {
    window.location.href = '/?reason=unauthorized'
  }
})

app.config.errorHandler = (err, instance, info) => {
  const componentName = instance?.$?.type?.__name
    || instance?.$?.type?.name
    || 'unknown'
  const errorPayload = {
    type: 'vue:error',
    message: err?.message || String(err),
    stack: err?.stack?.substring(0, 500) || '',
    component: componentName,
    info: info || '',
    timestamp: Date.now()
  }
  window.__appErrors = window.__appErrors || []
  window.__appErrors.push(errorPayload)
  // [FR-001] 替换 console.error → logger.error
  // logger.error 会在生产环境自动 sendBeacon 上报
  logger.error('[AppError]', componentName, errorPayload.message, err)
}

window.addEventListener('unhandledrejection', (event) => {
  const errorPayload = {
    type: 'vue:unhandledrejection',
    message: event.reason?.message || String(event.reason),
    stack: event.reason?.stack?.substring(0, 500) || '',
    timestamp: Date.now()
  }
  window.__appErrors = window.__appErrors || []
  window.__appErrors.push(errorPayload)
  // [FR-001] 替换 console.error → logger.error
  logger.error('[UnhandledRejection]', errorPayload.message, event.reason)
})

window.__pinia = pinia

// [FR-004] 将 zhCn 暴露给 App.vue (ElConfigProvider 需要 locale prop)
// [FR-015] provide 在 mount 之前 (App.vue inject 才能拿到)
app.provide('elementPlusLocale', zhCn)

// [FR-015] await session restore before mount
//   - 旧实现未 await,app.mount 时 session 可能未恢复,导致闪现登录页
//   - 使用 .then() 而非 top-level await (构建目标不支持 es2022)
const authStore = useAuthStore()
authStore.loadFromCookie('restore').then(() => {
  app.mount('#app')
})
