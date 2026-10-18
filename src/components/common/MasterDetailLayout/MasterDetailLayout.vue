<template>
  <div
    ref="rootRef"
    class="master-detail-layout"
    :class="{ 'master-detail-layout--collapsed': isCollapsed, 'master-detail-layout--resizing': isResizing }"
  >
    <aside
      :class="['master-detail-layout__sidebar', { 'master-detail-layout__sidebar--collapsed': isCollapsed }]"
      :style="sidebarStyle"
    >
      <!-- [窄屏抽屉 2026-10-18] 面板内 × 关闭按钮已移除。
           为什么不需要：关闭面板已有两条零成本路径 —— ① 顶部 GlobalToolbar 右下角的
           折叠钮（面板展开时依然可见可点）；② 点下方遮罩（标准 modal sheet dismissal）。
           原 × 需要 sidebar-content 让位 28px 纯占位行，在窄屏下挤占本已紧张的树区，
           且与 RelationScopeTree 刚加的窄屏 tab 行争夺空间。 -->
      <div class="master-detail-layout__sidebar-content">
        <slot name="master" />
      </div>
    </aside>

    <!-- [窄屏抽屉 2026-10-17] 遮罩层：盖住被面板遮住的内容，点击关闭。
         始终渲染、由 CSS 控制显隐（窄屏 + 展开态才可见）——避免在模板里判断视口宽度。
         z-index 低于 sidebar(30)、高于 detail 内容(0)，保证面板始终可交互。 -->
    <div class="master-detail-layout__scrim" @click="toggleCollapse" />

    <div
      v-if="showBorder && !isCollapsed"
      ref="resizerRef"
      class="master-detail-layout__resizer"
      :class="{ 'master-detail-layout__resizer--dragging': isResizing }"
      title="左右拖动调整宽度"
      @mousedown="startResize"
      @touchstart="startResize"
    >
      <span class="master-detail-layout__resizer-handle" aria-hidden="true" />
    </div>

    <main class="master-detail-layout__detail">
      <slot name="detail" />
      <slot name="empty" />
    </main>

    <!--
      折叠按钮：放在 layout 根级别（不是 sidebar 内部），避免 sidebar 折叠 width:0 时被 overflow:hidden 裁掉。
      通过 v-if 控制渲染，折叠态也显示以便用户重新展开。

      [Teleport 2026-10-17] collapseBtnTeleport：窄屏下把按钮搬到 layout 之外的容器
        （通常是顶部 GlobalToolbar），从而让侧栏收起态高度归零、免掉那条 24px 空横条。
        依据 Material Design 2 side sheets 指南：覆盖式面板的开启入口应放在 top app bar
        （"Common open affordances include action icons in top app bars"），
        而原实现把它压在 tab 行上、侧栏收起后只能靠一条空横条承载它。
        为什么必须 Teleport 而不能纯 CSS 偏移：本容器有 overflow:hidden，按钮是 absolute，
        无法越过容器边界 —— 用 bottom:100% 把它"贴"到上方 GlobalToolbar 区域（实测
        GlobalToolbar 底边恰等于本容器顶边，几何上完全可行）会被裁切规则直接剪掉。
        未传该 prop 时 :disabled，DOM 与引入前完全一致 —— 桌面端零影响。
    -->
    <Teleport
      v-if="sidebarCollapsible"
      :to="collapseBtnTeleport || 'body'"
      :disabled="!collapseBtnTeleport"
    >
      <button
        class="master-detail-layout__collapse-btn"
        :class="{ 'master-detail-layout__collapse-btn--collapsed': isCollapsed }"
        @click="toggleCollapse"
        :title="isCollapsed ? '展开侧边栏' : '折叠侧边栏'"
        :style="collapseBtnStyle"
        type="button"
      >
        <svg
          class="master-detail-layout__collapse-icon"
          :class="{ 'master-detail-layout__collapse-icon--collapsed': isCollapsed }"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  sidebarWidth: {
    type: String,
    default: '280px'
  },
  sidebarCollapsible: {
    type: Boolean,
    default: false
  },
  sidebarCollapsed: {
    type: Boolean,
    default: false
  },
  // [Teleport 2026-10-17] 折叠按钮的 Teleport 目标（CSS 选择器字符串或 DOM 元素）。
  //   传空串 = 按钮留在本容器内（引入本 prop 前的原始行为，桌面端走这条）。
  //   传目标 = 按钮被搬到该容器内，便于让侧栏收起态高度归零；
  //     目标容器需具备 position:relative 供按钮 absolute 定位。
  //   为什么需要它：本容器 overflow:hidden，按钮无法越界定位到上方工具栏。
  //   为什么 type 允许 Object：传 CSS 选择器时，Teleport 在挂载那一刻才
  //   querySelector 解析目标；若目标元素的 id 来自 fallthrough attrs（调用方透传），
  //   解析时序不可靠。直接传 DOM 元素可完全绕开该时序问题（实测踩过：传
  //   '#momp-global-toolbar' 时按钮整体消失，且生产构建下 Vue warning 被编译掉、
  //   控制台无任何线索）。Vue 的 Teleport :to 两者都支持。
  collapseBtnTeleport: {
    type: [String, Object],
    default: ''
  },
  showBorder: {
    type: Boolean,
    default: true
  },
  minWidth: {
    type: Number,
    default: 200
  },
  maxWidth: {
    type: Number,
    default: 500
  }
})

const emit = defineEmits(['update:sidebarCollapsed', 'collapse-change'])

const isCollapsed = computed(() => props.sidebarCollapsed)
const currentWidth = ref(parseInt(props.sidebarWidth, 10) || 280)
const isResizing = ref(false)
const rootRef = ref(null)
const resizerRef = ref(null)

const sidebarStyle = computed(() => {
  if (isCollapsed.value) {
    return { width: '0px' }
  }
  return { width: `${currentWidth.value}px` }
})

/**
 * 折叠按钮位置：始终位于 sidebar 右边缘外侧
 * - 展开态：left = sidebar 宽度，固定不动
 * - 折叠态：left = 8px（左对齐），方便用户找到
 */
const collapseBtnStyle = computed(() => {
  if (isCollapsed.value) {
    return { left: '8px' }
  }
  return { left: `${currentWidth.value - 12}px` }
})

function toggleCollapse() {
  const newState = !isCollapsed.value
  emit('update:sidebarCollapsed', newState)
  emit('collapse-change', newState)
}

function getClientX(event) {
  if (event.touches && event.touches.length) {
    return event.touches[0].clientX
  }
  if (event.changedTouches && event.changedTouches.length) {
    return event.changedTouches[0].clientX
  }
  return event.clientX
}

function getRootOffsetLeft() {
  if (!rootRef.value) return 0
  const rect = rootRef.value.getBoundingClientRect()
  return rect && typeof rect.left === 'number' ? rect.left : 0
}

function startResize(event) {
  if (isCollapsed.value) return

  isResizing.value = true
  document.addEventListener('mousemove', handleResize, { passive: false })
  document.addEventListener('mouseup', stopResize)
  document.addEventListener('touchmove', handleResize, { passive: false })
  document.addEventListener('touchend', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function handleResize(event) {
  if (!isResizing.value) return
  if (event && event.cancelable) event.preventDefault()

  const clientX = getClientX(event)
  const offsetLeft = getRootOffsetLeft()
  const newWidth = clientX - offsetLeft
  const minW = Number(props.minWidth) || 200
  const maxW = Number(props.maxWidth) || 500
  const clampedWidth = Math.min(maxW, Math.max(minW, Math.round(newWidth)))
  currentWidth.value = clampedWidth
}

function stopResize() {
  if (!isResizing.value) return
  isResizing.value = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
  document.removeEventListener('touchmove', handleResize)
  document.removeEventListener('touchend', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.body.style.overflow = ''
}

onMounted(async () => {
  await nextTick()
  const parsed = parseInt(props.sidebarWidth, 10)
  if (!Number.isNaN(parsed) && parsed > 0) {
    currentWidth.value = parsed
  }
})

onBeforeUnmount(() => {
  stopResize()
})
</script>

<style scoped>
.master-detail-layout {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--color-bg-primary);
  position: relative;
}

/* 拖拽中：禁用 sidebar 的 width transition 避免视觉延迟 */
.master-detail-layout--resizing .master-detail-layout__sidebar {
  transition: none !important;
}

.master-detail-layout__sidebar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-container);
  border-right: 1px solid var(--color-border);
  transition: width var(--transition-normal);
  overflow: hidden;
  position: relative;
  min-width: 0;
}

.master-detail-layout__sidebar--collapsed {
  width: 0 !important;
  border-right: none;
}

.master-detail-layout__sidebar-content {
  flex: 1;
  overflow: auto;
  min-width: 0;
}

/* [窄屏抽屉 2026-10-17] 遮罩的桌面端默认态。
   遮罩是窄屏专属（桌面侧栏常驻，没有"浮层"语义），故在媒体查询外先隐藏，
   只在 ≤768px 的媒体查询里打开 —— 保证桌面端渲染出该节点但不可见、不拦截点击。
   （节点始终渲染是为了让 CSS 独自决定显隐，避免在模板里判断视口宽度。） */
.master-detail-layout__scrim {
  display: none;
}

/* 拖拽分隔条：可见的握把 + 宽 hit 区域 */
.master-detail-layout__resizer {
  flex-shrink: 0;
  width: 12px;
  /* 负 margin-left 让 hit 区域跨越 sidebar 边缘 6px，hit-test 体验更好 */
  margin-left: -6px;
  margin-right: -6px;
  cursor: col-resize;
  background: transparent;
  position: relative;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 让 hit 区域不因 margin 收缩 */
  pointer-events: auto;
  touch-action: none;
}

.master-detail-layout__resizer-handle {
  width: 2px;
  height: 32px;
  background: var(--color-border);
  border-radius: 1px;
  transition: background 0.15s ease, height 0.15s ease;
  pointer-events: none;
  flex-shrink: 0;
}

.master-detail-layout__resizer:hover .master-detail-layout__resizer-handle,
.master-detail-layout__resizer--dragging .master-detail-layout__resizer-handle {
  background: var(--color-primary);
  height: 56px;
}

.master-detail-layout__detail {
  flex: 1;
  min-width: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

/*
 * 折叠按钮：放在 layout 根级别，避免 sidebar 折叠时 overflow:hidden 裁切
 * - 展开态：left = sidebar.width - 12 (盖在 sidebar 右边线上)
 * - 折叠态：left = 8px (独立显示在左边缘)
 */
.master-detail-layout__collapse-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-container);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  z-index: 20;
  color: var(--color-text-secondary);
  transition: background-color 0.15s ease, color 0.15s ease, left var(--transition-normal), border-radius 0.15s ease;
  padding: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.master-detail-layout__collapse-btn:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  z-index: 21;
}

.master-detail-layout__collapse-btn--collapsed {
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.12);
}

.master-detail-layout__collapse-icon {
  width: 16px;
  height: 16px;
  transition: transform var(--transition-normal);
}

.master-detail-layout__collapse-icon--collapsed {
  transform: rotate(180deg);
}

@media (max-width: 768px) {
  .master-detail-layout {
    flex-direction: column;
  }

  /* [窄屏抽屉 2026-10-17] 侧栏由「上下堆叠」改为「覆盖式面板」。
   *   规范依据（三处官方口径一致）：
   *     - Material Design 3 / M1 Lists："Layouts under 600dp wide may fill the screen
   *       with a single level of content hierarchy" —— 手机上不该同时呈现两层内容；
   *     - OpenUI5（SAP 官方 SDK）："on a phone device … only one column can be
   *       displayed at a time"；
   *     - PatternFly primary-detail：移动端 detail "slide in and overlay the primary
   *       component"，primary 保持全宽。
   *   改成 absolute 脱离文档流后，侧栏展开不再挤压下方 detail —— 内容区高度恒定，
   *   关闭面板即立刻恢复（堆叠式要等布局回弹）。
   *   max-height 从 40vh 提到 70vh：面板现在是覆盖层、可滚动，给足空间容纳树节点，
   *   且遮罩提示"这是浮层"不会让人以为下方内容被永久挤走。
   *   z-index 30 高于遮罩 25，确保面板始终可点。 */
  .master-detail-layout__sidebar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 30;
    width: 100% !important;
    max-height: 70vh;
    border-right: none;
    border-bottom: 1px solid var(--color-border);
    /* [P1 2026-10-18] 面板底边归属感：原 0 4px 16px/0.12 的阴影在浅灰底内容上几乎
       看不见，截图里"关系范围/过滤条件"两条浅灰 header 视觉上像是漏在面板外。
       改成向下更明确的双层阴影 + 顶部一道高光，让"这里是浮层的下边界"一眼可读。 */
    box-shadow:
      0 -1px 0 0 rgba(255, 255, 255, 0.6) inset,
      0 6px 16px -4px rgba(0, 0, 0, 0.18),
      0 12px 28px -8px rgba(0, 0, 0, 0.12);
    transition: transform 0.22s ease, opacity 0.22s ease;
  }

  .master-detail-layout__sidebar--collapsed {
    /* 收起态：整体上移出容器（被 overflow:hidden 裁掉，等效隐藏）+ 不接收指针事件。
     *   为什么用 transform 而非 height:0 / display:none：后两者不可过渡，
     *   展开/收起会瞬时跳变；transform 可平滑动画，且 absolute 元素移出后
     *   仍不占文档流位置，detail 高度不受影响。 */
    transform: translateY(-100%);
    opacity: 0;
    pointer-events: none;
    border-bottom: none;
  }

  /* 展开态：归位。不写这条也可以（默认值即此），显式写出以明确覆盖收起态的 transform。 */
  .master-detail-layout:not(.master-detail-layout--collapsed) .master-detail-layout__sidebar {
    transform: translateY(0);
    opacity: 1;
  }

  /* 遮罩：仅窄屏 + 展开态显示。盖住被面板遮住的内容，点击关闭（标准 sheet 行为）。
     桌面端不显示 —— 桌面侧栏常驻，没有"浮层"语义，加遮罩反而是错的。 */
  .master-detail-layout:not(.master-detail-layout--collapsed) .master-detail-layout__scrim {
    display: block;
    position: absolute;
    inset: 0;
    z-index: 25;
    background: rgba(0, 0, 0, 0.35);
  }

  /* [窄屏抽屉 2026-10-18] 原面板内 × 关闭按钮的样式与 sidebar-content 的 28px 让位
     已一并移除 —— 关闭入口由 GlobalToolbar 折叠钮 + 点遮罩承担，那 28px 归还给树区。 */

  /* [P0 补正 · 2026-10-18] 解除各 scope 树容器的 min-height 硬地板。
     背景：四个生产页面（archdata / 往来单位 / 物料 / 组织）各自的 scope 树都写了
     `min-height: 150px`，本意是「桌面端别让树太矮」。但窄屏下面板改为覆盖式后，
     面板高度由内容自适应、远小于桌面，这 150px 反而成了下限 —— 树被锁死在
     150px ≈ 3.8 行，末行仍被切一半（用户在 archdata 截图里报的原问题）。

     为什么写在 MDL 而不是各自组件里改：三个树组件的类名各不相同
     （.pgst- / .igst- / .ost- / .oss-），逐个改要动 4 个文件、且将来新增页面
     一定会再踩同一个坑。而它们在结构上都是本组件 #master slot 的后代 ——
     在这里用一条 descendant 规则即可统一覆盖，且天然对将来接入的页面生效。

     桌面端不受影响：整条规则在 max-width:768px 媒体查询内。
     解除后树由 flex:1 吃满面板可用高度（面板有 max-height:70vh 天花板兜底）。 */
  .master-detail-layout__sidebar-content :deep(.pgst-tree-container),
  .master-detail-layout__sidebar-content :deep(.igst-tree-container),
  .master-detail-layout__sidebar-content :deep(.ost-tree-container),
  .master-detail-layout__sidebar-content :deep(.oss-tree-container),
  .master-detail-layout__sidebar-content :deep(.rss-tree-container),
  .master-detail-layout__sidebar-content :deep(.rst-tree-container) {
    min-height: 0;
  }

  .master-detail-layout__resizer {
    display: none;
  }

  /* [移动端折叠按钮 · 2026-10-17] 定位改为「顶部 GlobalToolbar 右下角」。
     *   该按钮经 Teleport 挂在 #momp-global-toolbar 内（见模板 collapseBtnTeleport），
     *   那里 position:relative，按钮以它的 padding box 为包含块。
     *   bottom:0 ⇒ 按钮底边贴在工具栏底边（实测两者底/顶在 y=163 严格相接），
     *   正好是「底边对齐」；不依赖工具栏高度（实测 46/47/74px 三种，早期按固定高度
     *   做负偏移的方案已在 archdata 上被证伪并放弃）。
     *   right:0 + 工具栏右侧实测空 134~238px，按钮 48px 不与任何图标重叠。
     *   外部标记 !important 是为压过行内 collapseBtnStyle 的 left/top（那是桌面端
     *   贴侧栏中部用的同一套变量，不能让窄屏继承）。 */
  .master-detail-layout__collapse-btn {
    top: auto !important;
    bottom: 0;
    right: 0;
    left: auto !important;
    transform: none;
    border-radius: 0 0 0 var(--radius-sm);
    width: 48px;
    height: 24px;
  }

  .master-detail-layout__collapse-icon {
    transform: rotate(-90deg);
  }

  .master-detail-layout__collapse-icon--collapsed {
    transform: rotate(90deg);
  }
}
</style>
