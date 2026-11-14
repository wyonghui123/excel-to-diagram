<!--
  NotFound - 404 页（spec-error-warning-framework FR-008）
  访问未匹配路由时展示，避免白屏；提供返回首页 / 后退入口。
-->
<template>
  <div class="not-found">
    <div class="not-found__container">
      <div class="not-found__code">404</div>
      <h2 class="not-found__title">页面不存在</h2>
      <p class="not-found__message">
        请求的地址 <code>{{ path }}</code> 不存在或已被移除。
      </p>
      <div class="not-found__actions">
        <button class="not-found__btn not-found__btn--primary" @click="goHome">返回首页</button>
        <button class="not-found__btn" @click="goBack">返回上一页</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const path = computed(() => route.fullPath || route.path)

function goHome() {
  router.push('/')
}

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}
</script>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 24px;
}

.not-found__container {
  max-width: 480px;
  text-align: center;
}

.not-found__code {
  font-size: 72px;
  font-weight: 700;
  line-height: 1;
  color: var(--el-color-primary, #ea580c);
  margin-bottom: 16px;
}

.not-found__title {
  margin: 0 0 12px;
  font-size: 20px;
  color: var(--el-text-color-primary, #1f2937);
}

.not-found__message {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--el-text-color-regular, #6b7280);
  word-break: break-all;
}

.not-found__actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.not-found__btn {
  padding: 8px 20px;
  border: 1px solid var(--el-border-color, #d1d5db);
  border-radius: 4px;
  background: #fff;
  color: var(--el-text-color-regular, #374151);
  font-size: 14px;
  cursor: pointer;
}

.not-found__btn--primary {
  background: var(--el-color-primary, #ea580c);
  border-color: var(--el-color-primary, #ea580c);
  color: #fff;
}
</style>