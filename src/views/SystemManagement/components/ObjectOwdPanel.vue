<template>
  <AppCard
    title="对象级基线（OWD）"
    subtitle="每个对象类型的默认可见性（仅全局管理员可改）"
    class="owd-panel"
  >
    <el-table
      :data="props.owdList"
      size="small"
      stripe
      :empty-text="emptyText"
      data-test="owd-table"
    >
      <el-table-column prop="bo_id" label="对象类型" width="160">
        <template #default="{ row }">
          <span class="owd-bo-id">{{ row.bo_id || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="default_visibility" label="默认可见性" width="180">
        <template #default="{ row }">
          <el-tag
            :type="visibilityTagType(row.default_visibility)"
            size="small"
            effect="light"
          >
            {{ visibilityLabel(row.default_visibility) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="default_permission_level" label="默认权限级别" width="160">
        <template #default="{ row }">
          {{ permissionLevelLabel(row.default_permission_level) }}
        </template>
      </el-table-column>
      <el-table-column prop="description" label="说明" min-width="220">
        <template #default="{ row }">
          <span class="owd-desc">{{ row.description || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>
  </AppCard>
</template>

<script setup>
import { computed } from 'vue'
import AppCard from '@/components/common/AppCard/AppCard.vue'

// [Spec 21 FR-005 2026-09-12]
// 只读展示 OWD 基线；编辑入口是 P3 spec 范围，本组件不提供
const props = defineProps({
  owdList: {
    type: Array,
    default: () => [],
  },
})

const VISIBILITY_MAP = {
  private: { label: '仅 owner 可见', type: 'info' },
  public_read: { label: '公开读', type: 'success' },
  public_read_write: { label: '公开读写', type: 'warning' },
  controlled_by_parent: { label: 'Controlled by Parent', type: '' },
}
const LEVEL_MAP = {
  none: 'none（无默认授权）',
  read: 'read（默认可读）',
  write: 'write（默认可写）',
  admin: 'admin（默认可管理）',
}

function visibilityLabel(v) {
  if (!v) return '-'
  return VISIBILITY_MAP[v]?.label || v
}
function visibilityTagType(v) {
  return VISIBILITY_MAP[v]?.type || ''
}
function permissionLevelLabel(l) {
  if (!l) return '-'
  return LEVEL_MAP[l] || l
}

const emptyText = computed(() => '未配置 OWD（系统将按 Private + none 兜底）')
</script>

<style scoped>
.owd-panel {
  margin-bottom: var(--spacing-md, 12px);
}
.owd-bo-id {
  font-family: var(--font-family-mono, 'JetBrains Mono', Consolas, monospace);
  font-size: 12px;
  color: var(--color-text-primary, #1f2937);
}
.owd-desc {
  color: var(--color-text-secondary, #6b7280);
  font-size: 12px;
}
</style>
