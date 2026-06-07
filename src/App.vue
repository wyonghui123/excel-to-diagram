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
          <router-view />
        </AppRootLayout>
      </template>
      <NotificationContainer />
    </div>
  </el-config-provider>
</template>

<script>
import { inject } from 'vue'
import LoginPage from './components/LoginPage.vue'
import ChangePasswordDialog from './components/ChangePasswordDialog.vue'
import NotificationContainer from './components/NotificationContainer.vue'
import AppRootLayout from './components/common/AppRootLayout.vue'
import { useAuthStore } from './stores/authStore'
import { useMessage } from './composables/useMessage'

export default {
  name: 'App',
  components: {
    LoginPage,
    ChangePasswordDialog,
    NotificationContainer,
    AppRootLayout,
  },
  data() {
    return {
      authEnabled: true,
    }
  },
  computed: {
    authStore() {
      return useAuthStore()
    },
    // [FR-004] 接收 main.js 注入的 locale
    epLocale() {
      return inject('elementPlusLocale', null)
    }
  },
  methods: {
    handleChangePasswordClose() {
      const authStore = useAuthStore()
      const message = useMessage()
      if (authStore.mustChangePassword) {
        message.warning('请先修改密码')
        return
      }
    }
  },
  async mounted() {
    // session 恢复已移至 main.js 显式调用 loadFromCookie('restore')
    // 此处不再需要手动 fetchCurrentUser
  }
}
</script>

<style lang="scss">
/* 样式已在 main.js 中统一导入 */

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

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
