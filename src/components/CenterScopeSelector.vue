<template>
  <div class="center-scope-selector">
    <!-- 操作按钮 -->
    <div class="selector-actions">
      <button @click="selectAll" class="action-btn">全选</button>
      <button @click="clearAll" class="action-btn">清空</button>
      <button @click="expandAll" class="action-btn">展开</button>
      <button @click="collapseAll" class="action-btn">收起</button>
      <span class="selection-count">已选择 {{ selectedCount }} 个业务对象</span>
    </div>

    <!-- 树形选择器 -->
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
import { useMessage } from '@/composables/useMessage'
import TreeNode from './TreeNode.vue';

export default {
  name: 'CenterScopeSelector',
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
    presets: {
      type: Array,
      default: () => []
    }
  },
  emits: ['update:modelValue', 'save-preset', 'load-preset', 'delete-preset'],
  data() {
    return {
      selectedIds: new Set(this.modelValue),
      selectedPreset: ''
    };
  },
  setup() {
    const triggerState = reactive({
      expandCounter: 0,
      collapseCounter: 0
    });

    provide('triggerState', triggerState);

    return {
      triggerState
    };
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
  methods: {
    expandAll() {
      this.triggerState.expandCounter++;
    },
    collapseAll() {
      this.triggerState.collapseCounter++;
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
      // 递归计算节点的业务对象数量
      const countBusinessObjects = (node) => {
        if (node.isLeaf) {
          return 1;
        }
        if (!node.children || node.children.length === 0) {
          return 0;
        }
        let count = 0;
        node.children.forEach(child => {
          count += countBusinessObjects(child);
        });
        return count;
      };

      return this.domainProducts.map(domain => {
        const domainNode = {
          id: `domain-${domain.name}`,
          name: domain.name,
          type: 'domain',
          children: domain.modules ? domain.modules.map(module => {
            const moduleNode = {
              id: `module-${module.name}`,
              name: module.name,
              type: 'module',
              children: module.submodules ? module.submodules.map(submodule => {
                const submoduleNode = {
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
                };
                // 计算服务模块的业务对象数量
                submoduleNode.boCount = countBusinessObjects(submoduleNode);
                return submoduleNode;
              }) : []
            };
            // 计算子领域的业务对象数量
            moduleNode.boCount = countBusinessObjects(moduleNode);
            return moduleNode;
          }) : []
        };
        // 计算领域的业务对象数量
        domainNode.boCount = countBusinessObjects(domainNode);
        return domainNode;
      });
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
      this.selectedPreset = '';
      this.emitUpdate();
    },
    // 保存预设
    async handleSavePreset() {
      const selectedArray = Array.from(this.selectedIds);
      if (selectedArray.length === 0) {
        this.message.warning('请先选择业务对象');
        return;
      }
      const presetName = prompt('请输入预设名称：');
      if (presetName && presetName.trim()) {
        this.$emit('save-preset', {
          name: presetName.trim(),
          selectedIds: selectedArray
        });
      }
    },
    // 加载预设
    handleLoadPreset() {
      if (!this.selectedPreset) {
        return;
      }
      const preset = this.presets.find(p => p.id === this.selectedPreset);
      if (preset) {
        // 优先使用 centerScope，兼容旧版本的 selectedIds
        const scopeIds = preset.centerScope || preset.selectedIds;
        if (scopeIds && scopeIds.length > 0) {
          this.selectedIds = new Set(scopeIds);
          this.emitUpdate();
        }
        this.$emit('load-preset', preset);
      }
    },
    // 删除预设
    async handleDeletePreset() {
      if (!this.selectedPreset) {
        return;
      }
      const preset = this.presets.find(p => p.id === this.selectedPreset);
      if (preset) {
        const confirmed = await this.message.confirm({ content: `确定要删除预设 "${preset.name}" 吗？` })
        if (confirmed) {
          this.$emit('delete-preset', this.selectedPreset);
          this.selectedPreset = '';
        }
      }
    }
  }
};
</script>

<style scoped>
.center-scope-selector {
  margin-bottom: 20px;
  padding: 15px;
  background: #f5f5f5;
  border-radius: 4px;
}

.preset-section {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.preset-select {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  background: #fff;
  cursor: pointer;
}

.preset-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.preset-btn {
  padding: 8px 16px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.preset-btn:hover {
  background: var(--color-primary-hover);
}

.preset-btn.delete-btn {
  background: #ff4d4f;
}

.preset-btn.delete-btn:hover {
  background: #ff7875;
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
