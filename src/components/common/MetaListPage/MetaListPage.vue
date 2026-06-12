<template>
  <div class="meta-list-page" :class="{ 'meta-list-page--compact': displayMode !== 'page' }">
    <NavigationSourceInfo
      v-if="isNavTarget && navSourceInfo"
      :source-type="navSourceInfo.sourceType"
      :source-ids="navSourceInfo.sourceIds"
      :source-names="navSourceInfo.sourceNames"
      :association-name="navSourceInfo.associationName"
      :association-label="navSourceInfo.associationLabel"
      @navigate-back="onNavigateBack"
    />
    <slot name="toolbar">
      <div v-if="!hideToolbar" class="toolbar">
        <div class="toolbar-left">
          <div v-if="searchFields.length > 0 && !hideToolbar" class="search-field">
            <el-input
              v-model="keyword"
              :placeholder="`搜索 ${searchFields.map(f => f.label).join('/')}...`"
              clearable
              size="default"
              prefix-icon="Search"
              style="width: 280px"
              @keyup.enter="onKeywordSearch"
            />
          </div>
          <el-button
            v-if="!hideToolbar"
            v-for="action in getFilteredToolbarActions(primaryToolbarActions)"
            :key="action.key"
            :type="action.variant || 'primary'"
            size="small"
            @click="onToolbarAction(action)"
          >
            {{ action.label }}
          </el-button>

          <template v-if="isPageMode && !hideToolbar">
            <el-button v-if="searchFields.length > 0" size="small" @click="onKeywordSearch">搜索</el-button>
            <el-button v-if="searchFields.length > 0" size="small" @click="onResetFilters">重置</el-button>

            <el-dropdown
              v-if="getFilteredToolbarActions(secondaryToolbarActions).length > 0"
              trigger="click"
              @command="onToolbarAction"
            >
              <el-button type="default" size="small">
                更多
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="action in getFilteredToolbarActions(secondaryToolbarActions)"
                    :key="action.key"
                    :command="action"
                  >
                    {{ action.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>

          <template v-if="batchActions.length > 0 && totalSelectedCount > 0 && !hideToolbar">
            <el-divider direction="vertical" />
            <div class="selection-info-wrapper">
              <span class="selection-info">
                已选择 {{ totalSelectedCount }} 项
              </span>
              <el-button
                type="text"
                size="small"
                class="clear-selection-btn"
                @click="clearAllSelection"
              >
                清除选择
              </el-button>
            </div>
            <el-button
              v-for="action in batchActions"
              :key="action.key"
              :type="action.variant || 'default'"
              size="small"
              @click="onBatchAction(action)"
            >
              {{ action.label }}
            </el-button>
          </template>

          <AssociationNavigationMenu
            v-if="isPageMode && navigableAssociations.length > 0 && !hideToolbar && !hideAssociationNavigation"
            :associations="navigableAssociations"
            :selected-ids="selectedIds"
            :loading="loading"
            @navigate="onAssociationNavigate"
          />
        </div>
        <div v-if="isPageMode && !hideToolbar" class="toolbar-right">
          <!-- Inline Edit 模式切换按钮 -->
          <el-button
            v-if="inlineEditConfig?.enabled && !inlineEditMode && !isExternallyControlled"
            type="default"
            size="small"
            @click="enableInlineEdit(true)"
          >
            <el-icon><Edit /></el-icon>
            编辑
          </el-button>
          <el-button
            v-if="inlineEditConfig?.enabled && inlineEditMode && !isExternallyControlled"
            type="primary"
            size="small"
            @click="disableInlineEdit"
          >
            完成编辑
          </el-button>
          <el-button
            v-if="hiddenFilterFields.length > 0"
            type="default"
            size="small"
            :plain="!advancedFilterVisible"
            @click="advancedFilterVisible = !advancedFilterVisible"
          >
            {{ advancedFilterVisible ? '收起筛选' : '更多筛选' }}
            <el-icon class="filter-toggle-icon" :class="{ rotated: advancedFilterVisible }">
              <ArrowDown />
            </el-icon>
          </el-button>
        </div>
      </div>

      <transition name="slide-expand">
        <div v-if="advancedFilterVisible && hiddenFilterFields.length > 0 && !hideToolbar" class="advanced-filter-panel">
          <el-form :model="filterValues" label-width="auto" size="small" inline>
            <el-form-item
              v-for="field in hiddenFilterFields"
              :key="field.key"
              :label="field.label"
            >
              <el-select
                v-if="field.type === 'select'"
                v-model="filterValues[field.key]"
                :placeholder="field.placeholder || `请选择${field.label}`"
                clearable
                :multiple="field.multiple"
                style="width: 180px"
                @change="handleFilterChange(field.key, $event)"
              >
                <el-option
                  v-for="opt in field.options || []"
                  :key="opt.value ?? opt"
                  :label="opt.label ?? opt"
                  :value="opt.value ?? opt"
                />
              </el-select>
              <el-date-picker
                v-else-if="isDateRangeType(field.type)"
                v-model="filterValues[field.key]"
                :type="field.type === 'datetime-range' || field.type === 'datetimerange' ? 'datetimerange' : 'daterange'"
                range-separator="-"
                start-placeholder="开始"
                end-placeholder="结束"
                style="width: 260px"
                :value-format="field.format || (field.type === 'datetime-range' || field.type === 'datetimerange' ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD')"
                @change="handleFilterChange(field.key, $event)"
              />
              <div v-else-if="isNumberRangeType(field.type)" class="number-range-filter" style="width: 260px; display: flex; align-items: center; gap: 4px;">
                <el-input-number
                  v-model="filterValues[field.key + '_min']"
                  :placeholder="'最小'"
                  controls-position="right"
                  size="small"
                  style="width: 110px"
                />
                <span style="color: #909399; font-size: 12px;">至</span>
                <el-input-number
                  v-model="filterValues[field.key + '_max']"
                  :placeholder="'最大'"
                  controls-position="right"
                  size="small"
                  style="width: 110px"
                />
              </div>
              <el-input
                v-else
                v-model="filterValues[field.key]"
                :placeholder="field.placeholder || `请输入${field.label}`"
                clearable
                style="width: 180px"
                @keyup.enter="handleFilterChange(field.key, $event)"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" size="small" @click="onKeywordSearch">查询</el-button>
              <el-button size="small" @click="resetAdvancedFilters">清空</el-button>
            </el-form-item>
          </el-form>
        </div>
      </transition>
    </slot>

    <slot name="table">
      <div class="table-section">
        <div class="table-wrapper">
          <el-table
            ref="tableRef"
            :key="tableKey"
            v-loading="loading"
            :data="data"
            :default-sort="defaultSort"
            :sort="sortInfo"
            border
            class="custom-table"
            table-layout="fixed"
            :height="tableHeight"
            :max-height="tableMaxHeight"
            @sort-change="handleSortChange"
            @selection-change="onTableSelectionChange"
            @row-click="handleRowClick"
            @row-dblclick="handleRowDblClick"
          >
            <el-table-column
              v-if="selectionConfig.enabled"
              type="selection"
              width="55"
              fixed="left"
            />

            <el-table-column
              v-for="column in visibleColumns"
              :key="column.prop"
              :prop="column.prop"
              :label="column.label"
              :width="getColumnWidth(column)"
              :min-width="column.minWidth"
              :sortable="column.sortable ? 'custom' : false"
              :fixed="column.fixed"
              :align="column.align || 'left'"
              :header-align="column.align || 'left'"
              :show-overflow-tooltip="column.showOverflowTooltip"
              :resizable="column.resizable !== false"
            >
              <template #header>
                <div class="column-header" :class="{ 'is-immutable': column.immutable && inlineEditMode, 'is-sortable': column.sortable }">
                  <el-tooltip
                    :content="column.label + (column.immutable && inlineEditMode ? ' (不可编辑)' : '')"
                    placement="top"
                    :show-after="300"
                    effect="dark"
                    :teleported="false"
                    popper-class="app-tooltip-popper"
                  >
                    <span
                      class="column-title"
                      :class="{ 'is-sortable': column.sortable }"
                      :title="column.sortable ? '点击列名排序' : ''"
                      @click.stop="onHeaderTitleClick(column)"
                    >
                      {{ column.label }}
                      <el-icon v-if="column.immutable && inlineEditMode" class="immutable-icon">
                        <Lock />
                      </el-icon>
                    </span>
                  </el-tooltip>
                  <!-- [FIX 2026-06-10] 自定义列头补回排序指示器 (Element Plus 自定义 #header 后内置 sort icon 丢失) -->
                  <span
                    v-if="column.sortable"
                    class="sort-indicator"
                    :class="getSortIndicatorClass(column)"
                    :title="getSortIndicatorTitle(column)"
                    @click.stop="onSortIndicatorClick(column)"
                  >
                    <el-icon class="sort-icon sort-icon--asc">
                      <CaretTop />
                    </el-icon>
                    <el-icon class="sort-icon sort-icon--desc">
                      <CaretBottom />
                    </el-icon>
                  </span>
                  <TableHeaderFilter
                    v-if="column.filterable"
                    :filter-type="column.filter_type || 'search'"
                    :options="column.filter_options || column.options || []"
                    :enum-type="column.enum_type || ''"
                    :placeholder="column.filter_placeholder || '输入搜索'"
                    :model-value="headerFilterValues[column.prop]"
                    :width="getFilterWidth(column)"
                    :value-help-config="column.valueHelpConfig || column.value_help || null"
                    @update:model-value="(val) => handleHeaderFilter(column.prop, val)"
                  />
                </div>
              </template>

              <template #default="{ row }">
                <InlineEditCell
                  v-if="inlineEditMode"
                  :row="row"
                  :field-name="column.prop"
                  :field-config="getFieldEditConfig(column.prop)"
                  :value="getCellValue(row, column.prop)"
                  :editing="isCellEditable(row, column.prop) && isEditing(row.id, column.prop)"
                  :hovered="isHovered(row.id, column.prop)"
                  :mode="isExternallyControlled ? 'direct' : (inlineEditConfig?.mode || 'quick')"
                  :original-value="row[column.prop]"
                  :editable="isCellEditable(row, column.prop)"
                  :immutable="column.immutable"
                  @hover="setHoveredCell(row.id, column.prop)"
                  @leave="clearHoveredCell()"
                  @start-edit="startEditCell(row, column.prop)"
                  @finish-edit="finishEditCell(true)"
                  @cancel-edit="finishEditCell(false)"
                  @update:value="(val) => updateDraftValue(row.id, column.prop, val)"
                />
                
                <template v-if="!inlineEditMode">
                <FkLinkField
                  v-if="isFkColumn(column)"
                  :value="row[column.prop]"
                  :display-value="getFkDisplayValue(row, column)"
                  :target-object-type="getFkTargetObjectType(column)"
                  :link-disabled="isEmbeddedOrDialogMode"
                />
                <span
                  v-else-if="column.link && row[column.prop]"
                  class="bk-link"
                  @click.stop="handleColumnLinkClick(row, column)"
                >
                  {{ row[column.prop] }}
                </span>
                <span v-else-if="column.link && !row[column.prop]" class="bk-empty">-</span>
                <span
                  v-else-if="isBusinessKeyColumn(column) && row[column.prop]"
                  class="bk-link"
                  title="查看本对象详情"
                  @click.stop="handleBusinessKeyClick(row)"
                >
                  {{ row[column.prop] }}
                </span>
                <span v-else-if="isBusinessKeyColumn(column)" class="bk-empty">-</span>
                
                <template v-else-if="isBadgeColumn(column)">
                  <el-tag
                    :type="getBadgeTagType(row, column) || 'primary'"
                    size="small"
                    effect="light"
                  >
                    {{ getBadgeDisplayValue(row, column) }}
                  </el-tag>
                </template>
                
                <slot v-else-if="$slots[`cell-${column.prop}`]" :name="`cell-${column.prop}`" :row="row" :column="column">
                  {{ row[column.prop] ?? '-' }}
                </slot>
                
                <template v-else>
                  <template v-if="column.format === 'datetime' || column.type === 'datetime'">
                    {{ formatDate(getCellDisplayValue(row, column)) }}
                  </template>
                  <template v-else-if="column.format === 'code' && getCellDisplayValue(row, column)">
                    <code class="cell-code-text">{{ getCellDisplayValue(row, column) }}</code>
                  </template>
                  <template v-else-if="column.type === 'ellipsis'">
                    <span class="ellipsis-text">{{ getCellDisplayValue(row, column) || '-' }}</span>
                  </template>
                  <template v-else>
                    {{ getCellDisplayValue(row, column) ?? '-' }}
                  </template>
                </template>
                </template>
              </template>
            </el-table-column>

            <!-- 操作列：仅在有行级操作且非inline编辑时显示 -->
            <el-table-column
              v-if="!inlineEditConfig?.enabled && hasRowActions"
              label=""
              :width="50"
              fixed="right"
              header-align="center"
              align="center"
              class-name="action-column"
            >
              <template #default="{ row }">
                <el-dropdown
                  trigger="click"
                  :teleported="false"
                  popper-class="row-action-popper"
                  @command="(key) => handleDropdownCommand(key, row)"
                >
                  <el-button size="small" link class="row-action-trigger">
                    <el-icon :size="16"><MoreFilled /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu class="row-action-menu">
                      <el-dropdown-item
                        v-for="action in getRowActions(row)"
                        :key="action.key"
                        :command="action.key"
                        :disabled="action.disabled"
                        :divided="action.divided"
                      >
                        <el-icon :size="14">
                          <component :is="getActionIcon(action)" />
                        </el-icon>
                        {{ action.label }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </slot>

    <!-- Inline Edit 工具栏 -->
    <InlineEditToolbar
      v-if="inlineEditConfig?.enabled && !isExternallyControlled"
      :show="hasUnsavedChanges"
      :draft-count="draftValues.size"
      :position="inlineEditConfig?.toolbarPosition || 'bottom'"
      :saving="loading"
      @save="saveDraftValues"
      @cancel="cancelInlineEdit"
    />

    <slot name="pagination">
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.pageSize"
          :page-sizes="paginationConfig.pageSizes"
          :total="pagination.total"
          :layout="paginationConfig.layout"
          :background="paginationConfig.background"
          @size-change="handlePageSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </slot>

    <slot name="dialogs">
    </slot>

    <ExportDialog
      v-model:visible="showExportDialog"
      :object-type="objectType"
      :object-type-name="metaConfig?.name || ''"
      :current-count="data.length"
      :total-count="filteredTotalCount"
      :filters="exportFilters"
      :sort-info="sortInfo"
      :default-sort="defaultSort"
      :export-options="exportOptions"
      @success="handleExportSuccess"
      @close="showExportDialog = false"
    />

    <ImportDialog
      v-model:visible="showImportDialog"
      :object-type="objectType"
      :fields="visibleColumns"
      :import-options="importOptions"
      :context="importContext"
      @success="handleImportSuccess"
      @close="showImportDialog = false"
    />

    <DetailPage
      v-if="enableDetailPage && showDetailDrawer && (detailCreateMode || selectedDetailId)"
      v-model="showDetailDrawer"
      v-model:id="selectedDetailId"
      :object-type="objectType"
      :title="detailTitle"
      :edit-mode="detailEditMode"
      :create-mode="detailCreateMode"
      :show-delete="enableAutoDelete"
      @delete="handleDetailDelete"
      @close="handleDetailClose"
      @created="handleDetailCreated"
      @saved="handleDetailSaved"
    />

    <ConfirmDialog
      v-if="enableAutoDelete"
      v-model="showDeleteConfirm"
      :title="deleteConfirmTitle"
      :message="deleteConfirmMessage"
      :loading="deleteLoading"
      @confirm="executeDelete"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted, markRaw, inject } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown, ArrowUp, View, Edit, Delete, List, Plus, Upload, Download, Setting, Lock, MoreFilled, Document, CopyDocument, Promotion, CaretTop, CaretBottom, Sort } from '@element-plus/icons-vue'
import { useMetaList, formatDate } from '@/composables/useMetaList'
import { useAssociationNavigation } from '@/composables/useAssociationNavigation'
import { useMenuPermissions } from '@/composables/useMenuPermissions'
import { useCrudMessage } from '@/composables/useCrudMessage'
import TableHeaderFilter from '@/components/common/TableHeaderFilter/TableHeaderFilter.vue'
import ExportDialog from '@/components/common/ExportDialog/ExportDialog.vue'
import ImportDialog from '@/components/common/ImportDialog/ImportDialog.vue'
import { DetailPage } from '@/components/common/DetailPage'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import InlineEditCell from './InlineEditCell.vue'
import InlineEditToolbar from './InlineEditToolbar.vue'
import AssociationNavigationMenu from './AssociationNavigationMenu.vue'
import NavigationSourceInfo from './NavigationSourceInfo.vue'
import FkLinkField from '@/components/common/FkLinkField/FkLinkField.vue'

const ICON_MAP = {
  view: markRaw(View),
  edit: markRaw(Edit),
  delete: markRaw(Delete),
  list: markRaw(List),
  plus: markRaw(Plus),
  upload: markRaw(Upload),
  download: markRaw(Download),
  setting: markRaw(Setting),
  default: markRaw(View)
}

function getIconComponent(icon) {
  return ICON_MAP[icon] || ICON_MAP.default
}

const ACTION_ICON_MAP = {
  'view': View,
  'detail': View,
  '查看': View,
  '详情': View,
  'edit': Edit,
  '编辑': Edit,
  'update': Edit,
  'delete': Delete,
  '删除': Delete,
  'remove': Delete,
  'copy': CopyDocument,
  '复制': CopyDocument,
  'export': Download,
  '导出': Download,
  'import': Upload,
  '导入': Upload,
  'create': Plus,
  '新建': Plus,
  'add': Plus,
  'list': List,
  '列表': List,
  'setting': Setting,
  '设置': Setting,
  'config': Setting,
  'default': MoreFilled
}

function getActionIcon(action) {
  if (action.icon) {
    return ICON_MAP[action.icon] || ACTION_ICON_MAP.default
  }
  const key = action.key?.toLowerCase() || ''
  return ACTION_ICON_MAP[key] || ACTION_ICON_MAP.default
}
import { boService } from '@/services/boService'
import { useListActionStore } from '@/stores/listActionStore'

const props = defineProps({
  objectType: {
    type: String,
    required: true
  },
  options: {
    type: Object,
    default: () => ({})
  },
  initialFilters: {
    type: Object,
    default: () => ({})
  },
  exportOptions: {
    type: Object,
    default: () => ({ includeFilters: true })
  },
  importOptions: {
    type: Object,
    default: () => ({ validateBeforeImport: true })
  },
  rowActionsWidth: {
    type: [Number, String],
    default: 200
  },
  enableDetail: {
    type: Boolean,
    default: true
  },
  enableAutoCrud: {
    type: Boolean,
    default: true
  },
  rowMutability: {
    type: String,
    default: null,
    validator: (v) => [null, 'locked', 'extensible', 'fully_editable'].includes(v)
  },
  externalEditing: {
    type: Boolean,
    default: null
  },
  // ========== compact mode props ==========
  displayMode: {
    type: String,
    default: 'page',
    validator: (v) => ['page', 'embedded', 'dialog'].includes(v)
  },
  hideToolbar: {
    type: Boolean,
    default: false
  },
  columnsOverride: {
    type: Array,
    default: null
  },
  excludeIds: {
    type: Array,
    default: () => []
  },
  rowKey: {
    type: String,
    default: 'id'
  },
  rowActionsOverride: {
    type: Array,
    default: null
  },
  toolbarActionsOverride: {
    type: Array,
    default: null
  },
  batchActionsOverride: {
    type: Array,
    default: null
  },
  hideAssociationNavigation: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits([
  'action',
  'create',
  'edit',
  'delete',
  'detail',
  'export',
  'import',
  'batch-delete',
  'batch-action',
  'data-loaded',
  'request-edit',
  'toolbar-action',
  'selection-change',
  'row-click',
  'row-dblclick'
])

const router = useRouter()
const message = useCrudMessage()
const { objectTypeRouteMap, loadMenuPermissions: loadPermissions } = useMenuPermissions()
const tableRef = ref(null)
const coordinator = inject('refreshCoordinator', null)
// [FIX 2026-06-11] 点击循环状态: 0=无排序, 1=升序, 2=降序
// 单独维护避免依赖 Element Plus 内部状态 (自定义 sortable 时不可靠)
const sortClickCycle = ref(new Map())

const {
  metaConfig,
  columns,
  visibleColumns,
  data,
  loading,
  selectedRows,
  selectedIds,
  totalSelectedCount,
  filterFields,
  visibleFilterFields,
  filterValues,
  headerFilterValues,
  contextFilters,
  setContextFilters,
  searchFields,
  keyword,
  toolbarActions,
  rowActions,
  batchActions,
  pagination,
  paginationConfig,
  sortInfo,
  defaultSort,
  filteredTotalCount,
  selectionConfig,
  exportFilters,
  init,
  loadList,
  refresh,
  handleAction,
  handleToolbarAction,
  handleBatchAction,
  handleSortChange,
  handlePageChange,
  handlePageSizeChange,
  handleSelectionChange,
  handleHeaderFilter,
  resetFilters,
  handleFilter,
  getRowActions,
  clearAllSelection,
  showExportDialog,
  showImportDialog,
  handleExportSuccess,
  handleImportSuccess,
  handleBatchExport,
  handleBatchImport,
  // Inline Edit
  inlineEditConfig,
  inlineEditMode,
  draftValues,
  editingCell,
  hoveredCell,
  hasUnsavedChanges,
  enableInlineEdit,
  disableInlineEdit,
  startEditCell,
  finishEditCell,
  updateDraftValue,
  addNewRow,
  cancelInlineEdit,
  saveDraftValues,
  getDraftCreates,
  isCellEditable,
  getFieldEditConfig,
  getCellValue,
  isEditing,
  isHovered,
  setHoveredCell,
  clearHoveredCell,
  navigableAssociations,
  getNavigableAssociations,
  batchGetAssociationCounts
} = useMetaList(props.objectType, {
  mode: 'element-plus',
  autoLoad: props.options.autoLoad !== false,
  pageSize: props.options.pageSize || 20,
  pageSizes: props.options.pageSizes || null,
  debug: props.options.debug || false,
  rowMutability: props.rowMutability,
  displayMode: props.displayMode,
  columnsOverride: props.columnsOverride,
  excludeIds: props.excludeIds,
  rowKey: props.rowKey,
  rowActionsOverride: props.rowActionsOverride,
  toolbarActionsOverride: props.toolbarActionsOverride,
  batchActionsOverride: props.batchActionsOverride,
  fetcher: props.options.fetcher,
  inlineEdit: props.options.inlineEdit
})

// [DECORATIVE] [NEW] v1.3 / FR-6.4: 读取 display_value（优先后端注入）
// getCellValue 已处理 display_values，此处薄封装供模板用
function getCellDisplayValue(row, column) {
  return getCellValue(row, column.prop)
}

if (props.objectType === 'user') {
  console.log(`[MetaListPage] [DECORATIVE] useMetaList for user called, options=`, JSON.stringify(props.options), `displayMode=${props.displayMode}, externalEditing=${props.externalEditing}`)
}

function onTableSelectionChange(rows) {
  handleSelectionChange(rows)
  emit('selection-change', rows)
}

function handleRowClick(row, column, event) {
  emit('row-click', { row, column, event })
}

function handleRowDblClick(row, column, event) {
  emit('row-dblclick', { row, column, event })
}

const {
  navigationSource,
  parseNavigationParams,
  navigateToAssociation,
  navigateBack,
  isNavigationTarget,
  getNavigationFilterParam
} = useAssociationNavigation()

const isNavTarget = computed(() => isNavigationTarget())

const navSourceInfo = computed(() => {
  if (!navigationSource.value) return null
  return {
    sourceType: navigationSource.value.sourceType,
    sourceIds: navigationSource.value.sourceIds,
    sourceNames: navigationSource.value.sourceNames,
    associationName: navigationSource.value.associationName,
    associationLabel: navigationSource.value.associationName
  }
})

async function onAssociationNavigate(association) {
  if (selectedIds.value.size === 0) return
  await navigateToAssociation(association, selectedIds.value, props.objectType, {
    filterValues: filterValues.value,
    sortInfo: sortInfo.value,
    pagination: { current: pagination.current, pageSize: pagination.pageSize }
  })
}

function onNavigateBack() {
  navigateBack()
}

const hasDetailConfig = computed(() => {
  return !!metaConfig.value?.detail
})

const enableDetailPage = computed(() => {
  if (isCompactMode.value) return false
  return props.enableDetail
})

const importContext = computed(() => ({
  version_id: contextFilters.value?.version_id || null,
  product_id: contextFilters.value?.product_id || null
}))

const enableAutoDelete = computed(() => {
  return props.enableAutoCrud && props.enableDetail
})

const hasRowActions = computed(() => {
  return rowActions.value?.length > 0
})

const PRIMARY_ACTION_SEMANTICS = ['create', 'new', 'add', 'insert', 'assign']

const primaryToolbarActions = computed(() => {
  const result = toolbarActions.value.filter(action =>
    PRIMARY_ACTION_SEMANTICS.some(s => action.key?.toLowerCase().includes(s))
  )
  console.debug('[MetaListPage] primaryToolbarActions:', {
    allActions: toolbarActions.value,
    filtered: result
  })
  return result
})

const secondaryToolbarActions = computed(() =>
  toolbarActions.value.filter(action =>
    !PRIMARY_ACTION_SEMANTICS.some(s => action.key?.toLowerCase().includes(s))
  )
)

const showDetailDrawer = ref(false)
const selectedDetailId = ref(null)
const detailEditMode = ref(false)
const detailCreateMode = ref(false)
const tableKey = ref(0)

async function forceRefresh() {
  await refresh()
  tableKey.value++
}

const detailTitle = computed(() => {
  if (detailCreateMode.value) {
    return `新建 ${metaConfig.value?.name || ''}`
  }
  return metaConfig.value?.detail?.title || `${metaConfig.value?.name || '详情'}`
})

const showDeleteConfirm = ref(false)
const deleteConfirmTitle = ref('')
const deleteConfirmMessage = ref('')
const deleteLoading = ref(false)
const deleteTargetRow = ref(null)

const computedActionWidth = computed(() => {
  if (props.rowActionsWidth && props.rowActionsWidth !== 200) return props.rowActionsWidth
  const count = rowActions.value?.length || 0
  if (count === 0) return 80
  // 每个按钮约 70px (icon + text + padding + gap)
  return Math.max(100, count * 70 + 20)
})

function getColumnWidth(column) {
  const base = column.width || column.minWidth || 120
  let extra = 0
  if (column.sortable) extra += 22
  if (column.filterable) extra += 18
  return base + extra
}

// ========== [FIX 2026-06-10] 自定义列头排序指示器 ==========
// 当用户使用自定义 #header slot 时, Element Plus 内置 sort 图标不会渲染.
// 这里手动添加三态排序指示器 (无 → 升序 → 降序 → 无).
// 点击列名或排序图标都触发 onSortIndicatorClick.

/**
 * 获取当前列的排序状态类
 * - 'is-asc'  升序激活
 * - 'is-desc' 降序激活
 * - ''        无排序 (默认)
 */
function getSortIndicatorClass(column) {
  if (!column?.sortable) return ''
  const prop = column.prop
  if (!prop || !sortInfo.value) return ''
  if (sortInfo.value.prop !== prop) return ''
  if (sortInfo.value.order === 'ascending') return 'is-asc'
  if (sortInfo.value.order === 'descending') return 'is-desc'
  return ''
}

/**
 * 获取排序指示器的 tooltip
 */
function getSortIndicatorTitle(column) {
  if (!column?.sortable) return ''
  const cls = getSortIndicatorClass(column)
  if (cls === 'is-asc') return '当前升序，点击切换为降序'
  if (cls === 'is-desc') return '当前降序，点击取消排序'
  return '点击按此列排序'
}

/**
 * 三态切换排序: 无 → 升序 → 降序 → 无
 * [FIX 2026-06-11] 使用独立 clickCycle Map 维护状态, 不依赖 Element Plus 内部状态
 */
function onSortIndicatorClick(column) {
  if (!column?.sortable || !tableRef.value) return
  const prop = column.prop
  if (!prop) return

  // 1. 检测是否切换到新列: 如果是, 重置该列的 cycle 为 0
  const prevProp = sortClickCycle.value.get('__lastProp')
  if (prevProp !== prop) {
    // 重置所有列的 cycle
    sortClickCycle.value.clear()
    sortClickCycle.value.set('__lastProp', prop)
  }

  // 2. 获取当前列的 cycle (0=无, 1=升序, 2=降序)
  const currentCycle = sortClickCycle.value.get(prop) || 0

  // 3. 计算下一个状态
  let nextCycle, nextOrder
  if (currentCycle === 0) {
    // 无排序 → 升序
    nextCycle = 1
    nextOrder = 'ascending'
  } else if (currentCycle === 1) {
    // 升序 → 降序
    nextCycle = 2
    nextOrder = 'descending'
  } else {
    // 降序 → 取消排序
    nextCycle = 0
    nextOrder = null
  }

  // 4. 更新 cycle 状态
  sortClickCycle.value.set(prop, nextCycle)

  // 5. 立即同步本地 sortInfo, 避免 handleSortChange 时序问题
  sortInfo.value = {
    prop: nextOrder ? prop : null,
    order: nextOrder
  }

  // 6. 同步 Element Plus 内部状态 (用于表头高亮)
  // order 参数: 'ascending' / 'descending' / null
  if (nextOrder) {
    tableRef.value.sort(prop, nextOrder)
  } else {
    tableRef.value.clearSort()
  }

  // 7. 触发数据加载
  // 重要: 直接调用 loadList 而不是等 sort-change 事件, 避免重复请求
  pagination.current = 1
  loadList()
}

/**
 * 点击列名 (非图标) 也触发排序
 */
function onHeaderTitleClick(column) {
  if (!column?.sortable) return
  onSortIndicatorClick(column)
}

function isFkColumn(column) {
  if (!column?.valueHelpConfig?.source) return false
  return column.valueHelpConfig.source.type === 'bo'
}

function getFkTargetObjectType(column) {
  if (!isFkColumn(column)) return null
  return column.valueHelpConfig.source.target_bo || null
}

function getFkDisplayValue(row, column) {
  const value = row[column.prop]
  if (value == null) return ''
  const displayKey = `${column.prop}_display`
  const nameKey = `${column.prop.replace(/_id$/, '')}_name`
  return row[displayKey] || row[nameKey] || value
}

function isBusinessKeyColumn(column) {
  return column?.businessKey === true
}

function isBadgeColumn(column) {
  return column?.widget === 'badge' || 
    (column?.enum_values && column.enum_values.length > 0) ||
    (column?.options && column.options.length > 0 && column.widget === 'tag')
}

const TAG_TYPE_MAP = {
  success: 'success', warning: 'warning', danger: 'danger',
  info: 'info', primary: '', default: '', error: 'danger',
  green: 'success', red: 'danger', orange: 'warning', blue: 'primary',
  gray: 'info', grey: 'info'
}

function getMappedTagType(colorValue) {
  if (!colorValue) return ''
  const mapped = TAG_TYPE_MAP[colorValue]
  return mapped !== undefined ? mapped : ''
}

function getBadgeTagType(row, column) {
  const rawValue = row[column.prop]
  
  if (column.badgeColors) {
    const mappedColor = column.badgeColors[rawValue]
    if (mappedColor) return getMappedTagType(mappedColor)
    if (column.type === 'boolean') {
      const altColor = column.badgeColors[rawValue ? true : false] || column.badgeColors[rawValue ? 'true' : 'false']
      if (altColor) return getMappedTagType(altColor)
    }
  }
  
  if (column.enum_values) {
    let matched = column.enum_values.find(e => e.value === rawValue)
    if (!matched && column.type === 'boolean') {
      matched = column.enum_values.find(e =>
        e.value === rawValue ||
        e.value === Boolean(rawValue) ||
        (typeof e.value === 'boolean' && Number(e.value) === rawValue)
      )
    }
    if (matched?.color) return getMappedTagType(matched.color)
  }
  
  return ''
}

function getBadgeDisplayValue(row, column) {
  const rawValue = row[column.prop]
  if (rawValue === '') return '-'
  
  if (rawValue == null) {
    if (column.enum_values) {
      const nullVal = column.type === 'boolean' ? 0 : null
      const fallback = column.enum_values.find(e =>
        e.value === 0 || e.value === false || String(e.value) === '0'
      )
      if (fallback) return fallback.label
    }
    return '-'
  }
  
  if (typeof rawValue === 'boolean') {
    if (column.enum_values) {
      const matched = column.enum_values.find(e => e.value === rawValue || e.value === Number(rawValue))
      if (matched) return matched.label
    }
    return rawValue ? '是' : '否'
  }
  
  if ((rawValue === 1 || rawValue === 0 || rawValue === '1' || rawValue === '0') && column.type === 'boolean') {
    if (column.enum_values) {
      const matched = column.enum_values.find(e => {
        const ev = e.value
        return String(ev) === String(rawValue) || ev === rawValue || ev === Boolean(rawValue)
      })
      if (matched) return matched.label
    }
    return rawValue === 1 || rawValue === '1' ? '是' : '否'
  }
  
  if (column.enum_values) {
    let matched = column.enum_values.find(e => e.value === rawValue)
    if (!matched) {
      matched = column.enum_values.find(e =>
        e.value === rawValue ||
        String(e.value) === String(rawValue) ||
        (column.type === 'boolean' && (e.value === Boolean(rawValue) || Number(e.value) === Number(rawValue)))
      )
    }
    if (matched) return matched.label
  }
  
  if (column.options) {
    const matched = column.options.find(o => o.value === rawValue || String(o.value) === String(rawValue))
    if (matched) return matched.label
  }
  
  return rawValue
}

const advancedFilterVisible = ref(false)

const hiddenFilterFields = computed(() => {
  return filterFields.value.filter(field => field.defaultVisible === false)
})

function isDateRangeType(type) {
  return type === 'date-range' || type === 'daterange' || type === 'datetime-range' || type === 'datetimerange' || type === 'date_range'
}

function isNumberRangeType(type) {
  return type === 'number-range' || type === 'numberrange' || type === 'number_range'
}

function handleFilterChange(key, value) {
  filterValues.value[key] = value
}

function resetAdvancedFilters() {
  hiddenFilterFields.value.forEach(field => {
    filterValues.value[field.key] = undefined
  })
  handleFilter(filterValues.value)
}

function getFilterWidth(column) {
  const filterType = column.filter_type || 'search'
  if (filterType === 'date-range') return 320
  if (filterType === 'number-range') return 320
  if (filterType === 'select') return 200
  return 200
}

function onKeywordSearch() {
  pagination.current = 1
  loadList()
}

function onResetFilters() {
  // 使用 composable 的 resetFilters，它会保留 contextFilters
  keyword.value = ''
  resetFilters()
}

/**
 * 判断是否可以执行 CRUD 操作
 */
function canPerformCrud() {
  if (!props.rowMutability) return true
  return props.rowMutability !== 'locked'
}

function canDelete(row) {
  if (!props.rowMutability) return true
  if (props.rowMutability === 'locked') return false
  if (props.rowMutability === 'extensible') {
    return row?.is_system !== true && row?.system_value !== true
  }
  return true
}

/**
 * 获取过滤后的工具栏按钮
 * 基于 rowMutability 和编辑模式过滤
 */
function getFilteredToolbarActions(actions) {
  if (!canPerformCrud()) return []
  
  const filtered = actions.filter(action => {
    const key = action.key?.toLowerCase()
    // edit 按钮：只在非编辑模式下显示
    if (key === 'edit' || key === '编辑') {
      return !inlineEditMode.value
    }
    return true
  })
  return filtered
}

function onToolbarAction(action) {
  console.log('[MetaListPage] onToolbarAction 被调用, action.key:', action.key)
  
  // 先 emit toolbar-action 事件，让父组件有机会处理
  emit('toolbar-action', action)
  
  if (action.key === 'create' || action.key === '新建' || action.key === 'new') {
    if (isExternallyControlled.value && !inlineEditMode.value) {
      inlineEditMode.value = true
      emit('request-edit')
      nextTick(() => {
        addNewRow()
      })
      return
    }
    if (inlineEditMode.value) {
      addNewRow()
      return
    }
  }
  
  onRowAction({ action, row: null })
}

function onBatchAction(action) {
  console.log('[MetaListPage] onBatchAction 被调用, action.key:', action.key, 'selectedIds:', selectedIds.value)
  
  // emit batch-action 事件，让父组件处理
  // 对于 batch_unassign 等自定义批量操作，由父组件完全处理
  emit('batch-action', {
    action,
    selectedIds: selectedIds.value,
    selectedRows: selectedRows.value
  })
  
  // 对于已知的内置批量操作，调用 useMetaList 的 handleBatchAction
  // batch_unassign 由父组件处理，不再调用 handleBatchAction
  if (action.key !== 'batch_unassign') {
    handleBatchAction(action)
  }
}

function handleDropdownCommand(actionKey, row) {
  const actions = getRowActions(row)
  const action = actions.find(a => a.key === actionKey)
  if (action) {
    onRowAction({ action, row })
  }
}

function onRowAction(payload) {
  const { action, row } = payload
  console.log('[MetaListPage] onRowAction 被调用, action.key:', action.key, 'container:', action.container)

  if (action.container === 'page') {
    navigateToPage(action, row)
    emit('action', payload)
    return
  }

  if (action.key === 'create') {
    if (hasDetailPageRoute()) {
      navigateToDetailPageForCreate()
    } else if (enableDetailPage.value && !hasCustomDialog('create')) {
      openCreateDrawer()
    } else {
      emit('create', payload)
    }
  } else if (action.key === 'edit') {
    if (hasDetailPageRoute()) {
      navigateToDetailPage(row)
    } else if (enableDetailPage.value && !hasCustomDialog('edit')) {
      openDetailDrawer(row, true)
    } else {
      emit('edit', payload)
    }
  } else if (action.key === 'delete') {
    if (enableAutoDelete.value && !hasCustomDialog('delete')) {
      openDeleteConfirm(row, action)
    } else {
      emit('delete', payload)
    }
  } else if (action.key === 'detail' || action.key === 'view') {
    if (hasDetailPageRoute()) {
      navigateToDetailPage(row)
    } else if (enableDetailPage.value && !hasCustomDialog('detail')) {
      openDetailDrawer(row, false)
    } else {
      emit('detail', payload)
    }
  } else if (action.key === 'export') {
    handleBatchExport()
  } else if (action.key === 'import') {
    handleBatchImport()
  } else {
    // 其他自定义 action，默认 emit
    emit('action', payload)
  }
}

function hasDetailPageRoute() {
  return metaConfig.value?.list?.detail_mode === 'page'
}

function navigateToDetailPage(row) {
  const listConfig = metaConfig.value?.list
  const basePath = listConfig?.detail_path || `/detail/${props.objectType}`
  router.push({ path: `${basePath}/${row.id}` }).catch(() => {})
}

function navigateToDetailPageForCreate() {
  const listConfig = metaConfig.value?.list
  const basePath = listConfig?.detail_path || `/detail/${props.objectType}`
  router.push({ path: basePath, query: { mode: 'add' } }).catch(() => {})
}

function navigateToPage(action, row) {
  const listConfig = metaConfig.value?.list
  const target = action.target || props.objectType
  let routePath = ''
  const query = {}

  if (action.target) {
    const basePath = objectTypeRouteMap.value[target] || `/${target.replace(/_/g, '-')}`
    routePath = basePath
    query[`${props.objectType}_id`] = row.id
    query.id = row.id
    query.name = row.name || row.code || row.display_name
    query.mutability = row.mutability
  } else {
    const basePath = listConfig?.detail_path || `/${props.objectType.replace(/_/g, '-')}`
    routePath = `${basePath}/${row.id}`
  }

  if (action.params) {
    Object.entries(action.params).forEach(([key, value]) => {
      if (typeof value === 'string' && value.startsWith('{') && value.endsWith('}')) {
        const fieldKey = value.slice(1, -1)
        query[key] = row[fieldKey]
      } else {
        query[key] = value
      }
    })
  }

  console.log('[MetaListPage] navigateToPage path:', routePath, 'query:', JSON.stringify(query))

  router.push({
    path: routePath,
    query
  }).catch(err => {
    console.error('[MetaListPage] 路由跳转失败:', err)
  })
}

function hasCustomDialog(actionKey) {
  return false
}

function openCreateDrawer() {
  detailCreateMode.value = true
  detailEditMode.value = false
  selectedDetailId.value = null
  showDetailDrawer.value = true
}

function openDetailDrawer(row, editMode = false) {
  detailCreateMode.value = false
  selectedDetailId.value = row.id
  detailEditMode.value = editMode
  showDetailDrawer.value = true
}

function handleColumnLinkClick(row, column) {
  const link = column.link
  if (!link || !link.path) return

  const query = {}
  if (link.params) {
    Object.entries(link.params).forEach(([key, value]) => {
      if (typeof value === 'string' && value.startsWith('{{') && value.endsWith('}}')) {
        const fieldKey = value.slice(2, -2)
        query[key] = row[fieldKey] !== undefined ? row[fieldKey] : value
      } else {
        query[key] = value
      }
    })
  }

  router.push({ path: link.path, query }).catch(() => {})
}

function handleBusinessKeyClick(row) {
  const detailAction = rowActions.value.find(a => a.key === 'detail' || a.key === 'view')
  if (detailAction?.container === 'page' || hasDetailPageRoute()) {
    navigateToDetailPage(row)
  } else {
    openDetailDrawer(row, false)
  }
}

function handleDetailClose() {
  selectedDetailId.value = null
  detailEditMode.value = false
  detailCreateMode.value = false
}

function handleDetailCreated(createdData) {
  detailCreateMode.value = false
  emit('create', { row: createdData })
  if (createdData?.id) {
    showDetailDrawer.value = false
    selectedDetailId.value = null
    forceRefresh()
  } else {
    forceRefresh()
  }
}

function handleDetailSaved(savedData) {
  detailEditMode.value = false
  forceRefresh()
  emit('edit', { row: savedData })
}

function handleDetailDelete(deletedDetail) {
  forceRefresh()
  emit('delete', { row: deletedDetail })
}

function openDeleteConfirm(row, action) {
  deleteTargetRow.value = row
  deleteConfirmTitle.value = action.confirmTitle || '删除确认'

  const displayNameField = metaConfig.value?.display_name_field
  const displayValue = (displayNameField && row[displayNameField])
    || row.name || row.code || row.display_name || row.username || row.id

  deleteConfirmMessage.value = action.confirm || `确定要删除「${displayValue}」吗？`
  showDeleteConfirm.value = true
}

async function executeDelete() {
  if (!deleteTargetRow.value) return
  
  deleteLoading.value = true
  try {
    const result = await boService.delete(props.objectType, deleteTargetRow.value.id)
    if (result.success) {
      message.deleted('数据')
      showDeleteConfirm.value = false
      deleteTargetRow.value = null
      await forceRefresh()
    } else {
      message.error('删除失败', result)
    }
  } catch (e) {
    message.error('删除失败', e)
  } finally {
    deleteLoading.value = false
  }
}

const isExternallyControlled = computed(() => props.externalEditing !== null)

const isPageMode = computed(() => props.displayMode === 'page')

const isEmbeddedOrDialogMode = computed(() =>
  props.displayMode === 'dialog' || props.displayMode === 'embedded'
)

// dialog/embedded 模式：使用 max-height 限制表格行数；page 模式：使用 height="100%" 填满容器
const tableHeight = computed(() => {
  if (isEmbeddedOrDialogMode.value) {
    // dialog/embedded 模式下，限制表格最大高度为 400px
    return null // 使用 max-height
  }
  return '100%' // page 模式填满容器
})
const tableMaxHeight = computed(() => {
  if (isEmbeddedOrDialogMode.value) {
    return 420
  }
  return null
})

const isCompactMode = computed(() => props.displayMode !== 'page')

watch(() => props.externalEditing, (val) => {
  if (val === null) return
  if (val === true) {
    if (inlineEditConfig.value?.enabled && !inlineEditMode.value) {
      inlineEditMode.value = true
    }
  } else {
    if (inlineEditMode.value) {
      cancelInlineEdit()
      inlineEditMode.value = false
    }
  }
})

watch(data, () => {
  nextTick(() => {
    if (tableRef.value) {
      tableRef.value.doLayout()
    }
    if (selectedIds.value.size === 0) return
    data.value.forEach(row => {
      const isSelected = selectedIds.value.has(row.id)
      tableRef.value.toggleRowSelection(row, isSelected)
    })
  })
}, { flush: 'post' })

watch(selectedIds, (newIds) => {
  nextTick(() => {
    if (!tableRef.value) return
    if (newIds.size === 0) {
      tableRef.value.clearSelection()
    }
  })
}, { flush: 'post' })

watch(data, (newData) => {
  if (newData) {
    emit('data-loaded', newData)
  }
}, { immediate: true })

watch(() => selectionConfig.value.enabled, (newVal, oldVal) => {
  if (newVal && !oldVal) {
    tableKey.value++
  }
})

let unsubscribeAction = null

onMounted(() => {
  unsubscribeAction = useListActionStore().registerHandler(props.objectType, handleMetaListAction)
  loadPermissions()
  
  if (coordinator) {
    coordinator.register(`list:${props.objectType}`, forceRefresh)
  }
  
  const navParams = parseNavigationParams()
  if (navParams) {
    const filterParam = getNavigationFilterParam()
    if (Object.keys(filterParam).length > 0) {
      setContextFilters(filterParam)
    }
  }
  
  if (Object.keys(props.initialFilters).length > 0) {
    setContextFilters(props.initialFilters)
    if (props.options.autoLoad !== false) {
      refresh()
    }
  }
})

onUnmounted(() => {
  if (unsubscribeAction) {
    unsubscribeAction()
    unsubscribeAction = null
  }
  if (coordinator) {
    coordinator.unregister(`list:${props.objectType}`)
  }
})

watch(() => props.columnsOverride, (newVal, oldVal) => {
  if (newVal && Array.isArray(newVal) && newVal.length > 0 && !oldVal) {
    init(newVal)
  }
})

function handleMetaListAction(action, row) {
  onRowAction({ action, row })
}

defineExpose({
  tableRef,
  metaConfig,
  data,
  loading,
  selectedRows,
  selectedIds,
  totalSelectedCount,
  pagination,
  sortInfo,
  defaultSort,
  filteredTotalCount,
  keyword,
  refresh: forceRefresh,
  loadList,
  resetFilters,
  setContextFilters,
  clearAllSelection,
  showExportDialog,
  showImportDialog,
  showDetailDrawer,
  selectedDetailId,
  openDetailDrawer,
  navigableAssociations,
  isNavTarget,
  navigationSource,
  inlineEditMode,
  hasUnsavedChanges,
  draftValues,
  saveDraftValues,
  cancelInlineEdit,
  enableInlineEdit,
  disableInlineEdit,
  isExternallyControlled,
  addNewRow,
  getDraftCreates
})
</script>

<style scoped>
/* [FIX 2026-06-11] Unify meta-list-page as one rounded card so toolbar and table
   read as a single component instead of toolbar floating above the table.
   - .meta-list-page now owns the background + border-radius (was missing)
   - .toolbar drops its own background + border-radius and gains a divider line
   - Layout fixes from 2026-06-09 (overflow-x, min-height, position: relative,
     flex-wrap: nowrap) are preserved to keep the historical drift regression
     from recurring (see docs/lessons-learned/layout/toolbar-drift-recurrence.md). */
.meta-list-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  flex-shrink: 1;
  gap: 0;
  overflow: hidden;
  background: var(--color-bg-container);
  border-radius: var(--border-radius-md);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: nowrap;
  gap: 12px;
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  /* [FIX 2026-06-12] Root-cause fix #9: 去掉 border-bottom 让 toolbar 和 table
     完全无缝衔接（之前是 1px solid #ebeef5 让两者看起来像独立的卡片） */
  border-bottom: none;
  overflow-x: auto;
  min-height: 44px;
  position: relative; /* Lock positioning context (2026-06-09 regression fix) */
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;

  .search-field {
    flex-shrink: 0;
  }

  .selection-info-wrapper {
    flex-shrink: 0;
  }
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.filter-toggle-icon {
  margin-left: 2px;
  transition: transform 0.25s ease;

  &.rotated {
    transform: rotate(180deg);
  }
}

.advanced-filter-panel {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-light);
  border-radius: 0 0 var(--border-radius-md) var(--border-radius-md);
  border-top: 1px solid var(--color-border-light, #eee);
  width: 100%;
  box-sizing: border-box;
  overflow-x: auto;

  :deep(.el-form) {
    flex-wrap: wrap;
  }

  :deep(.el-form-item) {
    margin-bottom: 4px;
    margin-right: var(--spacing-md);
  }

  :deep(.el-form-item__label) {
    font-size: var(--font-size-sm, 13px);
    color: var(--color-text-secondary, #666);
  }
}

.slide-expand-enter-active,
.slide-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.slide-expand-enter-from,
.slide-expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.slide-expand-enter-to,
.slide-expand-leave-from {
  opacity: 1;
  max-height: 120px;
}

.table-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.table-wrapper {
  flex: 1;
  min-height: 0;
}

.custom-table {
  height: 100%;
}

:deep(.el-table .el-table__header th .cell) {
  white-space: nowrap;
  overflow: visible;
}

:deep(.el-table .el-table__header th) {
  overflow: visible;
}

:deep(.action-column) {
  white-space: nowrap;
  overflow: visible;
}

:deep(.action-column .cell) {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-xs);
  overflow: visible;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  padding: var(--spacing-md);
  background: transparent;
  border-top: 1px solid var(--color-border-light, #ebeef5);
  flex-shrink: 0;
  margin-top: auto;
}

.selection-info-wrapper {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.selection-info {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.column-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.column-header.is-immutable .column-title {
  color: #909399;
}

.column-title {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* [FIX 2026-06-10] 可排序列名加 cursor 提示 + 颜色变化 */
.column-title.is-sortable {
  cursor: pointer;
  user-select: none;
  transition: color 0.15s ease;
}
.column-title.is-sortable:hover {
  color: var(--color-primary);
}

/* [FIX 2026-06-10] 排序指示器: 双箭头三态 */
.sort-indicator {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin-left: 2px;
  cursor: pointer;
  user-select: none;
  line-height: 1;
  gap: 0;
  flex-shrink: 0;
}
.sort-indicator .sort-icon {
  font-size: 11px;
  height: 7px;
  width: 11px;
  color: #c0c4cc;
  transition: color 0.15s ease;
}
.sort-indicator:hover .sort-icon {
  color: var(--color-primary);
}
.sort-indicator.is-asc .sort-icon--asc {
  color: var(--color-primary);
}
.sort-indicator.is-desc .sort-icon--desc {
  color: var(--color-primary);
}
.sort-indicator.is-asc .sort-icon--desc,
.sort-indicator.is-desc .sort-icon--asc {
  color: #e4e7ed;
}

.immutable-icon {
  color: #c0c4cc;
  font-size: 12px;
}

.action-buttons {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
}

.row-action-trigger {
  padding: 4px !important;
  min-width: 28px !important;
  height: 28px !important;
}

.row-action-trigger:hover {
  background-color: var(--color-primary-bg) !important;
}

.row-action-menu {
  min-width: 120px;
}
.row-action-menu .el-dropdown-menu__item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
}

.row-action-menu .el-icon {
  color: var(--color-text-secondary);
}

.row-action-menu .el-dropdown-menu__item:not(.is-disabled):hover .el-icon {
  color: var(--color-primary);
}

/* 行操作下拉弹层：使用 :deep() 因为 popper 是 teleport=false 后渲染在组件内 */
:deep(.row-action-popper) {
  z-index: var(--z-index-select) !important;
}

.ellipsis-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 不可编辑单元格在编辑模式下的样式 */
:deep(.el-table--inline-edit-mode) .cell-is-immutable {
  background-color: #f5f7fa !important;
  color: #909399;
}

:deep(.el-table--inline-edit-mode) .cell-is-immutable:hover {
  background-color: #ebeef5 !important;
}

.bk-link {
  color: var(--color-primary);
  cursor: pointer;
  transition: color 0.15s ease, text-decoration 0.15s ease;
}

.bk-link:hover {
  color: var(--color-primary-hover);
  text-decoration: underline;
}

.bk-empty {
  color: var(--color-text-tertiary);
}

/* ======== compact mode styles ========
   [FIX 2026-06-11] compact mode keeps the unified card look but with
   tighter padding. Container background and toolbar divider line are
   preserved (no card-vs-card visual jump when toggling displayMode).
   Embedded/dialog use cases drop the outer shadow to avoid double cards. */
.meta-list-page--compact {
  height: auto;
  box-shadow: none;

  .toolbar {
    padding: var(--spacing-xs) var(--spacing-sm);
  }

  .table-section {
    flex: none;
  }

  .pagination-wrapper {
    padding: var(--spacing-sm) var(--spacing-md);
    background: transparent;
  }

  :deep(.el-table) {
    font-size: 13px;

    .el-table__header th {
      padding: 8px 0;
    }

    .el-table__body td {
      padding: 6px 0;
    }
  }
}
</style>
