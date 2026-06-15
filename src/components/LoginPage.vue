<template>
  <div class="login-overlay">
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo">
          <svg width="40" height="40" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="32" height="32" rx="6" fill="var(--color-primary)"/>
            <rect x="4" y="5" width="10" height="7" rx="1.5" fill="white" fill-opacity="0.9"/>
            <rect x="18" y="5" width="10" height="7" rx="1.5" fill="white" fill-opacity="0.9"/>
            <rect x="9" y="17" width="14" height="10" rx="2" fill="white" fill-opacity="0.9"/>
            <path d="M9 12V15L16 19" stroke="white" stroke-width="1.3" stroke-linecap="round"/>
            <path d="M23 12V15L16 19" stroke="white" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
        </div>
        <h2>BIP应用架构管理</h2>
        <p class="login-subtitle">请登录以继续</p>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
            :disabled="loading"
            @focus="clearError"
          />
        </div>

        <div class="form-group">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loading"
            @focus="clearError"
          />
        </div>

        <div v-if="authStore.error" class="login-error">
          {{ authStore.error }}
        </div>

        <button type="submit" class="login-btn" :disabled="loading || !username || !password">
          <span v-if="loading" class="loading-spinner"></span>
          <span v-else>登 录</span>
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const loading = ref(false)

function clearError() {
  authStore.error = ''
}

async function handleLogin() {
  if (!username.value || !password.value) return
  loading.value = true
  const success = await authStore.login(username.value, password.value)
  loading.value = false
  if (success) {
    const redirect = route.query.redirect
    if (redirect && typeof redirect === 'string' && redirect.startsWith('/')) {
      router.push(redirect)
    }
  }
}
</script>

<style scoped>
.login-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, var(--yonyou-orange-600) 0%, var(--yonyou-orange-800) 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-index-modal);
}

.login-card {
  background: var(--color-bg-container);
  border-radius: var(--radius-xl);
  padding: calc(var(--spacing-xl) * 1.5);
  width: 400px;
  max-width: 90vw;
  box-shadow: var(--shadow-xl);
}

.login-header {
  text-align: center;
  margin-bottom: var(--spacing-xl);
}

.login-logo {
  margin-bottom: var(--spacing-md);
}

.login-header h2 {
  margin: 0 0 var(--spacing-sm);
  font-size: var(--font-size-xxl);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-bold);
}

.login-subtitle {
  margin: 0;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-group label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.form-group input {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out), box-shadow var(--duration-fast) var(--ease-out);
}

.form-group input:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-group input:disabled {
  background: var(--color-bg-disabled);
  cursor: not-allowed;
}

.login-error {
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  border: 1px solid var(--color-error-border);
}

.login-btn {
  padding: var(--spacing-md) 0;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--btn-height-lg);
}

.login-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.login-btn:disabled {
  background: var(--color-primary-disabled);
  cursor: not-allowed;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
