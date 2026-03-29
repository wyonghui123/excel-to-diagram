<template>
  <div 
    class="group-item" 
    :style="{ marginLeft: `${depth * 16}px` }"
    :class="{ 'group-dragging': isGroupDragging }"
  >
    <div
      class="group-card"
      :class="{ 'drag-over': isDragOver, 'group-drag-over': isGroupDragOver }"
      @dragover.prevent="handleAllDragOver"
      @dragleave="handleAllDragLeave"
      @drop="handleAllDrop"
    >
      <div class="group-header">
        <div class="group-drag-handle" 
          draggable="true"
          @dragstart="handleGroupDragStart($event)"
          @dragend="handleGroupDragEnd"
          title="拖拽排序"
        >
          <svg viewBox="0 0 24 24" width="12" height="12">
            <path fill="currentColor" d="M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
          </svg>
        </div>
        <div class="group-title" @dblclick="startEditTitle">
          <template v-if="!isEditingTitle">
            {{ group.title }}
          </template>
          <input
            v-else
            ref="titleInput"
            v-model="editTitle"
            class="title-input"
            @blur="finishEditTitle"
            @keyup.enter="finishEditTitle"
            @keyup.escape="cancelEditTitle"
          />
        </div>

        <div class="group-actions">
          <button class="action-btn add-child-btn" @click="handleAddChild" title="添加子分组">
            <svg viewBox="0 0 24 24" width="14" height="14">
              <path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
            </svg>
          </button>
          <button class="action-btn delete-btn" @click="handleDelete" title="删除分组">
            <svg viewBox="0 0 24 24" width="14" height="14">
              <path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="group-config">
        <div class="config-row" v-if="hasMultipleChildren">
          <label class="config-label">方向</label>
          <select class="direction-select" :value="group.direction" @change="handleDirectionChange">
            <option value="TB">从上到下 (TB)</option>
            <option value="BT">从下到上 (BT)</option>
            <option value="LR">从左到右 (LR)</option>
            <option value="RL">从右到左 (RL)</option>
          </select>
        </div>

        <div class="config-row">
          <label class="config-label">显示边界</label>
          <label class="toggle-switch">
            <input
              type="checkbox"
              :checked="group.visible"
              @change="handleVisibleChange"
            />
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>

      <div v-if="group.containers && group.containers.length > 0" class="assigned-containers">
        <div class="containers-label">已分配容器：</div>
        <div class="containers-list">
          <div
            v-for="(container, idx) in group.containers"
            :key="container.id || idx"
            class="assigned-container-item"
            :class="{ 'dragging': draggingContainerIndex === idx, 'drag-over': dragOverIndex === idx }"
            draggable="true"
            @dragstart="handleContainerDragStart($event, container, idx)"
            @dragend="handleContainerDragEnd"
            @dragover="handleContainerDragOver($event, idx)"
            @dragleave="handleContainerDragLeave"
            @drop="handleContainerDrop($event, idx)"
          >
            <span class="container-name">{{ getContainerName(container) }}</span>
            <select 
              class="container-direction-select" 
              :value="container.direction || 'LR'" 
              @change="handleContainerDirectionChange(container, $event.target.value)"
              @click.stop
            >
              <option value="TB">上下</option>
              <option value="LR">左右</option>
            </select>
            <button class="remove-container-btn" @click="handleRemoveContainer(container)" title="移除容器">
              ×
            </button>
          </div>
        </div>
      </div>

      <div class="drop-zone-area" :class="{ 'active': isDragOver }">
        <span v-if="isDragOver" class="drop-hint">释放以添加容器</span>
        <span v-else class="drop-hint-placeholder">拖拽容器到此处</span>
      </div>

      <div v-if="group.children && group.children.length > 0" class="children-container">
        <GroupItem
          v-for="child in group.children"
          :key="child.id"
          :group="child"
          :depth="depth + 1"
          :containers="containers"
          @update="handleChildUpdate"
          @delete="handleChildDelete"
          @add-child="handleChildAddChild"
          @assign-container="handleChildAssignContainer"
          @remove-container="handleChildRemoveContainer"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, computed } from 'vue'

const props = defineProps({
  group: {
    type: Object,
    required: true
  },
  depth: {
    type: Number,
    default: 0
  },
  containers: {
    type: Array,
    default: () => []
  },
  index: {
    type: Number,
    default: -1
  }
})

const emit = defineEmits(['update', 'delete', 'add-child', 'assign-container', 'remove-container', 'reorder-containers', 'reorder-groups'])

const isEditingTitle = ref(false)
const editTitle = ref('')
const titleInput = ref(null)
const isDragOver = ref(false)
const draggingContainerData = ref(null)
const draggingContainerIndex = ref(-1)
const dragOverIndex = ref(-1)
const isGroupDragging = ref(false)
const isGroupDragOver = ref(false)

const hasMultipleChildren = computed(() => {
  const containerCount = props.group.containers?.length || 0
  const childCount = props.group.children?.length || 0
  return (containerCount + childCount) > 1
})

function startEditTitle() {
  editTitle.value = props.group.title
  isEditingTitle.value = true
  nextTick(() => {
    titleInput.value?.focus()
    titleInput.value?.select()
  })
}

function finishEditTitle() {
  if (editTitle.value.trim() && editTitle.value !== props.group.title) {
    emit('update', {
      id: props.group.id,
      updates: { title: editTitle.value.trim() }
    })
  }
  isEditingTitle.value = false
}

function cancelEditTitle() {
  isEditingTitle.value = false
}

function handleDirectionChange(event) {
  emit('update', {
    id: props.group.id,
    updates: { direction: event.target.value }
  })
}

function handleVisibleChange(event) {
  emit('update', {
    id: props.group.id,
    updates: { visible: event.target.checked }
  })
}

function handleDelete() {
  emit('delete', props.group.id)
}

function handleAddChild() {
  emit('add-child', props.group.id)
}

function handleChildUpdate(data) {
  emit('update', data)
}

function handleChildDelete(id) {
  emit('delete', id)
}

function handleChildAddChild(parentId) {
  emit('add-child', parentId)
}

function handleChildAssignContainer(data) {
  emit('assign-container', data)
}

function handleChildRemoveContainer(data) {
  emit('remove-container', data)
}

function handleDragOver(event) {
  isDragOver.value = true
}

function handleDragLeave(event) {
  isDragOver.value = false
}

function handleDrop(event) {
  isDragOver.value = false
  
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    
    if (data.type === 'container') {
      const container = data.container
      
      if (data.sourceType === 'group' && data.sourceGroupId === props.group.id) {
        return
      }
      
      if (data.sourceType === 'group' && data.sourceGroupId) {
        emit('remove-container', {
          groupId: data.sourceGroupId,
          containerId: container.id
        })
      }
      
      emit('assign-container', {
        groupId: props.group.id,
        container: container
      })
    }
  } catch (e) {
    console.error('Failed to parse drop data:', e)
  }
}

function handleAllDragOver(event) {
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type === 'group') {
      isGroupDragOver.value = true
    } else {
      isDragOver.value = true
    }
  } catch (e) {
    isDragOver.value = true
  }
}

function handleAllDragLeave(event) {
  isDragOver.value = false
  isGroupDragOver.value = false
}

function handleAllDrop(event) {
  isDragOver.value = false
  isGroupDragOver.value = false
  
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    
    if (data.type === 'group') {
      const sourceIdx = data.sourceIndex
      const targetIdx = props.index
      if (sourceIdx !== targetIdx && sourceIdx !== -1 && targetIdx !== -1) {
        emit('reorder-groups', { sourceIndex: sourceIdx, targetIndex: targetIdx })
      }
    } else if (data.type === 'container') {
      const container = data.container
      
      if (data.sourceType === 'group' && data.sourceGroupId === props.group.id) {
        return
      }
      
      if (data.sourceType === 'group' && data.sourceGroupId) {
        emit('remove-container', {
          groupId: data.sourceGroupId,
          containerId: container.id
        })
      }
      
      emit('assign-container', {
        groupId: props.group.id,
        container: container
      })
    }
  } catch (e) {
    console.error('Failed to parse drop data:', e)
  }
}

function getContainerName(container) {
  if (typeof container === 'object' && container.name) {
    return container.name
  }
  if (typeof container === 'string') {
    const found = props.containers.find(c => c.id === container)
    return found ? found.name : container
  }
  return '未知容器'
}

function getContainerNodeCount(container) {
  if (typeof container === 'object' && container.nodes) {
    return container.nodes.length
  }
  const containerId = typeof container === 'object' ? container.id : container
  const found = props.containers.find(c => c.id === containerId)
  return found?.nodes?.length || 0
}

function handleContainerDragStart(event, container, idx) {
  draggingContainerData.value = { container, idx }
  draggingContainerIndex.value = idx
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'container',
    container: container,
    sourceType: 'group',
    sourceGroupId: props.group.id,
    sourceIndex: idx
  }))
}

function handleContainerDragEnd() {
  draggingContainerData.value = null
  draggingContainerIndex.value = -1
  dragOverIndex.value = -1
}

function handleContainerDragOver(event, idx) {
  event.preventDefault()
  if (draggingContainerIndex.value !== -1 && draggingContainerIndex.value !== idx) {
    dragOverIndex.value = idx
  }
}

function handleContainerDragLeave() {
  dragOverIndex.value = -1
}

function handleContainerDrop(event, targetIdx) {
  event.preventDefault()
  dragOverIndex.value = -1
  
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    
    if (data.type === 'container' && data.sourceGroupId === props.group.id) {
      const sourceIdx = data.sourceIndex
      if (sourceIdx !== targetIdx) {
        const newContainers = [...props.group.containers]
        const [removed] = newContainers.splice(sourceIdx, 1)
        newContainers.splice(targetIdx, 0, removed)
        emit('update', {
          id: props.group.id,
          updates: { containers: newContainers }
        })
      }
    }
  } catch (e) {
    console.error('Failed to parse drop data:', e)
  }
}

function handleContainerDirectionChange(container, newDirection) {
  const containerIdx = props.group.containers.findIndex(c => 
    (typeof c === 'object' && c.id === container.id) || c === container
  )
  if (containerIdx !== -1) {
    const updatedContainers = [...props.group.containers]
    const targetContainer = updatedContainers[containerIdx]
    if (typeof targetContainer === 'object') {
      updatedContainers[containerIdx] = { ...targetContainer, direction: newDirection }
    } else {
      updatedContainers[containerIdx] = { id: targetContainer, direction: newDirection }
    }
    emit('update', {
      id: props.group.id,
      updates: { containers: updatedContainers }
    })
  }
}

function handleGroupDragStart(event) {
  isGroupDragging.value = true
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'group',
    groupId: props.group.id,
    sourceIndex: props.index
  }))
  event.stopPropagation()
}

function handleGroupDragEnd() {
  isGroupDragging.value = false
}

function handleRemoveContainer(container) {
  const containerId = typeof container === 'object' ? container.id : container
  emit('remove-container', {
    groupId: props.group.id,
    containerId: containerId
  })
}
</script>

<style scoped lang="scss">
.group-item {
  margin-bottom: var(--spacing-xs);

  &.group-dragging {
    opacity: 0.5;
  }
}

.group-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: all 0.2s;

  &.drag-over {
    border-color: var(--color-primary);
    border-width: 2px;
    box-shadow: 0 0 8px rgba(24, 144, 255, 0.3);
  }

  &.group-drag-over {
    border-color: #52c41a;
    border-width: 2px;
    box-shadow: 0 0 8px rgba(82, 196, 26, 0.3);
  }
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
}

.group-drag-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  cursor: grab;
  color: var(--color-text-secondary);
  margin-right: var(--spacing-xs);

  &:hover {
    color: var(--color-primary);
  }

  &:active {
    cursor: grabbing;
  }
}

.group-title {
  font-weight: 500;
  color: var(--color-text-primary);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--radius-sm);

  &:hover {
    background: rgba(24, 144, 255, 0.1);
  }
}

.title-input {
  padding: 2px 6px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  font-size: inherit;
  font-weight: 500;
  background: white;
  outline: none;
  min-width: 100px;
}

.group-actions {
  display: flex;
  gap: var(--spacing-xs);
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: white;
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: var(--color-bg-secondary);
    border-color: var(--color-primary);
  }

  svg {
    flex-shrink: 0;
  }
}

.add-child-btn:hover {
  color: var(--color-primary);
}

.delete-btn:hover {
  color: #e74c3c;
}

.group-config {
  padding: var(--spacing-sm) var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.config-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.config-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  min-width: 60px;
}

.direction-select {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  background: white;
  color: var(--color-text-primary);
  cursor: pointer;
  outline: none;

  &:focus {
    border-color: var(--color-primary);
  }
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  cursor: pointer;

  input {
    opacity: 0;
    width: 0;
    height: 0;

    &:checked + .toggle-slider {
      background-color: var(--color-primary);

      &::before {
        transform: translateX(16px);
      }
    }
  }

  .toggle-slider {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: var(--color-border);
    border-radius: 10px;
    transition: 0.2s;

    &::before {
      position: absolute;
      content: "";
      height: 16px;
      width: 16px;
      left: 2px;
      bottom: 2px;
      background-color: white;
      border-radius: 50%;
      transition: 0.2s;
    }
  }
}

.assigned-containers {
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--color-border);
}

.containers-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-xs);
}

.containers-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.assigned-container-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 2px 8px;
  background: rgba(24, 144, 255, 0.1);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  cursor: grab;
  transition: all 0.2s;

  &:hover {
    background: rgba(24, 144, 255, 0.2);
  }

  &:active {
    cursor: grabbing;
  }

  &.dragging {
    opacity: 0.5;
    border-style: dashed;
  }

  &.drag-over {
    border-color: #52c41a;
    background: rgba(82, 196, 26, 0.1);
    border-style: dashed;
  }
}

.assigned-container-item .container-name {
  color: var(--color-primary);
  font-weight: 500;
}

.container-direction-select {
  padding: 1px 4px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  background: white;
  cursor: pointer;
  outline: none;

  &:focus {
    border-color: var(--color-primary);
  }
}

.remove-container-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  line-height: 1;

  &:hover {
    color: #e74c3c;
  }
}

.drop-zone-area {
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--color-border);
  min-height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;

  &.active {
    background: rgba(24, 144, 255, 0.1);
    border: 2px dashed var(--color-primary);
    margin: var(--spacing-xs) var(--spacing-sm);
    border-radius: var(--radius-sm);
  }
}

.drop-hint {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  font-weight: 500;
}

.drop-hint-placeholder {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-style: italic;
}

.children-container {
  padding: var(--spacing-xs) var(--spacing-sm) var(--spacing-sm);
  border-top: 1px solid var(--color-border);
  margin-top: var(--spacing-xs);
}
</style>
