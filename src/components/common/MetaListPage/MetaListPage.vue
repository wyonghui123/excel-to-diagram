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
              :placeholder="searchPlaceholder"
              clearable
              size="default"
              prefix-icon="Search"
              style="width: 280px"
              @keydown.enter="onKeywordSearch"
              @clear="onKeywordSearch"
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
                @keydown.enter="handleFilterChange(field.key, $event)"
                @clear="handleFilterChange(field.key, $event)"
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
        <!-- [2026-10-13 移动端] 窄屏改渲染卡片，见 cardColumns 处的说明。
             与 el-table 互斥：卡片模式不含排序表头，故窄屏失去列排序能力
             （排序入口仍在表头筛选与工具栏中）。

             [FIX 2026-10-13 复用方回归] 此处曾用 v-if="isMobile"，导致
             embedded / dialog 类复用方在窄屏下也被卡片化 —— 但卡片内容
             由 useCardView（内含 displayMode==='page' 约束）驱动的
             cardColumns / cardPrimary 决定，embedded 下二者返回 []，
             于是渲染出「只有标题的 -、没有任何标签行」的空卡片列表，
             而依赖的 el-table 被 v-else 顶掉。审计日志页（embedded）
             实测中招。必须用 useCardView，与 v-else 严格互斥。 -->
        <div v-if="useCardView" v-loading="loading" class="meta-card-list">
          <div v-if="data.length === 0" class="list-empty-state">
            <el-icon :size="32" class="list-empty-icon"><FolderOpened /></el-icon>
            <div class="list-empty-title">{{ props.emptyText }}</div>
            <div v-if="props.emptyHint" class="list-empty-hint">{{ props.emptyHint }}</div>
          </div>

          <article
            v-for="row in data"
            :key="row[props.rowKey || 'id']"
            class="meta-card"
            :class="{ 'is-selected': isCardSelected(row) }"
          >
            <header class="meta-card__head">
              <el-checkbox
                v-if="selectionConfig.enabled"
                class="meta-card__check"
                :model-value="isCardSelected(row)"
                @click.stop
                @change="(v) => toggleCardSelection(row, v)"
              />
              <!-- [FIX 2026-10-13] 详情入口收敛到标题，参照 Ant Design 数据展示
                   规范：「By default, click on the title to navigate to the
                   details」。原先整卡绑 row-click，用户点卡片空白处也会跳详情，
                   误触成本高；且双击在触屏上不是可靠手势（可能与缩放冲突），
                   故双击也一并移除。标题后加箭头明示可点。 -->
              <component
                :is="cardTitleOpensDetail ? 'button' : 'span'"
                class="meta-card__title"
                :class="{ 'meta-card__title--link': cardTitleOpensDetail }"
                :type="cardTitleOpensDetail ? 'button' : undefined"
                @click="cardTitleOpensDetail && handleBusinessKeyClick(row)"
              >
                <span class="meta-card__title-text">{{ cardPrimary(row) ?? '-' }}</span>
                <el-icon
                  v-if="cardTitleOpensDetail"
                  class="meta-card__title-arrow"
                  :size="12"
                ><ArrowRight /></el-icon>
              </component>
              <el-dropdown
                v-if="!inlineEditConfig?.enabled && hasRowActions"
                trigger="click"
                :teleported="false"
                popper-class="row-action-popper"
                class="meta-card__menu"
                @click.stop
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
            </header>

            <dl class="meta-card__body">
              <div
                v-for="col in cardColumns"
                :key="col.prop"
                class="meta-card__row"
                @dblclick.stop
              >
                <dt class="meta-card__label">{{ col.label }}</dt>
                <dd class="meta-card__value">
                  <!-- [FIX 2026-10-13] 卡片值优先走 cell slot，与表格的
                       自定义渲染保持一致。这里刻意不加 v-if：Vue 的具名
                       插槽没有「未提供」的运行时判定，一旦用 slots 判断
                       是否提供并据此跳过，该列的标签行会整行消失，
                       变成只有标签没有值。靠 slot 的 fallback 兜底即可。 -->
                  <slot
                    :name="`cell-${col.prop}`"
                    :row="row"
                    :column="col"
                    :value="getCellDisplayValue(row, col)"
                  >
                    <FkLinkField
                      v-if="isFkColumn(col)"
                      :value="getFkIdValue(row, col)"
                      :display-value="getFkDisplayValue(row, col)"
                      :target-object-type="getFkTargetObjectType(col)"
                      :link-object-type="getFkLinkObjectType(col)"
                      :link-id="getFkLinkId(row, col)"
                      :detail-mode="getFkDetailMode(col)"
                      :link-disabled="isEmbeddedOrDialogMode"
                      @navigate="handleFkNavigate"
                    />
                    <el-tag
                      v-else-if="isBadgeColumn(col)"
                      :type="getBadgeTagType(row, col) || 'primary'"
                      size="small"
                      effect="light"
                    >{{ getBadgeDisplayValue(row, col) }}</el-tag>
                    <span
                      v-else-if="col.format === 'datetime' || col.type === 'datetime'"
                    >{{ formatDate(getCellDisplayValue(row, col)) }}</span>
                    <code
                      v-else-if="col.format === 'code' && getCellDisplayValue(row, col)"
                      class="cell-code-text"
                    >{{ getCellDisplayValue(row, col) }}</code>
                    <span v-else>{{ getCellDisplayValue(row, col) ?? '-' }}</span>
                  </slot>
                </dd>
              </div>
            </dl>
          </article>
        </div>

        <div v-else class="table-wrapper">
          <el-table
            ref="tableRef"
            :key="tableKey"
            v-loading="loading"
            :data="data"
            :row-key="rowKey"
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
              v-for="column in tableColumns"
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
                  <!-- [FIX 2026-06-10] 自定义列头补回排序指示器：Element Plus 自定义 header
     插槽后内置 sort icon 丢失 -->
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
                    :form-values="mergedFormValues"
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
                  :value="getFkIdValue(row, column)"
                  :display-value="getFkDisplayValue(row, column)"
                  :target-object-type="getFkTargetObjectType(column)"
                  :link-object-type="getFkLinkObjectType(column)"
                  :link-id="getFkLinkId(row, column)"
                  :detail-mode="getFkDetailMode(column)"
                  :link-disabled="isEmbeddedOrDialogMode"
                  @navigate="handleFkNavigate"
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
                  class="bk-link bk-link--primary"
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
                  :teleported="true"
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

            <!-- [2026-10-20] 兜底详情入口列：对象无业务键列时渲染（party_relation 等薄关系
                 对象全部列 business_key=false ⇒ 表格里没有任何可点进详情的列），否则不渲染、
                 对有业务键列的对象零影响。复用 bk-link 样式与 handleBusinessKeyClick 既有分派。 -->
            <el-table-column
              v-if="showDetailEntryColumn"
              label=""
              :width="70"
              fixed="right"
              header-align="center"
              align="center"
              class-name="detail-entry-column"
            >
              <template #default="{ row }">
                <span
                  class="bk-link bk-link--primary"
                  title="查看本对象详情"
                  @click.stop="handleBusinessKeyClick(row)"
                >详情</span>
              </template>
            </el-table-column>

            <!-- [MOMP 2026-08-30] 自定义空态：未选择范围时给出明确指示，替代默认"暂无数据" -->
            <template #empty>
              <div class="list-empty-state">
                <el-icon :size="32" class="list-empty-icon"><FolderOpened /></el-icon>
                <div class="list-empty-title">{{ props.emptyText }}</div>
                <div v-if="props.emptyHint" class="list-empty-hint">{{ props.emptyHint }}</div>
              </div>
            </template>
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
      <div v-if="showPagination" class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.pageSize"
          :page-sizes="paginationConfig.pageSizes"
          :total="pagination.total"
          :layout="effectivePaginationLayout"
          :pager-count="effectivePagerCount"
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
      :initial-data="detailCreateMode ? createInitialValues : {}"
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
import { ref, computed, watch, nextTick, onMounted, onUnmounted, onActivated, markRaw, inject } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown, ArrowUp, ArrowRight, View, Edit, Delete, List, Plus, Upload, Download, Setting, Lock, MoreFilled, Document, CopyDocument, Promotion, CaretTop, CaretBottom, Sort, FolderOpened } from '@element-plus/icons-vue'
import { useMetaList, formatDate } from '@/composables/useMetaList'
import { useAssociationNavigation } from '@/composables/useAssociationNavigation'
import { useBreakpoints } from '@/composables/useBreakpoints'
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
import { metaService } from '@/services/metaService'
import { objectTypeService } from '@/services/objectTypeService'
import { useListActionStore } from '@/stores/listActionStore'
// [P1-B 2026-07-25] 接入 ActionPolicy, 替代 canDelete 硬编码状态判断
import { canPerformAction as _canPerformActionByPolicy } from '@/services/actionPolicyService'

// [FR-004] 声明组件名以支持 keep-alive include 白名单匹配
defineOptions({ name: 'MetaListPage' })

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
    validator: (v) => [null, 'locked', 'extensible', 'fullEditable'].includes(v)
  },
  externalEditing: {
    type: Boolean,
    default: null
  },
  // [MOMP 2026-08-30] 空态文案（用于"未选择范围"等场景给出明确指示，替代默认"暂无数据"）
  emptyText: {
    type: String,
    default: '暂无数据'
  },
  emptyHint: {
    type: String,
    default: ''
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
  // [FIX 2026-06-14] 排除的列 key 列表（page 模式生效，传入后从 meta columns 过滤掉指定 key）
  // 适用场景: 子对象页的 children 列表 (如 product → version) 隐藏冗余的父对象列
  excludeColumnKeys: {
    type: Array,
    default: () => []
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
  extraRowActions: {
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
  removeNewRow,
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
} = useMetaList(computed(() => props.objectType), {
  mode: 'element-plus',
  autoLoad: props.options.autoLoad !== false,
  pageSize: props.options.pageSize || 20,
  pageSizes: props.options.pageSizes || null,
  debug: props.options.debug || false,
  rowMutability: props.rowMutability,
  displayMode: props.displayMode,
  columnsOverride: props.columnsOverride,
  excludeColumnKeys: props.excludeColumnKeys,
  excludeIds: props.excludeIds,
  rowKey: props.rowKey,
  rowActionsOverride: props.rowActionsOverride,
  extraRowActions: props.extraRowActions,
  toolbarActionsOverride: props.toolbarActionsOverride,
  batchActionsOverride: props.batchActionsOverride,
  fetcher: props.options.fetcher,
  inlineEdit: props.options.inlineEdit,
  initialFilters: props.initialFilters
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

/* ==========================================================================
   [2026-10-12 移动端] 表格列降级
   窄屏下宽表格必须横向滚动才能读，390px 屏幕一次只能看到 1-2 列。
   后端 view-config 的 columns 带importance 字段，实测取值 high/medium/low
   (如 name=high、code=medium、created_at=low)，据此分级:
     - high→ 始终保留
     - medium / low → 窄屏隐藏
   无importance 的列按 low 处理(保守隐藏)，若隐藏后一列不剩则放弃降级。
   不改动 PC 端行为：isMobile 为 false 时原样返回。
   ========================================================================== */
const { isMobile } = useBreakpoints()

/* ==========================================================================
   [窄屏搜索框 placeholder 截断 2026-10-18]
   根因：placeholder 直接把全部可搜索字段名拼进来
        （`搜索 ${labels.join('/')}...`），字段数一多就顶破 280px 输入框 ——
        实测 390x844 备注区为「搜索 分类/内容/关联对象类型/创建人...」，
        文字尾部被裁掉，同时把 .toolbar 撑出多余横向滚动条、压住按钮。
   为什么不用 CSS 截断：placeholder 渲染在原生 input::placeholder 上，
        CSS 截断会连带裁掉用户已输入的文字，属功能受损。
   改为按屏宽改文案：窄屏只留首个字段名 + 数量概括，PC 端原样不变。
   ========================================================================== */
const searchPlaceholder = computed(() => {
  const labels = (searchFields.value || []).map(f => f.label)
  if (!labels.length) return ''
  if (!isMobile.value || labels.length <= 1) return `搜索 ${labels.join('/')}...`
  return `搜索 ${labels[0]} 等 ${labels.length} 项...`
})

const tableColumns = computed(() => {
  if (!isMobile.value) return visibleColumns.value
  const keep = visibleColumns.value.filter(c => c.importance === 'high')
  // 无high 列时不降级，否则表格会被清空
  return keep.length > 0 && keep.length < visibleColumns.value.length
    ? keep
    : visibleColumns.value
})

/* ==========================================================================
   [2026-10-13 移动端] 卡片列表
   为什么不用横向滚动：实测 el-table 在 390px 下 body-wrapper 的
   scrollWidth 等于 clientWidth(可滑距离 0)，而内层<table>实际宽 1865px，
   Element Plus 用 overflow:hidden 一刀切掉 → 11 列只能看到 2 列，且真机
   拖拽 scrollLeft 恒为 0。给 .el-table 加 min-width 只能让表头可滚、
   表体仍锁死(两者是独立 wrapper)，会出现表头与表体错位。故窄屏改渲染
   卡片，彻底绕开列宽问题。
   卡片结构: importance=high 的列作主标题，其余列作键值行。列集合仍取
   visibleColumns 全量（不是 tableColumns），否则卡片只剩一个标题、
   丢掉所有细节字段。

   [FIX 2026-10-13 复用方回归] 只在 displayMode==='page' 时卡片化。
   MetaListPage 有 3 类复用方，窄屏下只有整页列表该换成卡片:
     - page     独立页面(GenericObjectList / TaskCenter 等)→ 卡片
     - embedded 详情页内的关联区(ObjectPage/AssociationSection)→ 保持表格，
                它是宽内容区里的一块纵向切片，卡片会把每行撑得很高，
                且详情页本身在窄屏已是单列堆叠，再套卡片是双重放大
     - dialog   SearchHelpDialog 内嵌选择列表 → 保持表格，
                该弹窗自身已限宽到 92vw，且强依赖 el-table 的
                row-click/row-dblclick 与多选交互
   ========================================================================== */
const useCardView = computed(() => isMobile.value && props.displayMode === 'page')

/* ==========================================================================
   [2026-10-13 移动端] 分页器布局
   之前用 CSS 隐藏 .el-pagination__total/__sizes/__jump 来解决窄屏溢出，
   代价是把「共 N 条」「每页条数」全藏了——用户只剩一个孤零零的页码，
   既不知道总量也不知道自己在第几页(截图实测: 只剩 < 1 >)。
   Element Plus 的 layout 是声明式的，窄屏直接换一份更短的布局即可，
   不需要 display:none 副作用。
   保留 total(唯一的信息来源) + prev/pager/next，
   去掉 sizes(128px) 与 jumper(114px) —— 这两个是可选项，缺失不影响功能。
   ========================================================================== */
const effectivePaginationLayout = computed(() =>
  useCardView.value ? 'total, prev, pager, next' : paginationConfig.value.layout
)

// 页码按钮个数: Element Plus 默认 7，窄屏放不下，收到 5
const effectivePagerCount = computed(() => (useCardView.value ? 5 : 7))

/* [FIX 2026-10-13] 内容不足一页时不显示分页器。
   Ant Design 数据展示规范：「when the content of the page is less than one
   page, the pager will not be displayed」。窄屏一屏仅能放 3 张卡片，分页条
   白占约 64px 高度。只在卡片视图生效，PC 端分页器是重要的规模信息
   （用户据此判断数据量），不应隐藏。
   注意：useMetaList 返回的 pagination 是 reactive 对象（模板里直接用
   pagination.current），不是 ref，写 pagination.value.total 会取到
   undefined 并让整个列表区渲染中断。 */
const showPagination = computed(() =>
  useCardView.value ? pagination.total > pagination.pageSize : true
)

const cardPrimaryColumn = computed(() => {
  // 主标题优先取 businessKey(语义最准)，退化到 importance=high，再退化到第一列
  const highs = visibleColumns.value.filter(c => c.importance === 'high')
  return visibleColumns.value.find(c => isBusinessKeyColumn(c)) ||
    highs[0] ||
    visibleColumns.value[0] || null
})

const cardColumns = computed(() => {
  const primary = cardPrimaryColumn.value
  if (!useCardView.value || !primary) return []
  return visibleColumns.value.filter(c => c.prop !== primary.prop)
})

function cardPrimary(row) {
  const primary = cardPrimaryColumn.value
  return primary ? getCellDisplayValue(row, primary) : null
}

/* 卡片上的行选择：el-table 的 selection 列在卡片模式下不存在，
   需手动维护并回写给 useMetaList 的 handleSelectionChange，
   否则批量操作拿不到选中行。 */
function isCardSelected(row) {
  const key = props.rowKey || 'id'
  return selectedIds.value.has(row[key])
}

function toggleCardSelection(row, checked) {
  const key = props.rowKey || 'id'
  const next = data.value.filter(r => {
    if (r[key] === row[key]) return checked
    return selectedIds.value.has(r[key])
  })
  handleSelectionChange(next)
  emit('selection-change', next)
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

/* [2026-10-20] 无业务键列对象的兜底详情入口。
   背景：详情抽屉的唯一入口原先挂在业务键列上（表格 bk-link / 移动卡片标题）；对
   party_relation 这类"薄关系"对象（F2 §10 D6：无 name/code ⇒ 全部列 business_key=false），
   列表里没有任何可点进详情的列，抽屉内的「编辑」按钮因此永远到不了
   （用户报障"第三个 tab 没有看到可编辑"）。
   处置：无业务键列时补一个固定的行尾「详情」链接列，并让移动端卡片标题一律可点。
   有业务键列的对象行为完全不变。
   注意：不可用 `semantics.business_key` 来"造"入口 —— 该标记同时驱动
   action_executor._validate_business_key_uniqueness，会误加唯一约束。 */
const hasBusinessKeyColumn = computed(() =>
  visibleColumns.value.some(c => isBusinessKeyColumn(c))
)

const showDetailEntryColumn = computed(() =>
  enableDetailPage.value &&
  !inlineEditConfig?.enabled &&
  !hasBusinessKeyColumn.value &&
  visibleColumns.value.length > 0
)

const cardTitleOpensDetail = computed(() =>
  enableDetailPage.value &&
  (isBusinessKeyColumn(cardPrimaryColumn.value) || !hasBusinessKeyColumn.value)
)

const importContext = computed(() => ({
  version_id: contextFilters.value?.version_id || null,
  product_id: contextFilters.value?.product_id || null
}))

// 合并过滤上下文：contextFilters (version_id/product_id from MultiObjectManagementPage)
// + 当前列表的 filterValues + 已设的 headerFilterValues
// 作为 value_help 的 parameter_bindings 输入 (例如 version_id)
const mergedFormValues = computed(() => ({
  ...(contextFilters.value || {}),
  ...(filterValues.value || {})
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
// [FIX 2026-06-29] 保存当前详情行用于 title 显示 (objectType + objectName 格式)
const currentDetailRow = ref(null)
const selectedDetailId = ref(null)
const detailEditMode = ref(false)
const detailCreateMode = ref(false)
const tableKey = ref(0)

// 新建抽屉的初始值：把列表固定的父外键过滤条件（如 * _id）带入表单，
// 让「组内换算」这类关联分区的新增无需重复选择所属父对象。
const createInitialValues = computed(() => {
  const out = {}
  if (!props.initialFilters) return out
  for (const [key, val] of Object.entries(props.initialFilters)) {
    if (key.endsWith('_id') && val !== undefined && val !== null && val !== '') {
      out[key] = val
    }
  }
  return out
})

async function forceRefresh() {
  await refresh()
  tableKey.value++
}

const detailTitle = computed(() => {
  if (detailCreateMode.value) {
    return `新建 ${metaConfig.value?.name || ''}`
  }
  // [FIX 2026-06-29] 标题优先用 metaConfig.detail.title 或 metaConfig.name,
  //                  并自动追加 row.name (来自 rowActions 触发的当前行)
  //   1) 优先 metaConfig.detail.title (后端配置)
  //   2) 否则 metaConfig.name (前端元数据)
  //   3) 否则用 objectTypeService.getDetailLabel 自动产出 "关系详情"
  //   4) 追加 row.name (如果有)
  const base = metaConfig.value?.detail?.title
    || metaConfig.value?.name
    || objectTypeService.getDetailLabel(props.objectType, '')
  // 尝试从当前 currentDetailRow 获取对象名
  const targetRow = currentDetailRow.value
  const targetName = targetRow?.name || targetRow?.code || targetRow?.title || ''
  if (targetName && base) {
    return `${base} ${targetName}`
  }
  return base || '详情'
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

// [FK 2026-10-22 跳转落点口径] 优先 detail_target_bo（配置了才落到基表），
//   缺省回退 target_bo —— 与旧行为一致。
function getFkLinkObjectType(column) {
  if (!isFkColumn(column)) return ''
  return column.valueHelpConfig.source.detail_target_bo || ''
}

// [FK 2026-10-22] 落点 id 由后端 enrichment 下发（{列名}_link_id）；
//   未下发时传 undefined，让 FkLinkField 回退用 FK 原值。
function getFkLinkId(row, column) {
  const prop = column.prop
  if (!prop) return undefined
  return row[`${prop}_link_id`]
}

/**
 * 获取 FK 列对应的 ID 值（而非显示文本）
 *
 * FK 显示列（如 service_module_name）的 column.prop 是显示列名，
 * row[column.prop] 拿到的是显示文本（如"采购管理"），不能作为导航 ID。
 * 需要通过 api_param_key 或 value_help.source.value_field 推导出 FK ID 字段名，
 * 再从 row 中取实际 ID 值（如 row.service_module_id = 42）。
 */
function getFkIdValue(row, column) {
  // 1. 优先用 api_param_key（YAML 显式声明的 FK 字段映射）
  const apiParamKey = column.apiParamKey || column.api_param_key
  if (apiParamKey && row[apiParamKey] != null) {
    return row[apiParamKey]
  }

  // 2. 从 value_help.source 推导：target_bo + '_id'
  const targetBo = column.valueHelpConfig?.source?.target_bo
  if (targetBo) {
    const fkIdKey = `${targetBo}_id`
    if (row[fkIdKey] != null) {
      return row[fkIdKey]
    }
  }

  // 3. 兜底：如果 column.prop 本身就是 _id 结尾，直接用
  if (column.prop?.endsWith('_id')) {
    return row[column.prop]
  }

  // 4. 最后兜底：返回原始值（可能不正确，但保持向后兼容）
  return row[column.prop]
}

/**
 * 确定 FK 链接的详情页打开模式
 *
 * 规则：
 * 1. 目标对象类型在 YAML 中配置了 detail_mode: page → 'page'
 * 2. 当前列表自身是 drawer 模式（非 page），且目标对象类型也在
 *    MultiObjectManagementPage 的 tabs 中 → 'drawer'（在侧边打开）
 * 3. 其他情况 → 'page'（默认跳转独立页面）
 */
function getFkDetailMode(column) {
  const targetBo = column.valueHelpConfig?.source?.target_bo
  if (!targetBo) return 'page'

  // 检查目标对象类型的 view config 中是否配置了 detail_mode: page
  const targetViewConfig = metaService.getViewConfigSync(targetBo)
  if (targetViewConfig?.data?.list?.detail_mode === 'page') {
    return 'page'
  }

  // 当前列表是 drawer 模式（非 page），且目标对象类型也在同页面 tabs 中
  // → 使用 drawer 模式，在侧边打开目标对象详情
  if (!hasDetailPageRoute() && isTargetInSamePage(targetBo)) {
    return 'drawer'
  }

  // 默认：跳转独立页面
  return 'page'
}

/**
 * 判断目标对象类型是否在当前页面的 tabs 中
 * （用于 MultiObjectManagementPage 上下文中的 FK 链接）
 */
function isTargetInSamePage(targetBo) {
  // 检查 visibleColumns 中是否有该对象类型的列
  // 或通过 props.objectTypes 检查（如果父组件传入了）
  if (props.options?.objectTypes?.includes(targetBo)) {
    return true
  }
  // 检查当前 metaConfig 中是否有相关 tab 信息
  if (metaConfig.value?.tabs?.some(t => t.name === targetBo)) {
    return true
  }
  return false
}

/**
 * 处理 FK 链接的 drawer 模式导航
 * 在当前 MetaListPage 的 drawer 中打开目标对象类型的详情
 */
function handleFkNavigate({ objectType, id, displayValue }) {
  // 如果目标对象类型跟当前列表相同，直接用当前 drawer
  if (objectType === props.objectType) {
    selectedDetailId.value = id
    detailEditMode.value = false
    detailCreateMode.value = false
    showDetailDrawer.value = true
    return
  }

  // 不同对象类型：导航到独立页面（跨对象类型 drawer 需要额外支持）
  router.push({ path: `/detail/${objectType}/${id}` }).catch(() => {})
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

  // [FIX V015e 2026-07-10] 兜底清洗历史脏 enum code (legacy_null / null 字符串 / 'undefined')
  //   原 BUG: 数据库早期导入数据时, 后端对空 relation_type 写了字符串 'legacy_null' 占位.
  //     UI 走 getBadgeDisplayValue 后, rawValue='legacy_null' 不在 enum_values 里也不在 options 里,
  //     最终落到 `return rawValue` → 用户在关系类型列看到 'legacy_null'.
  //     期望: 显示 '-' (与空值一致).
  //   修复: 在最开头 (string 路径) 把这种 sentinel 值映射为 '-'.
  //   注意: 正则不能含 'a'/'g' 等字符, 否则会被 babel 误判为 regex flag (如 /...n/a/i → 'a' 无效 flag)
  //   所以 'n/a' 单独 check, 不放在字符集里.
  if (typeof rawValue === 'string') {
    const cleaned = rawValue.trim().toLowerCase()
    if (
      cleaned === 'null' ||
      cleaned === 'undefined' ||
      cleaned === 'none' ||
      cleaned === 'n/a' ||
      cleaned === 'na' ||
      /^legacy[_\s-]*null$/.test(cleaned)
    ) {
      return '-'
    }
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
  // [P1-B 2026-07-25] 委托给 actionPolicyService, 统一行级状态规则
  //   规则源: services/actionPolicyService.js#canPerformAction
  //   - locked: 禁
  //   - extensible + is_system: 禁
  //   - 其他: 允许
  const policy = _canPerformActionByPolicy(
    { key: 'delete' },
    row,
    { rowMutability: props.rowMutability }
  )
  return policy.allowed
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
  currentDetailRow.value = null  // [FIX 2026-06-29] 清空 current row
  showDetailDrawer.value = true
}

function openDetailDrawer(row, editMode = false) {
  detailCreateMode.value = false
  selectedDetailId.value = row.id
  currentDetailRow.value = row  // [FIX 2026-06-29] 保存当前行供 title 使用
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

  const targetId = deleteTargetRow.value.id
  // [FIX 2026-06-13] 未保存的新行 (_isNew=true / __new_xxx) 走本地移除,
  // 不能调 boService.delete, 否则会触发 404/500 (BEFORE FIX BUG)
  const isNewRow = deleteTargetRow.value._isNew === true ||
                   (typeof targetId === 'string' && targetId.startsWith('__new_'))

  deleteLoading.value = true
  try {
    if (isNewRow) {
      // 本地移除新行 (useMetaList 提供的 API)
      const removed = removeNewRow(targetId)
      if (removed) {
        message.deleted('数据')
      } else {
        // 兜底：理论上不会出现 (isNewRow 已先判断过)
        message.info('已取消该新增行')
      }
      showDeleteConfirm.value = false
      deleteTargetRow.value = null
      return
    }

    const result = await boService.delete(props.objectType, targetId)
    if (result.success) {
      message.deleted('数据')
      showDeleteConfirm.value = false
      deleteTargetRow.value = null
      await forceRefresh()
    } else {
      message.deleteFailed('数据')
    }
  } catch (e) {
    message.deleteFailed('数据')
  } finally {
    deleteLoading.value = false
  }
}

const isExternallyControlled = computed(() => props.externalEditing !== null)

const isPageMode = computed(() => props.displayMode === 'page')

const isEmbeddedOrDialogMode = computed(() =>
  props.displayMode === 'dialog' || props.displayMode === 'embedded'
)

// page 模式：height="100%" 填满容器（依赖外层 flex 布局给出确定高度）
// dialog/embedded 模式：返回 null，使用 max-height
const tableHeight = computed(() => {
  if (isEmbeddedOrDialogMode.value) {
    return null
  }
  return '100%'
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

// [NFR-007] 同时 watch data 和 columns，确保 objectType 变化后两者都更新再 doLayout
// [FIX v20 2026-08-26] 使用 row[config.rowKey] 而非 row.id，保证与 rowKey 配置一致
//   - 修复: SearchHelpDialog 用 :row-key="'value'" 但 selectedIds 中存的是 row.value
//     原代码用 row.id === row.value（巧合相等）能跑；但 rowKey 改为 'value' 后应保持一致
watch([data, columns], () => {
  nextTick(() => {
    // [FIX 2026-10-13] 卡片模式下 el-table 不渲染，tableRef 为 null。
    // 原代码只对 doLayout 做了 null 判断，下面的 toggleRowSelection
    // 是裸调用 —— 一旦卡片模式下有选中行且 data/columns 变化就会抛
    // TypeError。此处统一 early return：卡片的选择态由 isCardSelected
    // 直接读 selectedIds 渲染，不需要回写 el-table。
    if (!tableRef.value) return
    tableRef.value.doLayout()
    if (selectedIds.value.size === 0) return
    const rowKey = config.rowKey || 'id'
    data.value.forEach(row => {
      const rowKeyValue = row[rowKey]
      const isSelected = rowKeyValue != null && selectedIds.value.has(rowKeyValue)
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

// [FIX 2026-06-30] 监听 initialFilters 变化, 重新应用过滤并刷新数据
//   之前只在 onMounted 应用一次, scope tree 勾选后 Tab 不刷新 → 显示全部
watch(() => props.initialFilters, (newFilters) => {
  if (!newFilters || Object.keys(newFilters).length === 0) return
  setContextFilters(newFilters)
  if (props.options.autoLoad !== false) {
    refresh()
  }
}, { deep: true })

// [FR-004] 路由级 keep-alive 恢复时刷新数据
// [FR-005] SAP Fiori iAppState 模式：路由切回时保留状态，不自动刷新
// 数据变更由 refreshCoordinator 处理，用户可手动点刷新按钮
onActivated(() => {
  if (props.objectType) {
    console.log(`[MetaListPage] onActivated: objectType=${props.objectType}, state preserved (no auto-refresh)`)
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

// [NFR-005] objectType 变化时重新注册事件处理器
watch(() => props.objectType, (newType, oldType) => {
  if (newType === oldType) return

  // 注销旧 objectType 的处理器
  if (unsubscribeAction) {
    unsubscribeAction()
  }
  if (coordinator) {
    coordinator.unregister(`list:${oldType}`)
  }

  // 注册新 objectType 的处理器
  unsubscribeAction = useListActionStore().registerHandler(newType, handleMetaListAction)
  if (coordinator) {
    coordinator.register(`list:${newType}`, forceRefresh)
  }

  // 重新加载权限
  loadPermissions()
})

// [FIX BUG-V015b 2026-06-26] 兜底：监听 window 事件总线
// 原 BUG: GenericObjectList 没 provide refreshCoordinator,
//        ObjectDetailPage.handleSaved 拿不到 coordinator → 无法通知 list 刷新.
// 修复: 即便没 coordinator, 也监听 'excel-diagram:list-refresh' 事件,
//       收到事件后 forceRefresh. 这是 GenericObjectList 路径的唯一可用机制.
const _windowEventHandler = (evt) => {
  const targetType = evt.detail?.objectType
  if (!targetType || targetType === props.objectType) {
    console.debug('[MetaListPage] excel-diagram:list-refresh → forceRefresh', evt.detail)
    forceRefresh()
  }
}
onMounted(() => {
  window.addEventListener('excel-diagram:list-refresh', _windowEventHandler)
})
onUnmounted(() => {
  window.removeEventListener('excel-diagram:list-refresh', _windowEventHandler)
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
  // [FIX 2026-06-29] 暴露 onRowAction 让 MOMP/GenericObjectList 等父组件可在 dblclick 时触发 action
  onRowAction,
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
  /**
   * [FIX 2026-06-14] 外部设置搜索关键词 (避免 ref 通过 defineExpose 被自动 unwrap 后无法赋值)
   * AssignmentDialog 等 dialog 模式下需要外部搜索框联动 MetaListPage 内部 keyword
   */
  setKeyword(value) {
    keyword.value = value ?? ''
  },
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
  /* [FIX 2026-06-20] 用 flex:1 + min-height:0 替代 height:100%
     在 flex 容器中 height:100% 不可靠, flex:1 让元素填满剩余空间 */
  flex: 1;
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
  background: var(--color-bg-container);
  /* [FIX 2026-06-12] Root-cause fix #9: 去掉 border-bottom 让 toolbar 和 table
     完全无缝衔接（之前是 1px solid #ebeef5 让两者看起来像独立的卡片） */
  border-bottom: none;
  overflow-x: auto;
  min-height: 44px;
  position: relative; /* Lock positioning context (2026-06-09 regression fix) */
  flex-shrink: 0;
  /* [FIX 2026-06-20 T-2026-06-20-002-v2] Sticky toolbar (SAP Dynamic Page Layout) - 滚动时工具栏吸顶 */
  position: sticky;
  top: 0;
  z-index: 10;
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

/* ==========================================================================
   [2026-10-12 移动端适配] ≤768px
   注意：.meta-list-page 的 overflow:hidden 与 .toolbar 的 flex-wrap:nowrap
   是2026-06-09 为修PC 端工具栏漂移回归刻意保留的
   (docs/lessons-learned/layout/toolbar-drift-recurrence.md)，
   故本段只在窄屏断点内覆盖，不动 PC 行为。
   问题：窄屏下 overflow:hidden 让宽表格被直接裁掉，数据不可见；
         工具栏 nowrap 使按钮只能横滑，出货率低。
   [FIX 2026-10-13] 本段原先写在 .toolbar 基础样式之前，同优先级下
   被后面的 nowrap / flex:1 / flex-shrink:0 全部覆盖，实测 wrap 仍为
   nowrap、按钮溢出屏幕。故移到基础样式之后定义。
   ========================================================================== */
@media screen and (max-width: 768px) {
  .meta-list-page {
    /* 表格需要横向滚动才能读，裁切比滚动更糟 */
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .toolbar {
    /* 窄屏允许换行，避免只能横滑发现隐藏按钮 */
    flex-wrap: wrap;
    height: auto;
  }

  /* 换行后两侧各占整行，按钮自然铺开。
     flex 必须用简写整体覆盖：基础样式里 .toolbar-left 是 flex:1、
     .toolbar-right 是 flex-shrink:0，只改单个子属性会被残留项
     拉成 0 宽或禁收缩，故此处统一用 flex 简写重置。 */
  .toolbar-left,
  .toolbar-right {
    flex: 1 1 100%;
    /* 容器内部也要换行：搜索框 280px + 4 个按钮 ≈ 565px，
       390px 屏放不下，nowrap 会挤成横滑 */
    flex-wrap: wrap;
    gap: 8px;
  }

  /* [窄屏按钮行多余滚动条 2026-10-18] 关掉按钮行的横向滚动。
     根因（实测 390x844 内嵌备注区）：上面已用 flex-wrap:wrap 让按钮换行，
     但基础样式 .toolbar / .toolbar-left 上的 overflow-x:auto 没有被覆盖
     （那段窄屏规则只改了 flex-wrap，漏了 overflow-x）⇒ 换行后浏览器仍判定
     内容溢出，划出一条没有任何可滚动内容的滚动条。
     典型症状：备注区只有「添加备注」1 个按钮（宽约 110px，容器 340px，
     根本放不下），却出现横向滚动条并压住按钮下半部分。
     为什么用 hidden 而非 visible：flex 容器上 overflow-x:visible 会连带把
     overflow-y 变成 auto，可能在无意的纵向溢出时凭空多出滚动条。
     注意：.meta-list-page 的 overflow-x:auto 必须保留 —— 它是表格横向
     滚动的唯一来源（见上方注释），删了窄屏就读不到宽表格。 */
  .toolbar,
  .toolbar-left {
    overflow-x: hidden;
  }

  /* [窄屏搜索框被裁 2026-10-18] 让输入框吃掉整行宽度，不再被裁掉右边框。
     根因：模板给 el-input 写了内联 style="width:280px"，而基础样式
     .search-field 又是 flex-shrink:0 —— 两者叠加使输入框既固定 280px
     又拒绝收缩；390px 屏的备注区容器实测仅约 340px，扣掉工具栏 padding
     后放不下，右侧边框被 overflow-x:hidden 直接裁掉。
     为什么需要 !important：内联样式优先级高于任何非 !important 的类选择器，
     不加则这条规则完全无效。
     为什么给 min-width:0：flex 子项默认 min-width:auto，内容（el-input）过宽时
     会拒绝收缩回容器宽度，即使设了 flex:1 也压不下来。 */
  .toolbar .search-field {
    flex: 1 1 100%;
    min-width: 0;
  }

  .toolbar .search-field :deep(.el-input) {
    width: 100% !important;
  }

  /* [窄屏按钮间距 2026-10-17] 去掉 Element Plus 相邻按钮的默认 margin-left。
     根因：gap 与 EP 全局 `.el-button + .el-button { margin-left: 12px }` 叠加，
     实测相邻按钮实际间距 = 8 + 12 = 20px（不是本规则声明的 8px）。
     390px 屏下 toolbar-left 内容区实测 310px，「往来单位组」tab 的按钮组需
     108(新建往来单位组) + 20 + 48(搜索) + 20 + 48(重置) + 20 + 69(更多) = 333px
     ⇒ 「更多」被挤到第三行，同一页面里只有这一个 tab 多占一行（文案的锅被间距放大）。
     去掉冗余 margin 后按 gap 8px 计：108+8+48+8+48+8+69 = 297 ≤ 310 ⇒ 一行放下。
     仅在窄屏生效，桌面端保持原有间距。 */
  .toolbar-left :deep(.el-button + .el-button),
  .toolbar-right :deep(.el-button + .el-button) {
    margin-left: 0;
  }

  /* [窄屏工具条底部空档 2026-10-17] 空 toolbar-right 不再占一整行。
     根因（实测 390x844）：.toolbar-right 有 v-if 容器但内容可全空（inlineEditConfig 未启用
       时其下所有按钮的 v-if 均不成立）。窄屏下它和 .toolbar-left 一样是 flex:1 1 100%，
       高度为 0 却仍触发父级 gap:12px ⇒ toolbar 实测高 92px
       = padding 8 + toolbar-left 64 + gap 12 + 空 right 0 + padding 8，
       底部凭空多出 20px（12 gap + 8 padding），视觉上就是「tab 下方与列表区域距离很大」。
     桌面端无需此修：那里 toolbar-right 是 flex-shrink:0 且父级 nowrap，空元素不换行、不占高。
     :has() 不支持时规则整条失效，退回现状（仅多 12px，无功能影响）。 */
  .toolbar-right:not(:has(> *)) {
    display: none;
  }

  /* [FIX 2026-10-13] 分页器溢出到屏幕外。
     实测 374px 容器里分页器自身宽 561px，父级 nowrap + 居中导致整块
     溢出后 x=-195。改为窄屏换用更短的 layout(见 effectivePaginationLayout)，
     这里只需允许换行并居中，不再需要隐藏子块 —— 隐藏会把「共 N 条」
     也一起藏掉，用户就完全不知道总量了。 */
  .pagination-wrapper {
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
  }

  /* [FIX 2026-10-24 窄屏分页器左侧被裁]
     实测 390 宽：el-pagination 实宽 362px（total 58 + prev 32/左距 16 + pager 216
     + next 32/左距 4），容器仅 358px；360 宽机型容器 328px ⇒ 居中溢出后
     左侧「共 282 条」被卡片裁成「2 条」。
     收紧按钮尺寸与间距（32→28、li 左右 2px→0、prev 左距 16→0、total 12px），
     实测 390 宽降到 306px、360 宽 296px（容器 328px），均可一行放下；
     320 宽再靠下面的 el-pagination 自身换行兜底。 */
  .pagination-wrapper :deep(.el-pagination) {
    /* ≤320 宽（容器 288px）时整条仍差 18px，允许自身换行并限宽，
       total 独占一行，页码组落到第二行，不再溢出到卡片外被裁。 */
    flex-wrap: wrap;
    justify-content: center;
    row-gap: 4px;
    max-width: 100%;
  }

  .pagination-wrapper :deep(.el-pagination__total) {
    font-size: 12px;
  }

  .pagination-wrapper :deep(.btn-prev) {
    margin-left: 0;
  }

  .pagination-wrapper :deep(.btn-prev),
  .pagination-wrapper :deep(.btn-next),
  .pagination-wrapper :deep(.el-pager li) {
    min-width: 28px;
    height: 28px;
    font-size: 12px;
  }

  .pagination-wrapper :deep(.el-pager li) {
    margin: 0;
  }
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
  /* [FIX 2026-06-20 T-2026-06-20-002] 限制高度 + 内部滚动 (解决"过滤区域没下限"问题: 内容多时撑很长) */
  max-height: 240px;
  overflow-y: auto;
  /* [FIX 2026-06-20 T-2026-06-20-002] Sticky filter (SAP Dynamic Page Layout) - 滚动时吸顶在 toolbar 下方 */
  position: sticky;
  top: 44px;
  z-index: 9;

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

/* ==========================================================================
   [2026-10-13 移动端] 卡片列表
   替代 el-table 在窄屏的渲染。键值行用 dl/dt/dd 语义(标题-值对)，
   label 固定 88px 左对齐，value 占据剩余宽度并允许换行——长文本不再被
   裁切或叠字。整卡可点区域留给标题与行菜单，不给整卡绑点击，避免与
   勾选框、行内链接冲突。
   ========================================================================== */
.meta-card-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: var(--spacing-sm);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.meta-card {
  background: var(--color-bg-container);
  border: 1px solid var(--color-border-light, #ebeef5);
  border-radius: var(--border-radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
}

.meta-card.is-selected {
  border-color: var(--color-primary, #409eff);
  background: var(--color-primary-light-9, #ecf5ff);
}

.meta-card__head {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.meta-card__check {
  flex-shrink: 0;
}

.meta-card__title {
  flex: 1;
  min-width: 0;
  font-weight: 500;
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  /* 长名称换行显示而非裁切 */
  word-break: break-word;
  line-height: 1.4;
}

/* [FIX 2026-10-13] 标题作为唯一详情入口，必须一眼可辨。
   用 button 元素是为了天然具备键盘可达性与 focus 样式，
   故需重置 UA 默认的边框/背景/字体对齐。 */
.meta-card__title--link {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  margin: 0;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: var(--color-primary, #409eff);
  text-align: left;
  cursor: pointer;
}

.meta-card__title-text {
  flex: 1;
  min-width: 0;
  word-break: break-word;
}

/* 箭头跟文字同色但更淡，暗示"可进入"而非独立控件 */
.meta-card__title-arrow {
  flex-shrink: 0;
  margin-top: 4px;
  opacity: 0.55;
}

.meta-card__title--link:hover .meta-card__title-arrow {
  opacity: 1;
}

.meta-card__title--link:focus-visible {
  outline: 2px solid var(--color-primary, #409eff);
  outline-offset: 2px;
  border-radius: 2px;
}

.meta-card__menu {
  flex-shrink: 0;
}

.meta-card__body {
  margin: var(--spacing-sm) 0 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.meta-card__row {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
}

.meta-card__label {
  flex-shrink: 0;
  width: 88px;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: 20px;
}

.meta-card__value {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  line-height: 20px;
  /* 关键修复：表格模式下长内容会溢出并叠字，卡片里允许正常换行 */
  word-break: break-word;
  white-space: normal;
}

/* [MOMP 2026-08-30] 空态提示：未选择范围时给出明确指示 */
.list-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  gap: 8px;
  color: var(--color-text-tertiary);
}

.list-empty-state .list-empty-icon {
  color: var(--color-text-quaternary, #c0c4cc);
}

.list-empty-state .list-empty-title {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.list-empty-state .list-empty-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
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
/* [UX 2026-06-21] 默认隐藏，hover 列头时显示，激活态常驻 */
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
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease;
}
/* hover 列头时显示排序图标 */
.column-header:hover .sort-indicator {
  opacity: 1;
}
/* hover 列头时显示过滤图标 (子组件 TableHeaderFilter) */
.column-header:hover :deep(.filter-trigger) {
  opacity: 0.6;
}
/* 过滤激活态：常驻显示，不受 hover 影响 */
.column-header :deep(.filter-trigger.is-active) {
  opacity: 1;
}
/* hover 图标本身：全显 + 背景 */
.column-header :deep(.filter-trigger:hover) {
  opacity: 1;
  background-color: rgba(64, 158, 255, 0.15);
}
/* 排序激活态：常驻显示，不受 hover 影响 */
.sort-indicator.is-asc,
.sort-indicator.is-desc {
  opacity: 1;
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
  /* 业务键链接：与原版一致使用黑色文本，hover 用 primary 强调 */
  color: var(--color-text-primary);
  cursor: pointer;
  transition: color 0.15s ease, text-decoration 0.15s ease;
}

.bk-link:hover {
  color: var(--color-primary);
  text-decoration: underline;
}

/* [FIX 2026-06-16] 业务键(主key) 高亮：YonDesign primary 橙色，font-weight 500 */
.bk-link--primary {
  color: var(--color-primary);
  font-weight: 500;
}

.bk-link--primary:hover {
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

  /* [FIX 2026-10-14 embedded 模式分页器被顶出视口]
     原 flex:none → table-section 取 el-table 的 max-height 固定 420px，
     遇到同页还有其它固定高区块时必然放不下：审计日志页概览区 326~385px，
     900px 视口下 768-326-420 = 22px 余量，meta-list-page 被压到 283px
     而内容 513px → 溢出 230px 把 49px 分页器顶到视口外（360px 屏需下滚 173px）。
     改 0 1 auto：仍不主动拉伸（保持 compact 紧凑观感），但允许在空间
     不足时收缩，溢出归零、分页器常驻底部。min-height 保底避免被压成 0。 */
  .table-section {
    flex: 0 1 auto;
    min-height: 160px;
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
