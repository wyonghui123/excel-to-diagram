<template>
  <div class="lgn-node">
    <div class="lgn-row" :class="{ 'row-drag-over': isRowDragOver }"
      @dragover.prevent="handleRowDragOver" @dragleave="handleRowDragLeave" @drop="handleRowDrop">
      <button class="lgn-caret" @click="toggleExpanded" :class="{ expanded: expanded }"
        :title="hasChildren ? (expanded ? '收起' : '展开') : ''">
        <span v-if="hasChildren" class="caret-arrow">▸</span>
        <span v-else class="caret-placeholder"></span>
      </button>
      <span class="lgn-type-icon" :title="getGroupTypeLabel(group.groupType)">{{ typeIcon }}</span>
      <div class="lgn-title" @dblclick="startEditTitle">
        <template v-if="!isEditingTitle">
          <span class="lgn-title-text">{{ group.title }}</span>
          <span v-if="group.isCenter" class="center-marker" title="中心范围">◆</span>
          <span v-if="group.groupType" class="lgn-type-badge">{{ getGroupTypeLabel(group.groupType) }}</span>
          <span v-if="group.title === '无外部关系' || group.title === '有外部关系'"
            class="elk-hint" :title="getElkGroupHint(group._elkGroup)">ⓘ</span>
        </template>
        <input v-else ref="titleInput" v-model="editTitle" class="title-input"
          @blur="finishEditTitle" @keyup.enter="finishEditTitle" @keyup.escape="cancelEditTitle" />
      </div>
      <div class="lgn-inline-actions">
        <button class="lgn-eye" :class="{ off: group.enabled === false }"
          :title="group.enabled !== false ? '点击禁用分组' : '点击启用分组'" @click="toggleEnabled">
          <AppIcon :name="group.enabled !== false ? 'eye' : 'eye-off'" size="sm" />
        </button>
        <button class="lgn-more" title="更多设置" @click="popoverVisible = true">
          <AppIcon name="settings" size="sm" />
        </button>
        <button v-if="isCustomGroup" class="lgn-delete" title="删除分组" @click="handleDelete">
          <AppIcon name="close" size="sm" />
        </button>
        <button class="lgn-drag-handle" draggable="true" @dragstart="handleGroupDragStart($event)"
          @dragend="handleGroupDragEnd" title="拖拽排序">
          <AppIcon name="sort" size="sm" />
        </button>
      </div>

      <el-popover v-model:visible="popoverVisible" :teleported="true" placement="right-start"
        :width="220" trigger="contextmenu" popper-class="lgn-popover">
        <template #reference>
          <span class="lgn-context-anchor"></span>
        </template>
        <div class="lgn-popover-body">
          <div class="pp-row">
            <span class="pp-label">启用</span>
            <el-switch :model-value="group.enabled !== false" @change="handleEnabledChange" size="small" />
          </div>
          <div class="pp-row">
            <span class="pp-label">显示边框</span>
            <el-switch :model-value="group.visible !== false" @change="handleVisibleChange" size="small" />
          </div>
          <div v-if="hasMultipleChildren && !isELK" class="pp-row">
            <span class="pp-label">方向</span>
            <div class="direction-toggle">
              <button class="direction-btn" :class="{ active: group.direction === 'TB' }"
                @click="handleDirectionChange('TB')" title="从上到下">TB</button>
              <button class="direction-btn" :class="{ active: group.direction === 'LR' }"
                @click="handleDirectionChange('LR')" title="从左到右">LR</button>
            </div>
          </div>
          <div class="pp-actions">
            <button v-if="!isCustomGroup" class="pp-btn" @click="handleAddChild">添加子分组</button>
            <button v-if="isCustomGroup" class="pp-btn danger" @click="handleDelete">删除分组</button>
          </div>
        </div>
      </el-popover>
    </div>

    <div v-if="expanded && group.children && group.children.length" class="lgn-children">
      <LayoutGroupNode
        v-for="(child, idx) in group.children" :key="child.id"
        :group="child" :depth="depth + 1" :containers="containers" :index="idx"
        :color-mapping="colorMapping"
        @update="handleChildUpdate" @delete="handleChildDelete" @add-child="handleChildAddChild"
        @assign-container="handleChildAssignContainer" @remove-container="handleChildRemoveContainer"
        @reorder-groups="handleChildReorderGroups" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { AppIcon } from '@/components/common/AppIcon'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'
import { useGroupDisplay } from '@/composables/useGroupDisplay'

const props = defineProps({
  group: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  containers: { type: Array, default: () => [] },
  index: { type: Number, default: -1 },
  colorMapping: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['update', 'delete', 'add-child', 'assign-container', 'remove-container', 'reorder-groups', 'remove-node'])

const store = useDiagramConfigStore()
const { getGroupTypeLabel, getElkGroupHint } = useGroupDisplay(props.colorMapping)

const expanded = ref(props.depth < 1) // 默认收起深层
const isEditingTitle = ref(false)
const editTitle = ref('')
const titleInput = ref(null)
const popoverVisible = ref(false)
const isRowDragOver = ref(false)

const isELK = computed(() => store.layoutEngine === 'elk')
const isCustomGroup = computed(() => props.group.groupType === 'custom')
const hasChildren = computed(() => (props.group.children?.length || 0) > 0)
const hasMultipleChildren = computed(() => {
  const childCount = props.group.children?.length || 0
  const containerCount = props.group.containers?.length || 0
  return childCount > 0 || containerCount > 1
})

const typeIcon = computed(() => {
  const map = {
    domain: '📁', subDomain: '📂', serviceModule: '📄',
    businessObject: '📄', virtualLayer: '🟦', custom: '📦'
  }
  return map[props.group.groupType] || '📄'
})

function toggleExpanded() {
  if (hasChildren.value) expanded.value = !expanded.value
}

function startEditTitle() {
  editTitle.value = props.group.title
  isEditingTitle.value = true
  nextTick(() => { titleInput.value?.focus(); titleInput.value?.select() })
}
function finishEditTitle() {
  if (editTitle.value.trim() && editTitle.value !== props.group.title) {
    emit('update', { id: props.group.id, updates: { title: editTitle.value.trim() } })
  }
  isEditingTitle.value = false
}
function cancelEditTitle() { isEditingTitle.value = false }

function toggleEnabled() {
  const enabled = props.group.enabled === false
  const updates = { enabled }
  if (!enabled) {
    updates.visible = false
    updates.previousVisible = props.group.visible
  } else {
    updates.visible = props.group.previousVisible !== undefined ? props.group.previousVisible : true
  }
  emit('update', { id: props.group.id, updates })
}
function handleEnabledChange(val) {
  const updates = { enabled: val }
  if (!val) {
    updates.visible = false
    updates.previousVisible = props.group.visible
  } else {
    updates.visible = props.group.previousVisible !== undefined ? props.group.previousVisible : true
  }
  emit('update', { id: props.group.id, updates })
}
function handleVisibleChange(val) {
  emit('update', { id: props.group.id, updates: { visible: val } })
}
function handleDirectionChange(direction) {
  emit('update', { id: props.group.id, updates: { direction } })
}
function handleDelete() { emit('delete', props.group.id) }
function handleAddChild() { emit('add-child', props.group.id) }

function handleChildUpdate(d) { emit('update', d) }
function handleChildDelete(id) { emit('delete', id) }
function handleChildAddChild(parentId) { emit('add-child', parentId) }
function handleChildAssignContainer(d) { emit('assign-container', d) }
function handleChildRemoveContainer(d) { emit('remove-container', d) }
function handleChildReorderGroups(d) { emit('reorder-groups', d) }

function handleGroupDragStart(event) {
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'group', groupId: props.group.id, sourceIndex: props.index
  }))
  event.stopPropagation()
}
function handleGroupDragEnd() {}

function handleRowDragOver(event) {
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type === 'container') isRowDragOver.value = true
  } catch { isRowDragOver.value = true }
}
function handleRowDragLeave() { isRowDragOver.value = false }
function handleRowDrop(event) {
  isRowDragOver.value = false
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type === 'container') {
      const container = data.container
      if (data.sourceType === 'group' && data.sourceGroupId && data.sourceGroupId !== props.group.id) {
        emit('remove-container', { groupId: data.sourceGroupId, containerId: container.id })
      }
      emit('assign-container', { groupId: props.group.id, container })
    }
  } catch (e) { console.error('Failed to parse drop data:', e) }
}
</script>

<style scoped lang="scss">
.lgn-row {
  display: flex; align-items: center; gap: 4px; height: 28px;
  padding: 0 6px; border-radius: 4px; cursor: pointer;
  &:hover { background: rgba(234, 88, 12, 0.08); }
  &.row-drag-over { background: rgba(82, 196, 26, 0.15); outline: 1px dashed #52c41a; }
}
.lgn-caret { width: 18px; height: 18px; border: none; background: transparent; cursor: pointer; color: #999; padding: 0; }
.caret-arrow { display: inline-block; transition: transform 0.15s; }
.lgn-caret.expanded .caret-arrow { transform: rotate(90deg); }
.caret-placeholder { display: inline-block; width: 8px; }
.lgn-type-icon { font-size: 14px; }
.lgn-title { flex: 1; display: flex; align-items: center; gap: 4px; overflow: hidden;
  white-space: nowrap; text-overflow: ellipsis; }
.lgn-title-text { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; }
.lgn-type-badge { font-size: 11px; padding: 0 5px; border-radius: 3px; background: rgba(0,0,0,0.06); color: #666; white-space: nowrap; }
.center-marker { font-style: italic; font-weight: bold; }
.elk-hint { font-size: 12px; color: #999; cursor: help; }
.title-input { padding: 2px 6px; border: 1px solid var(--color-primary); border-radius: 4px; font-size: 13px; min-width: 100px; }
.lgn-inline-actions { display: flex; align-items: center; gap: 2px; opacity: 0; transition: opacity 0.15s; }
.lgn-row:hover .lgn-inline-actions { opacity: 1; }
.lgn-eye, .lgn-more, .lgn-delete, .lgn-drag-handle {
  display: flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border: none; background: transparent; color: #999; cursor: pointer; border-radius: 3px;
  &:hover { background: rgba(0,0,0,0.06); color: #333; }
}
.lgn-eye.off { color: #bbb; }
.lgn-delete:hover { color: #e74c3c; }
.lgn-drag-handle { cursor: grab; }
.lgn-context-anchor { display: none; }
</style>