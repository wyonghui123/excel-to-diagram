<template>
  <!-- [FR-004] ElConfigProvider 注入 Element Plus locale (替代 app.use 全量注册) -->
  <el-config-provider :locale="epLocale" size="default">
    <div id="app">
      <div v-if="!authStore.sessionReady" class="session-loading">
        <div class="loading-spinner"></div>
      </div>
      <template v-else>
        <LoginPage v-if="authEnabled && !authStore.isLoggedIn" />
        <ChangePasswordDialog
          v-else-if="authEnabled && authStore.isLoggedIn && authStore.mustChangePassword"
          :visible="authStore.mustChangePassword"
          @close="handleChangePasswordClose"
        />
        <AppRootLayout v-else>
          <!-- [FR-007] keep-alive 缓存列表/工作台页面 -->
          <!-- [FR-021] ErrorBoundary 捕获路由页面错误 -->
          <ErrorBoundary>
            <keep-alive :max="10" :include="cachedRouteNames" :exclude="excludeRouteNames">
              <router-view />
            </keep-alive>
          </ErrorBoundary>
        </AppRootLayout>
      </template>
      <NotificationContainer />
    </div>
  </el-config-provider>
</template>

<script setup>
// [FR-014] Options API → <script setup>
import { inject } from 'vue'
import LoginPage from './components/LoginPage.vue'
import ChangePasswordDialog from './components/ChangePasswordDialog.vue'
import NotificationContainer from './components/NotificationContainer.vue'
import AppRootLayout from './components/common/AppRootLayout.vue'
import ErrorBoundary from './components/common/ErrorBoundary.vue'
import { useAuthStore } from './stores/authStore'
import { useMessage } from './composables/useMessage'

const authStore = useAuthStore()
const message = useMessage()

// [FR-004] 接收 main.js 注入的 locale
const epLocale = inject('elementPlusLocale', null)

// 认证开关 (默认启用)
const authEnabled = true

// [FR-007] 缓存路由名白名单 (component name, 不是 route name)
const cachedRouteNames = [
  'ArchWorkspaceNew',  // 工作台
  'MetaListPage',      // 通用元数据列表
  'GenericObjectList', // 通用对象列表
  'ObjectDetail',      // 详情查看 (不含编辑)
]

// [FR-007] 明确排除的组件名
const excludeRouteNames = [
  'LoginPage',
  'ChangePasswordDialog',
  'ObjectCreate',  // 创建页面 (表单重置)
]

function handleChangePasswordClose() {
  if (authStore.mustChangePassword) {
    message.warning('请先修改密码')
  }
}
</script>

<style lang="scss">
/* 样式已在 main.js 中统一导入 */

/* [FR-020] 移除全局 * 选择器,引入 modern-normalize 标准化重置 */
@import 'modern-normalize/modern-normalize.css';

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#app {
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
}

.session-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: var(--color-bg-secondary);
}

.session-loading .loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
