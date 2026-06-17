<template>
  <MultiObjectManagementPage
    ref="pageRef"
    :object-types="objectTypes"
    :options="pageOptions"
    @toolbar-action="handleToolbarAction"
  >
    <template #tabsExtra="{ context }">
      <div v-if="context.filters.length" class="rm-tabs-extra">
        <el-tag
          v-for="filter in context.filters"
          :key="filter.key"
          type="info"
          size="small"
          closable
          class="rm-filter-tag"
          @close="context.clearFilter(filter.key)"
        >
          {{ filter.label }} {{ filter.count }}
        </el-tag>
        <el-button type="primary" link size="small" @click="context.clear">清空</el-button>
      </div>
    </template>

    <template #cell-source_bo_name="{ row }">
      <div class="bo-cell">
        <span class="bo-name">{{ row.source_bo_name }}</span>
        <span class="bo-code">({{ row.source_code }})</span>
      </div>
    </template>

    <template #cell-target_bo_name="{ row }">
      <div class="bo-cell">
        <span class="bo-name">{{ row.target_bo_name }}</span>
        <span class="bo-code">({{ row.target_code }})</span>
      </div>
    </template>

    <template #cell-category_label="{ row }">
      <el-tag
        :type="getCategoryTagType(row.category_type)"
        size="small"
      >
        {{ row.category_label }}
      </el-tag>
    </template>
  </MultiObjectManagementPage>
</template>

<script setup>
import { ref } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'

defineOptions({ name: 'RelationshipManagement' })

const objectTypes = ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']
const pageOptions = { defaultTab: 'relationship' }
const pageRef = ref(null)

function getCategoryTagType(categoryType) {
  return ''
}

function handleToolbarAction(action) {
  switch (action) {
    case 'refresh':
      pageRef.value?.refresh()
      break
  }
}
</script>

<style lang="scss" scoped>
.bo-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.bo-name {
  color: var(--color-text-primary);
}

.bo-code {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

:deep(.el-table) {
  .bo-cell {
    .bo-name {
      font-weight: 500;
    }
  }
}

.rm-tabs-extra {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 16px;
}

.rm-filter-tag {
  border-radius: 4px;
}
</style>
