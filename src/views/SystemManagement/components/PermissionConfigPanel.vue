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
                    <!-- [v70 2026-08-28] 「共 X 项」原为静态总量不联动, 改为「已授予 G / 总量 82」与菜单徽章同口径 -->
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

              <!-- [v34 2026-08-27] 非 scope 类失败（500/网络/后端异常）的诊断 -->
              <AppAlert v-else-if="metaLastError && !metaLoading" type="error" class="matrix-meta-error">
                <strong>元数据加载失败：</strong>{{ metaLastError.message }}
                <span class="matrix-meta-diag">
                  <span v-if="metaLastError.httpStatus">HTTP {{ metaLastError.httpStatus }}</span>
                  <span v-if="metaLastError.code">code: {{ metaLastError.code }}</span>
                  <span>请求：GET /api/v2/bo/permission_dimension/meta?scope_code=SCP&amp;role_id={{ props.roleId }}</span>
                  <span>排查：① 后端 Python 服务是否启动；② /api/v2/bo/permission_dimension/meta 接口是否注册；③ 角色 ID 是否已保存为数字 ID。</span>
                </span>
              </AppAlert>

              <ResourceActionMatrix
                class="resource-action-matrix"
                :loading="metaLoading"
                :matrix="roleMatrix"
                :supported-actions="supportedActions"
                :resource-type-labels="resourceTypeLabels"
                :action-labels="actionLabels"
                :external-resource-filters="matrixExternalFilters"
                :external-resource-filter-mode="matrixExternalFilterMode"
                :title="matrixTitle || '资源 × 功能权限'"
                :subtitle="displayedMenu ? '' : '全部资源（受左侧菜单/资源分组筛选）'"
                :context-menu="displayedMenu"
                :readonly="!isEditing"
                @clear-context="handleClearActiveMenu"
                :dimensions="linkageDimensionList"
                :scope-matrix="scopeMatrix"
                @change="handleMatrixChange"
                @scope-change="handleScopeChange"
                @open-condition-dialog="handleOpenConditionDialog"
              />
            </div>
          </div>
        </section>
      </main>
    </div>

    <!-- [一体化 Phase 3 2026-08-25 废弃] 联动警告对话框已删除
         一体化后，范围与动作在同一组件内表达，无需联动校验对话框
         保留 state refs 以避免破坏编译 -->

    <ConditionRuleDialog
      v-if="showAddConditionDialog"
      :role-id="roleId"
      :editing-rule="editingRule"
      :readonly="dialogReadonly"
      @close="handleConditionDialogClose"
      @saved="handleConditionRuleSaved"
    />

    <!-- ====================================================================== -->
    <!-- [v43 2026-08-27] 底部操作栏                                            -->
    <!--   - v47 用户明确要求：不增加底部保存按钮，ObjectPage 顶部「编辑/保存」  -->
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
import ConditionRuleDialog from '../ConditionRuleDialog.vue'
import { useMenuPermission } from '../composables/useMenuPermission'
import { useMessage } from '@/composables/useMessage'
// [P2-Matrix-01] 权限配置元数据加载（scopeCode 3 层保护）
import { usePermissionMeta } from '@/composables/usePermissionMeta'
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
  roleId: string
  /** [v40 2026-08-27] 编辑态由外层 ObjectPage 统一控制（一体化模式） */
  editing?: boolean
  /**
   * [BUG-V072 2026-08-28] 退出编辑时是否自动 flush 权限保存
   * 背景: ObjectDetailPage 路由（/detail/role/:id）的保存按钮只调
   *   boService.update('role', ...) 保存基本信息, 完全不触发 permPanelRef.save(),
   *   导致用户在权限面板反勾选菜单后点保存, 实际只保存了 name/description/is_active,
   *   刷新后菜单从 DB 重读回来仍是勾选态 —— 表现为"反勾选后又被勾上".
   * 修复: ObjectDetailPage 传 :flush-on-exit="true", watch(isEditing) 退出时
   *   若有未保存改动 → 先 savePermissions() 再清回滚 (保留菜单改动).
   *   RolePermissionDetail 路由不传 (默认 false), 走原有"编辑→取消→回滚快照"逻辑,
   *   由外层自己调 permPanelRef.save() (RolePermissionDetail.handleSave 已实现).
   */
  flushOnExit?: boolean
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
} = useMenuPermission(toRef(props, 'roleId'))

const showAddConditionDialog = ref(false)
const editingRule = ref(null)

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
// 通过 /permission_dimension/meta?role_id&scope_code=SCP 加载：
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
} = usePermissionMeta()

const matrixChanges = ref([])

const roleMatrix = computed(() => meta.value?.role_resource_action_matrix || null)
const supportedActions = computed(() => meta.value?.resource_action_matrix || {})
const resourceTypeLabels = computed(() => meta.value?.resource_type_labels || {})
const actionLabels = computed(() => meta.value?.action_labels || {})

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
  if (!props.roleId) return
  if (!/^\d+$/.test(String(props.roleId))) return
  try {
    const r = await permService.loadDimensionScopes(props.roleId)
    if (r.success && r.data) {
      // 后端返回 [{ role_id, dimension_code, scope_mode, dimension_values, ... }]
      // 转换为 resource_type → dimension_code → scope 嵌套结构
      const m: Record<string, Record<string, any>> = {}
      for (const scope of r.data) {
        // 简化映射：每个 dimension_scope 对所有相关 resource_type 都可见（基于 yaml applies_to）
        //   完整实现需要从 meta.normalizedForTreePicker 解析 applies_to 关系
        //   当前简化：scope 绑定到与 dimension_code 同名的资源类型
        if (!m[scope.dimension_code]) m[scope.dimension_code] = {}
        m[scope.dimension_code][scope.dimension_code] = {
          scope_mode: scope.scope_mode || '',
          dimension_values: scope.dimension_values || [],
        }
      }
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

/** [Phase 3.5e 2026-08-25] 资源行「⚙ 自定义表达式」按钮触发 → 打开 ConditionRuleDialog
 *   v6 修正：
 *     - payload.mode 决定 dialog 打开哪个 mode（默认 'custom'）
 *     - 资源行 expression 入口总是打开 custom mode（维度自选 SQL）
 *   参数：{ resourceType, rowLabel, mode } — 资源类型 + 显示名 + dialog mode
 * [v45 2026-08-27] 浏览态不再拦截：允许点击查看条件，弹窗以只读模式展示
 *   （交互方案对齐「浏览可看、编辑可改」的 SAP Fiori display/edit 双态惯例） */
const dialogReadonly = ref(false)
function handleOpenConditionDialog(payload: { resourceType: string; rowLabel: string; mode?: string; readonly?: boolean }) {
  dialogReadonly.value = !isEditing.value
  // [v46 2026-08-27] 回填已保存的规则：condition + 结构化规则快照（__rules）
  const existing = scopeMatrix.value[payload.resourceType] || {}
  editingRule.value = {
    resource_type: payload.resourceType,
    rowLabel: payload.rowLabel,  // [Phase 3.14] 新增
    mode: payload.mode || 'custom',  // v6：默认 custom mode
    condition: existing.__expression || '',
    condition_display: existing.__expression_display || '',
    initialRules: existing.__rules || [],  // [v46] 有则回填 builder
    rule_id: existing._rule_id || null,  // [v48] 后端 id → 弹窗保存走 PUT 更新
  }
  showAddConditionDialog.value = true
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
  if (!props.roleId) return
  // 角色未保存（new / 非数字 id）不加载矩阵
  if (!/^\d+$/.test(String(props.roleId))) return
  await loadMetaWithScope(SCOPE_CODE, { role_id: props.roleId })
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
 *  返回：rules 数组（加载失败 / 无 roleId 时返回 null） */
async function mergeSavedConditionRules() {
  if (!props.roleId || !/^\d+$/.test(String(props.roleId))) return null
  try {
    const r = await permService.loadConditionRules({ role_id: props.roleId, rule_type: 'condition' })
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
    if (props.roleId && /^\d+$/.test(String(props.roleId))) {
      const cells = (matrixChanges.value || []).filter(
        (c) => c && c.resource_type && c.action,
      )
      if (cells.length > 0) {
        await permService.saveResourceActionMatrix(props.roleId, cells)
      }
    }

    // 2. 保存菜单权限（菜单勾选 + 派生 permissions）
    await saveMenuPermissions()

    // 3. 保存范围（一体化后 scope 绑定到 resource_type，需要聚合回 dimension 维度）
    await saveScopeMatrix()

    // [v43 2026-08-27] 全部保存成功 → 清空矩阵变更、重置范围快照
    matrixChanges.value = []
    scopeMatrixSnapshot = JSON.parse(JSON.stringify(scopeMatrix.value))
    // [v59 2026-08-27] 同步刷新编辑快照：外层保存成功后才置 isEditing=false，
    //   watch 退出分支会用 editSnapshot 恢复 UI——若不刷新，恢复的是进入编辑前的旧勾选，
    //   用户会看到已保存的勾选"弹回"旧值
    editSnapshot = JSON.parse(JSON.stringify(menus.value))

    message.saved('权限设置（含范围配置）')
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
  if (!props.roleId) return
  const scopes: any[] = []
  // 聚合：按 dimension_code 分组
  const byDim: Record<string, any[]> = {}
  for (const [rt, dimMap] of Object.entries(scopeMatrix.value)) {
    for (const [dimId, cfg] of Object.entries(dimMap)) {
      if (!byDim[dimId]) byDim[dimId] = []
      byDim[dimId].push({ resource_type: rt, ...cfg })
    }
  }
  for (const [dimId, cfgs] of Object.entries(byDim)) {
    // 聚合策略
    const excludedCfgs = cfgs.filter(c => c.scope_mode === 'exclude')
    const allCfgs = cfgs.filter(c => c.scope_mode === 'all')
    const includeCfgs = cfgs.filter(c => c.scope_mode === 'include' && (c.dimension_values || []).length > 0)

    if (excludedCfgs.length > 0) {
      // 排除优先（任何 exclude 都生效）
      const excludeValues = excludedCfgs.flatMap(c => c.dimension_values || [])
      scopes.push({
        dimension_code: dimId,
        scope_mode: 'exclude',
        dimension_values: Array.from(new Set(excludeValues)),
      })
    } else if (allCfgs.length > 0) {
      scopes.push({ dimension_code: dimId, scope_mode: 'all', dimension_values: [] })
    } else if (includeCfgs.length > 0) {
      // 包含：并集
      const includeValues = includeCfgs.flatMap(c => c.dimension_values || [])
      scopes.push({
        dimension_code: dimId,
        scope_mode: 'include',
        dimension_values: Array.from(new Set(includeValues)),
      })
    }
    // 其他情况：dimension 未配置，跳过
  }
  await permService.saveDimensionScopes(props.roleId, scopes)
}

// [v33 2026-08-27] 删 handleDeleteConditionRule / handleEditConditionRule（条件规则列表回调已无引用）

function handleConditionDialogClose() {
  showAddConditionDialog.value = false
  editingRule.value = null
}

async function handleConditionRuleSaved(savedRule) {
  // [v45 2026-08-27] 弹窗现在浏览/编辑双态都可打开，但只读弹窗没有保存按钮，
  //   此 guard 保留为纵深防御（理论上只读态不会走到这里）。
  if (!isEditing.value) {
    handleConditionDialogClose()
    message.warning('当前为浏览态，无法保存条件规则')
    return
  }
  // [Phase 3.16 2026-08-25] v16：保存时把 expression 同步到 scopeMatrix
  //   让 ResourceActionMatrix 的 rowScopeMode() 能识别"已配置"状态
  // [v33 2026-08-27] 去掉 await loadRules()——条件规则列表入口已删除，无刷新目标
  if (savedRule && savedRule.resource_type && savedRule.condition) {
    const rt = savedRule.resource_type
    if (!scopeMatrix.value[rt]) scopeMatrix.value[rt] = {}
    scopeMatrix.value[rt].__configured = true
    scopeMatrix.value[rt].__expression = savedRule.condition
    // [v45 2026-08-27] 人类可读表达式（字段中文 label + picker 显示名），按钮预览优先用
    scopeMatrix.value[rt].__expression_display = savedRule.condition_display || ''
    // [v46 2026-08-27] 结构化规则快照（含 picker 显示名缓存），再次打开弹窗时回填 builder
    if (Array.isArray(savedRule.rules)) {
      scopeMatrix.value[rt].__rules = JSON.parse(JSON.stringify(savedRule.rules))
    }
    // [v48 2026-08-27] 记录后端规则 id（新建时后端返回），后续保存走 PUT 更新
    if (savedRule.rule_id) {
      scopeMatrix.value[rt]._rule_id = savedRule.rule_id
    }
    // scopeMatrix 深层响应式 → ResourceActionMatrix chip 状态自动更新
  }
  handleConditionDialogClose()
}

async function initPermissions() {
  if (!props.roleId) return
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
