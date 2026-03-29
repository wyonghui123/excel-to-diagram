<template>
  <div class="layout-control-panel">
    <div class="panel-header">
      <label class="enable-switch">
        <input
          type="checkbox"
          :checked="localConfig.enabled"
          @change="toggleEnabled"
        />
        <span class="switch-label">启用分组控制</span>
      </label>
    </div>

    <div v-if="localConfig.enabled" class="panel-content">
      <div class="containers-section">
        <div class="section-title">未分配容器</div>
        <div class="containers-pool">
          <div
            v-for="(container, idx) in unassignedContainers"
            :key="container.id"
            class="container-item"
            draggable="true"
            @dragstart="handleDragStart($event, container, idx)"
            @dragend="handleDragEnd"
          >
            {{ container.name }}
          </div>
          <div v-if="unassignedContainers.length === 0" class="pool-empty">
            所有容器已分配到分组
          </div>
        </div>
      </div>

      <div class="groups-section">
        <div class="section-title">分组列表</div>
        <div class="groups-container">
          <div v-if="localConfig.groups.length === 0" class="empty-hint">
            暂无分组，点击下方按钮添加
          </div>

          <GroupItem
            v-for="(group, idx) in localConfig.groups"
            :key="group.id"
            :group="group"
            :depth="0"
            :containers="containers"
            :index="idx"
            @update="handleGroupUpdate"
            @delete="handleGroupDelete"
            @add-child="handleAddChild"
            @assign-container="handleAssignContainer"
            @remove-container="handleRemoveContainer"
            @reorder-groups="handleReorderGroups"
          />
        </div>

        <button class="add-group-btn" @click="handleAddGroup">
          <span class="btn-icon">+</span>
          <span>添加分组</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import GroupItem from './GroupItem.vue'

const props = defineProps({
  containers: {
    type: Array,
    default: () => []
  },
  modelValue: {
    type: Object,
    default: () => ({
      enabled: false,
      groups: [],
      engine: 'dagre',
      preserveOrder: true
    })
  }
})

const emit = defineEmits(['update:modelValue'])

const localConfig = ref({
  enabled: false,
  groups: [],
  engine: 'dagre',
  preserveOrder: true,
  overallDirection: 'TB'
})

const draggingContainer = ref(null)
const draggingIndex = ref(-1)

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    localConfig.value = JSON.parse(JSON.stringify(newVal))
  }
}, { immediate: true, deep: true })

function getAllAssignedContainerIds(groups) {
  const ids = new Set()
  for (const group of groups) {
    if (group.containers && Array.isArray(group.containers)) {
      group.containers.forEach(c => {
        if (typeof c === 'object' && c.id) {
          ids.add(c.id)
        } else if (typeof c === 'string') {
          ids.add(c)
        }
      })
    }
    if (group.children && group.children.length > 0) {
      const childIds = getAllAssignedContainerIds(group.children)
      childIds.forEach(id => ids.add(id))
    }
  }
  return ids
}

const unassignedContainers = computed(() => {
  const assignedIds = getAllAssignedContainerIds(localConfig.value.groups)
  return props.containers.filter(c => !assignedIds.has(c.id))
})

function generateGroupId() {
  return `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

function getDefaultGroup(title, parentId) {
  return {
    id: generateGroupId(),
    title,
    direction: 'TB',
    visible: true,
    style: {
      fill: '#f5f5f5',
      stroke: '#333333',
      strokeWidth: 1,
      strokeDasharray: ''
    },
    containers: [],
    children: [],
    parentId
  }
}

function emitUpdate() {
  emit('update:modelValue', JSON.parse(JSON.stringify(localConfig.value)))
}

function toggleEnabled() {
  localConfig.value.enabled = !localConfig.value.enabled
  emitUpdate()
}

function handleAddGroup() {
  const newGroup = getDefaultGroup(`分组 ${localConfig.value.groups.length + 1}`)
  localConfig.value.groups.push(newGroup)
  emitUpdate()
}

function findGroupById(groups, id) {
  for (const group of groups) {
    if (group.id === id) return group
    const found = findGroupById(group.children, id)
    if (found) return found
  }
  return null
}

function updateGroupInTree(groups, id, updates) {
  for (let i = 0; i < groups.length; i++) {
    if (groups[i].id === id) {
      const { id: _, children: __, parentId: ___, ...safeUpdates } = updates
      Object.assign(groups[i], safeUpdates)
      return true
    }
    if (updateGroupInTree(groups[i].children, id, updates)) {
      return true
    }
  }
  return false
}

function deleteGroupFromTree(groups, id) {
  const index = groups.findIndex(g => g.id === id)
  if (index !== -1) {
    groups.splice(index, 1)
    return true
  }
  for (const group of groups) {
    if (deleteGroupFromTree(group.children, id)) {
      return true
    }
  }
  return false
}

function getGroupDepth(groups, id, depth) {
  for (const group of groups) {
    if (group.id === id) return depth
    const found = getGroupDepth(group.children, id, depth + 1)
    if (found !== -1) return found
  }
  return -1
}

function handleGroupUpdate({ id, updates }) {
  updateGroupInTree(localConfig.value.groups, id, updates)
  emitUpdate()
}

function handleGroupDelete(id) {
  deleteGroupFromTree(localConfig.value.groups, id)
  emitUpdate()
}

function handleAddChild(parentId) {
  const parentDepth = getGroupDepth(localConfig.value.groups, parentId, 1)
  if (parentDepth >= 3) {
    console.warn('Cannot create child group: maximum depth of 3 levels reached')
    return
  }

  const parent = findGroupById(localConfig.value.groups, parentId)
  if (parent) {
    const newGroup = getDefaultGroup(`${parent.title}-子分组`, parentId)
    parent.children.push(newGroup)
    emitUpdate()
  }
}

function handleDragStart(event, container, idx) {
  draggingContainer.value = container
  draggingIndex.value = idx
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'container',
    container: container,
    sourceType: 'unassigned',
    sourceIndex: idx
  }))
}

function handleDragEnd() {
  draggingContainer.value = null
  draggingIndex.value = -1
}

function handleAssignContainer({ groupId, container }) {
  const group = findGroupById(localConfig.value.groups, groupId)
  if (group) {
    if (!group.containers) {
      group.containers = []
    }
    const existingIndex = group.containers.findIndex(c => 
      (typeof c === 'object' && c.id === container.id) || c === container.id
    )
    if (existingIndex === -1) {
      group.containers.push(container)
      emitUpdate()
    }
  }
}

function handleRemoveContainer({ groupId, containerId }) {
  const group = findGroupById(localConfig.value.groups, groupId)
  if (group && group.containers) {
    const idx = group.containers.findIndex(c => 
      (typeof c === 'object' && c.id === containerId) || c === containerId
    )
    if (idx !== -1) {
      group.containers.splice(idx, 1)
      emitUpdate()
    }
  }
}

function handleReorderGroups({ sourceIndex, targetIndex }) {
  if (sourceIndex !== targetIndex) {
    const newGroups = [...localConfig.value.groups]
    const [removed] = newGroups.splice(sourceIndex, 1)
    newGroups.splice(targetIndex, 0, removed)
    localConfig.value.groups = newGroups
    emitUpdate()
  }
}
</script>

<style scoped lang="scss">
.layout-control-panel {
  padding: var(--spacing-md);
}

.panel-header {
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
}

.enable-switch {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;

  input {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }
}

.switch-label {
  font-weight: 500;
  color: var(--color-text-primary);
}

.panel-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.overall-direction-section {
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.direction-select {
  width: 100%;
  padding: var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  background: white;
  cursor: pointer;

  &:focus {
    outline: none;
    border-color: var(--color-primary);
  }
}

.section-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.containers-section {
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.containers-pool {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  min-height: 40px;
}

.container-item {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: white;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  cursor: grab;
  transition: all 0.2s;
  user-select: none;

  &:hover {
    border-color: var(--color-primary);
    background: rgba(24, 144, 255, 0.05);
  }

  &:active {
    cursor: grabbing;
    opacity: 0.7;
  }
}

.pool-empty {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-style: italic;
  padding: var(--spacing-sm);
}

.groups-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.groups-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.empty-hint {
  padding: var(--spacing-lg);
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.add-group-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 0.2s;

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: rgba(24, 144, 255, 0.05);
  }

  .btn-icon {
    font-size: 16px;
    font-weight: bold;
  }
}
</style>
