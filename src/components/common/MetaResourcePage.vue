<template>
  <div class="meta-resource-page">
    <!-- 指标条：只声明取值来源 list.stats，字段与标题全部由后端聚合与标签提供 -->
    <div v-if="statsConfig && statsData" class="stats">
      <div v-for="item in statItems" :key="item.value ?? item.label" class="stat">
        <span class="stat-label">{{ item.label || item.value }}</span>
        <b class="stat-value">{{ item.count }}</b>
      </div>
      <div v-if="statsData.retry_exhausted !== undefined" class="stat">
        <span class="stat-label" title="status=failed 且无下次重试：重试预算已耗尽（终态）">重试耗尽</span>
        <b class="stat-value">{{ statsData.retry_exhausted }}</b>
      </div>
      <span class="spacer" />
      <span class="hint">
        共 {{ statsData.total }} 条
        <template v-if="statsData.retryable !== undefined"> · 可重试 {{ statsData.retryable }} 条</template>
        <template v-if="statsData.avg_latency_ms !== null && statsData.avg_latency_ms !== undefined">
          · 平均投递耗时 {{ statsData.avg_latency_ms }}ms
        </template>
      </span>
    </div>

    <!-- 列 / 筛选 / 徽标 / 工具栏动作全部由 ui-meta 驱动；本组件只负责
         数据源（list.data_source）、行动作与通用表单抽屉 -->
    <MetaListPage
      v-if="ready"
      ref="listRef"
      :object-type="objectType"
      :view-name="effectiveView"
      :options="listOptions"
      :enable-detail="false"
      :enable-auto-crud="false"
      @toolbar-action="onToolbarAction"
    >
      <template v-if="$slots.toolbar" #toolbar="scope">
        <slot name="toolbar" v-bind="scope" />
      </template>

      <template #cell-actions="{ row }">
        <div class="row-actions">
          <AppButton
            v-for="action in rowActionsFor(row)"
            :key="action.id || action.label"
            variant="ghost"
            size="sm"
            :disabled="!isActionEnabled(action, row)"
            :loading="busyKey === actionKey(action, row) || !!actionLoading?.(action, row)"
            @click="executeAction(action, row)"
          >
            {{ action.label }}
          </AppButton>
        </div>
      </template>
    </MetaListPage>

    <!-- 通用表单抽屉：字段 / 默认值 / 下拉取值域来自 ui-meta.form，动作的
         dialog=form 声明决定由哪个按钮打开、保存时复用同一份 http 声明 -->
    <Drawer v-model="dialog.visible" :title="dialogTitle" width="560px">
      <MetaForm ref="formRef" v-model="formModel" :fields="formFields" layout="vertical" />
      <p v-if="formHint" class="form-hint">{{ formHint }}</p>
      <template #footer>
        <div class="footer-actions">
          <AppButton variant="secondary" @click="dialog.visible = false">取消</AppButton>
          <AppButton variant="primary" :loading="saving" @click="submitForm">保存</AppButton>
        </div>
      </template>
    </Drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppButton from './AppButton'
import Drawer from './Drawer'
import MetaForm from './MetaForm.vue'
import { MetaListPage } from './MetaListPage'
import { useMessage } from '@/composables/useMessage'
import { metaService } from '@/services/metaService'
import {
  buildFetcher, emptyFormModel, fetchStats, formModelFromRow, isActionEnabled,
  isActionVisible, payloadFromForm, runAction, toFormControls, warnOnce,
} from '@/services/metaResourceService'

defineOptions({ name: 'MetaResourcePage' })

const props = defineProps({
  objectType: {
    type: String,
    required: true,
  },
  /** 页面级额外查询参数（前端参数名），经 data_source.params_map 映射 */
  extraParams: {
    type: Object,
    default: () => ({}),
  },
  /** 需要页面自行处理的动作 id：命中后只 emit(row-action)，不执行通用 http */
  customActions: {
    type: Array,
    default: () => [],
  },
  /** 通用表单抽屉底部提示（如密钥只接受引用） */
  formHint: {
    type: String,
    default: '',
  },
  /** 页面自行处理动作时的按钮 loading：(action, row) => boolean */
  actionLoading: {
    type: Function,
    default: null,
  },
  /** [M0] YAML variants 视图名；空时回退 route.meta.integrationResource.view */
  view: {
    type: String,
    default: '',
  },
})

const route = useRoute()
const effectiveView = computed(
  () => props.view || route.meta?.integrationResource?.view || '',
)

const emit = defineEmits(['row-action'])

const toast = useMessage()
const listRef = ref(null)
const formRef = ref(null)

const uiMeta = ref(null)
const ready = ref(false)

const busyKey = ref('')
const saving = ref(false)

const statsConfig = computed(() => uiMeta.value?.list?.stats || null)
const statsData = ref(null)
const statItems = computed(() => statsData.value?.items || [])
const rowActions = computed(() => (uiMeta.value?.list?.actions || []).filter(
  (action) => (action.position || 'row') === 'row',
))
const metaFields = computed(() => uiMeta.value?.form?.fields || [])

// [M0] 行动作按 visible_when / roles 隐藏（后端仍鉴权；未知声明 warnOnce）
function rowActionsFor(row) {
  return rowActions.value.filter((action) => isActionVisible(action, row))
}

const listOptions = computed(() => {
  const dataSource = uiMeta.value?.list?.data_source
  const options = { autoLoad: true, pageSize: 20 }
  if (dataSource) {
    options.fetcher = buildFetcher(dataSource, () => props.extraParams)
  }
  return options
})

// ---------------- 通用表单抽屉 ----------------
const dialog = reactive({
  visible: false,
  mode: 'create',
  action: null,
  row: null,
})
const formModel = ref({})

const formFields = computed(() => toFormControls(metaFields.value, {
  editing: dialog.mode === 'edit',
  model: formModel.value,
  policies: uiMeta.value?.field_policies || {},
}))

const dialogTitle = computed(() => {
  const action = dialog.action
  if (!action) return ''
  const label = uiMeta.value?.label || ''
  return action.id === 'create' ? (action.label || '新建') : `${action.label || '编辑'}${label}`
})

function openForm(action, row) {
  dialog.action = action
  dialog.row = row
  dialog.mode = action.id === 'create' ? 'create' : 'edit'
  formModel.value = dialog.mode === 'create'
    ? emptyFormModel(metaFields.value)
    : formModelFromRow(metaFields.value, row)
  dialog.visible = true
}

async function submitForm() {
  const valid = formRef.value?.validateAll ? formRef.value.validateAll() : true
  if (valid === false) return

  let payload
  try {
    payload = payloadFromForm(metaFields.value, formModel.value, {
      editing: dialog.mode === 'edit',
    })
  } catch (error) {
    toast.error(error.message)
    return
  }

  saving.value = true
  try {
    const result = await runAction(dialog.action, { row: dialog.row, body: payload })
    if (!result.ok) {
      toast.error(result.message || '保存失败')
      return
    }
    toast.success(result.message || '已保存')
    dialog.visible = false
    await refresh()
  } finally {
    saving.value = false
  }
}

// ---------------- 动作执行 ----------------
function actionKey(action, row) {
  return `${action.id || action.label}:${row?.id ?? ''}`
}

async function executeAction(action, row) {
  // 先广播，页面可自行处理复合视图（如批次下钻抽屉）
  emit('row-action', { action, row })

  if (action.dialog === 'form') {
    openForm(action, row)
    return
  }
  if (!action.http) return
  if (props.customActions.includes(action.id)) return

  busyKey.value = actionKey(action, row)
  try {
    const result = await runAction(action, { row })
    if (result.canceled || result.skip) return
    if (!result.ok) {
      toast.error(result.message || '操作失败')
      return
    }
    toast.success(result.message || `${action.label || '操作'}成功`)
    if (action.refresh) await refresh()
  } finally {
    busyKey.value = ''
  }
}

function onToolbarAction(action) {
  const raw = (uiMeta.value?.list?.actions || []).find(
    (item) => (item.id || item.label) === action.key,
  )
  if (!raw) {
    // [M0] 未声明的动作不静默：同一对象只告警一次
    warnOnce(props.objectType, 'UNKNOWN_ACTION', `工具栏动作未在 ui-meta 声明: ${action.key}`)
    return
  }
  executeAction(raw, null)
}

// ---------------- 数据加载 ----------------
async function loadStats() {
  if (!statsConfig.value) return
  try {
    const data = await fetchStats(statsConfig.value)
    if (data) statsData.value = data
  } catch {
    // 指标条失败不影响列表主体
  }
}

async function refresh() {
  await listRef.value?.refresh?.()
  await loadStats()
}

onMounted(async () => {
  try {
    uiMeta.value = await metaService.getUiMeta(props.objectType, {
      view: effectiveView.value || null,
    })
  } catch {
    toast.error('页面元数据加载失败')
  } finally {
    ready.value = true
    loadStats()
  }
})

defineExpose({ refresh, listRef })
</script>

<style scoped>
.stats {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 12px;
  border: 1px solid var(--border-color, #eef0f3);
  border-radius: 6px;
  background: var(--bg-subtle, #f9fafb);
  min-width: 78px;
}
.stat-label { font-size: 12px; color: var(--text-secondary, #6b7280); }
.stat-value { font-size: 16px; line-height: 1.2; }
.spacer { flex: 1; }
.hint { font-size: 12px; color: var(--text-secondary, #6b7280); }
.row-actions {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
}
.form-hint {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
  margin: 12px 0 0;
}
.footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
