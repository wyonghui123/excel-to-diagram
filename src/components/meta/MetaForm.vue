<template>
  <el-form
    ref="formRef"
    :model="modelValue"
    :disabled="formDisabled"
    class="meta-form"
    label-width="auto"
  >
    <!-- 有 tabs：按 section_keys 分组 -->
    <el-tabs v-if="hasTabs" v-model="activeTab" class="meta-form__tabs">
      <el-tab-pane
        v-for="tab in visibleTabs"
        :key="tab.key"
        :label="tab.label"
        :name="tab.key"
      >
        <div
          v-for="section in tab.sections"
          :key="section.key"
          class="meta-form__section"
        >
          <div v-if="section.label" class="meta-form__section-title">{{ section.label }}</div>
          <el-row :gutter="16">
            <el-col
              v-for="field in sectionFields(section)"
              :key="field.key"
              :span="fieldSpan(section, field)"
            >
              <el-form-item :label="field.label" :prop="field.key" :rules="rulesFor(field)">
                <component
                  :is="widgetComponent(field)"
                  :model-value="fieldValue(field.key)"
                  v-bind="widgetAttrs(field)"
                  :disabled="isFieldDisabled(field)"
                  clearable
                  @update:model-value="setFieldValue(field.key, $event)"
                >
                  <template v-if="isSelectWidget(field)">
                    <el-option
                      v-for="option in enumOptions(field)"
                      :key="String(option.value)"
                      :label="option.label"
                      :value="option.value"
                    />
                  </template>
                </component>
              </el-form-item>
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
        class="meta-form__section"
      >
        <div v-if="section.label" class="meta-form__section-title">{{ section.label }}</div>
        <el-row :gutter="16">
          <el-col
            v-for="field in sectionFields(section)"
            :key="field.key"
            :span="fieldSpan(section, field)"
          >
            <el-form-item :label="field.label" :prop="field.key" :rules="rulesFor(field)">
              <component
                :is="widgetComponent(field)"
                :model-value="fieldValue(field.key)"
                v-bind="widgetAttrs(field)"
                :disabled="isFieldDisabled(field)"
                clearable
                @update:model-value="setFieldValue(field.key, $event)"
              >
                <template v-if="isSelectWidget(field)">
                  <el-option
                    v-for="option in enumOptions(field)"
                    :key="String(option.value)"
                    :label="option.label"
                    :value="option.value"
                  />
                </template>
              </component>
            </el-form-item>
          </el-col>
        </el-row>
      </div>
    </template>
  </el-form>
</template>

<script setup>
/**
 * MetaForm.vue - ui-meta 表单渲染（T13-8）
 *
 * 4 列栅格：field.col_span 优先（1/2/3/4 => 6/12/18/24），
 * 缺省按 section.columns 推导（1 列全宽 24，2 列半宽 12）。
 * 控件分发最小集：text / textarea / number / select|enum / date / switch，未知降级 el-input。
 */

import { computed, onMounted, ref, watch } from 'vue'
import {
  ElInput,
  ElInputNumber,
  ElSelect,
  ElDatePicker,
  ElSwitch
} from 'element-plus'
import { useEnumMeta, preloadEnums } from '@/composables/useEnumMeta'
import { evaluateVisibleWhen } from '@/utils/visibilityEvaluator'

const props = defineProps({
  uiMeta: { type: Object, required: true },
  modelValue: { type: Object, default: () => ({}) },
  readonly: { type: Boolean, default: false },
  mode: { type: String, default: 'edit' } // 'create' | 'edit' | 'view'
})

// 控件分发表（未知 widget 统一降级 el-input）
const WIDGET_COMPONENTS = {
  text: ElInput,
  textarea: ElInput,
  number: ElInputNumber,
  select: ElSelect,
  enum: ElSelect,
  date: ElDatePicker,
  switch: ElSwitch
}

// 4 列栅格单位：6 => 每行 4 / 2 / 1 列
const GRID_SPAN_UNIT = 6

const formRef = ref(null)
const activeTab = ref('')
const enumTick = ref(0)
const { load, getItems } = useEnumMeta()

const formMeta = computed(() => props.uiMeta?.form || {})
const allSections = computed(() =>
  Array.isArray(formMeta.value.sections) ? formMeta.value.sections : []
)

// 字段元数据索引：form.fields 是权威定义，区段内联对象也可直接给出定义
const fieldIndex = computed(() => {
  const map = {}
  for (const field of formMeta.value.fields || []) {
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
  (Array.isArray(formMeta.value.tabs) ? formMeta.value.tabs : [])
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
const formDisabled = computed(() => props.readonly || props.mode === 'view')

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

/** 归一化字段定义（支持 form.fields 索引 + 区段内联对象两种形态） */
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
    required: Boolean(raw.required ?? def.required),
    readonly: Boolean(raw.readonly ?? def.readonly),
    visible_when: raw.visible_when ?? def.visible_when,
    col_span: raw.col_span ?? spanMap[key] ?? def.col_span,
    enum_type: raw.enum_type || def.enum_type || ''
  }
}

/** 当前区段中可见的字段（visible_when 为 false 的不渲染） */
function sectionFields(section) {
  return (section?.fields || [])
    .map(entry => resolveField(section, entry))
    .filter(field => field && evaluateVisibleWhen(field.visible_when, props.modelValue))
}

/** 栅格 span 归一化：限制在 1..24 且吸附为 6 的倍数（6/12/18/24） */
function normalizeGridSpan(span) {
  const value = Number(span)
  const base = Number.isFinite(value) ? value : 12
  const snapped = Math.round(base / GRID_SPAN_UNIT) * GRID_SPAN_UNIT
  return Math.min(24, Math.max(GRID_SPAN_UNIT, snapped))
}

function fieldSpan(section, field) {
  if (field.col_span) {
    return normalizeGridSpan(Number(field.col_span) * GRID_SPAN_UNIT)
  }
  return normalizeGridSpan(section?.columns === 1 ? 24 : 12)
}

function fieldValue(key) {
  return props.modelValue ? props.modelValue[key] : undefined
}

// v-model 直达：直接改写父级传入的对象，不做深拷贝
function setFieldValue(key, value) {
  if (props.modelValue && key) props.modelValue[key] = value
}

function isFieldDisabled(field) {
  return formDisabled.value || Boolean(field.readonly)
}

function enumOptions(field) {
  enumTick.value // 建立响应式依赖（枚举缓存非响应式）
  return getItems(field.enum_type)
}

function isSelectWidget(field) {
  return (
    (field.widget === 'select' || field.widget === 'enum') && enumOptions(field).length > 0
  )
}

function widgetComponent(field) {
  if (field.widget === 'select' || field.widget === 'enum') {
    // 无枚举数据时降级为文本输入
    return isSelectWidget(field) ? ElSelect : ElInput
  }
  return WIDGET_COMPONENTS[field.widget] || ElInput
}

function widgetAttrs(field) {
  if (field.widget === 'textarea') {
    return { type: 'textarea', autosize: { minRows: 2, maxRows: 6 } }
  }
  return {}
}

function rulesFor(field) {
  if (!field.required) return []
  return [{ required: true, message: `${field.label}必填`, trigger: 'blur' }]
}

// 预加载本表单用到的枚举；失败保持未知态（由控件降级兜底）
async function ensureEnums() {
  const names = new Set()
  for (const section of allSections.value) {
    for (const entry of section.fields || []) {
      const field = resolveField(section, entry)
      if (field?.enum_type) names.add(field.enum_type)
    }
  }
  if (names.size) await preloadEnums([...names]).catch(() => {})
  for (const name of names) {
    try {
      await load(name, props.uiMeta?.schema_version)
      enumTick.value++
    } catch {
      // fail-closed：枚举不可用时降级 el-input
    }
  }
}

onMounted(ensureEnums)
watch(() => props.uiMeta, ensureEnums)

/** 暴露给父组件的表单校验（Promise，失败时 reject） */
function validate() {
  if (!formRef.value) return Promise.resolve(true)
  return formRef.value.validate()
}

defineExpose({ validate })
</script>

<style scoped>
.meta-form__section + .meta-form__section {
  margin-top: 8px;
}

.meta-form__section-title {
  margin-bottom: 12px;
  font-weight: 600;
}
</style>