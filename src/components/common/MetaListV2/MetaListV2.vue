<!--
  MetaListV2 - 基于 el-table-v2 的高性能虚拟滚动列表
  [FR-005] 渐进式虚拟滚动组件

  设计目标:
  - 替换 el-table 处理 1000+ 行数据
  - 仅渲染可见区域,支持 60fps 滚动
  - 与现有 MetaListPage 兼容: columns/data props 风格一致
  - 支持排序、选择 (基础)
  - 支持自定义单元格 slot

  使用方式:
  <MetaListV2
    :columns="columns"
    :data="tableData"
    :width="1000"
    :height="600"
    :loading="loading"
    @row-click="onRowClick"
  />

  迁移建议:
  - MetaListPage.vue 的 <el-table> → MetaListV2
  - <el-table-column> 子节点 → columns 数组配置
  - 分页: el-table-v2 不分页,大数据量时用滚动+过滤
-->
<template>
  <div class="meta-list-v2" :style="containerStyle">
    <div v-if="loading" class="meta-list-v2__loading">
      <slot name="loading">
        <div class="meta-list-v2__loading-default">加载中…</div>
      </slot>
    </div>
    <ElTableV2
      v-else
      :columns="v2Columns"
      :data="data"
      :width="width"
      :height="height"
      :row-height="rowHeight"
      :header-height="headerHeight"
      :row-key="rowKey"
      :sort-by="sortBy"
      :default-sort-order="defaultSortOrder"
      @row-click="handleRowClick"
      @column-sort="handleSort"
    >
      <template v-for="(_, name) in $slots" #[name]="slotData">
        <slot :name="name" v-bind="slotData" />
      </template>
    </ElTableV2>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElTableV2 } from 'element-plus'

/**
 * @typedef {Object} MetaColumn
 * @property {string} prop         - 字段名
 * @property {string} label        - 表头
 * @property {number} [width]      - 列宽
 * @property {boolean} [sortable]  - 是否可排序
 * @property {string} [align]      - 对齐方式
 * @property {(row, column) => *} [formatter] - 格式化函数
 * @property {string} [slot]       - 自定义单元格 slot 名
 * @property {string} [fixed]      - 固定列 (left/right)
 */

const props = defineProps({
  /** 表格数据 */
  data: { type: Array, default: () => [] },
  /** 列配置 @type {MetaColumn[]} */
  columns: { type: Array, required: true },
  /** 表格宽度 (必须) */
  width: { type: Number, required: true },
  /** 表格高度 (必须) */
  height: { type: Number, required: true },
  /** 行高 (默认 50) */
  rowHeight: { type: Number, default: 50 },
  /** 表头高度 (默认 50) */
  headerHeight: { type: Number, default: 50 },
  /** 行 key 字段 */
  rowKey: { type: String, default: 'id' },
  /** 加载中 */
  loading: { type: Boolean, default: false },
  /** 默认排序字段 */
  sortBy: { type: String, default: '' },
  /** 默认排序方向 */
  defaultSortOrder: { type: String, default: 'asc' },
})

const emit = defineEmits(['row-click', 'sort-change'])

const containerStyle = computed(() => ({
  width: `${props.width}px`,
  height: `${props.height}px`,
  position: 'relative',
}))

/**
 * 将自定义 columns 转换为 el-table-v2 期望的格式
 * v2 格式: { key, title, width, sortable, align, fixed, dataKey, renderCell }
 */
const v2Columns = computed(() => {
  return props.columns.map((col) => ({
    key: col.prop,
    dataKey: col.prop,
    title: col.label,
    width: col.width || 120,
    align: col.align || 'left',
    sortable: col.sortable || false,
    fixed: col.fixed || false,
    // 渲染函数: 优先用 slot,其次用 formatter,最后用原值
    cellRenderer: ({ rowData, rowIndex, column }) => {
      if (col.slot) {
        return { __slot: col.slot, row: rowData, rowIndex, column }
      }
      const value = rowData?.[col.prop]
      if (col.formatter) {
        return col.formatter(value, rowData, column)
      }
      return value
    },
  }))
})

function handleRowClick(row) {
  emit('row-click', row)
}

function handleSort(payload) {
  emit('sort-change', payload)
}
</script>

<style scoped>
.meta-list-v2 {
  position: relative;
  overflow: hidden;
}

.meta-list-v2__loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.7);
  z-index: 10;
}

.meta-list-v2__loading-default {
  padding: 8px 16px;
  background: var(--el-color-primary-light-9, #fff7ed);
  border: 1px solid var(--el-color-primary-light-5, #fdba74);
  border-radius: 4px;
  color: var(--el-color-primary, #ea580c);
  font-size: 14px;
}
</style>
