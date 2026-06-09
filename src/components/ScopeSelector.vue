<!--
  @deprecated 2026-06-10
  旧版范围选择器，仅被已废弃的 DataPreview.vue 引用（链式依赖）。
  范围选择功能已迁移到 views/AADiagramApp/components/steps/StepScope.vue（CenterScopeSelector）。
  新版使用 el-tree 实现，不再需要自实现 TreeNode。
  无生产代码引用（grep 验证通过），保留仅为历史记录。
  建议下一轮清理时删除。
  替代: views/AADiagramApp/components/steps/StepScope.vue
-->
<template>
  <div class="scope-selector">
    <div class="selector-actions">
      <button @click="selectAll" class="action-btn">全选</button>
      <button @click="clearAll" class="action-btn">清空</button>
      <button @click="expandAll" class="action-btn">展开</button>
      <button @click="collapseAll" class="action-btn">收起</button>
    </div>
    <div class="tree-container">
      <TreeNode
        v-for="domain in treeData"
        :key="domain.id"
        :node="domain"
        :selected-ids="selectedIds"
        @toggle="handleNodeToggle"
      />
    </div>
  </div>
</template>

<script>
import { ref, provide, reactive } from 'vue'
import TreeNode from './TreeNode.vue';

export default {
  name: 'ScopeSelector',
  components: {
    TreeNode
  },
  props: {
    domainProducts: {
      type: Array,
      default: () => []
    },
    businessObjects: {
      type: Array,
      default: () => []
    },
    modelValue: {
      type: Array,
      default: () => []
    },
    autoSelectAll: {
      type: Boolean,
      default: false
    }
  },
  emits: ['update:modelValue'],
  data() {
    return {
      selectedIds: new Set(this.modelValue)
    };
  },
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
  computed: {
    treeData() {
      return this.buildTreeData();
    },
    selectedCount() {
      // 只计算业务对象（叶子节点）
      let count = 0;
      this.domainProducts.forEach(domain => {
        if (domain.modules) {
          domain.modules.forEach(module => {
            if (module.submodules) {
              module.submodules.forEach(submodule => {
                if (submodule.businessObjects) {
                  submodule.businessObjects.forEach(bo => {
                    const boId = typeof bo === 'string' ? bo : (bo.code || bo.name);
                    if (this.selectedIds.has(boId)) {
                      count++;
                    }
                  });
                }
              });
            }
          });
        }
      });
      return count;
    }
  },
  watch: {
    modelValue: {
      handler(newVal) {
        // 避免循环更新，只在值真正改变时才更新
        const newSet = new Set(newVal);
        if (this.setsAreEqual(newSet, this.selectedIds)) {
          return;
        }
        this.selectedIds = newSet;
      },
      deep: true
    }
  },
  mounted() {
    if (this.autoSelectAll && (!this.modelValue || this.modelValue.length === 0)) {
      this.$nextTick(() => {
        this.selectAll();
      });
    }
  },
  methods: {
    expandAll() {
      this.triggerState.expandCounter++
    },
    collapseAll() {
      this.triggerState.collapseCounter++
    },
    // 比较两个Set是否相等
    setsAreEqual(setA, setB) {
      if (setA.size !== setB.size) return false;
      for (const item of setA) {
        if (!setB.has(item)) return false;
      }
      return true;
    },
    // 触发更新事件
    emitUpdate() {
      this.$emit('update:modelValue', Array.from(this.selectedIds));
    },
    buildTreeData() {
      console.log('[buildTreeData] domainProducts:', JSON.stringify(this.domainProducts, null, 2).substring(0, 2000));
      return this.domainProducts.map(domain => ({
        id: `domain-${domain.name}`,
        name: domain.name,
        type: 'domain',
        children: domain.modules ? domain.modules.map(module => ({
          id: `module-${module.name}`,
          name: module.name,
          type: 'module',
          children: module.submodules ? module.submodules.map(submodule => ({
            id: `submodule-${submodule.code || submodule.name}`,
            name: `${submodule.name} (${submodule.code})`,
            type: 'submodule',
            children: submodule.businessObjects ? submodule.businessObjects.map(bo => {
              const boId = typeof bo === 'string' ? bo : (bo.code || bo.name);
              const boName = typeof bo === 'string' ? bo : (bo.name || bo.code);
              return {
                id: boId,
                name: boName,
                type: 'businessObject',
                isLeaf: true
              };
            }) : []
          })) : []
        })) : []
      }));
    },
    handleNodeToggle({ node, selected }) {
      const newSelectedIds = new Set(this.selectedIds);
      
      if (selected) {
        // 选择节点及其所有子孙节点
        this.selectNodeAndDescendants(node, newSelectedIds);
      } else {
        // 取消选择节点及其所有子孙节点
        this.deselectNodeAndDescendants(node, newSelectedIds);
      }
      
      this.selectedIds = newSelectedIds;
      this.emitUpdate();
    },
    selectNodeAndDescendants(node, selectedIds) {
      // 如果是叶子节点（业务对象），添加到选择集
      if (node.isLeaf) {
        selectedIds.add(node.id);
      }
      
      // 递归处理子节点
      if (node.children) {
        node.children.forEach(child => {
          this.selectNodeAndDescendants(child, selectedIds);
        });
      }
    },
    deselectNodeAndDescendants(node, selectedIds) {
      // 如果是叶子节点（业务对象），从选择集中移除
      if (node.isLeaf) {
        selectedIds.delete(node.id);
      }
      
      // 递归处理子节点
      if (node.children) {
        node.children.forEach(child => {
          this.deselectNodeAndDescendants(child, selectedIds);
        });
      }
    },
    selectAll() {
      const allIds = new Set();
      console.log('[ScopeSelector selectAll] treeData domains:', this.treeData.length);
      console.log('[ScopeSelector selectAll] businessObjects:', this.businessObjects?.length || 0);
      this.treeData.forEach(domain => {
        this.selectNodeAndDescendants(domain, allIds);
      });
      if (this.businessObjects && this.businessObjects.length > 0) {
        const treeBoIds = new Set();
        this.treeData.forEach(domain => {
          this.collectBoIds(domain, treeBoIds);
        });
        this.businessObjects.forEach(bo => {
          const boId = bo.code || bo.name;
          if (!treeBoIds.has(boId)) {
            allIds.add(boId);
          }
        });
      }
      console.log('[ScopeSelector selectAll] allIds has PLD00604:', allIds.has('PLD00604'));
      console.log('[ScopeSelector selectAll] allIds size:', allIds.size);
      this.selectedIds = allIds;
      this.emitUpdate();
    },
    collectBoIds(node, boIds) {
      if (node.isLeaf) {
        boIds.add(node.id);
      }
      if (node.children) {
        node.children.forEach(child => this.collectBoIds(child, boIds));
      }
    },
    clearAll() {
      this.selectedIds = new Set();
      this.emitUpdate();
    }
  }
};
</script>

<style scoped>
.scope-selector {
  margin-bottom: 20px;
  padding: 15px;
  background: #f5f5f5;
  border-radius: 4px;
}

.scope-selector h3 {
  margin: 0 0 15px 0;
  color: #333;
  font-size: 16px;
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

.selection-count {
  margin-left: auto;
  font-size: 13px;
  color: #666;
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
