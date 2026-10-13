<template>
  <div class="app-shell">
    <slot name="header">
      <header class="app-shell__header">
        <slot name="header-left">
          <div class="app-shell__header-left">
            <slot name="logo" />
          </div>
        </slot>
        <!-- [FIX 2026-10-13 移动端] 原 fallback 是空 div 却带 flex:2，
             白占 33% 宽度，与 TopNavHeader 已删除的 .app-header__center 同源。
             现改为纯 slot，宽度分配由调用方内容自身的 class 决定
             （app-shell__header-center），不再由组件强加。 -->
        <slot name="header-center" />
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

      <!-- [FIX2026-10-12 移动端] 侧栏转抽屉后的遮罩层，仅窄屏显示。
           桌面端抽屉是常驻侧栏，不需要遮罩。 -->
      <div
        v-if="showSidebar && sidebarWidth !== 0"
        class="app-shell__scrim"
        @click="$emit('scrim-click')"
      />

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

// [2026-10-12 移动端] 遮罩点击时通知父级关闭抽屉。
// 桌面端该事件不触发（遮罩 display:none），父子通信契约保持单向可控。
defineEmits(['scrim-click'])
</script>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  /* [FIX 2026-10-12 移动端] 100vh 在手机浏览器上是"地址栏收起时"的视口高度，
     地址栏展开/收起会导致布局跳动。100dvh 表示"地址栏展开时"的真实视口，
     配合 100vh 回退，老浏览器仍可用。 */
  height: 100vh;
  height: 100dvh;
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
.app-shell__header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  /* [FIX 2026-10-13 移动端] 允许收缩，否则内部长中文会撑破 header */
  min-width: 0;
}

.app-shell__header-left {
  flex: 1;
  justify-content: flex-start;
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

/* [2026-10-12 移动端] 侧栏遮罩层：桌面端不显示（常驻侧栏无需遮挡）。 */
.app-shell__scrim {
  display: none;
}

.app-shell__content {
  flex: 1;
  display: flex;
  flex-direction: column;
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

/* ==========================================================================
   [2026-10-12 移动端适配] ≤768px：把"侧栏+内容"改为"抽屉+内容"
   改造前：240px 固定侧栏 + flex-shrink:0 → 375px 屏上内容区仅剩 135px
   改造后：侧栏浮层抽屉，默认收起，overlay 遮罩，点击遮罩关闭
   ========================================================================== */
@media screen and (max-width: 768px) {
  .app-shell__header {
    padding: 0 var(--spacing-md);
    /* 刘海屏/底部小黑条避让：env() 在无安全区的浏览器上回退为 0，
       故可无条件书写。配合 index.html 的 viewport-fit=cover 生效。 */
    padding-top: env(safe-area-inset-top, 0px);
    padding-left: calc(var(--spacing-md) + env(safe-area-inset-left, 0px));
    padding-right: calc(var(--spacing-md) + env(safe-area-inset-right, 0px));
  }

  .app-shell__tabs-bar {
    padding: 0 var(--spacing-sm);
  }

  /* 侧栏脱离文档流，浮于内容之上 */
  .app-shell__sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 2002;
    width: 240px;
    /* 抽屉模式用 translate 动画，避免与 width 过渡冲突 */
    transform: translateX(0);
    transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1),
                box-shadow 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.12);
    /* iOS 独立滚动容器必须显式设置，否则侧栏内容无法滚动 */
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    /* 刘海屏: 侧栏顶到 left:0 会被状态栏/摄像头区域遮挡 */
    padding-top: env(safe-area-inset-top, 0px);
    padding-left: env(safe-area-inset-left, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }

  /* 收起态：移出屏幕左侧。注意 width 保持 240px，
     否则展开动画会因 width 变化产生挤压抖动 */
  .app-shell__sidebar--hidden {
    width: 240px;
    border-right: 1px solid var(--el-border-color, #e5e6eb);
    transform: translateX(-100%);
    box-shadow: none;
  }

  .app-shell__scrim {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 2001;
    background: rgba(0, 0, 0, 0.35);
    border: none;
  }

  .app-shell__content {
    /* 抽屉不再占位，内容区占满整个宽度 */
    width: 100%;
    /* 放开横向裁切：宽表格需要横向滚动才能读，
       裁切会导致内容直接消失（数据不可见比滚动更糟） */
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding: var(--spacing-sm);
  }
}
</style>
