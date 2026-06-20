<template>
  <div class="app-shell">
    <slot name="header">
      <header class="app-shell__header">
        <slot name="header-left">
          <div class="app-shell__header-left">
            <slot name="logo" />
          </div>
        </slot>
        <slot name="header-center">
          <div class="app-shell__header-center" />
        </slot>
        <slot name="header-right">
          <div class="app-shell__header-right" />
        </slot>
      </header>
    </slot>

    <div v-if="showTabs" class="app-shell__tabs-bar">
      <slot name="tabs" />
    </div>

    <div class="app-shell__body">
      <aside
        v-if="showSidebar"
        class="app-shell__sidebar"
        :class="{ 'app-shell__sidebar--hidden': sidebarWidth === 0 }"
      >
        <slot name="sidebar" />
      </aside>

      <main class="app-shell__content">
        <slot />
      </main>
    </div>

    <footer v-if="$slots.footer" class="app-shell__footer">
      <slot name="footer" />
    </footer>
  </div>
</template>

<script setup>
defineProps({
  showSidebar: {
    type: Boolean,
    default: true
  },
  showTabs: {
    type: Boolean,
    default: false
  },
  sidebarWidth: {
    type: [Number, String],
    default: 240
  },
  sidebarCollapsible: {
    type: Boolean,
    default: false
  }
})
</script>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--el-bg-color-page, #f5f7fa);
}

.app-shell__header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--spacing-lg);
  background: #fff;
  border-bottom: 1px solid var(--el-border-color, #e5e6eb);
}

.app-shell__header-left,
.app-shell__header-center,
.app-shell__header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.app-shell__header-left {
  flex: 1;
  justify-content: flex-start;
}

.app-shell__header-center {
  flex: 2;
  justify-content: center;
}

.app-shell__header-right {
  flex: 1;
  justify-content: flex-end;
}

.app-shell__tabs-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  background: var(--el-bg-color, #fff);
  border-bottom: 1px solid var(--el-border-color, #e5e6eb);
  padding: 0 var(--spacing-md);
  min-height: 44px;
}

.app-shell__body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.app-shell__sidebar {
  flex-shrink: 0;
  background: var(--el-bg-color, #fff);
  border-right: 1px solid var(--el-border-color, #e5e6eb);
  overflow: hidden;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  width: 240px;
}

.app-shell__sidebar--hidden {
  width: 0;
  border-right: none;
}

.app-shell__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  /* [FIX 2026-06-20] overflow-y:auto 让内容在视口内滚动 (列表页表格 + landing page 长内容) */
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-md);
  min-height: 0;
}

.app-shell__footer {
  flex-shrink: 0;
  border-top: 1px solid var(--el-border-color, #e5e6eb);
  background: var(--el-bg-color, #fff);
}
</style>
