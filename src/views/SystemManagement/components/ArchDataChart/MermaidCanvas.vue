<!--
  MermaidCanvas - 轻量级 Mermaid 画布组件

  所属模块：嵌入式图表视图（Phase 5）
  主要功能：
    - 接收 mermaidText，调用 mermaid.run() 渲染为 SVG
    - 视口保持（preserveViewport）：跨渲染保留 scrollLeft/scrollTop + transform
    - 节点点击事件透传（emit node-click）
    - mermaid 库本身渲染失败 try-catch（契约：5.10.4 ④ 未覆盖项）
    - 基础平移/缩放（wheel + drag）

  契约：见 chart-data-flow-and-interaction-upgrade.md §5.4.2 / §5.4.3 / §5.10.4 ④

  Props:
    - mermaidText: String (required) - mermaid 语法文本
    - loading: Boolean (default false) - 显示渲染中遮罩
    - preserveViewport: Boolean (default true) - 是否在重新渲染时保持视口
    - chartType: String (default 'businessObject') - 用于 mermaid.initialize 的 theme 配置

  Emits:
    - node-click: { id, type, dataset } - 节点点击
    - render-complete: { nodeCount, elapsedMs } - 渲染完成
    - render-error: { error, phase } - 渲染失败（phase: 'parse' | 'render' | 'other'）

  设计原则：
    - 轻量：不引入 useInteraction / useSvgProcessor / useTooltip 等重型 composable
    - 自洽：内部管理视口状态，对外只暴露 mermaidText + 事件
    - 健壮：mermaid.run() 失败时降级为 <pre> 显示源码 + 错误提示
-->
<template>
  <div
    ref="canvasRootRef"
    class="mermaid-canvas"
    :class="{ 'is-dragging': isDragging }"
  >
    <!-- 渲染中遮罩（保留上次 SVG，避免白屏） -->
    <div v-if="loading" class="mermaid-canvas__mask">
      <el-icon class="is-loading" :size="20"><Loading /></el-icon>
      <span>渲染中...</span>
    </div>

    <!-- 渲染失败提示 -->
    <div v-if="renderError" class="mermaid-canvas__error">
      <el-icon :size="20"><WarningFilled /></el-icon>
      <span class="mermaid-canvas__error-msg">
        {{ renderError.phase === 'parse' ? '语法解析失败' : '渲染失败' }}:
        {{ renderError.message }}
      </span>
      <details class="mermaid-canvas__error-detail">
        <summary>查看 mermaid 源码</summary>
        <pre>{{ mermaidText }}</pre>
      </details>
    </div>

    <!-- 主体：mermaid 渲染容器 -->
    <div
      ref="viewportRef"
      class="mermaid-canvas__viewport"
      @wheel.passive="handleWheel"
      @mousedown="handleDragStart"
    >
      <div ref="contentRef" class="mermaid-canvas__content">
        <!-- mermaid.run() 会把 <pre class="mermaid"> 替换为 <svg> -->
      </div>
    </div>

    <!-- 右下角：重置视图按钮 -->
    <div class="mermaid-canvas__toolbar">
      <button
        class="mermaid-canvas__btn"
        type="button"
        title="重置视图"
        @click="resetViewport"
      >
        <el-icon :size="14"><Refresh /></el-icon>
      </button>
      <span class="mermaid-canvas__zoom">{{ Math.round(scale * 100) }}%</span>
    </div>
  </div>
</template>

<script setup>
/**
 * MermaidCanvas - Phase 5
 *
 * 数据流：
 *   1. props.mermaidText 变化 → watch 触发
 *   2. preserveViewport 保存当前 scrollLeft/scrollTop/transform
 *   3. mermaid.run() 渲染 SVG → contentRef 内部
 *   4. 节点点击事件委托（addEventListener）
 *   5. preserveViewport 恢复视口
 *   6. emit render-complete / render-error
 *
 * 视口状态：
 *   - scrollLeft/scrollTop：viewportRef 的滚动位置
 *   - transform：contentRef 的 transform: translate() scale()
 *   - scale：当前缩放比例
 */
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import mermaid from 'mermaid'
import { Loading, WarningFilled, Refresh } from '@element-plus/icons-vue'

const props = defineProps({
  mermaidText: {
    type: String,
    required: true
  },
  loading: {
    type: Boolean,
    default: false
  },
  preserveViewport: {
    type: Boolean,
    default: true
  },
  chartType: {
    type: String,
    default: 'businessObject',
    validator: (v) => ['businessObject', 'serviceModule'].includes(v)
  }
})

const emit = defineEmits(['node-click', 'render-complete', 'render-error'])

// ============================================================
// Refs
// ============================================================
const canvasRootRef = ref(null)
const viewportRef = ref(null)
const contentRef = ref(null)

// ============================================================
// 视口状态
// ============================================================
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const isDragging = ref(false)
let dragStart = { x: 0, y: 0, scrollLeft: 0, scrollTop: 0 }

// ============================================================
// 渲染状态
// ============================================================
const renderError = ref(null) // { message, phase, detail? }
let isRendering = false // 防止并发渲染
let mermaidInitialized = false

// ============================================================
// Mermaid 初始化（仅一次）
// ============================================================
function ensureMermaidInitialized() {
  if (mermaidInitialized) return
  try {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'loose',
      flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        curve: 'basis'
      }
    })
    mermaidInitialized = true
  } catch (e) {
    console.error('[MermaidCanvas] mermaid.initialize failed:', e)
    renderError.value = {
      message: e?.message || String(e),
      phase: 'init'
    }
    emit('render-error', { error: e, phase: 'init' })
  }
}

// ============================================================
// 视口保持：保存/恢复
// ============================================================
function saveViewport() {
  if (!props.preserveViewport) return null
  const viewport = viewportRef.value
  const content = contentRef.value
  if (!viewport || !content) return null

  return {
    scrollLeft: viewport.scrollLeft,
    scrollTop: viewport.scrollTop,
    transform: content.style.transform || '',
    scale: scale.value,
    translateX: translateX.value,
    translateY: translateY.value
  }
}

function restoreViewport(saved) {
  if (!saved || !props.preserveViewport) return
  const viewport = viewportRef.value
  const content = contentRef.value
  if (!viewport || !content) return

  // 恢复 transform
  content.style.transform = saved.transform || `translate(${saved.translateX}px, ${saved.translateY}px) scale(${saved.scale})`
  scale.value = saved.scale
  translateX.value = saved.translateX
  translateY.value = saved.translateY

  // 恢复 scroll 位置（nextTick 后 DOM 已应用 transform，scroll 才有效）
  nextTick(() => {
    if (viewportRef.value) {
      viewportRef.value.scrollLeft = saved.scrollLeft
      viewportRef.value.scrollTop = saved.scrollTop
    }
  })
}

// ============================================================
// 核心：渲染 mermaid
// ============================================================
async function renderMermaid() {
  // 防止并发渲染（watch 触发 + 防抖可能重叠）
  if (isRendering) return
  if (!props.mermaidText) {
    if (contentRef.value) contentRef.value.innerHTML = ''
    return
  }

  isRendering = true
  renderError.value = null

  // Step 1: 保存视口
  const savedViewport = saveViewport()

  // Step 2: 确保 mermaid 已初始化
  ensureMermaidInitialized()
  if (!mermaidInitialized) {
    isRendering = false
    return
  }

  const startTime = performance.now()

  try {
    // Step 3: 准备渲染容器（mermaid 需要 <pre class="mermaid"> 或 <div class="mermaid">）
    if (!contentRef.value) {
      isRendering = false
      return
    }

    // 注入 mermaid 源码（mermaid.run() 会把 .mermaid 元素转换为 SVG）
    // 用唯一 ID 避免 mermaid 内部缓存冲突
    const renderId = `mc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    contentRef.value.innerHTML = `<pre class="mermaid" data-render-id="${renderId}">${escapeHtml(props.mermaidText)}</pre>`

    // Step 4: 调用 mermaid.run() 渲染
    await mermaid.run({
      nodes: contentRef.value.querySelectorAll('.mermaid')
    })

    // Step 5: 绑定节点点击事件（事件委托）
    bindNodeClickEvents()

    // Step 6: 恢复视口
    restoreViewport(savedViewport)

    // Step 7: 统计节点数（用于 emit）
    const nodeCount = contentRef.value.querySelectorAll('.node').length
    const elapsedMs = Math.round(performance.now() - startTime)

    emit('render-complete', { nodeCount, elapsedMs })
  } catch (err) {
    // 契约 5.10.4 ④：mermaid 库本身渲染失败 try-catch
    console.error('[MermaidCanvas] mermaid.run() failed:', err)

    const phase = err?.name === 'ParseError' || /parse/i.test(err?.message || '')
      ? 'parse'
      : 'render'

    renderError.value = {
      message: err?.message || String(err),
      phase
    }
    emit('render-error', { error: err, phase })

    // 降级：保留 mermaid 源码在 <pre> 中（让用户看到源码 + 错误）
  } finally {
    isRendering = false
  }
}

// ============================================================
// 节点点击事件委托
// ============================================================
function bindNodeClickEvents() {
  if (!contentRef.value) return

  const nodes = contentRef.value.querySelectorAll('.node, .node-id')
  nodes.forEach(node => {
    node.style.cursor = 'pointer'
    node.addEventListener('click', handleNodeClick, { once: false })
  })
}

function handleNodeClick(event) {
  // 找到最近的 .node 元素
  const target = event.currentTarget
  if (!target) return

  // 提取节点 ID（mermaid 通常用 id="flowchart-N0-..." 或 class="node default" data-id="xxx"）
  const nodeId = target.id || target.getAttribute('data-id') || target.getAttribute('data-node-id') || ''

  emit('node-click', {
    id: nodeId,
    type: 'node',
    dataset: { ...target.dataset },
    text: target.textContent?.trim() || ''
  })
}

// ============================================================
// HTML 转义（防止 mermaid 源码中的 < > 被浏览器解析）
// ============================================================
function escapeHtml(str) {
  if (!str) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// ============================================================
// 平移与缩放
// ============================================================
function handleWheel(event) {
  // Ctrl + 滚轮 = 缩放
  if (event.ctrlKey || event.metaKey) {
    event.preventDefault()
    const delta = event.deltaY > 0 ? 0.9 : 1.1
    setScale(scale.value * delta)
    return
  }
  // 普通滚轮 = 平移（浏览器默认行为，无需处理）
}

function handleDragStart(event) {
  // 左键 + 未点击节点时才拖动
  if (event.button !== 0) return
  // 如果点击目标是节点内部，不拖动（避免影响节点点击）
  if (event.target.closest('.node')) return

  isDragging.value = true
  const viewport = viewportRef.value
  dragStart = {
    x: event.clientX,
    y: event.clientY,
    scrollLeft: viewport?.scrollLeft || 0,
    scrollTop: viewport?.scrollTop || 0
  }

  document.addEventListener('mousemove', handleDragMove)
  document.addEventListener('mouseup', handleDragEnd)
}

function handleDragMove(event) {
  if (!isDragging.value) return
  const viewport = viewportRef.value
  if (!viewport) return

  const dx = event.clientX - dragStart.x
  const dy = event.clientY - dragStart.y
  viewport.scrollLeft = dragStart.scrollLeft - dx
  viewport.scrollTop = dragStart.scrollTop - dy
}

function handleDragEnd() {
  isDragging.value = false
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
}

function setScale(newScale) {
  // 限制缩放范围 [0.2, 5]
  scale.value = Math.min(5, Math.max(0.2, newScale))
  if (contentRef.value) {
    contentRef.value.style.transform = `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`
  }
}

function resetViewport() {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
  if (contentRef.value) {
    contentRef.value.style.transform = ''
  }
  if (viewportRef.value) {
    viewportRef.value.scrollLeft = 0
    viewportRef.value.scrollTop = 0
  }
}

// ============================================================
// Watch + 生命周期
// ============================================================
watch(() => props.mermaidText, () => {
  renderMermaid()
})

watch(() => props.chartType, () => {
  // chartType 变化时重新初始化 mermaid（theme 可能不同）
  mermaidInitialized = false
  renderMermaid()
})

onMounted(async () => {
  await nextTick()
  if (props.mermaidText) {
    renderMermaid()
  }
})

onBeforeUnmount(() => {
  // 清理事件监听
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)

  // 清理节点点击事件
  if (contentRef.value) {
    const nodes = contentRef.value.querySelectorAll('.node, .node-id')
    nodes.forEach(node => node.removeEventListener('click', handleNodeClick))
  }
})

// 暴露方法给父组件（允许 EmbeddedChartView 主动触发渲染）
defineExpose({
  render: renderMermaid,
  resetViewport,
  setScale
})
</script>

<style lang="scss" scoped>
.mermaid-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--color-bg-primary, #fff);
}

.mermaid-canvas__viewport {
  width: 100%;
  height: 100%;
  overflow: auto;
  cursor: grab;
}

.mermaid-canvas.is-dragging .mermaid-canvas__viewport {
  cursor: grabbing;
}

.mermaid-canvas__content {
  display: inline-block;
  min-width: 100%;
  min-height: 100%;
  padding: var(--spacing-md, 16px);
  transform-origin: 0 0;
  transition: transform 0.05s linear;
}

/* mermaid SVG 自适应 */
.mermaid-canvas__content :deep(svg) {
  max-width: none;
  display: block;
  margin: 0 auto;
}

/* 节点 hover 提示 */
.mermaid-canvas__content :deep(.node) {
  transition: opacity 0.15s;
}

.mermaid-canvas__content :deep(.node:hover) {
  opacity: 0.85;
}

/* 渲染中遮罩 */
.mermaid-canvas__mask {
  position: absolute;
  top: var(--spacing-sm, 8px);
  right: var(--spacing-sm, 8px);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 4px);
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--color-border, #e4e7ed);
  border-radius: 4px;
  font-size: 12px;
  color: var(--color-text-secondary, #606266);
  pointer-events: none;
  z-index: 10;
}

/* 渲染失败提示 */
.mermaid-canvas__error {
  position: absolute;
  top: var(--spacing-md, 16px);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs, 4px);
  padding: var(--spacing-md, 16px);
  background: #fef0f0;
  border: 1px solid #f56c6c;
  border-radius: 4px;
  font-size: 13px;
  color: #f56c6c;
  max-width: 80%;
  z-index: 20;
}

.mermaid-canvas__error-msg {
  font-weight: 500;
}

.mermaid-canvas__error-detail {
  margin-top: var(--spacing-xs, 4px);
  font-size: 12px;
  color: var(--color-text-secondary, #606266);
  max-height: 200px;
  overflow: auto;
}

.mermaid-canvas__error-detail pre {
  margin: 4px 0 0;
  padding: var(--spacing-xs, 4px) var(--spacing-sm, 8px);
  background: rgba(255, 255, 255, 0.6);
  border-radius: 2px;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
  max-width: 600px;
}

/* 右下角工具栏 */
.mermaid-canvas__toolbar {
  position: absolute;
  bottom: var(--spacing-sm, 8px);
  right: var(--spacing-sm, 8px);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 4px);
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--color-border, #e4e7ed);
  border-radius: 4px;
  font-size: 12px;
  color: var(--color-text-secondary, #606266);
  z-index: 10;
}

.mermaid-canvas__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 2px;
  cursor: pointer;
  color: var(--color-text-secondary, #606266);
  transition: background 0.15s;
}

.mermaid-canvas__btn:hover {
  background: rgba(0, 0, 0, 0.06);
}

.mermaid-canvas__btn:active {
  background: rgba(0, 0, 0, 0.1);
}

.mermaid-canvas__zoom {
  min-width: 40px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
