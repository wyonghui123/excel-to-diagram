<template>
  <nav class="sub-nav-tabs" :class="{ 'sub-nav-tabs--compact': compact }" role="tablist" :aria-label="ariaLabel">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      type="button"
      role="tab"
      class="sub-nav-tab"
      :class="{
        'sub-nav-tab--active': modelValue === tab.key,
        'sub-nav-tab--disabled': tab.disabled
      }"
      :aria-selected="modelValue === tab.key"
      :disabled="tab.disabled"
      @click="handleSelect(tab)"
    >
      <span class="sub-nav-tab__label">{{ tab.label }}</span>
      <span v-if="tab.badge" class="sub-nav-tab__badge">{{ tab.badge }}</span>
    </button>
  </nav>
</template>

<script setup>
const props = defineProps({
  tabs: {
    type: Array,
    required: true,
    validator: (val) => val.every(t => t.key && t.label)
  },
  modelValue: {
    type: [String, Number],
    required: true
  },
  compact: {
    type: Boolean,
    default: false
  },
  ariaLabel: {
    type: String,
    default: '标签页导航'
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

function handleSelect(tab) {
  if (tab.disabled) return
  emit('update:modelValue', tab.key)
  emit('change', tab.key)
}
</script>

<style scoped lang="scss">
.sub-nav-tabs {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-xs, 4px);
  background: var(--color-bg-container, #fff);
  border-bottom: 1px solid var(--color-border-light, #f0f0f0);
  padding: 0 var(--spacing-md, 16px);
  flex-shrink: 0;

  &--compact {
    gap: 0;
    padding: 0;
  }
}

.sub-nav-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xxs, 2px);
  padding: var(--spacing-sm, 8px) var(--spacing-md, 16px);
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #666666);
  font-size: var(--font-size-md, 14px);
  font-weight: 500;
  line-height: 1.5;
  cursor: pointer;
  white-space: nowrap;
  transition:
    color var(--duration-normal, 200ms) ease-in-out,
    background-color var(--duration-normal, 200ms) ease-in-out;
  user-select: none;

  &::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -1px;
    height: 2px;
    background: transparent;
    border-radius: 2px 2px 0 0;
    transition: background-color var(--duration-normal, 200ms) ease-in-out;
  }

  &:hover:not(.sub-nav-tab--disabled):not(.sub-nav-tab--active) {
    color: var(--color-text-primary, #333333);
    background-color: var(--yonyou-orange-50, #fff7ed);
  }

  &:focus-visible {
    outline: none;

    &::after {
      background-color: rgba(234, 88, 12, 0.3);
    }
  }

  &--active {
    color: var(--yonyou-orange-600, #ea580c);
    font-weight: 600;

    &::after {
      background-color: var(--yonyou-orange-600, #ea580c);
    }
  }

  &--disabled {
    color: var(--color-text-disabled, #cccccc);
    cursor: not-allowed;
    pointer-events: none;
  }

  .sub-nav-tabs--compact & {
    padding: var(--spacing-sm, 8px) var(--spacing-lg, 24px);
    border-right: 1px solid transparent;
    margin-right: -1px;
  }
}

.sub-nav-tab__label {
  line-height: inherit;
}

.sub-nav-tab__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: var(--font-size-xxs, 10px);
  font-weight: 600;
  line-height: 1;
  color: #fff;
  background: var(--yonyou-orange-600, #ea580c);
  border-radius: 9px;
}

.sub-nav-tab--active .sub-nav-tab__badge {
  background: var(--yonyou-orange-600, #ea580c);
}
</style>
