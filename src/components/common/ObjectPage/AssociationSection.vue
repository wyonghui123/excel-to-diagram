<template>
  <div class="op-association-section">
    <template v-if="isManyToMany">
      <MetaListPage
        :ref="setMetaListRef"
        :object-type="targetType"
        :display-mode="'embedded'"
        :columns-override="manyToManyColumns"
        :options="manyToManyOptions"
        :row-actions-override="manyToManyRowActions"
        :toolbar-actions-override="manyToManyToolbarActions"
        :batch-actions-override="manyToManyBatchActions"
        :enable-detail="false"
        :enable-auto-crud="false"
        :row-key="'id'"
        @action="handleEmbeddedAction($event, props.section)"
        @toolbar-action="handleToolbarAction($event, props.section)"
        @batch-action="handleBatchAction($event, props.section)"
      />
    </template>

    <div v-else-if="isMergedRelationships" class="op-merged-relations">
      <el-table :data="mergedRelationsData" v-loading="mergedRelationsLoading" size="small" max-height="400">
        <el-table-column label="关系类型" width="120">
          <template #default="{ row }">
            <span>{{ row.relation_type_name || row.relation_type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="方向" width="80">
          <template #default="{ row }">
            <span>{{ row.relation_direction || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="source_bo_name" label="源对象" min-width="180" />
        <el-table-column prop="target_bo_name" label="目标对象" min-width="180" />
        <el-table-column prop="relation_desc" label="关系描述" min-width="150" />
      </el-table>
      <div class="op-empty-state" v-if="!mergedRelationsLoading && mergedRelationsData.length === 0">
        <AppIcon name="link" size="lg" />
        <p>暂无关系数据</p>
      </div>
    </div>

    <template v-else-if="isAnnotation">
      <MetaListPage
        v-if="objectType && hasRealObjectId"
        :ref="setMetaListRef"
        object-type="annotation"
        :display-mode="'embedded'"
        :columns-override="props.section.columns || null"
        :options="annotationOptions"
        :toolbar-actions-override="annotationToolbarActions"
        :enable-auto-crud="false"
        :enable-detail="false"
        :row-actions-override="annotationRowActions"
        @action="handleAnnotationAction($event, props.section)"
        @toolbar-action="handleToolbarAction($event, props.section)"
      />
      <MetaDialog
        :visible="annotationFormVisible"
        :meta="annotationMeta"
        :entity-data="annotationEntityData"
        :saving="annotationSaving"
        z-index="10000"
        @close="handleAnnotationDialogClose"
        @save="handleAnnotationSave"
        @update:visible="annotationFormVisible = $event"
      />
    </template>

    <MetaListPage
      v-else-if="targetType && objectType && objectId"
      :ref="setMetaListRef"
      :object-type="targetType || section.association"
      :options="associationOptions"
      :initial-filters="associationFilters"
      :enable-detail="section.enableDetail !== undefined ? section.enableDetail : true"
      :enable-auto-crud="section.enableAutoCrud !== undefined ? section.enableAutoCrud : !section.readonly"
      :row-mutability="section.rowMutability || (section.readonly ? 'locked' : 'fully_editable')"
      :external-editing="editing"
      :exclude-column-keys="excludedColumnKeys"
      @request-edit="$emit('request-edit')"
    />

    <div v-else-if="!objectId || objectId === 'new'" class="op-empty-state">
      <AppIcon name="link" size="lg" />
      <p>保存对象后可以查看关联数据</p>
    </div>
    <div v-else class="op-empty-state">
      <AppIcon name="link" size="lg" />
      <p>缺少关联配置信息，无法加载关联数据。</p>
      <p>调试信息: assocType={{ section.assocType }}, assocName={{ section.assocName }}, objectType={{ objectType }}, objectId={{ objectId }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, shallowRef, inject, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import MetaListPage from '../MetaListPage/MetaListPage.vue'
import AppIcon from '../AppIcon/AppIcon.vue'
import MetaDialog from '../MetaDialog.vue'
import boService from '@/services/boService'
import { CATEGORY_CONFIG } from '@/composables/useMermaid/annotation/annotationConfig'
import * as annotationService from '@/services/annotationService'
import EnumService from '@/services/enumService'
import { useCrudMessage } from '@/composables/useCrudMessage'

const props = defineProps({
  section: {
    type: Object,
    required: true
  },
  objectType: {
    type: String,
    default: null
  },
  objectId: {
    type: [String, Number],
    default: null
  },
  editing: {
    type: Boolean,
    default: false
  },
  uiConfig: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['request-edit', 'open-assign', 'refresh', 'embedded-action'])

const message = useCrudMessage()

const hasRealObjectId = computed(() => {
  const id = props.objectId
  if (id == null || id === '' || id === 'new') return false
  const numId = Number(id)
  return !isNaN(numId) && numId > 0
})

function getAssociationConfig(assocName) {
  if (props.uiConfig?.associations) {
    const assocConfig = props.uiConfig.associations.find(a => a.name === assocName)
    if (assocConfig) {
      return assocConfig
    }
  }
  if (props.section.assocName === assocName || props.section.association === assocName) {
    return { target_type: props.section.association, ...props.section }
  }
  return {}
}

function getAssociationTargetType(assocName) {
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === assocName)
  if (assocConfig?.target_type) return assocConfig.target_type
  if (props.section.assocName === assocName && props.section.association) return props.section.association
  const sectionConfig = getAssociationConfig(assocName)
  return sectionConfig?.target_type || ''
}

const isManyToMany = computed(() => {
  return (props.section.assocType === 'many_to_many' || props.section.assocType === 'reverse_many_to_many')
    && props.section.assocName
    && getAssociationTargetType(props.section.assocName)
    && props.objectType
    && props.objectId
})

const isMergedRelationships = computed(() => {
  return props.section.customFetcher === 'merged_bo_relationships'
})

const isAnnotation = computed(() => {
  return props.section.type === 'annotation'
})

const targetType = computed(() => {
  return getAssociationTargetType(props.section.assocName)
})

// [FIX 2026-06-14] 父对象下的子对象 children 列表: 隐藏冗余的"所属产品"列
// 场景: product → version 列表, version 自带 product_name (所属产品) 列
//       但当前上下文父对象已经是 product, 该列是冗余信息
// 仅在 product → version 上下文生效, 不影响其他父子关系
const excludedColumnKeys = computed(() => {
  const parentType = props.objectType
  const childType = targetType.value || props.section.association
  if (parentType === 'product' && childType === 'version') {
    return ['product_id', 'product_name', 'product_code']
  }
  return []
})

const registerMetaListRef = inject('registerMetaListRef', null)
const metaListRef = shallowRef(null)

function setMetaListRef(el) {
  if (el && metaListRef.value !== el) {
    metaListRef.value = el
    registerMetaListRef?.(props.section.key, el)
  }
}

const manyToManyColumns = computed(() => {
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === props.section.assocName)
  return assocConfig?.display?.columns || null
})

const manyToManyFetcher = computed(() => {
  return (params) => {
    // [GUARD 2026-06-14] objectId='new' 是创建态, 后端 /bo/<type>/<id>/associations/<name> 期望 int id
    // 不拦截会触发 GET /api/v2/bo/role/new/associations/assigned_groups -> 404
    if (!hasRealObjectId.value) {
      return Promise.resolve({ success: true, data: { items: [], total: 0, counts: {} } })
    }
    return boService.queryAssociations(props.objectType, props.objectId, props.section.assocName, params)
  }
})

const manyToManyOptions = computed(() => ({
  autoLoad: true,
  pageSize: props.section.pageSize || 10,
  fetcher: manyToManyFetcher.value
}))

const manyToManyRowActions = computed(() => {
  // 如果有批量删除操作，则不显示单行删除按钮
  if (props.section.readonly) return []
  if (manyToManyBatchActions.value.length > 0) return []
  
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === props.section.assocName)
  const unassignAction = assocConfig?.actions?.unassign
  return [{
    key: 'remove',
    label: unassignAction?.label || '移除',
    type: 'danger',
    variant: 'danger'
  }]
})

const manyToManyToolbarActions = computed(() => {
  const section = props.section
  const actions = section?.actions || []
  
  console.debug('[AssociationSection] manyToManyToolbarActions:', {
    assocName: section?.assocName,
    assocType: section?.assocType,
    readonly: section?.readonly,
    actions,
    isManyToMany: isManyToMany.value
  })
  
  if (section?.readonly) {
    console.debug('[AssociationSection] Skipping toolbar actions: readonly=true')
    return []
  }
  
  const hasAssignAction = actions.some(a => {
    if (typeof a === 'string') return a === 'assign'
    return a.key === 'assign' || a.id === 'assign'
  })
  
  if (!hasAssignAction) {
    console.debug('[AssociationSection] Skipping toolbar actions: no assign action')
    return []
  }
  
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === section?.assocName)
  const result = [{
    key: 'assign',
    label: assocConfig?.actions?.assign?.label || '+ 添加',
    variant: 'primary'
  }]
  
  console.debug('[AssociationSection] Returning toolbar actions:', result)
  return result
})

const manyToManyBatchActions = computed(() => {
  const section = props.section
  if (section?.readonly) return []
  
  const actions = section?.actions || []
  const hasUnassignAction = actions.some(a => {
    if (typeof a === 'string') return a === 'unassign'
    return a.key === 'unassign' || a.id === 'unassign'
  })
  
  if (!hasUnassignAction) return []
  
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === section?.assocName)
  return [{
    key: 'batch_unassign',
    label: assocConfig?.actions?.unassign?.label || '批量移除',
    variant: 'danger',
    confirm: assocConfig?.actions?.unassign?.confirm_message || '确定要移除选中的项目吗？'
  }]
})

const associationFilters = computed(() => {
  const section = props.section
  if (section.assocType === 'many_to_many' || section.assocType === 'reverse_many_to_many') {
    return {}
  }
  const parentKey = `${props.objectType}_id`
  return { [parentKey]: props.objectId }
})

const associationFetcher = computed(() => {
  return (params) => {
    // [GUARD 2026-06-14] 同 manyToManyFetcher, 创建态 objectId='new' 拦截
    if (!hasRealObjectId.value) {
      return Promise.resolve({ success: true, data: { items: [], total: 0, counts: {} } })
    }
    return boService.queryAssociations(props.objectType, props.objectId, props.section.assocName, params)
  }
})

const associationOptions = computed(() => {
  const baseOptions = {
    autoLoad: true,
    pageSize: props.section.pageSize || 10
  }
  
  if (props.section.inlineEdit) {
    baseOptions.inlineEdit = props.section.inlineEdit
  }
  
  if (props.section.assocType === 'parent_child') {
    return baseOptions
  }
  return {
    ...baseOptions,
    fetcher: associationFetcher.value
  }
})

const annotationFetcher = computed(() => {
  return async (queryParams) => {
    const { page = 1, pageSize = props.section.pageSize || 10 } = queryParams || {}
    try {
      const result = await annotationService.queryAnnotations({
        target_type: props.objectType,
        target_id: props.objectId,
        page,
        page_size: pageSize
      })
      if (result.success) {
        const data = result.data?.data || result.data || []
        const total = result.data?.total ?? result.total ?? data.length
        return { success: true, data: { items: Array.isArray(data) ? data : [], total } }
      }
      return { success: false, message: result.message || '获取备注失败', data: { items: [], total: 0 } }
    } catch (e) {
      console.error('[AssociationSection] Failed to fetch annotations:', e)
      return { success: false, message: e.message, data: { items: [], total: 0 } }
    }
  }
})

const annotationOptions = computed(() => ({
  autoLoad: true,
  pageSize: props.section.pageSize || 10,
  fetcher: annotationFetcher.value
}))

const annotationRowActions = computed(() => [
  { key: 'annotation-edit', label: '编辑', type: 'primary' },
  { key: 'annotation-delete', label: '删除', type: 'danger' }
])

const annotationToolbarActions = computed(() => {
  if (!hasRealObjectId.value) return []
  const hasCreateAction = props.section.actions?.some(a => (typeof a === 'string' ? a : a.key) === 'create')
  if (!hasCreateAction) return []
  return [{
    key: 'create',
    label: '添加备注',
    variant: 'primary'
  }]
})

function handleToolbarAction(action, section) {
  console.debug('[AssociationSection] handleToolbarAction:', { action, section })
  if (action.key === 'assign') {
    console.debug('[AssociationSection] Emitting open-assign with section:', section)
    emit('open-assign', section)
  } else if (action.key === 'create') {
    handleAnnotationCreate(section)
  }
}

async function handleBatchAction(event, section) {
  const { action, selectedIds, selectedRows } = event
  console.debug('[AssociationSection] handleBatchAction:', { action, selectedIds, selectedRows, section })
  
  if (action.key === 'batch_unassign') {
    const confirmMsg = action.confirm || '确定要移除选中的项目吗？'
    try {
      await ElMessageBox.confirm(confirmMsg, '批量移除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
    } catch {
      return
    }
    
    const results = []
    const errors = []

    // [FIX 2026-06-08] 用后端 /batch_unassign 替代 N 次单条 unassign 循环
    // 原因：循环里第一条成功后,后端可能因 stale association_record_id 返回 404;
    //      且 N 次 HTTP 请求慢、不原子。后端 bo_api.py:585 已提供 batch_unassign 端点。
    // 重要：表格 row.id 是 **target_id (role.id)**，不是 through-table 行 id (group_roles.id)。
    //      之前 v1 unassign 循环误把 role.id 当 association_record_id 传给后端,所以后端查 group_roles 找不到。
    //      后端 /batch_unassign 接受 { target_ids, target_type } 直接按 role.id 删除,无需 SQL 反查。
    const assocConfig = getAssociationConfig(section.assocName)
    const targetType = assocConfig?.target_type
    const targetIds = selectedRows.map(r => r.id).filter(id => id != null)
    if (targetIds.length === 0) {
      message.warning('没有可移除的记录')
      return
    }

    try {
      const result = await boService.batchUnassignAssociationsV2(
        props.objectType,
        props.objectId,
        section.assocName,
        {
          target_ids: targetIds,
          target_type: targetType
        }
      )
      if (result && (result.success || result === true)) {
        results.push(...targetIds)
      } else {
        // 后端 batch_unassign 的 data.results 数组里每项含 success/target_id;
        // 失败项的 target_id 即本次请求里的 target_id 之一
        const resultsArr = result?.data?.results
        const failedIds = (Array.isArray(resultsArr) ? resultsArr : [])
          .filter(r => !r.success)
          .map(r => r.target_id)
        const failedSet = new Set(failedIds)
        const successIds = targetIds.filter(id => !failedSet.has(id))
        results.push(...successIds)
        targetIds.filter(id => failedSet.has(id)).forEach(id => {
          errors.push({ id, message: result?.message || '移除失败' })
        })
      }
    } catch (e) {
      targetIds.forEach(id => errors.push({ id, message: e.message }))
    }
    
    if (errors.length === 0) {
      message.success(`已移除 ${results.length} 项`)
    } else if (results.length > 0) {
      message.warning(`成功移除 ${results.length} 项，失败 ${errors.length} 项`)
    } else {
      message.error('移除失败')
    }

    boService._clearCache(props.objectType)
    await refresh()
    // [FIX 2026-06-08] 批量删除成功后清空 el-table 勾选状态。
    // 原因: refresh() 重新拉数据,但 el-table 内部的 selectionChange 状态没动,
    //      totalSelectedCount 仍然 > 0 → 工具栏 "已选择 N 项 / 清除选择 / 批量删除"
    //      持续显示,即便底层数据已删。clearAllSelection 由 MetaListPage
    //      defineExpose 暴露(L1480),走 tableRef.clearSelection() 把勾选清掉。
    if (results.length > 0 && metaListRef.value?.clearAllSelection) {
      metaListRef.value.clearAllSelection()
    }
    emit('refresh')
  }
}

const mergedRelationsData = ref([])
const mergedRelationsLoading = ref(false)
let _mergedLoadVersion = 0

async function loadMergedRelationships() {
  if (!props.objectId) return
  // [GUARD 2026-06-14] 创建态 objectId='new' 拦截, 避免 source_bo_id='new' 触发后端异常
  if (!hasRealObjectId.value) {
    mergedRelationsData.value = []
    mergedRelationsLoading.value = false
    return
  }
  const version = ++_mergedLoadVersion
  mergedRelationsLoading.value = true
  try {
    const [r1, r2] = await Promise.all([
      boService.query('relationship', { page_size: 9999, source_bo_id: props.objectId }),
      boService.query('relationship', { page_size: 9999, target_bo_id: props.objectId })
    ])
    if (version !== _mergedLoadVersion) return
    const seen = new Set()
    const merged = []
    for (const r of [r1, r2]) {
      const items = r?.success ? (r.data?.items || (Array.isArray(r.data) ? r.data : [])) : []
      for (const it of items) {
        if (!seen.has(it.id)) { seen.add(it.id); merged.push(it) }
      }
    }
    mergedRelationsData.value = merged
  } catch (e) {
    console.error('[AssociationSection] loadMergedRelationships:', e)
  } finally {
    if (version === _mergedLoadVersion) {
      mergedRelationsLoading.value = false
    }
  }
}

async function handleAnnotationAction(event, section) {
  const { action, row } = event
  const actionKey = action?.key || action
  try {
    if (actionKey === 'annotation-edit') {
      handleAnnotationEdit(row, section)
    } else if (actionKey === 'annotation-delete') {
      await handleAnnotationDelete(row, section)
    }
  } catch (e) {
    console.error('[AssociationSection] Annotation action failed:', e)
    message.error('操作失败', e)
  }
}

const defaultCategories = [
  { code: 'important', name: '重要' },
  { code: 'warning', name: '警告' },
  { code: 'info', name: '信息' },
  { code: 'tip', name: '提示' }
]

const annotationCategories = ref([...defaultCategories])
const annotationFormVisible = ref(false)
const annotationEditingId = ref(null)
const annotationEntityData = ref(null)
const annotationSaving = ref(false)

const annotationMeta = computed(() => ({
  label: '备注',
  fields: [
    {
      key: 'category',
      label: '分类',
      type: 'select',
      required: true,
      defaultValue: annotationCategories.value.length > 0 ? annotationCategories.value[0].code : '',
      options: annotationCategories.value.map(c => ({ label: c.name, value: c.code }))
    },
    {
      key: 'content',
      label: '内容',
      type: 'textarea',
      required: true,
      placeholder: '请输入备注内容...'
    }
  ]
}))

let categoriesLoaded = false

async function loadAnnotationCategories() {
  if (categoriesLoaded && annotationCategories.value.length > 0) return
  try {
    const items = await EnumService.loadOptions('annotation_category', { useHighSpeedEndpoint: false })
    if (items && items.length > 0) {
      annotationCategories.value = items.map(item => {
        const config = CATEGORY_CONFIG[item.value]
        return {
          code: item.value,
          name: config ? config.label : item.label
        }
      })
    }
    categoriesLoaded = true
  } catch {
    categoriesLoaded = false
  }
}

async function handleAnnotationCreate(section) {
  await loadAnnotationCategories()
  annotationEditingId.value = null
  annotationEntityData.value = null
  annotationFormVisible.value = true
}

async function handleAnnotationEdit(row, section) {
  await loadAnnotationCategories()
  annotationEditingId.value = row.id
  annotationEntityData.value = {
    category: row.category || '',
    content: row.content || ''
  }
  annotationFormVisible.value = true
}

function handleAnnotationDialogClose() {
  annotationFormVisible.value = false
  annotationEditingId.value = null
  annotationEntityData.value = null
}

async function handleAnnotationSave(formData) {
  annotationSaving.value = true
  try {
    let result
    if (annotationEditingId.value) {
      result = await annotationService.updateAnnotation(annotationEditingId.value, {
        category: formData.category,
        content: formData.content
      })
    } else {
      result = await annotationService.createAnnotation({
        target_type: props.objectType,
        target_id: props.objectId,
        category: formData.category,
        content: formData.content
      })
    }
    if (!result.success) throw new Error(result.message)
    message.success(annotationEditingId.value ? '备注已更新' : '备注已添加')
    annotationFormVisible.value = false
    refresh()
    emit('refresh')
  } catch (e) {
    message.error('保存失败', e)
  } finally {
    annotationSaving.value = false
  }
}

async function handleAnnotationDelete(row, section) {
  const result = await annotationService.deleteAnnotation(row.id)
  if (result.success) {
    message.success('备注已删除')
    refresh()
  } else {
    message.error('删除失败', result)
  }
}

async function handleEmbeddedAction({ action, row }, section) {
  emit('embedded-action', { action, row }, section)
  if (action?.key === 'remove' && row?.id) {
    try {
      const assocConfig = getAssociationConfig(section.assocName)
      const result = await boService.unassignAssociationV2(
        props.objectType,
        props.objectId,
        section.assocName,
        { association_record_id: row.id }
      )
      if (result && (result.success || result === true)) {
        message.success('已移除')
        boService._clearCache(props.objectType)
      } else {
        message.error('移除失败', result)
      }
    } catch (e) {
      console.error('[AssociationSection] unassign failed:', e)
      message.error('移除失败', e)
    }
    await refresh()
    emit('refresh')
  }
}

onMounted(() => {
  loadAnnotationCategories()
})

watch(() => props.objectId, (newVal, oldVal) => {
  if (newVal === oldVal) return
  if (isMergedRelationships.value) {
    loadMergedRelationships()
  }
}, { immediate: true })

function refresh() {
  if (metaListRef.value?.refresh) {
    metaListRef.value.refresh()
  }
}

defineExpose({ refresh, loadMergedRelationships })
</script>

<style scoped>
.op-association-section {
  padding: var(--spacing-sm) 0;
  min-height: 200px;
}

.op-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
  color: var(--color-text-secondary);
  text-align: center;
}

.op-merged-relations {
  padding: var(--spacing-sm) 0;
}
</style>
