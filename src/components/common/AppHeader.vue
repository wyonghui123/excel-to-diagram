<template>
  <header class="app-header">
    <div class="header-left">
      <button v-if="showBack" class="back-btn" @click="$emit('back')">
        <span>←</span>
        <span v-if="backText">{{ backText }}</span>
      </button>
      <h1 class="header-title">{{ title }}</h1>
      <slot name="left-extra" />
    </div>
    
    <div class="header-center">
      <slot name="center" />
    </div>
    
    <div class="header-right">
      <slot name="right" />
    </div>
  </header>
</template>

<script>
export default {
  name: 'AppHeader',
  props: {
    title: {
      type: String,
      required: true
    },
    showBack: {
      type: Boolean,
      default: false
    },
    backText: {
      type: String,
      default: '返回'
    }
  },
  emits: ['back']
}
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.app-header {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.back-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  transition: all var(--transition-normal);

  &:hover {
    background: var(--color-border);
    color: var(--color-text-primary);
  }
}

.header-title {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.header-center {
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-md);
}

// 响应式
@include respond-to('md') {
  .app-header {
    padding: var(--spacing-sm) var(--spacing-md);
  }

  .header-title {
    font-size: var(--font-size-lg);
  }
}

@include respond-to('sm') {
  .app-header {
    grid-template-columns: auto 1fr;
    gap: var(--spacing-sm);
  }

  .header-center {
    grid-column: 1 / -1;
    order: 3;
    justify-content: flex-start;
  }

  .header-right {
    display: none;
  }
}

@include respond-to('xs') {
  .back-btn span:last-child {
    display: none;
  }

  .header-title {
    font-size: var(--font-size-md);
  }
}
</style>
