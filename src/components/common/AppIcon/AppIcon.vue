<template>
  <svg
    class="app-icon"
    :class="[`app-icon--${name}`, `app-icon--${size}`]"
    :style="iconStyle"
    viewBox="0 0 16 16"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <template v-if="name === 'arrow-right'">
      <path d="M3 8H13M13 8L9 4M13 8L9 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'arrow-left'">
      <path d="M13 8H3M3 8L7 4M3 8L7 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'arrow-up'">
      <path d="M8 13V3M8 3L4 7M8 3L12 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'arrow-down'">
      <path d="M8 3V13M8 13L4 9M8 13L12 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'check'">
      <path d="M3 8L6.5 11.5L13 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'close'">
      <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'menu'">
      <path d="M3 4H13M3 8H13M3 12H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'chevron-right'">
      <path d="M6 4L10 8L6 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'chevron-down'">
      <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'chevron-up'">
      <path d="M4 10L8 6L12 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'lightning'">
      <path d="M9 2L4 9H8L7 14L12 7H8L9 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="currentColor" fill-opacity="0.1"/>
    </template>
    <template v-else-if="name === 'plus'">
      <path d="M8 3V13M3 8H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'minus'">
      <path d="M3 8H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'vertical-layout'">
      <rect x="3" y="2" width="10" height="3" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <rect x="3" y="7" width="10" height="3" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <rect x="3" y="12" width="10" height="2" rx="1" stroke="currentColor" stroke-width="1.5"/>
    </template>
    <template v-else-if="name === 'horizontal-layout'">
      <rect x="2" y="3" width="3" height="10" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <rect x="7" y="3" width="3" height="10" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <rect x="12" y="3" width="2" height="10" rx="1" stroke="currentColor" stroke-width="1.5"/>
    </template>
    <template v-else-if="name === 'enabled'">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
      <path d="M5.5 8L7 9.5L10.5 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'disabled'">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
      <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'bulb'">
      <path d="M8 2C5.79 2 4 3.79 4 6C4 7.78 4.73 9.37 6 10.4V12C6 12.55 6.45 13 7 13H9C9.55 13 10 12.55 10 12V10.4C11.27 9.37 12 7.78 12 6C12 3.79 10.21 2 8 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M6 14V14.01M10 14V14.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'chart'">
      <rect x="2" y="2" width="12" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M6 10V7M9 10V5M12 10V8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'settings'">
      <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.5"/>
      <path d="M12.5 8C12.5 7.5 12.4 7 12.2 6.5L13.5 5.2L12.8 4.5L11.5 5.8C11 5.6 10.5 5.5 10 5.5V4H9V5.5C8.5 5.5 8 5.6 7.5 5.8L6.2 4.5L5.5 5.2L6.8 6.5C6.6 7 6.5 7.5 6.5 8H5V9H6.5C6.5 9.5 6.6 10 6.8 10.5L5.5 11.8L6.2 12.5L7.5 11.2C8 11.4 8.5 11.5 9 11.5V13H10V11.5C10.5 11.5 11 11.4 11.5 11.2L12.8 12.5L13.5 11.8L12.2 10.5C12.4 10 12.5 9.5 12.5 9H14V8H12.5Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'diagram'">
      <rect x="2" y="2" width="5" height="4" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <rect x="9" y="2" width="5" height="4" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <rect x="5" y="9" width="6" height="5" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M4.5 6V7.5C4.5 7.78 4.72 8 5 8H7.5V9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M11.5 6V7.5C11.5 7.78 11.28 8 11 8H8.5V9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'arrow-right-long'">
      <path d="M2 8H14M14 8L10 4M14 8L10 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'direction-tb'">
      <rect x="2" y="2" width="12" height="4" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M8 6V8M6 10L8 8L10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="2" y="10" width="12" height="4" rx="1" stroke="currentColor" stroke-width="1.5"/>
    </template>
    <template v-else-if="name === 'direction-lr'">
      <rect x="2" y="2" width="4" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M6 8H8M10 6L8 8L10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="10" y="2" width="4" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/>
    </template>
    <template v-else-if="name === 'refresh'">
      <path d="M2 8C2 5.5 4 3 7 3C9.5 3 11.5 4.5 12 7M14 8C14 10.5 12 13 9 13C6.5 13 4.5 11.5 4 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M12 4V7H9M4 12V9H7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'fullscreen'">
      <path d="M4 8V4H8M12 8V4H8M12 12V8H8M4 12V8H8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="2" y="2" width="12" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/>
    </template>
    <template v-else-if="name === 'fullscreen-exit'">
      <path d="M4 6V4H6M12 6V4H10M12 10V12H10M4 10V12H6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="2" y="2" width="12" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/>
    </template>
    <template v-else-if="name === 'copy'">
      <rect x="4" y="4" width="8" height="10" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M4 6H3C2.45 6 2 6.45 2 7V14C2 14.55 2.45 15 3 15H10C10.55 15 11 14.55 11 14V13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'download'">
      <path d="M8 2V10M8 10L5 7M8 10L11 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M2 12V13C2 13.55 2.45 14 3 14H13C13.55 14 14 13.55 14 13V12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'export'">
      <path d="M14 8V12C14 12.55 13.55 13 13 13H3C2.45 13 2 12.55 2 12V8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M8 2V9M8 9L5 6M8 9L11 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>

    <!-- ============================================ -->
    <!-- 新增：语义图标 Semantic Icons         -->
    <!-- 用于 GlobalFilter, DataPreview, Notification -->
    <!-- ============================================ -->
    <template v-else-if="name === 'important'">
      <path d="M8 2L2 14h12L8 2z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M8 9v1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <circle cx="8" cy="12" r="0.5" fill="currentColor"/>
    </template>
    <template v-else-if="name === 'warning'">
      <path d="M8 3.5L14.5 14h-13L8 3.5z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M8 7v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <circle cx="8" cy="12" r="0.5" fill="currentColor"/>
    </template>
    <template v-else-if="name === 'info'">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
      <path d="M8 11v-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <circle cx="8" cy="6" r="0.5" fill="currentColor"/>
    </template>
    <template v-else-if="name === 'tip'">
      <path d="M8 2c-2.5 0-4.5 2-4.5 4.5 0 1.8.9 3.4 2.4 4.3V12c0 .6.4 1 1 1h2c.6 0 1-.4 1-1v-1.2c1.5-.9 2.4-2.5 2.4-4.3 0-2.5-2-4.5-4.5-4.5z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M6 14h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>

    <!-- ============================================ -->
    <!-- 新增：功能图标 Functional Icons        -->
    <!-- 用于各管理页面、工具栏、操作按钮          -->
    <!-- ============================================ -->
    <template v-else-if="name === 'search'">
      <circle cx="7" cy="7" r="4" stroke="currentColor" stroke-width="1.5"/>
      <path d="M10 10l4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'user'">
      <circle cx="8" cy="5" r="3" stroke="currentColor" stroke-width="1.5"/>
      <path d="M2 14c0-3.3 2.7-6 6-6s6 2.7 6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'link'">
      <path d="M9 7l-4 4c-1 1-1 3 0 4s3 1 4 0l4-4c1-1 1-3 0-4s-3-1-4 0" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'clipboard'">
      <rect x="5" y="2" width="6" height="4" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M4 4h8a1 1 0 011 1v9a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'eye'">
      <path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z" stroke="currentColor" stroke-width="1.5"/>
      <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.5"/>
    </template>
    <template v-else-if="name === 'eye-off'">
      <path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z" stroke="currentColor" stroke-width="1.5"/>
      <path d="M3 13l10-10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'lock'">
      <rect x="4" y="7" width="8" height="6" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M6 7V5a2 2 0 114 0v2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'key'">
      <circle cx="5" cy="8" r="2" stroke="currentColor" stroke-width="1.5"/>
      <path d="M7 8l2 2 4-4v-2c0-1.1-.9-2-2-2h-2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'mobile'">
      <rect x="4" y="1" width="8" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
      <path d="M8 11h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'robot'">
      <rect x="3" y="4" width="10" height="9" rx="2" stroke="currentColor" stroke-width="1.5"/>
      <circle cx="6" cy="8" r="1" fill="currentColor"/>
      <circle cx="10" cy="8" r="1" fill="currentColor"/>
      <path d="M6 1v3M10 1v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'chart-bar'">
      <rect x="2" y="2" width="12" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M5 12V8M8 12V5M11 12v-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'edit'">
      <path d="M11 3l2 2-8 8H3v-2l8-8z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M10 4l2 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'trash'">
      <path d="M3 5h10M5 5V3a1 1 0 011-1h4a1 1 0 011 1v2M7 8v4M9 8v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M4 5h8v9a1 1 0 01-1 1H5a1 1 0 01-1-1V5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'help'">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
      <path d="M8 11v-2M8 6h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'filter'">
      <polygon points="6 2 10 2 14 14 2 14 6 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'mail'">
      <rect x="2" y="4" width="12" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/>
      <path d="M2 4l6 5 6-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'file'">
      <path d="M9 2H4a1 1 0 00-1 1v10a1 1 0 001 1h8a1 1 0 001-1V6l-4-4z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M9 2v4h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'chat'">
      <path d="M14 10c0 2.2-2.7 4-6 4-.7 0-1.4-.1-2-.2L3 15v-3.2C1.8 10.9 1 9.5 1 8c0-2.2 2.7-4 6-4s6 1.8 6 4z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'timer'">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
      <path d="M8 5v3.5l2 1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M8 2v1M8 13v1M2 8h1M13 8h1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>

    <!-- ============================================ -->
    <!-- 新增：状态图标 Status Icons            -->
    <!-- 替代 [DECORATIVE] [DECORATIVE] [DECORATIVE] [DECORATIVE] 等符号                     -->
    <!-- ============================================ -->
    <template v-else-if="name === 'check-circle'">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
      <path d="M5 8l2 2 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'x-circle'">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
      <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else-if="name === 'check-square'">
      <rect x="3" y="3" width="10" height="10" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M6 8l2 2 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'square'">
      <rect x="3" y="3" width="10" height="10" rx="1" stroke="currentColor" stroke-width="1.5"/>
    </template>
    <template v-else-if="name === 'layers'">
      <polygon points="2 6 8 2 14 6 8 10 2 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <polyline points="2 10 8 14 14 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </template>
    <template v-else-if="name === 'sort'">
      <path d="M4 6h6M4 10h4M4 2h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </template>
    <template v-else>
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
    </template>
  </svg>
</template>

<script>
export default {
  name: 'AppIcon',
  props: {
    name: {
      type: String,
      required: true,
      validator: (value) => [
        'arrow-right', 'arrow-left', 'arrow-up', 'arrow-down', 'arrow-right-long',
        'check', 'close',
        'chevron-right', 'chevron-down', 'chevron-up',
        'lightning', 'plus', 'minus',
        'vertical-layout', 'horizontal-layout',
        'enabled', 'disabled',
        'bulb', 'chart', 'settings', 'diagram',
        'direction-tb', 'direction-lr',
        'refresh', 'fullscreen', 'fullscreen-exit',
        'copy', 'download', 'export',
        // 语义图标
        'important', 'warning', 'info', 'tip',
        // 功能图标
        'search', 'user', 'link', 'clipboard', 'eye', 'eye-off', 'lock', 'key',
        'mobile', 'robot', 'chart-bar', 'edit', 'trash', 'help', 'filter',
        'mail', 'file', 'chat',
        // 新增图标
        'layers', 'sort', 'timer',
        // 状态图标
        'check-circle', 'x-circle', 'check-square', 'square'
      ].includes(value)
    },
    size: {
      type: [String, Number],
      default: 'md',
      validator: (value) => {
        if (['xs', 'sm', 'md', 'lg', 'xl'].includes(value)) return true
        if (typeof value === 'number') return true
        if (typeof value === 'string' && /^\d+$/.test(value)) return true
        return false
      }
    },
    color: {
      type: String,
      default: 'currentColor'
    }
  },
  computed: {
    iconStyle() {
      const base = { color: this.color }
      if (typeof this.size === 'number') {
        return { ...base, width: `${this.size}px`, height: `${this.size}px` }
      }
      return base
    }
  }
}
</script>

<style scoped>
.app-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.app-icon--xs {
  width: 10px;
  height: 10px;
}

.app-icon--sm {
  width: 12px;
  height: 12px;
}

.app-icon--md {
  width: 14px;
  height: 14px;
}

.app-icon--lg {
  width: 16px;
  height: 16px;
}

.app-icon--xl {
  width: 20px;
  height: 20px;
}
</style>
