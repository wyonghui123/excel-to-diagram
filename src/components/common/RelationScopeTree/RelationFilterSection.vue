<template>
  <div class="relation-filter-section">
    <div class="rfs-group">
      <div class="rfs-group-header">
        <span class="rfs-group-label">备注类型 <span class="rfs-scope-hint">(全局)</span></span>
      </div>
      <el-select
        v-model="selectedAnnotations"
        multiple
        collapse-tags
        collapse-tags-tooltip
        :max-collapse-tags="2"
        filterable
        clearable
        placeholder="请选择备注类型"
        size="small"
        class="rfs-select"
        @change="handleAnnotationChange"
      >
        <el-option
          v-for="opt in annotationOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </div>

    <div class="rfs-group" :class="{ 'rfs-group-disabled': relationDisabled }">
      <div class="rfs-group-header">
        <span class="rfs-group-label">
          关系类型 
          <span v-if="relationDisabled" class="rfs-scope-hint">(仅关系页)</span>
        </span>
      </div>
      <el-select
        v-model="selectedRelations"
        multiple
        collapse-tags
        collapse-tags-tooltip
        :max-collapse-tags="2"
        filterable
        clearable
        placeholder="请选择关系类型"
        size="small"
        class="rfs-select"
        :disabled="relationDisabled"
        @change="handleRelationChange"
      >
        <el-option
          v-for="opt in relationOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <div v-if="relationDisabled" class="rfs-disabled-hint">
        切换到"关系"Tab 后可用
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import EnumService from '@/services/enumService'

const props = defineProps({
  versionId: {
    type: Number,
    default: null
  },
  relationDisabled: {
    type: Boolean,
    default: false
  },
  initialAnnotations: {
    type: Array,
    default: () => []
  },
  initialRelations: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['filter-change', 'load'])

const selectedAnnotations = ref([])
const selectedRelations = ref([])
const annotationOptions = ref([])
const relationOptions = ref([])
const loading = ref(false)

const filterCount = computed(() => {
  const annotationSelected = selectedAnnotations.value.length
  const relationSelected = selectedRelations.value.length
  const annotationTotal = annotationOptions.value.length
  const relationTotal = relationOptions.value.length
  
  let count = 0
  if (annotationSelected > 0 && annotationSelected < annotationTotal) count += 1
  if (relationSelected > 0 && relationSelected < relationTotal) count += 1
  return count
})

const annotationCount = computed(() => {
  const selected = selectedAnnotations.value.length
  const total = annotationOptions.value.length
  if (selected > 0 && selected < total) return selected
  return 0
})

const relationCount = computed(() => {
  const selected = selectedRelations.value.length
  const total = relationOptions.value.length
  if (selected > 0 && selected < total) return selected
  return 0
})

async function loadOptions() {
  if (loading.value) return
  loading.value = true
  
  try {
    const [annotationResult, relationResult] = await Promise.all([
      EnumService.loadOptions('annotation_category', { cache: true, throwError: false }),
      EnumService.loadOptions('relation_type', { cache: true, throwError: false })
    ])
    
    annotationOptions.value = (annotationResult || []).map(item => ({
      value: item.value || item.code,
      label: item.label || item.name || item.code,
      count: item.count
    }))
    
    relationOptions.value = (relationResult || []).map(item => ({
      value: item.value || item.code,
      label: item.label || item.name || item.code,
      count: item.count
    }))
    
    if (selectedAnnotations.value.length === 0 && annotationOptions.value.length > 0) {
      selectedAnnotations.value = []
    }
    
    if (selectedRelations.value.length === 0 && relationOptions.value.length > 0) {
      selectedRelations.value = []
    }
    
    emitFilterChange()
    emit('load', { annotationOptions: annotationOptions.value, relationOptions: relationOptions.value })
  } catch (e) {
    console.warn('[RelationFilterSection] 加载选项失败:', e)
  } finally {
    loading.value = false
  }
}

function emitFilterChange() {
  emit('filter-change', {
    annotationCategories: [...selectedAnnotations.value],
    relationCodes: [...selectedRelations.value]
  })
}

function handleAnnotationChange() {
  emitFilterChange()
}

function handleRelationChange() {
  emitFilterChange()
}

function setFilters(filters) {
  if (filters.annotationCategories) {
    selectedAnnotations.value = [...filters.annotationCategories]
  }
  if (filters.relationCodes) {
    selectedRelations.value = [...filters.relationCodes]
  }
}

function clearAll() {
  selectedAnnotations.value = annotationOptions.value.map(o => o.value)
  selectedRelations.value = relationOptions.value.map(o => o.value)
  emitFilterChange()
}

watch(() => props.versionId, (newVal, oldVal) => {
  if (newVal && newVal !== oldVal) {
    loadOptions()
  }
}, { immediate: true })

onMounted(() => {
  if (props.initialAnnotations.length > 0) {
    selectedAnnotations.value = [...props.initialAnnotations]
  }
  if (props.initialRelations.length > 0) {
    selectedRelations.value = [...props.initialRelations]
  }
})

defineExpose({
  filterCount,
  annotationCount,
  relationCount,
  selectedAnnotations,
  selectedRelations,
  setFilters,
  clearAll,
  loadOptions
})
</script>

<style scoped>
.relation-filter-section {
  padding: 8px var(--spacing-sm);
}

.rfs-group {
  margin-bottom: 12px;
}

.rfs-group:last-child {
  margin-bottom: 0;
}

.rfs-group-header {
  margin-bottom: 6px;
}

.rfs-group-label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.rfs-select {
  width: 100%;
}

.rfs-scope-hint {
  color: #909399;
  font-size: 11px;
  font-weight: normal;
}

.rfs-group-disabled {
  opacity: 0.6;
}

.rfs-disabled-hint {
  margin-top: 4px;
  padding: 4px 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #909399;
}
</style>
