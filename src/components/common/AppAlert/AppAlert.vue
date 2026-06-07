<template>
  <div :class="alertClasses" role="alert">
    <span v-if="showIcon" class="app-alert__icon">
      <svg v-if="type === 'info'" width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
      </svg>
      <svg v-else-if="type === 'success'" width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
      </svg>
      <svg v-else-if="type === 'warning'" width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
      </svg>
      <svg v-else-if="type === 'error'" width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
      </svg>
    </span>
    <div class="app-alert__content">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  type: {
    type: String,
    default: 'info',
    validator: (value) => ['info', 'success', 'warning', 'error'].includes(value)
  },
  showIcon: {
    type: Boolean,
    default: true
  }
})

const alertClasses = computed(() => [
  'app-alert',
  `app-alert--${props.type}`
])
</script>

<style scoped>
.app-alert {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

.app-alert__icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  margin-top: 1px;
}

.app-alert__content {
  flex: 1;
  min-width: 0;
}

.app-alert--info {
  background: var(--color-primary-bg-subtle, rgba(99,102,241,0.06));
  border: 1px solid var(--color-primary-border, rgba(99,102,241,0.15));
  color: var(--color-primary);
}

.app-alert--success {
  background: var(--color-success-bg, rgba(34,197,94,0.06));
  border: 1px solid var(--color-success-border, rgba(34,197,94,0.15));
  color: var(--color-success);
}

.app-alert--warning {
  background: var(--color-warning-bg, rgba(245,158,11,0.06));
  border: 1px solid var(--color-warning-border, rgba(245,158,11,0.15));
  color: var(--color-warning);
}

.app-alert--error {
  background: var(--color-error-bg, rgba(239,68,68,0.06));
  border: 1px solid var(--color-error-border, rgba(239,68,68,0.15));
  color: var(--color-error);
}
</style>
