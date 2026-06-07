<template>
  <div class="empty-state">
    <div class="empty-state__icon" v-html="iconSvg"></div>
    <p v-if="title" class="empty-state__title">{{ title }}</p>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <slot />
  </div>
</template>

<script>
const ICONS = {
  box: '<svg viewBox="0 0 48 48" width="56" height="56" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="6" y="10" width="36" height="28" rx="3"/><path d="M6 18h36"/><path d="M20 10V6a2 2 0 012-2h4a2 2 0 012 2v4"/><circle cx="24" cy="28" r="5"/><path d="M27 31l4 4"/></svg>',
  clipboard: '<svg viewBox="0 0 48 48" width="56" height="56" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 6h20v4H14z"/><path d="M16 6V4a2 2 0 012-2h12a2 2 0 012 2v2"/><rect x="11" y="10" width="26" height="32" rx="2"/><path d="M19 21h10M19 29h10"/></svg>',
  search: '<svg viewBox="0 0 48 48" width="56" height="56" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="21" cy="21" r="13"/><path d="M30.5 30.5L40 40"/></svg>',
  warning: '<svg viewBox="0 0 48 48" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M24 4L4 40h40L24 4z"/><path d="M24 17v12M24 35v1"/></svg>',
  folder: '<svg viewBox="0 0 48 48" width="56" height="56" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 12h16l4-4h20v32H4V12z"/></svg>'
}

export default {
  name: 'EmptyState',
  props: {
    type: {
      type: String,
      default: 'box',
      validator: (v) => ['box', 'clipboard', 'search', 'warning', 'folder'].includes(v)
    },
    title: {
      type: String,
      default: ''
    },
    description: {
      type: String,
      default: ''
    }
  },
  computed: {
    iconSvg() {
      return ICONS[this.type] || ICONS.box
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.empty-state {
  @include flex-center;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding: var(--spacing-xxl);
  color: var(--color-text-tertiary);
}

.empty-state__icon {
  color: var(--color-text-quaternary);
  opacity: 0.6;
}

.empty-state__title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin: 0;
}

.empty-state__desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0;
}
</style>
