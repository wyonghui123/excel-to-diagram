<template>
  <div class="help-accordion">
    <div v-if="loading" class="help-accordion__status">加载场景中…</div>
    <div v-else-if="error" class="help-accordion__status help-accordion__status--error">
      {{ error }}
    </div>
    <template v-else-if="scenario">
      <div class="help-accordion__header">
        <h2 class="help-accordion__title">{{ scenario.title }}</h2>
        <p v-if="scenario.summary" class="help-accordion__summary">{{ scenario.summary }}</p>
      </div>
      <div class="help-accordion__steps">
        <AppCollapse
          v-for="(step, idx) in scenario.steps"
          :key="step.step_no"
          :default-expanded="defaultExpandedSet.has(step.step_no) || (!hasInitialStep && idx === 0)"
          size="md"
          class="help-accordion__step"
        >
          <template #header>
            <span class="help-accordion__step-num">
              {{ String(step.step_no).padStart(2, '0') }}
            </span>
            <span class="help-accordion__step-title">{{ step.title }}</span>
          </template>
          <div class="help-accordion__step-body">
            <div v-if="step.video" class="help-accordion__media">
              <!-- [FIX v6] video-wrap 做全屏元素而非 video，这样 subtitle 天然可见 -->
              <div
                :ref="(el) => registerVideoWrap(el, step.step_no)"
                class="help-accordion__video-wrap"
              >
                <video
                  :ref="(el) => registerVideo(el, step.step_no)"
                  :src="videoUrl(step.video)"
                  :poster="step.screenshot ? screenshotUrl(step.screenshot) : undefined"
                  class="help-accordion__video"
                  controls
                  preload="metadata"
                  playsinline
                  disablepictureinpicture
                  @error="onVideoError($event, step.step_no)"
                  @timeupdate="onTimeUpdate($event, step.step_no)"
                  @seeked="onTimeUpdate($event, step.step_no)"
                  @loadedmetadata="onTimeUpdate($event, step.step_no)"
                ></video>
                <div
                  :ref="(el) => registerSubtitle(el, step.step_no)"
                  class="help-accordion__subtitle"
                  :class="{
                    'is-active': !!subtitleTexts[step.step_no]
                  }"
                >
                  {{ subtitleTexts[step.step_no] || '​' }}
                </div>
                <!-- 全屏按钮: 拦截原生 video 全屏，改为 wrapper 全屏 -->
                <button
                  class="help-accordion__fs-btn"
                  title="全屏"
                  @click.stop="toggleWrapperFullscreen(step.step_no)"
                >
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
                </button>
              </div>
              <div v-if="videoErrors[step.step_no]" class="help-accordion__media-fallback">
                <img
                  v-if="step.screenshot"
                  :src="screenshotUrl(step.screenshot)"
                  :alt="step.title"
                  class="help-accordion__screenshot"
                />
                <p class="help-accordion__media-fallback-hint">视频加载失败，已回退到静态截图</p>
              </div>
            </div>
            <img
              v-else-if="step.screenshot"
              :src="screenshotUrl(step.screenshot)"
              :alt="step.title"
              class="help-accordion__screenshot"
              loading="lazy"
              @error="onScreenshotError"
            />
            <div class="help-accordion__field">
              <div class="help-accordion__field-label">操作</div>
              <div class="help-accordion__field-value">{{ step.action }}</div>
            </div>
            <div class="help-accordion__field">
              <div class="help-accordion__field-label">预期结果</div>
              <div class="help-accordion__field-value">{{ step.expected }}</div>
            </div>
            <div v-if="step.tip" class="help-accordion__tip">
              <span class="help-accordion__tip-label">提示</span>
              <span class="help-accordion__tip-text">{{ step.tip }}</span>
            </div>
          </div>
        </AppCollapse>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, reactive, onBeforeUnmount, nextTick, computed } from 'vue'
import { AppCollapse } from '@/components/common'

const props = defineProps({
  scenarioId: {
    type: String,
    required: true
  },
  // [FIX P3 2026-06-30] URL ?step= 指定初始展开的步骤, 传 null 则默认展开第 1 步
  initialStep: {
    type: Number,
    default: null
  }
})

const scenario = ref(null)
const loading = ref(false)
const error = ref('')
const videoErrors = reactive({})
const subtitleTexts = reactive({})
const videoMap = reactive({})
const subtitleMap = reactive({})
const videoWrapMap = reactive({})
const isFullscreen = ref(false)
const fullscreenStepNo = ref(null)

function screenshotUrl(filename) {
  return `/docs/scenarios/${props.scenarioId}/${filename}`
}

function videoUrl(filename) {
  return `/docs/scenarios/${props.scenarioId}/${filename}`
}

function onScreenshotError(e) {
  e.target.style.display = 'none'
}

function onVideoError(e, stepNo) {
  videoErrors[stepNo] = true
  if (e?.target) e.target.style.display = 'none'
}

function computeSubtitle(stepNo, currentTime) {
  const step = scenario.value?.steps?.find(s => s.step_no === stepNo)
  if (!step?.subtitles?.length) return ''
  const cue = step.subtitles.find(c => currentTime >= c.start && currentTime < c.end)
  return cue?.text || ''
}

function onTimeUpdate(e, stepNo) {
  const t = e.target.currentTime
  subtitleTexts[stepNo] = computeSubtitle(stepNo, t)
}

function registerVideoWrap(el, stepNo) {
  if (el) videoWrapMap[stepNo] = el
}

function registerVideo(el, stepNo) {
  if (el) videoMap[stepNo] = el
}

function registerSubtitle(el, stepNo) {
  if (el) subtitleMap[stepNo] = el
}

// [FIX v6] 全屏改为 wrapper div 做全屏元素，subtitle 天然可见
// video-wrap > video + subtitle + fs-btn 都在 fullscreen 渲染上下文中
async function toggleWrapperFullscreen(stepNo) {
  const wrap = videoWrapMap[stepNo]
  if (!wrap) return
  try {
    if (document.fullscreenElement === wrap) {
      await document.exitFullscreen()
    } else {
      await wrap.requestFullscreen()
    }
  } catch (e) {
    // 静默失败
  }
}

function handleFullscreenChange() {
  let activeStepNo = null
  for (const stepNoStr of Object.keys(videoWrapMap)) {
    const stepNo = Number(stepNoStr)
    const wrap = videoWrapMap[stepNo]
    if (wrap && document.fullscreenElement === wrap) {
      activeStepNo = stepNo
      break
    }
  }
  fullscreenStepNo.value = activeStepNo
  isFullscreen.value = activeStepNo !== null
}

async function loadScenario() {
  if (!props.scenarioId) return
  loading.value = true
  error.value = ''
  scenario.value = null
  try {
    const resp = await fetch(`/docs/scenarios/${props.scenarioId}/scenario.json`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    scenario.value = await resp.json()
    for (const step of scenario.value?.steps || []) {
      if (step.video) subtitleTexts[step.step_no] = ''
    }
  } catch (e) {
    error.value = `场景「${props.scenarioId}」加载失败：${e.message}`
  } finally {
    loading.value = false
  }
}

// [FIX P3 2026-06-30] 计算初始展开: URL ?step=2 时只展开 step_no=2, 否则展开第 1 步
const hasInitialStep = computed(() => Number.isFinite(props.initialStep))
const defaultExpandedSet = computed(() => {
  if (!hasInitialStep.value) return new Set()
  return new Set([props.initialStep])
})

watch(() => props.scenarioId, loadScenario)
onMounted(() => {
  loadScenario()
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<style scoped>
.help-accordion {
  padding: 16px 24px 32px;
  height: 100%;
  overflow-y: auto;
}

.help-accordion__status {
  padding: 32px;
  text-align: center;
  color: var(--el-text-color-secondary, #86909c);
  font-size: 14px;
}

.help-accordion__status--error {
  color: var(--el-color-danger, #f56c6c);
}

.help-accordion__header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-light, #ebeef5);
}

.help-accordion__title {
  margin: 0 0 4px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary, #1d2129);
}

.help-accordion__summary {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary, #86909c);
  line-height: 1.5;
}

.help-accordion__steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.help-accordion__step :deep(.app-collapse__header) {
  padding: 12px 16px;
  align-items: center;
}

.help-accordion__step :deep(.app-collapse__header-content) {
  display: flex;
  align-items: center;
  gap: 12px;
}

.help-accordion__step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--yonyou-orange-50, #fff7ed);
  color: var(--yonyou-orange-600, #ea580c);
  font-size: 12px;
  font-weight: 700;
  font-family: 'Menlo', 'Consolas', monospace;
  flex-shrink: 0;
}

.help-accordion__step-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary, #1d2129);
}

.help-accordion__step-body {
  padding: 0 4px 4px;
}

.help-accordion__screenshot {
  width: 100%;
  max-height: 480px;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter, #f0f0f0);
  margin-bottom: 16px;
  background: var(--el-fill-color-blank, #ffffff);
}

.help-accordion__media {
  margin-bottom: 16px;
}

.help-accordion__video-wrap {
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  background: #000;
}

/* [FIX v6] wrapper 全屏时: 视频撑满 + 黑背景 + 字幕居中底部 */
.help-accordion__video-wrap:fullscreen {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0;
}

.help-accordion__video-wrap:fullscreen .help-accordion__video {
  max-width: 100vw;
  max-height: 100vh;
  width: auto;
  height: auto;
}

.help-accordion__video-wrap:fullscreen .help-accordion__subtitle {
  bottom: 80px;
  font-size: 20px;
  padding: 10px 22px;
}

.help-accordion__video {
  width: 100%;
  max-height: 480px;
  display: block;
}

/* 隐藏原生 video 全屏按钮，防止用户误触浏览器原生全屏 */
.help-accordion__video::-webkit-media-controls-fullscreen-button {
  display: none !important;
}

/* 自定义全屏按钮 */
.help-accordion__fs-btn {
  position: absolute;
  right: 10px;
  bottom: 10px;
  z-index: 20;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.help-accordion__video-wrap:hover .help-accordion__fs-btn {
  opacity: 1;
}

.help-accordion__video-wrap:fullscreen .help-accordion__fs-btn {
  opacity: 1;
  right: 20px;
  bottom: 20px;
  width: 40px;
  height: 40px;
}

.help-accordion__subtitle {
  position: absolute;
  left: 50%;
  bottom: 56px;
  transform: translateX(-50%);
  max-width: 80%;
  padding: 6px 14px;
  background: rgba(0, 0, 0, 0);
  color: transparent;
  font-size: 15px;
  font-weight: 500;
  line-height: 1.5;
  text-align: center;
  border-radius: 4px;
  pointer-events: none;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85);
  white-space: pre-wrap;
  letter-spacing: 0.3px;
  z-index: 10;
  transition: background 0.15s ease, color 0.15s ease;
}

.help-accordion__subtitle.is-active {
  background: rgba(0, 0, 0, 0.2);
  color: #fff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85);
}

.help-accordion__media-fallback {
  margin-top: 8px;
}

.help-accordion__media-fallback-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary, #86909c);
  text-align: center;
}

.help-accordion__field {
  margin-bottom: 12px;
}

.help-accordion__field-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--yonyou-orange-600, #ea580c);
  margin-bottom: 4px;
  letter-spacing: 0.5px;
}

.help-accordion__field-value {
  font-size: 14px;
  color: var(--el-text-color-primary, #1d2129);
  line-height: 1.6;
  white-space: pre-line;
}

.help-accordion__tip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: var(--yonyou-orange-50, #fff7ed);
  border-left: 3px solid var(--yonyou-orange-600, #ea580c);
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  color: var(--el-text-color-regular, #4e5969);
  line-height: 1.6;
}

.help-accordion__tip-label {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--yonyou-orange-700, #c2410c);
}

.help-accordion__tip-text {
  flex: 1;
}
</style>
