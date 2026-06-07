<template>
  <div class="relation-category-node">
    <div class="node-content" :style="{ paddingLeft: level * 20 + 'px' }">
      <!-- 展开收起图标 -->
      <span
        v-if="node.children && node.children.length"
        class="expand-icon"
        :class="{ expanded: isExpanded }"
        @click="toggleExpand"
      >▶</span>
      <span v-else class="expand-icon placeholder"></span>
      
      <!-- 复选框 -->
      <label class="checkbox-label">
        <input
          type="checkbox"
          :checked="isSelected"
          :indeterminate="isIndeterminate"
          @change="handleToggle"
        />
        <span class="node-name">{{ node.displayName || node.name }}</span>
        <span class="node-stats">{{ nodeStats }}</span>
      </label>
    </div>
    
    <!-- 子节点 -->
    <div v-if="node.children && node.children.length && isExpanded" class="node-children">
      <RelationCategoryNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :selected-ids="selectedIds"
        :level="level + 1"
        @toggle="$emit('toggle', $event)"
      />
    </div>
  </div>
</template>

<script>
import { inject, watch, ref } from 'vue'

export default {
  name: 'RelationCategoryNode',
  props: {
    node: {
      type: Object,
      required: true
    },
    selectedIds: {
      type: Set,
      required: true
    },
    level: {
      type: Number,
      default: 0
    }
  },
  emits: ['toggle'],
  setup() {
    const triggerState = inject('triggerState', { expandCounter: 0, collapseCounter: 0 })
    const localExpanded = ref(false)
    
    watch(
      () => triggerState.expandCounter,
      () => {
        localExpanded.value = true
      }
    )
    
    watch(
      () => triggerState.collapseCounter,
      () => {
        localExpanded.value = false
      }
    )
    
    return {
      triggerState,
      localExpanded
    }
  },
  computed: {
    isExpanded() {
      return this.localExpanded
    },
    isSelected() {
      if (this.node.children && this.node.children.length > 0) {
        return this.areAllDescendantsSelected(this.node)
      }
      if (this.node.relationCodes && this.node.relationCodes.length > 0) {
        return this.node.relationCodes.every(code => this.selectedIds.has(code))
      }
      return this.selectedIds.has(this.node.id)
    },
    isIndeterminate() {
      if (this.node.children && this.node.children.length > 0) {
        const hasSelected = this.hasSelectedDescendants(this.node)
        const allSelected = this.areAllDescendantsSelected(this.node)
        return hasSelected && !allSelected
      }
      if (this.node.relationCodes && this.node.relationCodes.length > 0) {
        const selectedCount = this.node.relationCodes.filter(code => this.selectedIds.has(code)).length
        return selectedCount > 0 && selectedCount < this.node.relationCodes.length
      }
      return false
    },
    nodeStats() {
      const count = this.node.count || 0
      const childCount = this.node.childCount || 0
      
      if (this.level === 0) {
        return `(${count}条)`
      }
      
      if (childCount > 0) {
        return `(${count}条 · ${childCount}类)`
      }
      
      return `(${count}条)`
    }
  },
  methods: {
    toggleExpand() {
      this.localExpanded = !this.localExpanded
    },
    handleToggle(event) {
      const selected = event.target.checked
      this.$emit('toggle', { node: this.node, selected })
    },
    areAllDescendantsSelected(node) {
      // 如果节点有关系编码，检查所有关系编码是否被选中
      if (node.relationCodes && node.relationCodes.length > 0) {
        return node.relationCodes.every(code => this.selectedIds.has(code))
      }
      
      // 如果节点有子节点，递归检查
      if (node.children && node.children.length > 0) {
        return node.children.every(child => this.areAllDescendantsSelected(child))
      }
      
      // 叶子节点检查节点ID
      return this.selectedIds.has(node.id)
    },
    hasSelectedDescendants(node) {
      // 如果节点有关系编码，检查是否有关系编码被选中
      if (node.relationCodes && node.relationCodes.length > 0) {
        return node.relationCodes.some(code => this.selectedIds.has(code))
      }
      
      // 如果节点有子节点，递归检查
      if (node.children && node.children.length > 0) {
        return node.children.some(child => this.hasSelectedDescendants(child))
      }
      
      // 叶子节点检查节点ID
      return this.selectedIds.has(node.id)
    }
  }
}
</script>

<style scoped>
.relation-category-node {
  user-select: none;
}

.node-content {
  display: flex;
  align-items: center;
  padding: 6px 0;
  cursor: pointer;
  transition: background-color 0.2s;
}

.node-content:hover {
  background-color: #f5f5f5;
}

.expand-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 10px;
  color: #666;
  transition: transform 0.2s;
  flex-shrink: 0;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.expand-icon.placeholder {
  cursor: default;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex: 1;
}

.checkbox-label input[type="checkbox"] {
  cursor: pointer;
  width: 16px;
  height: 16px;
}

.node-name {
  font-size: 14px;
  color: #333;
}

.node-stats {
  font-size: 12px;
  color: #999;
  margin-left: 4px;
}

.node-children {
  border-left: 1px dashed #e0e0e0;
  margin-left: 10px;
}
</style>
