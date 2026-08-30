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
            <MenuPermissionMatrix v-model="menus" :editing="false" />
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
            :resource-type-labels="resourceTypeLabels"
            :action-labels="actionLabels"
            :dimensions="dimensions"
            :scope-matrix="scopeMatrix"
            :readonly="true"
            title="资源 × 功能权限"
            subtitle="全部有效权限集并集（含数据权限）"
            @open-condition-dialog="handleOpenConditionDialog"
          />
        </div>
      </div>

      <!-- 只读查看数据范围条件 -->
      <ConditionRuleDialog
        v-if="showConditionDialog"
        :permission-set-id="firstPsId"
        :editing-rule="editingRule"
        :readonly="true"
        @close="handleConditionDialogClose"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiV1 } from '@/utils/httpClient'
import { loadPermissionMeta } from '@/services/permissionService'
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

// 全局元数据（resource_type_labels / action_labels / supportedActions / dimensions）
const meta = ref(null)
const metaLoading = ref(false)
const metaError = ref('')

// 只读条件查看弹窗
const showConditionDialog = ref(false)
const editingRule = ref(null)

// [2026-08-30 元数据驱动] 优先消费后端 identity_type 契约，URL 字符串仅作兜底
const isOrg = computed(() => {
  if (data.value?.identity_type) return data.value.identity_type === 'org'
  return (props.endpoint || '').includes('/orgs/')
})

const fusedMatrix = computed(() => data.value?.role_resource_action_matrix || null)
const supportedActions = computed(() => meta.value?.resource_action_matrix || {})
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
  metaLoading.value = true
  metaError.value = ''
  try {
    meta.value = await loadPermissionMeta()
  } catch (e) {
    metaError.value = String(e?.message || e)
  } finally {
    metaLoading.value = false
  }
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

function handleOpenConditionDialog(payload) {
  // [v74 2026-08-30] 融合视图拆行：优先用该行的 row_scope（同资源多行时每行独立），
  //   未携带时回退到 rt 级 scopeMatrix
  const rowScope = payload.rowScope || scopeMatrix.value[payload.resourceType] || {}
  editingRule.value = {
    resource_type: payload.resourceType,
    rowLabel: payload.rowLabel,
    mode: payload.mode || 'custom',
    condition: rowScope.__expression || '',
    condition_display: rowScope.__expression_display || '',
    // 融合视图的 __rules 是后端聚合的只读说明（非 Rule Builder 结构），不传给 builder
    initialRules: undefined,
    rule_id: rowScope._rule_id || null,
  }
  showConditionDialog.value = true
}

function handleConditionDialogClose() {
  showConditionDialog.value = false
  editingRule.value = null
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
