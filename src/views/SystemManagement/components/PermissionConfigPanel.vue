<template>
  <div class="permission-config-panel" :class="{ 'pcp--editing': isEditing, 'pcp--readonly': !isEditing }">
    <!-- [v34 2026-08-27] 页面标题已由 ObjectPage 顶层提供，此处不再重复 header；
         pcp-context-bar（"全部权限"面包屑）信息量极低，与当前选中菜单/meta-stat 中的
         "当前上下文"重复，移除；让整个权限配置区直接贴合到内容流，无多余页头/导航壳。-->
    <!-- [v43 2026-08-27] 删除浏览态 banner/chip
         业内共识（SAP Fiori Object Page / OutSystems Read-Only / Oloid Tenant Admin）：
         浏览态交互方案 = 顶部唯一「编辑」按钮 + 全部 disabled，不弹额外 banner/chip。
         ObjectPage 顶层已提供「编辑/保存」按钮，无需在面板内重复状态指示。 -->
    <div class="pcp-layout">
      <main class="pcp-content pcp-content--full">
        <!-- [v35 2026-08-27] 信息结构重组：
             1) 删掉 section 顶部 h4 + dl meta + 引导段（占大量空白）；
             2) "菜单权限"标题由左侧 AppCard 提供，视图切换 AppSegment 放在 AppCard extra slot；
             3) "资源 × 功能权限"标题 + 当前上下文 + 分页 全部由 ResourceActionMatrix AppCard 承担。 -->
        <section class="perm-section--inline">
          <div class="pcp-menu-dual">
            <div class="pcp-menu-left">
              <AppCard
                class="menu-permission-card"
                title="菜单权限"
              >
                <MenuPermissionMatrix
                  v-model="menus"
                  :loading="menusLoading"
                  :selected-menu-code="displayedMenu?.menu_code || ''"
                  :editing="isEditing"
                  @select-menu="handleSelectMenu"
                />

                <div class="perm-actions-bar">
                  <button class="btn btn-ghost btn-sm" :disabled="!isEditing" @click="selectAllMenus">全选菜单</button>
                  <button class="btn btn-ghost btn-sm" :disabled="!isEditing" @click="clearAllMenus">清空</button>
                  <div class="actions-spacer"></div>
                  <span class="perm-actions-meta">
                    <!-- [v70 2026-08-28] 「共 X 项」原为静态总量不联动, 改为「已授予 G／总量 82」与菜单徽章同口径 -->
                    已分配 {{ assignedMenuCount }} / {{ totalMenuCount }} 菜单 · 已授予 {{ grantedFuncPermissions }} / {{ totalFuncPermissions }} 项功能权限
                  </span>
                </div>
              </AppCard>
            </div>

            <div class="pcp-menu-right">
              <!-- [P2-Matrix-02 BLOCKER] scopeCode 无效 → Warning AppAlert -->
              <AppAlert v-if="scopeError" type="warning" class="matrix-scope-error">
                <strong>范围编码（scope_code）无效，已中止加载：</strong>{{ scopeError.message }}
                <span v-if="availableScopeCodes.length" class="matrix-scope-codes">
                  可用编码：{{ availableScopeCodes.join(' / ') }}
                </span>
              </AppAlert>

              <!-- [v34 2026-08-27] 非 scope 类失败（500／网络／后端异常）的诊断 -->
              <AppAlert v-else-if="metaLastError && !metaLoading" type="error" class="matrix-meta-error">
                <strong>元数据加载失败：</strong>{{ metaLastError.message }}
                <span class="matrix-meta-diag">
                  <span v-if="metaLastError.httpStatus">HTTP {{ metaLastError.httpStatus }}</span>
                  <span v-if="metaLastError.code">code: {{ metaLastError.code }}</span>
                  <span>请求：GET /api/v2/bo/permission_dimension/meta?scope_code=SCP&amp;permission_set_id={{ props.permissionSetId }}</span>
                  <span>排查：① 后端 Python 服务是否启动；② /api/v2/bo/permission_dimension/meta 接口是否注册；③ 角色 ID 是否已保存为数字 ID。</span>
                </span>
              </AppAlert>

              <!-- [Spec 19 FR-013 2026-09-06 PM 反馈] 委托授权门禁说明由常驻横幅改为
                   矩阵卡片右上角 info 图标 tooltip（ResourceActionMatrix 内实现），不占版面 -->

              <!-- [Spec 21 FR-005 2026-09-12 PM 反馈 2026-09-12] 对象级基线（OWD）只读卡
                   已从权限集详情页移除（OWD 是组织级全局基线，不是权限集级设置）。
                   ObjectOwdPanel 组件保留，未来由 P3「对象安全基线」专属页面使用。
                   后端 /meta 仍下发 object_owd 字段以备该页面。 -->
              <ResourceActionMatrix
                class="resource-action-matrix"
                :loading="metaLoading"
                :matrix="roleMatrix"
                :last-error="metaLastError"
                :supported-actions="mergedSupportedActions"
                :action-hints="actionHints"
                :resource-hierarchy="resourceHierarchy"
                :resource-type-labels="resourceTypeLabels"
                :action-labels="actionLabels"
                :action-meta="actionMeta"
                :external-resource-filters="matrixExternalFilters"
                :external-resource-filter-mode="matrixExternalFilterMode"
                :title="matrixTitle || '资源 × 功能权限'"
                :subtitle="displayedMenu ? '' : '全部资源（受左侧菜单/资源分组筛选）'"
                :context-menu="displayedMenu"
                :readonly="!isEditing"
                :show-ps-source="props.showPsSource ?? false"
                @clear-context="handleClearActiveMenu"
                :dimensions="linkageDimensionList"
                :scope-matrix="scopeMatrix"
                @change="handleMatrixChange"
                @scope-change="handleScopeChange"
                @open-condition-dialog="openConditionDialog"
              />
            </div>
          </div>
        </section>
      </main>
    </div>

    <!-- [一体化 Phase 3 2026-08-25 废弃] 联动警告对话框已删除
         一体化后，范围与动作在同一组件内表达，无需联动校验对话框
         保留 state refs 以避免破坏编译 -->

    <!-- [P2-9 2026-08-29] Spec 16: ConditionRuleDialog prop 统一为 permissionSetId -->
    <!-- [Spec 22 PM 反馈第十八次 2026-09-13] 全部 binding 由 useConditionRuleDialog 接管 -->
    <ConditionRuleDialog
      v-if="dialogShow"
      :permission-set-id="permissionSetId"
      :editing-rule="dialogEditingRule"
      :readonly="dialogReadonly"
      @close="closeConditionDialog"
      @saved="handleConditionRuleSaved"
    />

    <!-- ====================================================================== -->
    <!-- [v43 2026-08-27] 底部操作栏                                            -->
    <!--   - v47 用户明确要求：不增加底部保存按钮，ObjectPage 顶部「编辑／保存」  -->
    <!--     是唯一标准入口（双入口造成概念混乱）                                -->
    <!--   - v70 原「权限体检」按钮已上移到 RolePermissionDetail 的 ObjectPage   -->
    <!--     头部标准 action 区（体检是角色 object 的 validation action）        -->
    <!-- ====================================================================== -->
    <div class="pcp-bottom-bar">
      <div class="pcp-bottom-left">
        <!-- [v43 2026-08-27] 待保存数量提示：编辑态 + 有变更时显示 -->
        <span v-if="isEditing && hasPendingChanges" class="pcp-pending-hint">
          <AppIcon name="info" :size="14" />
          有未保存的变更
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, toRef, watch } from 'vue'
import { AppIcon } from '@/components/common/AppIcon'
import AppAlert from '@/components/common/AppAlert/AppAlert.vue'
import AppCard from '@/components/common/AppCard/AppCard.vue'
import MenuPermissionMatrix from './MenuPermissionMatrix.vue'
import ResourceActionMatrix from './ResourceActionMatrix.vue'
// [Spec 21 FR-005 PM 反馈 2026-09-12] ObjectOwdPanel 已从权限集详情页移除
//   组件文件保留供 P3「对象安全基线」页面使用，此处不再 import
import ConditionRuleDialog from '../ConditionRuleDialog.vue'
import { useMenuPermission } from '../composables/useMenuPermission'
import { useMessage } from '@/composables/useMessage'
// [P2-Matrix-01] 权限配置元数据加载（scopeCode 3 层保护）
import { usePermissionMeta } from '@/composables/usePermissionMeta'
// [Spec 22 PM 反馈第十八次 2026-09-13] ConditionRuleDialog 调用模板单一真源
//   与 ReadonlyAggregateSection 同入口；统一管理 editingRule / showDialog / dialogReadonly / open / close / handleSaved
import { useConditionRuleDialog } from '@/composables/useConditionRuleDialog'
import { boService } from '@/services/boService'
// [P6-T3 2026-07-20] 直接复用 permissionService 加载/保存 prohibition 规则
import * as permService from '@/services/permissionService'
// [2026-08-28 下沉 service 层] 纯业务主键表达式 → 实例名称 水合
import { hydrateIdExpressionDisplay } from '@/services/permissionService'

// [FIX v1.0.4] 改用项目统一消息系统 (useMessage + NotificationContainer)
//   - 旧实现用 ElMessage, 与 RoleDetailDrawer 的 useMessage 不一致
//   - Element Plus ElMessage 在 role 详情页内部被 high-z modal 遮挡时
//     通知 fixed 定位失效, 看不见
//   - NotificationContainer 是 z-index: 1700, teleport to body, 永远在最上层
const message = useMessage()

const props = defineProps<{
  permissionSetId: string
  /** [v40 2026-08-27] 编辑态由外层 ObjectPage 统一控制（一体化模式） */
  editing?: boolean
  /**
   * [BUG-V072 2026-08-28] 退出编辑时是否自动 flush 权限保存
   * 背景: ObjectDetailPage 路由（/detail/permission_set/:id）的保存按钮只调
   *   boService.update('permission_set', ...) 保存基本信息, 完全不触发 permPanelRef.save(),
   *   导致用户在权限面板反勾选菜单后点保存, 实际只保存了 name/description/is_active,
   *   刷新后菜单从 DB 重读回来仍是勾选态 —— 表现为"反勾选后又被勾上".
   * 修复: ObjectDetailPage 传 :flush-on-exit="true", watch(isEditing) 退出时
   *   若有未保存改动 → 先 savePermissions() 再清回滚 (保留菜单改动).
   *   RolePermissionDetail 路由不传 (默认 false), 走原有"编辑→取消→回滚快照"逻辑,
   *   由外层自己调 permPanelRef.save() (RolePermissionDetail.handleSave 已实现).
   */
  flushOnExit?: boolean
  /** [Spec 21 PM 反馈 2026-09-12] 是否显示「来源权限集」列
   *  false (默认): 不显示（权限集详情编辑/浏览态 - 避免误读为可按权限集配置）
   *  true:        显示（组织详情「权限预览」tab 等跨权限集聚合场景 - 看清每行授权来源）
   *  透传给 ResourceActionMatrix 的同名 prop。 */
  showPsSource?: boolean
}>()

const emit = defineEmits<{
  (e: 'saved'): void
}>()

const {
  menus,
  loading: menusLoading,
  isDirty: menuIsDirty,    // [v43 2026-08-27] 菜单勾选未保存标志
  loadMenus,
  selectAll,
  clearAll,
  save: saveMenuPermissions
} = useMenuPermission(toRef(props, 'permissionSetId'))

// [v40 2026-08-27] 编辑态一体化：isEditing 由外层 ObjectPage 的「编辑」按钮驱动（props.editing），
//   本组件不再拥有独立编辑入口。退出编辑（取消）时恢复快照。
const isEditing = computed(() => !!props.editing)

/** [Phase 3] 菜单视图：当前选中菜单（驱动右侧 ResourceActionMatrix） */
const activeMenu = ref<any>(null)

// [2026-08-28 重构清理] 删除死代码：
//   - activeFunctionalView 视图切换（AppSegment 组件不存在，切换器从未生效；
//     唯一消费 prop :compact 已随 MenuPermissionMatrix 契约清理移除）
//   - showLegacyOwd / sideFocus / sideFocusSet / sideFocusDisplay（侧边栏删除后的残留）
//   - assignedResourceCount / totalResourceCount（模板无引用）
//   - Tab2 联动区（writeGrantedResources / linkageSummary / availableResourcePool /
//     dimensionActions / dimensionActionMatrix / toggleDimensionAction / dimHasScope /
//     linkageActions / validateFunctionalDataLinkage）—— Tab2 已一体化删除，全部无引用

// [v70 2026-08-28] 「权限体检」入口已上移到 RolePermissionDetail 的 ObjectPage 标准 action 区
// ============================================================================
// [P2-Matrix-01] 资源 × 动作 矩阵（Spec 5.3.1 子 Tab A）
// 通过 /permission_dimension/meta?permission_set_id&scope_code=SCP 加载：
//   - role_resource_action_matrix：角色矩阵（行=资源，列=动作，cell={granted, source}）
//   - resource_action_matrix：每资源类型可授权动作（A5 灰化禁选依据）
//   - scopeCode 无效 → scopeError → Warning AppAlert（P2-Matrix-02 BLOCKER，绝不回退全量）
// ============================================================================
/** 标准测试范围：供应链计划（SCP）子领域（用户反复强调的测试铁律） */
const SCOPE_CODE = 'SCP'

const {
  meta,
  loading: metaLoading,
  scopeError,
  availableScopeCodes,
  lastError: metaLastError,
  loadMetaWithScope,
  clearScopeError,
  // [Spec 22 FR-005 2026-09-13 + PM 反馈第十七次 2026-09-13]
  // supportedActions 已由 usePermissionMeta 内部合并 state_transition action_ref
  // 两个调用方（PermissionConfigPanel / ReadonlyAggregateSection）从此同一接口消费
  supportedActions: mergedSupportedActions,
} = usePermissionMeta()

const matrixChanges = ref([])

const roleMatrix = computed(() => meta.value?.role_resource_action_matrix || null)
// supportedActions 直接消费 usePermissionMeta 的合并结果
const supportedActions = mergedSupportedActions
// [Spec 19 FR-012 2026-09-05] 灰化动作说明（说明与限制同源，yaml action_hints → /meta）
const actionHints = computed(() => meta.value?.action_hints || {})
// [Spec 19 FR-014 2026-09-06] 类型层树形数据源（hierarchies.yaml biz_hierarchy → /meta）
const resourceHierarchy = computed(() => meta.value?.resource_hierarchy || {})
const resourceTypeLabels = computed(() => meta.value?.resource_type_labels || {})
const actionLabels = computed(() => meta.value?.action_labels || {})
// [Spec 21 FR-003 2026-09-12] 动作元数据（用于前端按 action_type 分块渲染矩阵列）
// 缺失 → {}，前端 ResourceActionMatrix 走 crud 兜底
const actionMeta = computed(() => meta.value?.action_meta || {})
// [Spec 21 FR-005 PM 反馈 2026-09-12] objectOwdList 已不再需要（OWD 面板从详情页移除）
//   后端 /meta 仍下发 object_owd 字段，保留供 P3「对象安全基线」页面消费

/** [2026-08-28 元模型驱动] 数据范围维度列表从 meta.normalizedForDimensionSelector 派生
 *  （后端 dimension_object_mapping × hierarchies_ui_config 组装，零硬编码），
 *  替代原硬编码 4 维度（product/version/domain/sub_domain）。
 *  meta 未加载时为空数组 → ResourceActionMatrix 数据范围列自动隐藏。 */
const linkageDimensionList = computed(() => meta.value?.normalizedForDimensionSelector || [])

// [一体化 Phase 3 2026-08-25] 范围矩阵 state
//   来源：loadDimensionScopes() 加载后转换为 resource_type → dimension → scope 的嵌套结构
//   传给 ResourceActionMatrix 作为 :scope-matrix prop（一体化表达）
//   保存时由 handleSaveScopeMatrix() 转换为后端接受的 dimension_scopes 格式
const scopeMatrix = ref<Record<string, Record<string, any>>>({})
// [v43 2026-08-27] scopeMatrix 未保存标志：拍快照 + 与当前对比
let scopeMatrixSnapshot: Record<string, any> = {}
const scopeIsDirty = computed(() =>
  JSON.stringify(scopeMatrix.value) !== JSON.stringify(scopeMatrixSnapshot),
)

/** [v43 2026-08-27] 是否有未保存变更（任一来源有变更即触发）
 *   - 菜单勾选有变更 → menuIsDirty
 *   - 矩阵有手动变更 → matrixChanges 非空
 *   - 范围配置有变更 → scopeIsDirty
 *   - 进入编辑态时统一重置所有 snapshot（避免误报）
 *   [BUG-V072-fix2 2026-08-28] 修复: menuIsDirty 由 useMenuPermission 内部维护，
 *     只有 selectAll/clearAll/applyDerived 会调 refreshIsDirty()。但用户通过
 *     MenuPermissionMatrix 的 checkbox UI toggle 后，只 emit('update:modelValue')，
 *     useMenuPermission.isDirty 永远不更新 → hasPendingChanges 永远 false →
 *     watch(isEditing) 退出分支永远走老分支（恢复 editSnapshot），权限改动丢失。
 *     修复: 直接对比当前 menus 与 editSnapshot (任一 assigned 不同 → 有改动)。
 *     这样不依赖 useMenuPermission 的内部状态，也兼容 Matrix 的 toggle。
 */
const menuAssignedDirtyVsSnapshot = computed(() => {
  if (!editSnapshot) return false
  const cur = menus.value || []
  const snap = editSnapshot || []
  if (cur.length !== snap.length) return true
  for (let i = 0; i < cur.length; i++) {
    if (!!cur[i]?.assigned !== !!snap[i]?.assigned) return true
  }
  return false
})
const hasPendingChanges = computed(
  () => menuIsDirty.value || menuAssignedDirtyVsSnapshot.value
    || scopeIsDirty.value || (matrixChanges.value && matrixChanges.value.length > 0),
)

/** [一体化 Phase 3 2026-08-25] 加载范围矩阵（从 role_dimension_scopes 派生为 resource_type 视角） */
async function loadScopeMatrix() {
  if (!props.permissionSetId) return
  if (!/^\d+$/.test(String(props.permissionSetId))) return
  try {
    const r = await permService.loadDimensionScopes(props.permissionSetId)
    if (r.success && r.data) {
      // 后端返回 [{ permission_set_id, dimension_code, scope_mode, dimension_values, ... }]
      // 转换为 resource_type → dimension_code → scope 嵌套结构
      const m: Record<string, Record<string, any>> = {}
      for (const scope of r.data) {
        // 简化映射：每个 dimension_scope 对所有相关 resource_type 都可见（基于 yaml applies_to）
        //   完整实现需要从 meta.normalizedForTreePicker 解析 applies_to 关系
        //   当前简化：scope 绑定到与 dimension_code 同名的资源类型
        if (!m[scope.dimension_code]) m[scope.dimension_code] = {}
        const values = scope.dimension_values || []
        // [Spec 20 v3] 业务键锚点分离: 字符串非数字非 '*' = 业务键 code (如 'SCM')
        //   实例值走 id IN (...); 锚点走 code IN ('SCM') 动态语义, 展示标注「业务键」
        const anchorCodes = []
        const instanceVals = []
        for (const v of values) {
          const raw = typeof v === 'object' ? v.id : v
          if (typeof raw === 'string' && raw !== '*' && !/^-?\d+$/.test(String(raw))) {
            anchorCodes.push(raw)
          } else {
            instanceVals.push(v)
          }
        }
        // [v82 2026-09-03] 旧 include/exclude 数据合成显示字段。
        //   根因：v17 起矩阵 rowScopeMode() 只认 __expression（Rule Builder 产物），
        //   后端 dimension_scopes 的 scope_mode+dimension_values 被一律判「未配置」，
        //   导致迁移/存量的管理维度配置在矩阵上全部显示为空（staging 迁移验证 2026-09-03）。
        //   此处从 dimension_values 合成 __expression/__expression_display/__scope_value_names，
        //   保存路径（saveScopeMatrix）只消费 scope_mode+dimension_values，合成字段不回写。
        const names = instanceVals.map((v: any) =>
          typeof v === 'object' ? (v.name || v.code || String(v.id ?? v)) : String(v))
        const ids = instanceVals.map((v: any) => (typeof v === 'object' ? v.id : v))
        const anchorNames = anchorCodes.map(c => `${c}（业务键）`)
        const isExclude = scope.scope_mode === 'exclude'
        const joinWord = isExclude ? ' AND ' : ' OR '
        const exprParts: string[] = []
        if (ids.length) exprParts.push(`id ${isExclude ? 'NOT IN' : 'IN'} (${ids.join(',')})`)
        if (anchorCodes.length) {
          exprParts.push(`code ${isExclude ? 'NOT IN' : 'IN'} (${anchorCodes.map(c => `'${c}'`).join(',')})`)
        }
        const allNames = [...names, ...anchorNames]
        const display = scope.scope_mode === 'all'
          ? '不限制'
          : allNames.length
            ? `${isExclude ? '排除' : '包含'}: ${allNames.join('、')}`
            : ''
        // [v83 2026-09-03] 结构修正: rt 级平铺 (v82 误写为 m[dim][dim] 双层嵌套)。
        //   渲染端 rowScopeMode() 读 scopeMatrix[rt].__expression (平铺),
        //   Rule Builder 回写 handleConditionSaved 也是平铺; v82 嵌套导致 __expression
        //   读不到 → 迁移/存量配置仍显示「未配置」(staging 1228/1232 实测复现)。
        m[scope.dimension_code] = {
          scope_mode: scope.scope_mode || '',
          dimension_values: values,
          inherit_children: scope.inherit_children,
          __anchor_codes: anchorCodes,
          __scope_value_names: allNames,
          __expression: exprParts.join(joinWord),
          __expression_display: display,
        }
      }
      await hydrateAnchorPreviews(m)
      scopeMatrix.value = m
      // [v43 2026-08-27] 加载完成后拍快照
      scopeMatrixSnapshot = JSON.parse(JSON.stringify(m))
    }
  } catch (e) {
    console.error('[loadScopeMatrix] failed:', e)
  }
}

/** [一体化 Phase 3 2026-08-25] 子组件 scope-change 事件 */
function handleScopeChange(newMatrix: Record<string, Record<string, any>>) {
  scopeMatrix.value = JSON.parse(JSON.stringify(newMatrix))
}

/** [Spec 20 v3] 业务键锚点命中数水合: resolve-preview 回填「业务键·命中 N」, 0 命中警示
 *  仅改展示字段 __scope_value_names/__expression_display; dimension_values 不动 (锚点 code 原样回存) */
async function hydrateAnchorPreviews(m: Record<string, Record<string, any>>) {
  const scopes: any[] = []
  for (const [dim, cfg] of Object.entries(m)) {
    if (Array.isArray(cfg.__anchor_codes) && cfg.__anchor_codes.length > 0) {
      scopes.push({ dimension_code: dim, dimension_values: cfg.__anchor_codes })
    }
  }
  if (scopes.length === 0) return
  if (!props.permissionSetId || !/^\d+$/.test(String(props.permissionSetId))) return
  try {
    const r = await permService.resolveDimensionScopePreview(props.permissionSetId, scopes)
    const data = r?.data || {}
    for (const [dim, info] of Object.entries(data) as [string, any][]) {
      const cfg = m[dim]
      if (!cfg) continue
      const instanceNames = (cfg.__scope_value_names || [])
        .filter((n: string) => !n.includes('（业务键'))
      const anchorNames = (cfg.__anchor_codes || []).map((c: string) => {
        const cnt = info[c]?.resolved_count
        if (cnt === undefined) return `${c}（业务键）`
        return cnt > 0 ? `${c}（业务键·命中 ${cnt}）` : `${c}（业务键·未命中）`
      })
      const allNames = [...instanceNames, ...anchorNames]
      cfg.__scope_value_names = allNames
      const prefix = cfg.scope_mode === 'exclude' ? '排除' : '包含'
      cfg.__expression_display = allNames.length ? `${prefix}: ${allNames.join('、')}` : ''
    }
  } catch (e) {
    console.warn('[Spec20] hydrateAnchorPreviews failed (non-fatal):', e)
  }
}

function handleMatrixChange(changes) {
  matrixChanges.value = changes

  // [v69 2026-08-28] 右侧动作勾选 → 左侧菜单徽章实时联动
  //   根因: 此前 changes 只存入 matrixChanges 供保存用, 从不回写左侧 menus,
  //   导致左侧「32/32 权限」徽章统计与右侧勾选完全脱节（用户实测反馈）
  //   做法: 把 (resource_type, action, granted) 映射回 required_permissions 中的
  //   `${bo_id}:${action}` 权限项, 同步 granted + source, menus 是深层 reactive → 徽章自动刷新
  if (!Array.isArray(changes) || changes.length === 0) return
  const grantedByCode = new Map()
  for (const c of changes) {
    if (c?.resource_type && c?.action) {
      grantedByCode.set(`${c.resource_type}:${c.action}`, !!c.granted)
    }
  }
  if (grantedByCode.size === 0) return
  for (const menu of menus.value || []) {
    // [v70 2026-08-28] 只回写已分配菜单：
    //   未分配菜单的 granted 恒 false（v67 后端同口径），否则矩阵全量回写
    //   会把 role_permissions 残留权限推导出的 cell=true 推给未分配菜单，
    //   导致「已授予 60 → 76」虚增 + 保存时实际写入权限行
    if (!menu.assigned) continue
    for (const p of menu.required_permissions || []) {
      if (grantedByCode.has(p.code)) {
        const g = grantedByCode.get(p.code)
        if (p.granted !== g) {
          p.granted = g
          p.source = g ? 'include' : 'exclude'
        }
      }
    }
  }
}

// [v47 2026-08-27] 底部「保存当前权限」按钮已删除 — 用户明确要求：
//   ObjectPage 顶部「编辑/保存」是唯一标准入口，不再提供底部保存双入口

async function loadMatrixMeta() {
  if (!props.permissionSetId) return
  // 角色未保存（new / 非数字 id）不加载矩阵
  if (!/^\d+$/.test(String(props.permissionSetId))) return
  await loadMetaWithScope(SCOPE_CODE, { permission_set_id: props.permissionSetId })
  // [Spec 22 FR-005 2026-09-13] 加载 state_transition 引用的 action_ref，
  // 合并到 supportedActions 由 usePermissionMeta 内部完成
  // （loadStateTransitionActions 已在 usePermissionMeta 内自动调用）
}

/** [v47 2026-08-27] 把持久化的条件规则合并回 scopeMatrix
 *  根因：ConditionRuleDialog 的 __expression/__rules 只在内存，刷新后丢失；
 *  而规则实际已持久化到 data_permission_rules。加载时回读并按 resource_type
 *  挂到 scopeMatrix[rt].__configured / __expression，让行按钮恢复「配置条件(N 条)」状态。
 *  [v48 2026-08-27] 同资源多条历史规则：取 id 最大（最新）的一条作为当前生效表达式，
 *    记录 _rule_id，弹窗再次保存时走 PUT 更新而非 POST 新建。
 *    旧重复记录的清理已移出加载路径（见 cleanupDuplicateConditionRules）。
 *  注意：__expression_display / __rules 无法从表达式恢复（无 picker 缓存），
 *  弹窗打开时由 ConditionRuleDialog 反解析 + 名称水合补齐。
 *  [2026-08-28 重构] 返回原始规则列表供非阻塞清理任务使用；
 *    emitScopeChange 死调用已删除 —— scopeMatrix 是深层 reactive ref，
 *    经 :scope-matrix prop 传入 ResourceActionMatrix，变更自动联动。
 *  返回：rules 数组（加载失败 / 无 permissionSetId 时返回 null） */
async function mergeSavedConditionRules() {
  if (!props.permissionSetId || !/^\d+$/.test(String(props.permissionSetId))) return null
  try {
    const r = await permService.loadConditionRules({ permission_set_id: props.permissionSetId, rule_type: 'condition' })
    if (!r.success) return null
    const rules = r.data || []
    // 按 resource_type 分组，各组保留 id 最大（最新）的一条
    const latestByRt = new Map()
    for (const rule of rules) {
      const rt = rule.resource_type
      if (!rt || !rule.condition) continue
      const cur = latestByRt.get(rt)
      if (!cur || Number(rule.id) > Number(cur.id)) latestByRt.set(rt, rule)
    }
    for (const [rt, rule] of latestByRt) {
      if (!scopeMatrix.value[rt]) scopeMatrix.value[rt] = {}
      // 只合并不覆盖：本次会话内用户改过的优先（理论上加载阶段无冲突）
      if (!scopeMatrix.value[rt].__expression) {
        scopeMatrix.value[rt].__configured = true
        scopeMatrix.value[rt].__expression = rule.condition
        // [v56 2026-08-27] 持久化的人类可读描述（后端 condition_display 列），
        //   刷新后资源矩阵仍展示中文描述而非技术表达式
        scopeMatrix.value[rt].__expression_display = rule.condition_display || ''
        // [v58 2026-08-27] 旧记录无 condition_display → 纯业务主键表达式前端水合 ID→名称
        //   （hydrateIdExpressionDisplay 已下沉到 service 层，与弹窗 hydratePickerNames 策略一致）
        if (!scopeMatrix.value[rt].__expression_display) {
          hydrateIdExpressionDisplay(rt, rule.condition)
            .then((display) => {
              if (display && scopeMatrix.value[rt] && !scopeMatrix.value[rt].__expression_display) {
                scopeMatrix.value[rt].__expression_display = display
              }
            })
            .catch(() => {})
        }
        scopeMatrix.value[rt]._rule_id = rule.id  // [v48] 弹窗保存时走 PUT 更新
        // [2026-09-05 继承方向] 回读持久化规则的继承方向 → 行内 chip 展示
        //   与 handleConditionRuleSaved 保存路径同构；字段来自 data_permission_rules
        //   统一表（v082 列）。缺失此挂载会导致刷新/重进详情页后 chip 消失。
        scopeMatrix.value[rt]._inherit_flags = {
          down: rule.inherit_to_children !== false && rule.inherit_to_children !== 0,
          up: !!(rule.propagate_to_parents && rule.propagate_to_parents !== 0),
        }
      }
    }
    return rules
  } catch (e) {
    console.warn('[PermissionConfigPanel] mergeSavedConditionRules failed:', e)
    return null
  }
}

/** [2026-08-28 重构] 同资源历史重复规则清理（破坏性副作用移出加载路径）
 *  历史 bug 产物：旧版每次保存都 POST 新行，同 resource_type 堆积多条。
 *  由 initPermissions 在加载完成后 fire-and-forget 调用（不 await），
 *  不阻塞数据可用性；失败静默（仅 console.warn）。 */
async function cleanupDuplicateConditionRules(rules) {
  if (!Array.isArray(rules) || rules.length === 0) return
  try {
    // 按 resource_type 分组，各组保留 id 最大（最新）的一条
    const latestByRt = new Map()
    for (const rule of rules) {
      const rt = rule.resource_type
      if (!rt || !rule.condition) continue
      const cur = latestByRt.get(rt)
      if (!cur || Number(rule.id) > Number(cur.id)) latestByRt.set(rt, rule)
    }
    for (const [rt, rule] of latestByRt) {
      for (const old of rules) {
        if (old.resource_type === rt && Number(old.id) !== Number(rule.id)) {
          permService.deleteConditionRule(old.id).catch(() => {})
        }
      }
    }
  } catch (e) {
    console.warn('[PermissionConfigPanel] cleanupDuplicateConditionRules failed:', e)
  }
}

// [2026-08-28 重构清理] 删除死代码：* 通配符二次确认全流程（showWildcardConfirm 只被置 false
//   从未置 true，对话框永不弹出；pendingWildcardSaveFn 从未被赋值），
//   以及 showLinkageWarning / linkageWarnings（联动警告对话框废弃后的残留）

// [v33 2026-08-27] 删 handleDeleteConditionRule / handleEditConditionRule（条件规则列表回调已无引用）
const totalMenuCount = computed(() => menus.value.length)
const assignedMenuCount = computed(() =>
  menus.value.filter(m => m.assigned).length
)
const totalFuncPermissions = computed(() =>
  menus.value.reduce((sum, m) => sum + (m.required_permissions?.length || 0), 0)
)
// [v70 2026-08-28] 已授予功能权限数（实时联动）：
//   reduce/filter 读取深层 p.granted → Vue 深层响应式追踪, 勾选动作后自动重算
//   与 MenuPermissionMatrix 各菜单徽章（grantedCapCount）统计口径完全一致
const grantedFuncPermissions = computed(() =>
  menus.value.reduce(
    (sum, m) => sum + (m.required_permissions?.filter(p => p.granted).length || 0),
    0,
  )
)

// [2026-08-28 重构清理] 删除死代码：handleMenuPermissionChange（空实现，v-model 已覆盖）、
//   handleToggleActionGroup / handleToggleStandalone（MenuPermissionMatrix 已不 emit 对应事件，
//   且 useMenuPermission 已删除 toggleActionGroup / toggleStandaloneAction）、
//   filteredMenusForView（引用已删除的 sideFocus.menuGroup，且无模板引用）

/** [Phase 3] 菜单视图：选中菜单 → 右侧展示该菜单关联的资源×动作 */
function handleSelectMenu(menu: any) {
  activeMenu.value = menu
}

/** [Phase 5] 清除当前选中菜单，恢复到「全部资源」视图 */
function handleClearActiveMenu() {
  activeMenu.value = null
}

/** [Phase 5] 当前选中菜单（不兜底，未选中时返回 null，右栏显示全部资源） */
const displayedMenu = computed<any>(() => activeMenu.value)

/** [Phase 4] 当前菜单的 required_permissions code 前缀（bo_id）→ 与 yaml resourceTypeLabels 求并集
 *   - 菜单的 bo_id（如 scheduled_task）未必在 yaml 里有同名 resource_type
 *   - [Phase 6 2026-08-25 FIX] 放宽匹配：即使 bo_id 不在 rtl 也展示（fallback label = bo_id）
 *     因为 ResourceActionMatrix 内部用 props.resourceTypeLabels[rt] || rt 作为 label。
 *   - 例: ["scheduled_task:create", "product:read"] → ["scheduled_task", "product"]
 *   - [Phase 6 2026-08-25] 子菜单聚合：选中父菜单时，聚合其所有后代的资源类型（按 menu_path 推断子菜单关系）
 */
const activeMenuResourceTypes = computed<string[]>(() => {
  const menu = displayedMenu.value
  if (!menu) return []
  // [FIX 2026-08-25] 不再过滤 yamlKeys.has() —— 菜单里声明的所有 bo 都展示
  const matched = new Set<string>()
  // 来源1: required_permissions code 前缀
  ;(menu.required_permissions || []).forEach((p: any) => {
    const code = String(p?.code || '')
    const bo = code.split(':')[0]
    if (bo && bo !== '*') matched.add(bo)
  })
  // 来源2: primary_object_type（菜单定义的"主对象"）
  if (menu.primary_object_type) {
    matched.add(menu.primary_object_type)
  }
  // 来源3: object_types
  ;(menu.object_types || []).forEach((t: string) => {
    matched.add(t)
  })
  // [Phase 6] 聚合后代菜单的资源类型
  //   1. menu_path 严格前缀匹配（自上而下的物理层级，如 /system → /system/task-management）
  //   2. parent_menu 字段匹配（菜单元数据声明的逻辑层级，修复 menu_path 与 parent_menu 不一致的菜单）
  const selfPath = String(menu.menu_path || '').replace(/^\/+|\/+$/g, '')
  const selfCode = menu.menu_code
  const descendants = (menus.value || []).filter((m: any) => {
    if (!m) return false
    if (m.menu_code === selfCode) return false  // 不聚合自己
    // 路径前缀匹配
    if (selfPath) {
      const mp = String(m.menu_path || '').replace(/^\/+|\/+$/g, '')
      if (mp && mp !== selfPath && mp.startsWith(selfPath + '/')) return true
    }
    // parent_menu 匹配（兜底）
    if (selfCode && m.parent_menu === selfCode) return true
    return false
  })
  descendants.forEach((m: any) => {
    ;(m.required_permissions || []).forEach((p: any) => {
      const code = String(p?.code || '')
      const bo = code.split(':')[0]
      if (bo && bo !== '*') matched.add(bo)
    })
    if (m.primary_object_type) {
      matched.add(m.primary_object_type)
    }
    ;(m.object_types || []).forEach((t: string) => {
      matched.add(t)
    })
  })
  return Array.from(matched)
})

/** [Phase 6 2026-08-25] 矩阵的外部筛选数据源：
 *   - 已选菜单 → 该菜单关联资源类型（allowlist 强筛选）
 *   - 未选菜单 → 空数组，ResourceActionMatrix 自己默认展示 yaml 声明的 9 个核心资源
 *   （删除原 sideFocus.resourceTypes 引用：侧边栏资源分组已删除，无来源）
 */
const matrixExternalFilters = computed<string[]>(() => {
  if (displayedMenu.value) return activeMenuResourceTypes.value
  return []
})

/** [Phase 6 2026-08-25] 矩阵的外部筛选模式：已选菜单用 allowlist（强制只显示白名单）；
 *   未选菜单用 sync（让矩阵按自身 prop 规则过滤，不强制 allowlist） */
const matrixExternalFilterMode = computed<'allowlist' | 'sync'>(() => {
  if (displayedMenu.value) return 'allowlist'
  return 'sync'
})

/** [Phase 5] 矩阵标题 */
const matrixTitle = computed<string>(() => {
  if (displayedMenu.value) return `资源 × 动作 · ${displayedMenu.value.display_name}`
  return '资源 × 动作'
})

function selectAllMenus() {
  selectAll()
}

/**
 * [v40 2026-08-27] 编辑态快照（一体化模式）
 *  - 进入编辑（props.editing false→true）：克隆 menus 快照
 *  - 退出编辑（true→false，即 ObjectPage「取消」）：恢复快照 = 原「重置」语义
 */
let editSnapshot: any = null
watch(isEditing, (now, before) => {
  if (now && !before) {
    // 简单深拷贝依赖 JSON（结构内仅含 primitives / plain 对象 / array）
    editSnapshot = JSON.parse(JSON.stringify(menus.value))
    // [v43 2026-08-27] 进入编辑时，矩阵变更清空、范围快照重置（避免误报未保存变更）
    matrixChanges.value = []
    scopeMatrixSnapshot = JSON.parse(JSON.stringify(scopeMatrix.value))
  } else if (!now && before) {
    // [BUG-V072 2026-08-28] ObjectDetailPage 路径: 外层保存只更新 role 基本信息,
    //   不调 permPanelRef.save() → 权限菜单改动会随菜单回滚丢失.
    //   flushOnExit=true 时, 退出编辑时先 async 提交权限, 失败则保留菜单 (避免静默吞).
    if (props.flushOnExit && hasPendingChanges.value) {
      savePermissions().catch(err => {
        // 保留菜单状态 (不回滚), 让外层消息中心提示用户去手动重试
        console.error('[PermissionConfigPanel] flushOnExit save failed:', err)
        message.error('权限保存失败，请检查后重试', err)
      })
      // 注意: 不再回滚菜单, 让已保存到服务器的改动保留; 同时不再清 editSnapshot
      // (下一次进入编辑态会重新拍)
      matrixChanges.value = []
      scopeMatrixSnapshot = JSON.parse(JSON.stringify(scopeMatrix.value))
      return
    }
    if (editSnapshot) {
      menus.value = editSnapshot as any
      // [2026-08-28 重构清理] 原 applyDerived?.() 调用已删除：
      //   applyDerived(recommendedMenuCodes, derivedPermCodes) 需要两个参数，
      //   无参调用是无效死调用；menus.value = editSnapshot 替换整个数组，
      //   响应式自然触发所有派生计数（grantedFuncPermissions 等）重算
    }
    // [v43 2026-08-27] 退出编辑时清空所有变更
    matrixChanges.value = []
    scopeMatrixSnapshot = JSON.parse(JSON.stringify(scopeMatrix.value))
    editSnapshot = null
  }
})

function clearAllMenus() {
  clearAll()
}

async function savePermissions() {
  // [一体化 Phase 3 2026-08-25] 一体化保存：动作授权 + 范围配置 + Deny 一并落库
  //   不再需要联动校验对话框 — 范围与动作在同一组件内表达，一致性天然保证
  // [v41 2026-08-27] BUG 修复：此前只调 saveMenuPermissions（菜单勾选 + 推导 permissions），
  //   完全没提交资源×动作矩阵 cell.granted 变更，导致用户改矩阵后保存无效果。
  //   新增矩阵保存调用（与 _build_role_matrices 的 manual 来源语义对齐）。
  // [2026-08-28 重构清理] saving ref 已删除（无任何读取方，保存中状态由 ObjectPage 顶层管理）
  try {
    // 1. 保存资源×动作授权（矩阵）
    if (props.permissionSetId && /^\d+$/.test(String(props.permissionSetId))) {
      const cells = (matrixChanges.value || []).filter(
        (c) => c && c.resource_type && c.action,
      )
      if (cells.length > 0) {
        await permService.saveResourceActionMatrix(props.permissionSetId, cells)
      }
    }

    // 2. 保存菜单权限（菜单勾选 + 派生 permissions）
    await saveMenuPermissions()

    // 3. 保存范围（一体化后 scope 绑定到 resource_type，需要聚合回 dimension 维度）
    const scopeWarnings = await saveScopeMatrix()

    // [v43 2026-08-27] 全部保存成功 → 清空矩阵变更、重置范围快照
    matrixChanges.value = []
    scopeMatrixSnapshot = JSON.parse(JSON.stringify(scopeMatrix.value))
    // [v59 2026-08-27] 同步刷新编辑快照：外层保存成功后才置 isEditing=false，
    // watch 退出分支会用 editSnapshot 恢复 UI——若不刷新，恢复的是进入编辑前的旧勾选，
    // 用户会看到已保存的勾选"弹回"旧值
    editSnapshot = JSON.parse(JSON.stringify(menus.value))

    // [Spec 20] 锚点 0 命中警示 (保存已成功, 不阻断)
    if (Array.isArray(scopeWarnings) && scopeWarnings.length > 0) {
      message.warning('已保存，但存在范围警示：' + scopeWarnings.join('；'))
    } else {
      message.saved('权限设置（含范围配置）')
    }
    emit('saved')
  } catch (error) {
    message.error('保存权限设置失败：' + (error?.message || '请稍后重试'), error)
    throw error // [v40] 外层 ObjectPage handleSave 需感知失败以提示
  }
}

// [v40 2026-08-27] 一体化保存入口：外层 ObjectPage「保存」按钮通过 ref 调用
defineExpose({
  save: savePermissions,
})

/** [一体化 Phase 3 2026-08-25] 把 scopeMatrix 聚合为后端 dimension_scopes 格式保存
 *  聚合策略：每个 dimension 维度取所有 resource_type 中「最严格」的范围配置
 *    - 如果任一 resource_type 是 'exclude' → 用 exclude（排除优先）
 *    - 否则如果任一 resource_type 是 'include' 且有值 → 用并集
 *    - 否则如果任一 resource_type 是 'all' → 用 all
 *    - 否则跳过（dimension 未配置）
 */
async function saveScopeMatrix() {
  if (!props.permissionSetId) return
  const scopes: any[] = []
  // [v83 2026-09-03] 平铺结构回写: scopeMatrix 运行时结构是 rt 级平铺
  //   (rowScopeMode / handleConditionSaved / v83 合成加载均为平铺)。
  //   旧 [rt][dimId] 嵌套遍历在平铺结构下恒产出空 scopes, 而后端 POST 空 list = 全量清空
  //   (save_dimension_scopes 先 DELETE 再 INSERT), 会导致「打开详情→点保存」把迁移/存量配置洗掉。
  //   现按平铺原样回写; Rule Builder 元字段 (__configured/__expression 等, 无 scope_mode) 自然跳过。
  for (const [rt, cfg] of Object.entries(scopeMatrix.value)) {
    if (!cfg || typeof cfg !== 'object' || !cfg.scope_mode) continue
    const values = Array.isArray(cfg.dimension_values) ? cfg.dimension_values : []
    const inherit = cfg.inherit_children === undefined ? true : !!cfg.inherit_children
    if (cfg.scope_mode === 'exclude' && values.length > 0) {
      scopes.push({ dimension_code: rt, scope_mode: 'exclude', dimension_values: Array.from(new Set(values)), inherit_children: inherit })
    } else if (cfg.scope_mode === 'all') {
      scopes.push({ dimension_code: rt, scope_mode: 'all', dimension_values: [], inherit_children: inherit })
    } else if (cfg.scope_mode === 'include' && values.length > 0) {
      scopes.push({ dimension_code: rt, scope_mode: 'include', dimension_values: Array.from(new Set(values)), inherit_children: inherit })
    }
  }
  // [Spec 20] 后端锚点预检警示 (0 命中不阻塞): 返回给保存入口提示用户
  const r = await permService.saveDimensionScopes(props.permissionSetId, scopes)
  return (r && Array.isArray(r.warnings)) ? r.warnings : []
}

// [v33 2026-08-27] 删 handleDeleteConditionRule / handleEditConditionRule（条件规则列表回调已无引用）

// [Spec 22 PM 反馈第十八次 2026-09-13] ConditionRuleDialog 接入 useConditionRuleDialog 单一真源
//   编辑态保存回写 scopeMatrix 由 onSaved 回调接管（原 handleConditionRuleSaved 的核心逻辑）
function onConditionRuleSaved(savedRule) {
  if (!savedRule || !savedRule.resource_type || !savedRule.condition) return
  const rt = savedRule.resource_type
  if (!scopeMatrix.value[rt]) scopeMatrix.value[rt] = {}
  scopeMatrix.value[rt].__configured = true
  scopeMatrix.value[rt].__expression = savedRule.condition
  scopeMatrix.value[rt].__expression_display = savedRule.condition_display || ''
  if (Array.isArray(savedRule.rules)) {
    scopeMatrix.value[rt].__rules = JSON.parse(JSON.stringify(savedRule.rules))
  }
  if (savedRule.rule_id) {
    scopeMatrix.value[rt]._rule_id = savedRule.rule_id
  }
  scopeMatrix.value[rt]._inherit_flags = {
    down: savedRule.inherit_to_children !== false && savedRule.inherit_to_children !== 0,
    up: !!(savedRule.propagate_to_parents && savedRule.propagate_to_parents !== 0),
  }
}

// dialog 实例（条件规则弹窗）
const {
  editingRule: dialogEditingRule,
  showDialog: dialogShow,
  dialogReadonly,
  open: openConditionDialog,
  close: closeConditionDialog,
  handleSaved: dialogHandleSaved,
} = useConditionRuleDialog({
  permissionSetId: toRef(props, 'permissionSetId'),
  getRowScope: (rt) => scopeMatrix.value[rt] || {},
  isEditing,
  onSaved: onConditionRuleSaved,
})

// v45 [2026-08-27 保留] 只读态防御：理论上 dialog 在只读态没有保存按钮；保留警告便于排查
function handleConditionRuleSaved(savedRule) {
  if (!isEditing.value) {
    message.warning('当前为浏览态，无法保存条件规则')
  }
  return dialogHandleSaved(savedRule)
}

async function initPermissions() {
  if (!props.permissionSetId) return
  try {
    await loadMenus()
    await loadMatrixMeta()         // [P2-Matrix-01] 加载资源×动作矩阵
    await loadScopeMatrix()        // [一体化 Phase 3] 加载范围矩阵（从 dimension_scopes 派生）
    const savedRules = await mergeSavedConditionRules()  // [v47] 回读持久化条件规则 → 行按钮恢复已配置状态
    // [2026-08-28] 破坏性清理（历史重复规则删除）移出加载路径：非阻塞执行
    void cleanupDuplicateConditionRules(savedRules)
  } catch (e) {
    console.error('[PermissionConfigPanel] initPermissions error:', e)
  }
}

onMounted(() => {
  initPermissions()
})
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.permission-config-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

/* [v43 2026-08-27] 浏览态视觉降级（仅卡片外壳轻微灰化，元素 disabled 由子组件控制）
   删除 v41 的 .pcp-readonly-banner（顶部 banner）与 .pcp-status-chip（菜单卡 chip）
   业内共识：SAP Fiori Object Page / OutSystems Read-Only 模式不显示额外状态指示
*/
.pcp--readonly {
  .menu-permission-card,
  .resource-matrix-card {
    /* 子组件已用 :readonly 禁用 input；此处让卡片外壳做轻微灰化提示 */
    opacity: 0.92;
    transition: opacity 0.15s ease;
  }
}

/* [v43 2026-08-27] 底部「有未保存的变更」提示
   - 出现在编辑态且 hasPendingChanges=true 时
   - 蓝色 info 风格，与主操作按钮拉开间距 */
.pcp-pending-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--color-warning, #faad14);
  font-size: var(--font-size-sm);
  font-weight: 500;
}

/* [2026-08-28 重构清理] 删除死样式：.matrix-section / .perm-section h4（模板已无对应节点）、
   .condition-section（条件规则入口已迁移至资源矩阵 chip）、wildcard-confirm 系列、
   .pcp-subtabs（AppSegment 不存在，视图切换器整体删除）、.pcp-mb-md / .pcp-menu-empty /
   .pcp-bottom-right / .btn-link / .btn-primary / .btn-danger（无引用）、
   linkage-* 全系（Tab2 联动区死代码对应样式） */

.matrix-scope-error {
  margin-bottom: var(--spacing-md);

  .matrix-scope-codes {
    display: block;
    margin-top: var(--spacing-xs);
    font-size: var(--font-size-xs);
    opacity: 0.85;
  }
}

/* [v34 2026-08-27] 元数据加载失败诊断（HTTP / 网络 / 后端异常） */
.matrix-meta-error {
  margin-bottom: var(--spacing-md);

  .matrix-meta-diag {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: var(--spacing-xs);
    font-size: var(--font-size-xs);
    opacity: 0.9;

    span {
      font-family: ui-monospace, 'SF Mono', monospace;
    }
  }
}

/* [v35 2026-08-27] 删 .matrix-loading + 旧 .perm-section（外层 box 已替换为 AppCard） */

.perm-actions-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-light);
}

.actions-spacer {
  flex: 1;
}
.perm-actions-meta { /* [v35 2026-08-27] 右侧统计：已分配菜单数 + 功能权限数 */
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  /* [v71 2026-08-28] 对齐 UI 规范: 移除 monospace, 统一系统字体栈 */
  white-space: nowrap;
}

.btn {
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  transition: all var(--transition-fast);

  &:hover {
    border-color: var(--color-border);
    color: var(--color-text-primary);
  }

  &.btn-sm {
    padding: 2px var(--spacing-sm);
    font-size: var(--font-size-xs);
  }
}

/* [2026-08-28 重构清理] wildcard-confirm 对话框样式随死代码（对话框永不弹出）一并删除 */

/* [v35 2026-08-27] header/nav 已删除，无残留样式 */

/* [Phase 1 2026-08-25] 删除侧边栏后改为单列布局 */
.pcp-layout {
  display: block;
}

.pcp-content {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm); /* [v35 2026-08-27] 紧湊：section 之间间距从 md→sm */
}
.pcp-content--full {
  width: 100%;
}

/* [2026-08-28 重构清理] .pcp-subtabs / .pcp-subtab 随视图切换器死代码一并删除 */

.perm-section--inline {
  /* [v35 2026-08-27] 信息结构重组后，section 内部已用 AppCard 提供视觉边界，
     此处去除外层 box / padding，避免双重框架 + 顶部大空白。 */
  padding: 0;
  background: transparent;
  border: none;
}

/* [Phase 3] 菜单视图 · 左右双栏：左菜单卡片列表 / 右该菜单的 bo × 动作编辑器 */
.pcp-menu-dual {
  display: grid;
  grid-template-columns: minmax(260px, 0.8fr) minmax(0, 1.6fr);
  gap: var(--spacing-md);
  align-items: flex-start;
}
.pcp-menu-left {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  min-width: 0;
}
.pcp-menu-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm); /* [v35 2026-08-27] 矩阵上方 AppAlert 与 ResourceActionMatrix 间距 */
}
.pcp-menu-right > :deep(.app-alert) {
  margin-bottom: 0;
}
.menu-permission-card {
  /* [v35 2026-08-27] 菜单 AppCard：紧凑、自身不限制高度（AppCard 默认 max-height 会让 menu 列表被裁） */
  align-self: stretch;
}
/* [v38 2026-08-27] AppCard__body & AppCard__header 内边距压缩：
   整体目标是让"标题栏 → 搜索栏 → 菜单列表"三条元素紧贴，没有任何视觉空白带 */
.menu-permission-card :deep(.app-card__header) {
  padding-bottom: var(--spacing-xs); /* 16 → 4 */
}
.menu-permission-card :deep(.app-card__body) {
  padding-top: 0;   /* 24 → 0 */
  padding-bottom: var(--spacing-md); /* 24 → 16 */
}
.menu-permission-card :deep(.menu-list) {
  /* [v37 2026-08-27] 紧凑顶端：搜索栏紧贴 title，去掉 menu-list 与搜索栏之间的 padding-top */
  max-height: 460px;
  overflow-y: auto;
  padding: 0;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-sm);
  background: var(--color-bg-container);
  margin-top: 0; /* [v38] 取消 4px 间距，最终态与搜索栏合并为一个视觉块 */
}

/* [v38 2026-08-27] 资源矩阵 AppCard：同步菜单卡的紧凑节奏 */
.resource-action-matrix {
  align-self: stretch;
}
.resource-action-matrix :deep(.app-card__header) {
  padding-bottom: var(--spacing-xs); /* 16 → 4：与 .ram-filter-bar 顶部紧贴 */
}
.resource-action-matrix :deep(.app-card__body) {
  padding-top: 0;   /* 24 → 0：让筛选栏紧贴 header */
  padding-bottom: var(--spacing-md);
}
/* [2026-08-28 重构清理] .pcp-menu-empty 无模板引用，删除 */

/* [v34 2026-08-27] deny/owd 已合并入资源矩阵 chip 入口，section 已删除 */

/* 底部固定操作栏（sticky） */
.pcp-bottom-bar {
  position: sticky;
  bottom: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
  padding: var(--spacing-md) var(--spacing-lg);
  margin-top: var(--spacing-md);
  background: var(--color-bg-panel);
  border-top: 1px solid var(--color-border-subtle);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}
.pcp-bottom-left { flex: 1 1 auto; }

/* [2026-08-28 重构清理] .pcp-bottom-right / .btn-link / linkage-* 全系
   （Tab2 联动区死代码对应样式）一并删除 */

</style>
