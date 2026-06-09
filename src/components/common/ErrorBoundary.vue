<!--
  ErrorBoundary - Vue 3 错误边界
  [FR-021] 捕获子树错误,显示 fallback UI,阻止应用崩溃

  用法:
  <ErrorBoundary>
    <router-view />
  </ErrorBoundary>

  行为:
  - onErrorCaptured 捕获子树 throw
  - 阻止传播(return false)避免影响其他子树
  - 显示 fallback UI + 重试按钮
  - 错误已由 main.js 的 app.config.errorHandler 上报到 logger,此处不再重复
-->
<template>
  <slot v-if="!error" />
  <div v-else class="error-boundary">
    <div class="error-boundary__container">
      <div class="error-boundary__icon">⚠️</div>
      <h2 class="error-boundary__title">页面出错了</h2>
      <p class="error-boundary__message">{{ errorMessage }}</p>
      <details v-if="showStack" class="error-boundary__stack">
        <summary>查看堆栈</summary>
        <pre>{{ errorStack }}</pre>
      </details>
      <div class="error-boundary__actions">
        <button class="error-boundary__btn error-boundary__btn--primary" @click="retry">
          重试
        </button>
        <button class="error-boundary__btn" @click="goHome">
          返回首页
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  /** 是否在开发环境显示堆栈 */
  showStack: { type: Boolean, default: import.meta.env.DEV }
})

const error = ref(null)
const router = useRouter()

const errorMessage = computed(() => {
  if (!error.value) return ''
  if (error.value instanceof Error) return error.value.message || String(error.value)
  return String(error.value)
})

const errorStack = computed(() => {
  if (!error.value || !(error.value instanceof Error)) return ''
  return error.value.stack || ''
})

/**
 * onErrorCaptured: 捕获子树组件的错误
 * 返回 false 阻止错误继续向上传播
 */
import { onErrorCaptured } from 'vue'
onErrorCaptured((err, instance, info) => {
  error.value = err
  // 上报已由 main.js 的 app.config.errorHandler 处理
  // 此处只负责显示 fallback UI
  return false
})

function retry() {
  error.value = null
}

function goHome() {
  error.value = null
  router.push('/')
}
</script>

<style scoped>
.error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--color-bg-secondary, #f5f5f5);
}

.error-boundary__container {
  max-width: 480px;
  text-align: center;
  background: #fff;
  border-radius: 8px;
  padding: 32px 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.error-boundary__icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.error-boundary__title {
  margin: 0 0 12px;
  font-size: 20px;
  color: var(--color-text-primary, #1f2937);
}

.error-boundary__message {
  margin: 0 0 24px;
  color: var(--color-text-secondary, #6b7280);
  font-size: 14px;
  word-break: break-word;
}

.error-boundary__stack {
  margin: 16px 0;
  text-align: left;
  font-size: 12px;
  background: #f9fafb;
  border-radius: 4px;
  padding: 8px 12px;
}

.error-boundary__stack summary {
  cursor: pointer;
  color: #6b7280;
}

.error-boundary__stack pre {
  margin: 8px 0 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.error-boundary__actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.error-boundary__btn {
  padding: 8px 20px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #fff;
  color: #374151;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.error-boundary__btn:hover {
  border-color: #9ca3af;
  background: #f9fafb;
}

.error-boundary__btn--primary {
  background: var(--color-primary, #ea580c);
  border-color: var(--color-primary, #ea580c);
  color: #fff;
}

.error-boundary__btn--primary:hover {
  background: #c2410c;
  border-color: #c2410c;
}
</style>
