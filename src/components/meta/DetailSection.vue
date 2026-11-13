<template>
  <div class="detail-section">
    <!-- 有 tabs：按 section_keys 分组 -->
    <el-tabs v-if="hasTabs" v-model="activeTab" class="detail-section__tabs">
      <el-tab-pane
        v-for="tab in visibleTabs"
        :key="tab.key"
        :label="tab.label"
        :name="tab.key"
      >
        <div
          v-for="section in tab.sections"
          :key="section.key"
          class="detail-section__section"
        >
          <div v-if="section.label" class="detail-section__title">{{ section.label }}</div>
          <el-row :gutter="16">
            <el-col
              v-for="field in sectionFields(section)"
              :key="field.key"
              :span="fieldSpan(section, field)"
            >
              <div class="detail-section__item">
                <div class="detail-section__label">{{ field.label }}</div>
                <div class="detail-section__value">
                  <EnumTag
                    v-if="isEnumField(field)"
                    :enum-name="field.enum_type"
                    :value="dataValue(field.key)"
                    :schema-version="uiMeta.schema_version"
                  />
                  <span v-else>{{ displayValue(dataValue(field.key)) }}</span>
                </div>
              </div>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 无 tabs（或 tabs 全空）：平铺 -->
    <template v-else>
      <div
        v-for="section in allSections"
        :key="section.key"
        class="detail-section__section"
      >
        <div v-if="section.label" class="detail-section__title">{{ section.label }}</div>
        <el-row :gutter="16">
          <el-col
            v-for="field in sectionFields(section)"
            :key="field.key"
            :span="fieldSpan(section, field)"
          >
            <div class="detail-section__item">
              <div class="detail-section__label">{{ field.label }}</div>
              <div class="detail-section__value">
                <EnumTag
                  v-if="isEnumField(field)"
                  :enum-name="field.enum_type"
                  :value="dataValue(field.key)"
                  :schema-version="uiMeta.schema_version"
                />
                <span v-else>{{ displayValue(dataValue(field.key)) }}</span>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>
    </template>
  </div>
</template>

<script setup>
/**
 * DetailSection.vue - ui-meta 详情区渲染（T13-8）
 *
 * 列语义：columns=1 每项一行（span 24）；columns=2 半宽（span 12）。
 * 字段 col_span 优先：span = col_span * (24 / columns)，越界夹到 1..24。
 * 值渲染：有 enum_type 或 widget==='enum' 走 EnumTag，否则纯文本；空值显示 '-'。
 */

import { computed, onMounted, ref, watch } from 'vue'
import EnumTag from '@/components/meta/EnumTag.vue'
import { evaluateVisibleWhen } from '@/utils/visibilityEvaluator'
import { preloadEnums } from '@/composables/useEnumMeta'

const props = defineProps({
  uiMeta: { type: Object, required: true },
  data: { type: Object, default: () => ({}) },
  // 优先于 detail 配置的 columns（1 | 2）
  columns: { type: Number, default: undefined }
})

const activeTab = ref('')

const detailMeta = computed(() => props.uiMeta?.detail || {})
const allSections = computed(() =>
  Array.isArray(detailMeta.value.sections) ? detailMeta.value.sections : []
)

// 字段定义来自 form.fields（详情区段只存字段名），区段内联对象也兼容
const fieldIndex = computed(() => {
  const map = {}
  for (const field of props.uiMeta?.form?.fields || []) {
    const key = field?.key || field?.name
    if (key) map[key] = field
  }
  for (const section of allSections.value) {
    for (const entry of section.fields || []) {
      if (entry && typeof entry === 'object') {
        const key = entry.key || entry.name || entry.field
        if (key && !map[key]) map[key] = entry
      }
    }
  }
  return map
})

const sectionMap = computed(() => {
  const map = {}
  for (const section of allSections.value) map[section.key] = section
  return map
})

// tabs 只保留能映射到真实 section 的分组；无效 key 忽略
const visibleTabs = computed(() =>
  (Array.isArray(detailMeta.value.tabs) ? detailMeta.value.tabs : [])
    .map(tab => ({
      key: tab.key,
      label: tab.label,
      sections: (tab.section_keys || [])
        .map(key => sectionMap.value[key])
        .filter(Boolean)
    }))
    .filter(tab => tab.sections.length > 0)
)

const hasTabs = computed(() => visibleTabs.value.length > 0)

watch(
  visibleTabs,
  tabs => {
    if (!tabs.length) {
      activeTab.value = ''
      return
    }
    if (!tabs.some(tab => tab.key === activeTab.value)) {
      activeTab.value = tabs[0].key
    }
  },
  { immediate: true }
)

function resolveField(section, entry) {
  const raw = typeof entry === 'string' ? { key: entry } : entry || {}
  const key = raw.key || raw.name || raw.field
  if (!key) return null

  const def = fieldIndex.value[key] || {}
  const spanMap = section?.col_span_map || {}

  return {
    key,
    label: raw.label || def.label || key,
    widget: raw.widget || def.widget || 'text',
    visible_when: raw.visible_when ?? def.visible_when,
    col_span: raw.col_span ?? spanMap[key] ?? def.col_span,
    enum_type: raw.enum_type || def.enum_type || ''
  }
}

/** 当前区段中可见的字段（visible_when 为 false 的不渲染） */
function sectionFields(section) {
  return (section?.fields || [])
    .map(entry => resolveField(section, entry))
    .filter(field => field && evaluateVisibleWhen(field.visible_when, props.data))
}

function sectionColumns(section) {
  const value = Number(props.columns) || Number(section?.columns) || 2
  return value === 1 ? 1 : 2
}

function fieldSpan(section, field) {
  const unit = 24 / sectionColumns(section)
  const span = field.col_span ? Number(field.col_span) * unit : unit
  return Math.min(24, Math.max(1, Math.round(span)))
}

function isEnumField(field) {
  return Boolean(field.enum_type) || field.widget === 'enum'
}

function dataValue(key) {
  return props.data ? props.data[key] : undefined
}

// 空值才显示 '-'，0 / false 正常显示
function displayValue(value) {
  return value === null || value === undefined || value === '' ? '-' : String(value)
}

// 挂载时一次性预加载本区段用到的枚举（fail-soft，不影响渲染）
function collectEnumTypes() {
  const names = new Set()
  for (const section of allSections.value) {
    for (const entry of section.fields || []) {
      const field = resolveField(section, entry)
      if (field?.enum_type) names.add(field.enum_type)
    }
  }
  return [...names]
}

onMounted(() => {
  const names = collectEnumTypes()
  if (!names.length) return
  preloadEnums(names).catch(() => {})
})
</script>

<style scoped>
.detail-section__section {
  margin-bottom: 16px;
}

.detail-section__title {
  margin-bottom: 12px;
  font-weight: 600;
}

.detail-section__item {
  margin-bottom: 12px;
}

.detail-section__label {
  margin-bottom: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.detail-section__value {
  color: var(--el-text-color-primary);
}
</style>