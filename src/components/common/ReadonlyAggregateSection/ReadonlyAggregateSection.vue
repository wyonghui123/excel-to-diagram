<template>
  <div class="ras">
    <!-- 概览：统计行（融合视图仍保留来源汇总） -->
    <div v-if="data && data.summary" class="ras__summary">
      <el-tag type="primary" effect="plain" class="ras__summary-tag">
        有效权限集 {{ data.summary.permission_set_count }} 个
      </el-tag>
      <template v-if="!isOrg">
        <el-tag type="info" effect="plain" class="ras__summary-tag">来源组织 {{ data.summary.source_org_count }} 个</el-tag>
      </template>

      <!-- [2026-08-30 继承链来源分组] 本组织 → 各级父组织，按来源分组展示权限集
           objects merge pattern 的应用：同一「权限集」按最近来源组织归组，
           每行 = 来源组织(association) + 该组织授予的权限集 name 列表 -->
      <template v-for="grp in chainGroups" :key="grp.org_id">
        <el-tooltip
          :content="`来源权限集：${grp.psNames.join('、')}`"
          placement="top"
          :teleported="true"
        >
          <el-tag type="info" effect="plain" class="ras__summary-tag ras__chain-tag">
            {{ grp.label }}：{{ grp.psNames.join('、') }}
          </el-tag>
        </el-tooltip>
      </template>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="ras__loading">
      <el-skeleton :rows="3" animated />
    </div>

    <!-- 错误 + 重试 -->
    <el-alert
      v-else-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
    >
      <template #default>
        <el-button size="small" link type="primary" @click="load">重试</el-button>
      </template>
    </el-alert>

    <!-- 空态 -->
    <el-empty
      v-else-if="data && data.permission_sets.length === 0"
      :description="isOrg ? '该组织未配置权限，且无父级继承' : '该用户无有效权限集'"
      :image-size="72"
    />

    <template v-else-if="data">
      <!-- [2026-08-30 融合单份] 不再按权限集折叠，而是把全部有效权限集合并为
           「完整的一份」：左侧菜单权限树 + 右侧资源×功能权限矩阵（矩阵行内含数据范围列）。
           全中文、无英文码，风格与「权限配置」tab 一致，只读展示。 -->
      <div class="ras__dual">
        <div class="ras__left">
          <AppCard title="菜单权限" class="ras__card ras__menu-card">
            <!-- [Spec 21 PM 反馈 2026-09-12 第四次] 限高分页：避免菜单树挤掉下方资源矩阵 -->
            <MenuPermissionMatrix v-model="menus" :editing="false" :page-size="8" :max-height="280" />
          </AppCard>
        </div>

        <div class="ras__right">
          <AppAlert
            v-if="metaError"
            type="warning"
            class="ras__meta-error"
            :title="metaError"
            :closable="false"
          />
          <ResourceActionMatrix
            class="ras__matrix"
            :loading="metaLoading"
            :matrix="fusedMatrix"
            :supported-actions="supportedActions"
            :resource-hierarchy="resourceHierarchy"
            :resource-type-labels="resourceTypeLabels"
            :action-labels="actionLabels"
            :dimensions="dimensions"
            :scope-matrix="scopeMatrix"
            :readonly="true"
            :tree-allow-split-rows="true"
            :show-ps-source="true"
            title="资源 × 功能权限"
            subtitle="全部有效权限集并集（含数据权限）"
            @open-condition-dialog="handleOpenConditionDialog"
          />
        </div>
      </div>

      <!-- 只读查看数据范围条件 -->
      <!-- [Spec 22 PM 反馈第十八次 2026-09-13] binding 由 useConditionRuleDialog 接管 -->
      <ConditionRuleDialog
        v-if="dialogShow"
        :permission-set-id="firstPsId"
        :editing-rule="dialogEditingRule"
        :readonly="true"
        @close="closeConditionDialog"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiV1 } from '@/utils/httpClient'
// [P2-Matrix-01] 复用 usePermissionMeta 单一真源（与 PermissionConfigPanel 同源）
//   - 基础元数据（resource_action_matrix / action_labels / ...）
//   - state_transition action_ref 合并（用于矩阵「更多动作」列）
// [PM 反馈 2026-09-13 第十七次] 此前 ReadonlyAggregateSection 直接调
//   loadPermissionMeta()，未走 usePermissionMeta，导致 state_transition 合并缺失
//   "权限预览 tab 看不到 state_transition action" 的根因
import { usePermissionMeta } from '@/composables/usePermissionMeta'
// [Spec 22 PM 反馈第十八次 2026-09-13] ConditionRuleDialog 单一真源（与 PermissionConfigPanel 同入口）
//   readonly 视图永远只读，无需 onSaved；只取 open / close / editingRule / showDialog
import { useConditionRuleDialog } from '@/composables/useConditionRuleDialog'
import AppCard from '@/components/common/AppCard/AppCard.vue'
import AppAlert from '@/components/common/AppAlert/AppAlert.vue'
import MenuPermissionMatrix from '@/views/SystemManagement/components/MenuPermissionMatrix.vue'
import ResourceActionMatrix from '@/views/SystemManagement/components/ResourceActionMatrix.vue'
import ConditionRuleDialog from '@/views/SystemManagement/ConditionRuleDialog.vue'

const props = defineProps({
  endpoint: { type: String, default: '' },   // 由元数据 config 注入，如 /orgs/{id}/permission-config（id 已插值）
  fetchFn: { type: Function, default: null }, // 可注入的拉取函数（默认用 apiV1.get）
})
const emit = defineEmits(['loaded'])

const data = ref(null)
const menus = ref([])
const scopeMatrix = ref({})
const loading = ref(false)
const error = ref('')

// [P2-Matrix-01] 改用 usePermissionMeta 单一真源
//   meta / metaLoading / metaError / supportedActions 全部从此 composable 派生
//   supportedActions 已含 state_transition action_ref 合并（自动）
const {
  meta,
  loading: metaLoading,
  lastError: metaLastError,
  loadMetaWithScope,
  supportedActions,   // 来自 usePermissionMeta 内部 computed，已含 state_transition 合并
} = usePermissionMeta()

const metaError = computed(() => metaLastError.value?.message || '')

// 只读条件查看弹窗（composable 接管）
const isReadonly = computed(() => true)  // 只读视图永久只读
const {
  editingRule: dialogEditingRule,
  showDialog: dialogShow,
  open: openConditionDialog,
  close: closeConditionDialog,
} = useConditionRuleDialog({
  // [v74 2026-08-30] 融合视图拆行：getRowScope 优先用该行的 row_scope，
  //   未携带时回退到 rt 级 scopeMatrix；payload.rowScope 由 open() 自动应用
  permissionSetId: computed(() => firstPsId.value),
  getRowScope: (rt) => scopeMatrix.value[rt] || {},
  isEditing: isReadonly,  // 永久 false → dialogReadonly=true
})

// [2026-08-30 元数据驱动] 优先消费后端 identity_type 契约，URL 字符串仅作兜底
const isOrg = computed(() => {
  if (data.value?.identity_type) return data.value.identity_type === 'org'
  return (props.endpoint || '').includes('/orgs/')
})

const fusedMatrix = computed(() => data.value?.role_resource_action_matrix || null)
// supportedActions 已来自 usePermissionMeta（含 state_transition 合并），无需再算
// （保留此注释以提醒：不要重复定义同名 computed）
// [Spec 19 FR-014 2026-09-06] 类型层树形数据源；融合视图同 rt 拆行 → 组件内自动平铺回退
const resourceHierarchy = computed(() => meta.value?.resource_hierarchy || {})
const resourceTypeLabels = computed(() => meta.value?.resource_type_labels || {})
const actionLabels = computed(() => meta.value?.action_labels || {})
const dimensions = computed(() => meta.value?.normalizedForDimensionSelector || [])

/** ConditionRuleDialog 需要 permissionSetId（只读场景仅用于字段元数据/兜底，取第一个权限集） */
const firstPsId = computed(() => {
  const sets = data.value?.permission_sets || []
  return sets.length ? String(sets[0].permission_set_id) : ''
})

/**
 * [2026-08-30 继承链来源分组] 按「本组织 → 各级父组织」分组展示来源权限集。
 * 每个权限集归属到最近来源组织（org 单根链 source_orgs 已收敛为最浅 depth），
 * 行 label 累加祖先路径（例：父组织 供应链云->父组织 大业务）。
 */
const chainGroups = computed(() => {
  const d = data.value
  if (!d) return []
  const sets = d.permission_sets || []
  const chain = d.org_chain || []
  let prevLabel = ''
  return chain
    .map((node) => {
      const psNames = sets
        .filter((ps) => (ps.source_orgs || []).some((s) => s.org_id === node.org_id))
        .map((ps) => ps.permission_set_name)
        .filter(Boolean)
      return { ...node, psNames }
    })
    .filter((g) => g.psNames.length)
    .map((g) => {
      let label
      if (g.depth === 0) {
        label = isOrg.value ? '本组织' : `来源组织 ${g.org_name}`
      } else if (g.depth === 1) {
        // 第一级父组织不带前缀（例：父组织 供应链云）
        label = `父组织 ${g.org_name}`
      } else {
        // 深级累加祖先路径（例：父组织 供应链云->父组织 大业务）
        label = `${prevLabel}->父组织 ${g.org_name}`
      }
      prevLabel = label
      return { ...g, label }
    })
})

async function loadMeta() {
  // [P2-Matrix-01] 走 usePermissionMeta.loadMetaWithScope()
  // 与 PermissionConfigPanel 同入口、同 scope 保护、同 state_transition 合并
  await loadMetaWithScope()   // readonly 视图不传 scope_code，复用默认 scope（Spec 5.5.4 保护）
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    let endpoint = props.endpoint
    if (endpoint.startsWith('/api/v1')) endpoint = endpoint.replace('/api/v1', '')
    const resp = props.fetchFn
      ? await props.fetchFn(props.endpoint)
      : await apiV1.get(endpoint)
    if (resp.success && resp.data) {
      data.value = resp.data
      menus.value = resp.data.menus || []
      scopeMatrix.value = resp.data.scope_matrix || {}
      emit('loaded', resp.data)
      await loadMeta()
    } else {
      error.value = resp.message || '加载失败'
    }
  } catch (e) {
    error.value = String(e?.message || e)
  } finally {
    loading.value = false
  }
}

// [Spec 22 PM 反馈第十八次 2026-09-13] handleOpenConditionDialog / handleConditionDialogClose
//   全部由 useConditionRuleDialog.open / .close 接管。融合视图拆行的 rowScope 优先逻辑
//   已内置到 composable.open(payload)（payload.rowScope 优先，未携带回退 rt 级 scopeMatrix）
// 这里保留薄包装以承接 ResourceActionMatrix 的 @open-condition-dialog 事件：
function handleOpenConditionDialog(payload) {
  openConditionDialog(payload)
}

onMounted(load)
</script>

<style scoped lang="scss">
.ras__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.ras__summary-tag {
  margin-right: 0;
}
.ras__chain-tag {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ras__loading {
  padding: 16px;
  color: var(--el-text-color-secondary);
}

/* [2026-08-30 融合单份] 垂直布局：上「菜单权限」 / 下「资源×功能权限矩阵」（含数据范围列）
   用户偏好纵向单列，菜单树完整展开在上方，矩阵在下。 */
.ras__dual {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-items: stretch;
}
.ras__left,
.ras__right {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ras__menu-card :deep(.app-card__header) {
  padding-bottom: 4px;
}
.ras__menu-card :deep(.app-card__body) {
  padding-top: 0;
  padding-bottom: 16px;
}
.ras__menu-card :deep(.menu-list) {
  max-height: none; /* 垂直布局下菜单完整展开，不再限高 */
  padding: 0;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-sm);
  background: var(--color-bg-container);
}
.ras__matrix :deep(.app-card__header) {
  padding-bottom: 4px;
}
.ras__matrix :deep(.app-card__body) {
  padding-top: 0;
  padding-bottom: 16px;
}
.ras__meta-error {
  margin-bottom: 0;
}
</style>
