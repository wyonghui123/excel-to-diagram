<template>
  <div class="tree-node" :class="{ 'is-leaf': node.isLeaf }">
    <div class="node-content" :style="{ paddingLeft: level * 20 + 'px' }">
      <span
        v-if="!node.isLeaf"
        class="expand-icon"
        :class="{ expanded: localExpanded }"
        @click="toggleExpand"
      >
        <AppIcon name="chevron-right" size="sm" />
      </span>
      <span v-else class="expand-icon placeholder"></span>
      
      <label class="checkbox-label">
        <input
          type="checkbox"
          :checked="isSelected"
          :indeterminate="isIndeterminate"
          @change="handleToggle"
        />
        <span class="node-name">{{ node.name }}</span>
        <span v-if="node.type === 'businessObject'" class="node-type">业务对象</span>
        <span v-else-if="node.type === 'submodule'" class="node-type">服务模块({{ node.boCount || 0 }})</span>
        <span v-else-if="node.type === 'module'" class="node-type">子领域({{ node.boCount || 0 }})</span>
        <span v-else-if="node.type === 'domain'" class="node-type">领域({{ node.boCount || 0 }})</span>
      </label>
    </div>
    
    <div v-if="!node.isLeaf && localExpanded" class="node-children">
      <TreeNode
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
import { AppIcon } from '@/components/common/AppIcon'

export default {
  name: 'TreeNode',
  components: {
    AppIcon
  },
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
  computed: {
    isSelected() {
      if (this.node.isLeaf) {
        return this.selectedIds.has(this.node.id);
      }
      // 非叶子节点：只有当所有子节点都被选中时才选中
      return this.areAllDescendantsSelected(this.node);
    },
    isIndeterminate() {
      if (this.node.isLeaf) return false;
      // 非叶子节点：部分选中状态（有选中的但不是全部）
      const hasSelected = this.hasSelectedDescendants(this.node);
      const allSelected = this.areAllDescendantsSelected(this.node);
      return hasSelected && !allSelected;
    }
  },
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
  methods: {
    toggleExpand() {
      this.localExpanded = !this.localExpanded;
    },
    handleToggle(event) {
      const selected = event.target.checked;
      this.$emit('toggle', { node: this.node, selected });
    },
    areAllDescendantsSelected(node) {
      if (node.isLeaf) {
        return this.selectedIds.has(node.id);
      }
      if (!node.children || node.children.length === 0) return false;
      return node.children.every(child => this.areAllDescendantsSelected(child));
    },
    hasSelectedDescendants(node) {
      if (node.isLeaf) {
        return this.selectedIds.has(node.id);
      }
      if (!node.children || node.children.length === 0) return false;
      return node.children.some(child => this.hasSelectedDescendants(child));
    }
  }
};
</script>

<style scoped>
.tree-node {
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
  accent-color: var(--color-primary);
}

.node-name {
  font-size: 14px;
  color: #333;
}

.node-type {
  font-size: 11px;
  color: #999;
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
  margin-left: 8px;
}

.node-children {
  border-left: 1px dashed #e0e0e0;
  margin-left: 10px;
}

.is-leaf .node-name {
  color: #666;
}
</style>
