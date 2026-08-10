<template>
  <div class="truth-panel" data-testid="truth-panel">
    <div class="truth-panel__header">
      <span class="truth-panel__title">状态真相面板</span>
      <div class="truth-panel__actions">
        <button class="truth-panel__btn" @click="refresh" title="重新读取三份状态">刷新</button>
        <button class="truth-panel__btn truth-panel__btn--primary" @click="runVerify" title="一键自检（状态一致性 + 未重建 + 展开保持）">一键自检</button>
        <button class="truth-panel__btn" @click="exportUrl" title="把当前折叠态/区分编码成可复现链接并复制">导出复现链接</button>
        <button class="truth-panel__btn truth-panel__btn--close" @click="$emit('close')" title="关闭">✕</button>
      </div>
    </div>

    <div class="truth-panel__summary">
      <span class="truth-pill" :class="divergenceCount ? 'is-bad' : 'is-good'">
        状态分歧: {{ divergenceCount }}
      </span>
      <span class="truth-pill" :class="isIncremental ? 'is-good' : 'is-warn'">
        上次渲染: {{ isIncremental ? '增量(updateColorsOnly)' : '全量(renderMermaid)' }}
      </span>
      <span class="truth-pill">scopeHighlight: {{ config.centerScopeHighlight ? '区分' : '不区分' }}</span>
      <span class="truth-pill">expandLevel: {{ config.expandLevel }}</span>
    </div>

    <div v-if="verifyResult" class="truth-panel__verify" :class="verifyResult.pass ? 'is-pass' : 'is-fail'">
      <span class="truth-panel__verify-title">{{ verifyResult.pass ? '✅ 自检通过' : '❌ 自检未通过' }}</span>
      <ul class="truth-panel__checks">
        <li v-for="c in verifyResult.checks" :key="c.name" :class="c.pass ? 'is-pass' : 'is-fail'">
          <span class="truth-check-name">{{ c.name }}</span>
          <span class="truth-check-result">{{ c.pass ? 'PASS' : 'FAIL' }}</span>
        </li>
      </ul>
      <div class="truth-panel__verify-detail"><pre>{{ verifyDetail }}</pre></div>
    </div>

    <div class="truth-panel__table-wrap">
      <table class="truth-panel__table">
        <thead>
          <tr>
            <th>分组</th>
            <th>类型</th>
            <th>store<br>collapsed</th>
            <th>chart<br>collapsed</th>
            <th>render<br>collapsed</th>
            <th>enabled</th>
            <th>visible</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key + row.title"
            :class="{ 'is-divergent': row.divergent }" :title="row.divergent ? '三份 collapsed 不一致' : ''">
            <td class="truth-panel__key">{{ row.title || row.key }} <span class="truth-panel__code">{{ row.key }}</span></td>
            <td class="truth-panel__type">{{ row.type || '-' }}</td>
            <td class="truth-panel__flag">{{ flagIcon(row.store?.collapsed) }}</td>
            <td class="truth-panel__flag">{{ flagIcon(row.chart?.collapsed) }}</td>
            <td class="truth-panel__flag">{{ flagIcon(row.render?.collapsed) }}</td>
            <td class="truth-panel__flag">{{ row.store ? (row.store.enabled ? '✓' : '✗') : '-' }}</td>
            <td class="truth-panel__flag">{{ row.store ? (row.store.visible ? '✓' : '✗') : '-' }}</td>
          </tr>
          <tr v-if="!rows.length"><td colspan="7" class="truth-panel__empty">暂无分组</td></tr>
        </tbody>
      </table>
    </div>

    <div class="truth-panel__hint">
      Console 可用: <code>__archPage.diag()</code> · <code>__archPage.verify()</code> ·
      <code>__archPage.captureNodeSignature()</code> · <code>__archPage.exportUrl()</code> ·
      <code>__archPage.help()</code> (能力清单)
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const emit = defineEmits(['close'])

const diagData = ref(null)
const verifyResult = ref(null)
const verifyDetail = ref('')

const config = computed(() => diagData.value?.config || {})
const divergenceCount = computed(() => diagData.value?.divergences?.length || 0)
const isIncremental = computed(() => {
  const lr = diagData.value?.renderMeta?.lastRender
  return lr ? lr.incremental === true : undefined
})

/** 按 key 合并 store/chart/render 三份，生成表格行 + 差异标记 */
const rows = computed(() => {
  const d = diagData.value
  if (!d) return []
  const byKey = {}
  const add = (arr, src) => (arr || []).forEach(g => {
    if (!g || !g.key) return
    byKey[g.key] = byKey[g.key] || {}
    byKey[g.key].key = g.key
    byKey[g.key][src] = g
    byKey[g.key]._title = byKey[g.key]._title || g.title || ''
    byKey[g.key]._type = byKey[g.key]._type || g.type || ''
  })
  add(d.store, 'store'); add(d.chart, 'chart'); add(d.render, 'render')
  return Object.values(byKey).map(v => {
    const flags = [v.store?.collapsed, v.chart?.collapsed, v.render?.collapsed].filter(x => x !== undefined)
    const divergent = flags.length >= 2 && new Set(flags).size > 1
    return { key: v.key || '', title: v._title, type: v._type, store: v.store, chart: v.chart, render: v.render, divergent }
  })
})

function flagIcon(c) {
  if (c === undefined) return '-'
  return c ? '🟥' : '🟩'
}

function refresh() {
  const api = window.__archPage
  diagData.value = api?.diag?.() || null
  // 保留旧的 verify 结果，但重置 detail 以便对照最新 divergences
  verifyDetail.value = ''
}

function runVerify() {
  const api = window.__archPage
  const r = api?.verify?.() || null
  verifyResult.value = r
  verifyDetail.value = r ? JSON.stringify({ divergences: r.divergences, nodeSignature: r.nodeSignature }, null, 2) : ''
}

function exportUrl() {
  const api = window.__archPage
  const url = api?.exportUrl?.()
  if (!url) { alert('无法生成复现链接（exportUrl 不可用）'); return }
  try {
    navigator.clipboard.writeText(url).then(() => alert('已复制复现链接：\n' + url))
  } catch (e) {
    alert('复现链接：\n' + url)
  }
}

onMounted(refresh)
</script>

<style scoped>
.truth-panel {
  position: absolute;
  top: 44px;
  right: 12px;
  z-index: 1200;
  width: 640px;
  max-width: 92%;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,.15);
  font-size: 12px;
  color: #333;
  overflow: hidden;
}
.truth-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #1f2937;
  color: #fff;
}
.truth-panel__title { font-weight: 600; }
.truth-panel__actions { display: flex; gap: 6px; }
.truth-panel__btn {
  border: 1px solid rgba(255,255,255,.4);
  background: transparent;
  color: #fff;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 12px;
}
.truth-panel__btn:hover { background: rgba(255,255,255,.15); }
.truth-panel__btn--primary { background: #409eff; border-color: #409eff; }
.truth-panel__btn--close { background: transparent; border-color: transparent; color: #f56c6c; }
.truth-panel__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid #eee;
  background: #fafafa;
}
.truth-pill {
  border-radius: 10px;
  padding: 2px 8px;
  background: #eee;
  font-size: 11px;
}
.truth-pill.is-good { background: #f0f9eb; color: #67c23a; }
.truth-pill.is-bad { background: #fef0f0; color: #f56c6c; }
.truth-pill.is-warn { background: #fdf6ec; color: #e6a23c; }
.truth-panel__verify { padding: 8px 12px; border-bottom: 1px solid #eee; }
.truth-panel__verify.is-pass { background: #f0f9eb; }
.truth-panel__verify.is-fail { background: #fef0f0; }
.truth-panel__verify-title { font-weight: 600; }
.truth-panel__checks { margin: 6px 0 0; padding-left: 16px; }
.truth-check-name { font-family: monospace; }
.truth-check-result { float: right; font-weight: 600; }
.is-pass .truth-check-result { color: #67c23a; }
.is-fail .truth-check-result { color: #f56c6c; }
.truth-panel__verify-detail pre {
  max-height: 120px; overflow: auto; font-size: 11px; margin: 6px 0 0;
  background: #fff; border: 1px solid #eee; padding: 6px; border-radius: 4px;
}
.truth-panel__table-wrap { max-height: 300px; overflow: auto; }
.truth-panel__table { width: 100%; border-collapse: collapse; }
.truth-panel__table th, .truth-panel__table td {
  border: 1px solid #eee; padding: 4px 6px; text-align: left; white-space: nowrap;
}
.truth-panel__table th { background: #f5f7fa; position: sticky; top: 0; }
.truth-panel__table tr.is-divergent { background: #fef0f0; }
.truth-panel__key .truth-panel__code { color: #999; font-family: monospace; font-size: 10px; margin-left: 4px; }
.truth-panel__type { color: #888; font-size: 11px; }
.truth-panel__flag { text-align: center; }
.truth-panel__empty { text-align: center; color: #999; }
.truth-panel__hint {
  padding: 6px 12px; border-top: 1px solid #eee; background: #fafafa;
  color: #888; font-size: 11px; line-height: 1.5;
}
.truth-panel__hint code { background: #eee; border-radius: 3px; padding: 0 3px; }
</style>
