<template>
  <Teleport to="body">
    <div class="notification-container">
      <TransitionGroup name="notification">
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="notification"
          :class="'notification-' + msg.type"
        >
          <AppIcon :name="iconMap[msg.type]" :size="16" class="notification-icon" />
          <span class="notification-message">{{ msg.message }}</span>
          <button class="notification-close" @click="remove(msg.id)">×</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import { useMessage } from '@/composables/useMessage'

const { messages, remove } = useMessage()

const iconMap = {
  success: 'check-circle',
  error: 'x-circle',
  warning: 'warning',
  info: 'info'
}
</script>

<style scoped>
.notification-container {
  position: fixed;
  top: var(--spacing-lg);
  right: var(--spacing-lg);
  /* [FIX 2026-06-14] 与 el-message / el-notification 拉齐到 --z-index-max (9999)，
   *   否则在 el-drawer / el-dialog 打开时 (默认 z-index 2000-3000) 自定义 toast
   *   会被遮挡，用户看到"无声失败" (例如架构数据管理页 PUT /bo/domain/684 403)。
   *   对齐方案：与 .el-message/.el-notification 走 --z-index-max 同一档位。
   */
  z-index: var(--z-index-max, 9999) !important;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  max-width: 400px;
}

.notification {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  border-radius: var(--yonyou-border-radius-md, 6px);
  box-shadow: var(--yonyou-shadow-lg, 0 4px 12px rgba(0, 0, 0, 0.15));
  animation: slideInRight 0.3s ease-out;
}

@keyframes slideInRight {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.notification-success {
  background: var(--yonyou-success-bg, #f6ffed);
  border-left: 3px solid var(--yonyou-success-border, #52c41a);
  color: var(--yonyou-success-text, #52c41a);
}

.notification-error {
  background: var(--yonyou-error-bg, #fff2f0);
  border-left: 3px solid var(--yonyou-error-border, #ff4d4f);
  color: var(--yonyou-error-text, #ff4d4f);
}

.notification-warning {
  background: var(--yonyou-warning-bg, #fffbe6);
  border-left: 3px solid var(--yonyou-warning-border, #faad14);
  color: var(--yonyou-warning-text, #faad14);
}

.notification-info {
  background: var(--yonyou-info-bg, #e6f7ff);
  border-left: 3px solid var(--yonyou-info-border, #1890ff);
  color: var(--yonyou-info-text, #1890ff);
}

.notification-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.notification-message {
  flex: 1;
  font-size: 14px;
  line-height: 1.5;
}

.notification-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  opacity: 0.6;
  padding: 0 4px;
  transition: opacity 0.2s ease;
}

.notification-close:hover {
  opacity: 1;
}

.notification-enter-active,
.notification-leave-active {
  transition: all 0.3s ease;
}

.notification-enter-from,
.notification-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

.notification-move {
  transition: transform 0.3s ease;
}
</style>