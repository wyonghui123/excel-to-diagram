<template>
  <div class="relation-category-tree">
    <div class="selector-actions">
      <button @click="selectAll" class="action-btn">全选</button>
      <button @click="clearAll" class="action-btn">清空</button>
      <button @click="expandAll" class="action-btn">展开</button>
      <button @click="collapseAll" class="action-btn">收起</button>
    </div>
    <div class="tree-container">
      <RelationCategoryNode
        v-for="node in treeData"
        :key="node.id"
        :node="node"
        :selected-ids="selectedNodeIdsSet"
        :level="0"
        @toggle="handleNodeToggle"
      />
    </div>
  </div>
</template>

<script>
import { ref, provide, reactive, computed, watch } from 'vue'
import RelationCategoryNode from './RelationCategoryNode.vue'

export default {
  name: 'RelationCategoryTree',
  components: {
    RelationCategoryNode
  },
  props: {
    treeData: {
      type: Array,
      default: () => []
    },
    selectedNodeIds: {
      type: Array,
      default: () => []
    }
  },
  emits: ['update:selectedNodeIds', 'node-toggle'],
  setup() {
    const triggerState = reactive({
      expandCounter: 0,
      collapseCounter: 0
    })
    
    provide('triggerState', triggerState)
    
    return {
      triggerState
    }
  },
  data() {
    return {
      selectedNodeIdsSet: new Set(this.selectedNodeIds)
    }
  },
  computed: {
    selectedCount() {
      return this.selectedNodeIdsSet.size
    }
  },
  watch: {
    selectedNodeIds: {
      handler(newVal) {
        const newSet = new Set(newVal)
        if (this.setsAreEqual(newSet, this.selectedNodeIdsSet)) {
          return
        }
        this.selectedNodeIdsSet = newSet
      },
      deep: true
    }
  },
  methods: {
    expandAll() {
      this.triggerState.expandCounter++
    },
    collapseAll() {
      this.triggerState.collapseCounter++
    },
    setsAreEqual(setA, setB) {
      if (setA.size !== setB.size) return false
      for (const item of setA) {
        if (!setB.has(item)) return false
      }
      return true
    },
    emitUpdate() {
      this.$emit('update:selectedNodeIds', Array.from(this.selectedNodeIdsSet))
    },
    handleNodeToggle({ node, selected }) {
      const newSelectedIds = new Set(this.selectedNodeIdsSet)
      
      if (selected) {
        this.selectNodeAndDescendants(node, newSelectedIds)
      } else {
        this.deselectNodeAndDescendants(node, newSelectedIds)
      }
      
      this.selectedNodeIdsSet = newSelectedIds
      this.emitUpdate()
      
      // 触发 node-toggle 事件
      this.$emit('node-toggle', { node, selected })
    },
    selectNodeAndDescendants(node, selectedIds) {
      // 如果节点有关系编码，添加所有关系编码
      if (node.relationCodes && node.relationCodes.length > 0) {
        node.relationCodes.forEach(code => selectedIds.add(code))
      }
      
      // 添加节点ID
      selectedIds.add(node.id)
      
      // 递归处理子节点
      if (node.children && node.children.length > 0) {
        node.children.forEach(child => {
          this.selectNodeAndDescendants(child, selectedIds)
        })
      }
    },
    deselectNodeAndDescendants(node, selectedIds) {
      // 如果节点有关系编码，移除所有关系编码
      if (node.relationCodes && node.relationCodes.length > 0) {
        node.relationCodes.forEach(code => selectedIds.delete(code))
      }
      
      // 移除节点ID
      selectedIds.delete(node.id)
      
      // 递归处理子节点
      if (node.children && node.children.length > 0) {
        node.children.forEach(child => {
          this.deselectNodeAndDescendants(child, selectedIds)
        })
      }
    },
    selectAll() {
      const allIds = new Set()
      this.treeData.forEach(node => {
        this.selectNodeAndDescendants(node, allIds)
      })
      this.selectedNodeIdsSet = allIds
      this.emitUpdate()
    },
    clearAll() {
      this.selectedNodeIdsSet = new Set()
      this.emitUpdate()
    }
  }
}
</script>

<style scoped>
.relation-category-tree {
  margin-bottom: 20px;
  padding: 15px;
  background: #f5f5f5;
  border-radius: 4px;
}

.selector-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.action-btn {
  padding: 6px 12px;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.action-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.tree-container {
  max-height: 400px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 10px;
}
</style>
