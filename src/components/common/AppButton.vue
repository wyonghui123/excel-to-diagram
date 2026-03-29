<template>
  <button
    :class="['app-button', `app-button--${type}`, `app-button--${size}`, { 'is-loading': loading, 'is-block': block }]"
    :disabled="disabled || loading"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="button-loading">
      <span class="loading-spinner"></span>
    </span>
    <span class="button-content">
      <slot />
    </span>
  </button>
</template>

<script>
export default {
  name: 'AppButton',
  props: {
    type: {
      type: String,
      default: 'primary',
      validator: (value) => ['primary', 'secondary', 'text', 'danger'].includes(value)
    },
    size: {
      type: String,
      default: 'md',
      validator: (value) => ['sm', 'md', 'lg'].includes(value)
    },
    loading: {
      type: Boolean,
      default: false
    },
    disabled: {
      type: Boolean,
      default: false
    },
    block: {
      type: Boolean,
      default: false
    }
  },
  emits: ['click']
}
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.app-button {
  @include button-base;
  position: relative;

  &--primary {
    background: var(--color-primary);
    color: white;

    &:hover:not(:disabled) {
      background: var(--color-primary-hover);
    }

    &:active:not(:disabled) {
      background: var(--color-primary-active);
    }
  }

  &--secondary {
    background: var(--color-bg-tertiary);
    color: var(--color-text-secondary);
    border: 1px solid var(--color-border);

    &:hover:not(:disabled) {
      border-color: var(--color-primary);
      color: var(--color-primary);
    }
  }

  &--text {
    background: transparent;
    color: var(--color-primary);
    padding-left: var(--spacing-sm);
    padding-right: var(--spacing-sm);

    &:hover:not(:disabled) {
      background: rgba(24, 144, 255, 0.1);
    }
  }

  &--danger {
    background: var(--color-error);
    color: white;

    &:hover:not(:disabled) {
      background: #ff7875;
    }
  }

  &--sm {
    padding: var(--spacing-xs) var(--spacing-sm);
    font-size: var(--font-size-sm);
  }

  &--lg {
    padding: var(--spacing-md) var(--spacing-xl);
    font-size: var(--font-size-lg);
  }

  &.is-block {
    width: 100%;
  }

  &.is-loading {
    .button-content {
      opacity: 0;
    }
  }
}

.button-loading {
  position: absolute;
  inset: 0;
  @include flex-center;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
