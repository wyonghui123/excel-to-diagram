<template>
  <div class="stats-display">
    <table class="stats-table">
      <thead>
        <tr>
          <th></th>
          <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.key">
          <td class="row-label">{{ row.label }}</td>
          <td v-for="col in columns" :key="col.key" class="stat-cell">
            <span :class="['stat-value', { highlight: row.key === 'center' }]">
              {{ getStatValue(row.key, col.key) }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script>
export default {
  name: 'StatsDisplay',
  props: {
    stats: {
      type: Object,
      required: true,
      validator: (stats) => {
        return stats.import !== undefined &&
               stats.center !== undefined &&
               stats.external !== undefined &&
               stats.total !== undefined
      }
    }
  },
  setup(props) {
    const columns = [
      { key: 'domains', label: '领域' },
      { key: 'subDomains', label: '子领域' },
      { key: 'serviceModules', label: '服务模块' },
      { key: 'businessObjects', label: '业务对象' },
      { key: 'objectRelations', label: '业务对象关系' }
    ]

    const rows = [
      { key: 'import', label: '导入' },
      { key: 'center', label: '中心范围' },
      { key: 'external', label: '外部关联' },
      { key: 'total', label: '选择总数' }
    ]

    const getStatValue = (rowKey, colKey) => {
      const rowData = props.stats[rowKey]
      if (!rowData) return 0
      return rowData[colKey] || 0
    }

    return {
      columns,
      rows,
      getStatValue
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.stats-display {
  width: 100%;
}

.stats-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);

  th, td {
    padding: 8px 12px;
    text-align: center;
    border: 1px solid #e8e8e8;
  }

  th {
    background: #fafafa;
    font-weight: 600;
    color: #333;
  }

  .row-label {
    text-align: left !important;
    font-weight: 600;
    background: #fafafa;
    color: #333;
    width: 100px;
  }

  .stat-cell {
    min-width: 80px;
  }

  .stat-value {
    font-weight: 500;
    color: #666;

    &.highlight {
      color: #1890ff;
      font-weight: 700;
    }
  }

  tr:hover {
    background: #f5f5f5;
  }
}
</style>
