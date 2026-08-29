<template>
  <AppCard
    class="resource-action-matrix"
    :title="props.title || '资源 × 动作'"
    :subtitle="props.subtitle || ''"
  >
    <!-- [v37 2026-08-27] 当前上下文 chip 已下沉到 #extra slot（与分页器同行）：
         原来的位置是 subtitle 下方，会让 AppCard 顶部再开一行。
         现在 chip 与 ram-pager 横排在 AppCard 右上角，紧凑且与 subtitle 同高。 -->

    <!-- [v34 2026-08-27] 资源行分页控件（AppCard extra slot · 标题右侧） -->
    <template #extra>
      <div class="ram-extra">
        <!-- [v37 2026-08-27] 选中菜单时显示并支持清除，紧凑的 chip + 清除按钮 -->
        <span v-if="props.contextMenu" class="ram-context-chip">
          <AppIcon name="check" :size="12" />
          <span class="ram-context-label">已选菜单：</span>
          <strong>{{ props.contextMenu.display_name }}</strong>
          <button class="ram-context-clear" @click="$emit('clear-context')">清除</button>
        </span>
        <div v-if="filteredRows.length > 0" class="ram-pager">
          <span class="ram-pager-info">
            {{ (currentPage - 1) * PAGE_SIZE + 1 }}-{{ Math.min(currentPage * PAGE_SIZE, filteredRows.length) }} / {{ filteredRows.length }}
          </span>
          <AppButton size="sm" variant="text" :disabled="currentPage <= 1" @click="goPrevPage">
            ‹
          </AppButton>
          <AppButton size="sm" variant="text" :disabled="currentPage >= totalPages" @click="goNextPage">
            ›
          </AppButton>
        </div>
      </div>
    </template>
    <!-- 筛选栏（Spec 5.3.1） -->
    <div class="ram-filter-bar">
      <ElSelect
        v-model="resourceFilters"
        placeholder="资源类型（多选）"
        size="small"
        clearable
        filterable
        multiple
        collapse-tags
        class="ram-filter-resource"
      >
        <ElOption
          v-for="opt in resourceOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </ElSelect>
      <ElSelect
        v-model="actionFilter"
        placeholder="动作"
        size="small"
        clearable
        filterable
        class="ram-filter-action"
      >
        <ElOption
          v-for="opt in actionOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </ElSelect>
      <el-checkbox v-model="onlyAssigned" class="ram-only-assigned">
        仅显示已分配
      </el-checkbox>
      <span class="ram-spacer"></span>
      <AppButton size="sm" variant="secondary" :disabled="props.readonly" @click="selectAllFiltered">
        全选当前筛选
      </AppButton>
      <AppButton size="sm" variant="secondary" :disabled="props.readonly" @click="clearFiltered">
        清空当前筛选
      </AppButton>
    </div>

    <!-- 矩阵表：行 = 资源，列 = 动作（动态，A5 灰化禁选） -->
    <!-- matrix=null 时不挂载 el-table，避免出现"空表头"让用户误以为数据空。
         loading=true 时父级 v-if 会走骨架占位；loading=false 且 matrix=null 显示下方"元数据未就绪"提示。 -->
    <el-table
      v-if="props.matrix"
      v-loading="loading"
      :data="pagedRows"
      border
      size="small"
      class="ram-table"
      :header-cell-style="{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)' }"
    >
      <!-- 资源列 -->
      <el-table-column label="资源" min-width="120" fixed="left">
        <template #default="{ row }">
          <el-tooltip
            v-if="isRowReadonly(row)"
            :content="rowReadonlyReason(row)"
            placement="top"
            :teleported="true"
          >
            <span class="ram-resource-label ram-resource-label--readonly">
              {{ resourceLabel(row) }}
              <AppIcon name="lock" :size="11" class="ram-row-lock" />
            </span>
          </el-tooltip>
          <span v-else class="ram-resource-label">{{ resourceLabel(row) }}</span>
        </template>
      </el-table-column>

      <!-- [一体化 Phase 3 2026-08-25] 范围列
           头部产品对照：SAP/AWS IAM 都是「字段 + 操作符 + 值」单层，无 resource-level mode chip
           v17 简化：
             - 去掉 v16 的「未配置 / 已配置」2-mode chip
             - 资源行只有 1 个按钮「配置条件」
               · 未配置 → outline 风格按钮（灰色边框），文案「+ 配置条件」
               · 已配置 → 实色风格按钮（主色边框 + 浅主色背景），文案「⚙ N 条规则」+ 预览表达式
             - 按钮自身显示状态，mode chip 不再承担状态标识
           头部产品对照：
             - SAP PFCG: 直接打开条件规则列表编辑器，无 mode 切换
             - AWS IAM: 直接打开 condition 编辑器，无 mode 切换
             - Airtable Filter: 直接进入 filter 配置
           「包含 vs 排除」由 Rule Builder 操作符承载（IN/NOT IN/LIKE/NOT LIKE）
      -->
      <el-table-column label="数据范围" min-width="240" v-if="dimensions.length > 0">
        <template #default="{ row }">
          <div class="ram-scope-cell">
            <div class="ram-scope-modes" v-if="applicableDimensions(row.resource_type).length > 0 || rowScopeMode(row.resource_type) === 'configured'">
              <!-- [Phase 3.17 2026-08-25] v17：单一按钮 + 自带状态
                   - 未配置 → 虚线边框 + 灰色 + 「+ 配置条件」（提示用户添加）
                   - 已配置 → 实色边框 + 主色背景 + 「⚙ 配置条件（N 条）」+ 预览表达式
                   - 替换 v16 的 mode chip + 独立按钮的双元素设计 -->
              <button
                class="ram-scope-condition-btn"
                :class="{
                  'ram-scope-condition-btn--empty': rowScopeMode(row.resource_type) !== 'configured'
                }"
                @click.stop="openConditionDialog(row)"
                :title="(props.readonly ? '查看条件（浏览态只读）\n' : '') + rowExpressionTooltip(row.resource_type) || '点击配置数据范围条件'"
              >
                <AppIcon
                  :name="rowScopeMode(row.resource_type) === 'configured' ? 'tune' : 'plus'"
                  :size="11"
                />
                <span>
                  {{
                    rowScopeMode(row.resource_type) === 'configured'
                      ? `配置条件（${rowRuleCount(row.resource_type)} 条）`
                      : '配置条件'
                  }}
                </span>
                <span
                  v-if="rowScopeMode(row.resource_type) === 'configured'"
                  class="ram-scope-condition-preview"
                >
                  {{ rowExpressionPreview(row.resource_type) || '（无规则）' }}
                </span>
                <AppIcon
                  v-if="rowScopeMode(row.resource_type) === 'configured'"
                  :name="props.readonly ? 'eye' : 'edit'"
                  :size="11"
                />
              </button>
              <!-- [v58 2026-08-27] 快速删除：无需进弹窗逐条清理，行内一键删除该资源配置规则 -->
              <button
                v-if="rowScopeMode(row.resource_type) === 'configured' && !props.readonly"
                class="ram-scope-clear-btn"
                title="删除该资源的配置规则"
                @click.stop="clearRowCondition(row)"
              >
                <AppIcon name="trash" :size="11" />
              </button>
            </div>
            <!-- 该资源无适用维度（applies_to 为空）-->
            <span
              v-else
              class="ram-scope-no-dim"
              title="该资源类型不适用任何数据范围维度"
            >
              —
            </span>
          </div>
        </template>
      </el-table-column>

      <!-- 动作列（动态：actionFilter 选择时仅显示该列） -->
      <el-table-column
        v-for="action in visibleColumns"
        :key="action"
        :label="actionLabel(action)"
        align="center"
        width="88"
      >
        <template #header>
          <div class="ram-col-header">
            <el-checkbox
              :model-value="isColumnAllGranted(action)"
              :indeterminate="isColumnIndeterminate(action)"
              :disabled="props.readonly"
              @change="(v) => toggleColumn(action, !!v)"
            />
            <span class="ram-col-label">{{ actionLabel(action) }}</span>
          </div>
        </template>
        <template #default="{ row }">
          <!-- 灰化禁选：该资源不支持此动作（A5） -->
          <div
            v-if="!isSupported(row.resource_type, action)"
            class="ram-cell ram-cell--unsupported"
          >
            <el-tooltip content="该资源不支持此操作" placement="top" :teleported="true">
              <AppIcon name="ban" :size="14" class="ram-unsupported-icon" />
            </el-tooltip>
          </div>
          <!-- 支持：勾选 + 来源标签（4 色语义） -->
          <div
            v-else
            class="ram-cell"
            :class="['ram-cell--clickable',
              { 'ram-cell--exclude': cellOf(row, action).source === 'exclude',
                'ram-cell--readonly': props.readonly || isRowReadonly(row),
                'ram-cell--derived': cellOf(row, action).source === 'derived' && isRowReadonly(row) }]"
            @click="handleCellClick(row, action)"
          >
            <el-checkbox
              :model-value="cellOf(row, action).granted"
              :disabled="props.readonly || isRowReadonly(row)"
              @click.stop
              @change="(v) => handleCellChange(row, action, !!v)"
            />
            <!-- [v71 2026-08-28] 来源标识策略（用户确认）：
                 - 单独授予(include)：不显示任何文字标识，手动勾选结果自明
                 - 排除(exclude)：显示标识（特殊状态需醒目）
                 - 派生类(auto/derived/owner_auto)：显示标识 + 悬浮说明"从哪来" -->
            <el-tooltip
              v-if="hasOriginNote(row, action)"
              :content="cellSourceOrigin(row, action)"
              placement="top"
              :teleported="true"
              :disabled="!cellSourceOrigin(row, action)"
            >
              <span
                class="source-tag"
                :class="[`source-tag--${cellOf(row, action).source}`]"
              >
                {{ sourceLabel(cellOf(row, action).source) }}
              </span>
            </el-tooltip>
            <span
              v-else-if="showSourceTag(row, action)"
              class="source-tag"
              :class="[`source-tag--${cellOf(row, action).source}`]"
            >
              {{ sourceLabel(cellOf(row, action).source) }}
            </span>
          </div>
        </template>
      </el-table-column>

      <!-- 行批量操作 -->
      <el-table-column label="操作" width="96" align="center" fixed="right">
        <template #default="{ row }">
          <div class="ram-row-actions">
            <AppButton size="sm" variant="text" :disabled="props.readonly" @click="toggleRow(row)">
              {{ isRowAllGranted(row) ? '清空行' : '全选行' }}
            </AppButton>
            <!-- [v62 2026-08-28] 差异化动作入口：
                 该资源支持但未进主矩阵列的低频动作（支持率 < 50%），
                 在行内 popover 勾选配置；N=0 时按钮隐藏（当前数据全部 N=0，界面零变化） -->
            <el-popover
              v-if="extraActionsOf(row.resource_type).length > 0"
              placement="left-start"
              :width="260"
              trigger="click"
            >
              <template #reference>
                <AppButton size="sm" variant="text">
                  +{{ extraActionsOf(row.resource_type).length }} 动作
                </AppButton>
              </template>
              <div class="ram-more-panel">
                <div class="ram-more-title">
                  更多动作（{{ resourceLabel(row) }} 专属，主矩阵列未展示）
                </div>
                <label
                  v-for="a in extraActionsOf(row.resource_type)"
                  :key="a"
                  class="ram-more-item"
                >
                  <el-checkbox
                    :model-value="cellOf(row, a).granted"
                    :disabled="props.readonly || isRowReadonly(row)"
                    @change="(v) => handleCellChange(row, a, !!v)"
                  />
                  <span class="ram-more-label">{{ actionLabel(a) }}</span>
                  <span
                    v-if="showSourceTag(row, a)"
                    class="source-tag"
                    :class="[`source-tag--${cellOf(row, a).source}`]"
                  >
                    {{ sourceLabel(cellOf(row, a).source) }}
                  </span>
                </label>
              </div>
            </el-popover>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- [v34 2026-08-27] 三态分清：loading / 元数据未就绪 / 空数据
         旧的"加载中…"误导：实际是接口失败/未返回导致 meta=null，并非加载中。
         现在 loading=true 时由 el-table v-loading 接管；loading=false 且 matrix=null 才显示
         "元数据未就绪"提示（可能是 scopeCode 无效、网络失败、角色未保存等）。
         scopeError 由父级 AppAlert 单独显示，这里不再重复。 -->
    <div v-if="!props.matrix && !loading" class="ram-empty">
      元数据未就绪：请检查角色是否已保存、scope_code 是否有效、网络是否可达
    </div>
    <div v-else-if="rows.length === 0" class="ram-empty">
      当前角色 {{ props.matrix?.permission_set_id }} 在元数据中未找到任何资源类型（请检查 resource_types.yaml）
    </div>

    <!-- exclude 恢复 Allow 二次确认（Spec 5.3.1：danger variant 仍为橙系） -->
    <AppModal
      v-model="showExcludeConfirm"
      title="恢复 Allow 确认"
      width="520"
    >
      <p class="ram-confirm-text">
        当前为<strong>手动排除</strong>状态（该权限即使菜单勾选也不会授予），
        确认恢复为 Allow？
      </p>
      <template #footer>
        <AppButton variant="secondary" @click="showExcludeConfirm = false">
          取消
        </AppButton>
        <AppButton variant="danger" @click="confirmRestoreAllow">
          确认恢复
        </AppButton>
      </template>
    </AppModal>

    <!-- [一体化 Phase 3 2026-08-25] 范围配置抽屉
         点击资源行的「N 项」按钮或 mode chip 时打开
         内嵌一体化范围配置：每个维度（product/version/domain/sub_domain）的范围值
         [Phase 3.2 2026-08-25] mode 通过资源行的 4-mode chip 切换；抽屉专注范围值多选
         一体化表达：范围与动作授权在同一上下文，保存时联动一致性天然保证 -->
    <!-- [Phase 3.15 2026-08-25] v15：去掉抽屉（详见 §6.24）
         所有 picker 多选进入 Rule Builder → 见 ConditionRuleDialog
    -->
  </AppCard>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElSelect, ElOption, ElInput, ElTag, ElMessageBox } from 'element-plus'
import AppCard from '@/components/common/AppCard/AppCard.vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import AppModal from '@/components/common/AppModal/AppModal.vue'
import SearchHelpDialog from '@/components/common/SearchHelpDialog.vue'
import * as permService from '@/services/permissionService'
import { useMessage } from '@/composables/useMessage'
// 注：项目无 AppTag 组件，使用 el-tag 替代

/** 来源标签中文（[v68 2026-08-28] 双语义重构: 跟随菜单=自动联动 / 单独授予=独立生效） */
const SOURCE_LABELS = {
  auto: '跟随菜单',
  include: '单独授予',
  exclude: '排除',
  derived: '派生',
  owner_auto: 'Owner',  // [v42] subordinate 资源 owner 自治
}

/** [Phase 3.5e 2026-08-25] v6 行业标准对齐模型
 *   头部产品对照（基于 Web 调研）：
 *     - SAP PFCG：Org Levels 是 picker 多选，"全部"用 * 通配符表示（不单独成 mode）
 *     - AWS IAM：Condition 是与 Effect 并列的字段，有多种 operator
 *     - Salesforce：Record Access 与 Object Permission 是分层模型
 *   行业惯例核心（v5 错误 → v6 修正）：
 *     - v5 错误：5-mode chip (不限制/全部/包含/排除/条件规则)，mode 与 picker 重复入口
 *     - v6 修正：3-mode chip (不限制/包含/排除) + 2-source (picker/表达式) 平级二选一
 *     - "全部" 不单独成 mode，而是 picker 内的 * 通配符（SAP PFCG 实务惯例）
 *     - 自定义表达式与 picker 平级，二选一（无重复入口）*/
// [Phase 3.17 2026-08-25] v17：彻底删 MODE_CHIPS — 资源行不再有 chip 切换
//   按钮自身显示「未配置/已配置」状态
//   v16 之前：MODE_CHIPS 3-mode → v16 减为 2-mode → v17 全部去掉
//   头部产品对照：SAP PFCG / AWS IAM / Salesforce / Airtable 都直接在按钮上显示状态，无 mode chip
//   详见 §6.26

// [Phase 3.15 2026-08-25] v15 删掉 VALUE_SOURCE_OPTIONS（详见 §6.24）
//   v15 前：资源行有「多选 / 自定义」chip 二选一（picker 多选 vs 自定义表达式）
//   v15 后：直接点「配置条件」按钮 → 打开 Rule Builder → 多选是 Value 的属性（IN 操作符 + 多值）
//   行业共识：SAP/AWS IAM/Salesforce/Airtable 都是「字段 + 操作符 + 值」单层 Rule Builder

// [Phase 3.8b 2026-08-25] 移除 WILDCARD_ALL 常量（v7 错误地引入了）
//   v8 恢复 SearchHelpDialog 多选弹窗后，通配符由 picker 选项中的「全选」按钮处理

/** 动作中文兜底（优先 props.actionLabels） */
const DEFAULT_ACTION_LABELS = {
  create: '创建',
  read: '查看',
  list: '列表',
  update: '编辑',
  delete: '删除',
  export: '导出',
  manage: '管理',
}

const props = defineProps({
  /** [v34 2026-08-27] 元数据加载状态：true → el-table v-loading 接管，骨架占位 */
  loading: {
    type: Boolean,
    default: false,
  },
  /** [v39 2026-08-27] 只读模式：父级未进入编辑态时，所有 action checkbox 不可点击 */
  readonly: {
    type: Boolean,
    default: false,
  },
  /** role_resource_action_matrix：{ permission_set_id, columns, resources:[{resource_type,label,cells}] } */
  matrix: {
    type: Object,
    default: null,
  },
  /** resource_action_matrix：{ resource_type: [可授权动作] }（A5 灰化依据） */
  supportedActions: {
    type: Object,
    default: () => ({}),
  },
  /** { resource_type: 中文名 }（缺省回退 row.label / code） */
  resourceTypeLabels: {
    type: Object,
    default: () => ({}),
  },
  /** { action: 中文名 }（缺省回退 DEFAULT_ACTION_LABELS / code） */
  actionLabels: {
    type: Object,
    default: () => ({}),
  },
  /** 标题（默认 '资源 × 动作'；菜单视图可覆盖为 '资源 × 动作 · 菜单名'） */
  title: {
    type: String,
    default: '',
  },
  /** [v35 2026-08-27] AppCard 副标题（承载"已选菜单：xxx"或"全部资源"等上下文信息） */
  subtitle: {
    type: String,
    default: '',
  },
  /** [v35 2026-08-27] 当前选中菜单对象（用于显示"已选菜单 + 清除"chip）；null = 全部资源 */
  contextMenu: {
    type: Object,
    default: null,
  },
  /** 外部资源类型筛选（来自左侧侧边栏点击，多选），双向同步到内部 resourceFilters */
  externalResourceFilters: {
    type: Array,
    default: () => [],
  },
  /** [Phase 3] 外部筛选模式：
   *    'allowlist' (默认) - 当 externalResourceFilters 非空时，仅展示命中项（菜单视图用）
   *    'sync'        - 双向同步，内部 resourceFilters 可与外部交集 (资源分组视图用)
   */
  externalResourceFilterMode: {
    type: String,
    default: 'sync',
    validator: (v) => ['sync', 'allowlist'].includes(v),
  },
  /** [一体化 Phase 3 2026-08-25] 维度列表（来自 yaml dimension_object_mapping / meta.normalizedForDimensionSelector）
   *  例：[{ id: 'product', name: '产品' }, { id: 'version', name: '版本' }, ...]
   *  一体化表达：每个资源行可挂这些维度的范围值（替代独立 Tab2 数据权限） */
  dimensions: {
    type: Array,
    default: () => [],
  },
  /** [一体化 Phase 3 2026-08-25] 当前角色的范围矩阵
   *  结构：{ resource_type: { dimension_id: { scope_mode, dimension_values } } }
   *  例：{ product: { product: { scope_mode: 'include', dimension_values: [1,2] }, domain: { scope_mode: 'all' } } }
   *  一体化表达：scopeMatrix 与 matrix 同生命周期，联动一致性天然保证 */
  scopeMatrix: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['change', 'scope-change', 'open-condition-dialog', 'clear-context'])

// ---- 本地矩阵状态（深拷贝 props，组件内可勾选） ----
const rows = ref([])

function cloneMatrixRows() {
  const src = props.matrix?.resources || []
  const cols = props.matrix?.columns || []
  return src.map((r) => {
    // [v62 2026-08-28] cells 覆盖「主矩阵列 + 低频差异化动作」全集：
    // 低频动作不在 columns，若只按 columns 克隆，刷新后
    // 「+N 动作」popover 的勾选状态会丢失（回显 FAIL 根因）
    const keys = [...cols]
    for (const k of Object.keys(r.cells || {})) {
      if (!keys.includes(k)) keys.push(k)
    }
    return {
      resource_type: r.resource_type,
      label: r.label || '',
      cells: Object.fromEntries(
        keys.map((a) => [
          a,
          {
            granted: !!r.cells?.[a]?.granted,
            source: r.cells?.[a]?.source || '',
          },
        ]),
      ),
    }
  })
}

watch(
  () => props.matrix,
  () => {
    rows.value = cloneMatrixRows()
  },
  { immediate: true, deep: true },
)

// ---- 筛选 ----
const resourceFilters = ref([]) // string[] · 多选资源类型
const actionFilter = ref('')
const onlyAssigned = ref(false)

// 外部侧边栏点击（多选） → 同步到内部 resourceFilters
watch(
  () => props.externalResourceFilters,
  (val) => {
    resourceFilters.value = Array.isArray(val) ? [...val] : []
  },
  { immediate: true },
)

const resourceOptions = computed(() => {
  const types = Array.from(new Set(rows.value.map((r) => r.resource_type)))
  return types.map((rt) => ({ label: resourceLabel(rt), value: rt }))
})

const actionOptions = computed(() => {
  return (props.matrix?.columns || []).map((a) => ({
    label: actionLabel(a),
    value: a,
  }))
})

const visibleColumns = computed(() => {
  if (actionFilter.value) return [actionFilter.value]
  return props.matrix?.columns || []
})

const filteredRows = computed(() => {
  let list = rows.value
  if (resourceFilters.value.length > 0) {
    const set = new Set(resourceFilters.value)
    list = list.filter((r) => set.has(r.resource_type))
  }
  if (onlyAssigned.value) {
    list = list.filter((r) =>
      (props.matrix?.columns || []).some((a) => r.cells[a]?.granted),
    )
  }
  return list
})

// [v34 2026-08-27] 资源行分页（资源类型多时一屏过长，AppCard 标题右侧提供「‹/›」翻页）
const PAGE_SIZE = 10
const currentPage = ref(1)
watch(filteredRows, () => { currentPage.value = 1 }) // 筛选条件变化时回到第 1 页
const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / PAGE_SIZE)))
const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return filteredRows.value.slice(start, start + PAGE_SIZE)
})
function goPrevPage() { if (currentPage.value > 1) currentPage.value-- }
function goNextPage() { if (currentPage.value < totalPages.value) currentPage.value++ }

// ---- 标签 ----
function resourceLabel(row) {
  if (row.label) return row.label
  const rt = typeof row === 'string' ? row : row.resource_type
  return props.resourceTypeLabels[rt] || rt
}

function actionLabel(action) {
  return props.actionLabels[action] || DEFAULT_ACTION_LABELS[action] || action
}

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source
}

// ---- 单元格 ----

/** [v42 2026-08-27] 行级只读判断
 * 关系资源（relationship）权限由后端从端点 derive，前端不可手动配置。
 * 业界共识：SAP/Palantir/Salesforce Junction Object 都禁止独立 grant 关系权限。
 */
const DERIVED_ONLY_RESOURCE_TYPES = new Set(['relationship'])

function isRowReadonly(row) {
  return DERIVED_ONLY_RESOURCE_TYPES.has(row.resource_type)
}

/** 行级 tooltip 文案（解释为何只读） */
function rowReadonlyReason(row) {
  if (row.resource_type === 'relationship') {
    return '关系权限由 version/domain/sub_domain 维度范围自动派生，请在「维度范围」配置端点 scope'
  }
  return ''
}

/** [v42 2026-08-27] cell 来源明细 tooltip
 * 从 props.matrix.sources_detail 查 origin 文案，悬浮在 source-tag 上可看来源解释
 * 例: subordinate 资源 owner 自治 — annotation 的创建者自动获得该权限
 */
function cellSourceOrigin(row, action) {
  const src = cellOf(row, action).source
  if (!src) return ''
  const detail = props.matrix?.sources_detail || []
  const found = detail.find(
    (d) => d.resource_type === row.resource_type && d.action === action && d.source === src
  )
  return found?.origin || ''
}

/** [v70 2026-08-28] 说明 tooltip 仅对"被联动派生"的来源展示：
 *   auto/derived/owner_auto 的权限来自菜单勾选等关联派生，需要解释"从哪来"；
 *   include（单独授予）/ exclude（排除）是用户手动操作，结果自明，无需说明。 */
function hasOriginNote(row, action) {
  const src = cellOf(row, action).source
  return src === 'auto' || src === 'derived' || src === 'owner_auto'
}

/** [v71 2026-08-28] 文字标识策略：单独授予(include)不显示标识（手动勾选结果自明）；
 *   排除/派生类来源保留标识。 */
function showSourceTag(row, action) {
  const src = cellOf(row, action).source
  return !!src && src !== 'include'
}

function cellOf(row, action) {
  if (!row.cells[action]) {
    // 防御：matrix 列扩展后兜底
    row.cells[action] = { granted: false, source: '' }
  }
  return row.cells[action]
}

function isSupported(resourceType, action) {
  const acts = props.supportedActions[resourceType]
  return Array.isArray(acts) && acts.includes(action)
}

// [v62 2026-08-28] 差异化动作（行内「更多」）：
//   该资源支持但未进主矩阵列的动作（后端 _matrix_action_columns 已按支持率 >=50% 过滤主列）。
//   rowActions = 主矩阵列 ∪ 该行专属动作 — 供 emitChange / 行全选等口径使用，
//   保证「更多」动作与主列动作在保存链路、批量操作中完全同权。
function extraActionsOf(resourceType) {
  const acts = props.supportedActions[resourceType] || []
  const cols = props.matrix?.columns || []
  return acts.filter((a) => !cols.includes(a))
}

function rowActions(row) {
  const cols = props.matrix?.columns || []
  return [...cols, ...extraActionsOf(row.resource_type)]
}

function emitChange() {
  const changes = []
  for (const row of rows.value) {
    for (const action of rowActions(row)) {
      if (!isSupported(row.resource_type, action)) continue
      const cell = row.cells[action]
      if (!cell) continue
      changes.push({
        resource_type: row.resource_type,
        action,
        granted: cell.granted,
        source: cell.source,
      })
    }
  }
  emit('change', changes)
}

function applyCell(row, action, granted, source) {
  const cell = row.cells[action]
  if (!cell) return
  cell.granted = granted
  cell.source = source
}

// ---- 交互 ----
const pendingExclude = ref(null) // { row, action }
const showExcludeConfirm = ref(false)

function handleCellClick(row, action) {
  const cell = cellOf(row, action)
  if (cell.source === 'exclude') {
    // exclude 恢复 Allow 需二次确认（Spec 5.3.1）
    pendingExclude.value = { row, action }
    showExcludeConfirm.value = true
  }
}

function handleCellChange(row, action, value) {
  const cell = cellOf(row, action)
  // [v42 2026-08-27] 关系资源（relationship）不可手动配置：权限跟随端点 derive
  // 业界共识（SAP/Palantir/Salesforce Junction Object）：关联资源权限不可独立 grant。
  // 后端 _build_role_matrices 已实现 association derive，前端只读展示。
  // 此处阻断：即使前端绕过 readonly，也拒绝写入 matrixChanges。
  if (row.resource_type === 'relationship') {
    // 回滚 UI 变化（恢复 cell 原值）
    applyCell(row, action, cell.granted, cell.source)
    return
  }
  // 勾选 → include（手动）；取消 → 无来源
  applyCell(row, action, value, value ? 'include' : '')
  emitChange()
}

function confirmRestoreAllow() {
  if (!pendingExclude.value) return
  const { row, action } = pendingExclude.value
  applyCell(row, action, true, 'include')
  emitChange()
  pendingExclude.value = null
  showExcludeConfirm.value = false
}

/** 批量：当前筛选内所有「支持且非 exclude」的 cell 勾选 */
function selectAllFiltered() {
  // [v44 2026-08-27] 浏览态防御性 guard（即使 disabled 被绕过也不修改数据）
  if (props.readonly) return
  for (const row of filteredRows.value) {
    for (const action of rowActions(row)) {
      if (!isSupported(row.resource_type, action)) continue
      if (cellOf(row, action).source === 'exclude') continue
      applyCell(row, action, true, 'include')
    }
  }
  emitChange()
}

function clearFiltered() {
  if (props.readonly) return
  for (const row of filteredRows.value) {
    for (const action of rowActions(row)) {
      applyCell(row, action, false, '')
    }
  }
  emitChange()
}

function isRowAllGranted(row) {
  const supported = rowActions(row).filter((a) =>
    isSupported(row.resource_type, a),
  )
  if (supported.length === 0) return false
  return supported.every((a) => cellOf(row, a).granted)
}

function toggleRow(row) {
  if (props.readonly) return
  const willGrant = !isRowAllGranted(row)
  for (const action of rowActions(row)) {
    if (!isSupported(row.resource_type, action)) continue
    if (cellOf(row, action).source === 'exclude') continue
    applyCell(row, action, willGrant, willGrant ? 'include' : '')
  }
  emitChange()
}

function isColumnAllGranted(action) {
  const supported = rows.value.filter((r) => isSupported(r.resource_type, action))
  if (supported.length === 0) return false
  return supported.every((r) => cellOf(r, action).granted)
}

function isColumnIndeterminate(action) {
  const supported = rows.value.filter((r) => isSupported(r.resource_type, action))
  if (supported.length === 0) return false
  const granted = supported.filter((r) => cellOf(r, action).granted)
  return granted.length > 0 && granted.length < supported.length
}

function toggleColumn(action, value) {
  if (props.readonly) return
  for (const row of rows.value) {
    if (!isSupported(row.resource_type, action)) continue
    if (cellOf(row, action).source === 'exclude') continue
    applyCell(row, action, value, value ? 'include' : '')
  }
  emitChange()
}

defineExpose({
  /** 获取当前完整矩阵状态（父组件保存时使用） */
  getRows: () => rows.value,
  /** [一体化 Phase 3 2026-08-25] 获取当前范围矩阵状态 */
  getScopeMatrix: () => scopeMatrixLocal.value,
})

// ============================================================================
// [一体化 Phase 3 2026-08-25] 范围配置（内嵌 Tab1 资源行，不再走独立 Tab2）
//   头部产品对照：
//     - AWS IAM Statement: Resource + Condition 在一条原子表达内
//     - SAP PFCG Authorization Object: ACTVT + Org Levels 在同一对象
//   一体化表达：范围 scopeMatrix 与功能 matrix 同组件、同生命周期、同 change 事件
//   联动一致性天然保证（不存在「Tab1 配了 Tab2 没配」的不一致状态）
// ============================================================================

/** 本地范围矩阵（深拷贝 props）
 *  结构：{ resource_type: { dim_id: { scope_mode, dimension_values: [{id, name, code}, ...] } } }
 *  与后端存储兼容：保存时 dimension_values 只取 id 字段 */
const scopeMatrixLocal = ref({})
watch(
  () => props.scopeMatrix,
  (val) => {
    scopeMatrixLocal.value = JSON.parse(JSON.stringify(val || {}))
  },
  { immediate: true, deep: true },
)

// ============================================================================
// [P1 2026-08-25] yaml applies_to 静态 fallback (后端 meta API 暂不下发 dimension_object_mappings)
//   来源：meta/schemas/dimension_object_mapping.yaml 的 applies_to 字段
//   完整关系见 Spec 15 §6.12 — 每个资源可挂的维度字段由 yaml 声明
//   简化策略：
//     - product    → product
//     - version    → product + version
//     - domain     → product + version + domain
//     - sub_domain → product + version + domain + sub_domain
//     - service_module → domain + sub_domain
//     - business_object → domain + sub_domain
//     - relationship/annotation/audit_log → 无维度（不展示范围列）
//     - menu/enum_*/filter_variant/ai_async_task → 无维度
//   未来：后端 meta API 下发 dimension_object_mappings.applies_to 后，此函数可删除。
// ============================================================================
const APPLIES_TO_FALLBACK = {
  product:          ['product'],
  version:          ['product', 'version'],
  domain:           ['product', 'version', 'domain'],
  sub_domain:       ['product', 'version', 'domain', 'sub_domain'],
  service_module:   ['domain', 'sub_domain'],
  business_object:  ['domain', 'sub_domain'],
  relationship:     [],
  annotation:       [],
  audit_log:        [],
}

/** 该资源适用的维度（按 yaml applies_to 过滤），若无适用维度返回空数组（隐藏范围列）*/
function applicableDimensions(resourceType) {
  const allowed = APPLIES_TO_FALLBACK[resourceType]
  // 未声明的资源（如 menu/enum_*）默认展示全部维度（向后兼容）
  if (allowed === undefined) return props.dimensions || []
  return (props.dimensions || []).filter(d => allowed.includes(d.id))
}

// [Phase 3.2 2026-08-25] hasAnyScope / hasScopeConfigured / scopeChipType / scopeChipLabel 已废弃
//   原作用：资源行展示「产品: 3 项」「领域: 全部」摘要 chip
//   现状：4-mode chip 直接显示 mode + 「N 项」预览按钮，旧的摘要 chip 不再需要
//   替代：rowScopeMode + rowScopeValueCount 实现行级 mode + 范围值预览

// ============================================================================
// [Phase 3.2 2026-08-25] 4-mode 快选 chip 辅助函数（资源行内嵌）
//   一体化表达：mode 切换 + 范围值在同一行；mode 只切 mode 不动 values
//   多维度场景：mode 对该资源所有适用维度统一生效（如 "包含" = 所有维度都进入 include）
//   范围值：各维度各自的 dimension_values，跨维度并集显示
// ============================================================================

/** 该资源当前的 scope_mode (聚合所有适用维度的 mode，取最严格)
 *   [Phase 3.5e 2026-08-25] v6 修正：
 *     - 移除 condition mode（与 picker 平级，用 value_source 区分）
 *     - 移除 all mode（"全部" 由 picker 内的 * 通配符表达）
 *   v6 优先级：exclude > include > '' (不限制) */
/** [Phase 3.17 2026-08-25] v17 严格化：返回该资源是否真正「配置了 Rule Builder 规则」
 *  v15 前：返回 'include' / 'exclude' / ''（三态）
 *  v16 后：返回 'configured' / ''（二态）
 *  v17 后：仅当真正有 __expression（Rule Builder 输出）时才算已配置
 *    - 后端 dimension_scopes 数据（scope_mode + dimension_values）不算已配置
 *      因为这些是旧的「包含/排除」语义，已被 Rule Builder 操作符替代
 *    - v17 起「新」路径只有 Rule Builder，dimConfigs 仅作为历史数据兼容读取
 */
function rowScopeMode(resourceType) {
  const data = scopeMatrixLocal.value?.[resourceType]
  if (!data) return ''
  // 优先看 v16 起写入的 __expression
  if (data.__expression && data.__expression.trim()) return 'configured'
  return ''
}

// [Phase 3.15 2026-08-25] v15 删掉 rowValueSource / toggleRowValueSource
//   不再有 picker/expression chip 切换（详见 §6.24）

/** [Phase 3.5e + 3.15 + 3.17 2026-08-25] 表达式预览（截断到 20 字符）
 *   v15 后：预览的是 Rule Builder 生成的完整条件表达式（如 "product_id IN (1,2,3) AND domain = 'CORE'"）
 *   v17 后：返回值用于按钮内的预览文本，未配置时返回空
 *   [v45 2026-08-27] 优先用 __expression_display（字段中文 label + picker 显示名，
 *   如「业务对象 IN (供应链计划BO, 库存管理BO)」），无则回落原始表达式 */
function rowExpressionPreview(resourceType) {
  const data = scopeMatrixLocal.value?.[resourceType] || {}
  const expr = data.__expression_display || data.__expression || ''
  return expr.length > 28 ? expr.slice(0, 26) + '...' : expr
}

/** [v56 2026-08-27] 按钮 tooltip：完整人类可读描述 + 技术表达式（次级信息）
 *  头部产品惯例（Salesforce/Fiori 筛选器）：主文案业务可读，原始表达式放 tooltip */
function rowExpressionTooltip(resourceType) {
  const data = scopeMatrixLocal.value?.[resourceType] || {}
  const display = data.__expression_display || ''
  const technical = data.__expression || ''
  if (!display && !technical) return ''
  if (display && technical && display !== technical) {
    return `${display}\n技术表达式: ${technical}`
  }
  return display || technical
}

/** [Phase 3.17 2026-08-25] v17：该资源的规则数
 *   通过逗号/AND/OR 等分隔符大致估算（精确数需等 Rule Builder 输出后端持久化）
 *   简化估算：按 `AND`/`OR` 拆分行数 + 1（最小 1）*/
function rowRuleCount(resourceType) {
  const expr = scopeMatrixLocal.value?.[resourceType]?.__expression || ''
  if (!expr) return 0
  // 简化：按 AND/OR 拆分（不区分大小写）
  const parts = expr.split(/\s+AND\s+|\s+OR\s+/i).filter(Boolean)
  return Math.max(parts.length, 1)
}

// [Phase 3.17 2026-08-25] v17 删掉 toggleRowScopeMode（不再有 mode chip 切换）
//   v15/v16 之前：toggleRowScopeMode 接收 mode='include'/'exclude'/''/configured
//   v17 后：mode 状态完全由 __configured 标记决定，按钮自身显示状态，点击按钮直接打开 dialog

// ============================================================================
// [Phase 3.15 2026-08-25] v15 删掉大量过期代码（详见 §6.24）：
//   - rowScopeValueCount: 范围值总数（v15 后范围值在 Rule Builder 里表达，不再行内计数）
//   - rowScopeModeLabel: 抽屉 hint 文本（v15 后没有抽屉）
//   - drawerModeTagType: 抽屉内 tag 颜色（v15 后没有抽屉）
// ============================================================================

// [Phase 3.17 2026-08-25] v17 删掉 toggleRowScopeMode + clearResourceScope
//   之前 4 个 mode chip（不限制/包含/排除/已配置）都需要这两个函数
//   v17 后：唯一按钮直接调 openConditionDialog，状态由 scopeMatrixLocal 自动维护
//   重置场景：用户进入 Rule Builder 后点「取消」即可不生效；如需清空，走后端 API

// ============================================================================
// [Phase 3.15 2026-08-25] v15：打开 Rule Builder 弹窗（详见 §6.24）
//   v15 前：openConditionDialog 还需要切 value_source='expression'
//   v15 后：直接打开 dialog（mode 默认为 'custom'，不再有 picker 模式）
// ============================================================================
function openConditionDialog(row) {
  if (!row) return
  // [v45 2026-08-27] 浏览态不再阻断：允许点击查看条件（父组件以只读模式打开弹窗）
  emit('open-condition-dialog', {
    resourceType: row.resource_type,
    rowLabel: row.resource_label || row.label || row.resource_type,
    mode: 'custom',  // v15 dialog 只有 custom mode（Rule Builder）
    readonly: props.readonly,  // [v45] 父组件据此切换弹窗只读模式
  })
}

// [Phase 3.15 2026-08-25] v15 删掉大量过期代码：
//   - showScopeDrawer / scopeDrawerRow / scopeDrawerTitle
//   - openScopeDrawer / closeScopeDrawer
//   - scopeDrawerItems / removeScopeItem / scopeDrawerValue / scopeDrawerMode
//   - pickerVisible / pickerDim / pickerValueHelpConfig / pickerSelectedIds / pickerFetcher
//   - handlePickerConfirm / openScopePicker / ensureScopeEntry
//   - resetScopeForResource
// 所有 picker 多选行为 → Rule Builder 内的 FK 字段自动触发 picker
// 所有抽屉行为 → Rule Builder 本身就是 dialog，不需要额外抽屉
// 所有 dim/dimension_values 数据结构 → Rule Builder 直接生成 expression 字符串

// [Phase 3.15] v15 保留 emitScopeChange — toggleRowScopeMode 还需要它
//   用于通知父组件 mode chip 切换后的范围矩阵变化
//   v15 后不再传 dim/dimension_values（v15 数据结构简化），但 mode 切换仍需通知
function emitScopeChange() {
  emit('scope-change', JSON.parse(JSON.stringify(scopeMatrixLocal.value)))
}

/** [v58 2026-08-27] 行内快速删除资源配置规则
 *  - 后端：按 _rule_id 调 DELETE（无 _rule_id 仅清本地状态）
 *  - 本地：清空 __configured / __expression / __expression_display / __rules
 *  - 通知父组件 scope-change（保存时不再带上该资源的条件）
 *  - [v59] 确认弹窗改用标准组件 ElMessageBox（此前 useMessage.confirm 落到 window.confirm，
 *    不符合 UIGuideline）；图标 delete→trash（AppIcon 无 delete 字形，此前渲染成圆圈） */
const { success: showSuccess } = useMessage()
async function clearRowCondition(row) {
  const rt = row.resource_type
  const data = scopeMatrixLocal.value[rt]
  if (!data) return
  const label = props.resourceTypeLabels[rt] || row.label || rt
  try {
    await ElMessageBox.confirm(
      `确定删除「${label}」的配置规则吗？`,
      '删除确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return // 用户取消
  }
  const ruleId = data._rule_id
  if (ruleId) {
    try {
      await permService.deleteConditionRule(ruleId)
    } catch (e) {
      console.warn('[ResourceActionMatrix] clearRowCondition: 后端删除失败（仍清理本地状态）:', e)
    }
  }
  data._rule_id = null
  data.__configured = false
  data.__expression = ''
  data.__expression_display = ''
  data.__rules = []
  emitScopeChange()
  showSuccess(`已删除「${label}」的配置规则`)
}
</script>

<style scoped>
/* ========================================================================== */
/* [FIX] 筛选栏 · 强制并排一行（避免 select 占满整行把表格推下去）           */
/* AppSelect 根元素是 <el-select>，内部 :deep(.el-select){width:100%} 强制满  */
/* 用 display:inline-flex + 显式 width 让 flex 父容器可约束                  */
/* ========================================================================== */
.ram-filter-bar {
  display: flex;
  align-items: center;
  /* [v38 2026-08-27] 上下空白从 16 (md) → 8 (sm)，水平从 16 → 12，更紧凑 */
  padding: var(--spacing-sm) var(--spacing-md);
  gap: var(--spacing-sm);
  flex-wrap: nowrap;
}

/* 直接用原生 <el-select>，不受 AppSelect 内部 width:100% 影响 */
.ram-filter-bar > .el-select {
  flex-shrink: 0;
  width: 220px;
}
.ram-filter-bar > .el-select.ram-filter-action {
  width: 180px;
}

/* el-checkbox 标签不换行 */
.ram-only-assigned {
  margin-left: var(--spacing-sm);
  white-space: nowrap;
  flex-shrink: 0;
}

/* [v71 2026-08-28] 对齐 UI 规范: EP 默认 14px 与筛选栏 12/13px 混排突兀, 统一 sm+secondary
   注意: :deep 必须用顶层非嵌套写法, sass 嵌套内 :deep 编译不可靠 */
.ram-only-assigned :deep(.el-checkbox__label) {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.ram-spacer {
  flex: 1 1 auto;
}

.ram-filter-bar > .el-button {
  flex-shrink: 0;
}

/* [v34 2026-08-27] AppCard 标题右侧分页控件 */
.ram-pager {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.ram-pager-info {
  margin-right: 4px;
}
:deep(.app-card__extra) .ram-pager > .el-button {
  padding: 0 6px;
  min-height: 24px;
  font-size: 14px;
  line-height: 1;
}

/* [v37 2026-08-27] AppCard extra slot 容器：chip 与分页器同行 */
.ram-extra {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

/* [v37 2026-08-27] "已选菜单 + 清除" chip：从块级搬到 AppCard 右上角（与分页器同行） */
.ram-context-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px 3px 6px;
  background: var(--color-bg-spotlight, #f5f7fa);
  border: 1px solid var(--color-brand-2, #ffd6b3);
  border-radius: var(--radius-md, 6px);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary, #666);
  white-space: nowrap;
}
.ram-context-chip strong {
  color: var(--color-text-primary);
  font-weight: 600;
}
.ram-context-clear {
  margin-left: 4px;
  padding: 0 6px;
  border: none;
  background: transparent;
  color: var(--color-brand);
  font-size: var(--font-size-xs);
  cursor: pointer;
}
.ram-context-clear:hover {
  text-decoration: underline;
}

.ram-table {
  width: 100%;
  min-height: 200px;
}

.ram-resource-label {
  font-weight: 500;
  color: var(--color-text-primary);
}

/* [v42 2026-08-27] 派生只读行视觉（关系资源）：灰色 + lock icon 提示 */
.ram-resource-label--readonly {
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.ram-row-lock {
  color: var(--color-text-tertiary, #999);
}

/* [v62 2026-08-28] 行内「更多动作」popover — 差异化动作勾选配置
     - 交互语义与主矩阵 cell 完全一致（checkbox + 来源标签）
     - 样式遵循 uiguideline 令牌：字号 >= --font-size-xs，颜色用规范色阶 */
.ram-row-actions {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}
.ram-more-title {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-xs, 8px);
}
.ram-more-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 8px);
  padding: 4px 0;
  cursor: pointer;
}
.ram-more-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

/* [v42 2026-08-27] 派生 cell 视觉：chip 旁加蓝色边框提示这是 derive 而非手动 */
.ram-cell--derived {
  background-color: rgba(64, 158, 255, 0.04);
}

.ram-col-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.ram-col-label {
  font-size: var(--font-size-sm);
}

.ram-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 28px;
}

.ram-cell--clickable {
  cursor: pointer;
}

.ram-cell--exclude {
  opacity: 0.85;
}

.ram-cell--unsupported {
  color: var(--color-text-disabled, var(--color-text-secondary));
}

.ram-unsupported-icon {
  display: block;
}

.ram-empty {
  padding: var(--spacing-lg);
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.ram-confirm-text {
  margin: 0;
  line-height: 1.7;
  color: var(--color-text-primary);
}

/* [v68 2026-08-28] 来源标签黑白灰简洁配色: 去彩色语义, 用字重/透明度区分 */
.source-tag {
  display: inline-block;
  padding: 0 6px;
  height: 18px;
  line-height: 18px;
  border-radius: 4px;
  font-size: 11px;
  white-space: nowrap;
}

.source-tag--auto {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}

.source-tag--include {
  background: var(--color-bg-tertiary, #f0f0f0);
  color: var(--color-text-primary, #262626);
}

.source-tag--exclude {
  background: var(--color-bg-tertiary, #f0f0f0);
  color: var(--color-text-quaternary, #bfbfbf);
  text-decoration: line-through;
  text-decoration-color: var(--color-text-quaternary, #bfbfbf);
}

.source-tag--derived {
  background: var(--color-bg-secondary);
  color: var(--color-text-tertiary);
}

/* [v42 2026-08-27] owner_auto 标签：subordinate 资源 owner 自治（运行时拦截器实施） */
.source-tag--owner_auto {
  background: var(--color-bg-secondary);
  color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border);
}

/* ========================================================================== */
/* [一体化 Phase 3 2026-08-25] 范围列 + 范围抽屉样式                          */
/*   一体化表达：范围跟随资源行（AWS IAM Statement.Resource 内嵌表达）         */
/* ========================================================================== */
.ram-scope-cell {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.ram-scope-chip {
  cursor: pointer;
  transition: opacity 0.15s;
  &:hover {
    opacity: 0.85;
  }
}

/* ========================================================================== */
/* [Phase 3.2 2026-08-25] 4-mode 快选 chip + 范围值预览按钮                    */
/*   一体化表达：mode 切换 + 范围值在同一行内；UX 对照 SAP PFCG 快速切换      */
/* ========================================================================== */
.ram-scope-modes {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
}
/* [v58 2026-08-27] 行内快速删除按钮：低调 ghost，hover 变危险红 */
.ram-scope-clear-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid var(--color-border, #dcdfe6);
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary, #909399);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}
.ram-scope-clear-btn:hover {
  border-color: var(--color-danger, #f56c6c);
  color: var(--color-danger, #f56c6c);
  background: var(--color-danger-bg, #fef0f0);
}
/* ==========================================================================
 * [Phase 3.9 2026-08-25] v9 终极修正：chip CSS 完全重写以严格遵守项目 YonDesign 规范
 *   头部规范：.trae/rules/core/ui-standards.md + src/styles/YON_DESIGN_CONSTANTS.md
 *   关键规范：
 *     1. 主色必须用 var(--yonyou-orange-600, #ea580c) — YonDesign 橙色系
 *     2. 禁止硬编码颜色（#1890ff 蓝色禁止！#722ed1 紫色禁止！）
 *     3. 激活态规范：背景 var(--color-primary-bg) + 边框 var(--color-primary) + 文字 var(--color-primary)
 *     4. 按钮状态：默认/Hover/Focus/Active 渐进式反馈（背景透明度 0/6%/12%/16%）
 *     5. 圆角：chip 4px（标签圆角 --radius-sm）
 *     6. 状态色彩语义：激活=主色，错误=Orange 700，成功=Green
 *   v8 错误：用 #1890ff 蓝色（违反 YonDesign 规范）+ 实色填充背景（违反按钮状态规范）
 *   v9 修正：用 var(--yonyou-orange-600) + 浅橙背景（--color-primary-bg）
 * ========================================================================== */
/* [Phase 3.10b 2026-08-25] v10 终极修复：展开 SCSS 嵌套为标准 CSS
 *   根因：<style scoped> 不支持 SCSS 嵌套语法，&--active 整段被浏览器丢弃
 *   修复：把 &:hover / &--active / .ram-chip-check 全部展开为完整选择器
 *   教训：v5-v9 五次都没真正验证过浏览器实际 CSS，单纯凭印象写代码 */

/* ==========================================================================
 * [Phase 3.17 2026-08-25] v17：彻底删 mode chip CSS（详见 §6.26）
 *   v15 之前：5-mode chip（不限制/全部/包含/排除/条件规则）
 *   v15：减为 3-mode（不限制/包含/排除）
 *   v16：减为 2-mode（未配置/已配置）
 *   v17：去掉所有 chip，只剩唯一按钮
 * ========================================================================== */

/* [Phase 3.17] v17：唯一按钮 — 自带「未配置/已配置」状态
 *   状态由 rowScopeMode() 返回值决定（'/configured'）：
 *     - 未配置（--empty）：dashed border + 灰色文字 + 加号 icon + 「配置条件」
 *     - 已配置：solid 主色边框 + 浅主色背景 + 主色文字 + tune icon + 「配置条件（N 条）」+ 预览
 *   头部产品对照：AWS IAM Console 的条件编辑器按钮 / Airtable Filter 入口按钮
 */
.ram-scope-condition-btn {
  display: inline-flex !important;
  align-items: center !important;
  gap: 6px !important;
  padding: 4px 10px !important;
  font-size: 11px !important;
  line-height: 1.5 !important;
  border-radius: var(--radius-sm, 4px) !important;
  cursor: pointer !important;
  background: var(--color-primary-bg, #fff7ed) !important;
  border: 1px solid var(--color-primary, #ea580c) !important;
  color: var(--color-primary, #ea580c) !important;
  font-weight: 500 !important;
  transition: all 0.15s ease !important;
  white-space: nowrap !important;
  user-select: none !important;
}
.ram-scope-condition-btn:hover {
  background: rgba(234, 88, 12, 0.16) !important;
  border-color: var(--color-primary, #ea580c) !important;
}
/* [v44 2026-08-27] 浏览态：disabled 视觉降级 */
.ram-scope-condition-btn:disabled {
  cursor: not-allowed !important;
  opacity: 0.5 !important;
}
.ram-scope-condition-btn:disabled:hover {
  /* 覆盖 hover 态，不变颜色 */
  background: var(--color-primary-bg, #fff7ed) !important;
  border-color: var(--color-primary, #ea580c) !important;
}
.ram-scope-condition-btn--empty:disabled:hover {
  background: var(--color-bg-container) !important;
  border-color: var(--color-border-secondary, #d9d9d9) !important;
  border-style: dashed !important;
  color: var(--color-text-tertiary, #999) !important;
}
.ram-scope-condition-btn > svg {
  flex-shrink: 0 !important;
}
/* 未配置态 */
.ram-scope-condition-btn--empty {
  background: var(--color-bg-container) !important;
  border-style: dashed !important;
  border-color: var(--color-border-secondary, #d9d9d9) !important;
  color: var(--color-text-tertiary, #999) !important;
  font-weight: 400 !important;
}
.ram-scope-condition-btn--empty:hover {
  background: var(--color-bg-container) !important;
  border-color: var(--color-primary, #ea580c) !important;
  color: var(--color-primary, #ea580c) !important;
  border-style: solid !important;
}
/* 已配置态的预览文本 */
.ram-scope-condition-preview {
  font-size: 10px !important;
  font-weight: 400 !important;
  color: var(--color-text-secondary, #666) !important;
  margin-left: 4px !important;
  padding-left: 6px !important;
  border-left: 1px solid var(--color-primary-border, rgba(234, 88, 12, 0.3)) !important;
  max-width: 200px !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}

/* ==========================================================================
 * [Phase 3.9 2026-08-25] 移除 v8 错误的 4 色 chip（gray/blue/orange/purple）
 *   ui-design-standards.md 第 213-217 行明确禁止：
 *     "用 4 种不同颜色区分不同的分组" — 反模式
 *   v9 改为单一主色（激活=主色），用形状/文字/位置区分状态
 * ========================================================================== */

/* [Phase 3.15 2026-08-25] v15 删掉过期 CSS：
 *   - .ram-scope-source-toggle / .ram-scope-source-chip / .ram-scope-source-chip:hover / .ram-scope-source-chip--active
 *     → value_source chip 已去除
 *   - .ram-scope-values-btn / .ram-scope-values-btn:hover
 *     → picker 入口按钮已去除
 *   - .ram-scope-drawer / .ram-scope-drawer-hint / .ram-scope-empty / .ram-scope-table / .ram-scope-code / .ram-scope-actions
 *   - .ram-scope-mode-readonly / .ram-scope-mode-hint
 *   - .ram-scope-picker / .ram-scope-picker-empty / .ram-scope-picker-hint / .ram-scope-picker-tags / .ram-scope-picker-tag / .ram-scope-picker-code
 *     → 抽屉已去除，所有 picker 行为进入 Rule Builder
 *   保留：
 *     - .ram-scope-expression-btn（唯一按钮入口）
 *     - .ram-scope-no-dim（无适用维度时显示 —）
 *     - .ram-scope-config / .ram-scope-add / .ram-scope-edit（紧凑配置 chip）
 *     - .ram-scope-mode-chip / .ram-scope-mode-chip--active（mode chip 选中态）
 */

/* [Phase 3.9 + 3.15 2026-08-25] 「配置条件」按钮 — 唯一入口
   v15 前有 picker/expression 双按钮 + 上方 chip 二选一
   v15 后统一为单按钮 → 打开 Rule Builder */
.ram-scope-expression-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 11px;
  line-height: 1.5;
  border-radius: var(--radius-sm, 4px);
  background: var(--color-primary-bg, #fff7ed);
  border: 1px solid var(--color-primary, #ea580c);
  color: var(--color-primary, #ea580c);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}
.ram-scope-expression-btn:hover {
  background: rgba(234, 88, 12, 0.12);
  border-color: var(--color-primary, #ea580c);
}
.ram-scope-expression-btn > svg {
  flex-shrink: 0;
}

/* 该资源无适用维度（applies_to 为空）显示 "—" */
.ram-scope-no-dim {
  color: var(--color-text-tertiary, #999);
  font-size: var(--font-size-sm, 13px);
}
</style>
