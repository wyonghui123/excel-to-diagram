<template>
  <div class="association-cell">
    <template v-if="displayMode === 'count'">
      <el-link
        v-if="count > 0"
        type="primary"
        :underline="false"
        @click="handleClick"
      >
        <el-badge :value="count" class="association-badge">
          <span class="association-label">{{ label }}</span>
        </el-badge>
      </el-link>
      <span v-else class="association-empty">未分配</span>
    </template>

    <template v-else-if="displayMode === 'tags'">
      <div v-if="items.length" class="association-tags">
        <el-tag
          v-for="item in visibleItems"
          :key="item.id"
          type="primary"
          size="small"
          class="association-tag"
          @click="handleItemClick(item)"
        >
          {{ item.name || item.display_name || item.code || item.id }}
        </el-tag>
        <el-link
          v-if="items.length > maxTags"
          type="primary"
          :underline="false"
          class="more-link"
          @click="handleClick"
        >
          +{{ items.length - maxTags }}
        </el-link>
      </div>
      <span v-else class="association-empty">未分配</span>
    </template>

    <template v-else-if="displayMode === 'names'">
      <span v-if="names" class="association-names">{{ names }}</span>
      <span v-else class="association-empty">未分配</span>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  row: {
    type: Object,
    required: true
  },
  column: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['navigate'])

const displayMode = computed(() => props.column.displayMode || 'count')
const associationKey = computed(() => props.column.association || props.column.prop)
const maxTags = computed(() => props.column.maxTags || 2)

const items = computed(() => {
  const key = associationKey.value
  const val = props.row[key]
  if (Array.isArray(val)) return val
  if (val && Array.isArray(val.items)) return val.items
  return []
})

const count = computed(() => {
  const key = associationKey.value + '_count'
  if (props.row[key] !== undefined) return props.row[key]
  return items.value.length
})

const label = computed(() => {
  const cfg = props.column.navigateTo
  return cfg?.title || props.column.label || '查看'
})

const visibleItems = computed(() => items.value.slice(0, maxTags.value))

const names = computed(() => {
  return items.value.map(i => i.name || i.display_name || i.code).join(', ')
})

function handleClick() {
  const cfg = props.column.navigateTo
  if (!cfg) return
  emit('navigate', {
    objectType: cfg.objectType,
    filterField: cfg.filterField,
    rowId: props.row.id,
    title: cfg.title || props.column.label
  })
}

function handleItemClick(item) {
  const cfg = props.column.navigateTo
  if (!cfg) return
  emit('navigate', {
    objectType: cfg.objectType,
    filterField: cfg.filterField,
    rowId: props.row.id,
    targetId: item.id,
    title: cfg.title || props.column.label,
    item
  })
}
</script>

<style scoped lang="scss">
.association-cell {
  display: flex;
  align-items: center;
}

.association-badge {
  :deep(.el-badge__content) {
    font-size: 10px;
    height: 16px;
    line-height: 16px;
    padding: 0 5px;
  }
}

.association-label {
  font-size: 13px;
}

.association-empty {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

.association-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.association-tag {
  cursor: pointer;
}

.more-link {
  font-size: 12px;
  margin-left: 2px;
}

.association-names {
  color: var(--el-text-color-primary);
  font-size: 13px;
}
</style>
