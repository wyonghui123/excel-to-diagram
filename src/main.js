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
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'

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

// [FR-004] 移除 app.use(ElementPlus),改用 unplugin-vue-components 按需自动注册
//   - size/zIndex 通过 App.vue 的 <el-config-provider :size="default" :z-index="3000"> 配置
//   - locale 通过 App.vue 的 <el-config-provider :locale="zhCn"> 配置
//   - 注册逻辑由 ElementPlusResolver 在每个组件使用时自动 import
// app.use(ElementPlus, { locale: zhCn, size: 'default', zIndex: 3000 })

setOnUnauthorized(() => {
  if (window.location.pathname !== '/') {
    window.location.href = '/?reason=unauthorized'
  }
})

// 显式恢复会话（替代 authStore 内部的自动调用）
const authStore = useAuthStore()
authStore.loadFromCookie('restore')

// [FR-004] 将 zhCn 暴露给 App.vue (ElConfigProvider 需要 locale prop)
app.provide('elementPlusLocale', zhCn)

app.mount('#app')
