<template>
  <AppModal
    :model-value="modelValue"
    :title="title"
    :show-close="false"
    width="400px"
    @close="handleCancel"
  >
    <div class="confirm-body">
      <div class="confirm-icon" :class="`confirm-icon--${type}`">
        <svg v-if="type === 'warning'" viewBox="0 0 24 24" width="24" height="24" fill="none">
          <path d="M12 2L1 21h22L12 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
          <path d="M12 9V13M12 17V17.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <svg v-else-if="type === 'danger'" viewBox="0 0 24 24" width="24" height="24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
          <path d="M12 8V12M12 16V16.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" width="24" height="24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
          <path d="M12 8V12M12 16V16.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </div>
      <div class="confirm-content">
        <p class="confirm-message">{{ message }}</p>
        <p v-if="description" class="confirm-desc">{{ description }}</p>
      </div>
    </div>
    <template #footer>
      <AppButton variant="secondary" :disabled="loading" @click="handleCancel">{{ cancelText }}</AppButton>
      <AppButton :variant="type === 'danger' ? 'danger' : 'primary'" :loading="loading" @click="handleConfirm">{{ confirmText }}</AppButton>
    </template>
  </AppModal>
</template>

<script>
import AppModal from './AppModal/AppModal.vue'
import AppButton from './AppButton/AppButton.vue'

export default {
  name: 'ConfirmDialog',
  components: { AppModal, AppButton },
  inheritAttrs: false,
  props: {
    modelValue: {
      type: Boolean,
      default: false
    },
    visible: {
      type: Boolean,
      default: undefined
    },
    title: {
      type: String,
      default: '确认'
    },
    message: {
      type: String,
      default: ''
    },
    description: {
      type: String,
      default: ''
    },
    type: {
      type: String,
      default: 'warning',
      validator: (v) => ['info', 'warning', 'danger'].includes(v)
    },
    confirmText: {
      type: String,
      default: '确定'
    },
    cancelText: {
      type: String,
      default: '取消'
    },
    loading: {
      type: Boolean,
      default: false
    }
  },
  emits: ['confirm', 'cancel', 'update:modelValue', 'update:visible'],
  computed: {
    isVisible() {
      return this.modelValue ?? this.visible ?? false
    }
  },
  methods: {
    handleConfirm() {
      this.$emit('confirm')
      this.$emit('update:modelValue', false)
      this.$emit('update:visible', false)
    },
    handleCancel() {
      this.$emit('cancel')
      this.$emit('update:modelValue', false)
      this.$emit('update:visible', false)
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.confirm-body {
  display: flex;
  gap: var(--spacing-md);
}

.confirm-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  @include flex-center;

  &--warning {
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }

  &--danger {
    background: var(--color-error-bg);
    color: var(--color-error);
  }

  &--info {
    background: var(--color-primary-bg);
    color: var(--color-primary);
  }
}

.confirm-content {
  flex: 1;
}

.confirm-message {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-xs) 0;
  line-height: var(--line-height-normal);
}

.confirm-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0;
  line-height: var(--line-height-normal);
}
</style>
